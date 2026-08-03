"""
Tarea Celery periódica: reconciliación automática de Solicitudes de Transferencia (ITR) pendientes.

Automatiza lo que antes requería que un usuario presionara "Reintentar ST" manualmente:
cada RECONCILIAR_ST_INTERVALO_MINUTOS busca OCs ENVIADAS con tiendas pendientes de ITR
(por una caída transitoria de Service Layer) y reintenta solo esas, reutilizando
StockTransferService.reintentar_pendientes (misma idempotencia que el botón manual).

Escalamiento a técnicos (correo + pausa de autoreintentos hasta que expire la marca en Redis):
- Inmediato si el error no parece transitorio (mensaje_sugiere_reintento_transitorio):
  reintentar no va a arreglar un dato de negocio (ej. artículo no habilitado en la bodega).
- Tras RECONCILIAR_ST_ESCALAMIENTO_HORAS si el error sí parece transitorio pero no se
  resuelve solo (ej. una caída de Service Layer más larga de lo habitual).
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from celery import Task

from src.celery_app import celery_app
from src.config import RECONCILIAR_ST_ESCALAMIENTO_HORAS
from src.database.connection import get_db_connection_context
from src.database.repositories.orden_compra_repository import OrdenCompraRepository
from src.database.repositories.solicitud_transferencia_repository import SolicitudTransferenciaRepository
from src.database.services.proceso_estado_service import get_redis_client
from src.database.services.retry_utils import mensaje_sugiere_reintento_transitorio
from src.database.services.stock_transfer_service import StockTransferService, redis_lock_reintento_st
from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)

_USUARIO_AUTOMATICO = "celery-beat"
_LOCK_BLOCKING_TIMEOUT_SEGUNDOS = 3.0
_NOTIFICADO_TTL_SEGUNDOS = 24 * 3600
_STATUS_SIN_ACCION = ("no_pendientes", "no_encontrada", "estado_invalido", "sin_pedido")


def _notificado_key(oc_id: str) -> str:
    return f"reconciliar-st:notificado:{oc_id}"


def _ya_fue_notificado(redis_client, oc_id: str) -> bool:
    return bool(redis_client.exists(_notificado_key(oc_id)))


def _marcar_notificado(redis_client, oc_id: str) -> None:
    redis_client.setex(_notificado_key(oc_id), _NOTIFICADO_TTL_SEGUNDOS, "1")


def _horas_desde_envio(oc_cabecera: Dict[str, Any]) -> float:
    """Antigüedad de la OC desde su último cambio de estado (proxy de 'desde cuándo está pendiente')."""
    updated_at_raw = oc_cabecera.get("updated_at")
    if not updated_at_raw:
        return 0.0
    try:
        referencia = datetime.fromisoformat(updated_at_raw)
    except (TypeError, ValueError):
        return 0.0
    return (ahora_naive() - referencia).total_seconds() / 3600.0


def _tiene_error_no_transitorio(resultado_st: Dict[str, Any]) -> bool:
    """True si alguna tienda aún fallida tiene un error que reintentar no resolvería."""
    for r in resultado_st.get("resultados") or []:
        if r.get("success"):
            continue
        if not mensaje_sugiere_reintento_transitorio(r.get("error") or ""):
            return True
    return False


def _fetch_oc_cabecera(oc_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection_context() as conn:
        return OrdenCompraRepository(conn).get_existing_cabecera(oc_id)


def _escalar_a_tecnicos(oc_cabecera: Dict[str, Any], resultado_st: Dict[str, Any]) -> None:
    from src.utils.email_notifier import send_oc_st_error_notification_tecnicos

    send_oc_st_error_notification_tecnicos(
        oc_cabecera=oc_cabecera,
        doc_num=oc_cabecera.get("numero_oc_sap"),
        doc_entry=oc_cabecera.get("doc_entry"),
        solicitudes_transferencia=resultado_st,
        pedido_numero=None,
    )


def _escalar_inmediato(oc_id: str, resultado_st: Dict[str, Any], redis_client) -> None:
    """Escala sin esperar el umbral de tiempo: el error no parece transitorio."""
    oc_cabecera = _fetch_oc_cabecera(oc_id)
    if not oc_cabecera:
        return
    logger.warning(
        f"⚠️ OC {oc_id[:8]}... con error no transitorio en ST; "
        "escalando de inmediato a técnicos (sin esperar el umbral de tiempo)"
    )
    _escalar_a_tecnicos(oc_cabecera, resultado_st)
    _marcar_notificado(redis_client, oc_id)


def _evaluar_escalamiento_por_tiempo(oc_id: str, resultado_st: Dict[str, Any], redis_client) -> None:
    """Si la OC lleva más de RECONCILIAR_ST_ESCALAMIENTO_HORAS pendiente, notifica y pausa autoreintentos."""
    oc_cabecera = _fetch_oc_cabecera(oc_id)
    if not oc_cabecera:
        return

    horas_pendiente = _horas_desde_envio(oc_cabecera)
    if horas_pendiente < RECONCILIAR_ST_ESCALAMIENTO_HORAS:
        return

    logger.warning(
        f"⚠️ OC {oc_id[:8]}... lleva {horas_pendiente:.1f}h con ST pendientes "
        f"(umbral: {RECONCILIAR_ST_ESCALAMIENTO_HORAS}h); escalando a técnicos"
    )
    _escalar_a_tecnicos(oc_cabecera, resultado_st)
    _marcar_notificado(redis_client, oc_id)


def _reconciliar_oc(oc_id: str, redis_client) -> Optional[Dict[str, Any]]:
    if _ya_fue_notificado(redis_client, oc_id):
        logger.debug(f"⏭️ OC {oc_id[:8]}... ya escalada a técnicos; se omite reintento automático")
        return None

    with redis_lock_reintento_st(oc_id, blocking_timeout=_LOCK_BLOCKING_TIMEOUT_SEGUNDOS) as acquired:
        if not acquired:
            logger.debug(f"⏭️ OC {oc_id[:8]}... con reintento en curso; se omite este ciclo")
            return None

        resultado = StockTransferService().reintentar_pendientes(
            oc_id, usuario_id=_USUARIO_AUTOMATICO, origen="automatico"
        )

        if resultado["status"] in _STATUS_SIN_ACCION:
            return resultado

        if resultado["status"] == "success":
            logger.info(f"✅ Reconciliación automática ST completada para OC {oc_id[:8]}...")
            return resultado

        resultado_st = resultado.get("resultado_st") or {}
        if _tiene_error_no_transitorio(resultado_st):
            _escalar_inmediato(oc_id, resultado_st, redis_client)
        else:
            _evaluar_escalamiento_por_tiempo(oc_id, resultado_st, redis_client)
        return resultado


@celery_app.task(
    name="src.tasks.celery_reconciliar_transferencias.reconciliar_transferencias_pendientes",
    bind=True,
    max_retries=0,
    time_limit=300,
    soft_time_limit=270,
)
def reconciliar_transferencias_pendientes(self: Task) -> Dict[str, Any]:
    """Busca OCs ENVIADAS con ST pendientes y reintenta automáticamente las que no han sido escaladas."""
    with get_db_connection_context() as conn:
        oc_ids = SolicitudTransferenciaRepository(conn).get_oc_ids_con_tiendas_pendientes()

    if not oc_ids:
        logger.debug("✅ Reconciliación ST: sin OCs pendientes")
        return {"procesadas": 0}

    logger.info(f"🔄 Reconciliación ST: {len(oc_ids)} OC(s) con transferencias pendientes")
    redis_client = get_redis_client()
    procesadas = 0
    for oc_id in oc_ids:
        try:
            if _reconciliar_oc(oc_id, redis_client) is not None:
                procesadas += 1
        except Exception as e:
            logger.error(f"❌ Error reconciliando ST para OC {oc_id}: {e}", exc_info=True)

    return {"procesadas": procesadas, "candidatas": len(oc_ids)}
