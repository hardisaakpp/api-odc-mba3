"""
Destinatarios de notificaciones por email: exclusivamente desde
notificacion_persona_correo (personas vinculadas a un correo específico del
catálogo notificacion_tipo_correo).

Estrategia actual:
  - Se lee siempre desde notificacion_persona_correo, filtrando por el correo
    exacto (tipo_notificacion + tipo_correo) del catálogo. Si nadie está
    vinculado a ese correo, o hay un error de conexión/consulta, no hay
    destinatarios: el correo correspondiente no se envía (se registra
    warning/error en el log, pero no se usa ningún valor de .env como respaldo).
  - Excepción: EMAIL_DEV_OVERRIDE en desarrollo sigue redirigiendo todos los
    correos a esa(s) dirección(es), ignorando BD; es un override explícito para
    pruebas locales, no un fallback.
  - La antigua tabla notificacion_destinatarios (por tipo_notificacion, sin
    distinguir el correo específico) fue eliminada (ver
    scripts/migrations/drop_notificacion_destinatarios.sql); sus destinatarios
    activos se migraron antes a notificacion_persona_correo (ver
    scripts/migrations/seed_notificacion_persona_correo_desde_destinatarios.sql).
"""

import logging
from typing import List

from src.config import ENVIRONMENT, EMAIL_DEV_OVERRIDE
from src.database.connection import get_db_connection_context
from src.database.repositories.notificacion_persona_correo_repository import (
    get_destinatarios_por_correo as _get_destinatarios_por_correo_bd,
)

logger = logging.getLogger(__name__)


def get_destinatarios_por_correo(tipo_notificacion: str, tipo_correo: str) -> List[str]:
    """
    Devuelve la lista de emails vinculados a un correo específico del catálogo
    (notificacion_tipo_correo), vía notificacion_persona_correo.

    Args:
        tipo_notificacion: OPERACIONES | MABEL_TRADING | HOMOLOGACIONES | TECNICOS | PRODUCCION_ELRAYO.
        tipo_correo: Asunto exacto del correo tal como está en el catálogo
            (notificacion_tipo_correo.tipo_correo).

    Returns:
        Lista de correos (nunca None; [] si nadie está vinculado a ese correo).
    """
    tipo = (tipo_notificacion or "").strip().upper()
    asunto = (tipo_correo or "").strip()
    if not tipo or not asunto:
        return []

    # En desarrollo, si EMAIL_DEV_OVERRIDE está configurado, TODOS los correos
    # de notificaciones se redirigen a esa(s) dirección(es), ignorando BD.
    if ENVIRONMENT == "development" and EMAIL_DEV_OVERRIDE:
        logger.info(
            "📧 EMAIL_DEV_OVERRIDE activo en desarrollo: redirigiendo '%s / %s' a %s",
            tipo,
            asunto,
            EMAIL_DEV_OVERRIDE,
        )
        return list(EMAIL_DEV_OVERRIDE)

    try:
        with get_db_connection_context() as conn:
            destinatarios = _get_destinatarios_por_correo_bd(conn, tipo, asunto)
    except Exception as e:
        logger.warning(
            "No se pudieron obtener destinatarios desde BD para '%s / %s': %s",
            tipo,
            asunto,
            e,
        )
        return []

    if not destinatarios:
        logger.warning("No hay personas vinculadas en BD al correo '%s / %s'.", tipo, asunto)
    return destinatarios
