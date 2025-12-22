"""
Repositorio interno para estadísticas de homologación.
"""

import logging
import pyodbc
from typing import Dict, Any

logger = logging.getLogger(__name__)


class EstadisticasRepository:
    """Repositorio para obtener estadísticas de homologación."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def get_estadisticas_homologacion(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas generales de homologación.
        
        Returns:
            Diccionario con estadísticas:
            {
                "total_productos_mba3": 150,
                "productos_homologados": 145,
                "productos_no_homologados": 5,
                "porcentaje_homologacion": 96.67
            }
        """
        cursor = self.conn.cursor()
        try:
            query = """
            SELECT 
                (SELECT COUNT(DISTINCT dd.sku) 
                 FROM despacho_detalle dd 
                 WHERE dd.sku IS NOT NULL AND dd.sku != '') AS total_productos_mba3,
                (SELECT COUNT(DISTINCT psc.sku) 
                 FROM producto_sap_cache psc 
                 WHERE psc.activo = 1) AS productos_homologados,
                (SELECT COUNT(DISTINCT dd.sku) 
                 FROM despacho_detalle dd
                 LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
                 WHERE dd.sku IS NOT NULL 
                   AND dd.sku != ''
                   AND psc.sku IS NULL) AS productos_no_homologados
            """
            
            cursor.execute(query)
            result = cursor.fetchone()
            
            if result:
                total_mba3 = result[0] or 0
                homologados = result[1] or 0
                no_homologados = result[2] or 0
                
                porcentaje = (homologados * 100.0 / total_mba3) if total_mba3 > 0 else 0.0
                
                return {
                    "total_productos_mba3": total_mba3,
                    "productos_homologados": homologados,
                    "productos_no_homologados": no_homologados,
                    "porcentaje_homologacion": round(porcentaje, 2)
                }
            
            return {
                "total_productos_mba3": 0,
                "productos_homologados": 0,
                "productos_no_homologados": 0,
                "porcentaje_homologacion": 0.0
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener estadísticas de homologación: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_estadisticas_homologaciones_sku(self) -> Dict[str, int]:
        """
        Obtiene estadísticas de homologaciones por estado.
        
        Returns:
            Diccionario con conteos por estado
        """
        cursor = self.conn.cursor()
        try:
            query = """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN estado = 'PENDIENTE' THEN 1 ELSE 0 END) as pendientes,
                    SUM(CASE WHEN estado = 'HOMOLOGADO' THEN 1 ELSE 0 END) as homologados,
                    SUM(CASE WHEN estado = 'ERROR' THEN 1 ELSE 0 END) as errores
                FROM sku_homologacion
            """
            cursor.execute(query)
            row = cursor.fetchone()
            
            if row:
                return {
                    "count": row[0] or 0,
                    "total_pendientes": row[1] or 0,
                    "total_homologados": row[2] or 0,
                    "total_errores": row[3] or 0
                }
            
            return {
                "count": 0,
                "total_pendientes": 0,
                "total_homologados": 0,
                "total_errores": 0
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener estadísticas de homologaciones: {e}", exc_info=True)
            return {
                "count": 0,
                "total_pendientes": 0,
                "total_homologados": 0,
                "total_errores": 0
            }
        finally:
            cursor.close()

