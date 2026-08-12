"""
Tests para la derivación automática del código de Vendedor en el TXT MBA3 (req. 1.7).

Regla de negocio: si no se especifica un vendedor manual, la columna 9 (Vendedor)
del TXT se deriva de origen_traslado (cabecera del pedido):
- RL-CD (ROLAND) y RG-CD (REGIONS) -> "mrz"
- OUT-CD (DESCUENTON)              -> "descu"
- Cualquier otro valor / vacío     -> "" (sin cambios respecto al comportamiento previo)

Un valor manual de config.vendedor siempre tiene prioridad sobre la derivación automática.
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


def _columna_vendedor(txt_bytes: bytes) -> str:
    linea_detalle = txt_bytes.decode("utf-8").split("\n")[-1]
    return linea_detalle.split("\t")[8]  # columna 9 (índice 0-based 8)


@pytest.mark.parametrize(
    "origen_traslado,vendedor_esperado",
    [
        ("RL-CD", "mrz"),
        ("RG-CD", "mrz"),
        ("OUT-CD", "descu"),
        ("", ""),
        ("BODEGA-DESCONOCIDA", ""),
    ],
)
def test_vendedor_se_deriva_de_origen_traslado(origen_traslado, vendedor_esperado):
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

    assert _columna_vendedor(resultado) == vendedor_esperado


def test_vendedor_manual_tiene_prioridad_sobre_origen_traslado():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        mock_repo_class.return_value.get_pedido_completo.return_value = _pedido("OUT-CD")

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(vendedor="JPC"),
            incluir_encabezado=False,
        )

    assert _columna_vendedor(resultado) == "JPC"


def test_vendedor_se_deriva_tambien_en_modo_consolidado():
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

    assert _columna_vendedor(resultado) == "mrz"
