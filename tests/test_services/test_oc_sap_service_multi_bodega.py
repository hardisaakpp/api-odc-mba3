"""
Tests para la propagación de tiendas_destino_filtro en OCSAPService: cuando un pedido
tiene 2 ODC (una por bodega/marca, Fase 2 de PYTD002), cada una debe acotar sus
Solicitudes de Transferencia solo a sus propias tiendas.
"""

from unittest.mock import MagicMock, patch

from src.database.services.oc_sap_service import OCSAPService


def test_crear_solicitudes_transferencia_oc_propaga_tiendas_destino_filtro():
    oc_cabecera = {"codigo_bodega": "RL-CD"}
    result = {}
    with patch("src.database.services.stock_transfer_service.StockTransferService") as mock_sts_cls:
        mock_sts_cls.return_value.crear_solicitudes_transferencia_desde_pedido.return_value = {"success": True, "transferencias_creadas": 1}

        OCSAPService._crear_solicitudes_transferencia_oc(
            oc_id="oc-1",
            oc_cabecera=oc_cabecera,
            doc_num=123,
            serie_itr=None,
            oc_repo=MagicMock(),
            pedido_id="pedido-1",
            result=result,
            tiendas_destino_filtro=["TRL-QSN"],
        )

    llamada = mock_sts_cls.return_value.crear_solicitudes_transferencia_desde_pedido.call_args
    assert llamada.kwargs["tiendas_destino_filtro"] == ["TRL-QSN"]
    assert llamada.kwargs["bodega_origen"] == "RL-CD"


def test_crear_solicitudes_transferencia_oc_sin_filtro_no_cambia_comportamiento():
    oc_cabecera = {"codigo_bodega": "RL-CD"}
    result = {}
    with patch("src.database.services.stock_transfer_service.StockTransferService") as mock_sts_cls:
        mock_sts_cls.return_value.crear_solicitudes_transferencia_desde_pedido.return_value = {"success": True, "transferencias_creadas": 3}

        OCSAPService._crear_solicitudes_transferencia_oc(
            oc_id="oc-1",
            oc_cabecera=oc_cabecera,
            doc_num=123,
            serie_itr=None,
            oc_repo=MagicMock(),
            pedido_id="pedido-1",
            result=result,
        )

    llamada = mock_sts_cls.return_value.crear_solicitudes_transferencia_desde_pedido.call_args
    assert llamada.kwargs["tiendas_destino_filtro"] is None


def test_crear_solicitudes_transferencia_oc_propaga_process_id():
    """Fase 2 (tiempo real): process_id debe llegar hasta crear_solicitudes_
    transferencia_desde_pedido para que registre el alias oc_id<->process_id
    (ver ProcesoEstadoService.crear_alias_oc) y una reconciliación posterior
    pueda corregir el snapshot congelado del proceso SAP original."""
    oc_cabecera = {"codigo_bodega": "RL-CD"}
    result = {}
    with patch("src.database.services.stock_transfer_service.StockTransferService") as mock_sts_cls:
        mock_sts_cls.return_value.crear_solicitudes_transferencia_desde_pedido.return_value = {"success": True, "transferencias_creadas": 1}

        OCSAPService._crear_solicitudes_transferencia_oc(
            oc_id="oc-1",
            oc_cabecera=oc_cabecera,
            doc_num=123,
            serie_itr=None,
            oc_repo=MagicMock(),
            pedido_id="pedido-1",
            result=result,
            process_id="proceso-sap-abc123",
        )

    llamada = mock_sts_cls.return_value.crear_solicitudes_transferencia_desde_pedido.call_args
    assert llamada.kwargs["process_id"] == "proceso-sap-abc123"


def test_crear_solicitudes_transferencia_oc_sin_process_id_no_cambia_comportamiento():
    oc_cabecera = {"codigo_bodega": "RL-CD"}
    result = {}
    with patch("src.database.services.stock_transfer_service.StockTransferService") as mock_sts_cls:
        mock_sts_cls.return_value.crear_solicitudes_transferencia_desde_pedido.return_value = {"success": True, "transferencias_creadas": 1}

        OCSAPService._crear_solicitudes_transferencia_oc(
            oc_id="oc-1",
            oc_cabecera=oc_cabecera,
            doc_num=123,
            serie_itr=None,
            oc_repo=MagicMock(),
            pedido_id="pedido-1",
            result=result,
        )

    llamada = mock_sts_cls.return_value.crear_solicitudes_transferencia_desde_pedido.call_args
    assert llamada.kwargs["process_id"] is None


def test_resolver_tiendas_destino_filtro_none_si_pedido_tiene_una_sola_oc():
    oc_repo = MagicMock()
    oc_repo.get_existing_cabecera.return_value = {"pedido_id": "pedido-1", "codigo_bodega": "RL-CD"}
    oc_repo.get_by_pedido_id.return_value = [{"oc_id": "oc-1"}]  # solo esta

    resultado = OCSAPService.resolver_tiendas_destino_filtro(oc_repo, "oc-1")

    assert resultado is None


def test_resolver_tiendas_destino_filtro_acota_a_su_bodega_si_pedido_mixto():
    oc_repo = MagicMock()
    oc_repo.get_existing_cabecera.return_value = {"pedido_id": "pedido-1", "codigo_bodega": "RL-CD"}
    oc_repo.get_by_pedido_id.return_value = [{"oc_id": "oc-1"}, {"oc_id": "oc-2"}]  # 2 ODC -> pedido mixto
    oc_repo.conn = MagicMock()

    with patch(
        "src.database.services.pedido_oc_service.PedidoOCService._tiendas_por_bodega",
        return_value={"RL-CD": ["TRL-QSN", "TRL-SMA"]},
    ) as mock_tiendas:
        resultado = OCSAPService.resolver_tiendas_destino_filtro(oc_repo, "oc-1")

    mock_tiendas.assert_called_once_with(oc_repo.conn, "pedido-1", ["RL-CD"])
    assert resultado == ["TRL-QSN", "TRL-SMA"]


def test_resolver_tiendas_destino_filtro_none_si_falla_no_bloquea():
    oc_repo = MagicMock()
    oc_repo.get_existing_cabecera.side_effect = Exception("db down")

    resultado = OCSAPService.resolver_tiendas_destino_filtro(oc_repo, "oc-1")

    assert resultado is None
