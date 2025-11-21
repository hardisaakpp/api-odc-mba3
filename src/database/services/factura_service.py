"""
Servicio para guardar facturas de MBA3 en SQL Server.
"""

import logging
from typing import Dict, Any, List

from config import ENABLE_SQL_SERVER_STORAGE
from ..connection import get_db_connection
from ..repositories.despacho_repository import DespachoRepository
from ..mappers.factura_mapper import FacturaMapper

logger = logging.getLogger(__name__)

# Tipos de arrays que pueden existir en ObjDatosFactura
TIPOS_LINEAS = [
    "GrabarLineasProd",
    "Lineas",
    "CtrlEliminados1",
    "CtrlEliminados2",
    "CtrlEliminados3",
    "CtrlEliminados4",
    "CtrlEliminados5",
    "CtrlEliminados6",
    "CtrlEliminados7",
    "CtrlEliminados8",
    "CtrlEliminadosA",
    "CtrlEliminadosB",
]


def save_mba3_factura(
    repository: DespachoRepository,
    factura: Dict[str, Any],
    upsert: bool = False
) -> Dict[str, Any]:
    """
    Guarda una factura completa de MBA3 en SQL Server (cabecera + detalles).
    
    Args:
        repository: Repositorio de despacho
        factura: Diccionario con datos de factura de MBA3
        upsert: Si True, actualiza si existe; si False, inserta siempre
        
    Returns:
        Dict con estadísticas de la operación
    """
    result = {
        "status": "success",
        "despacho_id": None,
        "cabecera_insertada": False,
        "detalles_insertados": 0,
        "errors": []
    }
    
    try:
        codigo_factura = factura.get("CODIGO_FACTURA")
        
        # Verificar si ya existe (para upsert)
        if upsert and codigo_factura:
            existing_id = repository.find_by_codigo_factura(codigo_factura)
            if existing_id:
                result["despacho_id"] = existing_id
                logger.info(f"⚠️ Factura ya existe: {codigo_factura} (despacho_id: {existing_id})")
                result["status"] = "exists"
                return result
        
        # Transformar factura a formato SQL Server
        datos_cabecera = FacturaMapper.to_despacho_cabecera(factura)
        
        # Insertar cabecera
        despacho_id = repository.insert_cabecera(datos_cabecera)
        result["despacho_id"] = despacho_id
        result["cabecera_insertada"] = True
        
        # Procesar detalles desde ObjDatosFactura
        obj_datos = factura.get("ObjDatosFactura")
        if obj_datos:
            for tipo_linea in TIPOS_LINEAS:
                if tipo_linea in obj_datos and obj_datos[tipo_linea]:
                    try:
                        # Transformar líneas a formato SQL Server
                        detalles = []
                        for linea in obj_datos[tipo_linea]:
                            detalle = FacturaMapper.to_despacho_detalle(linea, tipo_linea)
                            if detalle:
                                detalles.append(detalle)
                        
                        # Insertar detalles
                        if detalles:
                            count = repository.insert_detalles(despacho_id, detalles)
                            result["detalles_insertados"] += count
                    except Exception as e:
                        error_msg = f"Error al insertar {tipo_linea}: {str(e)}"
                        logger.error(f"❌ {error_msg}")
                        result["errors"].append(error_msg)
        
        logger.info(
            f"✅ Factura guardada: {codigo_factura} "
            f"(despacho_id: {despacho_id}, detalles: {result['detalles_insertados']})"
        )
        
    except Exception as e:
        error_msg = f"Error al guardar factura {factura.get('CODIGO_FACTURA')}: {str(e)}"
        logger.error(f"❌ {error_msg}")
        result["status"] = "error"
        result["errors"].append(error_msg)
    
    return result


def save_mba3_data_to_sql_server(
    mba3_json_result: Any,
    upsert: bool = False,
    continue_on_error: bool = True
) -> Dict[str, Any]:
    """
    Guarda el resultado JSON de MBA3 en SQL Server.
    
    Esta función es el punto de entrada principal para guardar datos de MBA3.
    
    Args:
        mba3_json_result: Resultado JSON de MBA3 (puede ser list o dict)
        upsert: Si True, actualiza si existe; si False, inserta siempre
        continue_on_error: Si True, continúa procesando aunque falle una factura
        
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
        "total_facturas": 0,
        "facturas_guardadas": 0,
        "facturas_existentes": 0,
        "facturas_error": 0,
        "total_detalles": 0,
        "errors": []
    }
    
    conn = None
    try:
        # Conectar a SQL Server
        conn = get_db_connection()
        repository = DespachoRepository(conn)
        
        # Procesar según el tipo de resultado
        facturas = []
        if isinstance(mba3_json_result, list):
            facturas = mba3_json_result
        elif isinstance(mba3_json_result, dict):
            facturas = [mba3_json_result]
        else:
            logger.error(f"❌ Formato de resultado no soportado: {type(mba3_json_result)}")
            return {
                "status": "error",
                "message": f"Formato no soportado: {type(mba3_json_result)}"
            }
        
        stats["total_facturas"] = len(facturas)
        logger.info(f"📦 Procesando {stats['total_facturas']} factura(s) de MBA3...")
        
        # Procesar cada factura
        for idx, factura in enumerate(facturas, 1):
            try:
                codigo_factura = factura.get("CODIGO_FACTURA", f"Factura-{idx}")
                logger.info(f"[{idx}/{stats['total_facturas']}] Procesando: {codigo_factura}")
                
                result = save_mba3_factura(repository, factura, upsert=upsert)
                
                if result["status"] == "success":
                    stats["facturas_guardadas"] += 1
                    stats["total_detalles"] += result["detalles_insertados"]
                elif result["status"] == "exists":
                    stats["facturas_existentes"] += 1
                else:
                    stats["facturas_error"] += 1
                    stats["errors"].extend(result["errors"])
                    
                    if not continue_on_error:
                        raise Exception(f"Error al guardar factura: {result['errors']}")
                
            except Exception as e:
                error_msg = f"Error al procesar factura {idx}: {str(e)}"
                logger.error(f"❌ {error_msg}")
                stats["facturas_error"] += 1
                stats["errors"].append(error_msg)
                
                if not continue_on_error:
                    raise
        
        # Determinar estado final
        if stats["facturas_error"] == 0:
            stats["status"] = "success"
        elif stats["facturas_guardadas"] > 0:
            stats["status"] = "partial"
        else:
            stats["status"] = "error"
        
        logger.info("=" * 70)
        logger.info(f"✅ Proceso completado:")
        logger.info(f"   Total facturas: {stats['total_facturas']}")
        logger.info(f"   Guardadas: {stats['facturas_guardadas']}")
        logger.info(f"   Existentes: {stats['facturas_existentes']}")
        logger.info(f"   Errores: {stats['facturas_error']}")
        logger.info(f"   Total detalles: {stats['total_detalles']}")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"❌ Error crítico al guardar en SQL Server: {e}", exc_info=True)
        stats["status"] = "error"
        stats["errors"].append(f"Error crítico: {str(e)}")
        
    finally:
        if conn:
            try:
                conn.close()
                logger.debug("🔌 Conexión a SQL Server cerrada")
            except:
                pass
    
    return stats

