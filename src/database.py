"""
Módulo para conexión y operaciones con SQL Server.

Maneja la persistencia de datos de MBA3 en las tablas de SQL Server:
- despacho_cabecera
- despacho_detalle
"""

import logging
import pyodbc
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID

from config import (
    SQL_SERVER_DRIVER,
    SQL_SERVER_SERVER,
    SQL_SERVER_DATABASE,
    SQL_SERVER_UID,
    SQL_SERVER_PWD,
    ENABLE_SQL_SERVER_STORAGE
)

logger = logging.getLogger(__name__)


def get_db_connection() -> pyodbc.Connection:
    """
    Crea y retorna una conexión a SQL Server.
    
    Returns:
        Conexión a SQL Server
        
    Raises:
        Exception: Si no se puede conectar a la base de datos
    """
    try:
        # Construir cadena de conexión
        if SQL_SERVER_UID and SQL_SERVER_PWD:
            # Autenticación con usuario y contraseña
            connection_string = (
                f"DRIVER={SQL_SERVER_DRIVER};"
                f"SERVER={SQL_SERVER_SERVER};"
                f"DATABASE={SQL_SERVER_DATABASE};"
                f"UID={SQL_SERVER_UID};"
                f"PWD={SQL_SERVER_PWD}"
            )
        else:
            # Autenticación Windows (Trusted Connection)
            connection_string = (
                f"DRIVER={SQL_SERVER_DRIVER};"
                f"SERVER={SQL_SERVER_SERVER};"
                f"DATABASE={SQL_SERVER_DATABASE};"
                f"Trusted_Connection=yes;"
            )
        
        logger.debug(f"Conectando a SQL Server: {SQL_SERVER_SERVER}/{SQL_SERVER_DATABASE}")
        conn = pyodbc.connect(connection_string, timeout=10)
        logger.info("✅ Conexión a SQL Server establecida")
        return conn
        
    except Exception as e:
        logger.error(f"❌ Error al conectar a SQL Server: {e}")
        raise


def parse_date(date_str: Optional[str]) -> Optional[str]:
    """
    Parsea una fecha en formato string a formato compatible con SQL Server.
    
    Args:
        date_str: String con fecha (formato: "YYYY-MM-DD" o similar)
        
    Returns:
        String con fecha en formato SQL Server, o None si no se puede parsear
    """
    if not date_str:
        return None
    
    try:
        # Intentar parsear diferentes formatos
        if isinstance(date_str, str):
            # Formato esperado: "2025-11-20"
            if len(date_str) >= 10:
                return date_str[:10]  # YYYY-MM-DD
    except Exception:
        pass
    
    return None


def insert_despacho_cabecera(conn: pyodbc.Connection, factura: Dict[str, Any]) -> str:
    """
    Inserta un registro en despacho_cabecera a partir de una factura de MBA3.
    
    Args:
        conn: Conexión a SQL Server
        factura: Diccionario con datos de factura de MBA3
        
    Returns:
        despacho_id (UUID) como string
        
    Raises:
        Exception: Si falla la inserción
    """
    cursor = conn.cursor()
    
    try:
        # Generar UUID para despacho_id
        despacho_id = str(cursor.execute("SELECT NEWID()").fetchone()[0])
        
        # Extraer y transformar datos de la factura
        fecha_factura = parse_date(factura.get("FECHA_FACTURA"))
        fecha_despacho = fecha_factura  # Usar fecha_factura como fecha_despacho por defecto
        
        # SQL para insertar
        sql = """
        INSERT INTO despacho_cabecera (
            despacho_id,
            empresa,
            codigo_cliente,
            fecha_despacho,
            codigo_factura,
            anulada,
            numero_pedido_sistema,
            numero_orden,
            numero_factura,
            tipo_documento,
            orden_compra,
            orden_compra_cliente,
            remision_facturada,
            num_id_factura_relacionada,
            codigo_despacho,
            fecha_factura,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
        """
        
        values = (
            despacho_id,
            factura.get("EMPRESA"),
            factura.get("CODIGO_CLIENTE"),
            fecha_despacho,  # fecha_despacho (usa fecha_factura)
            factura.get("CODIGO_FACTURA"),
            1 if factura.get("ANULADA") else 0,  # Convertir boolean a bit
            factura.get("NUMERO_PEDIDO_SISTEMA"),
            factura.get("NUMERO_ORDEN"),
            factura.get("NUMERO_FACTURA"),
            factura.get("TIPO_DOCUMENTO"),
            factura.get("ORDEN_COMPRA") or None,  # Vacío string a None
            factura.get("ORDEN_COMPRA_CLIENTE") or None,
            1 if factura.get("Remision_Facturada") else 0,
            factura.get("NumIDFacturaRelacionada"),
            factura.get("CODIGO_DESPACHO"),
            fecha_factura,  # fecha_factura original
        )
        
        cursor.execute(sql, values)
        conn.commit()
        
        logger.debug(f"✅ Despacho cabecera insertado: {despacho_id} - {factura.get('CODIGO_FACTURA')}")
        return despacho_id
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Error al insertar despacho_cabecera: {e}")
        logger.error(f"   Factura: {factura.get('CODIGO_FACTURA')}")
        raise
    finally:
        cursor.close()


