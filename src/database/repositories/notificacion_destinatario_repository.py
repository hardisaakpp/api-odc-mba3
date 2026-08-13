"""
Repositorio para destinatarios de notificaciones por email.

Lee desde la tabla notificacion_destinatarios (configuración por tipo).
No depende de usuarios_ad; es configuración organizacional propia.
"""

import logging
from typing import List

import pyodbc

logger = logging.getLogger(__name__)

# Códigos de tipo de notificación (deben coincidir con los usados en la app)
TIPOS_NOTIFICACION = ("OPERACIONES", "MABEL_TRADING", "HOMOLOGACIONES", "TECNICOS", "PRODUCCION_ELRAYO")


def get_destinatarios_activos(
    conn: pyodbc.Connection, tipo_notificacion: str, codigo_evento: str | None = None
) -> List[str]:
    """
    Obtiene la lista de emails activos para un tipo de notificación.

    Un email puede quedar excluido de un evento puntual (ej. sólo el correo de
    "Redistribución Confirmada") sin sacarlo del resto de notificaciones de su
    tipo: para eso se inserta una fila con el mismo tipo_notificacion, el email,
    codigo_evento = <código del evento> y activo = 0. Esa fila no agrega
    destinatarios, sólo excluye al email de ese codigo_evento específico.

    Args:
        conn: Conexión a SQL Server (base principal).
        tipo_notificacion: Uno de OPERACIONES, MABEL_TRADING, HOMOLOGACIONES, TECNICOS.
        codigo_evento: Código del evento puntual (ej. "REDISTRIBUCION_CONFIRMADA")
            para aplicar exclusiones específicas. Si es None, no se filtra nada
            adicional (comportamiento igual al histórico).

    Returns:
        Lista de direcciones de correo (puede ser vacía si no hay filas).
    """
    cursor = conn.cursor()
    try:
        tipo = tipo_notificacion.strip().upper()
        cursor.execute(
            """
            SELECT email
            FROM notificacion_destinatarios
            WHERE tipo_notificacion = ? AND codigo_evento IS NULL AND activo = 1
              AND email NOT IN (
                  SELECT email
                  FROM notificacion_destinatarios
                  WHERE tipo_notificacion = ? AND codigo_evento = ? AND activo = 0
              )
            ORDER BY id
            """,
            (tipo, tipo, codigo_evento),
        )
        rows = cursor.fetchall()
        return [str(row[0]).strip() for row in rows if row[0]]
    except Exception as e:
        logger.warning(
            "No se pudo leer destinatarios desde BD para tipo '%s': %s",
            tipo_notificacion,
            e,
            exc_info=False,
        )
        return []
    finally:
        cursor.close()


def listar_destinatarios(conn: pyodbc.Connection) -> List[dict]:
    """
    Lista TODAS las filas existentes en notificacion_destinatarios (base y
    exclusiones puntuales por evento), para la interfaz de administración.

    Las filas base tienen codigo_evento NULL. Las filas de exclusión (ej. la
    de nvelasquez@elrayo.com.ec para REDISTRIBUCION_CONFIRMADA) tienen
    codigo_evento con el código del evento excluido; se muestran para que el
    admin pueda ver/activar/desactivar/eliminar exclusiones ya existentes sin
    tener que ejecutar un script SQL manual. Crear nuevas exclusiones sigue
    siendo manual (esta interfaz no expone un selector de codigo_evento).

    Returns:
        Lista de dicts con id, tipo_notificacion, email, activo, codigo_evento,
        creado_fecha, creado_por, modificado_fecha, modificado_por.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, tipo_notificacion, email, activo, codigo_evento, creado_fecha,
                   creado_por, modificado_fecha, modificado_por
            FROM notificacion_destinatarios
            ORDER BY tipo_notificacion, id
            """
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def crear_destinatario(
    conn: pyodbc.Connection, tipo_notificacion: str, email: str, creado_por: str
) -> int:
    """
    Crea un destinatario base (codigo_evento NULL, activo=1) para un tipo de
    notificación.

    Raises:
        ValueError: si ya existe una fila base con el mismo tipo_notificacion
            y email (evita duplicados silenciosos).

    Returns:
        id de la fila creada.
    """
    tipo = tipo_notificacion.strip().upper()
    correo = email.strip()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT 1 FROM notificacion_destinatarios
            WHERE tipo_notificacion = ? AND codigo_evento IS NULL AND email = ?
            """,
            (tipo, correo),
        )
        if cursor.fetchone():
            raise ValueError(f"El correo '{correo}' ya está registrado para el tipo '{tipo}'.")

        cursor.execute(
            """
            INSERT INTO notificacion_destinatarios (tipo_notificacion, email, activo, creado_por)
            OUTPUT INSERTED.id
            VALUES (?, ?, 1, ?)
            """,
            (tipo, correo, creado_por),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("INSERT no devolvió el id generado")
        return int(row[0])
    finally:
        cursor.close()


def actualizar_activo_destinatario(
    conn: pyodbc.Connection, destinatario_id: int, activo: bool, modificado_por: str
) -> bool:
    """
    Activa o desactiva cualquier fila existente (base o exclusión por evento).

    En una fila de exclusión, activo=0 es el estado que hace efecto (excluye
    al email de ese codigo_evento); ponerla en activo=1 equivale a levantar
    la exclusión sin borrar el registro.

    Returns:
        True si se actualizó una fila, False si no existía.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE notificacion_destinatarios
            SET activo = ?, modificado_fecha = GETDATE(), modificado_por = ?
            WHERE id = ?
            """,
            (1 if activo else 0, modificado_por, destinatario_id),
        )
        return cursor.rowcount > 0
    finally:
        cursor.close()


def eliminar_destinatario(conn: pyodbc.Connection, destinatario_id: int) -> bool:
    """
    Elimina definitivamente cualquier fila existente (base o exclusión por evento).

    Returns:
        True si se eliminó una fila, False si no existía.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM notificacion_destinatarios WHERE id = ?",
            (destinatario_id,),
        )
        return cursor.rowcount > 0
    finally:
        cursor.close()
