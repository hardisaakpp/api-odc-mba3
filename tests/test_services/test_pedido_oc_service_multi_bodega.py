"""
Tests para la generación de 2 ODC cuando un pedido mezcla tiendas ROLAND y REGIONS
(Fase 2 de PYTD002).

Cubre las piezas puras/aisladas de PedidoOCService:
- _sumar_cantidad_por_bodega: suma cantidad_asignada por bodega resuelta.
- _dividir_procesamientos_por_bodega: reparte procesamientos (cantidad_sap ya
  agregada por producto) entre bodegas, escalando proporcionalmente cuando un
  producto tiene tiendas de ambas.
- _tiendas_por_bodega: agrupa códigos de tienda (destino real de ST) por bodega.
"""

from unittest.mock import MagicMock, patch

from src.database.services.pedido_oc_service import PedidoOCService


def _dist(tienda_codigo, cantidad_asignada, es_bodega=False):
    return {"tienda_codigo": tienda_codigo, "cantidad_asignada": cantidad_asignada, "es_bodega": es_bodega}


BODEGA_POR_CODIGO = {
    "TRL-QSN": "RL-CD",
    "TRL-SMA": "RL-CD",
    "RG-INT": "RG-CD",
    "RG-CUE": "RG-CD",
}


def _patch_obtener_bodega():
    return patch(
        "src.database.services.stock_transfer_service.StockTransferService.obtener_bodega_de_tienda",
        side_effect=lambda codigo: BODEGA_POR_CODIGO.get(codigo),
    )


def test_sumar_cantidad_por_bodega_agrupa_y_excluye_bodegas():
    with _patch_obtener_bodega():
        distribuciones = [
            _dist("TRL-QSN", 20),
            _dist("TRL-SMA", 5),
            _dist("RG-INT", 15),
            _dist("RL-CD", 999, es_bodega=True),  # excluida: es_bodega=True
            _dist("SIN-MARCA", 3),  # sin marca resoluble -> se ignora
        ]
        sumas = PedidoOCService._sumar_cantidad_por_bodega(distribuciones)
        assert sumas == {"RL-CD": 25, "RG-CD": 15}


def _mock_dist_repo(productos):
    mock_repo_class = MagicMock()
    instance = mock_repo_class.return_value
    instance.get_version_actual.return_value = 1
    instance.get_distribucion_completa.return_value = {"productos": productos}
    return mock_repo_class


def test_dividir_procesamientos_producto_solo_roland_no_se_divide():
    proc = {
        "pedido_detalle_id": "det-1",
        "item_code_sap": "ITEM-1",
        "cantidad_original": 20,
        "cantidad_sap": 40,
        "total_linea_sap": 100,
    }
    productos = [{"pedido_detalle_id": "det-1", "distribuciones": [_dist("TRL-QSN", 20)]}]

    with _patch_obtener_bodega(), \
         patch(
             "src.database.repositories.distribucion_confirmada_repository.DistribucionConfirmadaRepository",
             _mock_dist_repo(productos)
         ):
        resultado = PedidoOCService._dividir_procesamientos_por_bodega(
            [proc], "pedido-1", MagicMock(), ["RL-CD", "RG-CD"]
        )

    assert resultado["RL-CD"] == [proc]
    assert resultado["RG-CD"] == []


def test_dividir_procesamientos_producto_mixto_se_divide_proporcionalmente():
    proc = {
        "pedido_detalle_id": "det-1",
        "item_code_sap": "ITEM-1",
        "cantidad_original": 35,
        "cantidad_sap": 70,
        "total_linea_sap": 140.0,
    }
    # 20 unidades a RL-CD, 15 a RG-CD -> proporción 20/35 y 15/35
    productos = [{
        "pedido_detalle_id": "det-1",
        "distribuciones": [_dist("TRL-QSN", 20), _dist("RG-INT", 15)],
    }]

    with _patch_obtener_bodega(), \
         patch(
             "src.database.repositories.distribucion_confirmada_repository.DistribucionConfirmadaRepository",
             _mock_dist_repo(productos)
         ):
        resultado = PedidoOCService._dividir_procesamientos_por_bodega(
            [proc], "pedido-1", MagicMock(), ["RL-CD", "RG-CD"]
        )

    assert len(resultado["RL-CD"]) == 1
    assert len(resultado["RG-CD"]) == 1
    rl = resultado["RL-CD"][0]
    rg = resultado["RG-CD"][0]

    # La suma de las 2 sub-cantidades debe dar la cantidad total original.
    assert rl["cantidad_sap"] + rg["cantidad_sap"] == 70
    assert rl["total_linea_sap"] + rg["total_linea_sap"] == 140.0
    assert rl["cantidad_sap"] == 40.0  # 70 * 20/35
    assert rg["cantidad_sap"] == 30.0  # 70 * 15/35
    # No se muta el dict original.
    assert proc["cantidad_sap"] == 70


