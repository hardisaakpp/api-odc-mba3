"""
Tests para Pedido Manual (col. 10) y Orden Compra Cliente (col. 12) en el TXT MBA3.

Regla de negocio: col. 10 (Pedido Manual) usa el número de pedido interno
(numero_pedido); col. 12 (Orden Compra Cliente) usa el DocNum de la Orden de
Compra ya enviada a SAP (orden_compra_cabecera.numero_oc_sap), no el número
de pedido como antes.
"""

from unittest.mock import MagicMock, patch

from src.database.services.mba_pedido_exporter import MBAExportConfig, MBAPedidoExporter


def _pedido(numero_pedido: str = "PED-123", cantidad: float = 1) -> dict:
    return {
        "cabecera": {
            "numero_pedido": numero_pedido,
            "fecha_pedido": None,
            "fecha_entrega": None,
            "origen_traslado": "",
        },
        "detalles": [
            {
                "codigo_interno": "COD-1",
                "costo_doc_sin_iva": 10.0,
                "tiendas": [{"codigo": "TRL-001", "cantidad": cantidad}],
            }
        ],
    }


def _columnas(txt_bytes: bytes) -> list:
    linea_detalle = txt_bytes.decode("utf-8").split("\n")[-1]
    return linea_detalle.split("\t")


def _mocks(mock_repo_class, mock_oc_class, numero_pedido="PED-123", doc_num="1524"):
    mock_repo_class.return_value.get_pedido_completo.return_value = _pedido(numero_pedido)
    mock_oc_class.return_value.get_doc_num_by_pedido_id.return_value = doc_num


def test_pedido_manual_usa_numero_pedido_y_orden_compra_cliente_usa_doc_num():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mocks(mock_repo_class, mock_oc_class, numero_pedido="PED-123", doc_num="1524")

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    cols = _columnas(resultado)
    assert cols[9] == "PED-123"  # col 10: Pedido Manual
    assert cols[11] == "1524"  # col 12: Orden Compra Cliente (DocNum SAP)


def test_orden_compra_cliente_vacia_si_no_hay_doc_num():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mocks(mock_repo_class, mock_oc_class, doc_num=None)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    cols = _columnas(resultado)
    assert cols[9] == "PED-123"  # Pedido Manual sigue presente
    assert cols[11] == ""  # sin OC/DocNum, queda vacía


def test_pedido_manual_y_doc_num_tambien_en_modo_consolidado():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mocks(mock_repo_class, mock_oc_class, numero_pedido="PED-999", doc_num="7788")

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba_consolidado(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    cols = _columnas(resultado)
    assert cols[9] == "PED-999"
    assert cols[11] == "7788"


def test_orden_compra_cliente_ya_no_usa_numero_pedido():
    """Verifica explícitamente que col. 12 dejó de usar numero_pedido (comportamiento previo)."""
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mocks(mock_repo_class, mock_oc_class, numero_pedido="PED-777", doc_num="4242")

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    cols = _columnas(resultado)
    assert cols[11] != "PED-777"
    assert cols[11] == "4242"
