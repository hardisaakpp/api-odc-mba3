"""
Repositorio para operaciones de producto_mba3_staging en SQL Server.
"""

import logging
import pyodbc
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ProductoMBA3StagingRepository:
    """Repositorio para operaciones de producto_mba3_staging."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def find_by_product_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca un producto por product_id.
        
        Args:
            product_id: ID del producto a buscar
            
        Returns:
            Diccionario con datos del producto, o None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT 
                    staging_id,
                    product_id,
                    product_name,
                    corp,
                    grupo_prenda,
                    talla,
                    presentacion,
                    descontinuado,
                    product_id_normalizado,
                    ultima_sincronizacion,
                    created_at,
                    updated_at
                FROM producto_mba3_staging
                WHERE product_id = ?
            """, (product_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                "staging_id": str(row[0]),
                "product_id": row[1],
                "product_name": row[2],
                "corp": row[3],
                "grupo_prenda": row[4],
                "talla": row[5],
                "presentacion": row[6],
                "descontinuado": bool(row[7]),
                "product_id_normalizado": row[8],
                "ultima_sincronizacion": row[9].isoformat() if row[9] else None,
                "created_at": row[10].isoformat() if row[10] else None,
                "updated_at": row[11].isoformat() if row[11] else None
            }
        except Exception as e:
            logger.error(f"❌ Error al buscar producto MBA3 {product_id}: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_all_active(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los productos activos (no descontinuados).
        
        Returns:
            Lista de productos activos
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT 
                    staging_id,
                    product_id,
                    product_name,
                    corp,
                    grupo_prenda,
                    talla,
                    presentacion,
                    descontinuado,
                    product_id_normalizado,
                    ultima_sincronizacion,
                    created_at,
                    updated_at
                FROM producto_mba3_staging
                WHERE descontinuado = 0
                ORDER BY product_id
            """)
            
            productos = []
            for row in cursor.fetchall():
                productos.append({
                    "product_id": row[1],
                    "product_name": row[2] or "",
                    "corp": row[3] or "",
                    "grupo_prenda": row[4] or "",
                    "talla": row[5] or "",
                    "presentacion": row[6] or "",
                    "descontinuado": bool(row[7]),
                    "product_id_normalizado": row[8]
                })
            
            return productos
        except Exception as e:
            logger.error(f"❌ Error al obtener productos MBA3 activos: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def insert_or_update(self, producto_data: Dict[str, Any]) -> bool:
        """
        Inserta o actualiza un producto (UPSERT).
        
        Args:
            producto_data: Diccionario con datos del producto
            
        Returns:
            True si se insertó, False si se actualizó
        """
        cursor = self.conn.cursor()
        try:
            product_id = producto_data.get("product_id")
            if not product_id:
                raise ValueError("product_id es requerido")
            
            # Verificar si existe
            existing = self.find_by_product_id(product_id)
            now = datetime.now()
            
            if existing:
                # UPDATE
                cursor.execute("""
                    UPDATE producto_mba3_staging
                    SET 
                        product_name = ?,
                        corp = ?,
                        grupo_prenda = ?,
                        talla = ?,
                        presentacion = ?,
                        descontinuado = ?,
                        product_id_normalizado = ?,
                        ultima_sincronizacion = ?,
                        updated_at = ?
                    WHERE product_id = ?
                """, (
                    producto_data.get("product_name", ""),
                    producto_data.get("corp", ""),
                    producto_data.get("grupo_prenda", ""),
                    producto_data.get("talla", ""),
                    producto_data.get("presentacion", ""),
                    producto_data.get("descontinuado", False),
                    producto_data.get("product_id_normalizado", ""),
                    now,
                    now,
                    product_id
                ))
                self.conn.commit()
                return False  # Actualizado
            else:
                # INSERT
                cursor.execute("""
                    INSERT INTO producto_mba3_staging (
                        product_id,
                        product_name,
                        corp,
                        grupo_prenda,
                        talla,
                        presentacion,
                        descontinuado,
                        product_id_normalizado,
                        ultima_sincronizacion,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    product_id,
                    producto_data.get("product_name", ""),
                    producto_data.get("corp", ""),
                    producto_data.get("grupo_prenda", ""),
                    producto_data.get("talla", ""),
                    producto_data.get("presentacion", ""),
                    producto_data.get("descontinuado", False),
                    producto_data.get("product_id_normalizado", ""),
                    now,
                    now,
                    now
                ))
                self.conn.commit()
                return True  # Insertado
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar/actualizar producto MBA3: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def bulk_insert_or_update(self, productos: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Inserta o actualiza múltiples productos en lote.
        
        Args:
            productos: Lista de diccionarios con datos de productos
            
        Returns:
            Diccionario con estadísticas de la operación
        """
        stats = {
            "insertados": 0,
            "actualizados": 0,
            "errores": 0,
            "total": len(productos)
        }
        
        for producto in productos:
            try:
                is_new = self.insert_or_update(producto)
                if is_new:
                    stats["insertados"] += 1
                else:
                    stats["actualizados"] += 1
            except Exception as e:
                stats["errores"] += 1
                logger.error(f"❌ Error procesando producto {producto.get('product_id')}: {e}")
                continue
        
        return stats
    
    def get_last_product_id(self) -> Optional[str]:
        """
        Obtiene el último product_id procesado (ordenado alfabéticamente).
        
        Returns:
            Último product_id o None si no hay productos
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT TOP 1 product_id
                FROM producto_mba3_staging
                ORDER BY product_id DESC
            """)
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"❌ Error al obtener último product_id: {e}", exc_info=True)
            return None
        finally:
            cursor.close()
    
    def count_all(self) -> int:
        """
        Cuenta el total de productos en staging.
        
        Returns:
            Número total de productos
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM producto_mba3_staging")
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"❌ Error al contar productos: {e}", exc_info=True)
            return 0
        finally:
            cursor.close()





