"""
Tests de la persistencia por tienda en SolicitudTransferenciaRepository
(insert_detalle_individual / update_detalle_individual / update_resumen).

Antes, el resultado completo de un lote de hasta 23 ITR se guardaba de una sola
vez, al final -- si el proceso se interrumpía a mitad de camino, se perdían de
la BD todas las confirmaciones reales de SAP hasta ese punto. Estos métodos
permiten persistir cada tienda apenas se resuelve. Usa un conn/cursor mockeado
(mismo patrón que el resto de tests de repositorios).
"""

from unittest.mock import MagicMock

from src.database.repositories.solicitud_transferencia_repository import (
    SolicitudTransferenciaRepository,
)


def _resultado_tienda(**overrides):
    base = {
        "tienda_codigo": "TRL-PSM",
        "tienda_nombre": "Portal Shopping Manta",
        "success": True,
        "estado": "confirmada",
        "doc_num": 70215585,
        "doc_entry": 400970,
        "error": None,
    }
    base.update(overrides)
    return base


class TestInsertDetalleIndividual:
    def test_inserta_y_commitea_una_sola_fila(self):
        conn = MagicMock()
        repo = SolicitudTransferenciaRepository(conn)

        ok = repo.insert_detalle_individual("solicitud-1", _resultado_tienda())

        assert ok is True
        conn.cursor.return_value.execute.assert_called_once()
        conn.commit.assert_called_once()

    def test_error_al_hacer_commit_no_propaga_y_hace_rollback(self):
        """_insert_one_detalle ya atrapa sus propios errores de execute() y
        devuelve False (no relanza) -- el try/except de este método cubre
        fallos fuera de eso, ej. el commit mismo."""
        conn = MagicMock()
        conn.commit.side_effect = Exception("timeout de BD")
        repo = SolicitudTransferenciaRepository(conn)

        ok = repo.insert_detalle_individual("solicitud-1", _resultado_tienda())

        assert ok is False
        conn.rollback.assert_called_once()

    def test_fallo_de_execute_no_propaga_ok_es_false_sin_relanzar(self):
        """_insert_one_detalle atrapa el error de execute() y devuelve False; el
        commit posterior (sobre nada insertado) no debe romper nada."""
        conn = MagicMock()
        conn.cursor.return_value.execute.side_effect = Exception("timeout de BD")
        repo = SolicitudTransferenciaRepository(conn)

        ok = repo.insert_detalle_individual("solicitud-1", _resultado_tienda())

        assert ok is False


class TestUpdateDetalleIndividual:
    def test_actualiza_estado_y_docnum_por_tienda(self):
        conn = MagicMock()
        conn.cursor.return_value.rowcount = 1
        repo = SolicitudTransferenciaRepository(conn)

        ok = repo.update_detalle_individual(
            "solicitud-1",
            _resultado_tienda(estado="confirmada", doc_num=70215585, doc_entry=400970),
        )

        assert ok is True
        args = conn.cursor.return_value.execute.call_args.args[1]
        # UPDATE ... SET estado, doc_num, doc_entry, error_mensaje WHERE solicitud_transferencia_id, tienda_codigo
        assert args[0] == "Creada"
        assert args[1] == 70215585
        assert args[2] == 400970
        assert args[3] is None
        assert args[4] == "solicitud-1"
        assert args[5] == "TRL-PSM"
        conn.commit.assert_called_once()

    def test_rowcount_cero_retorna_false_sin_romper(self):
        conn = MagicMock()
        conn.cursor.return_value.rowcount = 0
        repo = SolicitudTransferenciaRepository(conn)

        ok = repo.update_detalle_individual("solicitud-1", _resultado_tienda())

        assert ok is False

    def test_error_no_propaga_y_hace_rollback(self):
        conn = MagicMock()
        conn.cursor.return_value.execute.side_effect = Exception("timeout de BD")
        repo = SolicitudTransferenciaRepository(conn)

        ok = repo.update_detalle_individual("solicitud-1", _resultado_tienda())

        assert ok is False
        conn.rollback.assert_called_once()


class TestUpdateResumen:
    def test_actualiza_contadores_y_json_del_encabezado(self):
        conn = MagicMock()
        conn.cursor.return_value.rowcount = 1
        repo = SolicitudTransferenciaRepository(conn)
        resultado = {
            "success": True,
            "total_tiendas": 2,
            "transferencias_creadas": 2,
            "transferencias_errores": 0,
            "resultados": [_resultado_tienda()],
        }

        ok = repo.update_resumen("solicitud-1", resultado)

        assert ok is True
        args = conn.cursor.return_value.execute.call_args.args[1]
        assert args[0] == 2  # transferencias_creadas
        assert args[1] == 0  # transferencias_errores
        assert args[2] == 1  # success -> 1
        assert "TRL-PSM" in args[3]  # resultado_json serializado
        assert args[4] == "solicitud-1"
        conn.commit.assert_called_once()

    def test_error_no_propaga_y_hace_rollback(self):
        conn = MagicMock()
        conn.cursor.return_value.execute.side_effect = Exception("timeout de BD")
        repo = SolicitudTransferenciaRepository(conn)

        ok = repo.update_resumen("solicitud-1", {"transferencias_creadas": 0, "transferencias_errores": 0})

        assert ok is False
        conn.rollback.assert_called_once()
