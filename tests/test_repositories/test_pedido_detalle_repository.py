"""
Tests para PedidoDetalleRepository: guardar/obtener modificaciones de columnas
con rol_modificador (persistencia del color de resaltado por rol del editor
en Detalle del Pedido: PRODUCCION_ELRAYO = morado, ODCSAP = ámbar).
"""

from unittest.mock import MagicMock, patch
import uuid

from src.database.repositories.pedido.pedido_detalle_repository import PedidoDetalleRepository


class TestEjecutarMergeColumnaRolModificador:
    """Tests directos de _ejecutar_merge_columna: el MERGE debe incluir
    rol_modificador solo cuando la columna existe (tiene_rol=True), para no
    romper en un ambiente donde la migración 639 aún no corrió."""

    def test_incluye_rol_modificador_cuando_tiene_rol(self):
        conn = MagicMock()
        cursor = MagicMock()
        repo = PedidoDetalleRepository(conn)

        repo._ejecutar_merge_columna(
            cursor, "detalle-1", "total", "usuario1",
            tiene_valores=False, valor_anterior=None, valor_nuevo=None,
            fecha_actual="2026-08-16T00:00:00",
            rol_modificador="PRODUCCION_ELRAYO", tiene_rol=True,
        )

        cursor.execute.assert_called_once()
        sql, params = cursor.execute.call_args.args
        assert "rol_modificador" in sql
        assert "PRODUCCION_ELRAYO" in params

    def test_omite_rol_modificador_cuando_no_tiene_rol(self):
        conn = MagicMock()
        cursor = MagicMock()
        repo = PedidoDetalleRepository(conn)

        repo._ejecutar_merge_columna(
            cursor, "detalle-1", "total", "usuario1",
            tiene_valores=False, valor_anterior=None, valor_nuevo=None,
            fecha_actual="2026-08-16T00:00:00",
            rol_modificador="PRODUCCION_ELRAYO", tiene_rol=False,
        )

        sql, params = cursor.execute.call_args.args
        assert "rol_modificador" not in sql
        assert "PRODUCCION_ELRAYO" not in params


@patch("src.database.repositories.pedido.pedido_detalle_repository.AuditLogService")
class TestGuardarModificacionesColumnasRolModificador:
    """AuditLogService se mockea: su lógica de log (con caché global de
    existencia de tabla) es ortogonal a lo que se prueba acá."""

    def test_guarda_rol_modificador_del_editor(self, _mock_audit_cls):
        pedido_id = str(uuid.uuid4())
        detalle_id = str(uuid.uuid4())

        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.side_effect = [
            (pedido_id,),   # SELECT pedido_id FROM pedido
            (0,),           # tiene_valores -> False
            (1,),           # tiene_rol -> True
            (detalle_id,),  # el detalle pertenece al pedido
        ]

        repo = PedidoDetalleRepository(conn)
        resultado = repo.guardar_modificaciones_columnas(
            numero_pedido="P-1",
            modificaciones=[{"pedido_detalle_id": detalle_id, "columna_key": "total"}],
            modificado_por="usuario_produccion",
            rol_modificador="PRODUCCION_ELRAYO",
        )

        assert resultado["success"] is True
        assert resultado["modificaciones_guardadas"] == 1

        merge_calls = [c for c in cursor.execute.call_args_list if "MERGE" in c.args[0]]
        assert len(merge_calls) == 1
        sql, params = merge_calls[0].args
        assert "rol_modificador" in sql
        assert "PRODUCCION_ELRAYO" in params
        assert detalle_id in params
        conn.commit.assert_called_once()

    def test_no_rompe_si_migracion_no_corrio(self, _mock_audit_cls):
        """tiene_rol=False (columna no existe todavía): el MERGE se arma sin
        rol_modificador y la modificación se guarda igual."""
        pedido_id = str(uuid.uuid4())
        detalle_id = str(uuid.uuid4())

        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.side_effect = [
            (pedido_id,),
            (0,),  # tiene_valores -> False
            (0,),  # tiene_rol -> False
            (detalle_id,),
        ]

        repo = PedidoDetalleRepository(conn)
        resultado = repo.guardar_modificaciones_columnas(
            numero_pedido="P-1",
            modificaciones=[{"pedido_detalle_id": detalle_id, "columna_key": "total"}],
            modificado_por="usuario_produccion",
            rol_modificador="PRODUCCION_ELRAYO",
        )

        assert resultado["success"] is True
        merge_calls = [c for c in cursor.execute.call_args_list if "MERGE" in c.args[0]]
        sql, params = merge_calls[0].args
        assert "rol_modificador" not in sql
        assert "PRODUCCION_ELRAYO" not in params


class TestObtenerModificacionesColumnasRolModificador:
    def test_incluye_rol_modificador_de_la_fila(self):
        pedido_id = str(uuid.uuid4())
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.side_effect = [
            (pedido_id,),  # SELECT pedido_id FROM pedido
            (1,),          # tiene_rol -> True
        ]
        cursor.fetchall.return_value = [
            ("detalle-1", "total", "usuario1", None, "PRODUCCION_ELRAYO"),
        ]

        repo = PedidoDetalleRepository(conn)
        resultado = repo.obtener_modificaciones_columnas("P-1")

        assert resultado["success"] is True
        assert resultado["modificaciones"][0]["rol_modificador"] == "PRODUCCION_ELRAYO"

    def test_rol_modificador_none_si_columna_no_existe(self):
        pedido_id = str(uuid.uuid4())
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.side_effect = [
            (pedido_id,),
            (0,),  # tiene_rol -> False
        ]
        cursor.fetchall.return_value = [
            ("detalle-1", "total", "usuario1", None, None),
        ]

        repo = PedidoDetalleRepository(conn)
        resultado = repo.obtener_modificaciones_columnas("P-1")

        assert resultado["modificaciones"][0]["rol_modificador"] is None
