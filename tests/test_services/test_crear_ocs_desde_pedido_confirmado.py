"""
Tests para PedidoOCService.crear_ocs_desde_pedido_confirmado: 1 ODC en el caso
normal (comportamiento histórico sin cambios) vs. 2 ODC cuando el pedido mezcla
tiendas ROLAND y REGIONS (origen_traslado_detectado con 2 códigos, Fase 2 de
PYTD002).
"""

from unittest.mock import MagicMock, patch

from src.database.pedido_estados import ESTADO_PEDIDO_CONFIRMADO
from src.database.services.pedido_oc_service import PedidoOCService

BODEGA_POR_CODIGO = {
    "TRL-QSN": "RL-CD",
    "RG-INT": "RG-CD",
}


def _procesamiento(pedido_detalle_id, item_code, cantidad_sap=10.0):
    return {
        "pedido_detalle_id": pedido_detalle_id,
        "item_code_sap": item_code,
        "producto_homologado": True,
        "cantidad_sap": cantidad_sap,
        "cantidad_original": cantidad_sap,
        "total_linea_sap": cantidad_sap * 2,
        "precio_unitario_sap": 2.0,
        "unidad_sap": "PAR",
    }


def _cabecera(origen_traslado_detectado):
    return {
        "pedido_id": "pedido-1",
        "estado_id": ESTADO_PEDIDO_CONFIRMADO,
        "proveedor_nombre": "TEXTILES EL RAYO S.A.",
        "origen_traslado_detectado": origen_traslado_detectado,
    }


def _patch_comunes(cabecera, procesamientos, productos_distribucion, oc_repo_mock):
    """Contexto común: conexión, PedidoRepository, PedidoSAPProcesamientoRepository,
    OrdenCompraRepository (inyectado), DistribucionConfirmadaRepository, y la
    resolución de bodega por tienda (Fase 1)."""
    mock_ctx = patch("src.database.services.pedido_oc_service.get_db_connection_context")
    mock_pedido_repo_cls = patch("src.database.services.pedido_oc_service.PedidoRepository")
    mock_sap_proc_repo_cls = patch("src.database.services.pedido_oc_service.PedidoSAPProcesamientoRepository")
    mock_oc_repo_cls = patch("src.database.services.pedido_oc_service.OrdenCompraRepository", return_value=oc_repo_mock)
    mock_dist_repo_cls = patch(
        "src.database.repositories.distribucion_confirmada_repository.DistribucionConfirmadaRepository"
    )
    mock_obtener_bodega = patch(
        "src.database.services.stock_transfer_service.StockTransferService.obtener_bodega_de_tienda",
        side_effect=lambda codigo: BODEGA_POR_CODIGO.get(codigo),
    )

    ctx = mock_ctx.start()
    ctx.return_value.__enter__.return_value = MagicMock()

    pedido_repo_cls = mock_pedido_repo_cls.start()
    pedido_repo_cls.return_value.get_pedido_completo.return_value = {"cabecera": cabecera}

    sap_proc_repo_cls = mock_sap_proc_repo_cls.start()
    sap_proc_repo_cls.return_value.get_procesamientos_por_pedido.return_value = procesamientos

    mock_oc_repo_cls.start()

    dist_repo_cls = mock_dist_repo_cls.start()
    dist_repo_cls.return_value.get_version_actual.return_value = 1
    dist_repo_cls.return_value.get_distribucion_completa.return_value = {"productos": productos_distribucion}

    mock_obtener_bodega.start()

    return [mock_ctx, mock_pedido_repo_cls, mock_sap_proc_repo_cls, mock_oc_repo_cls, mock_dist_repo_cls, mock_obtener_bodega]


def _stop_all(patches):
    for p in patches:
        p.stop()


def _oc_repo_mock(existing_oc_id_por_bodega=None):
    """OrdenCompraRepository mock: cada insert_cabecera devuelve un oc_id distinto."""
    mock = MagicMock()
    mock.get_proveedor_from_cliente.return_value = "P-CARD-1"
    mock.find_by_pedido_id.return_value = None
    if existing_oc_id_por_bodega:
        mock.find_by_pedido_id_y_bodega.side_effect = lambda pedido_id, bodega: existing_oc_id_por_bodega.get(bodega)
    else:
        mock.find_by_pedido_id_y_bodega.return_value = None
    oc_ids = iter(["oc-A", "oc-B"])
    mock.insert_cabecera.side_effect = lambda data: next(oc_ids)
    mock.insert_detalles.side_effect = lambda oc_id, detalles: len(detalles)
    mock.get_existing_cabecera.return_value = None
    mock.get_detalles.return_value = None
    return mock


