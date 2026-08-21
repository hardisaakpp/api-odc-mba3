"""
Tests para la columna MARCA de "Descargar Pedido" / "Descargar Pedido Original":
es un campo por producto (pedido_detalle.marca, sincronizado desde SAP OITM.U_MARCA,
ver pedido_utils.py), igual que en la tabla "Detalle del Pedido" de la UI
(PedidoDetalleView.vue) -- no tiene relación con el CD/bodega (ROLAND/REGIONS/
DESCUENTON, origen_traslado_detectado) resuelto en la Fase 1 de PYTD002.
"""

from openpyxl import Workbook

from src.endpoints.pedidos.pedidos_exportacion import _escribir_detalles_productos
from openpyxl.styles import Border, Side


def _leer_columna_marca(ws, n_filas):
    return [ws[f"C{14 + i}"].value for i in range(n_filas)]


def test_marca_se_escribe_por_fila_desde_el_detalle_no_desde_la_cabecera():
    wb = Workbook()
    ws = wb.active
    thin_border = Border(left=Side(style="thin"), right=Side(style="thin"), top=Side(style="thin"), bottom=Side(style="thin"))
    detalles = [
        {"codigo_interno": "R1", "marca": "ROLAND"},
        {"codigo_interno": "R2", "marca": "ROLAND REGIONS"},
        {"codigo_interno": "R3", "marca": None},
    ]

    _escribir_detalles_productos(ws, detalles, thin_border)

    assert _leer_columna_marca(ws, 3) == ["ROLAND", "ROLAND REGIONS", ""]
