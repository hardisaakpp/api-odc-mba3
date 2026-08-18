"""
Tests para el control de acceso de los endpoints de edición de detalle de
pedido (costo/total/comentario/modificaciones-columnas).

Antes de este fix, estos 4 endpoints solo exigían un JWT válido
(verify_jwt_token) sin verificar odcsap.view/produccion-elrayo.view: el
docstring decía literalmente "Cualquier usuario autenticado puede editar".
El único control de acceso vivía en el frontend (router.ts / markup de
CargarPlantillaView.vue), no en el servidor.
"""

from unittest.mock import MagicMock, patch

import pytest  # type: ignore[reportMissingImports]
from fastapi import Request
from fastapi.testclient import TestClient

from src.api_server import app
from src.security.jwt_auth import verify_jwt_token

_DETALLE_ID = "11111111-1111-1111-1111-111111111111"
_NUMERO_PEDIDO = "P-TEST"

ENDPOINTS_ESCRITURA = [
    ("PATCH", f"/api/pedidos/{_NUMERO_PEDIDO}/detalle/{_DETALLE_ID}/costo", {"costo_doc_sin_iva": 10.0}),
    ("PATCH", f"/api/pedidos/{_NUMERO_PEDIDO}/detalle/{_DETALLE_ID}/total", {"total": 10.0}),
    ("PATCH", f"/api/pedidos/{_NUMERO_PEDIDO}/detalle/{_DETALLE_ID}/comentario", {"comentario": "obs"}),
    ("POST", f"/api/pedidos/{_NUMERO_PEDIDO}/modificaciones-columnas",
     {"numero_pedido": _NUMERO_PEDIDO, "modificaciones": [{"pedido_detalle_id": _DETALLE_ID, "columna_key": "total"}]}),
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
        # Replicar el side-effect real: require_permission/require_any_permission
        # validan con hasattr(request.state, "current_user").
        request.state.current_user = user
        return user
    return _override


@pytest.fixture
def client_sin_permiso():
    """Usuario autenticado con un permiso ajeno al módulo (ni odcsap.view ni
    produccion-elrayo.view)."""
    app.dependency_overrides[verify_jwt_token] = _override_verify_jwt_token(permissions=["mabel.view"])
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(verify_jwt_token, None)


@pytest.fixture
def client_con_permiso():
    app.dependency_overrides[verify_jwt_token] = _override_verify_jwt_token(permissions=["odcsap.view"])
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(verify_jwt_token, None)


class TestPermisoRequeridoEdicion:
    @pytest.mark.parametrize("method,url,body", ENDPOINTS_ESCRITURA)
    def test_rechaza_usuario_sin_odcsap_ni_produccion_elrayo(self, client_sin_permiso, method, url, body):
        resp = client_sin_permiso.request(method, url, json=body)
        assert resp.status_code == 403

    @pytest.mark.parametrize("method,url,body", ENDPOINTS_ESCRITURA)
    @patch("src.endpoints.pedidos.pedidos_edicion.get_db_connection_context")
    @patch("src.endpoints.pedidos.pedidos_edicion.PedidoRepository")
    def test_permite_pasar_el_gate_con_odcsap_view(
        self, mock_repo_cls, mock_get_conn, client_con_permiso, method, url, body
    ):
        # El pedido "no existe" (mock): así comprobamos que se llegó a la
        # lógica de negocio (404 pedido_not_found) en vez de quedar cortado
        # en el 403 del permiso.
        mock_repo = MagicMock()
        mock_repo.get_pedido_completo_por_numero.return_value = None
        mock_repo.get_pedido_completo.return_value = None
        mock_repo_cls.return_value = mock_repo
        mock_get_conn.return_value.__enter__.return_value = MagicMock()
        mock_get_conn.return_value.__exit__.return_value = False

        resp = client_con_permiso.request(method, url, json=body)

        assert resp.status_code != 403
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "pedido_not_found"
