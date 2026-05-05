"""Tests para puede_reintentar_envio_odc_sap (helpers de pedido)."""

from src.database.pedido_estados import ESTADO_ERROR_ENVIO_SAP_REINTENTO
from src.endpoints.pedidos.pedidos_crud_helpers import pedido_permite_reintento_envio_odc_sap


def _pedido(estado_id: int):
    return {"cabecera": {"estado_id": estado_id}}


def test_reintento_false_si_no_confirmado_redistribucion():
    assert not pedido_permite_reintento_envio_odc_sap(_pedido(4), [{"estado": "ERROR", "respuesta_sap": "conexión"}])


def test_reintento_true_oc_pendiente_estado_10():
    assert pedido_permite_reintento_envio_odc_sap(_pedido(10), [{"estado": "PENDIENTE"}])


def test_reintento_true_prevalidacion_error_conexion():
    oc = {
        "estado": "ERROR",
        "error_source": "SAP_VALIDATION",
        "respuesta_sap": "Prevalidación SAP falló: Error de conexión al validar proveedor 'P1790389219001'",
    }
    assert pedido_permite_reintento_envio_odc_sap(_pedido(10), [oc])


def test_reintento_false_error_maestro_sin_keywords_red():
    oc = {
        "estado": "ERROR",
        "error_source": "SAP_VALIDATION",
        "respuesta_sap": "Prevalidación SAP falló: artículo inexistente X",
    }
    assert not pedido_permite_reintento_envio_odc_sap(_pedido(10), [oc])


def test_reintento_true_error_presupuesto_excedido_rl():
    oc = {
        "estado": "ERROR",
        "error_source": "SAP_VALIDATION",
        "respuesta_sap": "(1) Presupuesto excedido RL → Línea: 0 | Item: 5019.911.NG | Monto: 31.94 (Código SAP: -1116)",
    }
    assert pedido_permite_reintento_envio_odc_sap(_pedido(10), [oc])


def test_reintento_true_por_error_code_sap_1116_sin_mensaje():
    oc = {
        "estado": "ERROR",
        "error_source": "SAP",
        "error_code": "-1116",
        "respuesta_sap": "",
        "error_message": "",
    }
    assert pedido_permite_reintento_envio_odc_sap(_pedido(10), [oc])


def test_reintento_false_por_error_code_sap_no_listado():
    oc = {
        "estado": "ERROR",
        "error_source": "SAP",
        "error_code": "-4013",
        "respuesta_sap": "Periodo contable cerrado",
    }
    assert not pedido_permite_reintento_envio_odc_sap(_pedido(10), [oc])


def test_reintento_true_sap_connection():
    oc = {
        "estado": "ERROR",
        "error_source": "SAP_CONNECTION",
        "respuesta_sap": "cualquier mensaje",
    }
    assert pedido_permite_reintento_envio_odc_sap(_pedido(10), [oc])


def test_reintento_true_estado_21_con_oc_error():
    oc = {"estado": "ERROR", "respuesta_sap": "Prevalidación SAP falló"}
    assert pedido_permite_reintento_envio_odc_sap(
        _pedido(ESTADO_ERROR_ENVIO_SAP_REINTENTO), [oc]
    )


def test_reintento_false_estado_21_sin_oc_pendiente_ni_error():
    assert not pedido_permite_reintento_envio_odc_sap(
        _pedido(ESTADO_ERROR_ENVIO_SAP_REINTENTO),
        [{"estado": "ENVIADA", "numero_oc_sap": "1"}],
    )
