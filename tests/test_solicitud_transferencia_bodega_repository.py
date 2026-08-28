"""
Tests de SolicitudTransferenciaBodegaRepository (insert / insert_detalle_individual /
update_resumen) -- persistencia de ITR entre bodegas (OCSAPService._enviar_itrs_por_bodega),
antes solo devuelta en la respuesta HTTP y nunca guardada en base de datos. Usa un
conn/cursor mockeado (mismo patrón que el resto de tests de repositorios).
"""

from unittest.mock import MagicMock

from src.database.repositories.solicitud_transferencia_bodega_repository import (
    SolicitudTransferenciaBodegaRepository,
)


def _resultado_bodega(**overrides):
    base = {
        "bodega_codigo": "OUT-CD",
        "success": True,
        "doc_num": 70215585,
        "doc_entry": 400970,
        "error": None,
    }
    base.update(overrides)
    return base


class TestInsert:
    def test_inserta_encabezado_y_devuelve_id(self):
        conn = MagicMock()
        conn.cursor.return_value.fetchone.return_value = ["solicitud-bodega-1"]
        repo = SolicitudTransferenciaBodegaRepository(conn)

        resultado_id = repo.insert(
            oc_id="oc-1", pedido_id="pedido-1", oc_doc_num=123, bodega_origen="RL-CD"
        )

        assert resultado_id == "solicitud-bodega-1"
        conn.commit.assert_called_once()

    def test_error_al_insertar_no_propaga_y_hace_rollback(self):
        conn = MagicMock()
        conn.cursor.return_value.execute.side_effect = Exception("timeout de BD")
        repo = SolicitudTransferenciaBodegaRepository(conn)

        resultado_id = repo.insert(
            oc_id="oc-1", pedido_id="pedido-1", oc_doc_num=123, bodega_origen="RL-CD"
        )

        assert resultado_id is None
        conn.rollback.assert_called_once()

    def test_acepta_oc_id_y_pedido_id_none(self):
        """El flujo de ITR por bodega puede correr sin pedido_id (ODC legacy de
        despacho) -- el insert no debe exigirlo."""
        conn = MagicMock()
        conn.cursor.return_value.fetchone.return_value = ["solicitud-bodega-1"]
        repo = SolicitudTransferenciaBodegaRepository(conn)

        resultado_id = repo.insert(oc_id=None, pedido_id=None, oc_doc_num=123, bodega_origen="RL-CD")

        assert resultado_id == "solicitud-bodega-1"


class TestInsertDetalleIndividual:
    def test_inserta_y_commitea_una_sola_fila(self):
        conn = MagicMock()
        repo = SolicitudTransferenciaBodegaRepository(conn)

        ok = repo.insert_detalle_individual("solicitud-bodega-1", _resultado_bodega())

        assert ok is True
        conn.cursor.return_value.execute.assert_called_once()
        conn.commit.assert_called_once()

    def test_persiste_estado_error_con_mensaje(self):
        conn = MagicMock()
        repo = SolicitudTransferenciaBodegaRepository(conn)

        ok = repo.insert_detalle_individual(
            "solicitud-bodega-1",
            _resultado_bodega(success=False, doc_num=None, doc_entry=None, error="Sin respuesta de SAP"),
        )

        assert ok is True
        args = conn.cursor.return_value.execute.call_args.args[1]
        assert "Error" in args
        assert "Sin respuesta de SAP" in args

    def test_error_al_hacer_commit_no_propaga_y_hace_rollback(self):
        conn = MagicMock()
        conn.commit.side_effect = Exception("timeout de BD")
        repo = SolicitudTransferenciaBodegaRepository(conn)

        ok = repo.insert_detalle_individual("solicitud-bodega-1", _resultado_bodega())

        assert ok is False
        conn.rollback.assert_called_once()


class TestUpdateResumen:
    def test_actualiza_contadores_del_encabezado(self):
        conn = MagicMock()
        conn.cursor.return_value.rowcount = 1
        repo = SolicitudTransferenciaBodegaRepository(conn)

        ok = repo.update_resumen("solicitud-bodega-1", {"created": 2, "errors": 0, "total": 2})

        assert ok is True
        conn.commit.assert_called_once()

    def test_error_no_propaga_y_hace_rollback(self):
        conn = MagicMock()
        conn.cursor.return_value.execute.side_effect = Exception("timeout de BD")
        repo = SolicitudTransferenciaBodegaRepository(conn)

        ok = repo.update_resumen("solicitud-bodega-1", {"created": 2, "errors": 0, "total": 2})

        assert ok is False
        conn.rollback.assert_called_once()
