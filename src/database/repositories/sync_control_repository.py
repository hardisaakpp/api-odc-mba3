"""
Repositorio para operaciones de sync_control en SQL Server.
"""

import logging
import pyodbc
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class SyncControlRepository:
    """Repositorio para operaciones de sync_control."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def iniciar_sync(self, entidad: str, iniciado_por: str = "BACKEND") -> str:
        """
        Inicia un registro de sincronización.
        
        Args:
            entidad: 'MBA3' o 'SAP'
            iniciado_por: Usuario o sistema que inicia el sync
            
        Returns:
            sync_id del registro creado
        """
        cursor = self.conn.cursor()
        try:
            sync_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO sync_control (
                    sync_id,
                    entidad,
                    estado,
                    iniciado_por,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (sync_id, entidad, 'EN_PROGRESO', iniciado_por, datetime.now()))
            
            self.conn.commit()
            logger.debug(f"✅ Sync iniciado: {entidad} (sync_id: {sync_id})")
            return sync_id
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al iniciar sync {entidad}: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def finalizar_sync(
        self,
        sync_id: str,
        estado: str,
        registros_sincronizados: int = 0,
        registros_nuevos: int = 0,
        registros_actualizados: int = 0,
        mensaje_error: Optional[str] = None,
        duracion_segundos: Optional[int] = None
    ) -> bool:
        """
        Finaliza un registro de sincronización.
        
        Args:
            sync_id: ID del sync a finalizar
            estado: 'EXITOSA' o 'ERROR'
            registros_sincronizados: Total de registros procesados
            registros_nuevos: Registros nuevos insertados
            registros_actualizados: Registros actualizados
            mensaje_error: Mensaje de error si estado es 'ERROR'
            duracion_segundos: Duración en segundos del sync
            
        Returns:
            True si se actualizó correctamente
        """
        cursor = self.conn.cursor()
        try:
            ultima_sync_exitosa = datetime.now() if estado == 'EXITOSA' else None
            
            cursor.execute("""
                UPDATE sync_control
                SET 
                    estado = ?,
                    ultima_sync_exitosa = ?,
                    registros_sincronizados = ?,
                    registros_nuevos = ?,
                    registros_actualizados = ?,
                    mensaje_error = ?,
                    duracion_segundos = ?
                WHERE sync_id = ?
            """, (
                estado,
                ultima_sync_exitosa,
                registros_sincronizados,
                registros_nuevos,
                registros_actualizados,
                mensaje_error,
                duracion_segundos,
                sync_id
            ))
            
            self.conn.commit()
            logger.debug(f"✅ Sync finalizado: {sync_id} - {estado}")
            return True
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al finalizar sync {sync_id}: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_ultima_sync_exitosa(self, entidad: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene la última sincronización exitosa de una entidad.
        
        Args:
            entidad: 'MBA3' o 'SAP'
            
        Returns:
            Diccionario con datos del sync, o None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT TOP 1
                    sync_id,
                    entidad,
                    estado,
                    ultima_sync_exitosa,
                    registros_sincronizados,
                    registros_nuevos,
                    registros_actualizados,
                    duracion_segundos,
                    iniciado_por,
                    created_at
                FROM sync_control
                WHERE entidad = ? AND estado = 'EXITOSA'
                ORDER BY ultima_sync_exitosa DESC
            """, (entidad,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                "sync_id": str(row[0]),
                "entidad": row[1],
                "estado": row[2],
                "ultima_sync_exitosa": row[3].isoformat() if row[3] else None,
                "registros_sincronizados": row[4],
                "registros_nuevos": row[5],
                "registros_actualizados": row[6],
                "duracion_segundos": row[7],
                "iniciado_por": row[8],
                "created_at": row[9].isoformat() if row[9] else None
            }
        except Exception as e:
            logger.error(f"❌ Error al obtener última sync {entidad}: {e}", exc_info=True)
            raise
        finally:
            cursor.close()



