"""
Exportador de logs de validación a CSV/Excel.
"""

import pandas as pd
import io
from typing import Dict, Any

from src.utils.timezone import ahora_naive

from .pedido_validator import ValidationIssue, ValidationSeverity


class PedidoValidationExporter:
    """Exporta logs de validación a CSV o Excel."""
    
    @staticmethod
    def _issue_to_row(row_num: Any, issue: Any) -> dict:
        if isinstance(issue, ValidationIssue):
            return {
                "Fila": row_num,
                "Campo": issue.field,
                "Severidad": issue.severity.value,
                "Mensaje": issue.message,
                "Valor": str(issue.value) if issue.value is not None else "",
            }
        return {
            "Fila": row_num,
            "Campo": issue.get("field", ""),
            "Severidad": issue.get("severity", "UNKNOWN"),
            "Mensaje": issue.get("message", ""),
            "Valor": str(issue.get("value", "")) if issue.get("value") is not None else "",
        }

    @staticmethod
    def export_to_dataframe(validation_result: Dict[str, Any]) -> pd.DataFrame:
        """
        Exporta resultado de validación a DataFrame.

        Args:
            validation_result: Resultado de validar_pedido_completo()

        Returns:
            DataFrame con columnas: fila, campo, severidad, mensaje, valor
        """
        rows = []

        for row_num, issues in validation_result.get("issues_by_row", {}).items():
            for issue in issues:
                rows.append(PedidoValidationExporter._issue_to_row(row_num, issue))
        
        if not rows:
            # Retornar DataFrame vacío con columnas
            return pd.DataFrame(columns=["Fila", "Campo", "Severidad", "Mensaje", "Valor"])  # type: ignore[arg-type]
        
        df = pd.DataFrame(rows)
        
        # Ordenar por fila y severidad (ERROR primero)
        if not df.empty:
            df["Severidad_Orden"] = df["Severidad"].map({  # type: ignore[arg-type]
                ValidationSeverity.ERROR.value: 0,
                ValidationSeverity.WARNING.value: 1
            }).fillna(2)
            df = df.sort_values(["Fila", "Severidad_Orden"])
            df = df.drop(columns=["Severidad_Orden"])
        
        return df
    
    @staticmethod
    def export_to_excel_bytes(validation_result: Dict[str, Any]) -> bytes:
        """
        Exporta resultado de validación a Excel (bytes).
        
        Args:
            validation_result: Resultado de validar_pedido_completo()
            
        Returns:
            Bytes del archivo Excel
        """
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:  # type: ignore[arg-type]
            # Hoja 1: Resumen
            resumen_df = pd.DataFrame([{
                "Total Issues": validation_result.get("total_issues", 0),
                "Errores": validation_result.get("errors", 0),
                "Advertencias": validation_result.get("warnings", 0),
                "Válido": validation_result.get("valid", False),
                "Fecha Validación": ahora_naive().isoformat()
            }])
            resumen_df.to_excel(writer, sheet_name="Resumen", index=False)
            
            # Hoja 2: Detalle de issues
            df = PedidoValidationExporter.export_to_dataframe(validation_result)
            if not df.empty:
                df.to_excel(writer, sheet_name="Errores y Advertencias", index=False)
            else:
                # Crear hoja vacía con headers
                pd.DataFrame(columns=["Fila", "Campo", "Severidad", "Mensaje", "Valor"]).to_excel(  # type: ignore[arg-type]
                    writer, sheet_name="Errores y Advertencias", index=False
                )
        
        output.seek(0)
        return output.read()
    
    @staticmethod
    def export_to_csv(validation_result: Dict[str, Any]) -> str:
        """
        Exporta resultado de validación a CSV (string).
        
        Args:
            validation_result: Resultado de validar_pedido_completo()
            
        Returns:
            String CSV
        """
        df = PedidoValidationExporter.export_to_dataframe(validation_result)
        return df.to_csv(index=False, encoding='utf-8-sig')  # utf-8-sig para Excel


