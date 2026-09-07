"""
Regresión: itrs_por_tienda solo debe incluir ITR realmente creadas en SAP
(con doc_num), no tiendas que fallaron o quedaron encoladas.

Ver docs/RESOLUCION_PEDIDO_CONGELADO_TRAS_REINTENTO_ST.md y el incidente
diagnosticado 2026-08-27 (pedido "pedido prueba 130"): el modal mostraba
filas de tienda sin DocNum en la tabla de Solicitudes de Transferencia
porque _resolver_doc_num_y_solicitudes armaba itrs_por_tienda a partir de
TODOS los resultados, sin filtrar por doc_num is not None.
"""

from src.endpoints.pedidos.redistribucion.endpoints_proceso import (
    _resolver_doc_num_y_solicitudes,
)


def test_itrs_por_tienda_excluye_tiendas_sin_doc_num():
    resultado_sap_envio = {
        "doc_num": 24715,
        "solicitudes_transferencia": {
            "total_tiendas": 3,
            "transferencias_creadas": 1,
            "transferencias_errores": 0,
            "resultados": [
                {"tienda_codigo": "TRL-MSU", "doc_num": 70215584, "success": True},
                {"tienda_codigo": "TRL-PSM", "doc_num": None, "success": False, "error": "timeout"},
                {"tienda_codigo": "TRL-PSP", "doc_num": None, "queued": True},
            ],
        },
    }

    _, _, solicitudes = _resolver_doc_num_y_solicitudes(resultado_sap_envio)

    assert solicitudes["itrs_por_tienda"] == [
        {"doc_num": 70215584, "tienda_codigo": "TRL-MSU", "tienda_nombre": None}
    ]


def test_itrs_por_tienda_vacio_si_ninguna_tienda_tiene_doc_num():
    resultado_sap_envio = {
        "doc_num": 24715,
        "solicitudes_transferencia": {
            "total_tiendas": 2,
            "transferencias_creadas": 0,
            "transferencias_errores": 0,
            "resultados": [
                {"tienda_codigo": "TRL-QSN", "doc_num": None, "success": False},
                {"tienda_codigo": "TRL-QSS2", "doc_num": None, "success": False},
            ],
        },
    }

    _, _, solicitudes = _resolver_doc_num_y_solicitudes(resultado_sap_envio)

    assert solicitudes["itrs_por_tienda"] == []
