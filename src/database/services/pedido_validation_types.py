"""
Tipos comunes para validación de pedidos.
Extraído de pedido_validator.py para reutilización.

CHANGELOG:
- 2026-01-08: Creado como parte de la refactorización de pedido_validator.py
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ValidationSeverity(Enum):
    """Severidad de la validación."""
    ERROR = "ERROR"      # Crítico - bloquea el proceso
    WARNING = "WARNING"  # Advertencia - no bloquea


@dataclass
class ValidationIssue:
    """Representa un problema de validación."""
    row_number: int  # Número de fila en el Excel (1-based)
    field: str       # Campo con el problema
    severity: ValidationSeverity
    message: str
    value: Any = None  # Valor que causó el problema

