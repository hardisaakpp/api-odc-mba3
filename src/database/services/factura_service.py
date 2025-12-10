"""
Servicio para guardar facturas de MBA3 en SQL Server.
"""

import logging
from typing import Dict, Any, List, Optional

from config import ENABLE_SQL_SERVER_STORAGE
from ..connection import get_db_connection
from ..repositories.despacho_repository import DespachoRepository
from ..mappers.factura_mapper import FacturaMapper
from ..services.sap_service import SAPService

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
    upsert: bool = False,
    homologacion_service: Optional[Any] = None
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
        "cabecera_actualizada": False,
        "detalles_insertados": 0,
        "errors": []
    }
    
    try:
        codigo_factura = factura.get("CODIGO_FACTURA")
        
        # Transformar factura a formato SQL Server
        datos_cabecera = FacturaMapper.to_despacho_cabecera(factura)
        
        # Verificar si ya existe (para upsert)
        existing_id = None
        if upsert and codigo_factura:
            existing_id = repository.find_by_codigo_factura(codigo_factura)
        
        if existing_id:
            # ACTUALIZAR factura existente (UPSERT)
            logger.info(f"🔄 Factura ya existe: {codigo_factura} (despacho_id: {existing_id}) - Actualizando...")
            
            # Actualizar cabecera
            repository.update_cabecera(existing_id, datos_cabecera)
            result["despacho_id"] = existing_id
            result["cabecera_insertada"] = False  # No se insertó, se actualizó
            result["cabecera_actualizada"] = True
            
            # Eliminar detalles antiguos
            detalles_eliminados = repository.delete_detalles(existing_id)
            logger.debug(f"   → {detalles_eliminados} detalles antiguos eliminados")
            
            # Insertar detalles nuevos
            despacho_id = existing_id
        else:
            # INSERTAR nueva factura
            despacho_id = repository.insert_cabecera(datos_cabecera)
            result["despacho_id"] = despacho_id
            result["cabecera_insertada"] = True
            result["cabecera_actualizada"] = False
        
        # Procesar detalles desde ObjDatosFactura (tanto para INSERT como UPDATE)
        obj_datos = factura.get("ObjDatosFactura")
        if obj_datos:
            # Inicializar servicio SAP para consultar información de productos
            sap_service = SAPService()
            
            for tipo_linea in TIPOS_LINEAS:
                if tipo_linea in obj_datos and obj_datos[tipo_linea]:
                    try:
                        # Transformar líneas a formato SQL Server
                        detalles = []
                        for linea in obj_datos[tipo_linea]:
                            codigo = linea.get("Codigo")
                            
                            # Consultar información SAP para este SKU
                            sap_info = None
                            if codigo:
                                try:
                                    sap_info = sap_service.get_or_fetch_producto_info(codigo)
                                    if sap_info:
                                        logger.debug(
                                            f"   → SAP info para {codigo}: "
                                            f"Pack={sap_info.get('pack_sap')}, "
                                            f"Unidad={sap_info.get('unidad_conversion')}"
                                        )
                                    else:
                                        # Producto no encontrado en SAP - detectar como no homologado
                                        if homologacion_service:
                                            homologacion_service.detectar_producto_no_homologado(codigo)
                                        logger.debug(f"   ⚠️ Producto no encontrado en SAP: {codigo}")
                                except Exception as sap_error:
                                    # No fallar si no se puede consultar SAP, continuar sin conversión
                                    logger.warning(f"   ⚠️ Error al consultar SAP para {codigo}: {sap_error}")
                                    # También detectar como no homologado si hay error
                                    if homologacion_service:
                                        homologacion_service.detectar_producto_no_homologado(codigo)
                            
                            # Transformar línea con información SAP si está disponible
                            detalle = FacturaMapper.to_despacho_detalle(linea, tipo_linea, sap_info=sap_info)
                            if detalle:
                                # Log de conversión si se aplicó
                                if detalle.get("cantidad_sap"):
                                    logger.info(
                                        f"   ✅ Conversión aplicada para {codigo}: "
                                        f"{detalle['cantidad']} docenas → {detalle['cantidad_sap']:.2f} packs "
                                        f"({detalle.get('unidad_sap')})"
                                    )
                                detalles.append(detalle)
                        
                        # Insertar detalles
                        if detalles:
                            count = repository.insert_detalles(despacho_id, detalles)
                            result["detalles_insertados"] += count
                    except Exception as e:
                        error_msg = f"Error al insertar {tipo_linea}: {str(e)}"
                        logger.error(f"❌ {error_msg}")
                        result["errors"].append(error_msg)
        
        accion = "actualizada" if result.get("cabecera_actualizada") else "guardada"
        logger.info(
            f"✅ Factura {accion}: {codigo_factura} "
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
    continue_on_error: bool = True,
    homologacion_service: Optional[Any] = None
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
        "facturas_actualizadas": 0,
        "facturas_existentes": 0,  # Deprecated: usar facturas_actualizadas
        "facturas_error": 0,
        "total_detalles": 0,
        "errors": []
    }
    
    conn = None
    try:
        # Conectar a SQL Server
        try:
            conn = get_db_connection()
            repository = DespachoRepository(conn)
        except Exception as conn_error:
            logger.error(f"❌ Error al conectar a SQL Server: {conn_error}")
            return {
                "status": "error",
                "message": f"Error de conexión a SQL Server: {str(conn_error)}",
                "total_facturas": 0,
                "facturas_guardadas": 0,
                "facturas_actualizadas": 0,
                "facturas_error": 0,
                "total_detalles": 0,
                "errors": [f"Error de conexión: {str(conn_error)}"]
            }
        
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
        logger.info(f"📦 Procesando {stats['total_facturas']} factura(s)...")
        
        # Procesar cada factura
        for idx, factura in enumerate(facturas, 1):
            try:
                result = save_mba3_factura(repository, factura, upsert=upsert, homologacion_service=homologacion_service)
                
                if result["status"] == "success":
                    if result.get("cabecera_actualizada"):
                        stats["facturas_actualizadas"] += 1
                    else:
                        stats["facturas_guardadas"] += 1
                    stats["total_detalles"] += result["detalles_insertados"]
                elif result["status"] == "exists":
                    # Este caso ya no debería ocurrir con upsert=True, pero lo mantenemos por compatibilidad
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
        
        logger.info(f"✅ Proceso completado: {stats['facturas_guardadas']} guardadas, {stats['facturas_actualizadas']} actualizadas, {stats['facturas_error']} errores de {stats['total_facturas']} totales")
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



