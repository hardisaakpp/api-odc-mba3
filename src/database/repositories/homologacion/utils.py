"""
Utilidades para serialización de datos en repositorios de homologación.
"""

from datetime import datetime, date


def serialize_date(value):
    """Convierte date/datetime a string ISO."""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def serialize_decimal(value):
    """Convierte Decimal a float."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

