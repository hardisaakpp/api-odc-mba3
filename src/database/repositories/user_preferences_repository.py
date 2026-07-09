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
                try:
                    visible_columns = json.loads(row[0]) if row[0] else []
                    column_order = json.loads(row[1]) if row[1] else []
                    filters = json.loads(row[2]) if row[2] else {}
                    page_size = row[3]
                    
                    return {
                        "visibleColumns": visible_columns,
                        "columnOrder": column_order,
                        "filters": filters,
                        "pageSize": page_size
                    }
                except json.JSONDecodeError as json_err:
                    logger.error(f"Error al parsear JSON de preferencias: {json_err}")
                    logger.error(f"   VisibleColumns raw: {row[0]}")
                    logger.error(f"   ColumnOrder raw: {row[1]}")
                    logger.error(f"   Filters raw: {row[2]}")
                    raise ValueError(f"Error al parsear JSON de preferencias: {json_err}")
            
            return None
            
        except Exception as e:
            logger.error(f"Error al obtener preferencias para usuario {user_id}, tabla {table_id}: {e}")
            logger.exception(e)  # Log completo del stack trace
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
            
            # Validar y convertir a JSON con logging detallado
            visible_columns = preferences.get("visibleColumns", [])
            column_order = preferences.get("columnOrder", [])
            filters = preferences.get("filters", {})
            page_size = preferences.get("pageSize")
            
            logger.debug(f"Guardando preferencias - visibleColumns: {visible_columns}, columnOrder: {column_order}")
            
            try:
                visible_columns_json = json.dumps(visible_columns)
                column_order_json = json.dumps(column_order)
                filters_json = json.dumps(filters) if filters else None
            except (TypeError, ValueError) as json_err:
                logger.error(f"Error al serializar JSON de preferencias: {json_err}")
                logger.error(f"   visibleColumns type: {type(visible_columns)}, value: {visible_columns}")
                logger.error(f"   columnOrder type: {type(column_order)}, value: {column_order}")
                logger.error(f"   filters type: {type(filters)}, value: {filters}")
                raise ValueError(f"Error al serializar JSON de preferencias: {json_err}")
            
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
            logger.info(f"✅ Preferencias guardadas exitosamente para usuario {user_id}, tabla {table_id}")
            
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            logger.error(f"❌ Error al guardar preferencias para usuario {user_id}, tabla {table_id}: {e}")
            logger.exception(e)  # Log completo del stack trace
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
                try:
                    result[table_id] = {
                        "visibleColumns": json.loads(row[1]) if row[1] else [],
                        "columnOrder": json.loads(row[2]) if row[2] else [],
                        "filters": json.loads(row[3]) if row[3] else {},
                        "pageSize": row[4]
                    }
                except json.JSONDecodeError as json_err:
                    logger.error(f"Error al parsear JSON de preferencias para tabla {table_id}: {json_err}")
                    logger.error(f"   VisibleColumns raw: {row[1]}")
                    logger.error(f"   ColumnOrder raw: {row[2]}")
                    logger.error(f"   Filters raw: {row[3]}")
                    # Continuar con otras tablas en lugar de fallar completamente
                    continue
            
            return result
            
        except Exception as e:
            logger.error(f"Error al obtener todas las preferencias para usuario {user_id}: {e}")
            logger.exception(e)  # Log completo del stack trace
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
    
    def get_sidebar_preferences(self, user_id: str) -> Optional[Dict]:
        """
        Obtiene las preferencias del sidebar para un usuario.
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Diccionario con preferencias del sidebar o None si no existen
        """
        cursor = None
        try:
            cursor = self.conn.cursor()
            
            # Usamos TableId = 'sidebar' y almacenamos las preferencias en Filters como JSON
            cursor.execute("""
                SELECT Filters
                FROM UserPreferences
                WHERE UserId = ? AND TableId = 'sidebar'
            """, (user_id,))
            
            row = cursor.fetchone()
            
            if row and row[0]:
                # Las preferencias del sidebar se almacenan en Filters como JSON
                sidebar_prefs = json.loads(row[0])
                return sidebar_prefs
            
            return None
            
        except Exception as e:
            logger.error(f"Error al obtener preferencias del sidebar: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
    
    def save_sidebar_preferences(self, user_id: str, preferences: Dict) -> None:
        """
        Guarda o actualiza las preferencias del sidebar.
        
        Args:
            user_id: ID del usuario
            preferences: Diccionario con preferencias del sidebar (debe contener 'collapsed')
        """
        cursor = None
        try:
            cursor = self.conn.cursor()
            
            # Almacenamos las preferencias del sidebar en Filters como JSON
            # Usamos TableId = 'sidebar' y dejamos los otros campos con valores por defecto
            sidebar_prefs_json = json.dumps(preferences)
            
            # Verificar si ya existe
            cursor.execute("""
                SELECT Id FROM UserPreferences
                WHERE UserId = ? AND TableId = 'sidebar'
            """, (user_id,))
            
            existing = cursor.fetchone()
            
            if existing:
                # Actualizar
                cursor.execute("""
                    UPDATE UserPreferences
                    SET Filters = ?,
                        UpdatedAt = GETUTCDATE()
                    WHERE UserId = ? AND TableId = 'sidebar'
                """, (sidebar_prefs_json, user_id))
            else:
                # Insertar - usamos valores por defecto para los campos de tabla
                cursor.execute("""
                    INSERT INTO UserPreferences 
                    (UserId, TableId, VisibleColumns, ColumnOrder, Filters, PageSize, CreatedAt, UpdatedAt)
                    VALUES (?, 'sidebar', '[]', '[]', ?, NULL, GETUTCDATE(), GETUTCDATE())
                """, (user_id, sidebar_prefs_json))
            
            self.conn.commit()
            logger.info(f"Preferencias del sidebar guardadas para usuario {user_id}")
            
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            logger.error(f"Error al guardar preferencias del sidebar: {e}")
            raise
        finally:
            if cursor:
                cursor.close()

