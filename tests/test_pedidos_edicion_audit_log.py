"""
Tests para GET /api/pedidos/{numero_pedido}/audit-log: expone el historial
de pedido_audit_log de un pedido (quién cambió qué, cuándo, valor
anterior/nuevo).
"""

from unittest.mock import MagicMock, patch

import pytest  # type: ignore[reportMissingImports]
from fastapi import Request
from fastapi.testclient import TestClient

from src.api_server import app
from src.security.jwt_auth import verify_jwt_token

_NUMERO_PEDIDO = "P-TEST"
_URL = f"/api/pedidos/{_NUMERO_PEDIDO}/audit-log"

_PEDIDO_MOCK = {
    "cabecera": {"pedido_id": "pedido-1", "numero_pedido": _NUMERO_PEDIDO},
    "detalles": [],
}

_REGISTROS_MOCK = [
    {
        "entidad": "pedido_detalle", "entidad_id": "detalle-1", "accion": "UPDATE",
        "campo_modificado": "total", "valor_anterior": "10.0", "valor_nuevo": "20.0",
        "usuario": "usuario2@mabel.com", "fecha": "2026-08-18T11:00:00", "origen": "WEB",
        "ip_origen": "10.0.0.2", "comentario": None,
    },
    {
        "entidad": "pedido_detalle", "entidad_id": "detalle-1", "accion": "UPDATE",
        "campo_modificado": "costo_doc_sin_iva", "valor_anterior": "5.0", "valor_nuevo": "8.0",
        "usuario": "usuario1@mabel.com", "fecha": "2026-08-18T10:00:00", "origen": "WEB",
        "ip_origen": "10.0.0.1", "comentario": None,
    },
]


def _override_verify_jwt_token(permissions, roles=None):
    def _override(request: Request):
        user = {
            "id": "test-user-id",
            "username": "test_user",
            "email": "test@example.com",
            "roles": roles or [],
            "permissions": permissions,
            "raw_claims": {},
        }
        request.state.current_user = user
        return user
    return _override


def _mock_repo_y_audit_svc(mock_repo_cls, mock_audit_cls):
    mock_repo = MagicMock()
    mock_repo.get_pedido_completo_por_numero.return_value = _PEDIDO_MOCK
    mock_repo.get_pedido_completo.return_value = None
    mock_repo_cls.return_value = mock_repo

    mock_audit_svc = MagicMock()
    mock_audit_svc.obtener_por_pedido.return_value = [dict(r) for r in _REGISTROS_MOCK]
    mock_audit_cls.return_value = mock_audit_svc
    return mock_repo, mock_audit_svc


class TestObtenerAuditLogPermisos:
    def test_rechaza_usuario_sin_permiso(self):
        app.dependency_overrides[verify_jwt_token] = _override_verify_jwt_token(permissions=["otro.permiso"])
        try:
            client = TestClient(app)
            resp = client.get(_URL)
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

    @pytest.mark.parametrize("permiso", ["odcsap.view", "mabel.view", "produccion-elrayo.view"])
    @patch("src.endpoints.pedidos.pedidos_edicion.get_db_connection_context")
    @patch("src.endpoints.pedidos.pedidos_edicion.AuditLogService")
    @patch("src.endpoints.pedidos.pedidos_edicion.PedidoRepository")
    def test_permite_los_3_perfiles_del_modulo(
        self, mock_repo_cls, mock_audit_cls, mock_get_conn, permiso
    ):
        _mock_repo_y_audit_svc(mock_repo_cls, mock_audit_cls)
        mock_get_conn.return_value.__enter__.return_value = MagicMock()
        mock_get_conn.return_value.__exit__.return_value = False

        app.dependency_overrides[verify_jwt_token] = _override_verify_jwt_token(permissions=[permiso])
        try:
            client = TestClient(app)
            resp = client.get(_URL)
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)


class TestObtenerAuditLogContenido:
    @patch("src.endpoints.pedidos.pedidos_edicion.get_db_connection_context")
    @patch("src.endpoints.pedidos.pedidos_edicion.AuditLogService")
    @patch("src.endpoints.pedidos.pedidos_edicion.PedidoRepository")
    def test_devuelve_registros_sin_ip_origen(self, mock_repo_cls, mock_audit_cls, mock_get_conn):
        mock_repo, mock_audit_svc = _mock_repo_y_audit_svc(mock_repo_cls, mock_audit_cls)
        mock_get_conn.return_value.__enter__.return_value = MagicMock()
        mock_get_conn.return_value.__exit__.return_value = False

        app.dependency_overrides[verify_jwt_token] = _override_verify_jwt_token(permissions=["odcsap.view"])
        try:
            client = TestClient(app)
            resp = client.get(_URL)
            body = resp.json()

            assert resp.status_code == 200
            assert body["numero_pedido"] == _NUMERO_PEDIDO
            assert len(body["registros"]) == 2
            assert body["registros"][0]["usuario"] == "usuario2@mabel.com"
            assert "ip_origen" not in body["registros"][0]
            mock_audit_svc.obtener_por_pedido.assert_called_once_with("pedido-1")
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

    @patch("src.endpoints.pedidos.pedidos_edicion.get_db_connection_context")
    @patch("src.endpoints.pedidos.pedidos_edicion.AuditLogService")
    @patch("src.endpoints.pedidos.pedidos_edicion.PedidoRepository")
    def test_oculta_cambios_de_costo_a_solo_produccion_elrayo(
        self, mock_repo_cls, mock_audit_cls, mock_get_conn
    ):
        """RN-03: produccion-elrayo.view sin odcsap.view/mabel.view no debe ver
        el registro de auditoría de un cambio de costo_doc_sin_iva."""
        _mock_repo_y_audit_svc(mock_repo_cls, mock_audit_cls)
        mock_get_conn.return_value.__enter__.return_value = MagicMock()
        mock_get_conn.return_value.__exit__.return_value = False

        app.dependency_overrides[verify_jwt_token] = _override_verify_jwt_token(permissions=["produccion-elrayo.view"])
        try:
            client = TestClient(app)
            resp = client.get(_URL)
            body = resp.json()

            assert resp.status_code == 200
            campos = [r["campo_modificado"] for r in body["registros"]]
            assert "costo_doc_sin_iva" not in campos
            assert "total" in campos
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

    @patch("src.endpoints.pedidos.pedidos_edicion.get_db_connection_context")
    @patch("src.endpoints.pedidos.pedidos_edicion.AuditLogService")
    @patch("src.endpoints.pedidos.pedidos_edicion.PedidoRepository")
    def test_no_oculta_costo_si_ademas_tiene_odcsap_view(
        self, mock_repo_cls, mock_audit_cls, mock_get_conn
    ):
        """Si el usuario tiene además odcsap.view, no aplica el filtro RN-03
        (mismo criterio que es_solo_produccion_el_rayo)."""
        _mock_repo_y_audit_svc(mock_repo_cls, mock_audit_cls)
        mock_get_conn.return_value.__enter__.return_value = MagicMock()
        mock_get_conn.return_value.__exit__.return_value = False

        app.dependency_overrides[verify_jwt_token] = _override_verify_jwt_token(
            permissions=["produccion-elrayo.view", "odcsap.view"]
        )
        try:
            client = TestClient(app)
            resp = client.get(_URL)
            body = resp.json()

            campos = [r["campo_modificado"] for r in body["registros"]]
            assert "costo_doc_sin_iva" in campos
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)
