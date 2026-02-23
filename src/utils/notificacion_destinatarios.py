"""
Destinatarios de notificaciones por email: BD con fallback a .env.

Estrategia:
  1. Intentar leer desde tabla notificacion_destinatarios (por tipo).
  2. Si no hay filas o hay error de BD → usar listas de config (.env).

Así se puede migrar de .env a BD sin redeploy y sin romper producción.
"""

import logging
from typing import List

from src.config import (
    EMAIL_MABEL_TRADING,
    EMAIL_TO_HOMOLOGACIONES,
    EMAIL_TO_OPERACIONES,
    EMAIL_TO_TECNICOS,
)
from src.database.connection import get_db_connection_context
from src.database.repositories.notificacion_destinatario_repository import (
    get_destinatarios_activos,
)

logger = logging.getLogger(__name__)

# Mapeo tipo_notificacion -> lista de fallback desde config
_FALLBACK: dict[str, List[str]] = {
    "OPERACIONES": lambda: EMAIL_TO_OPERACIONES if isinstance(EMAIL_TO_OPERACIONES, list) else [EMAIL_TO_OPERACIONES] if EMAIL_TO_OPERACIONES else [],
    "MABEL_TRADING": lambda: EMAIL_MABEL_TRADING if isinstance(EMAIL_MABEL_TRADING, list) else [EMAIL_MABEL_TRADING] if EMAIL_MABEL_TRADING else [],
    "HOMOLOGACIONES": lambda: EMAIL_TO_HOMOLOGACIONES if isinstance(EMAIL_TO_HOMOLOGACIONES, list) else [EMAIL_TO_HOMOLOGACIONES] if EMAIL_TO_HOMOLOGACIONES else [],
    "TECNICOS": lambda: EMAIL_TO_TECNICOS if isinstance(EMAIL_TO_TECNICOS, list) else [EMAIL_TO_TECNICOS] if EMAIL_TO_TECNICOS else [],
}


def get_destinatarios_por_tipo(tipo_notificacion: str) -> List[str]:
    """
    Devuelve la lista de emails destinatarios para un tipo de notificación.

    Primero consulta la tabla notificacion_destinatarios. Si hay al menos un
    destinatario activo, devuelve esa lista. Si la tabla no existe, está vacía
    o hay error, devuelve la lista configurada en .env (EMAIL_TO_OPERACIONES, etc.).

    Args:
        tipo_notificacion: OPERACIONES | MABEL_TRADING | HOMOLOGACIONES | TECNICOS.

    Returns:
        Lista de correos (nunca None; puede ser [] si tampoco hay fallback).
    """
    tipo = (tipo_notificacion or "").strip().upper()
    if not tipo:
        return []

    fallback_list = _FALLBACK.get(tipo)
    if fallback_list is None:
        logger.debug("Tipo de notificación desconocido '%s', sin fallback", tipo_notificacion)
        return []

    try:
        with get_db_connection_context() as conn:
            destinatarios = get_destinatarios_activos(conn, tipo)
    except Exception as e:
        logger.debug("Fallback .env para destinatarios (%s): %s", tipo, e)
        return list(fallback_list())

    if not destinatarios:
        return list(fallback_list())
    return destinatarios
