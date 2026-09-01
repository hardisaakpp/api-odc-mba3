"""
Tarea Celery periódica: reconciliación automática de ODC ENCOLADAS pendientes.

Cuando el middleware SAP encola la creación de una Purchase Order (HTTP 202, SAP
saturado), la ODC queda en estado ENCOLADA con su job_id (ver
OCSAPService._resolver_job_encolado_previo). Antes de esta tarea, la única forma de
que esa ODC avanzara era que alguien la reintentara manualmente desde la UI -- y
mientras nadie lo hiciera, la ODC quedaba "colgada" sin que se supiera si sus
Solicitudes de Transferencia llegaron a generarse (ver incidente ODC 24711/24712).

Cada RECONCILIAR_OC_INTERVALO_MINUTOS, esta tarea llama a
OCSAPService.enviar_oc_a_sap sobre cada ODC ENCOLADA -- sin lock propio: el lock
distribuido que serializa envíos de una misma ODC (redis_lock_envio_odc, ver
oc_sap_service.py) ya vive DENTRO de enviar_oc_a_sap, y protege por igual a
cualquier llamador (esta tarea o un reintento manual desde la UI) contra 2 envíos
concurrentes de la misma oc_id. Internamente, eso consulta primero GET
/api/v1/jobs/{jobId} (mismo patrón que la reconciliación de ST, ver
celery_reconciliar_transferencias.py) y:
- Si el job ya COMPLETÓ: adopta el DocEntry/DocNum, crea sus ST, notifica y cierra
  el pedido si corresponde -- sin recrear el documento en SAP.
- Si sigue ENCOLADO/PROCESANDO: no hace nada, se reintenta el próximo ciclo.
- Si el job resolvió en un error real de SAP: la ODC queda libre y se reintenta un
  envío nuevo en el mismo ciclo (mismo comportamiento que un reintento manual).

A diferencia de la reconciliación de ST, esta tarea siempre corre (no depende de un
flag de encendido/apagado, ver src/celery_app.py) y, si el job resuelve en un error
real (no transitorio), notifica a técnicos por correo
(send_oc_creacion_error_notification_tecnicos) -- nadie está mirando la pantalla en
este flujo automático, a diferencia de un reintento manual que ya es visible de
inmediato para quien lo hizo. Desde 2026-08-31 también publica una notificación SSE
(odcsap.view/mabel.view) en ambos casos -- antes esta tarea era la única de las 3
reconciliaciones automáticas del módulo que no avisaba a nadie conectado en tiempo
real (ver celery_reconciliar_transferencias.py, que sí lo hacía desde antes).

Esta misma tarea también barre ODC ENVIANDO estancadas (ver
get_oc_ids_envianco_estancadas / ENVIANDO_ESTANCADO_UMBRAL_MINUTOS en config.py):
un envío que quedó ENVIANDO por un crash del proceso a mitad del envío a SAP (sin
job_id, a diferencia de ENCOLADA -- no hay forma segura de verificar contra SAP si
la ODC llegó a crearse). Se escala a ERROR para revisión manual, nunca se
reintenta sola -- ver OCSAPService._resolver_envio_estancado_previo, que solo
detecta y bloquea, dejando el flip real a esta tarea.
"""
import logging
from typing import Any, Dict

from celery import Task

from src.celery_app import celery_app
from src.config import ENVIANDO_ESTANCADO_UMBRAL_MINUTOS
from src.database.connection import get_db_connection_context
from src.database.repositories.orden_compra_repository import OrdenCompraRepository
from src.database.services.oc_sap_service import OCSAPService
from src.database.services.retry_utils import mensaje_sugiere_reintento_transitorio

logger = logging.getLogger(__name__)


def _identificador_oc(oc_cabecera: Dict[str, Any]) -> str:
    """Referencia legible de la ODC para mensajes de notificación (título/correo)."""
    oc_cabecera = oc_cabecera or {}
    return (
        oc_cabecera.get("referencia_despacho")
        or oc_cabecera.get("numero_oc_sap")
        or oc_cabecera.get("oc_id")
        or "?"
    )


