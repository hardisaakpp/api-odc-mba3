"""
Repositorio para operaciones CRUD de preferencias de usuario en SQL Server.
"""

import logging
import json
import pyodbc
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class UserPreferencesRepository:
    """Repositorio para operaciones de preferencias de usuario."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def get_table_preferences(
        self, 
        user_id: str, 
        table_id: str
    ) -> Optional[Dict]:
        """
        Obtiene las preferencias de una tabla específica para un usuario.
        
        Args:
            user_id: ID del usuario
            table_id: ID de la tabla
            
        Returns:
            Diccionario con preferencias o None si no existen
        """
        cursor = None
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                SELECT VisibleColumns, ColumnOrder, Filters, PageSize
                FROM UserPreferences
                WHERE UserId = ? AND TableId = ?
            """, (user_id, table_id))
            
            row = cursor.fetchone()
            
            if row:
                return {
                    "visibleColumns": json.loads(row[0]) if row[0] else [],
                    "columnOrder": json.loads(row[1]) if row[1] else [],
                    "filters": json.loads(row[2]) if row[2] else {},
                    "pageSize": row[3]
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error al obtener preferencias: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
    
    def save_table_preferences(
        self,
        user_id: str,
        table_id: str,
        preferences: Dict
    ) -> None:
        """
        Guarda o actualiza las preferencias de una tabla.
        
        Args:
            user_id: ID del usuario
            table_id: ID de la tabla
            preferences: Diccionario con preferencias
        """
        cursor = None
        try:
            cursor = self.conn.cursor()
            
            visible_columns_json = json.dumps(preferences.get("visibleColumns", []))
            column_order_json = json.dumps(preferences.get("columnOrder", []))
            filters_json = json.dumps(preferences.get("filters", {})) if preferences.get("filters") else None
            page_size = preferences.get("pageSize")
            
            # Verificar si ya existe
            cursor.execute("""
                SELECT Id FROM UserPreferences
                WHERE UserId = ? AND TableId = ?
            """, (user_id, table_id))
            
            existing = cursor.fetchone()
            
            if existing:
                # Actualizar
                cursor.execute("""
                    UPDATE UserPreferences
                    SET VisibleColumns = ?,
                        ColumnOrder = ?,
                        Filters = ?,
                        PageSize = ?,
                        UpdatedAt = GETUTCDATE()
                    WHERE UserId = ? AND TableId = ?
                """, (
                    visible_columns_json,
                    column_order_json,
                    filters_json,
                    page_size,
                    user_id,
                    table_id
                ))
            else:
                # Insertar
                cursor.execute("""
                    INSERT INTO UserPreferences 
                    (UserId, TableId, VisibleColumns, ColumnOrder, Filters, PageSize, CreatedAt, UpdatedAt)
                    VALUES (?, ?, ?, ?, ?, ?, GETUTCDATE(), GETUTCDATE())
                """, (
                    user_id,
                    table_id,
                    visible_columns_json,
                    column_order_json,
                    filters_json,
                    page_size
                ))
            
            self.conn.commit()
            logger.info(f"Preferencias guardadas para usuario {user_id}, tabla {table_id}")
            
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            logger.error(f"Error al guardar preferencias: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
    
    def get_all_preferences(self, user_id: str) -> Dict[str, Dict]:
        """
        Obtiene todas las preferencias de un usuario.
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Diccionario con todas las preferencias indexadas por table_id
        """
        cursor = None
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                SELECT TableId, VisibleColumns, ColumnOrder, Filters, PageSize
                FROM UserPreferences
                WHERE UserId = ?
            """, (user_id,))
            
            result = {}
            for row in cursor.fetchall():
                table_id = row[0]
                result[table_id] = {
                    "visibleColumns": json.loads(row[1]) if row[1] else [],
                    "columnOrder": json.loads(row[2]) if row[2] else [],
                    "filters": json.loads(row[3]) if row[3] else {},
                    "pageSize": row[4]
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error al obtener todas las preferencias: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
    
    def delete_table_preferences(self, user_id: str, table_id: str) -> bool:
        """
        Elimina las preferencias de una tabla.
        
        Args:
            user_id: ID del usuario
            table_id: ID de la tabla
            
        Returns:
            True si se eliminó, False si no existía
        """
        cursor = None
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                DELETE FROM UserPreferences
                WHERE UserId = ? AND TableId = ?
            """, (user_id, table_id))
            
            deleted_count = cursor.rowcount
            self.conn.commit()
            
            if deleted_count > 0:
                logger.info(f"Preferencias eliminadas para usuario {user_id}, tabla {table_id}")
                return True
            else:
                logger.info(f"No se encontraron preferencias para usuario {user_id}, tabla {table_id}")
                return False
            
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            logger.error(f"Error al eliminar preferencias: {e}")
            raise
        finally:
            if cursor:
                cursor.close()

