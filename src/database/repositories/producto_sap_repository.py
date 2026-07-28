"""
Repositorio para operaciones CRUD de producto_sap_cache en SQL Server.
"""

import logging
import pyodbc
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)


class ProductoSAPRepository:
    """Repositorio para operaciones de producto_sap_cache."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def find_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Busca un producto en el cache por SKU.
        
        Args:
            sku: SKU del producto a buscar
            
        Returns:
            Diccionario con datos del producto cacheado, o None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT 
                    cache_id,
                    sku,
                    item_code,
                    item_name,
                    pack_sap,
                    unidad_conversion,
                    pack_id,
                    grupo_articulos,
                    ultima_consulta,
                    activo,
                    created_at,
                    updated_at
                FROM producto_sap_cache
                WHERE sku = ? AND activo = 1
                """,
                (sku,)
            )
            result = cursor.fetchone()
            
            if result:
                return {
                    "cache_id": str(result[0]),
                    "sku": result[1],
                    "item_code": result[2],
                    "item_name": result[3],
                    "pack_sap": result[4],
                    "unidad_conversion": float(result[5]) if result[5] is not None else None,
                    "pack_id": result[6],
                    "grupo_articulos": result[7],
                    "ultima_consulta": result[8],
                    "activo": bool(result[9]),
                    "created_at": result[10],
                    "updated_at": result[11],
                }
            return None
        finally:
            cursor.close()
    
    def is_cache_valid(self, sku: str, cache_days: int = 30) -> bool:
        """
        Verifica si el cache de un producto es válido (no ha expirado).
        
        Args:
            sku: SKU del producto
            cache_days: Días de validez del cache (por defecto 30)
            
        Returns:
            True si el cache existe y es válido, False en caso contrario
        """
        producto = self.find_by_sku(sku)
        if not producto:
            return False
        
        ultima_consulta = producto.get("ultima_consulta")
        if not ultima_consulta:
            return False
        
        # Verificar si la última consulta es más antigua que cache_days
        if isinstance(ultima_consulta, str):
            ultima_consulta = datetime.fromisoformat(ultima_consulta.replace('Z', '+00:00'))
        elif not isinstance(ultima_consulta, datetime):
            return False
        
        fecha_limite = ahora_naive() - timedelta(days=cache_days)
        return ultima_consulta >= fecha_limite
    
    def insert_or_update(self, producto_data: Dict[str, Any]) -> bool:
        """
        Inserta o actualiza un producto en el cache (UPSERT).
        
        Args:
            producto_data: Diccionario con datos del producto:
                - sku: SKU del producto (requerido)
                - item_code: ItemCode de SAP
                - item_name: Nombre del producto
                - pack_sap: Pack de SAP (X1, X2, etc.)
                - unidad_conversion: Unidad de conversión calculada
                - pack_id: ID del pack en pack_conversion
                - grupo_articulos: Grupo de artículos (ItmsGrpNam)
                
        Returns:
            True si se insertó/actualizó correctamente
        """
        cursor = self.conn.cursor()
        
        try:
            sku = producto_data.get("sku")
            if not sku:
                raise ValueError("SKU es requerido")
            
            # Verificar si ya existe
            existing = self.find_by_sku(sku)
            
            if existing:
                # ACTUALIZAR
                sql = """
                UPDATE producto_sap_cache SET
                    item_code = ?,
                    item_name = ?,
                    pack_sap = ?,
                    unidad_conversion = ?,
                    pack_id = ?,
                    grupo_articulos = ?,
                    ultima_consulta = ?,
                    updated_at = ?
                WHERE sku = ? AND activo = 1
                """
                
                values = (
                    producto_data.get("item_code", sku),
                    producto_data.get("item_name"),
                    producto_data.get("pack_sap"),
                    producto_data.get("unidad_conversion"),
                    producto_data.get("pack_id"),
                    producto_data.get("grupo_articulos"),
                    ahora_naive(),
                    ahora_naive(),
                    sku,
                )
                
                cursor.execute(sql, values)
                self.conn.commit()
                logger.debug(f"✅ Producto SAP cache actualizado: {sku}")
                affected_rows = cursor.rowcount
                if affected_rows in (-1, None):
                    return True
                if isinstance(affected_rows, int):
                    return affected_rows > 0
                return True
            else:
                # INSERTAR
                sql = """
                INSERT INTO producto_sap_cache (
                    sku,
                    item_code,
                    item_name,
                    pack_sap,
                    unidad_conversion,
                    pack_id,
                    grupo_articulos,
                    ultima_consulta,
                    activo,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """
                _ahora = ahora_naive()
                values = (
                    sku,
                    producto_data.get("item_code", sku),
                    producto_data.get("item_name"),
                    producto_data.get("pack_sap"),
                    producto_data.get("unidad_conversion"),
                    producto_data.get("pack_id"),
                    producto_data.get("grupo_articulos"),
                    _ahora,
                    _ahora,
                    _ahora,
                )
                
                cursor.execute(sql, values)
                self.conn.commit()
                logger.debug(f"✅ Producto SAP cache insertado: {sku}")
                affected_rows = cursor.rowcount
                if affected_rows in (-1, None):
                    return True
                if isinstance(affected_rows, int):
                    return affected_rows > 0
                return True
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar/actualizar producto_sap_cache: {e}")
            logger.error(f"   SKU: {producto_data.get('sku')}")
            raise
        finally:
            cursor.close()
    
    def get_unidad_conversion_by_pack(self, pack_sap: Optional[str]) -> Optional[float]:
        """
        Obtiene la unidad de conversión desde pack_conversion basado en el pack_sap.
        
        Args:
            pack_sap: Pack de SAP (X1, X2, X3, etc.) o None
            
        Returns:
            Unidad de conversión (float) o None si no se encuentra
        """
        if not pack_sap:
            return None
        
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT unidad_conversion
                FROM pack_conversion
                WHERE pack_id = ? AND activo = 1
                """,
                (pack_sap,)
            )
            result = cursor.fetchone()
            
            if result and result[0] is not None:
                return float(result[0])
            return None
        finally:
            cursor.close()

