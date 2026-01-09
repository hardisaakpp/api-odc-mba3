"""
Validador especializado para precios e impuestos.

CHANGELOG:
- 2026-01-08: Extraído de pedido_validator.py como parte de la refactorización
"""

import logging
import pandas as pd
from typing import Dict, Any, List, Optional

from .pedido_validation_types import ValidationIssue, ValidationSeverity

logger = logging.getLogger(__name__)


class PedidoPrecioValidator:
    """Validador para precios e impuestos."""

    def __init__(
        self,
        iva_porcentaje: float = 15.0,
        usar_comas_decimales: bool = False
    ):
        """
        Args:
            iva_porcentaje: Porcentaje de IVA para validaciones (default: 15.0 para Ecuador)
            usar_comas_decimales: Si True, acepta comas como separador decimal (formato europeo)
        """
        self.iva_porcentaje = iva_porcentaje
        self.usar_comas_decimales = usar_comas_decimales

    def validar(
        self,
        detalle: Dict[str, Any],
        row_number: int
    ) -> List[ValidationIssue]:
        """
        Valida reglas regionales de precio e impuestos.

        Valida:
        - Formato numérico (puntos vs comas como separador decimal)
        - Precios positivos
        - Descuentos en rango válido (0-100%)
        - Coherencia entre costo, descuento y PVP
        - Coherencia entre subtotal y total

        Args:
            detalle: Diccionario con datos del detalle
            row_number: Número de fila en el Excel

        Returns:
            Lista de issues de validación
        """
        issues = []

        # Validar costo sin IVA
        costo_sin_iva = self._parse_numeric_value(
            detalle.get("costo_doc_sin_iva"),
            "costo_doc_sin_iva",
            row_number,
            issues
        )
        if costo_sin_iva is not None:
            if costo_sin_iva < 0:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field="costo_doc_sin_iva",
                    severity=ValidationSeverity.ERROR,
                    message="El costo sin IVA no puede ser negativo",
                    value=costo_sin_iva
                ))
            elif costo_sin_iva == 0:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field="costo_doc_sin_iva",
                    severity=ValidationSeverity.WARNING,
                    message="El costo sin IVA es cero. Verifique que sea correcto",
                    value=costo_sin_iva
                ))

        # Validar descuento
        descuento = self._parse_numeric_value(
            detalle.get("descuento_1"),
            "descuento_1",
            row_number,
            issues
        )
        descuento_porcentaje = self._normalizar_descuento(descuento, row_number, issues)

        # Validar PVP
        pvp = self._parse_numeric_value(
            detalle.get("pvp"),
            "pvp",
            row_number,
            issues
        )
        if pvp is not None:
            self._validar_pvp(pvp, costo_sin_iva, descuento_porcentaje, row_number, issues)

        # Validar subtotal y total
        self._validar_subtotal_total(
            detalle.get("subtotal"),
            detalle.get("total"),
            row_number,
            issues
        )

        return issues

    def _parse_numeric_value(
        self,
        value: Any,
        field_name: str,
        row_number: int,
        issues: List[ValidationIssue]
    ) -> Optional[float]:
        """
        Parsea un valor numérico, manejando formato regional.

        Args:
            value: Valor a parsear
            field_name: Nombre del campo (para mensajes de error)
            row_number: Número de fila
            issues: Lista donde agregar errores de parseo

        Returns:
            Valor flotante parseado o None
        """
        if value is None or pd.isna(value):
            return None

        # Convertir a string y limpiar
        str_value = str(value).strip()
        if not str_value:
            return None

        # Remover símbolos de moneda comunes
        str_value = str_value.replace('$', '').replace('€', '').replace('USD', '').strip()

        # Manejar formato regional (comas vs puntos)
        if self.usar_comas_decimales:
            # Formato europeo: 10,50 (coma como decimal)
            # Reemplazar punto de miles por nada y coma por punto
            if '.' in str_value and ',' in str_value:
                # Tiene ambos: asumir punto=miles, coma=decimal
                str_value = str_value.replace('.', '').replace(',', '.')
            elif ',' in str_value:
                # Solo coma: es decimal
                str_value = str_value.replace(',', '.')
        else:
            # Formato estándar: 10.50 (punto como decimal)
            # Reemplazar coma por punto (si hay coma, asumir que es decimal mal formateado)
            if ',' in str_value and '.' not in str_value:
                # Solo coma: intentar como decimal
                str_value = str_value.replace(',', '.')
            elif ',' in str_value and '.' in str_value:
                # Tiene ambos: asumir coma=miles, punto=decimal
                str_value = str_value.replace(',', '')

        try:
            return float(str_value)
        except (ValueError, TypeError):
            issues.append(ValidationIssue(
                row_number=row_number,
                field=field_name,
                severity=ValidationSeverity.ERROR,
                message=f"El valor de {field_name} no es un número válido. Valor recibido: {value}",
                value=value
            ))
            return None

    def _normalizar_descuento(
        self,
        descuento: Optional[float],
        row_number: int,
        issues: List[ValidationIssue]
    ) -> Optional[float]:
        """
        Normaliza descuento a porcentaje (0-100).

        Args:
            descuento: Valor del descuento (puede ser decimal 0-1 o porcentaje 0-100)
            row_number: Número de fila
            issues: Lista donde agregar errores

        Returns:
            Descuento normalizado como porcentaje (0-100) o None
        """
        if descuento is None:
            return None

        # El descuento puede venir como porcentaje (0-100) o como decimal (0-1)
        if descuento > 1 and descuento <= 100:
            # Está como porcentaje (ej: 20 para 20%)
            descuento_porcentaje = descuento
        elif descuento >= 0 and descuento <= 1:
            # Está como decimal (ej: 0.20 para 20%)
            descuento_porcentaje = descuento * 100
        else:
            issues.append(ValidationIssue(
                row_number=row_number,
                field="descuento_1",
                severity=ValidationSeverity.ERROR,
                message=f"El descuento debe estar entre 0 y 100% (o 0 y 1 si es decimal). Valor recibido: {descuento}",
                value=descuento
            ))
            return None

        # Validar rango final
        if descuento_porcentaje < 0 or descuento_porcentaje > 100:
            issues.append(ValidationIssue(
                row_number=row_number,
                field="descuento_1",
                severity=ValidationSeverity.ERROR,
                message=f"El descuento debe estar entre 0 y 100%. Valor recibido: {descuento_porcentaje}%",
                value=descuento
            ))
            return None
        elif descuento_porcentaje > 50:
            issues.append(ValidationIssue(
                row_number=row_number,
                field="descuento_1",
                severity=ValidationSeverity.WARNING,
                message=f"El descuento es muy alto ({descuento_porcentaje}%). Verifique que sea correcto",
                value=descuento
            ))

        return descuento_porcentaje

    def _validar_pvp(
        self,
        pvp: float,
        costo_sin_iva: Optional[float],
        descuento_porcentaje: Optional[float],
        row_number: int,
        issues: List[ValidationIssue]
    ) -> None:
        """
        Valida PVP contra costo y descuento.

        Args:
            pvp: Precio de venta al público
            costo_sin_iva: Costo sin IVA (opcional)
            descuento_porcentaje: Descuento como porcentaje (opcional)
            row_number: Número de fila
            issues: Lista donde agregar errores
        """
        if pvp < 0:
            issues.append(ValidationIssue(
                row_number=row_number,
                field="pvp",
                severity=ValidationSeverity.ERROR,
                message="El PVP no puede ser negativo",
                value=pvp
            ))
        elif pvp == 0:
            issues.append(ValidationIssue(
                row_number=row_number,
                field="pvp",
                severity=ValidationSeverity.WARNING,
                message="El PVP es cero. Verifique que sea correcto",
                value=pvp
            ))

        # Validar coherencia: PVP debería ser >= costo (después de aplicar descuento)
        if costo_sin_iva is not None and pvp > 0:
            costo_con_iva = costo_sin_iva * (1 + self.iva_porcentaje / 100)
            if descuento_porcentaje is not None:
                costo_con_descuento = costo_con_iva * (1 - descuento_porcentaje / 100)
            else:
                costo_con_descuento = costo_con_iva

            # PVP debería ser razonablemente mayor o igual al costo con descuento
            # Permitir hasta 10% de diferencia por redondeo
            if pvp < costo_con_descuento * 0.9:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field="pvp",
                    severity=ValidationSeverity.WARNING,
                    message=f"El PVP ({pvp:.2f}) es menor que el costo con IVA y descuento ({costo_con_descuento:.2f}). Verifique los cálculos",
                    value=pvp
                ))

    def _validar_subtotal_total(
        self,
        subtotal: Any,
        total: Any,
        row_number: int,
        issues: List[ValidationIssue]
    ) -> None:
        """
        Valida subtotal y total.

        Args:
            subtotal: Subtotal del detalle
            total: Total del detalle
            row_number: Número de fila
            issues: Lista donde agregar errores
        """
        subtotal_val = self._parse_numeric_value(subtotal, "subtotal", row_number, issues)
        total_val = self._parse_numeric_value(total, "total", row_number, issues)

        if subtotal_val is not None and subtotal_val < 0:
            issues.append(ValidationIssue(
                row_number=row_number,
                field="subtotal",
                severity=ValidationSeverity.ERROR,
                message="El subtotal no puede ser negativo",
                value=subtotal_val
            ))

        if total_val is not None and total_val < 0:
            issues.append(ValidationIssue(
                row_number=row_number,
                field="total",
                severity=ValidationSeverity.ERROR,
                message="El total no puede ser negativo",
                value=total_val
            ))

        # Validar coherencia: total debería ser >= subtotal
        if subtotal_val is not None and total_val is not None:
            if total_val < subtotal_val:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field="total",
                    severity=ValidationSeverity.WARNING,
                    message=f"El total ({total_val:.2f}) es menor que el subtotal ({subtotal_val:.2f}). Verifique los cálculos",
                    value=total_val
                ))

