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
    result = repo.get_oc_ids_con_tiendas_pendientes(dias_ventana=2, margen_antiguedad_minutos=30)

    assert result == ["oc-1", "oc-2"]
    cursor.execute.assert_called_once()


def test_filtra_filas_con_oc_id_vacio():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [("oc-1",), (None,)]
    conn.cursor.return_value = cursor

    repo = SolicitudTransferenciaRepository(conn)
    result = repo.get_oc_ids_con_tiendas_pendientes(dias_ventana=2, margen_antiguedad_minutos=30)

    assert result == ["oc-1"]


def test_error_de_sql_retorna_lista_vacia():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.execute.side_effect = Exception("tabla no existe")
    conn.cursor.return_value = cursor

    repo = SolicitudTransferenciaRepository(conn)
    result = repo.get_oc_ids_con_tiendas_pendientes(dias_ventana=2, margen_antiguedad_minutos=30)

    assert result == []


def test_pasa_dias_ventana_y_margen_antiguedad_como_parametros_de_la_query():
    """dias_ventana y margen_antiguedad_minutos viajan como parámetros reales de
    SQL (no interpolados en el texto). dias_ventana distingue lunes-sábado (2) de
    domingo (7); margen_antiguedad_minutos evita chocar con un envío en curso."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn.cursor.return_value = cursor
    repo = SolicitudTransferenciaRepository(conn)

    repo.get_oc_ids_con_tiendas_pendientes(dias_ventana=7, margen_antiguedad_minutos=30)

    params = cursor.execute.call_args.args[1]
    assert params == (7, 30)


def test_dias_ventana_none_omite_filtro_de_fecha():
    """dias_ventana=None (usado por el filtro manual solo_pendiente_reintento de
    GET /ordenes-compra): sin límite de antigüedad, a diferencia de la
    reconciliación Celery que siempre pasa un valor explícito."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn.cursor.return_value = cursor
    repo = SolicitudTransferenciaRepository(conn)

    repo.get_oc_ids_con_tiendas_pendientes(dias_ventana=None, margen_antiguedad_minutos=30)

    sql = cursor.execute.call_args.args[0]
    params = cursor.execute.call_args.args[1]
    assert "DATEADD(day" not in sql
    assert params == (30,)


def test_incluye_encolada_en_el_where_de_la_query():
    """F: antes solo se reconciliaban tiendas 'Error'; ahora también 'Encolada'
    (HTTP 202, job de middleware sin resolver) -- ver conversación 2026-08-28."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn.cursor.return_value = cursor
    repo = SolicitudTransferenciaRepository(conn)

    repo.get_oc_ids_con_tiendas_pendientes(dias_ventana=2, margen_antiguedad_minutos=30)

    sql = cursor.execute.call_args.args[0]
    assert "'Error', 'Encolada'" in sql
    assert "DATEADD(minute, -?, GETDATE())" in sql
