"""
Repositorio para operaciones de producto_sap_staging en SQL Server.
"""

import logging
import pyodbc
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ProductoSAPStagingRepository:
    """Repositorio para operaciones de producto_sap_staging."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def find_by_item_code(self, item_code: str) -> Optional[Dict[str, Any]]:
        """
        Busca un producto por item_code.
        
        Args:
            item_code: ItemCode del producto a buscar
            
        Returns:
            Diccionario con datos del producto, o None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT 
                    staging_id,
                    item_code,
                    item_name,
                    pack_sap,
                    itms_grp_cod,
                    itms_grp_nam,
                    valid_for,
                    activo,
                    item_code_normalizado,
                    ultima_sincronizacion,
                    created_at,
                    updated_at
                FROM producto_sap_staging
                WHERE item_code = ?
            """, (item_code,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                "staging_id": str(row[0]),
                "item_code": row[1],
                "item_name": row[2],
                "pack_sap": row[3],
                "itms_grp_cod": row[4],
                "itms_grp_nam": row[5],
                "valid_for": row[6],
                "activo": bool(row[7]),
                "item_code_normalizado": row[8],
                "ultima_sincronizacion": row[9].isoformat() if row[9] else None,
                "created_at": row[10].isoformat() if row[10] else None,
                "updated_at": row[11].isoformat() if row[11] else None
            }
        except Exception as e:
            logger.error(f"❌ Error al buscar producto SAP {item_code}: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_all_active(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los productos activos (activo = 1).
        
        Returns:
            Lista de productos activos
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT 
                    staging_id,
                    item_code,
                    item_name,
                    pack_sap,
                    itms_grp_cod,
                    itms_grp_nam,
                    valid_for,
                    activo,
                    item_code_normalizado,
                    ultima_sincronizacion,
                    created_at,
                    updated_at
                FROM producto_sap_staging
                WHERE activo = 1
                ORDER BY item_code
            """)
            
            productos = []
            for row in cursor.fetchall():
                productos.append({
                    "item_code": row[1],
                    "item_name": row[2] or "",
                    "pack": row[3] or "",
                    "group_code": row[4],
                    "group_name": row[5] or "",
                    "valid_for": row[6] or "N",
                    "active": bool(row[7]),
                    "item_code_normalizado": row[8]
                })
            
            return productos
        except Exception as e:
            logger.error(f"❌ Error al obtener productos SAP activos: {e}", exc_info=True)
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
            item_code = producto_data.get("item_code")
            if not item_code:
                raise ValueError("item_code es requerido")
            
            # Verificar si existe
            existing = self.find_by_item_code(item_code)
            now = datetime.now()
            
            if existing:
                # UPDATE
                cursor.execute("""
                    UPDATE producto_sap_staging
                    SET 
                        item_name = ?,
                        pack_sap = ?,
                        itms_grp_cod = ?,
                        itms_grp_nam = ?,
                        valid_for = ?,
                        activo = ?,
                        item_code_normalizado = ?,
                        ultima_sincronizacion = ?,
                        updated_at = ?
                    WHERE item_code = ?
                """, (
                    producto_data.get("item_name", ""),
                    producto_data.get("pack_sap", ""),
                    producto_data.get("itms_grp_cod"),
                    producto_data.get("itms_grp_nam", ""),
                    producto_data.get("valid_for", "N"),
                    producto_data.get("activo", False),
                    producto_data.get("item_code_normalizado", ""),
                    now,
                    now,
                    item_code
                ))
                self.conn.commit()
                return False  # Actualizado
            else:
                # INSERT
                cursor.execute("""
                    INSERT INTO producto_sap_staging (
                        item_code,
                        item_name,
                        pack_sap,
                        itms_grp_cod,
                        itms_grp_nam,
                        valid_for,
                        activo,
                        item_code_normalizado,
                        ultima_sincronizacion,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item_code,
                    producto_data.get("item_name", ""),
                    producto_data.get("pack_sap", ""),
                    producto_data.get("itms_grp_cod"),
                    producto_data.get("itms_grp_nam", ""),
                    producto_data.get("valid_for", "N"),
                    producto_data.get("activo", False),
                    producto_data.get("item_code_normalizado", ""),
                    now,
                    now,
                    now
                ))
                self.conn.commit()
                return True  # Insertado
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar/actualizar producto SAP: {e}", exc_info=True)
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
                logger.error(f"❌ Error procesando producto {producto.get('item_code')}: {e}")
                continue
        
        return stats
    
    def get_last_item_code(self) -> Optional[str]:
        """
        Obtiene el último item_code procesado (ordenado alfabéticamente).
        
        Returns:
            Último item_code o None si no hay productos
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT TOP 1 item_code
                FROM producto_sap_staging
                ORDER BY item_code DESC
            """)
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"❌ Error al obtener último item_code: {e}", exc_info=True)
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
            cursor.execute("SELECT COUNT(*) FROM producto_sap_staging")
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"❌ Error al contar productos: {e}", exc_info=True)
            return 0
        finally:
            cursor.close()
    
    def buscar_por_normalizado_similar(
        self, 
        codigo_normalizado: str, 
        limite: int = 20,
        solo_activos: bool = True,
        longitud_minima: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Busca productos por código normalizado usando LIKE sobre item_code_normalizado.
        
        Esta búsqueda es eficiente porque usa el índice sobre item_code_normalizado
        y permite encontrar productos con diferentes separadores ya que la normalización
        elimina separadores comunes (., -, /, _, espacio).
        
        VALIDACIÓN: Si el código normalizado es muy corto (< longitud_minima),
        puede devolver demasiados resultados. Se registra un warning pero no se bloquea.
        
        Args:
            codigo_normalizado: Código normalizado (sin separadores, ya procesado)
            limite: Límite máximo de resultados a retornar (se busca 3x más antes del scoring)
            solo_activos: Si True, solo productos activos (activo = 1)
            longitud_minima: Longitud mínima del código normalizado (validación)
            
        Returns:
            Lista de productos encontrados con formato esperado por SAPClient
        """
        # Validación de longitud mínima (registrar warning pero no bloquear)
        if len(codigo_normalizado) < longitud_minima:
            logger.warning(
                f"⚠️ Código normalizado muy corto ({len(codigo_normalizado)} < {longitud_minima}): "
                f"'{codigo_normalizado}'. La búsqueda puede devolver muchos resultados."
            )
        
        cursor = self.conn.cursor()
        try:
            # Escapar caracteres especiales para LIKE
            codigo_escaped = codigo_normalizado.replace("%", "[%]").replace("_", "[_]")
            
            where_clause = "item_code_normalizado LIKE ?"
            params = [f"%{codigo_escaped}%"]
            
            if solo_activos:
                where_clause += " AND activo = 1"
            
            # Pedir más resultados para que scoring tenga mejor selección
            # El scoring luego limitará a la cantidad solicitada
            limite_busqueda = limite * 3
            
            query = f"""
                SELECT TOP {limite_busqueda}
                    staging_id,
                    item_code,
                    item_name,
                    pack_sap,
                    itms_grp_cod,
                    itms_grp_nam,
                    valid_for,
                    activo,
                    item_code_normalizado
                FROM producto_sap_staging
                WHERE {where_clause}
                ORDER BY item_code
            """
            
            cursor.execute(query, params)
            
            productos = []
            for row in cursor.fetchall():
                productos.append({
                    "ItemCode": row[1],
                    "ItemName": row[2] or "",
                    "U_IXX_PACK": row[3] or "",
                    "ItmsGrpNam": row[5] or "",
                    "ItmsGrpCod": row[4],
                    "validFor": row[6] or "N",
                    "item_code_normalizado": row[8]  # Ya viene normalizado de staging
                })
            
            logger.debug(
                f"✅ Staging: {len(productos)} productos encontrados para código normalizado '{codigo_normalizado}'"
            )
            
            return productos
            
        except Exception as e:
            logger.error(f"❌ Error al buscar por código normalizado '{codigo_normalizado}': {e}", exc_info=True)
            raise
        finally:
            cursor.close()

