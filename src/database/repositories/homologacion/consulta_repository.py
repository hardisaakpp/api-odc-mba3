"""
Repositorio interno para consultas de productos no homologados.
"""

import logging
import pyodbc
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class ConsultaRepository:
    """Repositorio para consultar productos no homologados."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def get_productos_no_homologados(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los productos de MBA3 que NO están homologados en SAP.
        
        Un producto NO está homologado si:
        - Existe en despacho_detalle (viene de MBA3)
        - NO existe en producto_sap_cache (nunca se consultó en SAP o no existe)
        
        Returns:
            Lista de diccionarios con información de productos no homologados:
            [
                {
                    "sku": "5-0012.9",
                    "nombre_producto": "Nombre del producto",
                    "veces_usado": 15,
                    "total_docenas": 456.0,
                    "total_valor": 2120.4,
                    "primera_aparicion": "2024-01-15",
                    "ultima_aparicion": "2024-03-20"
                },
                ...
            ]
        """
        cursor = self.conn.cursor()
        try:
            query = """
            SELECT 
                dd.sku,
                dd.nombre_producto,
                COUNT(*) AS veces_usado,
                SUM(dd.cantidad_docena_mba3) AS total_docenas,
                SUM(dd.total_linea_mba3) AS total_valor,
                MIN(dc.fecha_despacho) AS primera_aparicion,
                MAX(dc.fecha_despacho) AS ultima_aparicion
            FROM despacho_detalle dd
            INNER JOIN despacho_cabecera dc ON dd.despacho_id = dc.despacho_id
            LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
            WHERE dd.sku IS NOT NULL 
              AND dd.sku != ''
              AND psc.sku IS NULL  -- NO está en cache SAP (no homologado)
            GROUP BY dd.sku, dd.nombre_producto
            ORDER BY COUNT(*) DESC, dd.sku
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            productos = []
            for row in results:
                productos.append({
                    "sku": row[0],
                    "nombre_producto": row[1] if row[1] else "Sin nombre",
                    "veces_usado": row[2],
                    "total_docenas": float(row[3]) if row[3] is not None else 0.0,
                    "total_valor": float(row[4]) if row[4] is not None else 0.0,
                    "primera_aparicion": row[5].strftime("%Y-%m-%d") if row[5] else None,
                    "ultima_aparicion": row[6].strftime("%Y-%m-%d") if row[6] else None,
                })
            
            logger.debug(f"✅ Encontrados {len(productos)} productos no homologados")
            return productos
            
        except Exception as e:
            logger.error(f"❌ Error al consultar productos no homologados: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_skus_no_homologados(self) -> List[str]:
        """
        Obtiene una lista simple de SKUs no homologados.
        
        Returns:
            Lista de SKUs (strings)
        """
        cursor = self.conn.cursor()
        try:
            query = """
            SELECT DISTINCT dd.sku
            FROM despacho_detalle dd
            LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
            WHERE dd.sku IS NOT NULL 
              AND dd.sku != ''
              AND psc.sku IS NULL
            ORDER BY dd.sku
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            skus = [row[0] for row in results]
            return skus
            
        except Exception as e:
            logger.error(f"❌ Error al obtener SKUs no homologados: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_productos_no_homologados_por_empresa(self) -> List[Dict[str, Any]]:
        """
        Obtiene productos no homologados agrupados por empresa.
        
        Returns:
            Lista de diccionarios con información agrupada por empresa
        """
        cursor = self.conn.cursor()
        try:
            query = """
            SELECT 
                dc.empresa,
                dd.sku,
                dd.nombre_producto,
                COUNT(*) AS veces_usado,
                SUM(dd.cantidad_docena_mba3) AS total_docenas
            FROM despacho_detalle dd
            INNER JOIN despacho_cabecera dc ON dd.despacho_id = dc.despacho_id
            LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
            WHERE dd.sku IS NOT NULL 
              AND dd.sku != ''
              AND psc.sku IS NULL
            GROUP BY dc.empresa, dd.sku, dd.nombre_producto
            ORDER BY dc.empresa, COUNT(*) DESC
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            productos = []
            for row in results:
                productos.append({
                    "empresa": row[0],
                    "sku": row[1],
                    "nombre_producto": row[2] if row[2] else "Sin nombre",
                    "veces_usado": row[3],
                    "total_docenas": float(row[4]) if row[4] is not None else 0.0,
                })
            
            return productos
            
        except Exception as e:
            logger.error(f"❌ Error al consultar productos no homologados por empresa: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

