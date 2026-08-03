from src.database.services.retry_utils import (
    retry_operation,
    sap_service_layer_result_should_retry,
    mensaje_sugiere_reintento_transitorio,
)


def test_mensaje_sugiere_reintento_transitorio_conexion_con_y_sin_tilde():
    assert mensaje_sugiere_reintento_transitorio("Error de conexión con SAP") is True
    assert mensaje_sugiere_reintento_transitorio("Error de conexion con SAP") is True


def test_mensaje_sugiere_reintento_transitorio_timeout_y_presupuesto_rl():
    assert mensaje_sugiere_reintento_transitorio("Timeout al llamar a Service Layer") is True
    assert mensaje_sugiere_reintento_transitorio("Presupuesto excedido RL para el pedido") is True


def test_mensaje_sugiere_reintento_transitorio_error_de_datos_es_false():
    assert mensaje_sugiere_reintento_transitorio("Artículo no habilitado para compra") is False
    assert mensaje_sugiere_reintento_transitorio("Proveedor congelado en SAP") is False


def test_mensaje_sugiere_reintento_transitorio_vacio_es_false():
    assert mensaje_sugiere_reintento_transitorio("") is False
    assert mensaje_sugiere_reintento_transitorio(None) is False


def test_sap_service_layer_result_should_retry_transient_http():
    assert sap_service_layer_result_should_retry({"success": False, "status_code": 503}) is True
    assert sap_service_layer_result_should_retry({"success": False, "status_code": 429}) is True


def test_sap_service_layer_result_should_retry_permanent_http():
    assert sap_service_layer_result_should_retry({"success": False, "status_code": 400}) is False
    assert sap_service_layer_result_should_retry({"success": False, "status_code": 401}) is False


def test_sap_b1_error_code_lock_overrides_400():
    assert (
        sap_service_layer_result_should_retry(
            {
                "success": False,
                "status_code": 400,
                "error_code": "-2038",
                "error": "Record locked",
            }
        )
        is True
    )


def test_sap_b1_error_code_validation_no_retry_on_400():
    assert (
        sap_service_layer_result_should_retry(
            {
                "success": False,
                "status_code": 400,
                "error_code": -2055,
                "error": "Invalid value",
            }
        )
        is False
    )


def test_sap_b1_error_code_period_locked_no_retry():
    assert (
        sap_service_layer_result_should_retry(
            {
                "success": False,
                "status_code": 400,
                "error_code": "-4013",
                "error": "Period is locked for new data",
            }
        )
        is False
    )


def test_sap_b1_error_code_no_retry_overrides_503():
    """Permiso/validación explícita por código B1: no reintentar aunque HTTP sea 5xx."""
    assert (
        sap_service_layer_result_should_retry(
            {
                "success": False,
                "status_code": 503,
                "error_code": "-3000",
                "error": "No permission",
            }
        )
        is False
    )


def test_sap_service_layer_result_should_retry_connection_message_without_status():
    assert (
        sap_service_layer_result_should_retry(
            {"success": False, "error": "Error de conexión: boom"}
        )
        is True
    )


def test_sap_service_layer_result_should_retry_middleware_unreachable():
    # Mensaje real emitido por SAPServiceLayerClient._post() cuando el middleware no responde
    # (create_purchase_order / create_stock_transfer), sin status_code en el dict.
    assert (
        sap_service_layer_result_should_retry(
            {"success": False, "error": "No se pudo conectar con el middleware SAP"}
        )
        is True
    )


def test_mensaje_sugiere_reintento_transitorio_middleware_unreachable():
    assert mensaje_sugiere_reintento_transitorio("No se pudo conectar con el middleware SAP") is True


def test_retry_operation_stops_early_when_not_retryable():
    calls = {"n": 0}

    def execute():
        calls["n"] += 1
        return {"success": False, "status_code": 400, "error": "bad request"}

    class _Logger:
        def warning(self, *_args, **_kwargs):
            pass

        def info(self, *_args, **_kwargs):
            pass

    result = retry_operation(
        execute=execute,
        is_success=lambda r: bool(r and r.get("success")),
        extract_error=lambda r: r.get("error", "err"),
        max_attempts=5,
        should_retry=sap_service_layer_result_should_retry,
        base_delay_seconds=0.0,
        max_jitter_seconds=0.0,
        logger=_Logger(),
        operation_label="TEST",
    )

    assert result["success"] is False
    assert result["attempts"] == 1
    assert calls["n"] == 1
