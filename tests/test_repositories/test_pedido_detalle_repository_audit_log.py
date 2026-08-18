"""
Tests de regresión: pedido_audit_log debe registrar la identidad real del
usuario (via AuditContext) en las ediciones de total/costo/comentario.

Bug corregido: los endpoints de src/endpoints/pedidos/pedidos_edicion.py
llamaban a estos métodos solo con modificado_por=<string>, sin construir un
AuditContext. PedidoDetalleRepository.update_total (y update_costo/
update_comentario) sí soportan audit_context, pero como nunca llegaba uno,
caían al fallback AuditContext(usuario="SYSTEM", origen="LEGACY") al
registrar en pedido_audit_log — la única tabla append-only capaz de dar el
historial completo (quién, cuándo, valor anterior/nuevo) de una columna que
varios usuarios editan a lo largo del tiempo. pedido_detalle.modificado_por
sí quedaba con el usuario correcto (parámetro separado), lo que ocultaba el
problema en pedido_detalle_modificacion_columna / en la fila viva.
"""

from unittest.mock import MagicMock

from src.database.repositories.pedido.pedido_detalle_repository import PedidoDetalleRepository
from src.database.services import audit_log_service
from src.utils.audit_context import AuditContext, ORIGEN_WEB

# Índices de los parámetros posicionales del INSERT INTO pedido_audit_log
# (pedido_id, entidad, entidad_id, accion, campo_modificado, valor_anterior,
#  valor_nuevo, usuario, origen, ip_origen, comentario)
_IDX_USUARIO = 7
_IDX_ORIGEN = 8
_IDX_IP_ORIGEN = 9


def _cursor_update_total(total_anterior, costo_anterior, pedido_id):
    cursor = MagicMock()
    cursor.fetchone.return_value = (total_anterior, costo_anterior, pedido_id)
    cursor.rowcount = 1
    return cursor


def _audit_log_insert_params(cursor):
    inserts = [c for c in cursor.execute.call_args_list if "INSERT INTO pedido_audit_log" in c.args[0]]
    assert len(inserts) == 1, "se esperaba exactamente un INSERT en pedido_audit_log"
    return inserts[0].args[1]


class TestUpdateTotalAuditLogIdentidad:
    def test_registra_usuario_real_cuando_hay_audit_context(self, monkeypatch):
        monkeypatch.setattr(audit_log_service, "_tabla_existe", True)
        conn = MagicMock()
        cursor = _cursor_update_total(10.0, 5.0, "pedido-1")
        conn.cursor.return_value = cursor
        repo = PedidoDetalleRepository(conn)
        audit = AuditContext(usuario="carlos.ortiz@mabel.com", origen=ORIGEN_WEB, ip_origen="10.0.0.5")

        repo.update_total("detalle-1", 99.5, audit_context=audit)

        params = _audit_log_insert_params(cursor)
        assert params[_IDX_USUARIO] == "carlos.ortiz@mabel.com"
        assert params[_IDX_ORIGEN] == ORIGEN_WEB
        assert params[_IDX_IP_ORIGEN] == "10.0.0.5"

    def test_sin_audit_context_cae_a_system_legacy(self, monkeypatch):
        """Documenta el bug ya corregido en el llamador: si algún caller
        vuelve a omitir audit_context, pedido_audit_log pierde la identidad
        real (aunque modificado_por en pedido_detalle siga bien)."""
        monkeypatch.setattr(audit_log_service, "_tabla_existe", True)
        conn = MagicMock()
        cursor = _cursor_update_total(10.0, 5.0, "pedido-1")
        conn.cursor.return_value = cursor
        repo = PedidoDetalleRepository(conn)

        repo.update_total("detalle-1", 99.5, modificado_por="carlos.ortiz@mabel.com")

        params = _audit_log_insert_params(cursor)
        assert params[_IDX_USUARIO] == "SYSTEM"
        assert params[_IDX_ORIGEN] == "LEGACY"
