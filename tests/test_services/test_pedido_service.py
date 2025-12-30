"""
Tests para PedidoService - Parsing de Excel.
"""

import pytest  # type: ignore[reportMissingImports]
import pandas as pd
import io
from datetime import date
from typing import Optional

from src.database.services.pedido_service import PedidoService


class TestPedidoServiceParsearExcel:
    """Tests para parsear_excel_pedido()."""
    
    def _crear_excel_cabecera_detalle(
        self,
        cabecera_data: list,
        detalle_data: list,
        detalle_headers: Optional[list[str]] = None
    ) -> bytes:
        """
        Crea un archivo Excel en memoria con hojas CABECERA_PEDIDO y DETALLE_ARTICULO.
        
        Args:
            cabecera_data: Lista de listas [Campo, Valor, Ejemplo]
            detalle_data: Lista de listas con datos del detalle
            detalle_headers: Lista de nombres de columnas para detalle (default: CodigoProducto, IdTienda, Cantidad)
        """
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:  # type: ignore[arg-type]
            # Hoja CABECERA_PEDIDO
            if cabecera_data:
                df_cabecera = pd.DataFrame(cabecera_data, columns=["Campo", "Valor", "Ejemplo"])  # type: ignore[arg-type]
            else:
                df_cabecera = pd.DataFrame(columns=["Campo", "Valor", "Ejemplo"])  # type: ignore[arg-type]
            df_cabecera.to_excel(writer, sheet_name="CABECERA_PEDIDO", index=False, header=True)
            
            # Hoja DETALLE_ARTICULO
            if detalle_headers is None:
                detalle_headers = ["CodigoProducto", "IdTienda", "Cantidad"]
            
            if detalle_data:
                df_detalle = pd.DataFrame(detalle_data, columns=detalle_headers)  # type: ignore[arg-type]
            else:
                df_detalle = pd.DataFrame(columns=detalle_headers)  # type: ignore[arg-type]
            df_detalle.to_excel(writer, sheet_name="DETALLE_ARTICULO", index=False, header=True)
        
        output.seek(0)
        return output.read()
    
    def test_parsear_excel_formato_correcto(self):
        """Test que parsea un Excel con formato correcto."""
        cabecera = [
            ["CODIGO PEDIDO", "P-12.48", "P-12.48"],
            ["FECHA PEDIDO", "21/01/2025", "21/01/2025"],
            ["FECHA ENTREGA", "INMEDIATO", "INMEDIATO"]
        ]
        
        detalle = [
            ["R225.1012.BCO", "T001", 10],
            ["A889.3321.NEG", "T002", 5]
        ]
        
        excel_bytes = self._crear_excel_cabecera_detalle(cabecera, detalle)
        
        service = PedidoService()
        resultado = service.parsear_excel_pedido(excel_bytes)
        
        # Verificar estructura
        assert "cabecera" in resultado
        assert "resumen" in resultado
        assert "errores" in resultado
        assert "data" in resultado
        
        # Verificar cabecera
        assert "CODIGO PEDIDO" in resultado["cabecera"] or "numero_pedido" in resultado["cabecera"]
        assert resultado["resumen"]["filasLeidas"] == 2
        assert resultado["resumen"]["filasValidas"] == 2
        assert resultado["resumen"]["filasInvalidas"] == 0
        
        # Verificar data
        assert len(resultado["data"]) == 2
        assert resultado["data"][0]["codigoProducto"] == "R225.1012.BCO"
        assert resultado["data"][0]["idTienda"] == "T001"
        assert resultado["data"][0]["cantidad"] == 10
        assert resultado["data"][0]["filaOrigen"] == 2  # Fila 2 (header es fila 1)
    
    def test_parsear_excel_hoja_faltante(self):
        """Test que detecta cuando falta una hoja obligatoria."""
        # Crear Excel solo con cabecera (sin detalle)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:  # type: ignore[arg-type]
            df_cabecera = pd.DataFrame([["CODIGO PEDIDO", "P-12.48", "P-12.48"]], 
                                      columns=["Campo", "Valor", "Ejemplo"])  # type: ignore[arg-type]
            df_cabecera.to_excel(writer, sheet_name="CABECERA_PEDIDO", index=False)
        
        output.seek(0)
        excel_bytes = output.read()
        
        service = PedidoService()
        resultado = service.parsear_excel_pedido(excel_bytes)
        
        # Debe tener error por hoja faltante
        assert len(resultado["errores"]) > 0
        assert any("DETALLE_ARTICULO" in err["mensaje"] for err in resultado["errores"])
        assert resultado["resumen"]["filasInvalidas"] > 0
    
    def test_parsear_excel_columnas_faltantes(self):
        """Test que detecta cuando faltan columnas obligatorias en detalle."""
        cabecera = [["CODIGO PEDIDO", "P-12.48", "P-12.48"]]
        # Detalle sin columnas obligatorias
        detalle = [["R225.1012.BCO"]]  # Solo código, falta IdTienda y Cantidad
        detalle_headers = ["CodigoProducto"]  # Sin IdTienda ni Cantidad
        
        excel_bytes = self._crear_excel_cabecera_detalle(cabecera, detalle, detalle_headers)
        
        service = PedidoService()
        resultado = service.parsear_excel_pedido(excel_bytes)
        
        # Debe tener errores por columnas faltantes
        assert len(resultado["errores"]) > 0
        assert any("IdTienda" in err["mensaje"] or "Cantidad" in err["mensaje"] 
                  for err in resultado["errores"])
    
    def test_parsear_excel_duplicados_detecta_error(self):
        """Test que detecta duplicados (mismo CodigoProducto + IdTienda) como ERROR."""
        cabecera = [["CODIGO PEDIDO", "P-12.48", "P-12.48"]]
        
        # Dos filas con mismo producto y tienda (duplicado)
        detalle = [
            ["R225.1012.BCO", "T001", 10],
            ["R225.1012.BCO", "T001", 5]  # Duplicado
        ]
        
        excel_bytes = self._crear_excel_cabecera_detalle(cabecera, detalle)
        
        service = PedidoService()
        resultado = service.parsear_excel_pedido(excel_bytes)
        
        # Debe tener error por duplicado
        assert len(resultado["errores"]) > 0
        assert any("duplicado" in err["mensaje"].lower() or "duplicada" in err["mensaje"].lower()
                  for err in resultado["errores"])
        
        # Solo debe incluir la primera fila en data (no consolida)
        assert len(resultado["data"]) == 1
        assert resultado["data"][0]["cantidad"] == 10  # Primera cantidad, no suma
    
    def test_parsear_excel_formato_regional_comas(self):
        """Test que maneja correctamente números con comas (formato regional)."""
        cabecera = [["CODIGO PEDIDO", "P-12.48", "P-12.48"]]
        
        # Cantidad con coma (formato regional)
        detalle = [
            ["R225.1012.BCO", "T001", "10,0"]  # String con coma
        ]
        
        excel_bytes = self._crear_excel_cabecera_detalle(cabecera, detalle)
        
        service = PedidoService()
        resultado = service.parsear_excel_pedido(excel_bytes)
        
        # Debe convertir correctamente
        assert len(resultado["data"]) == 1
        assert resultado["data"][0]["cantidad"] == 10
    
    def test_parsear_excel_cantidad_decimal_rechaza(self):
        """Test que rechaza cantidades decimales (debe ser entero)."""
        cabecera = [["CODIGO PEDIDO", "P-12.48", "P-12.48"]]
        
        # Cantidad decimal (10.5)
        detalle = [
            ["R225.1012.BCO", "T001", 10.5]
        ]
        
        excel_bytes = self._crear_excel_cabecera_detalle(cabecera, detalle)
        
        service = PedidoService()
        resultado = service.parsear_excel_pedido(excel_bytes)
        
        # Debe tener error por cantidad decimal
        assert len(resultado["errores"]) > 0
        assert any("entero" in err["mensaje"].lower() or "decimal" in err["mensaje"].lower()
                  for err in resultado["errores"])
    
    def test_parsear_excel_cantidad_cero_rechaza(self):
        """Test que rechaza cantidades <= 0."""
        cabecera = [["CODIGO PEDIDO", "P-12.48", "P-12.48"]]
        
        detalle = [
            ["R225.1012.BCO", "T001", 0]
        ]
        
        excel_bytes = self._crear_excel_cabecera_detalle(cabecera, detalle)
        
        service = PedidoService()
        resultado = service.parsear_excel_pedido(excel_bytes)
        
        # Debe tener error por cantidad <= 0
        assert len(resultado["errores"]) > 0
        assert any("mayor a 0" in err["mensaje"].lower() or "cero" in err["mensaje"].lower()
                  for err in resultado["errores"])
    
    def test_parsear_excel_filas_vacias_ignora(self):
        """Test que ignora filas vacías en el detalle."""
        cabecera = [["CODIGO PEDIDO", "P-12.48", "P-12.48"]]
        
        # Filas con datos vacíos
        detalle = [
            ["R225.1012.BCO", "T001", 10],
            [None, None, None],  # Fila vacía
            ["", "", ""],  # Fila con strings vacíos
            ["A889.3321.NEG", "T002", 5]
        ]
        
        excel_bytes = self._crear_excel_cabecera_detalle(cabecera, detalle)
        
        service = PedidoService()
        resultado = service.parsear_excel_pedido(excel_bytes)
        
        # Solo debe procesar 2 filas válidas
        assert resultado["resumen"]["filasValidas"] == 2
        assert len(resultado["data"]) == 2
    
    def test_parsear_excel_trim_espacios(self):
        """Test que hace trim de espacios en valores."""
        cabecera = [
            ["CODIGO PEDIDO", "  P-12.48  ", "P-12.48"]  # Con espacios
        ]
        
        detalle = [
            ["  R225.1012.BCO  ", "  T001  ", 10]  # Con espacios
        ]
        
        excel_bytes = self._crear_excel_cabecera_detalle(cabecera, detalle)
        
        service = PedidoService()
        resultado = service.parsear_excel_pedido(excel_bytes)
        
        # Debe hacer trim
        assert resultado["data"][0]["codigoProducto"] == "R225.1012.BCO"
        assert resultado["data"][0]["idTienda"] == "T001"
    
    def test_parsear_excel_case_insensitive_columnas(self):
        """Test que acepta columnas con diferentes mayúsculas/minúsculas."""
        cabecera = [["CODIGO PEDIDO", "P-12.48", "P-12.48"]]
        
        # Columnas con diferentes casos
        detalle = [
            ["R225.1012.BCO", "T001", 10]
        ]
        detalle_headers = ["codigoproducto", "idtienda", "cantidad"]  # Todo minúsculas
        
        excel_bytes = self._crear_excel_cabecera_detalle(cabecera, detalle, detalle_headers)
        
        service = PedidoService()
        resultado = service.parsear_excel_pedido(excel_bytes)
        
        # Debe parsear correctamente
        assert len(resultado["data"]) == 1
        assert resultado["data"][0]["codigoProducto"] == "R225.1012.BCO"
    
    def test_parsear_excel_resumen_contadores(self):
        """Test que los contadores del resumen son correctos."""
        cabecera = [["CODIGO PEDIDO", "P-12.48", "P-12.48"]]
        
        detalle = [
            ["R225.1012.BCO", "T001", 10],  # Válida
            ["A889.3321.NEG", "T002", 5],   # Válida
            ["INVALID", None, 0]            # Inválida (sin tienda, cantidad 0)
        ]
        
        excel_bytes = self._crear_excel_cabecera_detalle(cabecera, detalle)
        
        service = PedidoService()
        resultado = service.parsear_excel_pedido(excel_bytes)
        
        # Verificar contadores
        assert resultado["resumen"]["filasLeidas"] == 3
        assert resultado["resumen"]["filasValidas"] == 2
        assert resultado["resumen"]["filasInvalidas"] == 1

