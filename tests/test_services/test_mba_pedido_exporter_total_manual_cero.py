"""
Tests para la exclusión de productos con Total editado manualmente a 0.

Regla de negocio: si en el Detalle del Pedido el usuario edita el campo "Total"
de un producto a 0 (pedido_detalle.total_modificado_manual=1 y total=0/None),
ese producto no debe exportarse al TXT MBA3 (ninguna línea, en ninguna tienda),
ya que una línea sin código de producto identificado no es válida para MBA.

Si el producto llegó con total 0 desde el Excel original (sin edición manual,
total_modificado_manual=0/False), se mantiene el comportamiento previo: sí se
exporta (comportamiento de "cantidad" ya cubierto por otros tests).
"""

from unittest.mock import MagicMock, patch

from src.database.services.mba_pedido_exporter import MBAExportConfig, MBAPedidoExporter


def _pedido(detalles: list) -> dict:
    return {
        "cabecera": {
            "numero_pedido": "PED-1",
            "fecha_pedido": None,
            "fecha_entrega": None,
            "origen_traslado": "",
        },
        "detalles": detalles,
    }


TIENDA_ID = "tienda-1"


def _detalle(codigo_interno: str, total_modificado_manual: bool, total, cantidad: float = 5) -> dict:
    return {
        "pedido_detalle_id": f"detalle-{codigo_interno}",
        "codigo_interno": codigo_interno,
        "costo_doc_sin_iva": 10.0,
        "total": total,
        "total_modificado_manual": total_modificado_manual,
        "tiendas": [{"tienda_id": TIENDA_ID, "codigo": "TRL-001", "cantidad": cantidad}],
    }


def _codigos_exportados(txt_bytes: bytes) -> list:
    lineas = [linea for linea in txt_bytes.decode("utf-8").split("\n") if linea.strip()]
    return [linea.split("\t")[20] for linea in lineas]  # col 21 (índice 0-based 20)


def _mock_pedido(mock_repo_class, mock_oc_class, mock_dist_class, detalles):
    mock_repo_class.return_value.get_pedido_completo.return_value = _pedido(detalles)
    mock_oc_class.return_value.get_doc_num_by_pedido_id.return_value = None
    # Reproduce exactamente las mismas cantidades que cada fixture ya tenía en
    # tienda["cantidad"], para no cambiar la intención de estos tests (verifican
    # exclusión por Total manual a 0, no cantidad).
    cantidades_asignadas = {
        detalle["pedido_detalle_id"]: {
            tienda["tienda_id"]: tienda["cantidad"] for tienda in detalle["tiendas"]
        }
        for detalle in detalles
    }
    mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = cantidades_asignadas


def test_excluye_producto_con_total_editado_manualmente_a_cero():
    detalles = [
        _detalle("COD-A", total_modificado_manual=True, total=0),
        _detalle("COD-B", total_modificado_manual=False, total=100),
    ]
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mock_pedido(mock_repo_class, mock_oc_class, mock_dist_class, detalles)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    codigos = _codigos_exportados(resultado)
    assert "COD-A" not in codigos
    assert codigos == ["COD-B"]


def test_no_excluye_si_total_cero_no_fue_editado_manualmente():
    """Total=0 sin total_modificado_manual (ej. vino así del Excel original): se exporta igual."""
    detalles = [_detalle("COD-A", total_modificado_manual=False, total=0)]
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mock_pedido(mock_repo_class, mock_oc_class, mock_dist_class, detalles)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    assert _codigos_exportados(resultado) == ["COD-A"]


def test_no_excluye_si_total_modificado_manual_pero_distinto_de_cero():
    """Si el usuario editó el Total pero a un valor distinto de 0, el producto se exporta."""
    detalles = [_detalle("COD-A", total_modificado_manual=True, total=7)]
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mock_pedido(mock_repo_class, mock_oc_class, mock_dist_class, detalles)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    assert _codigos_exportados(resultado) == ["COD-A"]


def test_excluye_producto_con_total_none_y_modificado_manual():
    """total=None (mapeo backend de 0 -> None) con total_modificado_manual=True también excluye."""
    detalles = [_detalle("COD-A", total_modificado_manual=True, total=None)]
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mock_pedido(mock_repo_class, mock_oc_class, mock_dist_class, detalles)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    assert _codigos_exportados(resultado) == []


def test_excluye_producto_tambien_en_modo_consolidado():
    detalles = [
        _detalle("COD-A", total_modificado_manual=True, total=0),
        _detalle("COD-B", total_modificado_manual=False, total=100),
    ]
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        _mock_pedido(mock_repo_class, mock_oc_class, mock_dist_class, detalles)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba_consolidado(
            pedido_id="00000000-0000-0000-0000-000000000000",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    codigos = _codigos_exportados(resultado)
    assert "COD-A" not in codigos
    assert codigos == ["COD-B"]
