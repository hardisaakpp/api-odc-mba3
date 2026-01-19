"""
Repositorio para operaciones CRUD de bodega_sap_cache en SQL Server.
"""

import logging
import pyodbc
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class BodegaSAPRepository:
    """Repositorio para operaciones de bodega_sap_cache."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def find_by_whs_code(self, whs_code: str) -> Optional[Dict[str, Any]]:
        """
        Busca una bodega/tienda en el cache por código.
        
        Args:
            whs_code: Código de bodega/tienda (WhsCode) a buscar
            
        Returns:
            Diccionario con datos de la bodega/tienda cacheada, o None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT 
                    cache_id,
                    whs_code,
                    whs_name,
                    es_bodega,
                    ultima_consulta,
                    activo,
                    created_at,
                    updated_at
                FROM bodega_sap_cache
                WHERE whs_code = ? AND activo = 1
                """,
                (whs_code.strip().upper(),)
            )
            result = cursor.fetchone()
            
            if result:
                return {
                    "cache_id": str(result[0]),
                    "whs_code": result[1],
                    "whs_name": result[2],
                    "es_bodega": bool(result[3]) if result[3] is not None else None,
                    "ultima_consulta": result[4],
                    "activo": bool(result[5]),
                    "created_at": result[6],
                    "updated_at": result[7],
                }
            return None
        finally:
            cursor.close()
    
    def find_all_valid(self, cache_days: int = 30) -> List[Dict[str, Any]]:
        """
        Busca todas las bodegas/tiendas válidas en el cache (no expiradas).
        
        Args:
            cache_days: Días de validez del cache (por defecto 30)
            
        Returns:
            Lista de diccionarios con datos de bodegas/tiendas cacheadas
        """
        cursor = self.conn.cursor()
        try:
            fecha_limite = datetime.now() - timedelta(days=cache_days)
            
            cursor.execute(
                """
                SELECT 
                    cache_id,
                    whs_code,
                    whs_name,
                    es_bodega,
                    ultima_consulta,
                    activo,
                    created_at,
                    updated_at
                FROM bodega_sap_cache
                WHERE activo = 1 
                  AND ultima_consulta >= ?
                ORDER BY whs_code
                """,
                (fecha_limite,)
            )
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "cache_id": str(row[0]),
                    "whs_code": row[1],
                    "whs_name": row[2],
                    "es_bodega": bool(row[3]) if row[3] is not None else None,
                    "ultima_consulta": row[4],
                    "activo": bool(row[5]),
                    "created_at": row[6],
                    "updated_at": row[7],
                })
            return results
        finally:
            cursor.close()
    
    def is_cache_valid(self, whs_code: str, cache_days: int = 30) -> bool:
        """
        Verifica si el cache de una bodega/tienda es válido (no ha expirado).
        
        Args:
            whs_code: Código de bodega/tienda
            cache_days: Días de validez del cache (por defecto 30)
            
        Returns:
            True si el cache existe y es válido, False en caso contrario
        """
        bodega = self.find_by_whs_code(whs_code)
        if not bodega:
            return False
        
        ultima_consulta = bodega.get("ultima_consulta")
        if not ultima_consulta:
            return False
        
        # Verificar si la última consulta es más antigua que cache_days
        if isinstance(ultima_consulta, str):
            ultima_consulta = datetime.fromisoformat(ultima_consulta.replace('Z', '+00:00'))
        elif isinstance(ultima_consulta, datetime):
            pass
        else:
            return False
        
        fecha_limite = datetime.now() - timedelta(days=cache_days)
        return ultima_consulta >= fecha_limite
    
    def insert_or_update(self, bodega_data: Dict[str, Any]) -> bool:
        """
        Inserta o actualiza una bodega/tienda en el cache (UPSERT).
        
        Args:
            bodega_data: Diccionario con datos de la bodega/tienda:
                - whs_code: Código de bodega/tienda (requerido)
                - whs_name: Nombre de bodega/tienda en SAP
                - es_bodega: Si es bodega central (True) o tienda (False)
                - activo: Si está activo (por defecto True)
                
        Returns:
            True si se insertó/actualizó correctamente
        """
        cursor = self.conn.cursor()
        
        try:
            whs_code = bodega_data.get("whs_code")
            if not whs_code:
                raise ValueError("whs_code es requerido")
            
            whs_code_normalized = whs_code.strip().upper()
            
            # Verificar si ya existe
            existing = self.find_by_whs_code(whs_code_normalized)
            
            if existing:
                # ACTUALIZAR
                sql = """
                UPDATE bodega_sap_cache SET
                    whs_name = ?,
                    es_bodega = ?,
                    ultima_consulta = GETDATE(),
                    updated_at = GETDATE()
                WHERE whs_code = ? AND activo = 1
                """
                
                values = (
                    bodega_data.get("whs_name"),
                    bodega_data.get("es_bodega"),
                    whs_code_normalized,
                )
                
                cursor.execute(sql, values)
                self.conn.commit()
                logger.debug(f"✅ Bodega/Tienda SAP cache actualizada: {whs_code_normalized}")
                return True
            else:
                # INSERTAR
                sql = """
                INSERT INTO bodega_sap_cache (
                    whs_code,
                    whs_name,
                    es_bodega,
                    ultima_consulta,
                    activo,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, GETDATE(), ?, GETDATE(), GETDATE())
                """
                
                activo = bodega_data.get("activo", True)
                if not isinstance(activo, bool):
                    activo = True
                
                values = (
                    whs_code_normalized,
                    bodega_data.get("whs_name"),
                    bodega_data.get("es_bodega"),
                    1 if activo else 0,
                )
                
                cursor.execute(sql, values)
                self.conn.commit()
                logger.debug(f"✅ Bodega/Tienda SAP cache insertada: {whs_code_normalized}")
                return True
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar/actualizar bodega_sap_cache: {e}")
            logger.error(f"   WhsCode: {bodega_data.get('whs_code')}")
            raise
        finally:
            cursor.close()
    
    def insert_or_update_batch(self, bodegas_data: List[Dict[str, Any]]) -> int:
        """
        Inserta o actualiza múltiples bodegas/tiendas en el cache (UPSERT batch).
        
        Args:
            bodegas_data: Lista de diccionarios con datos de bodegas/tiendas
            
        Returns:
            Número de registros insertados/actualizados
        """
        if not bodegas_data:
            return 0
        
        cursor = self.conn.cursor()
        updated_count = 0
        
        try:
            for bodega_data in bodegas_data:
                try:
                    if self.insert_or_update(bodega_data):
                        updated_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ Error al procesar bodega {bodega_data.get('whs_code')}: {e}")
                    continue
            
            logger.info(f"✅ {updated_count}/{len(bodegas_data)} bodegas/tiendas procesadas en batch")
            return updated_count
            
        except Exception as e:
            logger.error(f"❌ Error al procesar batch de bodegas: {e}")
            raise
        finally:
            cursor.close()
