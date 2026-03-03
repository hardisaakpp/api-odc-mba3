"""
Utilidades compartidas para repositorios.

CHANGELOG:
- 2026-01-08: Centraliza funciones de serialización usadas por repositorios
"""

from .serialization import serialize_date, serialize_decimal, make_json_serializable

__all__ = ['serialize_date', 'serialize_decimal', 'make_json_serializable']
