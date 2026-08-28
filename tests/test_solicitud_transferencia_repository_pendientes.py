"""
Tests de SolicitudTransferenciaRepository.get_oc_ids_con_tiendas_pendientes.

Usa un cursor mockeado (mismo patrón que el resto de tests de repositorios en
este proyecto) ya que el método ejecuta SQL directo contra SQL Server.
"""

from unittest.mock import MagicMock

from src.database.repositories.solicitud_transferencia_repository import (
    SolicitudTransferenciaRepository,
)


def test_retorna_oc_ids_de_la_query():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [("oc-1",), ("oc-2",)]
    conn.cursor.return_value = cursor

    repo = SolicitudTransferenciaRepository(conn)
    result = repo.get_oc_ids_con_tiendas_pendientes(dias_ventana=2)

    assert result == ["oc-1", "oc-2"]
    cursor.execute.assert_called_once()


def test_filtra_filas_con_oc_id_vacio():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [("oc-1",), (None,)]
    conn.cursor.return_value = cursor

    repo = SolicitudTransferenciaRepository(conn)
    result = repo.get_oc_ids_con_tiendas_pendientes(dias_ventana=2)

    assert result == ["oc-1"]


def test_error_de_sql_retorna_lista_vacia():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.execute.side_effect = Exception("tabla no existe")
    conn.cursor.return_value = cursor

    repo = SolicitudTransferenciaRepository(conn)
    result = repo.get_oc_ids_con_tiendas_pendientes(dias_ventana=2)

    assert result == []


def test_pasa_dias_ventana_como_parametro_de_la_query():
    """dias_ventana viaja como parámetro real de SQL (no interpolado en el texto),
    y distintos valores (2 para lunes-sábado, 7 para el barrido semanal del
    domingo) deben reflejarse en la llamada."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn.cursor.return_value = cursor
    repo = SolicitudTransferenciaRepository(conn)

    repo.get_oc_ids_con_tiendas_pendientes(dias_ventana=7)

    params = cursor.execute.call_args.args[1]
    assert params == (7,)
