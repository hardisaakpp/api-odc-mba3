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
TIPOS_NOTIFICACION = ("OPERACIONES", "MABEL_TRADING", "HOMOLOGACIONES", "TECNICOS")


def get_destinatarios_activos(conn: pyodbc.Connection, tipo_notificacion: str) -> List[str]:
    """
    Obtiene la lista de emails activos para un tipo de notificación.

    Args:
        conn: Conexión a SQL Server (base principal).
        tipo_notificacion: Uno de OPERACIONES, MABEL_TRADING, HOMOLOGACIONES, TECNICOS.

    Returns:
        Lista de direcciones de correo (puede ser vacía si no hay filas).
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT email
            FROM notificacion_destinatarios
            WHERE tipo_notificacion = ? AND activo = 1
            ORDER BY id
            """,
            (tipo_notificacion.strip().upper(),),
        )
        rows = cursor.fetchall()
        return [str(row[0]).strip() for row in rows if row[0]]
    except Exception as e:
        logger.warning(
            "No se pudo leer destinatarios desde BD (usando fallback .env): %s",
            e,
            exc_info=False,
        )
        return []
    finally:
        cursor.close()
