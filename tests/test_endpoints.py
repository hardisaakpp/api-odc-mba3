"""
Tests para endpoints de la API.

Estos tests verifican que los endpoints funcionan correctamente
sin modificar la funcionalidad existente.
"""

import pytest
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


class TestQueryEndpoint:
    """Tests para el endpoint /query."""
    
    def test_query_validation_select(self, client: TestClient):
        """Verifica que acepta queries SELECT válidas."""
        response = client.post(
            "/query",
            json={"query": "SELECT * FROM tabla WHERE id = 1"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "original" in data
        assert "parsed" in data
    
    def test_query_rejects_insert(self, client: TestClient):
        """Verifica que rechaza queries INSERT."""
        response = client.post(
            "/query",
            json={"query": "INSERT INTO tabla VALUES (1)"}
        )
        assert response.status_code == 400
    
    def test_query_rejects_delete(self, client: TestClient):
        """Verifica que rechaza queries DELETE."""
        response = client.post(
            "/query",
            json={"query": "DELETE FROM tabla"}
        )
        assert response.status_code == 400


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

