"""
Tarea Celery para ejecutar cruce de productos en background.

Este módulo define la tarea Celery que ejecuta el cruce de productos
de manera asíncrona, permitiendo que el endpoint responda inmediatamente
y el progreso se pueda seguir mediante Server-Sent Events (SSE).
"""
import logging
from typing import Optional
from celery import Task
from src.celery_app import celery_app
from src.database.services.cruce_productos_service import CruceProductosService
from src.database.services.proceso_estado_service import ProcesoEstadoService

logger = logging.getLogger(__name__)


@celery_app.task(
    name='src.tasks.celery_cruce_productos.ejecutar_cruce_productos',
    bind=True,
    max_retries=0,  # No reintentar si falla (el proceso es determinista)
    time_limit=600,  # 10 minutos máximo por tarea
    soft_time_limit=540  # Aviso después de 9 minutos
)
def ejecutar_cruce_productos(self: Task, process_id: str, user_id: Optional[str] = None):
    """
    Ejecuta el cruce de productos en background usando Celery.
    
    Esta tarea:
    1. Actualiza progreso en Redis mediante callbacks
    2. Ejecuta el cruce completo de productos
    3. Marca el proceso como completado o error
    
    Args:
        process_id: ID del proceso para actualizar estado en Redis
        user_id: ID del usuario que inició el proceso (opcional, para auditoría)
        
    Raises:
        Exception: Si hay error durante el cruce (se marca como error en estado)
    """
    estado_service = ProcesoEstadoService()
    
    try:
        logger.info(f"🚀 Iniciando cruce Celery para proceso {process_id}")
        
        # Callback para actualizar progreso en Redis
        def progress_callback(step: str, progress: int, message: str, data: Optional[dict] = None):
            """Actualiza el progreso del proceso en Redis."""
            estado_service.actualizar_progreso(process_id, step, progress, message, data)
        
        # Ejecutar el cruce con callback de progreso
        service = CruceProductosService()
        resultado = service.realizar_cruce(progress_callback=progress_callback)
        
        # ✅ AJUSTE 2: Guardar solo campos necesarios para sugerencias (reducir payload)
        productos_sap_completos = service.obtener_productos_sap()
        
        # Reducir payload: solo código, nombre y normalizado (necesarios para sugerencias)
        resultado["productos_sap_base"] = [
            {
                "item_code": p.get("item_code", ""),
                "item_name": p.get("item_name", ""),
                "item_code_normalizado": p.get("item_code_normalizado", ""),
                "active": p.get("active", True)
            }
            for p in productos_sap_completos
        ]
        
        # Log para monitoreo
        logger.info(
            f"📦 Guardando {len(resultado['productos_sap_base'])} productos SAP "
            f"(payload reducido para sugerencias)"
        )
        
        # Marcar como completado
        estado_service.completar_proceso(process_id, resultado)
        
        logger.info(f"✅ Cruce Celery completado para proceso {process_id}")
        
    except Exception as e:
        logger.error(f"❌ Error en cruce Celery {process_id}: {e}", exc_info=True)
        estado_service.marcar_error(process_id, str(e))
        # Re-lanzar para que Celery registre el error
        raise

