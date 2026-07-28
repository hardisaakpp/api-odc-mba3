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
        assert isinstance(resultado, dict)
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
        assert resultado is not None
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


class TestGetOrFetchProductosBatch:
    """
    get_or_fetch_productos_batch: resuelve varios SKUs con UNA sola llamada
    get_items_batch en vez de N get_or_fetch_producto_info. Los que ya están en
    cache no tocan el middleware; los que el batch no resuelve (flag apagada,
    batch no disponible, o el código no vino en el resultado) caen a
    get_or_fetch_producto_info uno por uno — el camino de siempre.
    """

    @staticmethod
    def _service():
        service = SAPService()
        service.enabled = True
        return service

    def test_deshabilitado_retorna_none_para_todos(self):
        service = SAPService()
        service.enabled = False
        assert service.get_or_fetch_productos_batch(["A1", "B2"]) == {"A1": None, "B2": None}

    def test_lista_vacia_retorna_vacio(self):
        assert self._service().get_or_fetch_productos_batch([]) == {}

    def test_cache_hit_no_llama_middleware(self):
        service = self._service()
        with patch("src.database.services.sap_service.get_db_connection"), \
             patch("src.database.services.sap_service.ProductoSAPRepository"), \
             patch.object(service, "_consultar_cache", return_value={"sku": "A1", "item_code": "A1"}), \
             patch("src.database.services.sap_service.SAPServiceLayerClient") as mock_mw:
            resultado = service.get_or_fetch_productos_batch(["A1"])
        assert resultado["A1"] == {"sku": "A1", "item_code": "A1"}
        mock_mw.assert_not_called()

    def test_cache_miss_resuelve_via_batch_middleware(self):
        service = self._service()
        with patch("src.database.services.sap_service.get_db_connection"), \
             patch("src.database.services.sap_service.ProductoSAPRepository"), \
             patch.object(service, "_consultar_cache", return_value=None), \
             patch("src.database.services.sap_service.USE_MIDDLEWARE_PRODUCTO_INFO", True), \
             patch("src.database.services.sap_service.SAPServiceLayerClient") as mock_mw, \
             patch.object(service, "_procesar_sap_info", return_value={"sku": "A1", "item_code": "A1"}) as mock_procesar:
            mock_mw.return_value.get_items_batch.return_value = {
                "A1": {"ItemCode": "A1", "ItemName": "Prod", "U_IXX_PACK": "X3", "ItmsGrpNam": "GRUPO", "Valid": "tYES"}
            }
            resultado = service.get_or_fetch_productos_batch(["A1"])
        mock_mw.return_value.get_items_batch.assert_called_once_with(["A1"])
        assert mock_procesar.call_args.args[0] == "A1"
        assert mock_procesar.call_args.args[1]["validFor"] == "Y"
        assert resultado["A1"] == {"sku": "A1", "item_code": "A1"}

    def test_flag_apagada_cae_directo_a_fallback_individual(self):
        service = self._service()
        with patch("src.database.services.sap_service.get_db_connection"), \
             patch("src.database.services.sap_service.ProductoSAPRepository"), \
             patch.object(service, "_consultar_cache", return_value=None), \
             patch("src.database.services.sap_service.USE_MIDDLEWARE_PRODUCTO_INFO", False), \
             patch("src.database.services.sap_service.SAPServiceLayerClient") as mock_mw, \
             patch.object(service, "get_or_fetch_producto_info", return_value={"sku": "A1"}) as mock_individual:
            resultado = service.get_or_fetch_productos_batch(["A1"])
        mock_mw.assert_not_called()
        mock_individual.assert_called_once_with("A1", False)
        assert resultado["A1"] == {"sku": "A1"}

    def test_batch_confirmado_no_disponible_va_directo_a_openquery_sin_reintentar_middleware(self):
        """
        items is None (batch confirmó middleware caído/saturado): NO debe reintentar
        el middleware por SKU (eso pagaría de nuevo la espera de QueueAfterSeconds bajo
        SAP saturado) — va directo a OPENQUERY para todos los pendientes.
        """
        service = self._service()
        with patch("src.database.services.sap_service.get_db_connection"), \
             patch("src.database.services.sap_service.ProductoSAPRepository"), \
             patch.object(service, "_consultar_cache", return_value=None), \
             patch("src.database.services.sap_service.USE_MIDDLEWARE_PRODUCTO_INFO", True), \
             patch("src.database.services.sap_service.SAPServiceLayerClient") as mock_mw, \
             patch.object(service, "sap_client") as mock_oq, \
             patch.object(service, "get_or_fetch_producto_info") as mock_individual, \
             patch.object(service, "_procesar_sap_info", return_value={"sku": "A1"}) as mock_procesar:
            mock_mw.return_value.get_items_batch.return_value = None
            mock_oq.get_producto_info.return_value = {"ItemCode": "A1"}
            resultado = service.get_or_fetch_productos_batch(["A1", "B2"])
        mock_individual.assert_not_called()
        assert mock_oq.get_producto_info.call_count == 2
        mock_oq.get_producto_info.assert_any_call("A1")
        mock_oq.get_producto_info.assert_any_call("B2")
        assert mock_procesar.call_count == 2
        assert resultado["A1"] == {"sku": "A1"}

    def test_codigo_ausente_del_batch_cae_a_fallback_individual_los_demas_no(self):
        service = self._service()
        with patch("src.database.services.sap_service.get_db_connection"), \
             patch("src.database.services.sap_service.ProductoSAPRepository"), \
             patch.object(service, "_consultar_cache", return_value=None), \
             patch("src.database.services.sap_service.USE_MIDDLEWARE_PRODUCTO_INFO", True), \
             patch("src.database.services.sap_service.SAPServiceLayerClient") as mock_mw, \
             patch.object(service, "_procesar_sap_info", return_value={"sku": "A1"}), \
             patch.object(service, "get_or_fetch_producto_info", return_value={"sku": "B2"}) as mock_individual:
            mock_mw.return_value.get_items_batch.return_value = {
                "A1": {"ItemCode": "A1", "ItemName": "Prod", "Valid": "tYES"}
                # B2 ausente: ese chunk no lo resolvió
            }
            resultado = service.get_or_fetch_productos_batch(["A1", "B2"])
        mock_individual.assert_called_once_with("B2", False)
        assert resultado["A1"] == {"sku": "A1"}
        assert resultado["B2"] == {"sku": "B2"}

    def test_item_no_existe_en_batch_se_procesa_como_no_encontrado(self):
        service = self._service()
        with patch("src.database.services.sap_service.get_db_connection"), \
             patch("src.database.services.sap_service.ProductoSAPRepository"), \
             patch.object(service, "_consultar_cache", return_value=None), \
             patch("src.database.services.sap_service.USE_MIDDLEWARE_PRODUCTO_INFO", True), \
             patch("src.database.services.sap_service.SAPServiceLayerClient") as mock_mw, \
             patch.object(service, "get_or_fetch_producto_info") as mock_individual:
            mock_mw.return_value.get_items_batch.return_value = {
                "XX": {"_error": True, "_error_type": "no_existe", "_error_message": "no existe"}
            }
            resultado = service.get_or_fetch_productos_batch(["XX"])
        mock_individual.assert_not_called()  # no_existe es definitivo, no cae a fallback individual
        assert resultado["XX"] == {"_error": True, "_error_type": "no_existe", "_sku": "XX", "_item_code_sap": None}
