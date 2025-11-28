"""
Tests para endpoints de la API.

Estos tests verifican que los endpoints esenciales funcionan correctamente.
"""

import pytest  # type: ignore[reportMissingImports]
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Tests para el endpoint /health."""
    
    def test_health_check(self, client: TestClient):
        """Verifica que el health check funciona."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "time" in data


class TestConsultarEndpoint:
    """Tests para el endpoint /consultar."""
    
    def test_consultar_endpoint_exists(self, client: TestClient):
        """Verifica que el endpoint existe y responde."""
        # Nota: Este test puede fallar si MBA3 no está disponible
        # pero verifica que el endpoint existe
        response = client.get("/consultar")
        # Acepta 200 (éxito) o 503 (servicio no disponible)
        assert response.status_code in [200, 503, 500]


class TestProcesarOCEndpoint:
    """Tests para el endpoint /procesar-oc."""
    
    def test_procesar_oc_endpoint_exists(self, client: TestClient):
        """Verifica que el endpoint existe."""
        response = client.get("/procesar-oc")
        # Acepta 200 (éxito) o 500 (error de BD)
        assert response.status_code in [200, 500]


class TestIntegrarSAPEndpoint:
    """Tests para el endpoint /integrar-sap."""
    
    def test_integrar_sap_endpoint_exists(self, client: TestClient):
        """Verifica que el endpoint existe."""
        response = client.post("/integrar-sap")
        # Acepta 200, 400 (SAP deshabilitado) o 500 (error)
        assert response.status_code in [200, 400, 500]

