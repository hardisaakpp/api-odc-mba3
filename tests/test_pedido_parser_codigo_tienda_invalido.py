"""
Tests para la señalización de códigos de tienda no reconocidos en la fila de códigos.

Contexto (incidente 2026-09-01): un pedido con columnas de tienda 'RL-PCH'/'RL-CHL'
(prefijo 'RL-' en vez de 'TRL-') se rechazaba con "SUBTOTAL/TOTAL no coincide con la
suma de tiendas parseadas" en las 14 filas afectadas, sin señalar la causa real: la
columna se omitía en silencio por no matchear ningún formato de tienda/bodega válido
(ver _es_codigo_columna_tienda en pedido_parser_detalle.py). Este test cubre que ahora
se agrega un error explícito por columna apuntando al código mal escrito.
"""

import io
from typing import Any, Dict, List

import pandas as pd
from openpyxl import Workbook

from src.database.services.pedido_parser.pedido_parser_detalle import PedidoParserDetalle


def _crear_excel_detalle(headers: List[str], filas: List[List[Any]]) -> bytes:
    """Crea un .xlsx mínimo con hoja 'detalle': fila 1 nombres, fila 2 códigos, fila 3+ datos."""
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


def _errores_codigo_tienda(resultado: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [e for e in resultado["errores"] if e.get("campo") == "CODIGO_TIENDA"]


_HEADERS = [
    "Codigo Producto", "Codigo de Barras", "Descripcion SAP", "Pack",
    "Costo sin IVA", "Descuento", "PVP", "Subtotal", "Total",
    "RL-CD", "OUT-CD", "RG-CD",
    "TRL-MDA", "RL-PCH", "RL-CHL",
]


class TestCodigoTiendaNoReconocido:
    def test_columna_con_prefijo_mal_escrito_genera_error_por_columna(self):
        """'RL-PCH'/'RL-CHL' (falta la 'T' de TRL-) deben señalarse, no omitirse en silencio."""
        fila = ["SKU-1", "7501234567890", "Producto Uno", "6", 10.5, 0, 15.0, "", "", "", "", "", 4, 3, 2]
        resultado = _parsear(_HEADERS, [fila])

        errores = _errores_codigo_tienda(resultado)
        assert len(errores) == 2
        mensajes = " | ".join(e["mensaje"] for e in errores)
        assert "RL-PCH" in mensajes
        assert "RL-CHL" in mensajes
        assert all(e["tipo"] == "ERROR" for e in errores)

    def test_columna_no_reconocida_no_se_contabiliza_como_tienda(self):
        """La cantidad de la columna mal escrita no debe aparecer en las distribuciones."""
        fila = ["SKU-1", "7501234567890", "Producto Uno", "6", 10.5, 0, 15.0, "", "", "", "", "", 4, 3, 2]
        resultado = _parsear(_HEADERS, [fila])

        distribuciones = {d["idTienda"]: d["cantidad"] for d in resultado["data"] if d["codigoProducto"] == "SKU-1"}
        assert distribuciones.get("TRL-MDA") == 4
        assert "RL-PCH" not in distribuciones
        assert "RL-CHL" not in distribuciones

    def test_codigos_de_tienda_validos_no_generan_falso_positivo(self):
        """Bodegas (RL-CD/OUT-CD/RG-CD), TRL-/TOUT-/RG- y el patrón ABC01 no deben señalarse."""
        headers = [
            "Codigo Producto", "Codigo de Barras", "Descripcion SAP", "Pack",
            "Costo sin IVA", "Descuento", "PVP", "Subtotal", "Total",
            "RL-CD", "OUT-CD", "RG-CD",
            "TRL-MDA", "TOUT-COT", "RG-QVD",
            "ABC01",
        ]
        fila = ["SKU-1", "7501234567890", "Producto Uno", "6", 10.5, 0, 15.0, "", "", 1, 1, 1, 1, 1, 1, 1]
        resultado = _parsear(headers, [fila])

        assert _errores_codigo_tienda(resultado) == []

    def test_encabezados_reservados_no_generan_falso_positivo(self):
        """Una columna final vacía o repetida de OBSERVACION no debe señalarse como típo."""
        headers = [
            "Codigo Producto", "Codigo de Barras", "Descripcion SAP", "Pack",
            "Costo sin IVA", "Descuento", "PVP", "Subtotal", "Total",
            "RL-CD", "OUT-CD", "RG-CD",
            "TRL-MDA", "OBSERVACIONES",
        ]
        fila = ["SKU-1", "7501234567890", "Producto Uno", "6", 10.5, 0, 15.0, "", "", "", "", "", 4, "ok"]
        resultado = _parsear(headers, [fila])

        assert _errores_codigo_tienda(resultado) == []
