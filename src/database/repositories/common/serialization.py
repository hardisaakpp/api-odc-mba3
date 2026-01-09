"""
Utilidades de serialización compartidas para repositorios.
Extraídas de despacho_repository.py, remision_repository.py, etc.

CHANGELOG:
- 2026-01-08: Creado para centralizar utilidades de serialización
"""

from datetime import date, datetime
from typing import Any, Optional


def serialize_date(value: Any) -> Optional[str]:
    """
    Convierte un objeto date o datetime a string ISO format para JSON serialization.

    Args:
        value: Objeto date, datetime, o None

    Returns:
        String en formato ISO o None
    """
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def serialize_decimal(value: Any) -> Optional[float]:
    """
    Convierte un objeto Decimal de pyodbc a float para JSON serialization.

    Args:
        value: Objeto Decimal, float, int, o None

    Returns:
        float o None
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

