"""
Servicio centralizado de auditoría para operaciones sobre pedidos.

Registra todas las operaciones (INSERT, UPDATE, DELETE) en la tabla
pedido_audit_log, proporcionando un log unificado y consultable de
todos los cambios realizados sobre pedidos y entidades relacionadas.

Uso:
    from src.database.services.audit_log_service import AuditLogService

    audit_svc = AuditLogService(conn)
    audit_svc.registrar(
        pedido_id=pedido_id,
        entidad="pedido",
        entidad_id=pedido_id,
        accion="UPDATE",
        audit_context=audit,
        campo="estado_id",
        valor_anterior="3",
        valor_nuevo="4",
    )
"""

import json
import logging
from typing import Optional, Dict, Any, List, TYPE_CHECKING

import pyodbc

if TYPE_CHECKING:
    from src.utils.audit_context import AuditContext

logger = logging.getLogger(__name__)

# Cache a nivel de clase para existencia de la tabla
_tabla_existe: Optional[bool] = None


class AuditLogService:
    """Servicio para registrar operaciones en pedido_audit_log."""

    def __init__(self, conn: pyodbc.Connection):
        self.conn = conn

    # ------------------------------------------------------------------
    # Verificación de tabla (cacheada)
    # ------------------------------------------------------------------
    def _tabla_audit_log_existe(self, cursor: pyodbc.Cursor) -> bool:
        """Verifica si existe la tabla pedido_audit_log (cacheado)."""
        global _tabla_existe
        if _tabla_existe is None:
            cursor.execute(
                "SELECT OBJECT_ID(N'[dbo].[pedido_audit_log]', N'U')"
            )
            row = cursor.fetchone()
            _tabla_existe = row is not None and row[0] is not None
        return _tabla_existe

    # ------------------------------------------------------------------
    # Registro individual
    # ------------------------------------------------------------------
    def registrar(
        self,
        pedido_id: str,
        entidad: str,
        entidad_id: Optional[str],
        accion: str,
        audit_context: Optional["AuditContext"],
        campo: Optional[str] = None,
        valor_anterior: Optional[str] = None,
        valor_nuevo: Optional[str] = None,
        comentario: Optional[str] = None,
        cursor: Optional[pyodbc.Cursor] = None,
    ) -> None:
        """
        Inserta un registro en pedido_audit_log.

        Args:
            pedido_id: UUID del pedido
            entidad: Nombre de la tabla/entidad afectada
            entidad_id: PK del registro afectado
            accion: 'INSERT', 'UPDATE' o 'DELETE'
            audit_context: Contexto de auditoría (usuario, origen, IP)
            campo: Columna modificada (solo para UPDATE)
            valor_anterior: Valor previo (string)
            valor_nuevo: Nuevo valor (string)
            comentario: Observación opcional
            cursor: Cursor externo (para usar dentro de transacción)
        """
        own_cursor = cursor is None
        cur = cursor or self.conn.cursor()

        try:
            if not self._tabla_audit_log_existe(cur):
                return

            usuario = "SYSTEM"
            origen = None
            ip_origen = None
            if audit_context:
                usuario = audit_context.get_modificado_por()
                origen = audit_context.origen
                ip_origen = audit_context.ip_origen

            cur.execute("""
                INSERT INTO pedido_audit_log (
                    pedido_id, entidad, entidad_id, accion,
                    campo_modificado, valor_anterior, valor_nuevo,
                    usuario, origen, ip_origen, comentario
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pedido_id,
                entidad,
                str(entidad_id) if entidad_id else None,
                accion,
                campo,
                _truncar(valor_anterior),
                _truncar(valor_nuevo),
                usuario,
                origen,
                ip_origen,
                comentario,
            ))

            if own_cursor:
                self.conn.commit()

        except Exception as e:
            # No fallar la operación principal por un error de auditoría
            logger.warning(
                f"⚠️ No se pudo registrar audit_log para {entidad}/{entidad_id}: {e}"
            )
        finally:
            if own_cursor and cur:
                cur.close()

    # ------------------------------------------------------------------
    # Helpers de alto nivel
    # ------------------------------------------------------------------
    def registrar_insert(
        self,
        pedido_id: str,
        entidad: str,
        entidad_id: str,
        audit_context: Optional["AuditContext"],
        datos: Optional[Dict[str, Any]] = None,
        cursor: Optional[pyodbc.Cursor] = None,
    ) -> None:
        """Registra un INSERT con los datos insertados como JSON."""
        datos_json = json.dumps(datos, default=str) if datos else None
        self.registrar(
            pedido_id=pedido_id,
            entidad=entidad,
            entidad_id=entidad_id,
            accion="INSERT",
            audit_context=audit_context,
            valor_nuevo=datos_json,
            cursor=cursor,
        )

    def registrar_delete(
        self,
        pedido_id: str,
        entidad: str,
        entidad_id: str,
        audit_context: Optional["AuditContext"],
        datos_eliminados: Optional[Dict[str, Any]] = None,
        comentario: Optional[str] = None,
        cursor: Optional[pyodbc.Cursor] = None,
    ) -> None:
        """Registra un DELETE con snapshot de lo que se eliminó."""
        snapshot_json = json.dumps(datos_eliminados, default=str) if datos_eliminados else None
        self.registrar(
            pedido_id=pedido_id,
            entidad=entidad,
            entidad_id=entidad_id,
            accion="DELETE",
            audit_context=audit_context,
            valor_anterior=snapshot_json,
            comentario=comentario,
            cursor=cursor,
        )

    def registrar_cambios(
        self,
        pedido_id: str,
        entidad: str,
        entidad_id: str,
        audit_context: Optional["AuditContext"],
        cambios: Dict[str, Dict[str, Any]],
        cursor: Optional[pyodbc.Cursor] = None,
    ) -> None:
        """
        Registra múltiples cambios de campo en un UPDATE.

        Args:
            cambios: Dict con formato {campo: {"anterior": val, "nuevo": val}}
        """
        for campo, vals in cambios.items():
            anterior = vals.get("anterior")
            nuevo = vals.get("nuevo")
            # Solo registrar si hay cambio real
            if str(anterior) != str(nuevo):
                self.registrar(
                    pedido_id=pedido_id,
                    entidad=entidad,
                    entidad_id=entidad_id,
                    accion="UPDATE",
                    audit_context=audit_context,
                    campo=campo,
                    valor_anterior=str(anterior) if anterior is not None else None,
                    valor_nuevo=str(nuevo) if nuevo is not None else None,
                    cursor=cursor,
                )

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------
    def obtener_por_pedido(
        self,
        pedido_id: str,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Devuelve el historial de pedido_audit_log de un pedido, más reciente
        primero.

        Args:
            pedido_id: UUID del pedido
            limit: Tope de filas a devolver

        Returns:
            Lista de dicts con entidad, entidad_id, accion, campo_modificado,
            valor_anterior, valor_nuevo, usuario, fecha (ISO 8601), origen,
            ip_origen, comentario. Lista vacía si la tabla no existe todavía.
        """
        cursor = self.conn.cursor()
        try:
            if not self._tabla_audit_log_existe(cursor):
                return []

            cursor.execute("""
                SELECT TOP (?)
                    entidad, entidad_id, accion, campo_modificado,
                    valor_anterior, valor_nuevo, usuario, fecha, origen,
                    ip_origen, comentario
                FROM pedido_audit_log
                WHERE pedido_id = ?
                ORDER BY fecha DESC
            """, (limit, pedido_id))

            registros = []
            for row in cursor.fetchall():
                fecha = row[7]
                registros.append({
                    "entidad": row[0],
                    "entidad_id": row[1],
                    "accion": row[2],
                    "campo_modificado": row[3],
                    "valor_anterior": row[4],
                    "valor_nuevo": row[5],
                    "usuario": row[6],
                    "fecha": fecha.isoformat() if fecha else None,
                    "origen": row[8],
                    "ip_origen": row[9],
                    "comentario": row[10],
                })
            return registros
        finally:
            cursor.close()

    def registrar_delete_masivo(
        self,
        pedido_id: str,
        entidad: str,
        audit_context: Optional["AuditContext"],
        registros: List[Dict[str, Any]],
        id_field: str = "id",
        cursor: Optional[pyodbc.Cursor] = None,
    ) -> None:
        """
        Registra múltiples DELETEs (ej: eliminar todas las distribuciones).

        Args:
            registros: Lista de dicts con los datos de cada registro eliminado
            id_field: Nombre del campo que contiene el ID de cada registro
        """
        for reg in registros:
            entidad_id = str(reg.get(id_field, ""))
            self.registrar_delete(
                pedido_id=pedido_id,
                entidad=entidad,
                entidad_id=entidad_id,
                audit_context=audit_context,
                datos_eliminados=reg,
                cursor=cursor,
            )


def _truncar(valor: Optional[str], max_len: int = 4000) -> Optional[str]:
    """Trunca un valor para evitar exceder límites de columna."""
    if valor is None:
        return None
    if len(valor) > max_len:
        return valor[:max_len] + "...[truncado]"
    return valor
