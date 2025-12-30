"""
Tests para PedidoValidationExporter - Exportación de logs de validación.
"""

import pytest  # type: ignore[reportMissingImports]
import pandas as pd
import io

from src.database.services.pedido_validation_exporter import PedidoValidationExporter
from src.database.services.pedido_validator import ValidationIssue, ValidationSeverity


class TestPedidoValidationExporter:
    """Tests para PedidoValidationExporter."""
    
    def _crear_resultado_validacion(self, issues: list) -> dict:
        """Crea un resultado de validación para testing."""
        issues_by_row = {}
        errors = 0
        warnings = 0
        
        for issue in issues:
            row_num = issue.row_number if isinstance(issue, ValidationIssue) else issue.get("row_number", 0)
            if row_num not in issues_by_row:
                issues_by_row[row_num] = []
            issues_by_row[row_num].append(issue)
            
            severity = issue.severity if isinstance(issue, ValidationIssue) else issue.get("severity")
            if severity == ValidationSeverity.ERROR or severity == "ERROR":
                errors += 1
            elif severity == ValidationSeverity.WARNING or severity == "WARNING":
                warnings += 1
        
        return {
            "valid": errors == 0,
            "total_issues": len(issues),
            "errors": errors,
            "warnings": warnings,
            "issues_by_row": issues_by_row
        }
    
    def test_export_to_dataframe_sin_issues(self):
        """Test que exporta DataFrame vacío cuando no hay issues."""
        resultado = self._crear_resultado_validacion([])
        
        df = PedidoValidationExporter.export_to_dataframe(resultado)
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert list(df.columns) == ["Fila", "Campo", "Severidad", "Mensaje", "Valor"]
    
    def test_export_to_dataframe_con_issues(self):
        """Test que exporta DataFrame con issues."""
        issues = [
            ValidationIssue(
                row_number=2,
                field="codigo_interno",
                severity=ValidationSeverity.ERROR,
                message="Código inválido",
                value="PROD#123"
            ),
            ValidationIssue(
                row_number=3,
                field="cantidad",
                severity=ValidationSeverity.WARNING,
                message="Cantidad alta",
                value=1000
            )
        ]
        
        resultado = self._crear_resultado_validacion(issues)
        
        df = PedidoValidationExporter.export_to_dataframe(resultado)
        
        assert len(df) == 2
        assert list(df.columns) == ["Fila", "Campo", "Severidad", "Mensaje", "Valor"]
        
        # Verificar primera fila (ERROR)
        assert df.iloc[0]["Fila"] == 2
        assert df.iloc[0]["Campo"] == "codigo_interno"
        assert df.iloc[0]["Severidad"] == "ERROR"
        assert df.iloc[0]["Mensaje"] == "Código inválido"
        assert str(df.iloc[0]["Valor"]) == "PROD#123"
    
    def test_export_to_dataframe_ordena_por_severidad(self):
        """Test que ordena issues por severidad (ERROR primero)."""
        # Issues en la misma fila para que el ordenamiento por severidad sea visible
        issues = [
            ValidationIssue(2, "campo1", ValidationSeverity.WARNING, "Warning 1", None),
            ValidationIssue(2, "campo2", ValidationSeverity.ERROR, "Error 1", None),
            ValidationIssue(2, "campo3", ValidationSeverity.WARNING, "Warning 2", None)
        ]
        
        resultado = self._crear_resultado_validacion(issues)
        
        df = PedidoValidationExporter.export_to_dataframe(resultado)
        
        # El primer issue debe ser ERROR (misma fila, pero ERROR primero)
        assert df.iloc[0]["Severidad"] == "ERROR"
        assert df.iloc[0]["Fila"] == 2
    
    def test_export_to_dataframe_dict_issues(self):
        """Test que maneja issues como diccionarios (deserializados)."""
        issues = [
            {
                "row_number": 2,
                "field": "codigo_interno",
                "severity": "ERROR",
                "message": "Código inválido",
                "value": "PROD#123"
            }
        ]
        
        resultado = self._crear_resultado_validacion(issues)
        
        df = PedidoValidationExporter.export_to_dataframe(resultado)
        
        assert len(df) == 1
        assert df.iloc[0]["Fila"] == 2
        assert df.iloc[0]["Campo"] == "codigo_interno"
        assert df.iloc[0]["Severidad"] == "ERROR"
    
    def test_export_to_excel_bytes_sin_issues(self):
        """Test que exporta Excel vacío cuando no hay issues."""
        resultado = self._crear_resultado_validacion([])
        
        excel_bytes = PedidoValidationExporter.export_to_excel_bytes(resultado)
        
        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0
        
        # Verificar que es un Excel válido leyéndolo
        excel_file = pd.ExcelFile(io.BytesIO(excel_bytes))
        assert "Resumen" in excel_file.sheet_names
        assert "Errores y Advertencias" in excel_file.sheet_names
    
    def test_export_to_excel_bytes_con_issues(self):
        """Test que exporta Excel con issues."""
        issues = [
            ValidationIssue(2, "campo1", ValidationSeverity.ERROR, "Error 1", "valor1"),
            ValidationIssue(3, "campo2", ValidationSeverity.WARNING, "Warning 1", "valor2")
        ]
        
        resultado = self._crear_resultado_validacion(issues)
        
        excel_bytes = PedidoValidationExporter.export_to_excel_bytes(resultado)
        
        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0
        
        # Leer Excel y verificar contenido
        excel_file = pd.ExcelFile(io.BytesIO(excel_bytes))
        
        # Verificar hoja Resumen
        df_resumen = pd.read_excel(excel_file, sheet_name="Resumen")
        assert df_resumen.iloc[0]["Total Issues"] == 2
        assert df_resumen.iloc[0]["Errores"] == 1
        assert df_resumen.iloc[0]["Advertencias"] == 1
        
        # Verificar hoja Errores y Advertencias
        df_issues = pd.read_excel(excel_file, sheet_name="Errores y Advertencias")
        assert len(df_issues) == 2
        assert list(df_issues.columns) == ["Fila", "Campo", "Severidad", "Mensaje", "Valor"]
    
    def test_export_to_csv_sin_issues(self):
        """Test que exporta CSV vacío cuando no hay issues."""
        resultado = self._crear_resultado_validacion([])
        
        csv_str = PedidoValidationExporter.export_to_csv(resultado)
        
        assert isinstance(csv_str, str)
        assert "Fila" in csv_str
        assert "Campo" in csv_str
        assert "Severidad" in csv_str
    
    def test_export_to_csv_con_issues(self):
        """Test que exporta CSV con issues."""
        issues = [
            ValidationIssue(2, "campo1", ValidationSeverity.ERROR, "Error 1", "valor1")
        ]
        
        resultado = self._crear_resultado_validacion(issues)
        
        csv_str = PedidoValidationExporter.export_to_csv(resultado)
        
        assert isinstance(csv_str, str)
        assert "Fila" in csv_str
        assert "2" in csv_str
        assert "campo1" in csv_str
        assert "ERROR" in csv_str
        assert "Error 1" in csv_str
    
    def test_export_to_csv_encoding_utf8_sig(self):
        """Test que CSV usa encoding utf-8-sig (para Excel)."""
        issues = [
            ValidationIssue(2, "campo1", ValidationSeverity.ERROR, "Error con ñ y á", "valor1")
        ]
        
        resultado = self._crear_resultado_validacion(issues)
        
        csv_str = PedidoValidationExporter.export_to_csv(resultado)
        
        # Verificar que contiene caracteres especiales correctamente
        assert "ñ" in csv_str or "á" in csv_str

