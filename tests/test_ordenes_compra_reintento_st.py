"""
Tests de _traducir_resultado_reintento_st: mapeo del status interno de
StockTransferService.reintentar_pendientes al contrato HTTP externo.
"""

from src.endpoints.ordenes_compra import _traducir_resultado_reintento_st


def test_no_encontrada_es_404_error():
    out = _traducir_resultado_reintento_st({"status": "no_encontrada", "oc_id": "x"})
    assert out["status_code"] == 404
    assert out["body"]["status"] == "error"


def test_estado_invalido_es_400_error():
    out = _traducir_resultado_reintento_st({"status": "estado_invalido", "oc_id": "x"})
    assert out["status_code"] == 400
    assert out["body"]["status"] == "error"


def test_sin_pedido_es_400_error():
    out = _traducir_resultado_reintento_st({"status": "sin_pedido", "oc_id": "x"})
    assert out["status_code"] == 400
    assert out["body"]["status"] == "error"


def test_no_pendientes_es_200_success():
    out = _traducir_resultado_reintento_st({"status": "no_pendientes", "oc_id": "x", "reintentadas": 0})
    assert out["status_code"] == 200
    assert out["body"]["status"] == "success"


def test_success_es_200_success():
    out = _traducir_resultado_reintento_st({"status": "success", "oc_id": "x"})
    assert out["status_code"] == 200
    assert out["body"]["status"] == "success"


def test_partial_es_200_partial():
    out = _traducir_resultado_reintento_st({"status": "partial", "oc_id": "x"})
    assert out["status_code"] == 200
    assert out["body"]["status"] == "partial"


def test_preserva_campos_adicionales_del_resultado():
    out = _traducir_resultado_reintento_st({
        "status": "success", "oc_id": "x", "tiendas_count": 2, "resultado_st": {"a": 1},
    })
    assert out["body"]["tiendas_count"] == 2
    assert out["body"]["resultado_st"] == {"a": 1}
