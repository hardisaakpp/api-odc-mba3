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
from datetime import datetime
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from src.celery_app import celery_app

logger = logging.getLogger(__name__)


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
                fecha_ejecucion=datetime.now()
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
    from src.utils.email_notifier import send_migration_notification, send_homologacion_notification
    from src.exceptions import MBA3QueryError
    
    fecha_ejecucion = datetime.now()
    is_retry = False  # Flag para saber si estamos en el segundo intento
    
    try:
        logger.info("=" * 70)
        logger.info(f"🤖 MIGRACIÓN AUTOMÁTICA (Celery Worker - PROCESO AISLADO)")
        logger.info(f"   Iniciada: {fecha_ejecucion.isoformat()}")
        logger.info(f"   Task ID: {self.request.id}")
        logger.info(f"   Worker: {self.request.hostname}")
        logger.info(f"   PID: {os.getpid()}")
        logger.info("   ⚠️ Este proceso NO afecta a FastAPI ni al proceso manual")
        logger.info("=" * 70)
        
        # Cliente MBA3 dedicado para este worker
        # Cada worker tiene su propia instancia (no compartida con FastAPI)
        client = MBA3APIClient(
            base_url=MBA3_BASE_URL,
            service_code=MBA3_SERVICE_CODE,
            service_password=MBA3_SERVICE_PASSWORD,
            digest_username=MBA3_DIGEST_USERNAME,
            digest_password=MBA3_DIGEST_PASSWORD
        )
        
        # Construir query con filtro de fecha
        query = build_query_with_date_filter(
            MBA3_QUERY_PREDEFINIDA,
            days=MIGRATE_DATE_FILTER_DAYS
        )
        
        logger.info(f"📅 Filtro: últimos {MIGRATE_DATE_FILTER_DAYS} días")
        
        # Consultar MBA3 con manejo especial de "Object or Collection Expected"
        # Este error es temporal y se soluciona esperando y reintentando
        result = None
        try:
            result = client.execute_query(query, require_jwt=True)
            
            # Normalizar resultado
            if result is None:
                result = []
            elif not isinstance(result, (list, dict)):
                result = [result] if result else []
                
        except MBA3QueryError as query_error:
            error_message = str(query_error).lower()
            if "object or collection expected" in error_message:
                logger.warning("⚠️ Error 'Object or Collection Expected' en primer intento")
                logger.info("⏳ Esperando 15 segundos y reintentando...")
                time.sleep(15)
                
                is_retry = True
                logger.info("🔄 Reintentando consulta después de espera...")
                result = client.execute_query(query, require_jwt=True)
                
                # Normalizar resultado
                if result is None:
                    result = []
                elif not isinstance(result, (list, dict)):
                    result = [result] if result else []
                
                logger.info("✅ Reintento exitoso")
            else:
                # Si es otro error, re-lanzar
                raise
        
        count = len(result) if isinstance(result, list) else (1 if result else 0)
        logger.info(f"📊 Registros obtenidos: {count}")
        
        # Guardar en BD con context manager (garantiza cierre de conexión)
        logger.info("💾 Guardando en base de datos (proceso aislado, no afecta FastAPI)...")
        
        homologacion_service = HomologacionService()
        homologacion_service.limpiar_detecciones()
        
        # MBA3Service.save_to_database usa context manager internamente
        # Esto garantiza que la conexión se cierre correctamente
        save_status = MBA3Service.save_to_database(
            result,
            upsert=True,
            homologacion_service=homologacion_service
        )
        
        if save_status:
            facturas_guardadas = save_status.get('facturas_guardadas', 0)
            facturas_actualizadas = save_status.get('facturas_actualizadas', 0)
            total_detalles = save_status.get('total_detalles', 0)
            
            logger.info(f"✅ Migración automática completada (worker aislado):")
            logger.info(f"   Facturas guardadas: {facturas_guardadas}")
            logger.info(f"   Facturas actualizadas: {facturas_actualizadas}")
            logger.info(f"   Total detalles: {total_detalles}")
            
            # Notificar si hay nuevos registros (tanto en primer o segundo intento)
            if facturas_guardadas > 0:
                logger.info("📧 Enviando notificación por email (nuevos registros)...")
                send_migration_notification(
                    facturas_guardadas=facturas_guardadas,
                    facturas_actualizadas=facturas_actualizadas,
                    total_detalles=total_detalles,
                    fecha_ejecucion=fecha_ejecucion
                )
            else:
                logger.info("⏭️ No hay nuevos registros, no se envía email")
            
            # Verificar productos no homologados y notificar
            try:
                # Obtener TODOS los productos no homologados
                productos_no_homologados = homologacion_service.get_productos_no_homologados()
                
                if productos_no_homologados:
                    logger.info(f"⚠️ Detectados {len(productos_no_homologados)} productos no homologados en total")
                    
                    # Obtener estadísticas para el reporte
                    todos_productos = homologacion_service.get_todos_productos_no_homologados()
                    estadisticas = todos_productos.get("estadisticas", {})
                    
                    # Enviar notificación por email (la función filtrará productos ya notificados)
                    logger.info("📧 Enviando notificación de productos no homologados...")
                    email_enviado = send_homologacion_notification(
                        productos_no_homologados=productos_no_homologados,
                        estadisticas=estadisticas,
                        fecha_ejecucion=fecha_ejecucion,
                        filtrar_ya_notificados=True,  # ← Filtrar productos ya notificados
                        homologacion_repository=homologacion_service.repository  # ← Pasar repository
                    )
                    
                    if email_enviado:
                        logger.info("✅ Notificación de homologación enviada (solo productos nuevos)")
                    else:
                        logger.info("⏭️ No se envió notificación (todos ya fueron notificados)")
                else:
                    logger.debug("✅ No hay productos no homologados para notificar")
            except Exception as homologacion_error:
                # No fallar la migración si hay error en homologación
                logger.warning(f"⚠️ Error al verificar productos no homologados: {homologacion_error}")
            
            # Invalidar caché después de actualizar datos
            # Esto asegura que el frontend vea los datos más recientes
            try:
                from src.endpoints.despachos_info import invalidate_despachos_cache
                from src.endpoints.ordenes_compra import invalidate_ordenes_compra_cache
                
                invalidate_despachos_cache()
                invalidate_ordenes_compra_cache()
                logger.debug("🗑️ Caché invalidado después de migración automática")
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
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise Exception("save_status es None")
            
    except SoftTimeLimitExceeded:
        logger.error("⏱️ Tiempo límite excedido en worker (10 minutos)")
        raise
        
    except Exception as e:
        logger.error(f"❌ Error en migración automática (worker): {e}", exc_info=True)
        
        # Notificar error solo si estamos en el segundo intento o si es un error no esperado
        if is_retry:
            try:
                from src.utils.email_notifier import send_error_notification
                send_error_notification(
                    error_message=str(e),
                    fecha_ejecucion=fecha_ejecucion
                )
            except Exception as email_error:
                logger.error(f"Error al enviar notificación de error: {email_error}")
        
        # Re-lanzar la excepción para que Celery pueda reintentarla si es necesario
        raise

