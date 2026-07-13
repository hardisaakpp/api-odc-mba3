"""
Tests de la migración a middleware de SAPService.get_or_fetch_producto_info
(cache-miss): dispatcher `_consultar_producto_sap` con flag
USE_MIDDLEWARE_PRODUCTO_INFO y fallback a OPENQUERY.

Punto crítico: aquí None es una respuesta VÁLIDA ("no existe en SAP",
definitiva) — el sentinel _SIN_RESPUESTA_MIDDLEWARE distingue ese caso del
"middleware caído" que sí debe caer a OPENQUERY.
"""

from unittest.mock import patch

from src.database.services.sap_service import SAPService, _SIN_RESPUESTA_MIDDLEWARE


def _item_middleware(valid="tYES", grupo="R-MEDIAS"):
    return {
        "ItemCode": "5-0012.9",
        "ItemName": "DEPORTIVO C. TOBILLERA MEDIA FELPA SURTIDO X3",
        "Valid": valid,
        "U_IXX_PACK": "X3",
        "ItmsGrpCod": 103,
        "ItmsGrpNam": grupo,
    }


class TestConsultarProductoViaMiddleware:
    def test_item_activo_mapea_formato_openquery(self):
        with patch("src.database.services.sap_service.SAPServiceLayerClient") as mock_cls:
            mock_cls.return_value.get_item.return_value = _item_middleware()
            resultado = SAPService._consultar_producto_via_middleware("5-0012.9")
        assert resultado == {
            "ItemCode": "5-0012.9",
            "ItemName": "DEPORTIVO C. TOBILLERA MEDIA FELPA SURTIDO X3",
            "U_IXX_PACK": "X3",
            "ItmsGrpNam": "R-MEDIAS",
            "validFor": "Y",
        }

    def test_item_inactivo_mapea_validfor_n(self):
        with patch("src.database.services.sap_service.SAPServiceLayerClient") as mock_cls:
            mock_cls.return_value.get_item.return_value = _item_middleware(valid="tNO")
            resultado = SAPService._consultar_producto_via_middleware("5-0012.9")
        assert resultado["validFor"] == "N"

    def test_404_confirmado_retorna_none_definitivo(self):
        with patch("src.database.services.sap_service.SAPServiceLayerClient") as mock_cls:
            mock_cls.return_value.get_item.return_value = {
                "_error": True, "_error_type": "no_existe", "_error_message": "no existe",
            }
            assert SAPService._consultar_producto_via_middleware("XX") is None

    def test_sin_conexion_retorna_sentinel(self):
        with patch("src.database.services.sap_service.SAPServiceLayerClient") as mock_cls:
            mock_cls.return_value.get_item.return_value = None
            assert SAPService._consultar_producto_via_middleware("XX") is _SIN_RESPUESTA_MIDDLEWARE

    def test_error_generico_retorna_sentinel(self):
        with patch("src.database.services.sap_service.SAPServiceLayerClient") as mock_cls:
            mock_cls.return_value.get_item.return_value = {
                "_error": True, "_error_type": "error", "_error_message": "boom",
            }
            assert SAPService._consultar_producto_via_middleware("XX") is _SIN_RESPUESTA_MIDDLEWARE


class TestConsultarProductoSap:
    def test_middleware_resuelve_no_llama_openquery(self):
        service = SAPService()
        with patch(
            "src.database.services.sap_service.USE_MIDDLEWARE_PRODUCTO_INFO", True
        ), patch(
            "src.database.services.sap_service.SAPServiceLayerClient"
        ) as mock_mw, patch.object(service, "sap_client") as mock_oq:
            mock_mw.return_value.get_item.return_value = _item_middleware()
            resultado = service._consultar_producto_sap("5-0012.9")
        assert resultado["ItmsGrpNam"] == "R-MEDIAS"
        mock_oq.get_producto_info.assert_not_called()

    def test_404_definitivo_no_va_a_openquery(self):
        """No existe en SAP (confirmado por middleware) NO debe disparar fallback."""
        service = SAPService()
        with patch(
            "src.database.services.sap_service.USE_MIDDLEWARE_PRODUCTO_INFO", True
        ), patch(
            "src.database.services.sap_service.SAPServiceLayerClient"
        ) as mock_mw, patch.object(service, "sap_client") as mock_oq:
            mock_mw.return_value.get_item.return_value = {
                "_error": True, "_error_type": "no_existe",
            }
            resultado = service._consultar_producto_sap("XX")
        assert resultado is None
        mock_oq.get_producto_info.assert_not_called()

    def test_middleware_caido_hace_fallback_a_openquery(self):
        service = SAPService()
        with patch(
            "src.database.services.sap_service.USE_MIDDLEWARE_PRODUCTO_INFO", True
        ), patch(
            "src.database.services.sap_service.SAPServiceLayerClient"
        ) as mock_mw, patch.object(service, "sap_client") as mock_oq:
            mock_mw.return_value.get_item.return_value = None
            mock_oq.get_producto_info.return_value = {"ItemCode": "5-0012.9"}
            resultado = service._consultar_producto_sap("5-0012.9")
        assert resultado == {"ItemCode": "5-0012.9"}
        mock_oq.get_producto_info.assert_called_once_with("5-0012.9")

    def test_flag_apagada_usa_solo_openquery(self):
        service = SAPService()
        with patch(
            "src.database.services.sap_service.USE_MIDDLEWARE_PRODUCTO_INFO", False
        ), patch(
            "src.database.services.sap_service.SAPServiceLayerClient"
        ) as mock_mw, patch.object(service, "sap_client") as mock_oq:
            mock_oq.get_producto_info.return_value = None
            service._consultar_producto_sap("XX")
        mock_mw.assert_not_called()
        mock_oq.get_producto_info.assert_called_once_with("XX")
