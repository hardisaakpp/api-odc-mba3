"""
Tests de delegación de audit_context en PedidoRepository.

Bug corregido: update_costo_detalle/update_total_detalle/update_comentario_detalle
y guardar_modificaciones_columnas (la fachada PedidoRepository que usan los
endpoints de src/endpoints/pedidos/pedidos_edicion.py) no aceptaban ni
reenviaban audit_context a PedidoDetalleRepository. Como resultado,
pedido_audit_log quedaba registrando usuario="SYSTEM"/origen="LEGACY" para
cada edición de costo/total/comentario, en vez del usuario real (email) que
hizo el cambio. La columna pedido_detalle.modificado_por sí quedaba bien
(vía el parámetro modificado_por, separado), lo que ocultaba el problema en
una revisión superficial.
"""

from unittest.mock import MagicMock

from src.database.repositories.pedido_repository import PedidoRepository
from src.utils.audit_context import AuditContext, ORIGEN_WEB


def _fake_audit():
    return AuditContext(usuario="carlos.ortiz@mabel.com", origen=ORIGEN_WEB, ip_origen="10.0.0.5")


class TestDelegacionAuditContext:
    def test_update_costo_detalle_reenvia_audit_context(self):
        conn = MagicMock()
        repo = PedidoRepository(conn)
        repo.detalle_repo = MagicMock()
        audit = _fake_audit()

        repo.update_costo_detalle("detalle-1", 10.0, modificado_por="carlos.ortiz@mabel.com", audit_context=audit)

        repo.detalle_repo.update_costo.assert_called_once_with("detalle-1", 10.0, "carlos.ortiz@mabel.com", audit)

    def test_update_total_detalle_reenvia_audit_context(self):
        conn = MagicMock()
        repo = PedidoRepository(conn)
        repo.detalle_repo = MagicMock()
        audit = _fake_audit()

        repo.update_total_detalle("detalle-1", 99.5, modificado_por="carlos.ortiz@mabel.com", audit_context=audit)

        repo.detalle_repo.update_total.assert_called_once_with("detalle-1", 99.5, "carlos.ortiz@mabel.com", audit)

    def test_update_comentario_detalle_reenvia_audit_context(self):
        conn = MagicMock()
        repo = PedidoRepository(conn)
        repo.detalle_repo = MagicMock()
        audit = _fake_audit()

        repo.update_comentario_detalle("detalle-1", "obs", modificado_por="carlos.ortiz@mabel.com", audit_context=audit)

        repo.detalle_repo.update_comentario.assert_called_once_with("detalle-1", "obs", "carlos.ortiz@mabel.com", audit)

    def test_guardar_modificaciones_columnas_reenvia_audit_context(self):
        conn = MagicMock()
        repo = PedidoRepository(conn)
        repo.detalle_repo = MagicMock()
        audit = _fake_audit()
        modificaciones = [{"pedido_detalle_id": "detalle-1", "columna_key": "total"}]

        repo.guardar_modificaciones_columnas(
            "P-1", modificaciones, modificado_por="carlos.ortiz@mabel.com",
            rol_modificador="ODCSAP", audit_context=audit,
        )

        repo.detalle_repo.guardar_modificaciones_columnas.assert_called_once_with(
            "P-1", modificaciones, "carlos.ortiz@mabel.com", "ODCSAP", audit
        )

    def test_update_total_detalle_funciona_sin_audit_context(self):
        """audit_context sigue siendo opcional: no debe romper llamadores
        legacy que aún no lo pasan (compatibilidad hacia atrás)."""
        conn = MagicMock()
        repo = PedidoRepository(conn)
        repo.detalle_repo = MagicMock()

        repo.update_total_detalle("detalle-1", 99.5, modificado_por="carlos.ortiz@mabel.com")

        repo.detalle_repo.update_total.assert_called_once_with("detalle-1", 99.5, "carlos.ortiz@mabel.com", None)
