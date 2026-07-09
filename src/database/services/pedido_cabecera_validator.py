"""
Validador especializado para cabecera de pedidos.

CHANGELOG:
- 2026-01-08: Extraído de pedido_validator.py como parte de la refactorización
"""

import logging
from typing import Any, Dict, List
from datetime import date, datetime

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

        # Validar numero_pedido (obligatorio y máx. 100 caracteres)
        numero_pedido = cabecera.get("numero_pedido")
        if not numero_pedido or not str(numero_pedido).strip():
            issues.append(ValidationIssue(
                row_number=row_number,
                field="numero_pedido",
                severity=ValidationSeverity.ERROR,
                message="El número de pedido es obligatorio",
                value=numero_pedido
            ))
        elif len(str(numero_pedido).strip()) > 100:
            issues.append(ValidationIssue(
                row_number=row_number,
                field="numero_pedido",
                severity=ValidationSeverity.ERROR,
                message="El número de pedido no puede superar 100 caracteres",
                value=numero_pedido
            ))

        # Validar mensaje (máx. 100 caracteres)
        mensaje = cabecera.get("mensaje")
        if mensaje is not None and str(mensaje).strip() and len(str(mensaje).strip()) > 100:
            issues.append(ValidationIssue(
                row_number=row_number,
                field="mensaje",
                severity=ValidationSeverity.ERROR,
                message="El mensaje no puede superar 100 caracteres",
                value=mensaje
            ))

        # Validar fecha_pedido
        fecha_pedido = cabecera.get("fecha_pedido")
        if fecha_pedido:
            issues.extend(self._validar_fecha_pedido(fecha_pedido, row_number))

        # Validar fecha_entrega
        fecha_entrega = cabecera.get("fecha_entrega")
        if fecha_entrega and str(fecha_entrega).upper() != "INMEDIATO":
            issues.extend(self._validar_fecha_entrega(fecha_entrega, row_number))

        return issues

    def _validar_fecha_pedido(self, fecha_pedido: Any, row_number: int) -> List[ValidationIssue]:
        result = []
        fecha_parsed = self._parsear_fecha(fecha_pedido)
        if fecha_parsed is None:
            result.append(ValidationIssue(
                row_number=row_number,
                field="fecha_pedido",
                severity=ValidationSeverity.ERROR,
                message="Formato de fecha inválido. Use YYYY-MM-DD o DD/MM/YYYY",
                value=fecha_pedido
            ))
        else:
            hoy = date.today()
            if fecha_parsed < date(hoy.year - 1, hoy.month, hoy.day):
                result.append(ValidationIssue(
                    row_number=row_number,
                    field="fecha_pedido",
                    severity=ValidationSeverity.WARNING,
                    message=f"La fecha de pedido es muy antigua: {fecha_parsed}",
                    value=fecha_parsed
                ))
        return result

    def _validar_fecha_entrega(self, fecha_entrega: Any, row_number: int) -> List[ValidationIssue]:
        result = []
        fecha_entrega_dt = self._parsear_fecha(fecha_entrega)
        if fecha_entrega_dt is None:
            result.append(ValidationIssue(
                row_number=row_number,
                field="fecha_entrega",
                severity=ValidationSeverity.ERROR,
                message="Formato de fecha de entrega inválido. Use YYYY-MM-DD, DD/MM/YYYY o 'INMEDIATO'",
                value=fecha_entrega
            ))
        elif not self.permitir_fechas_pasadas:
            hoy = date.today()
            if fecha_entrega_dt < hoy:
                result.append(ValidationIssue(
                    row_number=row_number,
                    field="fecha_entrega",
                    severity=ValidationSeverity.ERROR,
                    message=f"La fecha de entrega no puede ser pasada: {fecha_entrega_dt}",
                    value=fecha_entrega_dt
                ))
        return result

    def _parsear_fecha(self, fecha_value: Any) -> date | None:
        """
        Parsea una fecha desde string o date.

        Acepta: YYYY-MM-DD, DD/MM/YYYY, YYYY-MM-DD HH:MM:SS (datetime)
        y objetos date/datetime.

        Args:
            fecha_value: Valor a parsear (str, date o datetime)

        Returns:
            Objeto date si es válido, None si no se pudo parsear
        """
        if isinstance(fecha_value, datetime):
            return fecha_value.date()
        if isinstance(fecha_value, date):
            return fecha_value
        if isinstance(fecha_value, str):
            s = fecha_value.strip()
            if not s:
                return None
            # Intentar formatos en orden: solo fecha, luego datetime
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                try:
                    return datetime.strptime(s, fmt).date()
                except ValueError:
                    continue
            # Si la cadena es larga (ej. "2026-02-25 00:00:00"), usar solo los primeros 10 para %Y-%m-%d
            if len(s) >= 10:
                try:
                    return datetime.strptime(s[:10], "%Y-%m-%d").date()
                except ValueError:
                    pass
        return None

