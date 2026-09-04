"""Tests para src/security/rate_limit.py (ENABLE_RATE_LIMITING).

Bug real (2026-09): setup_rate_limiting creaba el Limiter sin default_limits
y sin registrar SlowAPIMiddleware, por lo que ENABLE_RATE_LIMITING=true no
limitaba ninguna ruta (ninguna tiene un @limiter.limit(...) propio). Estos
tests prueban el mecanismo con una app mínima, no la app completa de
src.api_server (que ya se importó con ENABLE_RATE_LIMITING=false al cargar
el módulo).
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.security import rate_limit as rate_limit_module


def test_setup_rate_limiting_habilitado_limita_requests(monkeypatch):
    """Con ENABLE_RATE_LIMITING=true, RATE_LIMIT_DEFAULT debe aplicarse a
    cualquier ruta sin necesidad de decorarla."""
    monkeypatch.setattr(rate_limit_module, "ENABLE_RATE_LIMITING", True)
    monkeypatch.setenv("RATE_LIMIT_DEFAULT", "2/minute")

    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    limiter = rate_limit_module.setup_rate_limiting(app)
    assert limiter is not None

    client = TestClient(app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429


def test_setup_rate_limiting_deshabilitado_no_limita(monkeypatch):
    """Con ENABLE_RATE_LIMITING=false (default), no se agrega ningún límite."""
    monkeypatch.setattr(rate_limit_module, "ENABLE_RATE_LIMITING", False)

    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    limiter = rate_limit_module.setup_rate_limiting(app)
    assert limiter is None

    client = TestClient(app)
    for _ in range(5):
        assert client.get("/ping").status_code == 200