def _notificar_error_real_a_tecnicos(oc_id: str, oc_cabecera: Dict[str, Any], error: str) -> None:
    from src.utils.email_notifier import send_oc_creacion_error_notification_tecnicos

    try:
        send_oc_creacion_error_notification_tecnicos(
            oc_cabecera=oc_cabecera or {},
            error_message=error,
            pedido_numero=None,
        )
    except Exception as e:
        logger.warning(f"⚠️ No se pudo notificar a técnicos el error real de ODC {oc_id[:8]}...: {e}")


def _publicar_sse_reconciliacion(oc_id: str, oc_cabecera: Dict[str, Any], titulo: str, mensaje: str, tipo: str, accion: str) -> None:
    """Publica (best-effort, vía Redis) la notificación SSE de un resultado de esta
    tarea -- este proceso (worker de Celery) no tiene acceso a las colas SSE en
    memoria del proceso mba3-api, publish_notification_from_worker_multi las
    alcanza vía Redis pub/sub. Nunca debe romper la tarea si falla."""
    try:
        from src.utils.sse_redis_bridge import publish_notification_from_worker_multi

        publish_notification_from_worker_multi(
            ["odcsap.view", "mabel.view"],
            titulo,
            mensaje,
            tipo,
            {"oc_id": oc_id, "pedido_id": (oc_cabecera or {}).get("pedido_id"), "accion": accion},
        )
    except Exception as e:
        logger.warning(f"⚠️ No se pudo publicar notificación SSE de reconciliación OC (no crítico): {e}")


def _reconciliar_oc(oc_id: str) -> bool:
    """Intenta resolver una ODC ENCOLADA llamando a enviar_oc_a_sap. Devuelve
    True si se procesó (con cualquier resultado, incluida una colisión
    transitoria con otro envío en curso -- ver enviar_oc_a_sap/
    redis_lock_envio_odc, cuyo lock interno ya protege esta llamada sin
    necesidad de un lock propio aquí)."""
    with get_db_connection_context() as conn:
        oc_repo = OrdenCompraRepository(conn)
        resultado = OCSAPService().enviar_oc_a_sap(oc_repo=oc_repo, oc_id=oc_id)
        oc_cabecera = oc_repo.get_existing_cabecera(oc_id)

    identificador = _identificador_oc(oc_cabecera)

    if resultado.get("queued"):
        logger.info(f"⏳ OC {oc_id[:8]}... sigue encolada en SAP; se reintenta el próximo ciclo")
    elif resultado.get("success"):
        logger.info(f"✅ Reconciliación automática de ODC completada para {oc_id[:8]}...")
        doc_num = resultado.get("doc_num")
        _publicar_sse_reconciliacion(
            oc_id, oc_cabecera,
            "ODC confirmada en SAP (reconciliación automática)",
            f"La ODC {identificador} quedó confirmada en SAP" + (f" (DocNum: {doc_num})" if doc_num else "")
            + " tras la reconciliación automática.",
            "success", "reconciliacion_oc_confirmada",
        )
    else:
        error = resultado.get("error") or "error desconocido"
        es_transitorio = mensaje_sugiere_reintento_transitorio(error)
        nivel = logging.WARNING if es_transitorio else logging.ERROR
        logger.log(
            nivel,
            f"❌ ODC {oc_id[:8]}... encolada resolvió en error real al reintentar: {error} "
            "(requiere atención manual; sigue disponible el botón de reintento en la UI)"
        )
        if not es_transitorio:
            _notificar_error_real_a_tecnicos(oc_id, oc_cabecera, error)
            _publicar_sse_reconciliacion(
                oc_id, oc_cabecera,
                "Error al crear ODC en SAP (reconciliación automática)",
                f"La reconciliación automática de la ODC {identificador} encontró un error real de "
                f"SAP: {error}. Requiere revisión manual.",
                "error", "reconciliacion_oc_error",
            )
    return True


