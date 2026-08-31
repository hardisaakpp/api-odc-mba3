"""
Tests para el soporte del estado ENVIANDO en OrdenCompraRepository:
get_oc_ids_envianco_estancadas y el guard estado_actual_esperado de update_estado.

El guard existe para que la reconciliación periódica (ver
src/tasks/celery_reconciliar_ordenes_compra.py) pueda escalar una ENVIANDO
estancada a ERROR sin riesgo de pisar un envío que en realidad terminó
legítimamente (ENVIADA/ERROR) justo entre el SELECT de candidatas y este UPDATE
-- si el estado ya cambió, el UPDATE no matchea ninguna fila y el método
devuelve False sin tocar nada.
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


def test_get_oc_ids_envianco_estancadas_filtra_por_estado_y_umbral(repository, mock_connection):
    cursor = MagicMock()
    cursor.fetchall.return_value = [("oc-1",), ("oc-2",)]
    mock_connection.cursor.return_value = cursor

    resultado = repository.get_oc_ids_envianco_estancadas(15)

    assert resultado == ["oc-1", "oc-2"]
    query, params = cursor.execute.call_args.args
    assert "estado = 'ENVIANDO'" in query
    assert params == (15,)


def test_update_estado_con_guard_no_afecta_fila_si_estado_ya_cambio(repository, mock_connection):
    """Simula la carrera: la fila ya pasó a ENVIADA cuando el barrido intenta el
    flip a ERROR -- el UPDATE con AND estado = ? no matchea nada (rowcount=0)."""
    cursor = MagicMock()
    cursor.rowcount = 0
    mock_connection.cursor.return_value = cursor

    resultado = repository.update_estado(
        "oc-1", "ERROR", error_message="estancada", estado_actual_esperado="ENVIANDO",
    )

    assert resultado is False
    query = cursor.execute.call_args.args[0]
    assert "AND estado = ?" in query


def test_update_estado_con_guard_afecta_fila_si_estado_coincide(repository, mock_connection):
    cursor = MagicMock()
    cursor.rowcount = 1
    mock_connection.cursor.return_value = cursor

    resultado = repository.update_estado(
        "oc-1", "ERROR", error_message="estancada", estado_actual_esperado="ENVIANDO",
    )

    assert resultado is True
    query, params = cursor.execute.call_args.args
    assert params[-1] == "ENVIANDO"


def test_update_estado_sin_guard_no_agrega_condicion_de_estado(repository, mock_connection):
    cursor = MagicMock()
    cursor.rowcount = 1
    mock_connection.cursor.return_value = cursor

    repository.update_estado("oc-1", "ENVIANDO")

    query = cursor.execute.call_args.args[0]
    assert "AND estado = ?" not in query
    assert "fecha_envio_iniciado = ?" in query
