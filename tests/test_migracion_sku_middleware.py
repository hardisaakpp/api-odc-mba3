"""
Tests de la migración a middleware de los dos puntos que seguían 100% en
OPENQUERY (patrón dispatcher: middleware primero, fallback a OPENQUERY):

1. Validación de existencia de SKU al reasignarlo en una línea de OC
   (`ordenes_compra._sku_existe_en_sap`).
2. Enriquecimiento de detalles de pedido (descripcion_sap/pack) que hacía
   una llamada OPENQUERY por cada SKU único
   (`pedido_service._consultar_productos_sap`).
"""

from unittest.mock import patch

from src.endpoints.ordenes_compra import _sku_existe_en_sap, _sku_existe_via_middleware
from src.database.services.pedido_service import PedidoService


def _item_ok(codigo="SKU1", nombre="Producto", pack="X3"):
    return {"ItemCode": codigo, "ItemName": nombre, "U_IXX_PACK": pack}


def _item_no_existe():
    return {"_error": True, "_error_type": "no_existe", "_error_message": "no existe"}


def _item_error_generico():
    return {"_error": True, "_error_type": "error", "_error_message": "boom"}


class TestSkuExisteViaMiddleware:
    def test_item_encontrado_retorna_true(self):
        with patch(
            "src.endpoints.ordenes_compra.SAPServiceLayerClient"
        ) as mock_cls:
            mock_cls.return_value.get_item.return_value = _item_ok()
            assert _sku_existe_via_middleware("SKU1") is True

    def test_404_confirmado_retorna_false(self):
        with patch(
            "src.endpoints.ordenes_compra.SAPServiceLayerClient"
        ) as mock_cls:
            mock_cls.return_value.get_item.return_value = _item_no_existe()
            assert _sku_existe_via_middleware("SKU1") is False

    def test_sin_conexion_retorna_none(self):
        with patch(
            "src.endpoints.ordenes_compra.SAPServiceLayerClient"
        ) as mock_cls:
            mock_cls.return_value.get_item.return_value = None
            assert _sku_existe_via_middleware("SKU1") is None

    def test_error_generico_retorna_none(self):
        with patch(
            "src.endpoints.ordenes_compra.SAPServiceLayerClient"
        ) as mock_cls:
            mock_cls.return_value.get_item.return_value = _item_error_generico()
            assert _sku_existe_via_middleware("SKU1") is None


class TestSkuExisteEnSap:
    def test_middleware_resuelve_no_llama_openquery(self):
        with patch(
            "src.endpoints.ordenes_compra.USE_MIDDLEWARE_SKU_LOOKUP", True
        ), patch(
            "src.endpoints.ordenes_compra.SAPServiceLayerClient"
        ) as mock_mw, patch(
            "src.endpoints.ordenes_compra.SAPClient"
        ) as mock_oq:
            mock_mw.return_value.get_item.return_value = _item_ok()
            assert _sku_existe_en_sap("SKU1") is True
            mock_oq.assert_not_called()

    def test_middleware_caido_hace_fallback_a_openquery(self):
        with patch(
            "src.endpoints.ordenes_compra.USE_MIDDLEWARE_SKU_LOOKUP", True
        ), patch(
            "src.endpoints.ordenes_compra.SAPServiceLayerClient"
        ) as mock_mw, patch(
            "src.endpoints.ordenes_compra.SAPClient"
        ) as mock_oq:
            mock_mw.return_value.get_item.return_value = None
            mock_oq.return_value.get_producto_info.return_value = {"ItemCode": "SKU1"}
            assert _sku_existe_en_sap("SKU1") is True
            mock_oq.return_value.get_producto_info.assert_called_once_with("SKU1")

    def test_flag_apagada_usa_solo_openquery(self):
        with patch(
            "src.endpoints.ordenes_compra.USE_MIDDLEWARE_SKU_LOOKUP", False
        ), patch(
            "src.endpoints.ordenes_compra.SAPServiceLayerClient"
        ) as mock_mw, patch(
            "src.endpoints.ordenes_compra.SAPClient"
        ) as mock_oq:
            mock_oq.return_value.get_producto_info.return_value = None
            assert _sku_existe_en_sap("SKU1") is False
            mock_mw.assert_not_called()


