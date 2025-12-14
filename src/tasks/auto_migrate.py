"""
Tarea programada para ejecutar migración automática cada 15 minutos.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from services.mba3_service import MBA3Service
from config import (
    MBA3_QUERY_PREDEFINIDA,
    AUTO_MIGRATE_INTERVAL_MINUTES,
    AUTO_MIGRATE_DATE_FILTER_DAYS,
    ENABLE_AUTO_MIGRATE,
    MBA3_BASE_URL,
    MBA3_SERVICE_CODE,
    MBA3_SERVICE_PASSWORD,
    MBA3_DIGEST_USERNAME,
    MBA3_DIGEST_PASSWORD
)
# Importar función para construir query con filtro de fecha
from endpoints.despachos_migrar import build_query_with_date_filter
# Importar excepciones para detectar errores específicos
from exceptions import MBA3QueryError
# Importar funciones de notificación por email
from utils.email_notifier import send_migration_notification, send_error_notification, send_homologacion_notification
# Importar servicio de homologación
from database.services.homologacion_service import HomologacionService
# Importar cliente MBA3 dedicado para el proceso automatizado
from mba3_query_client import MBA3APIClient

logger = logging.getLogger(__name__)

# Variable global para controlar si la tarea está activa
_auto_migrate_task: Optional[asyncio.Task] = None
_auto_migrate_enabled = False

# Cliente MBA3 dedicado para el proceso automatizado (separado del singleton)
# Esto evita bloqueos con las peticiones del usuario
_auto_migrate_client: Optional[MBA3APIClient] = None


def get_auto_migrate_client() -> MBA3APIClient:
    """
    Obtiene un cliente MBA3 dedicado para el proceso automatizado.
    
    Este cliente es independiente del singleton usado por las peticiones del usuario,
    lo que permite que el proceso automatizado no bloquee las peticiones del usuario
    y viceversa.
    
    Returns:
        Instancia de MBA3APIClient configurada con las credenciales
    """
    global _auto_migrate_client
    if _auto_migrate_client is None:
        logger.info("🔧 Inicializando cliente MBA3 dedicado para migración automática...")
        _auto_migrate_client = MBA3APIClient(
            base_url=MBA3_BASE_URL,
            service_code=MBA3_SERVICE_CODE,
            service_password=MBA3_SERVICE_PASSWORD,
            digest_username=MBA3_DIGEST_USERNAME,
            digest_password=MBA3_DIGEST_PASSWORD
        )
        logger.info("✅ Cliente MBA3 para migración automática inicializado (independiente del singleton)")
    return _auto_migrate_client


def filter_by_date(result: Any, days: int) -> Any:
    """
    Filtra los resultados por fecha después de obtenerlos de MBA3.
    Esto evita problemas con el formato de fecha en la consulta SQL de MBA3/4D.
    
    Args:
        result: Resultado de la consulta MBA3 (puede ser list o dict)
        days: Número de días hacia atrás para filtrar
    
    Returns:
        Resultado filtrado (mismo tipo que el input)
    """
    if result is None:
        return result
    
    # Calcular fecha límite
    fecha_limite = datetime.now() - timedelta(days=days)
    fecha_limite_date = fecha_limite.date()
    
    if isinstance(result, list):
        filtered = []
        for item in result:
            if isinstance(item, dict):
                fecha_factura_str = item.get("FECHA_FACTURA")
                if fecha_factura_str:
                    try:
                        # Intentar parsear la fecha en diferentes formatos
                        if isinstance(fecha_factura_str, str):
                            # Formato YYYY-MM-DD
                            if len(fecha_factura_str) >= 10:
                                fecha_factura = datetime.strptime(fecha_factura_str[:10], "%Y-%m-%d").date()
                                if fecha_factura >= fecha_limite_date:
                                    filtered.append(item)
                            else:
                                # Si no tiene formato válido, incluir por seguridad
                                filtered.append(item)
                        else:
                            # Si no es string, incluir por seguridad
                            filtered.append(item)
                    except (ValueError, TypeError) as e:
                        # Si hay error al parsear, incluir por seguridad
                        logger.warning(f"⚠️ Error al parsear fecha '{fecha_factura_str}': {e}. Incluyendo registro.")
                        filtered.append(item)
                else:
                    # Si no tiene fecha, no incluir (filtrar)
                    pass
            else:
                # Si no es dict, incluir por seguridad
                filtered.append(item)
        return filtered
    elif isinstance(result, dict):
        # Si es un solo dict, aplicar el mismo filtro
        fecha_factura_str = result.get("FECHA_FACTURA")
        if fecha_factura_str:
            try:
                if isinstance(fecha_factura_str, str) and len(fecha_factura_str) >= 10:
                    fecha_factura = datetime.strptime(fecha_factura_str[:10], "%Y-%m-%d").date()
                    if fecha_factura >= fecha_limite_date:
                        return result
                else:
                    return result
            except (ValueError, TypeError):
                return result
        return None  # Si no tiene fecha, no incluir
    else:
        # Tipo desconocido, retornar tal cual
        return result


async def execute_auto_migration():
    """
    Ejecuta la migración automática: consulta MBA3 con filtro de fecha y guarda en base de datos.
    
    Funcionalidad:
    - Consulta datos desde MBA3 usando query predefinida con filtro de fecha
    - Filtra registros de los últimos N días (configurado en AUTO_MIGRATE_DATE_FILTER_DAYS)
    - Guarda resultados en SQL Server (despacho_cabecera/detalle)
    - Si falla la primera vez con "Object or Collection Expected", espera y reintenta (simula comportamiento manual)
    - Envía notificaciones por email:
      * Notifica cuando hay nuevos registros (tanto en primer o segundo intento)
      * Notifica errores solo cuando ocurren en el segundo intento
    """
    fecha_ejecucion = datetime.now()
    is_retry = False  # Flag para saber si estamos en el segundo intento
    
    try:
        logger.info("=" * 70)
        logger.info(f"🤖 MIGRACIÓN AUTOMÁTICA: Iniciada a las {fecha_ejecucion.isoformat()}")
        logger.info("=" * 70)
        
        # Construir query con filtro de fecha
        query_with_filter = build_query_with_date_filter(MBA3_QUERY_PREDEFINIDA, days=AUTO_MIGRATE_DATE_FILTER_DAYS)
        logger.info(f"📅 Aplicando filtro de fecha: últimos {AUTO_MIGRATE_DATE_FILTER_DAYS} días")
        logger.info(f"Query: {query_with_filter[:200]}...")  # Primeros 200 caracteres
        
        # Ejecutar consulta con filtro de fecha usando cliente dedicado
        # Esto evita bloqueos con las peticiones del usuario que usan el singleton
        # Si falla con "Object or Collection Expected", esperar y reintentar (como en ejecución manual)
        result = None
        try:
            # Usar cliente dedicado en lugar del singleton para evitar bloqueos
            client = get_auto_migrate_client()
            result = client.execute_query(query_with_filter, require_jwt=True)
            
            # Normalizar resultado
            if result is None:
                logger.warning("⚠️ La consulta retornó None. Usando lista vacía.")
                result = []
            elif not isinstance(result, (list, dict)):
                logger.warning(f"⚠️ Tipo de resultado inesperado: {type(result)}. Convirtiendo a lista.")
                result = [result] if result else []
        except MBA3QueryError as query_error:
            # Detectar si es el error específico "Object or Collection Expected"
            error_message = str(query_error).lower()
            is_object_collection_error = "object or collection expected" in error_message
            
            if is_object_collection_error:
                logger.warning("⚠️ Primera ejecución falló con 'Object or Collection Expected'")
                logger.info("⏳ Esperando 15 segundos y reintentando (simulando comportamiento manual)...")
                await asyncio.sleep(15)  # Esperar 15 segundos como en ejecución manual
                
                # Reintentar la consulta
                is_retry = True  # Marcamos que estamos en el segundo intento
                logger.info("🔄 Reintentando consulta después de espera...")
                try:
                    # Usar cliente dedicado en lugar del singleton
                    client = get_auto_migrate_client()
                    result = client.execute_query(query_with_filter, require_jwt=True)
                    
                    # Normalizar resultado
                    if result is None:
                        logger.warning("⚠️ La consulta retornó None. Usando lista vacía.")
                        result = []
                    elif not isinstance(result, (list, dict)):
                        logger.warning(f"⚠️ Tipo de resultado inesperado: {type(result)}. Convirtiendo a lista.")
                        result = [result] if result else []
                    
                    logger.info("✅ Reintento exitoso")
                except MBA3QueryError as retry_error:
                    # Si falla en el segundo intento, notificar error
                    logger.error(f"❌ Error en segundo intento: {retry_error}")
                    send_error_notification(
                        error_message=str(retry_error),
                        fecha_ejecucion=fecha_ejecucion
                    )
                    raise
            else:
                # Si es otro error en el primer intento, no notificar (solo notificar en segundo intento)
                logger.error(f"❌ Error inesperado en primer intento: {query_error}")
                raise
        
        total_registros = len(result) if isinstance(result, list) else (1 if result else 0)
        logger.info(f"📊 Registros obtenidos: {total_registros}")
        
        # Inicializar servicio de homologación para detectar productos no homologados
        homologacion_service = HomologacionService()
        homologacion_service.limpiar_detecciones()  # Limpiar detecciones previas
        
        # Guardar en base de datos
        logger.info("💾 Guardando en despacho_cabecera/detalle...")
        save_status = None
        try:
            # Pasar el servicio de homologación para detectar productos no homologados
            save_status = MBA3Service.save_to_database(result, upsert=True, homologacion_service=homologacion_service)
            
            if save_status:
                facturas_guardadas = save_status.get('facturas_guardadas', 0)
                facturas_actualizadas = save_status.get('facturas_actualizadas', 0)
                total_detalles = save_status.get('total_detalles', 0)
                
                logger.info(f"✅ Migración automática completada:")
                logger.info(f"   Facturas guardadas: {facturas_guardadas}")
                logger.info(f"   Facturas actualizadas: {facturas_actualizadas}")
                logger.info(f"   Total detalles: {total_detalles}")
                logger.info(f"   Total registros procesados: {total_registros}")
                
                # Enviar notificación por email si hay nuevos registros (tanto en primer o segundo intento)
                if facturas_guardadas > 0:
                    logger.info("📧 Enviando notificación por email (nuevos registros encontrados)...")
                    send_migration_notification(
                        facturas_guardadas=facturas_guardadas,
                        facturas_actualizadas=facturas_actualizadas,
                        total_detalles=total_detalles,
                        fecha_ejecucion=fecha_ejecucion
                    )
                else:
                    logger.info("⏭️ No hay nuevos registros, no se envía email")
                
                # Verificar productos nuevos no homologados y notificar
                try:
                    productos_nuevos = homologacion_service.get_productos_no_homologados_nuevos()
                    if productos_nuevos:
                        logger.info(f"⚠️ Detectados {len(productos_nuevos)} productos NUEVOS no homologados")
                        
                        # Obtener estadísticas para el reporte
                        todos_productos = homologacion_service.get_todos_productos_no_homologados()
                        estadisticas = todos_productos.get("estadisticas", {})
                        
                        # Enviar notificación por email
                        logger.info("📧 Enviando notificación de productos no homologados...")
                        email_enviado = send_homologacion_notification(
                            productos_no_homologados=productos_nuevos,
                            estadisticas=estadisticas,
                            fecha_ejecucion=fecha_ejecucion
                        )
                        
                        # Registrar productos como notificados solo si el email se envió correctamente
                        if email_enviado:
                            skus_notificados = [p["sku"] for p in productos_nuevos]
                            registrados = homologacion_service.registrar_productos_notificados(skus_notificados)
                            logger.info(f"✅ Registrados {registrados} productos como notificados")
                        else:
                            logger.warning("⚠️ Email no se envió, productos no se registraron como notificados")
                    else:
                        logger.debug("✅ No hay productos nuevos no homologados para notificar")
                except Exception as homologacion_error:
                    # No fallar la migración si hay error en homologación
                    logger.warning(f"⚠️ Error al verificar productos no homologados: {homologacion_error}")
                
                # Invalidar caché después de actualizar datos
                # Esto asegura que el usuario vea los datos más recientes
                try:
                    from endpoints.despachos_info import invalidate_despachos_cache
                    from endpoints.ordenes_compra import invalidate_ordenes_compra_cache
                    
                    invalidate_despachos_cache()
                    invalidate_ordenes_compra_cache()
                    logger.debug("🗑️ Caché invalidado después de migración automática")
                except Exception as cache_error:
                    # No fallar la migración si hay error al invalidar caché
                    logger.warning(f"⚠️ Error al invalidar caché: {cache_error}")
                    
        except Exception as save_error:
            logger.error(f"❌ Error al guardar en SQL Server: {save_error}", exc_info=True)
            # Notificar error al guardar solo si estamos en el segundo intento
            if is_retry:
                send_error_notification(
                    error_message=f"Error al guardar en base de datos: {save_error}",
                    fecha_ejecucion=fecha_ejecucion
                )
        
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"❌ Error en migración automática: {e}", exc_info=True)
        # Notificar error solo si estamos en el segundo intento o si es un error no esperado
        if is_retry:
            send_error_notification(
                error_message=f"Error en migración automática (segundo intento): {e}",
                fecha_ejecucion=fecha_ejecucion
            )
        logger.error("   La tarea continuará ejecutándose según el intervalo programado")


async def auto_migrate_loop(interval_minutes: int = 15):
    """
    Loop que ejecuta la migración automática cada N minutos.
    
    Args:
        interval_minutes: Intervalo en minutos entre ejecuciones (por defecto 15)
    """
    interval_seconds = interval_minutes * 60
    
    logger.info("=" * 70)
    logger.info(f"🚀 Iniciando tarea de migración automática")
    logger.info(f"   Intervalo: cada {interval_minutes} minutos ({interval_seconds} segundos)")
    logger.info(f"   Filtro de fecha: últimos {AUTO_MIGRATE_DATE_FILTER_DAYS} días")
    logger.info("=" * 70)
    
    # Esperar antes de la primera ejecución para dar tiempo a que MBA3 procese el JWT
    # Esto resuelve el problema de "Object or Collection Expected" en la primera ejecución
    # que ocurre cuando la migración automática se ejecuta inmediatamente después del startup
    initial_delay_seconds = 10  # Esperar 10 segundos después del startup
    logger.info(f"⏳ Esperando {initial_delay_seconds} segundos antes de la primera ejecución (para que MBA3 procese el JWT)...")
    await asyncio.sleep(initial_delay_seconds)
    
    while _auto_migrate_enabled:
        try:
            # Ejecutar migración
            await execute_auto_migration()
            
            # Esperar antes de la siguiente ejecución
            logger.info(f"⏳ Esperando {interval_minutes} minutos hasta la próxima ejecución...")
            await asyncio.sleep(interval_seconds)
            
        except asyncio.CancelledError:
            logger.info("🛑 Tarea de migración automática cancelada")
            break
        except Exception as e:
            logger.error(f"❌ Error en loop de migración automática: {e}", exc_info=True)
            # Esperar un poco antes de reintentar
            await asyncio.sleep(60)  # Esperar 1 minuto antes de reintentar


def start_auto_migrate(interval_minutes: int = 15):
    """
    Inicia la tarea de migración automática.
    
    Args:
        interval_minutes: Intervalo en minutos entre ejecuciones (por defecto 15)
    """
    global _auto_migrate_task, _auto_migrate_enabled
    
    if not ENABLE_AUTO_MIGRATE:
        logger.info("⏭️ Migración automática deshabilitada (ENABLE_AUTO_MIGRATE=false)")
        return
    
    if _auto_migrate_task is not None and not _auto_migrate_task.done():
        logger.warning("⚠️ La tarea de migración automática ya está en ejecución")
        return
    
    _auto_migrate_enabled = True
    _auto_migrate_task = asyncio.create_task(auto_migrate_loop(interval_minutes))
    logger.info("✅ Tarea de migración automática iniciada")


def stop_auto_migrate():
    """
    Detiene la tarea de migración automática.
    """
    global _auto_migrate_task, _auto_migrate_enabled
    
    _auto_migrate_enabled = False
    
    if _auto_migrate_task is not None and not _auto_migrate_task.done():
        _auto_migrate_task.cancel()
        logger.info("🛑 Deteniendo tarea de migración automática...")
    else:
        logger.info("ℹ️ No hay tarea de migración automática en ejecución")


def is_auto_migrate_running() -> bool:
    """
    Verifica si la tarea de migración automática está en ejecución.
    
    Returns:
        True si está en ejecución, False en caso contrario
    """
    return _auto_migrate_task is not None and not _auto_migrate_task.done()


