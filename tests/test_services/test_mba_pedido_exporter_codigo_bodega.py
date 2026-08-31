"""
Tests para el parámetro codigo_bodega en el exportador TXT MBA3: cuando un pedido
generó más de una ODC (una por bodega/CD, ver
StockTransferService.detectar_origenes_traslado), el TXT de cada ODC debe:

- incluir solo las tiendas de esa bodega (no las de la otra ODC del mismo pedido)
- usar el DocNum de la ODC de esa bodega (no una ODC arbitraria del pedido)

Sin codigo_bodega, el comportamiento es el histórico (todas las tiendas, DocNum
de la ODC más reciente) -- ver test_mba_pedido_exporter_pedido_manual_docnum.py.
"""

from unittest.mock import MagicMock, patch

from src.database.services.mba_pedido_exporter import MBAExportConfig, MBAPedidoExporter

BODEGA_POR_TIENDA = {
    "TRL-QSN": "RL-CD",
    "RG-INT": "RG-CD",
}

TIENDA_ID_POR_CODIGO = {
    "TRL-QSN": "tienda-trl-qsn",
    "RG-INT": "tienda-rg-int",
}


def _pedido_mixto() -> dict:
    return {
        "cabecera": {
            "numero_pedido": "PED-1",
            "fecha_pedido": None,
            "fecha_entrega": None,
            "origen_traslado": "",
        },
        "detalles": [
            {
                "pedido_detalle_id": "detalle-roland",
                "codigo_interno": "COD-ROLAND",
                "costo_doc_sin_iva": 10.0,
                "tiendas": [{"tienda_id": TIENDA_ID_POR_CODIGO["TRL-QSN"], "codigo": "TRL-QSN", "cantidad": 5}],
            },
            {
                "pedido_detalle_id": "detalle-regions",
                "codigo_interno": "COD-REGIONS",
                "costo_doc_sin_iva": 20.0,
                "tiendas": [{"tienda_id": TIENDA_ID_POR_CODIGO["RG-INT"], "codigo": "RG-INT", "cantidad": 7}],
            },
        ],
    }


def _lineas_detalle(txt_bytes: bytes) -> list:
    return [linea for linea in txt_bytes.decode("utf-8").split("\n") if linea]


def _cantidades_asignadas_desde_pedido(pedido: dict) -> dict:
    """Deriva {pedido_detalle_id: {tienda_id: cantidad}} directamente de las
    cantidades que la fixture ya tenía en tienda["cantidad"], para que el mock de
    DistribucionConfirmadaRepository reproduzca exactamente lo mismo -- estos tests
    verifican bodega/DocNum, no cantidad."""
    return {
        detalle["pedido_detalle_id"]: {
            tienda["tienda_id"]: tienda["cantidad"] for tienda in detalle["tiendas"]
        }
        for detalle in pedido["detalles"]
    }


def _patch_comunes(mock_ctx, mock_repo_class, mock_oc_repo_class, mock_stock_service, mock_dist_class):
    mock_ctx.return_value.__enter__.return_value = MagicMock()
    pedido = _pedido_mixto()
    mock_repo_class.return_value.get_pedido_completo.return_value = pedido
    mock_repo_class.return_value.get_fecha_confirmacion_estado.return_value = None
    mock_stock_service.obtener_bodega_de_tienda.side_effect = lambda codigo: BODEGA_POR_TIENDA.get(codigo)
    mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = (
        _cantidades_asignadas_desde_pedido(pedido)
    )

    oc_repo = MagicMock()
    oc_repo.get_doc_num_by_pedido_id_y_bodega.side_effect = lambda pedido_id, bodega: (
        "DOCNUM-ROLAND" if bodega == "RL-CD" else "DOCNUM-REGIONS"
    )
    oc_repo.get_doc_num_by_pedido_id.return_value = "DOCNUM-MAS-RECIENTE"
    mock_oc_repo_class.return_value = oc_repo
    return oc_repo


def test_sin_codigo_bodega_incluye_todas_las_tiendas_y_docnum_generico():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_repo_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class:
        mock_ctx.return_value.__enter__.return_value = MagicMock()
        pedido = _pedido_mixto()
        mock_repo_class.return_value.get_pedido_completo.return_value = pedido
        mock_repo_class.return_value.get_fecha_confirmacion_estado.return_value = None
        mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = (
            _cantidades_asignadas_desde_pedido(pedido)
        )
        oc_repo = MagicMock()
        oc_repo.get_doc_num_by_pedido_id.return_value = "DOCNUM-MAS-RECIENTE"
        mock_oc_repo_class.return_value = oc_repo

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba_consolidado(
            pedido_id="pedido-mixto",
            config=MBAExportConfig(),
            incluir_encabezado=False,
        )

    lineas = _lineas_detalle(resultado)
    assert len(lineas) == 2
    oc_repo.get_doc_num_by_pedido_id_y_bodega.assert_not_called()
    for linea in lineas:
        assert linea.split("\t")[11] == "DOCNUM-MAS-RECIENTE"  # col 12: Orden Compra Cliente


