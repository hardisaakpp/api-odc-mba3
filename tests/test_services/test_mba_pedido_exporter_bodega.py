"""
Tests para el campo Bodega (columna H) en el TXT MBA3.

Regla de negocio: la columna 8 (Bodega) siempre se exporta como "BPT",
sin importar origen_traslado ni ningún valor de configuración.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.database.services.mba_pedido_exporter import MBAExportConfig, MBAPedidoExporter


def _pedido(origen_traslado: str, cantidad: float = 1) -> dict:
    return {
        "cabecera": {
            "numero_pedido": "PED-1",
            "fecha_pedido": None,
            "fecha_entrega": None,
            "origen_traslado": origen_traslado,
        },
        "detalles": [
            {
                "codigo_interno": "COD-1",
                "costo_doc_sin_iva": 10.0,
                "tiendas": [{"codigo": "TRL-001", "cantidad": cantidad}],
            }
        ],
    }


def _columna_bodega(txt_bytes: bytes) -> str:
    linea_detalle = txt_bytes.decode("utf-8").split("\n")[-1]
    return linea_detalle.split("\t")[7]  # columna 8 (índice 0-based 7)


@pytest.mark.parametrize("origen_traslado", ["RL-CD", "RG-CD", "OUT-CD", "", "BODEGA-DESCONOCIDA"])
def test_bodega_siempre_es_bpt_sin_importar_origen_traslado(origen_traslado):
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = _pedido(origen_traslado)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    assert _columna_bodega(resultado) == "BPT"


def test_bodega_es_bpt_tambien_en_modo_consolidado():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = _pedido("RG-CD")

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba_consolidado(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    assert _columna_bodega(resultado) == "BPT"
