"""
Tarea Celery periódica: reconciliación automática de Solicitudes de Transferencia (ITR) pendientes.

Automatiza lo que antes requería que un usuario presionara "Reintentar ST" manualmente:
busca OCs ENVIADAS con tiendas pendientes de ITR (por una caída transitoria de Service
Layer) y reintenta solo esas, reutilizando StockTransferService.reintentar_pendientes
(misma idempotencia que el botón manual). La MISMA tarea corre con dos configuraciones
distintas según el día (ver beat_schedule en src/celery_app.py):
- Lunes a sábado: dias_ventana corto (RECONCILIAR_ST_VENTANA_DIAS) -- solo OCs
  enviadas recientemente. No mira nada más viejo A PROPÓSITO: alcanzar OCs de meses
  atrás sin supervisión no es el objetivo (ver conversación 2026-08-28); lo que no se
  resuelve solo ya escaló a técnicos (ver abajo).
- Domingo: dias_ventana más amplio (RECONCILIAR_ST_VENTANA_DIAS_DOMINGO) para alcanzar
  cualquier OC que se le haya escapado a los barridos cortos de la semana, y además
  verificar_salud_diaria=True -- ese día también revisa si la reconciliación viene
  corriendo con éxito (colchón de seguridad, ver _verificar_salud_diaria más abajo)
  en vez de una tarea aparte corriendo cada hora.

Escalamiento a técnicos (correo + pausa de autoreintentos hasta que expire la marca en Redis):
- Inmediato si el error no parece transitorio (mensaje_sugiere_reintento_transitorio):
  reintentar no va a arreglar un dato de negocio (ej. artículo no habilitado en la bodega).
- Tras 2 corridas consecutivas si el error sí parece transitorio pero no se resuelve
  solo (ej. una caída de Service Layer más larga de lo habitual). Con la reconciliación
  corriendo una vez al día, un umbral de horas transcurridas ya no sirve de señal (para
  cuando el job corre, casi cualquier OC pendiente ya lleva más horas que un umbral
  razonable) -- se mide en corridas consecutivas en su lugar, ver
  _evaluar_escalamiento_por_recurrencia.
"""
import logging
from typing import Any, Dict, Optional

from celery import Task

from src.celery_app import celery_app
from src.config import RECONCILIAR_ST_MARGEN_COLCHON_HORAS
from src.database.connection import get_db_connection_context
from src.database.repositories.orden_compra_repository import OrdenCompraRepository
from src.database.repositories.solicitud_transferencia_repository import SolicitudTransferenciaRepository
from src.database.services.proceso_estado_service import get_redis_client
from src.database.services.retry_utils import mensaje_sugiere_reintento_transitorio
from src.database.services.stock_transfer_service import StockTransferService, redis_lock_reintento_st
from src.services.celery_availability import RECONCILIAR_ST_LAST_RUN_REDIS_KEY, reconciliacion_st_al_dia
from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)

_USUARIO_AUTOMATICO = "celery-beat"
_LOCK_BLOCKING_TIMEOUT_SEGUNDOS = 3.0
_NOTIFICADO_TTL_SEGUNDOS = 24 * 3600
_VISTO_PENDIENTE_TTL_SEGUNDOS = 48 * 3600
_STATUS_SIN_ACCION = ("no_pendientes", "no_encontrada", "estado_invalido", "sin_pedido")


def _notificado_key(oc_id: str) -> str:
    return f"reconciliar-st:notificado:{oc_id}"


def _ya_fue_notificado(redis_client, oc_id: str) -> bool:
    return bool(redis_client.exists(_notificado_key(oc_id)))


def _marcar_notificado(redis_client, oc_id: str) -> None:
    redis_client.setex(_notificado_key(oc_id), _NOTIFICADO_TTL_SEGUNDOS, "1")


def _visto_pendiente_key(oc_id: str) -> str:
    return f"reconciliar-st:visto-pendiente:{oc_id}"


def _limpiar_visto_pendiente(redis_client, oc_id: str) -> None:
    """OC ya no está en un estado pendiente/fallido: borra el rastro de corridas
    anteriores, para que una incidencia futura y distinta no se escale de
    inmediato por arrastrar la marca de una ya resuelta."""
    redis_client.delete(_visto_pendiente_key(oc_id))


def _marcar_ultima_corrida_exitosa(redis_client) -> None:
    """Colchón de seguridad (ver src/services/celery_availability.py): confirma que
    esta corrida terminó sin una excepción no manejada. Best-effort -- un fallo al
    escribir esto no debe tumbar el resultado real de la reconciliación."""
    try:
        redis_client.setex(
            RECONCILIAR_ST_LAST_RUN_REDIS_KEY,
            int(RECONCILIAR_ST_MARGEN_COLCHON_HORAS * 3600),
            ahora_naive().isoformat(),
        )
    except Exception as e:
        logger.warning(f"⚠️ No se pudo marcar la última corrida exitosa de reconciliación ST: {e}")


def _verificar_salud_diaria() -> None:
    """
    Colchón de seguridad: se llama solo el domingo (verificar_salud_diaria=True),
    ANTES de que esta misma corrida marque su propio éxito -- así refleja si las
    corridas ANTERIORES (lunes a sábado, u otros domingos) vinieron completando
    exitosamente, no un falso "todo bien" por la marca que esta corrida está a
    punto de escribir. Deliberadamente en la MISMA tarea semanal en vez de una
    tarea aparte corriendo cada hora -- el problema que vigila no es urgente.
    """
    if reconciliacion_st_al_dia():
        return
    logger.error(
        "❌ La reconciliación automática de ST no completó exitosamente dentro del "
        "margen esperado -- posible caída de Celery Beat o error no manejado en la tarea."
    )
    try:
        from src.utils.email_notifier import send_reconciliacion_st_caida_notification
        send_reconciliacion_st_caida_notification()
    except Exception as e:
        logger.warning(f"⚠️ No se pudo enviar la notificación de reconciliación ST caída: {e}")


