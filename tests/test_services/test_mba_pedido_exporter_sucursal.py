"""
Tests para el campo Sucursal (columna 20) en el TXT MBA3.

Regla de negocio: la columna 20 (Sucursal) siempre se exporta como "PRI",
sin importar el código de tienda del detalle.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.database.services.mba_pedido_exporter import MBAExportConfig, MBAPedidoExporter


def _pedido(tienda_codigo: str, cantidad: float = 1) -> dict:
    return {
        "cabecera": {
            "numero_pedido": "PED-1",
            "fecha_pedido": None,
            "fecha_entrega": None,
            "origen_traslado": "",
        },
        "detalles": [
            {
                "codigo_interno": "COD-1",
                "costo_doc_sin_iva": 10.0,
                "tiendas": [{"codigo": tienda_codigo, "cantidad": cantidad}],
            }
        ],
    }


def _columna_sucursal(txt_bytes: bytes) -> str:
    linea_detalle = txt_bytes.decode("utf-8").split("\n")[-1]
    return linea_detalle.split("\t")[19]  # columna 20 (índice 0-based 19)


@pytest.mark.parametrize("tienda_codigo", ["TRL-QSN", "TOUT-001", "PRI", "", "OTRA-TIENDA-XYZ"])
def test_sucursal_siempre_es_pri_sin_importar_codigo_tienda(tienda_codigo):
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = _pedido(tienda_codigo)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    assert _columna_sucursal(resultado) == "PRI"


def test_sucursal_es_pri_tambien_en_modo_consolidado():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = _pedido("TRL-QSN")

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba_consolidado(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    assert _columna_sucursal(resultado) == "PRI"
