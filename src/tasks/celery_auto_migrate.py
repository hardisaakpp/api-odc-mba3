"""
Tarea de migración automática ejecutada por Celery.

⚠️ IMPORTANTE: Este código corre en un PROCESO SEPARADO.
NO comparte recursos con FastAPI (no hay cuello de botella).

Características:
- Proceso aislado que no afecta al proceso manual
- Reintentos automáticos en caso de error
- Notificaciones por email
- Manejo robusto de conexiones (context manager)
- Invalidación de caché después de migrar

El proceso manual (/migrar/completo) NO usa este código.
"""

import logging
import time
import os

from src.utils.timezone import ahora_naive
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from src.celery_app import celery_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers de módulo (cada uno es responsable de una sola etapa del proceso)
# ---------------------------------------------------------------------------

def _normalizar_resultado(result):
    if result is None:
        return []
    if not isinstance(result, (list, dict)):
        return [result] if result else []
    return result


def _contar_resultado(result) -> int:
    if isinstance(result, list):
        return len(result)
    return 1 if result else 0


def _consultar_mba3(client, query):
    """Ejecuta la consulta MBA3 con reintento ante 'Object or Collection Expected'.

    Returns:
        (result, is_retry) — result normalizado, is_retry indica si se reintentó.
    Raises:
        MBA3QueryError: si el error no es recuperable.
    """
    from src.exceptions import MBA3QueryError

    try:
        result = client.execute_query(query, require_jwt=True)
        return _normalizar_resultado(result), False
    except MBA3QueryError as query_error:
        if "object or collection expected" not in str(query_error).lower():
            raise
        logger.warning("⚠️ Error 'Object or Collection Expected' en primer intento")
        logger.info("⏳ Esperando 15 segundos y reintentando...")
        time.sleep(15)
        logger.info("🔄 Reintentando consulta después de espera...")
        result = client.execute_query(query, require_jwt=True)
        logger.info("✅ Reintento exitoso")
        return _normalizar_resultado(result), True


def _notificar_migracion(facturas_guardadas, facturas_actualizadas, total_detalles, fecha_ejecucion):
    from src.utils.email_notifier import send_migration_notification

    if facturas_guardadas > 0:
        logger.info("📧 Enviando notificación por email (nuevos registros)...")
        send_migration_notification(
            facturas_guardadas=facturas_guardadas,
            facturas_actualizadas=facturas_actualizadas,
            total_detalles=total_detalles,
            fecha_ejecucion=fecha_ejecucion,
        )
    else:
        logger.info("⏭️ No hay nuevos registros, no se envía email")


def _notificar_homologacion(homologacion_service, fecha_ejecucion):
    from src.utils.email_notifier import send_homologacion_notification
    from src.database.connection import get_db_connection
    from src.database.repositories.homologacion_repository import HomologacionRepository

    todos_productos = homologacion_service.get_todos_productos_no_homologados()
    productos_no_homologados = todos_productos.get("productos", [])
    estadisticas = todos_productos.get("estadisticas", {})

    if not productos_no_homologados:
        logger.debug("✅ No hay productos no homologados para notificar")
        return

    logger.info(f"⚠️ Detectados {len(productos_no_homologados)} productos no homologados en total")
    conn = None
    try:
        conn = get_db_connection()
        repository = HomologacionRepository(conn)
        logger.info("📧 Enviando notificación de productos no homologados...")
        email_enviado = send_homologacion_notification(
            productos_no_homologados=productos_no_homologados,
            estadisticas=estadisticas,
            fecha_ejecucion=fecha_ejecucion,
            filtrar_ya_notificados=True,
            homologacion_repository=repository,
        )
        if email_enviado:
            logger.info("✅ Notificación de homologación enviada (solo productos nuevos)")
        else:
            logger.info("⏭️ No se envió notificación (todos ya fueron notificados)")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _invalidar_cache():
    from src.endpoints.despachos_info import invalidate_despachos_cache
    from src.endpoints.ordenes_compra import invalidate_ordenes_compra_cache

    invalidate_despachos_cache()
    invalidate_ordenes_compra_cache()
    logger.debug("🗑️ Caché invalidado después de migración automática")


def _notificar_error_retry(error, fecha_ejecucion):
    try:
        from src.utils.email_notifier import send_error_notification
        send_error_notification(
            error_message=str(error),
            fecha_ejecucion=fecha_ejecucion,
        )
    except Exception as email_error:
        logger.error(f"Error al enviar notificación de error: {email_error}")


# ---------------------------------------------------------------------------
# Clase base y tarea Celery
# ---------------------------------------------------------------------------

class AutoMigrationTask(Task):
    """
    Clase base para tarea de migración automática.

    Características:
    - Reintentos automáticos en caso de error de conexión
    - Limpieza de recursos garantizada
    - Notificaciones de errores por email
    """

    # Reintentar automáticamente en caso de errores de conexión
    autoretry_for = (ConnectionError, TimeoutError)
    retry_kwargs = {'max_retries': 2, 'countdown': 120}  # 2 reintentos, esperar 2 minutos
    retry_backoff = True  # Backoff exponencial
    retry_jitter = True  # Agregar jitter aleatorio

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Se ejecuta cuando la tarea falla definitivamente.

        Limpia recursos y envía notificación de error.
        """
        logger.error(f"❌ Migración automática falló definitivamente: {exc}")
        logger.error(f"   Task ID: {task_id}")
        logger.error(f"   Detalles: {einfo}")

        # Enviar notificación de error por email
        try:
            from src.utils.email_notifier import send_error_notification
            send_error_notification(
                error_message=str(exc),
                fecha_ejecucion=ahora_naive()
            )
            logger.info("📧 Notificación de error enviada por email")
        except Exception as email_error:
            logger.error(f"Error al enviar email de notificación: {email_error}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Se ejecuta cuando la tarea se va a reintentar"""
        logger.warning(f"⚠️ Reintentando migración automática: {exc}")
        logger.warning(f"   Task ID: {task_id}")


