"""
Configuración compartida para tests (fixtures).
"""

import pytest
from fastapi.testclient import TestClient
from src.api_server import app


@pytest.fixture
def client():
    """Cliente de prueba para FastAPI."""
    return TestClient(app)


@pytest.fixture
def api_key():
    """API Key de prueba (solo para tests)."""
    return "test-api-key-12345"


@pytest.fixture
def mock_env(monkeypatch):
    """Fixture para mockear variables de entorno."""
    def _set_env(**kwargs):
        for key, value in kwargs.items():
            monkeypatch.setenv(key, value)
    return _set_env

