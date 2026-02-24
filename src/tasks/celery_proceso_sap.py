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
from src.utils.audit_context import AuditContext, ORIGEN_CELERY

logger = logging.getLogger(__name__)


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

        resultado = _ejecutar_proceso_completo_sync(
            numero_pedido=numero_pedido,
            ajustes_detalle=ajustes_objs,
            user_id=user_id,
            audit=audit,
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
        logger.info(f"✅ Proceso SAP Celery completado: {process_id} (status: {resultado_serialized.get('status')})")

    except HTTPException as e:
        logger.error(f"❌ Error HTTP en proceso SAP {process_id}: {e}", exc_info=True)
        detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
        msg = detail.get("message", str(detail))
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
