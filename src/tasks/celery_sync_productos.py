"""
Tarea de sincronización automática de maestros de productos ejecutada por Celery.

⚠️ IMPORTANTE: Este código corre en un PROCESO SEPARADO.
NO comparte recursos con FastAPI (no hay cuello de botella).

Características:
- Proceso aislado que no afecta al proceso manual
- Reintentos automáticos en caso de error
- Sincroniza maestros MBA3 y SAP a staging
- Registra estadísticas en sync_control
"""

import logging
import time
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from src.celery_app import celery_app

logger = logging.getLogger(__name__)


class SyncProductosTask(Task):
    """
    Clase base para tarea de sincronización de productos.
    Permite manejo personalizado de errores y logging.
    """
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Callback cuando la tarea falla."""
        logger.error("❌ Tarea de sincronización de productos falló")
        logger.error(f"   Task ID: {task_id}")
        logger.error(f"   Error: {exc}", exc_info=einfo)
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Callback cuando la tarea se reintenta."""
        logger.warning("⚠️ Reintentando sincronización de productos...")
        logger.warning(f"   Task ID: {task_id}")


@celery_app.task(
    name='src.tasks.celery_sync_productos.sync_productos_maestro',
    base=SyncProductosTask,
    bind=True,
    time_limit=1800,  # 30 minutos máximo
    soft_time_limit=1620  # Aviso después de 27 minutos
)
def sync_productos_maestro(self):
    """
    Tarea programada para sincronizar maestros de productos.
    
    Ejecuta:
    1. Sincronización de productos MBA3 desde API a staging
    2. Sincronización de productos SAP desde OPENQUERY a staging
    3. Logging de estadísticas
    
    Frecuencia sugerida: Diaria (ej: 2:00 AM)
    
    Returns:
        Dict con estadísticas de sincronización
    """
    from src.database.services.producto_staging_sync_service import ProductoStagingSyncService
    
    start_time = time.time()
    
    try:
        logger.info("=" * 70)
        logger.info("🔄 INICIANDO SINCRONIZACIÓN AUTOMÁTICA DE PRODUCTOS")
        logger.info("=" * 70)
        
        service = ProductoStagingSyncService()
        resultado = service.sync_all()
        
        elapsed_time = time.time() - start_time
        
        logger.info("=" * 70)
        logger.info("✅ SINCRONIZACIÓN AUTOMÁTICA COMPLETADA")
        logger.info(f"   Tiempo total: {elapsed_time:.2f} segundos")
        logger.info(f"   MBA3: {resultado.get('mba3', {}).get('registros_procesados', 0)} productos")
        logger.info(f"   SAP: {resultado.get('sap', {}).get('registros_procesados', 0)} productos")
        logger.info("=" * 70)
        
        return resultado
        
    except SoftTimeLimitExceeded:
        logger.error("⏱️ Tiempo límite excedido en sincronización de productos")
        raise
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"❌ Error crítico en sincronización de productos: {e}", exc_info=True)
        logger.error(f"   Tiempo transcurrido: {elapsed_time:.2f} segundos")
        raise
