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
inmediato para quien lo hizo.
"""
import logging
from typing import Any, Dict

from celery import Task

from src.celery_app import celery_app
from src.database.connection import get_db_connection_context
from src.database.repositories.orden_compra_repository import OrdenCompraRepository
from src.database.services.oc_sap_service import OCSAPService
from src.database.services.retry_utils import mensaje_sugiere_reintento_transitorio

logger = logging.getLogger(__name__)


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

    if resultado.get("queued"):
        logger.info(f"⏳ OC {oc_id[:8]}... sigue encolada en SAP; se reintenta el próximo ciclo")
    elif resultado.get("success"):
        logger.info(f"✅ Reconciliación automática de ODC completada para {oc_id[:8]}...")
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
    return True


@celery_app.task(
    name="src.tasks.celery_reconciliar_ordenes_compra.reconciliar_ordenes_compra_pendientes",
    bind=True,
    max_retries=0,
    time_limit=300,
    soft_time_limit=270,
)
def reconciliar_ordenes_compra_pendientes(self: Task) -> Dict[str, Any]:
    """Busca ODC ENCOLADAS y resuelve el job pendiente de cada una (ver módulo)."""
    with get_db_connection_context() as conn:
        oc_ids = OrdenCompraRepository(conn).get_oc_ids_encoladas()

    if not oc_ids:
        logger.debug("✅ Reconciliación OC: sin ODC encoladas")
        return {"procesadas": 0}

    logger.info(f"🔄 Reconciliación OC: {len(oc_ids)} ODC encolada(s)")
    procesadas = 0
    for oc_id in oc_ids:
        try:
            if _reconciliar_oc(oc_id):
                procesadas += 1
        except Exception as e:
            logger.error(f"❌ Error reconciliando ODC {oc_id}: {e}", exc_info=True)

    return {"procesadas": procesadas, "candidatas": len(oc_ids)}
