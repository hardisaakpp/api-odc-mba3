"""
Tests para PedidoCabeceraRepository.get_fecha_confirmacion_estado.

Usado por el exportador TXT MBA3 para las columnas Fecha Pedido / Fecha Entrega:
la fecha en que el pedido transicionó a un estado (ej. CONFIRMADO POR EL RAYO),
según la bitácora pedido_estado_historial.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.database.pedido_estados import ESTADO_REDISTRIBUCION
from src.database.repositories.pedido.pedido_cabecera_repository import PedidoCabeceraRepository


@pytest.fixture(autouse=True)
def _reset_tabla_historial_cache():
    # Cache de clase compartida entre tests; resetear para no filtrar estado entre casos.
    PedidoCabeceraRepository._tiene_historial = None
    yield
    PedidoCabeceraRepository._tiene_historial = None


@pytest.fixture
def mock_connection():
    conn = MagicMock()
    conn.cursor.return_value = MagicMock()
    return conn


@pytest.fixture
def repository(mock_connection):
    return PedidoCabeceraRepository(mock_connection)


def test_retorna_fecha_cuando_existe_transicion(repository, mock_connection):
    cursor = MagicMock()
    # Primera consulta: OBJECT_ID (existe la tabla). Segunda: fecha_cambio convertida.
    cursor.fetchone.side_effect = [(1,), (datetime(2026, 3, 15, 10, 30),)]
    mock_connection.cursor.return_value = cursor

    resultado = repository.get_fecha_confirmacion_estado("PED-1", ESTADO_REDISTRIBUCION)

    assert resultado == datetime(2026, 3, 15, 10, 30)
    cursor.close.assert_called_once()


def test_retorna_none_cuando_no_hay_transicion(repository, mock_connection):
    cursor = MagicMock()
    cursor.fetchone.side_effect = [(1,), None]
    mock_connection.cursor.return_value = cursor

    resultado = repository.get_fecha_confirmacion_estado("PED-1", ESTADO_REDISTRIBUCION)

    assert resultado is None


def test_retorna_none_cuando_no_existe_tabla_historial(repository, mock_connection):
    cursor = MagicMock()
    cursor.fetchone.return_value = (None,)  # OBJECT_ID no encuentra la tabla
    mock_connection.cursor.return_value = cursor

    resultado = repository.get_fecha_confirmacion_estado("PED-1", ESTADO_REDISTRIBUCION)

    assert resultado is None
    # No debe intentar la segunda consulta si la tabla no existe.
    assert cursor.execute.call_count == 1


def test_convierte_de_utc_a_hora_colombia_en_sql():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [(1,), (datetime(2026, 3, 15, 5, 0),)]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    repo = PedidoCabeceraRepository(conn)
    PedidoCabeceraRepository._tiene_historial = None

    repo.get_fecha_confirmacion_estado("PED-1", ESTADO_REDISTRIBUCION)

    query_historial = cursor.execute.call_args_list[1].args[0]
    assert "DATEADD(HOUR, -5, fecha_cambio)" in query_historial