def test_pedido_normal_una_sola_bodega_genera_1_odc():
    cabecera = _cabecera(["RL-CD"])
    procesamientos = [_procesamiento("det-1", "ITEM-1")]
    oc_repo = _oc_repo_mock()

    patches = _patch_comunes(cabecera, procesamientos, [], oc_repo)
    try:
        with patch.object(PedidoOCService, "_determinar_bodega_oc", return_value="RL-CD"):
            service = PedidoOCService()
            resultados = service.crear_ocs_desde_pedido_confirmado("pedido-1")
    finally:
        _stop_all(patches)

    assert len(resultados) == 1
    assert resultados[0]["codigo_bodega"] == "RL-CD"
    assert oc_repo.insert_cabecera.call_count == 1
    oc_repo.find_by_pedido_id_y_bodega.assert_not_called()


def test_pedido_mixto_genera_2_odc_una_por_bodega():
    cabecera = _cabecera(["RL-CD", "RG-CD"])
    procesamientos = [
        _procesamiento("det-1", "ITEM-ROLAND"),
        _procesamiento("det-2", "ITEM-REGIONS"),
    ]
    productos_distribucion = [
        {"pedido_detalle_id": "det-1", "distribuciones": [
            {"tienda_codigo": "TRL-QSN", "cantidad_asignada": 10, "es_bodega": False}
        ]},
        {"pedido_detalle_id": "det-2", "distribuciones": [
            {"tienda_codigo": "RG-INT", "cantidad_asignada": 10, "es_bodega": False}
        ]},
    ]
    oc_repo = _oc_repo_mock()

    patches = _patch_comunes(cabecera, procesamientos, productos_distribucion, oc_repo)
    try:
        service = PedidoOCService()
        resultados = service.crear_ocs_desde_pedido_confirmado("pedido-1")
    finally:
        _stop_all(patches)

    assert len(resultados) == 2
    codigos_bodega = {r["codigo_bodega"] for r in resultados}
    assert codigos_bodega == {"RL-CD", "RG-CD"}
    assert oc_repo.insert_cabecera.call_count == 2
    # find_by_pedido_id (singular, del caso normal) NO debe usarse en el flujo mixto.
    oc_repo.find_by_pedido_id.assert_not_called()
    assert oc_repo.find_by_pedido_id_y_bodega.call_count == 2

    oc_por_bodega = {r["codigo_bodega"]: r for r in resultados}
    # Cada ODC tiene solo 1 línea (la de su propio producto), no las 2.
    assert oc_por_bodega["RL-CD"]["total_lineas"] == 1
    assert oc_por_bodega["RG-CD"]["total_lineas"] == 1
    assert oc_por_bodega["RL-CD"]["tiendas_bodega"] == ["TRL-QSN"]
    assert oc_por_bodega["RG-CD"]["tiendas_bodega"] == ["RG-INT"]


def test_pedido_mixto_upsert_reutiliza_oc_existente_por_bodega():
    cabecera = _cabecera(["RL-CD", "RG-CD"])
    procesamientos = [
        _procesamiento("det-1", "ITEM-ROLAND"),
        _procesamiento("det-2", "ITEM-REGIONS"),
    ]
    productos_distribucion = [
        {"pedido_detalle_id": "det-1", "distribuciones": [
            {"tienda_codigo": "TRL-QSN", "cantidad_asignada": 10, "es_bodega": False}
        ]},
        {"pedido_detalle_id": "det-2", "distribuciones": [
            {"tienda_codigo": "RG-INT", "cantidad_asignada": 10, "es_bodega": False}
        ]},
    ]
    oc_repo = _oc_repo_mock(existing_oc_id_por_bodega={"RL-CD": "oc-existente-RL"})
    oc_repo.delete_detalles.return_value = 0
    oc_repo.update_cabecera.return_value = None

    patches = _patch_comunes(cabecera, procesamientos, productos_distribucion, oc_repo)
    try:
        service = PedidoOCService()
        resultados = service.crear_ocs_desde_pedido_confirmado("pedido-1", upsert=True)
    finally:
        _stop_all(patches)

    oc_por_bodega = {r["codigo_bodega"]: r for r in resultados}
    assert oc_por_bodega["RL-CD"]["oc_id"] == "oc-existente-RL"
    assert oc_por_bodega["RL-CD"]["cabecera_actualizada"] is True
    assert oc_por_bodega["RG-CD"]["cabecera_insertada"] is True
    oc_repo.update_cabecera.assert_called_once()
