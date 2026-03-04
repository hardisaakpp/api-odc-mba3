"""
Destinatarios de notificaciones por email: BD con fallback a .env.

Estrategia actual:
  - Siempre se intenta leer desde la tabla notificacion_destinatarios (por tipo).
  - Si la tabla no existe, hay error o no hay filas:
      * En producción se usa el fallback configurado en .env por tipo.
      * En desarrollo:
          - Para OPERACIONES (EL RAYO) y MABEL_TRADING **no** se usa fallback .env,
            solo se leen destinatarios desde BD.
          - Para otros tipos se mantiene el fallback .env.
"""

import logging
from typing import Callable, List

from src.config import (
    EMAIL_MABEL_TRADING,
    EMAIL_TO_HOMOLOGACIONES,
    EMAIL_TO_OPERACIONES,
    EMAIL_TO_TECNICOS,
    ENVIRONMENT,
    EMAIL_DEV_OVERRIDE,
)
from src.database.connection import get_db_connection_context
from src.database.repositories.notificacion_destinatario_repository import (
    get_destinatarios_activos,
)

logger = logging.getLogger(__name__)

# Mapeo tipo_notificacion -> callable que devuelve lista de fallback desde config
_FALLBACK: dict[str, Callable[[], List[str]]] = {
    "OPERACIONES": lambda: EMAIL_TO_OPERACIONES if isinstance(EMAIL_TO_OPERACIONES, list) else [EMAIL_TO_OPERACIONES] if EMAIL_TO_OPERACIONES else [],
    "MABEL_TRADING": lambda: EMAIL_MABEL_TRADING if isinstance(EMAIL_MABEL_TRADING, list) else [EMAIL_MABEL_TRADING] if EMAIL_MABEL_TRADING else [],
    "HOMOLOGACIONES": lambda: EMAIL_TO_HOMOLOGACIONES if isinstance(EMAIL_TO_HOMOLOGACIONES, list) else [EMAIL_TO_HOMOLOGACIONES] if EMAIL_TO_HOMOLOGACIONES else [],
    "TECNICOS": lambda: EMAIL_TO_TECNICOS if isinstance(EMAIL_TO_TECNICOS, list) else [EMAIL_TO_TECNICOS] if EMAIL_TO_TECNICOS else [],
}


def get_destinatarios_por_tipo(tipo_notificacion: str) -> List[str]:
    """
    Devuelve la lista de emails destinatarios para un tipo de notificación.

    En producción se consulta la tabla notificacion_destinatarios; si no hay datos
    o hay error, se usa el fallback .env por tipo.

    En desarrollo (ENVIRONMENT=development):
      - Para tipos OPERACIONES (EL RAYO) y MABEL_TRADING ya **no** se usan los
        correos configurados en .env; solo se leen desde BD.
      - Para otros tipos (HOMOLOGACIONES, TECNICOS) se mantiene el fallback .env.

    Args:
        tipo_notificacion: OPERACIONES | MABEL_TRADING | HOMOLOGACIONES | TECNICOS.

    Returns:
        Lista de correos (nunca None; puede ser [] si tampoco hay fallback).
    """
    tipo = (tipo_notificacion or "").strip().upper()
    if not tipo:
        return []

    # En desarrollo, si EMAIL_DEV_OVERRIDE está configurado, TODOS los correos
    # de notificaciones se redirigen a esa(s) dirección(es), ignorando BD y .env.
    if ENVIRONMENT == "development" and EMAIL_DEV_OVERRIDE:
        logger.info(
            "📧 EMAIL_DEV_OVERRIDE activo en desarrollo: redirigiendo tipo '%s' a %s",
            tipo,
            EMAIL_DEV_OVERRIDE,
        )
        return list(EMAIL_DEV_OVERRIDE)

    # En desarrollo, para OPERACIONES (EL RAYO) y MABEL_TRADING dejamos de usar
    # correos de .env y obligamos a que vengan desde BD.
    skip_env_fallback = ENVIRONMENT == "development" and tipo in {"OPERACIONES", "MABEL_TRADING"}

    fallback_list = _FALLBACK.get(tipo)
    if fallback_list is None:
        logger.debug("Tipo de notificación desconocido '%s', sin fallback", tipo_notificacion)
        return []

    try:
        with get_db_connection_context() as conn:
            destinatarios = get_destinatarios_activos(conn, tipo)
    except Exception as e:
        if skip_env_fallback:
            logger.warning(
                "No se pudieron obtener destinatarios desde BD para tipo '%s' en desarrollo "
                "y el fallback .env está deshabilitado: %s",
                tipo,
                e,
            )
            return []
        logger.debug("Fallback .env para destinatarios (%s): %s", tipo, e)
        return list(fallback_list())

    if not destinatarios:
        if skip_env_fallback:
            logger.warning(
                "No hay destinatarios configurados en BD para tipo '%s' en desarrollo "
                "y el fallback .env está deshabilitado.",
                tipo,
            )
            return []
        return list(fallback_list())
    return destinatarios