def test_dividir_procesamientos_sin_distribucion_confirmada_usa_primera_bodega():
    proc = {"pedido_detalle_id": "det-1", "item_code_sap": "ITEM-1", "cantidad_sap": 10, "total_linea_sap": 10}
    mock_repo_class = MagicMock()
    mock_repo_class.return_value.get_version_actual.return_value = 0  # sin distribución confirmada

    with patch(
        "src.database.repositories.distribucion_confirmada_repository.DistribucionConfirmadaRepository",
        mock_repo_class
    ):
        resultado = PedidoOCService._dividir_procesamientos_por_bodega(
            [proc], "pedido-1", MagicMock(), ["RL-CD", "RG-CD"]
        )

    assert resultado["RL-CD"] == [proc]
    assert resultado["RG-CD"] == []


def test_buscar_bodega_en_producto_respeta_bodega_objetivo():
    """Regresión: una línea es_bodega=True de UNA bodega no debe resolverse como
    la bodega de la OTRA ODC del mismo pedido mixto (bug real: ambas ODC de
    'pedido prueba 114' terminaron con WarehouseCode=RG-CD en todas sus líneas)."""
    producto = {
        "pedido_detalle_id": "det-1",
        "distribuciones": [_dist("RG-CD", 5, es_bodega=True)],
    }
    assert PedidoOCService._buscar_bodega_en_producto(producto, "det-1", bodega_objetivo="RL-CD") is None
    assert PedidoOCService._buscar_bodega_en_producto(producto, "det-1", bodega_objetivo="RG-CD") == "RG-CD"
    # Sin bodega objetivo (caso histórico de una sola bodega): comportamiento sin filtrar.
    assert PedidoOCService._buscar_bodega_en_producto(producto, "det-1") == "RG-CD"


def test_to_orden_compra_detalle_no_contamina_bodega_de_otra_odc_en_pedido_mixto():
    service = PedidoOCService()
    productos = [{
        "pedido_detalle_id": "det-1",
        "distribuciones": [_dist("RG-CD", 5, es_bodega=True)],
    }]
    proc = {
        "pedido_detalle_id": "det-1",
        "item_code_sap": "ITEM-1",
        "cantidad_sap": 10,
        "unidad_sap": "UN",
        "precio_unitario_sap": 1,
        "total_linea_sap": 10,
        "cantidad_original": 10,
    }

    with patch(
        "src.database.repositories.distribucion_confirmada_repository.DistribucionConfirmadaRepository",
        _mock_dist_repo(productos)
    ):
        detalle_rl = service._to_orden_compra_detalle_from_procesamiento(
            proc, conn=MagicMock(), pedido_id="pedido-1", codigo_bodega_cabecera="RL-CD"
        )
        detalle_rg = service._to_orden_compra_detalle_from_procesamiento(
            proc, conn=MagicMock(), pedido_id="pedido-1", codigo_bodega_cabecera="RG-CD"
        )

    assert detalle_rl["codigo_bodega"] == "RL-CD"
    assert detalle_rg["codigo_bodega"] == "RG-CD"


def test_tiendas_por_bodega_agrupa_codigos_unicos():
    productos = [
        {"pedido_detalle_id": "det-1", "distribuciones": [_dist("TRL-QSN", 20), _dist("RG-INT", 15)]},
        {"pedido_detalle_id": "det-2", "distribuciones": [_dist("TRL-QSN", 5), _dist("TRL-SMA", 8)]},
    ]
    with _patch_obtener_bodega(), \
         patch(
             "src.database.repositories.distribucion_confirmada_repository.DistribucionConfirmadaRepository",
             _mock_dist_repo(productos)
         ):
        grupos = PedidoOCService._tiendas_por_bodega(MagicMock(), "pedido-1", ["RL-CD", "RG-CD"])

    assert sorted(grupos["RL-CD"]) == ["TRL-QSN", "TRL-SMA"]
    assert grupos["RG-CD"] == ["RG-INT"]
