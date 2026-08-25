"""
Tests de _fetch_integracion_sap (endpoint GET /ordenes-compra/{oc_id}/integracion-sap).

Bug: el modal "Integración con SAP Completada" mostraba el resumen ITR del
envío original (ej. "2 de 6 creadas") aunque un reintento posterior ya hubiera
creado las ITR faltantes, porque este endpoint leía total_tiendas/
transferencias_creadas/solicitud_transferencia_id como snapshot congelado de
envio_odc_sap (escrito una sola vez, en el envío original) en vez de agregar
en vivo todos los batches de solicitud_transferencia por oc_id.

Se mockean los repositorios (EnvioODCSAPRepository, SolicitudTransferenciaRepository)
para verificar que el resumen expuesto proviene de
SolicitudTransferenciaRepository.get_resumen_agregado_por_oc_id, no de los
campos total_transferencias/transferencias_creadas de envio_odc_sap.
"""

from unittest.mock import MagicMock, patch

from src.endpoints.ordenes_compra import _fetch_integracion_sap


def _mock_repos(envio: dict, resumen: dict):
    envio_repo = MagicMock()
    envio_repo.get_by_oc_id.return_value = envio

    st_repo = MagicMock()
    st_repo.get_resumen_agregado_por_oc_id.return_value = resumen

    return envio_repo, st_repo


def test_usa_resumen_agregado_no_el_snapshot_congelado():
    """
    envio_odc_sap sigue con el snapshot viejo (2 de 6), pero el resumen agregado
    en vivo ya refleja el reintento exitoso (6 de 6): el endpoint debe devolver
    el segundo, no el primero.
    """
    envio = {
        "numero_oc_sap": "24640",
        "doc_entry": 45826,
        "proveedor": "Proveedor X",
        "solicitud_transferencia_id": "st-batch-original",
        "total_transferencias": 2,
        "transferencias_creadas": 2,
    }
    resumen_agregado = {
        "total_tiendas": 6,
        "transferencias_creadas": 6,
        "transferencias_errores": 0,
        "resultados": [
            {"tienda_codigo": "TRL-RGAI", "tienda_nombre": None, "doc_num": 70215121,
             "doc_entry": 111, "success": True, "error": None},
            {"tienda_codigo": "TRL-SMA", "tienda_nombre": None, "doc_num": 70215122,
             "doc_entry": 112, "success": True, "error": None},
        ],
        "itrs_por_tienda": [
            {"doc_num": 70215121, "tienda_codigo": "TRL-RGAI"},
            {"doc_num": 70215122, "tienda_codigo": "TRL-SMA"},
        ],
    }
    envio_repo, st_repo = _mock_repos(envio, resumen_agregado)

    with patch("src.endpoints.ordenes_compra.get_db_connection", return_value=MagicMock()), \
         patch("src.endpoints.ordenes_compra.EnvioODCSAPRepository", return_value=envio_repo), \
         patch("src.endpoints.ordenes_compra.SolicitudTransferenciaRepository", return_value=st_repo):
        data = _fetch_integracion_sap("oc-1")

    st_repo.get_resumen_agregado_por_oc_id.assert_called_once_with("oc-1")
    assert data["solicitudes_transferencia"]["total_tiendas"] == 6
    assert data["solicitudes_transferencia"]["transferencias_creadas"] == 6
    assert data["envio_sap"]["solicitudes_transferencia"]["transferencias_creadas"] == 6
    assert data["envio_sap"]["numero_oc_sap"] == "24640"
    assert data["envio_sap"]["doc_entry"] == 45826


def test_doc_num_first_viene_del_resumen_agregado():
    envio = {
        "numero_oc_sap": "24640", "doc_entry": 45826, "proveedor": "Proveedor X",
        "solicitud_transferencia_id": "st-1", "total_transferencias": 1, "transferencias_creadas": 0,
    }
    resumen_agregado = {
        "total_tiendas": 1,
        "transferencias_creadas": 1,
        "transferencias_errores": 0,
        "resultados": [],
        "itrs_por_tienda": [{"doc_num": 999888, "tienda_codigo": "TRL-Z"}],
    }
    envio_repo, st_repo = _mock_repos(envio, resumen_agregado)

    with patch("src.endpoints.ordenes_compra.get_db_connection", return_value=MagicMock()), \
         patch("src.endpoints.ordenes_compra.EnvioODCSAPRepository", return_value=envio_repo), \
         patch("src.endpoints.ordenes_compra.SolicitudTransferenciaRepository", return_value=st_repo):
        data = _fetch_integracion_sap("oc-1")

    assert data["envio_sap"]["doc_num"] == 999888


def test_sin_registro_envio_retorna_none():
    envio_repo = MagicMock()
    envio_repo.get_by_oc_id.return_value = None
    st_repo = MagicMock()

    with patch("src.endpoints.ordenes_compra.get_db_connection", return_value=MagicMock()), \
         patch("src.endpoints.ordenes_compra.EnvioODCSAPRepository", return_value=envio_repo), \
         patch("src.endpoints.ordenes_compra.SolicitudTransferenciaRepository", return_value=st_repo):
        data = _fetch_integracion_sap("oc-inexistente")

    assert data is None
    st_repo.get_resumen_agregado_por_oc_id.assert_not_called()
