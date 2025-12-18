"""
Servicio para guardar remisiones de MBA3 en SQL Server.
"""

import logging
from typing import Dict, Any, List, Optional

from src.config import ENABLE_SQL_SERVER_STORAGE
from ..connection import get_db_connection
from ..repositories.remision_repository import RemisionRepository
from ..mappers.factura_mapper import FacturaMapper

logger = logging.getLogger(__name__)


def save_mba3_remision(
    repository: RemisionRepository,
    remision: Dict[str, Any],
    upsert: bool = False
) -> Dict[str, Any]:
    """
    Guarda una remisión de MBA3 en SQL Server (solo cabecera, sin detalles).
    
    Args:
        repository: Repositorio de remisión
        remision: Diccionario con datos de remisión de MBA3
        upsert: Si True, actualiza si existe; si False, inserta siempre
        
    Returns:
        Dict con estadísticas de la operación
    """
    result = {
        "status": "success",
        "remision_id": None,
        "cabecera_insertada": False,
        "cabecera_actualizada": False,
        "errors": []
    }
    
    try:
        codigo_factura = remision.get("CODIGO_FACTURA")
        
        # Transformar remisión a formato SQL Server
        datos_cabecera = FacturaMapper.to_remision_cabecera(remision)
        
        # Verificar si ya existe (para upsert)
        existing_id = None
        if upsert and codigo_factura:
            existing_id = repository.find_by_codigo_factura(codigo_factura)
        
        if existing_id:
            # ACTUALIZAR remisión existente (UPSERT)
            logger.info(f"🔄 Remisión ya existe: {codigo_factura} (remision_id: {existing_id}) - Actualizando...")
            
            # Actualizar cabecera
            repository.update_cabecera(existing_id, datos_cabecera)
            result["remision_id"] = existing_id
            result["cabecera_insertada"] = False  # No se insertó, se actualizó
            result["cabecera_actualizada"] = True
        else:
            # INSERTAR nueva remisión
            remision_id = repository.insert_cabecera(datos_cabecera)
            result["remision_id"] = remision_id
            result["cabecera_insertada"] = True
            result["cabecera_actualizada"] = False
        
        accion = "actualizada" if result.get("cabecera_actualizada") else "guardada"
        logger.info(
            f"✅ Remisión {accion}: {codigo_factura} "
            f"(remision_id: {result['remision_id']})"
        )
        
    except Exception as e:
        error_msg = f"Error al guardar remisión {remision.get('CODIGO_FACTURA')}: {str(e)}"
        logger.error(f"❌ {error_msg}")
        result["status"] = "error"
        result["errors"].append(error_msg)
    
    return result


def save_mba3_remisiones_to_sql_server(
    mba3_json_result: Any,
    upsert: bool = False,
    continue_on_error: bool = True
) -> Dict[str, Any]:
    """
    Guarda el resultado JSON de remisiones de MBA3 en SQL Server.
    
    Esta función es el punto de entrada principal para guardar remisiones de MBA3.
    
    Args:
        mba3_json_result: Resultado JSON de MBA3 (puede ser list o dict)
        upsert: Si True, actualiza si existe; si False, inserta siempre
        continue_on_error: Si True, continúa procesando aunque falle una remisión
        
    Returns:
        Dict con estadísticas de la operación
    """
    if not ENABLE_SQL_SERVER_STORAGE:
        logger.info("⏭️ Guardado en SQL Server deshabilitado (ENABLE_SQL_SERVER_STORAGE=False)")
        return {
            "status": "disabled",
            "message": "SQL Server storage is disabled"
        }
    
    stats = {
        "status": "success",
        "total_remisiones": 0,
        "remisiones_guardadas": 0,
        "remisiones_actualizadas": 0,
        "remisiones_error": 0,
        "errors": []
    }
    
    conn = None
    try:
        # Conectar a SQL Server
        try:
            conn = get_db_connection()
            repository = RemisionRepository(conn)
        except Exception as conn_error:
            logger.error(f"❌ Error al conectar a SQL Server: {conn_error}")
            return {
                "status": "error",
                "message": f"Error de conexión a SQL Server: {str(conn_error)}",
                "total_remisiones": 0,
                "remisiones_guardadas": 0,
                "remisiones_actualizadas": 0,
                "remisiones_error": 0,
                "errors": [f"Error de conexión: {str(conn_error)}"]
            }
        
        # Procesar según el tipo de resultado
        remisiones = []
        if isinstance(mba3_json_result, list):
            remisiones = mba3_json_result
        elif isinstance(mba3_json_result, dict):
            remisiones = [mba3_json_result]
        else:
            logger.error(f"❌ Formato de resultado no soportado: {type(mba3_json_result)}")
            return {
                "status": "error",
                "message": f"Formato no soportado: {type(mba3_json_result)}"
            }
        
        stats["total_remisiones"] = len(remisiones)
        logger.info(f"📦 Procesando {stats['total_remisiones']} remisión(es)...")
        
        # Procesar cada remisión
        for idx, remision in enumerate(remisiones, 1):
            try:
                result = save_mba3_remision(repository, remision, upsert=upsert)
                
                if result["status"] == "success":
                    if result.get("cabecera_actualizada"):
                        stats["remisiones_actualizadas"] += 1
                    else:
                        stats["remisiones_guardadas"] += 1
                else:
                    stats["remisiones_error"] += 1
                    stats["errors"].extend(result["errors"])
                    
                    if not continue_on_error:
                        raise Exception(f"Error al guardar remisión: {result['errors']}")
                
            except Exception as e:
                error_msg = f"Error al procesar remisión {idx}: {str(e)}"
                logger.error(f"❌ {error_msg}")
                stats["remisiones_error"] += 1
                stats["errors"].append(error_msg)
                
                if not continue_on_error:
                    raise
        
        logger.info(
            f"✅ Proceso completado: {stats['remisiones_guardadas']} guardadas, "
            f"{stats['remisiones_actualizadas']} actualizadas, "
            f"{stats['remisiones_error']} errores"
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ Error general al guardar remisiones: {e}", exc_info=True)
        stats["status"] = "error"
        stats["errors"].append(f"Error general: {str(e)}")
        return stats
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass



