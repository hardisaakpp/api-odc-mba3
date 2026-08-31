"""
Puente Redis pub/sub entre los workers de Celery y el bus de notificaciones SSE.

Problema que resuelve:
    src/utils/notification_manager.py mantiene, en memoria, una asyncio.Queue por
    cliente SSE conectado. Esas colas viven únicamente dentro del proceso del
    servidor FastAPI (contenedor mba3-api). Un worker de Celery (mba3-celery-worker)
    o Celery Beat (mba3-celery-beat) corre en un proceso del sistema operativo
    aparte -- llamar a notification_manager.notify(...) directamente desde ahí no
    tiene ningún efecto real (sería un singleton distinto, sin listeners) y además
    no es seguro: los primitivos de asyncio (Queue, Future) no son thread-safe ni
    cross-process.

Solución:
    1. Un worker de Celery llama a publish_notification_from_worker(...) (síncrona,
       best-effort, usa el mismo cliente redis-py singleton que ya usa
       ProcesoEstadoService) para publicar un mensaje JSON en un canal Redis.
    2. El proceso FastAPI arranca, en su propio event loop, un listener en segundo
       plano (escuchar_notificaciones_redis, iniciado desde src/api_server.py) que
       se suscribe a ese canal y reenvía cada mensaje a notification_manager.notify(...)
       -- esto SÍ es seguro porque corre en el mismo event loop que las colas SSE.

Igual que el resto del sistema de notificaciones, es best-effort: un fallo al
publicar o al reenviar solo se registra en logs, nunca rompe el flujo de negocio
(el envío a SAP, la reconciliación, etc. ya reportan su propio resultado por otros
canales -- email, estado en BD/Redis).
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from src.config import REDIS_URL

logger = logging.getLogger(__name__)

SSE_NOTIFICATIONS_REDIS_CHANNEL = "mba3:sse:notifications"

# Backoff de reconexión del listener si se cae la conexión a Redis (no debe
# reintentar en un loop apretado ni tampoco tardar minutos en recuperarse).
_RECONEXION_SEGUNDOS = 5


def publish_notification_from_worker(
    target_permission: str,
    title: str,
    message: str,
    notification_type: str = "info",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Publica una notificación desde un worker de Celery (proceso aparte de mba3-api).

    Síncrona y best-effort: si Redis no está disponible o falla la publicación, solo
    se registra un warning -- nunca debe romper la tarea de Celery que la dispara
    (el envío a SAP, la reconciliación automática, etc. ya reportan su resultado real
    por otros canales: estado en BD/Redis, email, logs).
    """
    try:
        from src.database.services.proceso_estado_service import get_redis_client

        payload = json.dumps({
            "target_permission": target_permission,
            "title": title,
            "message": message,
            "notification_type": notification_type,
            "metadata": metadata or {},
        })
        get_redis_client().publish(SSE_NOTIFICATIONS_REDIS_CHANNEL, payload)
    except Exception as e:
        logger.warning(f"⚠️ No se pudo publicar notificación SSE desde worker Celery (no crítico): {e}")


def publish_notification_from_worker_multi(
    target_permissions: List[str],
    title: str,
    message: str,
    notification_type: str = "info",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Igual que publish_notification_from_worker, pero a varios permisos a la vez
    (ej. odcsap.view y mabel.view) -- una publicación independiente por permiso."""
    for permiso in target_permissions:
        publish_notification_from_worker(permiso, title, message, notification_type, metadata)


async def _reenviar_mensaje(raw_data: str) -> None:
    from src.utils.notification_manager import notification_manager, NotificationType

    data = json.loads(raw_data)
    await notification_manager.notify(
        target_permission=data["target_permission"],
        title=data["title"],
        message=data["message"],
        notification_type=NotificationType(data.get("notification_type", "info")),
        metadata=data.get("metadata") or {},
    )


async def _procesar_mensajes_redis(pubsub, ready_event: Optional[asyncio.Event]) -> None:
    """Marca ready_event (si se indica) y reenvía cada mensaje recibido por `pubsub`
    -- ya suscrito por el llamador -- hasta que la conexión se caiga o se cancele
    (ver escuchar_notificaciones_redis)."""
    if ready_event is not None:
        ready_event.set()
    async for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        try:
            await _reenviar_mensaje(message["data"])
        except Exception as e:
            logger.warning(f"⚠️ Notificación SSE de Celery descartada (mensaje inválido): {e}")


async def _cerrar_conexion_redis(pubsub, client) -> None:
    """Cierra pubsub/cliente de Redis del listener, best-effort (ver
    escuchar_notificaciones_redis): un fallo al cerrar no debe impedir el
    reintento de conexión."""
    try:
        if pubsub is not None:
            await pubsub.aclose()
        if client is not None:
            await client.aclose()
    except Exception:
        pass


async def escuchar_notificaciones_redis(ready_event: Optional[asyncio.Event] = None) -> None:
    """Tarea de fondo (iniciada en el startup de FastAPI, ver src/api_server.py): se
    suscribe al canal Redis de notificaciones y reenvía cada mensaje a
    notification_manager.notify(...) -- corre en el event loop principal, el mismo
    donde viven las colas SSE, así que es seguro tocarlas desde aquí.

    Reconecta automáticamente si se cae la conexión a Redis (Redis reiniciando,
    caída de red); se detiene limpiamente si se cancela la tarea (shutdown de FastAPI).

    ready_event: si se indica, se marca (set()) justo después de que el SUBSCRIBE a
    Redis queda confirmado -- lo usan los tests para esperar a que la suscripción esté
    realmente activa antes de publicar (un mensaje publicado antes de que el SUBSCRIBE
    se confirme en el servidor se pierde, por semántica normal de pub/sub de Redis).
    """
    import redis.asyncio as redis_asyncio

    logger.info(f"📡 Listener SSE↔Redis iniciado (canal: {SSE_NOTIFICATIONS_REDIS_CHANNEL})")
    while True:
        client = None
        pubsub = None
        try:
            client = redis_asyncio.from_url(REDIS_URL, decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.subscribe(SSE_NOTIFICATIONS_REDIS_CHANNEL)
            await _procesar_mensajes_redis(pubsub, ready_event)
        except asyncio.CancelledError:
            logger.info("📡 Listener SSE↔Redis detenido (shutdown)")
            raise
        except Exception as e:
            logger.warning(
                f"⚠️ Listener SSE↔Redis perdió la conexión a Redis, reintentando en "
                f"{_RECONEXION_SEGUNDOS}s: {e}"
            )
            await asyncio.sleep(_RECONEXION_SEGUNDOS)
        finally:
            await _cerrar_conexion_redis(pubsub, client)
