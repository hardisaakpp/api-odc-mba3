#!/usr/bin/env python3
"""Aplica el patch para EMAIL_DEV_OVERRIDE en config y notificacion_destinatarios."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "src", "config.py")
NOTIF_PATH = os.path.join(ROOT, "src", "utils", "notificacion_destinatarios.py")


def patch_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    if "EMAIL_DEV_OVERRIDE" in content:
        print("config.py: EMAIL_DEV_OVERRIDE ya existe")
        return
    # Insert after EMAIL_MABEL_TRADING = [...]
    marker = "EMAIL_MABEL_TRADING = [email.strip() for email in _email_mabel_trading.split(\",\") if email.strip()]"
    insert = """

# Override en desarrollo: todos los correos van a este destinatario (ignora BD).
# Solo aplica cuando ENVIRONMENT=development. En producción no se usa.
_email_dev_override_str = os.getenv("EMAIL_DEV_OVERRIDE", "")
EMAIL_DEV_OVERRIDE = [e.strip() for e in _email_dev_override_str.split(",") if e.strip()]
"""
    if marker not in content:
        print("config.py: marker not found")
        return
    content = content.replace(
        marker + "\n\n\n# Configuraci",
        marker + insert + "\n# Configuraci",
    )
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print("config.py: patch aplicado")


def patch_notificacion():
    with open(NOTIF_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    if "EMAIL_DEV_OVERRIDE" in content and "ENVIRONMENT == \"development\"" in content:
        print("notificacion_destinatarios.py: override ya existe")
        return
    # 1) Update docstring and imports
    old_import = """from src.config import (
    EMAIL_MABEL_TRADING,
    EMAIL_TO_HOMOLOGACIONES,
    EMAIL_TO_OPERACIONES,
    EMAIL_TO_TECNICOS,
)"""
    new_import = """from src.config import (
    EMAIL_DEV_OVERRIDE,
    EMAIL_MABEL_TRADING,
    EMAIL_TO_HOMOLOGACIONES,
    EMAIL_TO_OPERACIONES,
    EMAIL_TO_TECNICOS,
    ENVIRONMENT,
)"""
    content = content.replace(old_import, new_import)
    # 2) Update strategy docstring
    content = content.replace(
        "Estrategia:\n  1. Intentar leer desde tabla",
        "Estrategia:\n  - Si ENVIRONMENT=development y EMAIL_DEV_OVERRIDE está configurado → devolver solo ese(s) correo(s).\n  - Si no: intentar leer desde tabla",
    )
    content = content.replace(
        "Así se puede migrar de .env a BD sin redeploy y sin romper producción.",
        "Así en desarrollo solo el dev recibe todos los correos; en producción se usa la BD.",
    )
    # 3) In get_destinatarios_por_tipo, after "if not tipo: return []" add override
    content = content.replace(
        "    tipo = (tipo_notificacion or \"\").strip().upper()\n    if not tipo:\n        return []\n\n    fallback_list = _FALLBACK.get(tipo)",
        "    tipo = (tipo_notificacion or \"\").strip().upper()\n    if not tipo:\n        return []\n\n    # Desarrollo: todos los correos al destinatario override (ignora BD)\n    if ENVIRONMENT == \"development\" and EMAIL_DEV_OVERRIDE:\n        logger.debug(\"Destinatarios (%s): usando EMAIL_DEV_OVERRIDE en desarrollo\", tipo)\n        return list(EMAIL_DEV_OVERRIDE)\n\n    fallback_list = _FALLBACK.get(tipo)",
    )
    # 4) Update docstring of get_destinatarios_por_tipo
    content = content.replace(
        "    \"\"\"\n    Devuelve la lista de emails destinatarios para un tipo de notificación.\n\n    Primero consulta la tabla notificacion_destinatarios.",
        "    \"\"\"\n    Devuelve la lista de emails destinatarios para un tipo de notificación.\n\n    En desarrollo (ENVIRONMENT=development), si EMAIL_DEV_OVERRIDE está configurado,\n    se devuelve solo esa lista para todos los tipos. En producción se consulta la tabla notificacion_destinatarios.",
    )
    content = content.replace(
        "    Si la tabla no existe, está vacía\n    o hay error, devuelve la lista configurada en .env (EMAIL_TO_OPERACIONES, etc.).",
        "    Si no hay datos, se usa el fallback .env por tipo.",
    )
    with open(NOTIF_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print("notificacion_destinatarios.py: patch aplicado")


if __name__ == "__main__":
    patch_config()
    patch_notificacion()