def insert_despacho_detalle(
    conn: pyodbc.Connection,
    despacho_id: str,
    obj_datos_factura: Dict[str, Any],
    tipo_linea: str
) -> int:
    """
    Inserta líneas de detalle en despacho_detalle a partir de un array de ObjDatosFactura.
    
    Args:
        conn: Conexión a SQL Server
        despacho_id: UUID de la cabecera de despacho
        obj_datos_factura: Array de líneas de factura (puede ser None o lista vacía)
        tipo_linea: Tipo de línea (GrabarLineasProd, CtrlEliminados1, etc.)
        
    Returns:
        Número de líneas insertadas
    """
    if not obj_datos_factura:
        return 0
    
    cursor = conn.cursor()
    inserted_count = 0
    
    try:
        sql = """
        INSERT INTO despacho_detalle (
            detalle_id,
            despacho_id,
            sku,
            cantidad,
            precio_unitario,
            total_linea,
            descuento,
            tipo_linea,
            nombre_producto,
            impuesto,
            reg_num
        ) VALUES (NEWID(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        for linea in obj_datos_factura:
            try:
                # Extraer datos de la línea
                codigo = linea.get("Codigo") or None
                nombre = linea.get("Nombre") or None
                cantidad = linea.get("Cantidad") or 0
                precio_unitario = linea.get("PrecioUnitario") or 0
                total_linea = linea.get("TotalLinea") or 0
                descuento = linea.get("Descuento") or 0
                impuesto = linea.get("Impuesto")  # Puede ser None
                reg_num = linea.get("RegNum")  # Puede ser None
                
                # Solo insertar si hay un código de producto válido
                if codigo and codigo.strip():
                    values = (
                        despacho_id,
                        codigo,  # sku
                        cantidad,
                        precio_unitario,
                        total_linea,
                        descuento,
                        tipo_linea,
                        nombre,  # nombre_producto
                        impuesto,
                        reg_num,
                    )
                    
                    cursor.execute(sql, values)
                    inserted_count += 1
                    logger.debug(f"   → Línea insertada: {codigo} ({tipo_linea})")
                else:
                    logger.debug(f"   → Línea omitida (sin código): {tipo_linea}")
                    
            except Exception as e:
                logger.warning(f"   ⚠️ Error al insertar línea de detalle: {e}")
                logger.warning(f"      Tipo: {tipo_linea}, Datos: {linea}")
                continue
        
        conn.commit()
        logger.debug(f"✅ {inserted_count} líneas de detalle insertadas (tipo: {tipo_linea})")
        return inserted_count
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Error al insertar despacho_detalle: {e}")
        raise
    finally:
        cursor.close()


def save_mba3_factura_to_sql_server(
    conn: pyodbc.Connection,
    factura: Dict[str, Any],
    upsert: bool = False
) -> Dict[str, Any]:
    """
    Guarda una factura completa de MBA3 en SQL Server (cabecera + detalles).
    
    Args:
        conn: Conexión a SQL Server
        factura: Diccionario con datos de factura de MBA3
        upsert: Si True, actualiza si existe; si False, inserta siempre
        
    Returns:
        Dict con estadísticas de la operación:
        {
            "status": "success" o "error",
            "despacho_id": UUID,
            "cabecera_insertada": bool,
            "detalles_insertados": int,
            "errors": []
        }
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
            cursor = conn.cursor()
            cursor.execute(
                "SELECT despacho_id FROM despacho_cabecera WHERE codigo_factura = ?",
                (codigo_factura,)
            )
            existing = cursor.fetchone()
            cursor.close()
            
            if existing:
                result["despacho_id"] = str(existing[0])
                logger.info(f"⚠️ Factura ya existe: {codigo_factura} (despacho_id: {result['despacho_id']})")
                # Por ahora, solo retornamos que ya existe. Puedes implementar UPDATE aquí si necesitas
                result["status"] = "exists"
                return result
        
        # Insertar cabecera
        despacho_id = insert_despacho_cabecera(conn, factura)
        result["despacho_id"] = despacho_id
        result["cabecera_insertada"] = True
        
        # Insertar detalles desde ObjDatosFactura
        obj_datos = factura.get("ObjDatosFactura")
        if obj_datos:
            # Tipos de arrays que pueden existir en ObjDatosFactura
            tipos_lineas = [
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
            
            for tipo_linea in tipos_lineas:
                if tipo_linea in obj_datos and obj_datos[tipo_linea]:
                    try:
                        count = insert_despacho_detalle(
                            conn,
                            despacho_id,
                            obj_datos[tipo_linea],
                            tipo_linea
                        )
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
        Dict con estadísticas de la operación:
        {
            "status": "success" o "partial" o "error",
            "total_facturas": int,
            "facturas_guardadas": int,
            "facturas_existentes": int,
            "total_detalles": int,
            "errors": []
        }
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
        
        # Procesar según el tipo de resultado
        facturas = []
        
        if isinstance(mba3_json_result, list):
            facturas = mba3_json_result
        elif isinstance(mba3_json_result, dict):
            # Si es un dict único, tratarlo como una factura
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
                
                result = save_mba3_factura_to_sql_server(conn, factura, upsert=upsert)
                
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