class TestConsultarProductosSapPedido:
    def test_middleware_resuelve_todos_sin_openquery(self):
        service = PedidoService()
        with patch(
            "src.database.services.pedido_service.USE_MIDDLEWARE_SKU_LOOKUP", True
        ), patch(
            "src.database.services.pedido_service.SAPServiceLayerClient"
        ) as mock_mw, patch(
            "src.database.services.pedido_service.SAPClient"
        ) as mock_oq:
            mock_mw.return_value.get_item.side_effect = [
                _item_ok("A1", "Prod A", "X1"),
                _item_ok("B2", "Prod B", "X2"),
            ]
            resultado = service._consultar_productos_sap(["A1", "B2"])
        assert resultado["A1"]["ItemName"] == "Prod A"
        assert resultado["B2"]["U_IXX_PACK"] == "X2"
        mock_oq.assert_not_called()

    def test_404_confirmado_no_va_a_openquery(self):
        service = PedidoService()
        with patch(
            "src.database.services.pedido_service.USE_MIDDLEWARE_SKU_LOOKUP", True
        ), patch(
            "src.database.services.pedido_service.SAPServiceLayerClient"
        ) as mock_mw, patch(
            "src.database.services.pedido_service.SAPClient"
        ) as mock_oq:
            mock_mw.return_value.get_item.return_value = _item_no_existe()
            resultado = service._consultar_productos_sap(["NOEXISTE"])
        assert resultado == {}
        mock_oq.assert_not_called()

    def test_middleware_caido_todo_el_resto_va_a_openquery(self):
        """Al primer fallo de conexión, no se insiste código por código."""
        service = PedidoService()
        with patch(
            "src.database.services.pedido_service.USE_MIDDLEWARE_SKU_LOOKUP", True
        ), patch(
            "src.database.services.pedido_service.SAPServiceLayerClient"
        ) as mock_mw, patch(
            "src.database.services.pedido_service.SAPClient"
        ) as mock_oq:
            mock_mw.return_value.get_item.side_effect = [
                _item_ok("A1", "Prod A", "X1"),
                None,  # cae el middleware en el segundo código
            ]
            mock_oq.return_value.get_productos_info_batch.return_value = {
                "B2": {"ItemCode": "B2", "ItemName": "Prod B", "U_IXX_PACK": "X2"},
                "C3": {"ItemCode": "C3", "ItemName": "Prod C", "U_IXX_PACK": "X3"},
            }
            resultado = service._consultar_productos_sap(["A1", "B2", "C3"])

        assert mock_mw.return_value.get_item.call_count == 2  # no insistió con C3
        mock_oq.return_value.get_productos_info_batch.assert_called_once_with(["B2", "C3"])
        assert set(resultado.keys()) == {"A1", "B2", "C3"}

    def test_error_generico_solo_ese_codigo_va_a_openquery(self):
        service = PedidoService()
        with patch(
            "src.database.services.pedido_service.USE_MIDDLEWARE_SKU_LOOKUP", True
        ), patch(
            "src.database.services.pedido_service.SAPServiceLayerClient"
        ) as mock_mw, patch(
            "src.database.services.pedido_service.SAPClient"
        ) as mock_oq:
            mock_mw.return_value.get_item.side_effect = [
                _item_error_generico(),
                _item_ok("B2", "Prod B", "X2"),
            ]
            mock_oq.return_value.get_productos_info_batch.return_value = {}
            service._consultar_productos_sap(["A1", "B2"])
        mock_oq.return_value.get_productos_info_batch.assert_called_once_with(["A1"])

    def test_flag_apagada_usa_solo_openquery(self):
        service = PedidoService()
        with patch(
            "src.database.services.pedido_service.USE_MIDDLEWARE_SKU_LOOKUP", False
        ), patch(
            "src.database.services.pedido_service.SAPServiceLayerClient"
        ) as mock_mw, patch(
            "src.database.services.pedido_service.SAPClient"
        ) as mock_oq:
            mock_oq.return_value.get_productos_info_batch.return_value = {}
            service._consultar_productos_sap(["A1"])
        mock_mw.assert_not_called()
        mock_oq.return_value.get_productos_info_batch.assert_called_once_with(["A1"])
