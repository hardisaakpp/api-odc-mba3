"""
Tests de SolicitudTransferenciaRepository.get_tiendas_faltantes_por_oc_id y
get_oc_ids_con_tiendas_faltantes (F4.5): tiendas que la distribución confirmada
espera pero que nunca se intentaron -- ningún registro en
solicitud_transferencia_detalle, a diferencia de get_tiendas_pendientes_reintento_st
/ get_oc_ids_con_tiendas_pendientes, que solo detectan tiendas que SÍ se
intentaron y quedaron en Error/Encolada.

Usa un cursor mockeado (mismo patrón que el resto de tests de repositorios).
"""

from unittest.mock import MagicMock

from src.database.repositories.solicitud_transferencia_repository import (
    SolicitudTransferenciaRepository,
)


class TestGetTiendasFaltantesPorOcId:
    def test_retorna_tiendas_de_la_query(self):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = [("TOUT-NEW",), ("TRL-QSN",)]
        conn.cursor.return_value = cursor

        repo = SolicitudTransferenciaRepository(conn)
        result = repo.get_tiendas_faltantes_por_oc_id("oc-1")

        assert result == ["TOUT-NEW", "TRL-QSN"]
        cursor.execute.assert_called_once()

    def test_sin_oc_id_no_ejecuta_query(self):
        conn = MagicMock()
        repo = SolicitudTransferenciaRepository(conn)

        result = repo.get_tiendas_faltantes_por_oc_id("")

        assert result == []
        conn.cursor.assert_not_called()

    def test_pasa_oc_id_como_parametro_dos_veces(self):
        """El oc_id se usa en dos CTE distintas (pedido e intentadas) -- ambas
        deben recibir el mismo valor como parámetro."""
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn.cursor.return_value = cursor
        repo = SolicitudTransferenciaRepository(conn)

        repo.get_tiendas_faltantes_por_oc_id("oc-1")

        params = cursor.execute.call_args.args[1]
        assert params == ("oc-1", "oc-1")

    def test_error_de_sql_retorna_lista_vacia(self):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("tabla no existe")
        conn.cursor.return_value = cursor

        repo = SolicitudTransferenciaRepository(conn)
        result = repo.get_tiendas_faltantes_por_oc_id("oc-1")

        assert result == []

    def test_filtra_filas_con_tienda_codigo_vacio(self):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = [("TOUT-NEW",), (None,), ("",)]
        conn.cursor.return_value = cursor

        repo = SolicitudTransferenciaRepository(conn)
        result = repo.get_tiendas_faltantes_por_oc_id("oc-1")

        assert result == ["TOUT-NEW"]


class TestGetOcIdsConTiendasFaltantes:
    def test_retorna_oc_ids_de_la_query(self):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = [("oc-1",), ("oc-2",)]
        conn.cursor.return_value = cursor

        repo = SolicitudTransferenciaRepository(conn)
        result = repo.get_oc_ids_con_tiendas_faltantes(dias_ventana=2, margen_antiguedad_minutos=30)

        assert result == ["oc-1", "oc-2"]
        cursor.execute.assert_called_once()

    def test_pasa_dias_ventana_y_margen_antiguedad_como_parametros_de_la_query(self):
        """Mismo margen de antigüedad que get_oc_ids_con_tiendas_pendientes: una
        tienda "nunca intentada" mientras el envío original sigue en curso se ve
        idéntica a una realmente faltante (ver conversación 2026-08-28)."""
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn.cursor.return_value = cursor
        repo = SolicitudTransferenciaRepository(conn)

        repo.get_oc_ids_con_tiendas_faltantes(dias_ventana=7, margen_antiguedad_minutos=30)

        params = cursor.execute.call_args.args[1]
        assert params == (7, 30)
        sql = cursor.execute.call_args.args[0]
        assert "ultimo_envio" in sql
        assert "DATEADD(minute, -?, GETDATE())" in sql

    def test_error_de_sql_retorna_lista_vacia(self):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("tabla no existe")
        conn.cursor.return_value = cursor

        repo = SolicitudTransferenciaRepository(conn)
        result = repo.get_oc_ids_con_tiendas_faltantes(dias_ventana=2, margen_antiguedad_minutos=30)

        assert result == []
