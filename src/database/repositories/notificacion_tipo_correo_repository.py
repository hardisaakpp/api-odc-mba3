"""
Repositorio para el catálogo de correos (notificacion_tipo_correo).

Documenta qué correo (asunto) envía el sistema y a qué tipo_notificacion
pertenece. No determina el envío real (eso sigue en email_notifier.py); es
la referencia administrable que reemplaza el array hardcodeado del frontend.

tipo_notificacion aquí no es una FK a una tabla de tipos: el conjunto de
tipos válidos para la interfaz de administración se deriva de los valores
distintos presentes en esta misma tabla (ver listar_tipos_notificacion).
"""

import logging
from typing import List

import pyodbc

logger = logging.getLogger(__name__)


def listar_tipos_correo(conn: pyodbc.Connection) -> List[dict]:
    """Lista todas las filas del catálogo (activas e inactivas)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, tipo_notificacion, tipo_correo, descripcion, orden_flujo, activo,
                   creado_fecha, creado_por, modificado_fecha, modificado_por
            FROM notificacion_tipo_correo
            ORDER BY CASE WHEN orden_flujo IS NULL THEN 1 ELSE 0 END, orden_flujo, tipo_notificacion, id
            """
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def obtener_tipo_correo(conn: pyodbc.Connection, tipo_correo_id: int) -> dict | None:
    """Obtiene una fila del catálogo por id, o None si no existe."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, tipo_notificacion, tipo_correo, descripcion, orden_flujo, activo,
                   creado_fecha, creado_por, modificado_fecha, modificado_por
            FROM notificacion_tipo_correo
            WHERE id = ?
            """,
            (tipo_correo_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))
    finally:
        cursor.close()


def listar_tipos_notificacion(conn: pyodbc.Connection) -> List[str]:
    """
    Tipos de notificación distintos y activos presentes en el catálogo.

    Fuente dinámica para los selectores de tipo_notificacion en la interfaz
    de administración (destinatarios y catálogo de correos), en vez de un
    tuple hardcodeado en Python.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT DISTINCT tipo_notificacion
            FROM notificacion_tipo_correo
            WHERE activo = 1
            ORDER BY tipo_notificacion
            """
        )
        return [str(row[0]) for row in cursor.fetchall()]
    finally:
        cursor.close()


def crear_tipo_correo(
    conn: pyodbc.Connection, tipo_notificacion: str, tipo_correo: str, descripcion: str | None, creado_por: str
) -> int:
    """
    Agrega una fila al catálogo.

    Raises:
        ValueError: si ya existe una fila con el mismo tipo_notificacion y
            tipo_correo (evita duplicados silenciosos).

    Returns:
        id de la fila creada.
    """
    tipo = tipo_notificacion.strip().upper()
    asunto = tipo_correo.strip()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT 1 FROM notificacion_tipo_correo
            WHERE tipo_notificacion = ? AND tipo_correo = ?
            """,
            (tipo, asunto),
        )
        if cursor.fetchone():
            raise ValueError(f"Ya existe '{asunto}' para el tipo '{tipo}'.")

        cursor.execute(
            """
            INSERT INTO notificacion_tipo_correo (tipo_notificacion, tipo_correo, descripcion, creado_por)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?)
            """,
            (tipo, asunto, (descripcion or "").strip() or None, creado_por),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("INSERT no devolvió el id generado")
        return int(row[0])
    finally:
        cursor.close()


def actualizar_activo_tipo_correo(
    conn: pyodbc.Connection, tipo_correo_id: int, activo: bool, modificado_por: str
) -> bool:
    """Activa o desactiva una fila del catálogo. Returns True si existía."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE notificacion_tipo_correo
            SET activo = ?, modificado_fecha = GETDATE(), modificado_por = ?
            WHERE id = ?
            """,
            (1 if activo else 0, modificado_por, tipo_correo_id),
        )
        return cursor.rowcount > 0
    finally:
        cursor.close()


def eliminar_tipo_correo(conn: pyodbc.Connection, tipo_correo_id: int) -> bool:
    """Elimina definitivamente una fila del catálogo. Returns True si existía."""
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM notificacion_tipo_correo WHERE id = ?", (tipo_correo_id,))
        return cursor.rowcount > 0
    finally:
        cursor.close()