def _reconciliar_envio_estancado(oc_id: str) -> None:
    """Escala a ERROR una ODC ENVIANDO estancada (ver módulo). El UPDATE va guardado
    con estado_actual_esperado='ENVIANDO': si el envío en realidad terminó
    legítimamente (ENVIADA/ERROR) justo entre el SELECT de candidatas y este
    UPDATE, no matchea ninguna fila y no se notifica nada -- la carrera se
    autosana en vez de pisar un resultado real."""
    mensaje_error = (
        f"Envío a SAP interrumpido inesperadamente (posible caída del proceso, más de "
        f"{ENVIANDO_ESTANCADO_UMBRAL_MINUTOS} min en ENVIANDO); verificar manualmente en SAP "
        "antes de reintentar."
    )
    with get_db_connection_context() as conn:
        oc_repo = OrdenCompraRepository(conn)
        flipeada = oc_repo.update_estado(
            oc_id, "ERROR", error_message=mensaje_error, error_source="BACKEND",
            estado_actual_esperado="ENVIANDO",
        )
        oc_cabecera = oc_repo.get_existing_cabecera(oc_id) if flipeada else None

    if not flipeada:
        logger.info(f"ℹ️ OC {oc_id[:8]}... ya no estaba ENVIANDO al intentar escalarla (se resolvió sola)")
        return

    identificador = _identificador_oc(oc_cabecera)
    logger.error(f"❌ OC {oc_id[:8]}... ENVIANDO estancada, escalada a ERROR: {mensaje_error}")
    _notificar_error_real_a_tecnicos(oc_id, oc_cabecera, mensaje_error)
    _publicar_sse_reconciliacion(
        oc_id, oc_cabecera,
        "ODC con envío interrumpido (revisión manual requerida)",
        f"La ODC {identificador} tenía un envío a SAP en curso hace más de "
        f"{ENVIANDO_ESTANCADO_UMBRAL_MINUTOS} minutos sin resolverse y se marcó como error "
        "para revisión manual.",
        "warning", "oc_envio_estancado",
    )


@celery_app.task(
    name="src.tasks.celery_reconciliar_ordenes_compra.reconciliar_ordenes_compra_pendientes",
    bind=True,
    max_retries=0,
    time_limit=300,
    soft_time_limit=270,
)
def reconciliar_ordenes_compra_pendientes(self: Task) -> Dict[str, Any]:
    """Busca ODC ENCOLADAS y resuelve el job pendiente de cada una, y ODC ENVIANDO
    estancadas y las escala a ERROR (ver módulo)."""
    with get_db_connection_context() as conn:
        oc_repo = OrdenCompraRepository(conn)
        oc_ids = oc_repo.get_oc_ids_encoladas()
        oc_ids_estancadas = oc_repo.get_oc_ids_envianco_estancadas(ENVIANDO_ESTANCADO_UMBRAL_MINUTOS)

    for oc_id in oc_ids_estancadas:
        try:
            _reconciliar_envio_estancado(oc_id)
        except Exception as e:
            logger.error(f"❌ Error escalando ODC ENVIANDO estancada {oc_id}: {e}", exc_info=True)

    if not oc_ids:
        logger.debug("✅ Reconciliación OC: sin ODC encoladas")
        return {"procesadas": 0, "estancadas": len(oc_ids_estancadas)}

    logger.info(f"🔄 Reconciliación OC: {len(oc_ids)} ODC encolada(s)")
    procesadas = 0
    for oc_id in oc_ids:
        try:
            if _reconciliar_oc(oc_id):
                procesadas += 1
        except Exception as e:
            logger.error(f"❌ Error reconciliando ODC {oc_id}: {e}", exc_info=True)

    return {"procesadas": procesadas, "candidatas": len(oc_ids), "estancadas": len(oc_ids_estancadas)}
