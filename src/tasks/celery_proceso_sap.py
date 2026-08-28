"""
Tarea Celery para ejecutar el proceso completo SAP (Enviar ODC a SAP) en segundo plano.

Redistribución + Generar ODC + Enviar a SAP. Actualiza estado en Redis
para que el frontend pueda hacer polling o SSE (GET resultado/stream).
"""
import logging
from typing import List, Any, Dict

from celery import Task
from fastapi import HTTPException

from src.celery_app import celery_app
from src.database.services.proceso_estado_service import ProcesoEstadoService
from src.logging_config import log_business_operation
from src.utils.audit_context import AuditContext, ORIGEN_CELERY

logger = logging.getLogger(__name__)


def _log_resultado_proceso_sap(
    process_id: str,
    numero_pedido: str,
    user_id: str,
    resultado: Dict[str, Any],
) -> None:
    """Registra en logs (y business.log) el cierre del proceso SAP async."""
    status = resultado.get("status")
    paso_fallido = resultado.get("paso_fallido")
    error_detalle = resultado.get("error_detalle") or resultado.get("error")
    envio = resultado.get("envio_sap") or {}
    if isinstance(envio, dict):
        envio_error = envio.get("error") or envio.get("error_message")
        if envio_error and not error_detalle:
            error_detalle = envio_error

    ctx = (
        f"process_id={process_id} pedido={numero_pedido} usuario={user_id} "
        f"status={status} paso_fallido={paso_fallido}"
    )

    if status == "success":
        logger.info(f"✅ Proceso SAP Celery OK: {ctx}")
        return

    if status == "partial":
        logger.error(
            f"⚠️ Proceso SAP Celery parcial (fallo envío/prevalidación SAP): {ctx} "
            f"detalle={error_detalle}"
        )
        log_business_operation(
            operation="proceso_sap_envio_fallido",
            id_usuario=user_id,
            id_transaccion=process_id,
            success=False,
            detalles={
                "numero_pedido": numero_pedido,
                "status": status,
                "paso_fallido": paso_fallido,
                "error_detalle": error_detalle,
                "oc_id": envio.get("oc_id") if isinstance(envio, dict) else None,
                "error_source": envio.get("error_source") if isinstance(envio, dict) else None,
            },
        )
        return

    logger.error(f"❌ Proceso SAP Celery con status inesperado: {ctx} detalle={error_detalle}")


def _response_to_dict(response: Any) -> Dict[str, Any]:
    """Serializa la respuesta del proceso completo a dict JSON-serializable para Redis."""
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if hasattr(response, "dict"):
        return response.dict()
    if isinstance(response, dict):
        return response
    return {"response": str(response)}


@celery_app.task(
    name="src.tasks.celery_proceso_sap.ejecutar_proceso_completo_sap",
    bind=True,
    max_retries=0,
    time_limit=600,   # 10 min máximo
    soft_time_limit=540,
)
def ejecutar_proceso_completo_sap(
    self: Task,
    process_id: str,
    numero_pedido: str,
    user_id: str,
    ajustes_detalle: List[Any],
) -> None:
    """
    Ejecuta en segundo plano: Redistribución + Generar ODC + Enviar a SAP.

    Actualiza progreso en Redis y al finalizar guarda el resultado (éxito o error)
    para que el frontend lo consulte con GET /api/pedidos/proceso-sap/resultado/{process_id}.

    ajustes_detalle: lista de dicts (JSON deserializado); se convierte a AjusteDetalle internamente.
    """
    from src.endpoints.pedidos.redistribucion.endpoints_proceso import _ejecutar_proceso_completo_sync
    from src.models import AjusteDetalle

    estado_service = ProcesoEstadoService()

    try:
        logger.info(f"🚀 Iniciando proceso SAP Celery: {process_id} (pedido: {numero_pedido})")

        # Reconstruir AjusteDetalle desde los dicts (Celery recibe JSON → list of dicts)
        ajustes_objs = [AjusteDetalle(**d) for d in ajustes_detalle]

        estado_service.actualizar_progreso(
            process_id, "redistribucion", 10,
            "Confirmando redistribución y generando ODC..."
        )

        audit = AuditContext(
            usuario=user_id,
            origen=ORIGEN_CELERY,
            ip_origen=None,
        )

        def _reportar_progreso(step: str, progress: int, message: str) -> None:
            estado_service.actualizar_progreso(process_id, step, progress, message)

        resultado = _ejecutar_proceso_completo_sync(
            numero_pedido=numero_pedido,
            ajustes_detalle=ajustes_objs,
            user_id=user_id,
            audit=audit,
            on_progress=_reportar_progreso,
            process_id=process_id,
        )

        # Siempre hay "response" en el dict devuelto (éxito o parcial)
        response = resultado.get("response")
        if not response:
            estado_service.marcar_error(
                process_id,
                "El proceso no devolvió respuesta",
                error_data={"paso_fallido": "desconocido"},
            )
            return

        resultado_serialized = _response_to_dict(response)
        estado_service.completar_proceso(process_id, resultado_serialized)
        _log_resultado_proceso_sap(
            process_id, numero_pedido, user_id, resultado_serialized
        )

    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
        msg = detail.get("message", str(detail))
        logger.error(
            f"❌ Proceso SAP Celery HTTP {process_id} pedido={numero_pedido}: {msg} "
            f"detail={detail}",
            exc_info=True,
        )
        log_business_operation(
            operation="proceso_sap_validacion_fallida",
            id_usuario=user_id,
            id_transaccion=process_id,
            success=False,
            detalles={"numero_pedido": numero_pedido, "message": msg, **detail},
        )
        estado_service.marcar_error(process_id, msg, error_data=detail)
        raise
    except Exception as e:
        logger.error(f"❌ Error en proceso SAP Celery {process_id}: {e}", exc_info=True)
        estado_service.marcar_error(
            process_id,
            str(e),
            error_data={
                "paso_fallido": "desconocido",
                "error_detalle": str(e),
                "error": "internal_error",
            },
        )
        raise
