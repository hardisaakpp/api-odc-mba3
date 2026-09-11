"""
Tests para el filtro `solo_pendiente_reintento` de OrdenCompraRepository.list_paginated.

Debe reflejar exactamente la misma regla que _enrich_oc_actions en
src/endpoints/ordenes_compra.py: mostrar_reintentar (PENDIENTE/ERROR) OR
mostrar_reintentar_st (ENVIADA con oc_id en la lista de ST pendiente).
"""

from unittest.mock import MagicMock

import pytest

from src.database.repositories.orden_compra_repository import (
    OrdenCompraRepository,
    _build_in_clause,
)


@pytest.fixture
def mock_connection():
    conn = MagicMock()
    conn.cursor.return_value = MagicMock()
    return conn


@pytest.fixture
def repository(mock_connection):
    return OrdenCompraRepository(mock_connection)


def _preparar_cursor(mock_connection, total=0):
    cursor = MagicMock()
    cursor.fetchone.return_value = (total,)
    cursor.fetchall.return_value = []
    mock_connection.cursor.return_value = cursor
    return cursor


def test_solo_pendiente_reintento_sin_ids_st_filtra_solo_por_estado(repository, mock_connection):
    """Sin ODCs con ST pendiente (oc_ids_st_pendiente vacío/None), el filtro se
    reduce a estado IN ('PENDIENTE','ERROR') -- nunca debe emitir un `IN ()` vacío."""
    cursor = _preparar_cursor(mock_connection)

    repository.list_paginated(solo_pendiente_reintento=True, oc_ids_st_pendiente=None)

    count_query = cursor.execute.call_args_list[0].args[0]
    assert "estado IN ('PENDIENTE', 'ERROR')" in count_query
    assert "IN ()" not in count_query


def test_solo_pendiente_reintento_con_ids_st_combina_con_or(repository, mock_connection):
    cursor = _preparar_cursor(mock_connection)

    repository.list_paginated(
        solo_pendiente_reintento=True,
        oc_ids_st_pendiente=["oc-a", "oc-b"],
        limit=20,
        offset=0,
    )

    count_query, count_params = cursor.execute.call_args_list[0].args
    assert "estado IN ('PENDIENTE', 'ERROR')" in count_query
    assert "estado = 'ENVIADA'" in count_query
    assert "oc_id IN (?,?)" in count_query
    assert count_params == ["oc-a", "oc-b"]

    data_query, data_params = cursor.execute.call_args_list[1].args
    assert data_params[:2] == ["oc-a", "oc-b"]
    assert data_params[-2:] == [0, 20]


def test_solo_pendiente_reintento_false_no_agrega_condicion(repository, mock_connection):
    cursor = _preparar_cursor(mock_connection)

    repository.list_paginated(oc_ids_st_pendiente=["oc-a"])

    count_query = cursor.execute.call_args_list[0].args[0]
    assert "PENDIENTE" not in count_query
    assert "oc_id IN" not in count_query


def test_solo_pendiente_reintento_combina_con_otros_filtros_via_and(repository, mock_connection):
    cursor = _preparar_cursor(mock_connection)

    repository.list_paginated(
        solo_pendiente_reintento=True,
        oc_ids_st_pendiente=[],
        search="REF-1",
    )

    count_query = cursor.execute.call_args_list[0].args[0]
    assert " AND " in count_query
    assert "referencia_despacho LIKE ?" in count_query
    assert "estado IN ('PENDIENTE', 'ERROR')" in count_query


def test_build_in_clause_una_sola_tanda_para_pocos_valores():
    clause, params = _build_in_clause("oc_id", ["a", "b", "c"])

    assert clause == "oc_id IN (?,?,?)"
    assert params == ["a", "b", "c"]


def test_build_in_clause_particiona_en_bloques_de_1000_con_or():
    valores = [f"oc-{i}" for i in range(1500)]

    clause, params = _build_in_clause("oc_id", valores)

    assert clause.count(" OR ") == 1
    assert clause.count("IN (") == 2
    assert params == valores
