"""
Validador especializado para cabecera de pedidos.

CHANGELOG:
- 2026-01-08: Extraído de pedido_validator.py como parte de la refactorización
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, date

from .pedido_validation_types import ValidationIssue, ValidationSeverity

logger = logging.getLogger(__name__)


class PedidoCabeceraValidator:
    """Validador para cabecera de pedidos."""

    def __init__(
        self,
        permitir_fechas_pasadas: bool = False
    ):
        """
        Args:
            permitir_fechas_pasadas: Si False, valida que fecha_entrega no sea pasada
        """
        self.permitir_fechas_pasadas = permitir_fechas_pasadas

    def validar(
        self,
        cabecera: Dict[str, Any],
        row_number: int = 1
    ) -> List[ValidationIssue]:
        """
        Valida la cabecera del pedido.

        Args:
            cabecera: Diccionario con datos de cabecera
            row_number: Número de fila (para reporte)

        Returns:
            Lista de issues de validación
        """
        issues = []

        # Validar numero_pedido (obligatorio)
        numero_pedido = cabecera.get("numero_pedido")
        if not numero_pedido or not str(numero_pedido).strip():
            issues.append(ValidationIssue(
                row_number=row_number,
                field="numero_pedido",
                severity=ValidationSeverity.ERROR,
                message="El número de pedido es obligatorio",
                value=numero_pedido
            ))

        # Validar fecha_pedido
        fecha_pedido = cabecera.get("fecha_pedido")
        if fecha_pedido:
            fecha_parsed = self._parsear_fecha(fecha_pedido)
            if fecha_parsed is None:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field="fecha_pedido",
                    severity=ValidationSeverity.ERROR,
                    message="Formato de fecha inválido. Use YYYY-MM-DD o DD/MM/YYYY",
                    value=cabecera.get("fecha_pedido")
                ))
            else:
                # Validar que fecha_pedido no sea muy antigua (ej: > 1 año)
                hoy = date.today()
                if fecha_parsed < date(hoy.year - 1, hoy.month, hoy.day):
                    issues.append(ValidationIssue(
                        row_number=row_number,
                        field="fecha_pedido",
                        severity=ValidationSeverity.WARNING,
                        message=f"La fecha de pedido es muy antigua: {fecha_parsed}",
                        value=fecha_parsed
                    ))

        # Validar fecha_entrega
        fecha_entrega = cabecera.get("fecha_entrega")
        if fecha_entrega and str(fecha_entrega).upper() != "INMEDIATO":
            fecha_entrega_dt = self._parsear_fecha(fecha_entrega)
            if fecha_entrega_dt is None:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field="fecha_entrega",
                    severity=ValidationSeverity.ERROR,
                    message="Formato de fecha de entrega inválido. Use YYYY-MM-DD, DD/MM/YYYY o 'INMEDIATO'",
                    value=fecha_entrega
                ))
            elif not self.permitir_fechas_pasadas:
                hoy = date.today()
                if fecha_entrega_dt < hoy:
                    issues.append(ValidationIssue(
                        row_number=row_number,
                        field="fecha_entrega",
                        severity=ValidationSeverity.ERROR,
                        message=f"La fecha de entrega no puede ser pasada: {fecha_entrega_dt}",
                        value=fecha_entrega_dt
                    ))

        return issues

    def _parsear_fecha(self, fecha_value: Any) -> date | None:
        """
        Parsea una fecha desde string o date.

        Args:
            fecha_value: Valor a parsear (str o date)

        Returns:
            Objeto date si es válido, None si no se pudo parsear
        """
        if isinstance(fecha_value, date):
            return fecha_value
        if isinstance(fecha_value, str):
            try:
                return datetime.strptime(fecha_value, "%Y-%m-%d").date()
            except ValueError:
                try:
                    return datetime.strptime(fecha_value, "%d/%m/%Y").date()
                except ValueError:
                    return None
        return None

