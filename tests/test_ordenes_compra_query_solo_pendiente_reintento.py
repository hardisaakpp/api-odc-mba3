"""
Tests de _query_ordenes_compra: wiring del filtro solo_pendiente_reintento.

Cuando el filtro está activo, debe calcular primero los oc_id con ST pendiente
(sin ventana de días -- el usuario pide "todas", a diferencia de la
reconciliación Celery) y pasarlos a OrdenCompraRepository.list_paginated.
Cuando está inactivo, no debe tocar SolicitudTransferenciaRepository para nada
extra (más allá del enriquecimiento normal de la página).
"""

from unittest.mock import MagicMock, patch

from src.endpoints.ordenes_compra import _query_ordenes_compra


@patch("src.endpoints.ordenes_compra.get_db_connection")
@patch("src.endpoints.ordenes_compra.SolicitudTransferenciaRepository")
@patch("src.endpoints.ordenes_compra.OrdenCompraRepository")
def test_solo_pendiente_reintento_activo_calcula_ids_sin_ventana(
    mock_oc_repo_cls, mock_st_repo_cls, mock_get_conn
):
    mock_get_conn.return_value = MagicMock()
    mock_oc_repo = mock_oc_repo_cls.return_value
    mock_oc_repo.list_paginated.return_value = {"data": [], "total": 0}
    mock_st_repo = mock_st_repo_cls.return_value
    mock_st_repo.get_oc_ids_con_tiendas_pendientes.return_value = ["oc-1", "oc-2"]

    _query_ordenes_compra(
        None, 10, 0, None, None, None, solo_pendiente_reintento_param=True,
    )

    mock_st_repo.get_oc_ids_con_tiendas_pendientes.assert_called_once()
    _, kwargs = mock_st_repo.get_oc_ids_con_tiendas_pendientes.call_args
    assert kwargs["dias_ventana"] is None

    mock_oc_repo.list_paginated.assert_called_once()
    _, list_kwargs = mock_oc_repo.list_paginated.call_args
    assert list_kwargs["solo_pendiente_reintento"] is True
    assert list_kwargs["oc_ids_st_pendiente"] == ["oc-1", "oc-2"]


@patch("src.endpoints.ordenes_compra.get_db_connection")
@patch("src.endpoints.ordenes_compra.SolicitudTransferenciaRepository")
@patch("src.endpoints.ordenes_compra.OrdenCompraRepository")
def test_solo_pendiente_reintento_inactivo_no_calcula_ids_previos(
    mock_oc_repo_cls, mock_st_repo_cls, mock_get_conn
):
    mock_get_conn.return_value = MagicMock()
    mock_oc_repo = mock_oc_repo_cls.return_value
    mock_oc_repo.list_paginated.return_value = {"data": [], "total": 0}

    _query_ordenes_compra(None, 10, 0, None, None, None)

    mock_st_repo_cls.return_value.get_oc_ids_con_tiendas_pendientes.assert_not_called()
    _, list_kwargs = mock_oc_repo.list_paginated.call_args
    assert list_kwargs["solo_pendiente_reintento"] is False
    assert list_kwargs["oc_ids_st_pendiente"] is None
