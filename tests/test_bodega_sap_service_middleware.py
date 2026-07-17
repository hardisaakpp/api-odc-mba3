"""
Tests de los dispatchers middleware/OPENQUERY en BodegaSAPService.

Cubre la selección de vía según USE_MIDDLEWARE_WAREHOUSES y el fallback
a OPENQUERY cuando el middleware no está disponible.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from src.database.services.bodega_sap_service import BodegaSAPService


def _service() -> Any:
    service = BodegaSAPService.__new__(BodegaSAPService)
    service.sap_client = MagicMock()
    service.sap_sl_client = MagicMock()
    return service


class TestConsultarBodegaMiddleware:
    def test_bodega_encontrada(self):
        service = _service()
        service.sap_sl_client.validate_warehouses_batch.return_value = {
            "warehouses": [{"whsCode": "RL-CD", "exists": True, "whsName": "ROLAND CD"}]
        }
        disponible, info = service._consultar_bodega_middleware("RL-CD")
        assert disponible is True
        assert info == {"WhsCode": "RL-CD", "WhsName": "ROLAND CD"}

    def test_bodega_no_existe_es_disponible_pero_sin_info(self):
        service = _service()
        service.sap_sl_client.validate_warehouses_batch.return_value = {
            "warehouses": [{"whsCode": "NOEXISTE", "exists": False, "errorType": "not_found"}]
        }
        disponible, info = service._consultar_bodega_middleware("NOEXISTE")
        assert disponible is True
        assert info is None

    def test_middleware_no_disponible(self):
        service = _service()
        service.sap_sl_client.validate_warehouses_batch.return_value = None
        disponible, info = service._consultar_bodega_middleware("RL-CD")
        assert disponible is False
        assert info is None

    def test_error_de_conexion_por_elemento(self):
        service = _service()
        service.sap_sl_client.validate_warehouses_batch.return_value = {
            "warehouses": [{"whsCode": "RL-CD", "errorType": "connection_error"}]
        }
        disponible, info = service._consultar_bodega_middleware("RL-CD")
        assert disponible is False


class TestConsultarBodegaSapDispatcher:
    def test_flag_apagado_usa_openquery_directo(self):
        service = _service()
        service.sap_client.get_bodega_info.return_value = {"WhsCode": "RL-CD", "WhsName": "X"}
        with patch("src.database.services.bodega_sap_service.USE_MIDDLEWARE_WAREHOUSES", False):
            resultado = service._consultar_bodega_sap("RL-CD")
        assert resultado == {"WhsCode": "RL-CD", "WhsName": "X"}
        service.sap_sl_client.validate_warehouses_batch.assert_not_called()

    def test_flag_encendido_usa_middleware(self):
        service = _service()
        service.sap_sl_client.validate_warehouses_batch.return_value = {
            "warehouses": [{"whsCode": "RL-CD", "exists": True, "whsName": "X"}]
        }
        with patch("src.database.services.bodega_sap_service.USE_MIDDLEWARE_WAREHOUSES", True):
            resultado = service._consultar_bodega_sap("RL-CD")
        assert resultado == {"WhsCode": "RL-CD", "WhsName": "X"}
        service.sap_client.get_bodega_info.assert_not_called()

    def test_middleware_caido_hace_fallback_a_openquery(self):
        service = _service()
        service.sap_sl_client.validate_warehouses_batch.return_value = None
        service.sap_client.get_bodega_info.return_value = {"WhsCode": "RL-CD", "WhsName": "X"}
        with patch("src.database.services.bodega_sap_service.USE_MIDDLEWARE_WAREHOUSES", True):
            resultado = service._consultar_bodega_sap("RL-CD")
        assert resultado == {"WhsCode": "RL-CD", "WhsName": "X"}
        service.sap_client.get_bodega_info.assert_called_once()


class TestObtenerTodasBodegasSapDispatcher:
    def test_flag_encendido_usa_middleware(self):
        service = _service()
        service.sap_sl_client.get_all_warehouses.return_value = [{"WhsCode": "RL-CD", "WhsName": "X"}]
        with patch("src.database.services.bodega_sap_service.USE_MIDDLEWARE_WAREHOUSES", True):
            resultado = service._obtener_todas_bodegas_sap()
        assert resultado == [{"WhsCode": "RL-CD", "WhsName": "X"}]
        service.sap_client.get_todas_bodegas.assert_not_called()

    def test_middleware_caido_hace_fallback(self):
        service = _service()
        service.sap_sl_client.get_all_warehouses.return_value = None
        service.sap_client.get_todas_bodegas.return_value = [{"WhsCode": "RL-CD", "WhsName": "X"}]
        with patch("src.database.services.bodega_sap_service.USE_MIDDLEWARE_WAREHOUSES", True):
            resultado = service._obtener_todas_bodegas_sap()
        assert resultado == [{"WhsCode": "RL-CD", "WhsName": "X"}]


class TestConsultarSapCodigosDispatcher:
    @staticmethod
    def _repo():
        return MagicMock()

    def test_flag_apagado_usa_loop_openquery(self):
        service = _service()
        service.sap_client.get_bodega_info.return_value = {"WhsName": "X"}
        with patch("src.database.services.bodega_sap_service.USE_MIDDLEWARE_WAREHOUSES", False):
            resultado, nuevos = service._consultar_sap_codigos(self._repo(), ["RL-CD"])
        assert resultado["RL-CD"]["encontrado"] is True
        assert resultado["RL-CD"]["fuente"] == "sap"
        service.sap_sl_client.validate_warehouses_batch.assert_not_called()

    def test_flag_encendido_usa_batch_unico(self):
        service = _service()
        repo = self._repo()
        service.sap_sl_client.validate_warehouses_batch.return_value = {
            "warehouses": [
                {"whsCode": "RL-CD", "exists": True, "whsName": "X"},
                {"whsCode": "NOEXISTE", "exists": False, "errorType": "not_found"},
            ]
        }
        with patch("src.database.services.bodega_sap_service.USE_MIDDLEWARE_WAREHOUSES", True):
            resultado, nuevos = service._consultar_sap_codigos(repo, ["RL-CD", "NOEXISTE"])
        assert resultado["RL-CD"]["encontrado"] is True
        assert resultado["RL-CD"]["fuente"] == "middleware"
        assert resultado["NOEXISTE"]["encontrado"] is False
        assert nuevos == ["RL-CD"]
        service.sap_client.get_bodega_info.assert_not_called()

    def test_middleware_caido_hace_fallback_a_loop(self):
        service = _service()
        service.sap_sl_client.validate_warehouses_batch.return_value = None
        service.sap_client.get_bodega_info.return_value = {"WhsName": "X"}
        with patch("src.database.services.bodega_sap_service.USE_MIDDLEWARE_WAREHOUSES", True):
            resultado, nuevos = service._consultar_sap_codigos(self._repo(), ["RL-CD"])
        assert resultado["RL-CD"]["encontrado"] is True
        assert resultado["RL-CD"]["fuente"] == "sap"
