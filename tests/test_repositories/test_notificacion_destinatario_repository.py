"""
Tests para get_destinatarios_activos.

Cubre la exclusión por codigo_evento: un email puede quedar excluido de un
evento puntual (ej. solo el correo "Redistribución Confirmada") sin sacarlo
del resto de notificaciones de su mismo tipo_notificacion.
"""

from unittest.mock import MagicMock

import pytest

from src.database.repositories.notificacion_destinatario_repository import (
    get_destinatarios_activos,
)


@pytest.fixture
def mock_connection():
    conn = MagicMock()
    conn.cursor.return_value = MagicMock()
    return conn


def test_retorna_emails_activos_sin_codigo_evento(mock_connection):
    cursor = MagicMock()
    cursor.fetchall.return_value = [("a@elrayo.com.ec",), ("b@elrayo.com.ec",)]
    mock_connection.cursor.return_value = cursor

    resultado = get_destinatarios_activos(mock_connection, "operaciones")

    assert resultado == ["a@elrayo.com.ec", "b@elrayo.com.ec"]
    cursor.close.assert_called_once()


def test_normaliza_tipo_notificacion_y_pasa_codigo_evento_none_por_defecto(mock_connection):
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    mock_connection.cursor.return_value = cursor

    get_destinatarios_activos(mock_connection, " operaciones ")

    _, params = cursor.execute.call_args.args
    assert params == ("OPERACIONES", "OPERACIONES", None)


def test_pasa_codigo_evento_a_la_consulta_para_permitir_exclusion(mock_connection):
    cursor = MagicMock()
    cursor.fetchall.return_value = [("a@elrayo.com.ec",)]
    mock_connection.cursor.return_value = cursor

    resultado = get_destinatarios_activos(
        mock_connection, "OPERACIONES", codigo_evento="REDISTRIBUCION_CONFIRMADA"
    )

    query, params = cursor.execute.call_args.args
    assert "codigo_evento IS NULL" in query
    assert "NOT IN" in query
    assert params == ("OPERACIONES", "OPERACIONES", "REDISTRIBUCION_CONFIRMADA")
    assert resultado == ["a@elrayo.com.ec"]


def test_retorna_lista_vacia_si_falla_la_consulta(mock_connection):
    cursor = MagicMock()
    cursor.execute.side_effect = Exception("boom")
    mock_connection.cursor.return_value = cursor

    resultado = get_destinatarios_activos(mock_connection, "OPERACIONES")

    assert resultado == []
    cursor.close.assert_called_once()
