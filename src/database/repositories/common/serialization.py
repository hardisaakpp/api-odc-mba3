"""
Utilidades de serialización compartidas para repositorios.
Extraídas de despacho_repository.py, remision_repository.py, etc.

CHANGELOG:
- 2026-01-08: Creado para centralizar utilidades de serialización
- 2026-03-02: Añadido make_json_serializable para Decimal en respuestas API
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional


def make_json_serializable(obj: Any) -> Any:
    """
    Recorre dict/list y convierte Decimal (y opcionalmente date/datetime) a tipos serializables en JSON.
    Útil para respuestas API que incluyen datos de BD con columnas DECIMAL.
    """
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_json_serializable(item) for item in obj]
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


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

