"""
Cliente para consultar información de productos desde SAP (HANA) usando OPENQUERY.

Este cliente ejecuta consultas OPENQUERY desde SQL Server hacia SAP HANA
para obtener información de productos (ItemCode, ItemName, U_IXX_PACK).
"""

import logging
import pyodbc
from typing import Optional, Dict, Any
from datetime import datetime

from config import (
    SAP_LINKED_SERVER,
    SAP_DATABASE,
    SAP_SCHEMA,
    ENABLE_SAP_QUERIES
)
from ..connection import get_sap_db_connection

logger = logging.getLogger(__name__)


class SAPClient:
    """Cliente para consultar información de productos desde SAP."""
    
    def __init__(self):
        """Inicializa el cliente SAP."""
        self.enabled = ENABLE_SAP_QUERIES
        if not self.enabled:
            logger.warning("⚠️ Consultas SAP deshabilitadas (ENABLE_SAP_QUERIES=False)")
    
    def get_producto_info(self, item_code: str) -> Optional[Dict[str, Any]]:
        """
        Consulta información de un producto desde SAP usando OPENQUERY.
        
        Args:
            item_code: Código del producto (ItemCode) a consultar
            
        Returns:
            Diccionario con información del producto:
            {
                "ItemCode": "5-0012.9",
                "ItemName": "Nombre del producto",
                "U_IXX_PACK": "X3"
            }
            O None si no se encuentra o hay error
            
        Raises:
            Exception: Si hay error de conexión o consulta
        """
        if not self.enabled:
            logger.debug(f"⏭️ Consulta SAP deshabilitada para ItemCode: {item_code}")
            return None
        
        if not item_code or not item_code.strip():
            logger.warning("⚠️ ItemCode vacío o inválido")
            return None
        
        # Escapar comillas simples en el item_code para la consulta SQL
        item_code_escaped = item_code.replace("'", "''")
        
        # Construir consulta OPENQUERY
        # Nota: El servidor vinculado debe estar configurado en SQL Server
        query = f"""
        SELECT 
            T0."ItemCode",
            T0."ItemName",
            T0."U_IXX_PACK"
        FROM OPENQUERY([{SAP_LINKED_SERVER}], '
            SELECT 
                "ItemCode",
                "ItemName",
                "U_IXX_PACK"
            FROM "{SAP_DATABASE}"."OITM"
            WHERE "ItemCode" = ''{item_code_escaped}''
            LIMIT 100
        ') T0;
        """
        
        conn = None
        try:
            logger.debug(f"🔍 Consultando SAP para ItemCode: {item_code}")
            # Usar conexión específica para SAP (servidor con OPENQUERY)
            conn = get_sap_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(query)
            result = cursor.fetchone()
            
            if result:
                producto_info = {
                    "ItemCode": result[0] if result[0] else None,
                    "ItemName": result[1] if result[1] else None,
                    "U_IXX_PACK": result[2] if result[2] else None,
                }
                logger.info(f"✅ Producto encontrado en SAP: {item_code} - Pack: {producto_info.get('U_IXX_PACK')}")
                return producto_info
            else:
                logger.warning(f"⚠️ Producto no encontrado en SAP: {item_code}")
                return None
                
        except pyodbc.Error as e:
            error_msg = f"Error al consultar SAP para ItemCode {item_code}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            # No lanzar excepción, retornar None para que el sistema continúe
            return None
        except Exception as e:
            error_msg = f"Error inesperado al consultar SAP para ItemCode {item_code}: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            return None
        finally:
            if conn:
                try:
                    cursor.close()
                    conn.close()
                except:
                    pass
    
    def get_productos_info_batch(self, item_codes: list[str]) -> Dict[str, Dict[str, Any]]:
        """
        Consulta información de múltiples productos desde SAP en batch.
        
        Args:
            item_codes: Lista de códigos de productos a consultar
            
        Returns:
            Diccionario con ItemCode como clave y información del producto como valor:
            {
                "5-0012.9": {
                    "ItemCode": "5-0012.9",
                    "ItemName": "Nombre",
                    "U_IXX_PACK": "X3"
                },
                ...
            }
        """
        if not self.enabled:
            logger.debug(f"⏭️ Consulta SAP batch deshabilitada para {len(item_codes)} productos")
            return {}
        
        if not item_codes:
            return {}
        
        resultados = {}
        
        # Consultar cada producto individualmente
        # (Se podría optimizar con una consulta IN, pero OPENQUERY puede tener limitaciones)
        for item_code in item_codes:
            try:
                info = self.get_producto_info(item_code)
                if info:
                    resultados[item_code] = info
            except Exception as e:
                logger.warning(f"⚠️ Error al consultar {item_code}: {e}")
                continue
        
        logger.info(f"✅ Consultados {len(resultados)} de {len(item_codes)} productos desde SAP")
        return resultados

