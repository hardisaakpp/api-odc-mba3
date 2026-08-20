"""
Tests de la prevalidación batch de ODC (USE_BATCH_VALIDATION).

Cubre el mapeo de la respuesta del middleware al formato interno,
la validación del proveedor, y el fallback a la validación línea por línea
cuando el batch no está disponible.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from src.database.services.oc_sap_service import OCSAPService


def _item_batch(**overrides):
    """Elemento de respuesta batch exitoso; se sobreescribe por caso."""
    base = {
        "itemCode": "5986.NG.8",
        "warehouseCode": "RL-CD",
        "exists": True,
        "purchaseItem": True,
        "valid": True,
        "frozen": False,
        "warehouseConfigured": True,
        "inStock": 120.0,
        "isCommitted": 20.0,
        "errorType": None,
    }
    base.update(overrides)
    return base


class TestValidacionDesdeBatchItem:
    """Mapeo de un elemento batch al formato de validate_item_in_warehouse."""

    def test_item_valido_calcula_stock_disponible(self):
        result = OCSAPService._validacion_desde_batch_item(_item_batch(), "5986.NG.8", "RL-CD")
        assert result["valid"] is True
        assert result["stock"] == 100.0  # inStock - isCommitted
        assert result["errors"] == []

    def test_item_no_existe(self):
        item = _item_batch(errorType="item_not_found", exists=False)
        result = OCSAPService._validacion_desde_batch_item(item, "XXX", "RL-CD")
        assert result["valid"] is False
        assert result["item_exists"] is False
        assert "no existe en SAP" in result["errors"][0]

    def test_bodega_no_configurada(self):
        item = _item_batch(errorType="warehouse_not_found", warehouseConfigured=False)
        result = OCSAPService._validacion_desde_batch_item(item, "5986.NG.8", "RL-CD")
        assert result["valid"] is False
        assert result["item_exists"] is True
        assert "no está configurado en bodega 'RL-CD'" in result["errors"][0]

    def test_no_habilitado_para_compra(self):
        item = _item_batch(purchaseItem=False)
        result = OCSAPService._validacion_desde_batch_item(item, "5986.NG.8", "RL-CD")
        assert result["valid"] is False
        assert "no está habilitado para compra" in result["errors"][0]

    def test_error_de_conexion_parcial(self):
        item = _item_batch(errorType="connection_error")
        result = OCSAPService._validacion_desde_batch_item(item, "5986.NG.8", "RL-CD")
        assert result["valid"] is False
        assert "Error de conexión" in result["errors"][0]

    def test_elemento_ausente_en_respuesta(self):
        result = OCSAPService._validacion_desde_batch_item(None, "5986.NG.8", "RL-CD")
        assert result["valid"] is False
        assert "Error de conexión" in result["errors"][0]

    def test_stock_nulo_se_trata_como_cero(self):
        item = _item_batch(inStock=None, isCommitted=None)
        result = OCSAPService._validacion_desde_batch_item(item, "5986.NG.8", "RL-CD")
        assert result["valid"] is True
        assert result["stock"] == 0.0


class TestValidarProveedorBatch:
    """Validación del proveedor a partir de la sección businessPartner."""

    @staticmethod
    def _bp(**overrides):
        base = {
            "cardCode": "P1790389219001",
            "exists": True,
            "cardName": "PROVEEDOR X",
            "cardType": "cSupplier",
            "valid": True,
            "frozen": False,
            "errorType": None,
        }
        base.update(overrides)
        return base

    def test_proveedor_valido(self):
        errors, detalle = [], {"proveedor": {}, "articulos": {}}
        OCSAPService._validar_proveedor_batch(self._bp(), "P1790389219001", errors, detalle)
        assert errors == []
        assert detalle["proveedor"]["valid"] is True

    def test_proveedor_no_existe(self):
        errors, detalle = [], {"proveedor": {}, "articulos": {}}
        bp = self._bp(errorType="not_found", exists=False)
        OCSAPService._validar_proveedor_batch(bp, "P999", errors, detalle)
        assert "no existe en SAP BusinessPartners" in errors[0]
        assert detalle["proveedor"]["error"] == "no_existe"

    def test_proveedor_congelado(self):
        errors, detalle = [], {"proveedor": {}, "articulos": {}}
        OCSAPService._validar_proveedor_batch(self._bp(frozen=True), "P123", errors, detalle)
        assert "CONGELADO" in errors[0]

    def test_proveedor_error_conexion(self):
        errors, detalle = [], {"proveedor": {}, "articulos": {}}
        bp = self._bp(errorType="connection_error")
        OCSAPService._validar_proveedor_batch(bp, "P123", errors, detalle)
        assert "Error de conexión al validar proveedor" in errors[0]
        assert detalle["proveedor"]["error"] == "conexion"

    def test_sin_card_code_no_valida(self):
        errors, detalle = [], {"proveedor": {}, "articulos": {}}
        OCSAPService._validar_proveedor_batch(None, None, errors, detalle)
        assert errors == []


class TestPrecheckBatchFallback:
    """Condiciones en que _precheck_batch cede a la validación por línea."""

    @staticmethod
    def _service_con_mock() -> Any:
        service = OCSAPService.__new__(OCSAPService)
        service.sap_client = MagicMock()
        return service

    def test_batch_none_retorna_none(self):
        service = self._service_con_mock()
        service.sap_client.validate_purchase_order_batch.return_value = None
        resultado = service._precheck_batch(
            {"proveedor": "123"}, [{"sku_sap": "A", "cantidad_sap": 1, "codigo_bodega": "RL-CD"}],
            [], [], {"proveedor": {}, "articulos": {}},
        )
        assert resultado is None

    def test_mas_de_500_pares_no_llama_al_batch(self):
        service = self._service_con_mock()
        detalles = [
            {"sku_sap": f"SKU{i}", "cantidad_sap": 1, "codigo_bodega": "RL-CD"}
            for i in range(501)
        ]
        resultado = service._precheck_batch(
            {"proveedor": ""}, detalles, [], [], {"proveedor": {}, "articulos": {}},
        )
        assert resultado is None
        service.sap_client.validate_purchase_order_batch.assert_not_called()

    def test_deduplica_pares_y_antepone_p_al_proveedor(self):
        service = self._service_con_mock()
        service.sap_client.validate_purchase_order_batch.return_value = {
            "businessPartner": None,
            "items": [_item_batch(itemCode="A", warehouseCode="RL-CD")],
        }
        detalles = [
            {"sku_sap": "A", "cantidad_sap": 1, "codigo_bodega": "RL-CD"},
            {"sku_sap": "A", "cantidad_sap": 2, "codigo_bodega": "RL-CD"},
        ]
        service._precheck_batch(
            {"proveedor": "123"}, detalles, [], [], {"proveedor": {}, "articulos": {}},
        )
        card_code, lines = service.sap_client.validate_purchase_order_batch.call_args[0]
        assert card_code == "P123"
        assert lines == [{"itemCode": "A", "warehouseCode": "RL-CD"}]

    def test_lineas_sin_cantidad_o_sku_no_van_al_batch(self):
        service = self._service_con_mock()
        service.sap_client.validate_purchase_order_batch.return_value = {
            "businessPartner": None,
            "items": [],
        }
        detalles = [
            {"sku_sap": "", "cantidad_sap": 5, "codigo_bodega": "RL-CD"},
            {"sku_sap": "B", "cantidad_sap": 0, "codigo_bodega": "RL-CD"},
        ]
        errors = []
        service._precheck_batch(
            {"proveedor": ""}, detalles, errors, [], {"proveedor": {}, "articulos": {}},
        )
        _, lines = service.sap_client.validate_purchase_order_batch.call_args[0]
        assert lines == []
        # La línea con SKU vacío igualmente se reporta como error
        assert any("SKU vacío" in e for e in errors)


class TestPrecheckWiring:
    """Selección de vía (batch vs. línea por línea) en _precheck_against_service_layer."""

    @staticmethod
    def _service_con_mock() -> Any:
        service = OCSAPService.__new__(OCSAPService)
        service.sap_client = MagicMock()
        return service

    _CABECERA = {"proveedor": "1790389219001"}
    _DETALLES = [{"sku_sap": "5986.NG.8", "cantidad_sap": 10, "codigo_bodega": "RL-CD"}]

    def test_flag_apagado_usa_via_por_linea(self):
        service = self._service_con_mock()
        service.sap_client.validate_item_in_warehouse.return_value = {
            "valid": True, "item_exists": True, "is_purchase_item": True,
            "warehouse_configured": True, "stock": 50, "errors": [],
        }
        service.sap_client.get_business_partner.return_value = {
            "CardCode": "P1790389219001", "CardName": "X",
            "CardType": "cSupplier", "Valid": "tYES", "Frozen": "tNO",
        }
        with patch("src.database.services.oc_sap_service.USE_BATCH_VALIDATION", False):
            resultado = service._precheck_against_service_layer(self._CABECERA, self._DETALLES)
        assert resultado["valid"] is True
        service.sap_client.validate_purchase_order_batch.assert_not_called()

    def test_flag_encendido_usa_batch(self):
        service = self._service_con_mock()
        service.sap_client.validate_purchase_order_batch.return_value = {
            "businessPartner": {
                "cardCode": "P1790389219001", "exists": True, "cardName": "X",
                "cardType": "cSupplier", "valid": True, "frozen": False, "errorType": None,
            },
            "items": [_item_batch()],
        }
        with patch("src.database.services.oc_sap_service.USE_BATCH_VALIDATION", True):
            resultado = service._precheck_against_service_layer(self._CABECERA, self._DETALLES)
        assert resultado["valid"] is True
        assert resultado["resumen"]["articulos_validados"] == 1
        service.sap_client.validate_item_in_warehouse.assert_not_called()
        service.sap_client.get_business_partner.assert_not_called()

    def test_batch_caido_hace_fallback_sin_duplicar_errores(self):
        service = self._service_con_mock()
        service.sap_client.validate_purchase_order_batch.return_value = None
        service.sap_client.validate_item_in_warehouse.return_value = {
            "valid": True, "item_exists": True, "is_purchase_item": True,
            "warehouse_configured": True, "stock": 50, "errors": [],
        }
        service.sap_client.get_business_partner.return_value = {
            "CardCode": "P1790389219001", "CardName": "X",
            "CardType": "cSupplier", "Valid": "tYES", "Frozen": "tNO",
        }
        with patch("src.database.services.oc_sap_service.USE_BATCH_VALIDATION", True):
            resultado = service._precheck_against_service_layer(self._CABECERA, self._DETALLES)
        assert resultado["valid"] is True
        assert resultado["errors"] == []
        service.sap_client.validate_item_in_warehouse.assert_called_once()


class TestPrevalidarConReintento:
    """
    _prevalidar_con_reintento: la prevalidación en sí (_precheck_against_service_layer)
    no tenía retry propio, a diferencia del envío de la ODC. Ante "SAP saturado"
    (HTTP 202 del middleware agotando su ventana de reintento interna) debe reintentar
    con backoff; ante un error de validación real, no debe perder tiempo reintentando.
    """

    _SATURADO = {
        "valid": False,
        "errors": ["SAP saturado: no se pudo validar en este momento, inténtalo de nuevo en unos segundos"],
        "warnings": [],
    }
    _ERROR_REAL = {
        "valid": False,
        "errors": ["Item 'XYZ' no existe en SAP"],
        "warnings": [],
    }
    _EXITOSO = {"valid": True, "errors": [], "warnings": []}

    @staticmethod
    def _service_con_reintento_rapido() -> Any:
        service = OCSAPService.__new__(OCSAPService)
        service.sap_client = MagicMock()
        # Backoff en 0 para no ralentizar el test; el conteo de intentos es lo que se prueba.
        service.PREVALIDACION_RETRY_MAX_ATTEMPTS = 3
        service.PREVALIDACION_RETRY_BASE_DELAY_SECONDS = 0.0
        service.PREVALIDACION_RETRY_MAX_JITTER_SECONDS = 0.0
        return service

    def test_reintenta_ante_sap_saturado_y_finalmente_exitoso(self):
        service = self._service_con_reintento_rapido()
        with patch.object(
            service, "_precheck_against_service_layer",
            side_effect=[self._SATURADO, self._EXITOSO],
        ) as mock_precheck:
            resultado = service._prevalidar_con_reintento({}, [])
        assert resultado["valid"] is True
        assert mock_precheck.call_count == 2

    def test_no_reintenta_ante_error_de_validacion_real(self):
        service = self._service_con_reintento_rapido()
        with patch.object(
            service, "_precheck_against_service_layer",
            side_effect=[self._ERROR_REAL, self._EXITOSO],
        ) as mock_precheck:
            resultado = service._prevalidar_con_reintento({}, [])
        assert resultado["valid"] is False
        assert mock_precheck.call_count == 1

    def test_agota_intentos_si_sigue_saturado(self):
        service = self._service_con_reintento_rapido()
        with patch.object(
            service, "_precheck_against_service_layer",
            side_effect=[self._SATURADO, self._SATURADO, self._SATURADO],
        ) as mock_precheck:
            resultado = service._prevalidar_con_reintento({}, [])
        assert resultado["valid"] is False
        assert mock_precheck.call_count == 3