def _tiene_error_no_transitorio(resultado_st: Dict[str, Any]) -> bool:
    """True si alguna tienda aún fallida tiene un error que reintentar no resolvería.

    Las tiendas 'queued' (HTTP 202, ITR encolada en el middleware) no cuentan como
    error: por definición son transitorias, se resuelven consultando el job en el
    próximo ciclo, no escalando a técnicos.
    """
    for r in resultado_st.get("resultados") or []:
        if r.get("success") or r.get("queued"):
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


def _evaluar_escalamiento_por_recurrencia(oc_id: str, resultado_st: Dict[str, Any], redis_client) -> None:
    """
    Con la reconciliación corriendo una vez al día, un umbral de horas transcurridas
    ya no es señal útil (para cuando el job corre, casi cualquier OC pendiente ya
    lleva más horas que cualquier umbral razonable -- escalaría en la primera
    corrida, sin margen). En su lugar: si esta OC ya estaba marcada como "vista
    pendiente" en la corrida anterior, esta es la 2da noche consecutiva sin
    resolverse -- ahí sí se escala. La primera vez, solo se marca para la próxima
    corrida (le da una noche de margen a un problema transitorio de SAP).
    """
    key = _visto_pendiente_key(oc_id)
    if not redis_client.exists(key):
        redis_client.setex(key, _VISTO_PENDIENTE_TTL_SEGUNDOS, "1")
        logger.info(f"ℹ️ OC {oc_id[:8]}... con ST pendientes por primera vez; se reintentará mañana antes de escalar")
        return

    oc_cabecera = _fetch_oc_cabecera(oc_id)
    if not oc_cabecera:
        return

    logger.warning(
        f"⚠️ OC {oc_id[:8]}... sigue con ST pendientes en 2 corridas diarias consecutivas; "
        "escalando a técnicos"
    )
    _escalar_a_tecnicos(oc_cabecera, resultado_st)
    _marcar_notificado(redis_client, oc_id)
    redis_client.delete(key)


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
            _limpiar_visto_pendiente(redis_client, oc_id)
            return resultado

        if resultado["status"] == "success":
            logger.info(f"✅ Reconciliación automática ST completada para OC {oc_id[:8]}...")
            _limpiar_visto_pendiente(redis_client, oc_id)
            return resultado

        resultado_st = resultado.get("resultado_st") or {}
        if _tiene_error_no_transitorio(resultado_st):
            _escalar_inmediato(oc_id, resultado_st, redis_client)
            _limpiar_visto_pendiente(redis_client, oc_id)
        else:
            _evaluar_escalamiento_por_recurrencia(oc_id, resultado_st, redis_client)
        return resultado


@celery_app.task(
    name="src.tasks.celery_reconciliar_transferencias.reconciliar_transferencias_pendientes",
    bind=True,
    max_retries=0,
    # Corre una sola vez al día (vs. cada 5 min antes): más margen para el caso
    # (raro, según datos de producción) de varias OC candidatas acumuladas.
    time_limit=1800,
    soft_time_limit=1700,
)
def reconciliar_transferencias_pendientes(
    self: Task, dias_ventana: int, verificar_salud_diaria: bool = False
) -> Dict[str, Any]:
    """
    Busca OCs ENVIADAS (con su primer intento de ST dentro de los últimos
    `dias_ventana` días) con ST pendientes, y reintenta automáticamente las que no
    han sido escaladas.

    `verificar_salud_diaria`: True solo en la corrida del domingo (ver
    beat_schedule) -- revisa si la reconciliación viene completando exitosamente,
    sin necesidad de una tarea aparte corriendo cada hora.
    """
    if verificar_salud_diaria:
        _verificar_salud_diaria()

    redis_client = get_redis_client()
    with get_db_connection_context() as conn:
        st_repo = SolicitudTransferenciaRepository(conn)
        oc_ids_pendientes = st_repo.get_oc_ids_con_tiendas_pendientes(dias_ventana)
        oc_ids_faltantes = st_repo.get_oc_ids_con_tiendas_faltantes(dias_ventana)

    # Unión sin duplicados: tiendas con intento fallido (pendientes) + tiendas que
    # nunca se intentaron según la distribución confirmada (faltantes, F4.5).
    # _reconciliar_oc → reintentar_pendientes ya resuelve ambos casos por OC
    # (ver StockTransferService._resolver_tiendas_objetivo).
    oc_ids = list(dict.fromkeys(oc_ids_pendientes + oc_ids_faltantes))

    if not oc_ids:
        logger.debug("✅ Reconciliación ST: sin OCs pendientes")
        _marcar_ultima_corrida_exitosa(redis_client)
        return {"procesadas": 0}

    logger.info(f"🔄 Reconciliación ST: {len(oc_ids)} OC(s) con transferencias pendientes")
    procesadas = 0
    for oc_id in oc_ids:
        try:
            if _reconciliar_oc(oc_id, redis_client) is not None:
                procesadas += 1
        except Exception as e:
            logger.error(f"❌ Error reconciliando ST para OC {oc_id}: {e}", exc_info=True)

    _marcar_ultima_corrida_exitosa(redis_client)
    return {"procesadas": procesadas, "candidatas": len(oc_ids)}
