"""
Repositorio para operaciones relacionadas con homologación de productos.
"""

import logging
import pyodbc
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class HomologacionRepository:
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
    
    def is_sku_ya_notificado(self, sku: str) -> bool:
        """
        Verifica si un SKU ya fue notificado anteriormente.
        
        Args:
            sku: SKU del producto a verificar
            
        Returns:
            True si ya fue notificado, False en caso contrario
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT COUNT(*) 
                FROM productos_no_homologados_notificados
                WHERE sku = ? AND activo = 1
                """,
                (sku,)
            )
            result = cursor.fetchone()
            return result[0] > 0 if result else False
        except Exception as e:
            logger.error(f"❌ Error al verificar si SKU ya fue notificado: {e}", exc_info=True)
            # En caso de error, retornar False para no bloquear la notificación
            return False
        finally:
            cursor.close()
    
    def get_skus_ya_notificados(self) -> set:
        """
        Obtiene el conjunto de SKUs que ya fueron notificados.
        
        Returns:
            Set de SKUs ya notificados
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT sku 
                FROM productos_no_homologados_notificados
                WHERE activo = 1
                """
            )
            results = cursor.fetchall()
            return {row[0] for row in results}
        except Exception as e:
            logger.error(f"❌ Error al obtener SKUs ya notificados: {e}", exc_info=True)
            # En caso de error, retornar set vacío
            return set()
        finally:
            cursor.close()
    
    def registrar_producto_notificado(self, sku: str) -> bool:
        """
        Registra un producto como notificado (o actualiza si ya existe).
        
        Args:
            sku: SKU del producto notificado
            
        Returns:
            True si se registró correctamente, False en caso contrario
        """
        cursor = self.conn.cursor()
        try:
            # Verificar si ya existe
            cursor.execute(
                """
                SELECT notificacion_id, veces_notificado
                FROM productos_no_homologados_notificados
                WHERE sku = ? AND activo = 1
                """,
                (sku,)
            )
            existing = cursor.fetchone()
            
            if existing:
                # ACTUALIZAR: incrementar contador y actualizar fecha
                cursor.execute(
                    """
                    UPDATE productos_no_homologados_notificados
                    SET veces_notificado = veces_notificado + 1,
                        ultima_notificacion = GETDATE(),
                        updated_at = GETDATE()
                    WHERE sku = ? AND activo = 1
                    """,
                    (sku,)
                )
                logger.debug(f"✅ Producto {sku} actualizado en notificados (veces: {existing[1] + 1})")
            else:
                # INSERTAR: primera notificación
                cursor.execute(
                    """
                    INSERT INTO productos_no_homologados_notificados (
                        sku,
                        fecha_notificacion,
                        veces_notificado,
                        ultima_notificacion,
                        activo,
                        created_at,
                        updated_at
                    ) VALUES (?, GETDATE(), 1, GETDATE(), 1, GETDATE(), GETDATE())
                    """,
                    (sku,)
                )
                logger.debug(f"✅ Producto {sku} registrado como notificado")
            
            self.conn.commit()
            return True
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al registrar producto notificado: {e}", exc_info=True)
            return False
        finally:
            cursor.close()
    
    def registrar_productos_notificados(self, skus: List[str]) -> int:
        """
        Registra múltiples productos como notificados.
        
        Args:
            skus: Lista de SKUs a registrar
            
        Returns:
            Número de productos registrados exitosamente
        """
        if not skus:
            return 0
        
        registrados = 0
        for sku in skus:
            if self.registrar_producto_notificado(sku):
                registrados += 1
        
        logger.info(f"✅ Registrados {registrados} de {len(skus)} productos como notificados")
        return registrados