@celery_app.task(
    name='src.tasks.celery_auto_migrate.execute_auto_migration',
    base=AutoMigrationTask,
    bind=True,
    time_limit=600,  # 10 minutos máximo
    soft_time_limit=540  # Aviso después de 9 minutos
)
def execute_auto_migration(self):
    """
    Tarea de migración automática ejecutada por Celery.

    ⚠️ Corre en un PROCESO SEPARADO de FastAPI.
    ⚠️ NO afecta al proceso manual (/migrar/completo).

    Proceso:
    1. Consulta datos desde MBA3 con filtro de fecha
    2. Guarda en SQL Server usando context manager (previene leaks)
    3. Detecta productos no homologados
    4. Envía notificaciones por email si hay nuevos registros
    5. Invalida caché para que el frontend vea datos actualizados

    Returns:
        Dict con estadísticas de la migración
    """
    from src.services.mba3_service import MBA3Service
    from src.database.services.homologacion_service import HomologacionService
    from src.endpoints.despachos_migrar import build_query_with_date_filter
    from src.config import MBA3_QUERY_PREDEFINIDA, MIGRATE_DATE_FILTER_DAYS
    from src.mba3_query_client import MBA3APIClient
    from src.config import (
        MBA3_BASE_URL, MBA3_SERVICE_CODE, MBA3_SERVICE_PASSWORD,
        MBA3_DIGEST_USERNAME, MBA3_DIGEST_PASSWORD
    )

    fecha_ejecucion = ahora_naive()
    is_retry = False

    try:
        logger.info("=" * 70)
        logger.info("🤖 MIGRACIÓN AUTOMÁTICA (Celery Worker - PROCESO AISLADO)")
        logger.info(f"   Iniciada: {fecha_ejecucion.isoformat()}")
        logger.info(f"   Task ID: {self.request.id}")
        logger.info(f"   Worker: {self.request.hostname}")
        logger.info(f"   PID: {os.getpid()}")
        logger.info("   ⚠️ Este proceso NO afecta a FastAPI ni al proceso manual")
        logger.info("=" * 70)

        client = MBA3APIClient(
            base_url=MBA3_BASE_URL,
            service_code=MBA3_SERVICE_CODE,
            service_password=MBA3_SERVICE_PASSWORD,
            digest_username=MBA3_DIGEST_USERNAME,
            digest_password=MBA3_DIGEST_PASSWORD
        )

        query = build_query_with_date_filter(
            MBA3_QUERY_PREDEFINIDA,
            days=MIGRATE_DATE_FILTER_DAYS
        )

        logger.info(f"📅 Filtro: últimos {MIGRATE_DATE_FILTER_DAYS} días")

        result, is_retry = _consultar_mba3(client, query)
        count = _contar_resultado(result)
        logger.info(f"📊 Registros obtenidos: {count}")

        logger.info("💾 Guardando en base de datos (proceso aislado, no afecta FastAPI)...")

        homologacion_service = HomologacionService()
        homologacion_service.limpiar_detecciones()

        save_status = MBA3Service.save_to_database(
            result,
            upsert=True,
            homologacion_service=homologacion_service
        )

        if not save_status:
            raise RuntimeError("save_status es None")

        facturas_guardadas = save_status.get('facturas_guardadas', 0)
        facturas_actualizadas = save_status.get('facturas_actualizadas', 0)
        total_detalles = save_status.get('total_detalles', 0)

        logger.info("✅ Migración automática completada (worker aislado):")
        logger.info(f"   Facturas guardadas: {facturas_guardadas}")
        logger.info(f"   Facturas actualizadas: {facturas_actualizadas}")
        logger.info(f"   Total detalles: {total_detalles}")

        _notificar_migracion(facturas_guardadas, facturas_actualizadas, total_detalles, fecha_ejecucion)

        try:
            _notificar_homologacion(homologacion_service, fecha_ejecucion)
        except Exception as homologacion_error:
            # No fallar la migración si hay error en homologación
            logger.warning(f"⚠️ Error al verificar productos no homologados: {homologacion_error}")

        try:
            _invalidar_cache()
        except Exception as cache_error:
            # No fallar la migración si hay error al invalidar caché
            logger.warning(f"⚠️ Error al invalidar caché: {cache_error}")

        logger.info("=" * 70)

        return {
            "status": "success",
            "facturas_guardadas": facturas_guardadas,
            "facturas_actualizadas": facturas_actualizadas,
            "total_detalles": total_detalles,
            "task_id": self.request.id,
            "worker_pid": os.getpid(),
            "timestamp": ahora_naive().isoformat()
        }

    except SoftTimeLimitExceeded:
        logger.error("⏱️ Tiempo límite excedido en worker (10 minutos)")
        raise

    except Exception as e:
        logger.error(f"❌ Error en migración automática (worker): {e}", exc_info=True)
        if is_retry:
            _notificar_error_retry(e, fecha_ejecucion)
        # Re-lanzar la excepción para que Celery pueda reintentarla si es necesario
        raise
