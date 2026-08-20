"""
Tests para AuditLogService.obtener_por_pedido: lectura del historial de
pedido_audit_log (endpoint GET /api/pedidos/{numero_pedido}/audit-log).
"""

from datetime import datetime
from unittest.mock import MagicMock

from src.database.services import audit_log_service
from src.database.services.audit_log_service import AuditLogService


class TestObtenerPorPedido:
    def test_devuelve_registros_mas_reciente_primero(self, monkeypatch):
        monkeypatch.setattr(audit_log_service, "_tabla_existe", True)
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        fecha1 = datetime(2026, 8, 18, 10, 0, 0)
        fecha2 = datetime(2026, 8, 18, 11, 0, 0)
        # El propio SQL ya pide ORDER BY fecha DESC; el fake cursor devuelve
        # las filas ya en ese orden (más reciente primero).
        cursor.fetchall.return_value = [
            ("pedido_detalle", "detalle-1", "UPDATE", "total", "10.0", "20.0",
             "usuario2@mabel.com", fecha2, "WEB", "10.0.0.2", None),
            ("pedido_detalle", "detalle-1", "UPDATE", "total", "5.0", "10.0",
             "usuario1@mabel.com", fecha1, "WEB", "10.0.0.1", None),
        ]

        svc = AuditLogService(conn)
        registros = svc.obtener_por_pedido("pedido-1")

        assert len(registros) == 2
        assert registros[0]["usuario"] == "usuario2@mabel.com"
        assert registros[0]["fecha"] == fecha2.isoformat()
        assert registros[0]["valor_anterior"] == "10.0"
        assert registros[0]["valor_nuevo"] == "20.0"
        assert registros[1]["usuario"] == "usuario1@mabel.com"

        sql, params = cursor.execute.call_args.args
        assert "ORDER BY fecha DESC" in sql
        assert "WHERE pedido_id = ?" in sql
        assert params == (500, "pedido-1")

    def test_devuelve_lista_vacia_si_tabla_no_existe(self, monkeypatch):
        monkeypatch.setattr(audit_log_service, "_tabla_existe", False)
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor

        svc = AuditLogService(conn)
        registros = svc.obtener_por_pedido("pedido-1")

        assert registros == []
        cursor.fetchall.assert_not_called()

    def test_respeta_limit_pasado(self, monkeypatch):
        monkeypatch.setattr(audit_log_service, "_tabla_existe", True)
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []

        svc = AuditLogService(conn)
        svc.obtener_por_pedido("pedido-1", limit=50)

        _, params = cursor.execute.call_args.args
        assert params == (50, "pedido-1")