def test_codigo_bodega_roland_filtra_solo_sus_tiendas_y_su_docnum():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_repo_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class, \
         patch("src.database.services.stock_transfer_service.StockTransferService") as mock_stock_service:
        oc_repo = _patch_comunes(mock_ctx, mock_repo_class, mock_oc_repo_class, mock_stock_service, mock_dist_class)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba_consolidado(
            pedido_id="pedido-mixto",
            config=MBAExportConfig(),
            incluir_encabezado=False,
            codigo_bodega="RL-CD",
        )

    lineas = _lineas_detalle(resultado)
    assert len(lineas) == 1
    cols = lineas[0].split("\t")
    assert cols[20] == "COD-ROLAND"  # col 21: Código Producto
    assert cols[11] == "DOCNUM-ROLAND"  # col 12: Orden Compra Cliente
    oc_repo.get_doc_num_by_pedido_id_y_bodega.assert_called_once_with("pedido-mixto", "RL-CD")
    oc_repo.get_doc_num_by_pedido_id.assert_not_called()


def test_codigo_bodega_regions_filtra_solo_sus_tiendas_y_su_docnum():
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_repo_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class, \
         patch("src.database.services.stock_transfer_service.StockTransferService") as mock_stock_service:
        _patch_comunes(mock_ctx, mock_repo_class, mock_oc_repo_class, mock_stock_service, mock_dist_class)

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba(
            pedido_id="pedido-mixto",
            config=MBAExportConfig(),
            incluir_encabezado=False,
            codigo_bodega="RG-CD",
        )

    lineas = _lineas_detalle(resultado)
    assert len(lineas) == 1
    cols = lineas[0].split("\t")
    assert cols[20] == "COD-REGIONS"
    assert cols[11] == "DOCNUM-REGIONS"


def _pedido_muchas_lineas_pocas_tiendas(n_lineas: int) -> dict:
    """N líneas repartidas en solo 2 tiendas -- simula un pedido real donde muchos
    productos comparten las mismas tiendas de destino."""
    return {
        "cabecera": {"numero_pedido": "PED-1", "fecha_pedido": None, "fecha_entrega": None, "origen_traslado": ""},
        "detalles": [
            {
                "pedido_detalle_id": f"detalle-{i}",
                "codigo_interno": f"COD-{i}",
                "costo_doc_sin_iva": 10.0,
                "tiendas": [{
                    "tienda_id": TIENDA_ID_POR_CODIGO["TRL-QSN"] if i % 2 == 0 else TIENDA_ID_POR_CODIGO["RG-INT"],
                    "codigo": "TRL-QSN" if i % 2 == 0 else "RG-INT",
                    "cantidad": 1,
                }],
            }
            for i in range(n_lineas)
        ],
    }


def test_no_repite_consulta_de_bodega_por_cada_linea_del_pedido():
    """Regresión: con codigo_bodega, la resolución de bodega por tienda debe hacerse
    una sola vez por código de tienda DISTINTO, no una vez por línea del pedido --
    StockTransferService.obtener_bodega_de_tienda abre una conexión nueva por llamada;
    repetirla por línea volvió una descarga de 12 líneas en ~31s (ver incidente real)."""
    with patch("src.database.services.mba_pedido_exporter.get_db_connection_context") as mock_ctx, \
         patch("src.database.services.mba_pedido_exporter.PedidoRepository") as mock_repo_class, \
         patch("src.database.services.mba_pedido_exporter.OrdenCompraRepository") as mock_oc_repo_class, \
         patch("src.database.services.mba_pedido_exporter.DistribucionConfirmadaRepository") as mock_dist_class, \
         patch("src.database.services.stock_transfer_service.StockTransferService") as mock_stock_service:
        oc_repo = _patch_comunes(mock_ctx, mock_repo_class, mock_oc_repo_class, mock_stock_service, mock_dist_class)
        pedido_muchas_lineas = _pedido_muchas_lineas_pocas_tiendas(12)
        mock_repo_class.return_value.get_pedido_completo.return_value = pedido_muchas_lineas
        mock_dist_class.return_value.get_cantidades_asignadas_por_pedido.return_value = (
            _cantidades_asignadas_desde_pedido(pedido_muchas_lineas)
        )

        exporter = MBAPedidoExporter()
        resultado = exporter.exportar_pedido_formato_mba_consolidado(
            pedido_id="pedido-muchas-lineas",
            config=MBAExportConfig(),
            incluir_encabezado=False,
            codigo_bodega="RG-CD",
        )

    assert len(_lineas_detalle(resultado)) == 6  # las 6 líneas de RG-INT
    # 2 tiendas distintas en todo el pedido -> a lo sumo 2 llamadas, sin importar
    # que haya 12 líneas.
    assert mock_stock_service.obtener_bodega_de_tienda.call_count <= 2
    oc_repo.get_doc_num_by_pedido_id_y_bodega.assert_called_once_with("pedido-muchas-lineas", "RG-CD")
