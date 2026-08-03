"""
Tests del dispatcher de búsqueda de SKU exacto (middleware vs. OPENQUERY).
"""

import asyncio
from unittest.mock import patch

from src.endpoints.cruce_productos import (
    _mapear_item_middleware_a_producto,
    _buscar_sku_via_middleware,
)


class TestMapearItemMiddlewareAProducto:
    def test_item_activo(self):
        item = {
            "ItemCode": "A1", "ItemName": "Producto", "U_IXX_PACK": "X1",
            "ItmsGrpCod": 103, "CardCode": "P123", "Valid": "tYES",
        }
        producto = _mapear_item_middleware_a_producto(item, "A1")
        assert producto["estado"] == "activo"
        assert producto["pack"] == "X1"
        assert producto["card_code"] == "P123"
        # valid_for crudo normalizado al formato del canal OPENQUERY
        assert producto["valid_for"] == "Y"

    def test_item_inactivo(self):
        item = {"ItemCode": "A1", "ItemName": "Producto", "Valid": "tNO"}
        producto = _mapear_item_middleware_a_producto(item, "A1")
        assert producto["estado"] == "inactivo"
        assert producto["valid_for"] == "N"

    def test_campos_ausentes_usan_defaults(self):
        producto = _mapear_item_middleware_a_producto({}, "A1")
        assert producto["codigo"] == "A1"
        assert producto["nombre"] == ""
        assert producto["pack"] == ""
        assert producto["group_code"] is None
        assert producto["card_code"] is None


class TestBuscarSkuViaMiddleware:
    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def test_item_encontrado(self):
        item = {"ItemCode": "A1", "ItemName": "Producto", "Valid": "tYES"}
        with patch("src.endpoints.cruce_productos.SAPServiceLayerClient") as MockClient:
            MockClient.return_value.get_item.return_value = item
            resultado = self._run(_buscar_sku_via_middleware("A1"))
        assert resultado["status"] == "success"
        assert resultado["data"]["codigo"] == "A1"

    def test_item_no_existe_no_hace_fallback(self):
        with patch("src.endpoints.cruce_productos.SAPServiceLayerClient") as MockClient:
            MockClient.return_value.get_item.return_value = {
                "_error": True, "_error_type": "no_existe",
            }
            resultado = self._run(_buscar_sku_via_middleware("SKU-FALSO"))
        assert resultado["status"] == "not_found"

    def test_sin_conexion_retorna_none_para_fallback(self):
        with patch("src.endpoints.cruce_productos.SAPServiceLayerClient") as MockClient:
            MockClient.return_value.get_item.return_value = None
            resultado = self._run(_buscar_sku_via_middleware("A1"))
        assert resultado is None

    def test_error_generico_retorna_none_para_fallback(self):
        with patch("src.endpoints.cruce_productos.SAPServiceLayerClient") as MockClient:
            MockClient.return_value.get_item.return_value = {
                "_error": True, "_error_type": "error", "_error_message": "boom",
            }
            resultado = self._run(_buscar_sku_via_middleware("A1"))
        assert resultado is None
