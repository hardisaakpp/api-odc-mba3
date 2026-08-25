"""
Tests para OrdenCompraRepository.get_doc_num_by_pedido_id.

Usado por el exportador TXT MBA3 (columna 12, Orden Compra Cliente): el DocNum
de la OC más reciente enviada a SAP para un pedido.
"""

from unittest.mock import MagicMock

import pytest

from src.database.repositories.orden_compra_repository import OrdenCompraRepository


@pytest.fixture
def mock_connection():
    conn = MagicMock()
    conn.cursor.return_value = MagicMock()
    return conn


@pytest.fixture
def repository(mock_connection):
    return OrdenCompraRepository(mock_connection)


def test_retorna_doc_num_como_string_cuando_existe(repository, mock_connection):
    cursor = MagicMock()
    cursor.fetchone.return_value = (1524,)
    mock_connection.cursor.return_value = cursor

    resultado = repository.get_doc_num_by_pedido_id("PED-1")

    assert resultado == "1524"
    cursor.close.assert_called_once()


def test_retorna_none_cuando_no_hay_oc_con_doc_num(repository, mock_connection):
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    mock_connection.cursor.return_value = cursor

    resultado = repository.get_doc_num_by_pedido_id("PED-1")

    assert resultado is None


def test_filtra_por_pedido_id_y_ordena_por_mas_reciente(repository, mock_connection):
    cursor = MagicMock()
    cursor.fetchone.return_value = (7788,)
    mock_connection.cursor.return_value = cursor

    repository.get_doc_num_by_pedido_id("PED-1")

    query, params = cursor.execute.call_args.args
    assert "orden_compra_cabecera" in query
    assert "numero_oc_sap IS NOT NULL" in query
    assert "ORDER BY created_at DESC" in query
    assert params == ("PED-1",)
