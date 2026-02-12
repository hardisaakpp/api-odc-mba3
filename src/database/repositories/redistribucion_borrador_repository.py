"""
Repositorio para operaciones de borrador de redistribución.

CHANGELOG:
- 2026-02-12: Agregado soporte para audit_context en upsert_borrador
- 2026-02-09: Agregado para mover SQL fuera de endpoints (FASE 4)
"""

import logging
from typing import Optional, Dict, Any, TYPE_CHECKING

import pyodbc

from src.utils.timezone import ahora_naive

if TYPE_CHECKING:
    from src.utils.audit_context import AuditContext

from src.database.services.audit_log_service import AuditLogService

logger = logging.getLogger(__name__)


class RedistribucionBorradorRepository:
    """Repositorio para operaciones de borrador de redistribución."""

    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.

        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn

    def upsert_borrador(
        self,
        pedido_id: str,
        numero_pedido: str,
        ajustes_detalle_json: str,
        user_id: str,
        audit_context: Optional["AuditContext"] = None,
    ) -> None:
        """
        Inserta o actualiza el borrador de redistribución para un pedido.

        Args:
            pedido_id: UUID del pedido
            numero_pedido: Número del pedido
            ajustes_detalle_json: JSON serializado con ajustes
            user_id: Usuario creador/modificador
            audit_context: Contexto de auditoría (Buenas Prácticas - Sección 3)
        """
        from src.utils.audit_context import ensure_audit_context
        audit = ensure_audit_context(audit_context)

        cursor = None
        try:
            cursor = self.conn.cursor()

            # Verificar si la tabla tiene columnas de auditoría extendidas
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = 'redistribucion_borrador' AND COLUMN_NAME = 'modificado_por'
            """)
            tiene_audit_cols = (cursor.fetchone()[0] or 0) > 0

            _ahora = ahora_naive()

            if tiene_audit_cols:
                cursor.execute("""
                    IF EXISTS (SELECT 1 FROM redistribucion_borrador WHERE pedido_id = ?)
                        UPDATE redistribucion_borrador
                        SET ajustes_detalle = ?,
                            fecha_guardado = ?,
                            modificado_por = ?,
                            modificado_fecha = ?,
                            origen = ?,
                            ip_origen = ?
                        WHERE pedido_id = ?
                    ELSE
                        INSERT INTO redistribucion_borrador (pedido_id, numero_pedido, ajustes_detalle, creado_por, fecha_guardado, origen, ip_origen)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    pedido_id,
                    ajustes_detalle_json, _ahora,
                    audit.get_modificado_por(), _ahora,
                    audit.origen, audit.ip_origen,
                    pedido_id,
                    pedido_id, numero_pedido, ajustes_detalle_json,
                    audit.get_creado_por(), _ahora,
                    audit.origen, audit.ip_origen,
                ))
            else:
                cursor.execute("""
                    IF EXISTS (SELECT 1 FROM redistribucion_borrador WHERE pedido_id = ?)
                        UPDATE redistribucion_borrador
                        SET ajustes_detalle = ?,
                            fecha_guardado = ?,
                            creado_por = ?
                        WHERE pedido_id = ?
                    ELSE
                        INSERT INTO redistribucion_borrador (pedido_id, numero_pedido, ajustes_detalle, creado_por)
                        VALUES (?, ?, ?, ?)
                """, (pedido_id, ajustes_detalle_json, _ahora, user_id, pedido_id, pedido_id, numero_pedido, ajustes_detalle_json, user_id))

            # Registrar en audit log
            audit_svc = AuditLogService(self.conn)
            audit_svc.registrar(
                pedido_id=pedido_id,
                entidad="redistribucion_borrador",
                entidad_id=pedido_id,
                accion="UPDATE",
                audit_context=audit,
                comentario=f"Borrador guardado para pedido {numero_pedido}",
                cursor=cursor,
            )

            self.conn.commit()
            logger.info(f"✅ Borrador guardado para pedido {numero_pedido} por usuario {audit.get_modificado_por()}")
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            logger.error(f"❌ Error al guardar borrador para pedido {numero_pedido}: {e}", exc_info=True)
            raise
        finally:
            if cursor:
                cursor.close()

    def get_borrador(self, pedido_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el borrador de redistribución de un pedido.

        Args:
            pedido_id: UUID del pedido

        Returns:
            Diccionario con ajustes_detalle y fecha_guardado, o None si no existe
        """
        cursor = None
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT ajustes_detalle, fecha_guardado
                FROM redistribucion_borrador
                WHERE pedido_id = ?
            """, (pedido_id,))

            row = cursor.fetchone()
            if not row:
                return None

            return {
                "ajustes_detalle": row[0],
                "fecha_guardado": row[1]
            }
        except Exception as e:
            logger.error(f"❌ Error al obtener borrador para pedido {pedido_id}: {e}", exc_info=True)
            raise
        finally:
            if cursor:
                cursor.close()
