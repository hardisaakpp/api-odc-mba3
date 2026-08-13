"""
Repositorio para notificacion_persona_correo: organización persona-céntrica
de qué correos (notificacion_tipo_correo) debería recibir cada persona.

Fuente real de los destinatarios del envío de correos (vía
src.utils.notificacion_destinatarios.get_destinatarios_por_correo, usado por
email_notifier.py). notificacion_destinatarios (por tipo_notificacion, sin
distinguir el correo específico) queda como tabla histórica: ya no determina
el envío real.
"""

from typing import List

import pyodbc


def get_destinatarios_por_correo(conn: pyodbc.Connection, tipo_notificacion: str, tipo_correo: str) -> List[str]:
    """
    Emails de personas vinculadas a un correo activo específico del catálogo,
    identificado por tipo_notificacion + tipo_correo exactos.

    Returns:
        Lista de correos (puede ser vacía si nadie está vinculado a ese correo).
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT DISTINCT pc.email
            FROM notificacion_persona_correo pc
            INNER JOIN notificacion_tipo_correo tc ON tc.id = pc.tipo_correo_id
            WHERE tc.tipo_notificacion = ? AND tc.tipo_correo = ? AND tc.activo = 1
            ORDER BY pc.email
            """,
            (tipo_notificacion.strip().upper(), tipo_correo.strip()),
        )
        return [str(row[0]).strip() for row in cursor.fetchall() if row[0]]
    finally:
        cursor.close()


def listar_personas_correo(conn: pyodbc.Connection) -> List[dict]:
    """
    Lista todas las filas (persona x correo), unidas con el catálogo para
    traer también el asunto, la descripción y el tipo_notificacion de cada correo.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT pc.id, pc.nombre, pc.email, pc.creado_fecha, pc.creado_por,
                   tc.id AS tipo_correo_id, tc.tipo_correo, tc.tipo_notificacion, tc.descripcion
            FROM notificacion_persona_correo pc
            INNER JOIN notificacion_tipo_correo tc ON tc.id = pc.tipo_correo_id
            ORDER BY pc.email, tc.tipo_notificacion, tc.id
            """
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def crear_link_persona_correo(
    conn: pyodbc.Connection, nombre: str, email: str, tipo_correo_id: int, creado_por: str
) -> int:
    """
    Vincula una persona (nombre + email) a un correo del catálogo.

    Raises:
        ValueError: si esa persona ya está vinculada a ese correo.

    Returns:
        id de la fila creada.
    """
    correo = email.strip()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT 1 FROM notificacion_persona_correo WHERE email = ? AND tipo_correo_id = ?",
            (correo, tipo_correo_id),
        )
        if cursor.fetchone():
            raise ValueError(f"'{correo}' ya está vinculado a ese correo.")

        cursor.execute(
            """
            INSERT INTO notificacion_persona_correo (nombre, email, tipo_correo_id, creado_por)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?)
            """,
            (nombre.strip(), correo, tipo_correo_id, creado_por),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("INSERT no devolvió el id generado")
        return int(row[0])
    finally:
        cursor.close()


def eliminar_link_persona_correo(conn: pyodbc.Connection, link_id: int) -> bool:
    """Desvincula un correo específico de una persona. Returns True si existía."""
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM notificacion_persona_correo WHERE id = ?", (link_id,))
        return cursor.rowcount > 0
    finally:
        cursor.close()


def eliminar_persona(conn: pyodbc.Connection, email: str) -> bool:
    """Elimina a una persona por completo (todos sus correos vinculados). Returns True si existía."""
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM notificacion_persona_correo WHERE email = ?", (email.strip(),))
        return cursor.rowcount > 0
    finally:
        cursor.close()
