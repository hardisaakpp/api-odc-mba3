"""
Tests para la validación bloqueante de códigos de tienda/bodega no reconocidos.

Incidente 2026-09-01: un pedido con columnas de tienda 'RL-PCH'/'RL-CHL' (prefijo 'RL-' en
vez de 'TRL-') se rechazaba con 14 mensajes de "revisa la fórmula de SUBTOTAL/TOTAL", cuando
las fórmulas del Excel eran correctas y el problema real era el código de la columna (ver
PedidoParserDetalle._codigo_tienda_no_reconocido). Este test cubre que PedidoService ahora
señala esa causa raíz con un error_code y mensaje propios, antes de evaluar TOTAL/SUBTOTAL.
"""

import io
from typing import Any, Dict, List

import pandas as pd
import pytest
from openpyxl import Workbook

from src.database.services.pedido_parser.pedido_parser_detalle import PedidoParserDetalle
from src.database.services.pedido_service import PedidoService
from src.exceptions import BusinessException

_HEADERS_CON_CODIGOS_INVALIDOS = [
    "Codigo Producto", "Codigo de Barras", "Descripcion SAP", "Pack",
    "Costo sin IVA", "Descuento", "PVP", "Subtotal", "Total",
    "RL-CD", "OUT-CD", "RG-CD",
    "TRL-MDA", "RL-PCH", "RL-CHL",
]

_HEADERS_VALIDOS = [
    "Codigo Producto", "Codigo de Barras", "Descripcion SAP", "Pack",
    "Costo sin IVA", "Descuento", "PVP", "Subtotal", "Total",
    "RL-CD", "OUT-CD", "RG-CD",
    "TRL-MDA", "TOUT-COT",
]


def _crear_excel_detalle(headers: List[str], filas: List[List[Any]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "detalle"
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=1, column=col_idx, value=header)
        ws.cell(row=2, column=col_idx, value=header)
    for fila_idx, fila in enumerate(filas, start=3):
        for col_idx, valor in enumerate(fila, start=1):
            ws.cell(row=fila_idx, column=col_idx, value=valor)
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.read()


def _parsear(headers: List[str], filas: List[List[Any]]) -> Dict[str, Any]:
    excel_bytes = _crear_excel_detalle(headers, filas)
    excel_file = pd.ExcelFile(io.BytesIO(excel_bytes))
    return PedidoParserDetalle().parsear_nuevo_formato_v1_0(excel_file, excel_bytes, "detalle")


class TestValidacionCodigosTiendaReconocidos:
    def test_sin_codigos_invalidos_no_lanza_excepcion(self):
        fila = ["SKU-1", "7501234567890", "Producto Uno", "6", 10.5, 0, 15.0, "", "", "", "", "", 4, 3]
        resultado = _parsear(_HEADERS_VALIDOS, [fila])

        PedidoService._validar_codigos_tienda_reconocidos(resultado)  # no debe lanzar

    def test_codigos_invalidos_lanzan_business_exception_con_causa_real(self):
        # SUBTOTAL/TOTAL en blanco: aislamos esta validación de la de TOTAL/SUBTOTAL.
        fila = ["SKU-1", "7501234567890", "Producto Uno", "6", 10.5, 0, 15.0, "", "", "", "", "", 4, 3, 2]
        resultado = _parsear(_HEADERS_CON_CODIGOS_INVALIDOS, [fila])

        with pytest.raises(BusinessException) as exc_info:
            PedidoService._validar_codigos_tienda_reconocidos(resultado)

        exc = exc_info.value
        assert exc.error_code == "CODIGOS_TIENDA_NO_RECONOCIDOS"
        assert "RL-PCH" in exc.message
        assert "RL-CHL" in exc.message
        # El mensaje no debe decirle al usuario que revise la fórmula: el problema es el código.
        assert "revisa la fórmula" not in exc.message.lower()
        detalle = exc.data["validacion"]["codigos_tienda"]
        assert detalle["total_columnas_con_error"] == 2

    def test_codigos_invalidos_se_señalan_antes_que_total_subtotal(self):
        """Con SUBTOTAL/TOTAL desfasados Y códigos inválidos a la vez, se prioriza el código:
        arreglar el código es el paso previo antes de que TOTAL/SUBTOTAL se pueda evaluar bien."""
        fila = ["SKU-1", "7501234567890", "Producto Uno", "6", 10.5, 0, 15.0, 85, 100, "", "", "", 4, 3, 2]
        resultado = _parsear(_HEADERS_CON_CODIGOS_INVALIDOS, [fila])

        with pytest.raises(BusinessException) as exc_info:
            PedidoService._validar_codigos_tienda_reconocidos(resultado)
            PedidoService._validar_calculo_total_subtotal(resultado)

        assert exc_info.value.error_code == "CODIGOS_TIENDA_NO_RECONOCIDOS"
