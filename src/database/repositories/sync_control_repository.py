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
    
    def get_estado_sincronizacion(self, entidad: str) -> Dict[str, Any]:
        """
        Obtiene el estado actual de sincronización de una entidad.
        
        Lógica:
        1. Primero verifica si hay una sync EN_PROGRESO (prioridad)
        2. Si no, obtiene la última sync (EXITOSA o ERROR)
        3. Normaliza estados para frontend
        
        ⚠️ IMPORTANTE: Si hay una sync EN_PROGRESO con created_at > 2 horas,
           se considera inconsistente (proceso colgado).
        
        ⚠️ NOTA TIMEZONE: Usa datetime.now() sin timezone para consistencia
           con GETDATE() de SQL Server (hora local del servidor).
        
        Args:
            entidad: 'MBA3' o 'SAP'
            
        Returns:
            Diccionario con estado normalizado:
            {
                "ultima_sync": str (ISO) o None,
                "estado": "exitoso" | "error" | "en_proceso" | None,
                "mensaje": str
            }
        """
        cursor = self.conn.cursor()
        try:
            # 1. Verificar si hay una sincronización EN_PROGRESO
            cursor.execute("""
                SELECT TOP 1
                    estado,
                    created_at,
                    mensaje_error
                FROM sync_control
                WHERE entidad = ? AND estado = 'EN_PROGRESO'
                ORDER BY created_at DESC
            """, (entidad,))
            
            row_progreso = cursor.fetchone()
            if row_progreso:
                created_at = row_progreso[1]
                
                # ⚠️ Validación: Si la sync lleva > 2 horas, considerar inconsistente
                if created_at:
                    # datetime.now() sin timezone para consistencia con GETDATE() de SQL Server
                    tiempo_transcurrido = (datetime.now() - created_at).total_seconds()
                    horas_transcurridas = tiempo_transcurrido / 3600
                    
                    if horas_transcurridas > 2:
                        # Proceso probablemente colgado
                        return {
                            "ultima_sync": None,
                            "estado": "error",
                            "mensaje": f"Sincronización iniciada hace {int(horas_transcurridas)} horas. Posible proceso colgado."
                        }
                
                # Sync en progreso válida
                fecha_str = created_at.isoformat() if created_at else "desconocido"
                return {
                    "ultima_sync": None,
                    "estado": "en_proceso",
                    "mensaje": f"Sincronización en progreso desde {fecha_str}"
                }
            
            # 2. Si no hay EN_PROGRESO, obtener la última sync (EXITOSA o ERROR)
            # ⚠️ ORDER BY created_at DESC es correcto porque cada sync inserta una fila nueva
            cursor.execute("""
                SELECT TOP 1
                    estado,
                    ultima_sync_exitosa,
                    mensaje_error,
                    registros_sincronizados
                FROM sync_control
                WHERE entidad = ?
                ORDER BY created_at DESC
            """, (entidad,))
            
            row = cursor.fetchone()
            if not row:
                # No hay registros de sincronización
                return {
                    "ultima_sync": None,
                    "estado": None,
                    "mensaje": "No hay sincronizaciones registradas"
                }
            
            estado = row[0]
            ultima_sync = row[1]  # ⚠️ Este es el campo correcto (no created_at)
            mensaje_error = row[2]
            registros = row[3]
            
            # 3. Normalizar estado para frontend
            # ⚠️ CONTRATO DE API: Estos valores son estables, no cambiar sin coordinación con frontend
            estado_normalizado = None
            mensaje = None
            
            if estado == 'EXITOSA':
                estado_normalizado = "exitoso"
                registros_str = f"{registros or 0} registros procesados" if registros else ""
                mensaje = f"Sincronización completada exitosamente. {registros_str}".strip()
            elif estado == 'ERROR':
                estado_normalizado = "error"
                mensaje = mensaje_error or "Error en la última sincronización"
            # EN_PROGRESO ya se manejó arriba, pero por si acaso:
            elif estado == 'EN_PROGRESO':
                estado_normalizado = "en_proceso"
                mensaje = "Sincronización en progreso"
            else:
                # Estado desconocido
                estado_normalizado = None
                mensaje = f"Estado desconocido: {estado}"
            
            return {
                "ultima_sync": ultima_sync.isoformat() if ultima_sync else None,
                "estado": estado_normalizado,
                "mensaje": mensaje
            }
        except Exception as e:
            logger.error(f"❌ Error al obtener estado sync {entidad}: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
