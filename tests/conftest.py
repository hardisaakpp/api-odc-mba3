"""
Configuración compartida para tests (fixtures).
"""

import pytest  # type: ignore[reportMissingImports]
from unittest.mock import MagicMock
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
    return _set_env


@pytest.fixture
def sample_factura_mba3():
    """Fixture con datos de ejemplo de factura MBA3."""
    return {
        "CODIGO_FACTURA": "FE-123-TRAYO",
        "EMPRESA": "TRAYO",
        "CODIGO_CLIENTE": "CLI001",
        "FECHA_FACTURA": "2025-01-21",
        "ANULADA": False,
        "NUMERO_PEDIDO_SISTEMA": "176120",
        "NUMERO_ORDEN": 129165,
        "NUMERO_FACTURA": 900125351,
        "TIPO_DOCUMENTO": "FE",
        "ORDEN_COMPRA": "OC001",
        "ORDEN_COMPRA_CLIENTE": "OC_CLI001",
        "Remision_Facturada": True,
        "NumIDFacturaRelacionada": 123,
        "CODIGO_DESPACHO": 456,
        "CODIGO_BODEGA": "BOD001",
        "CONFIRMADO": True,
        "ObjDatosFactura": {
            "GrabarLineasProd": [
                {
                    "Codigo": "5-0012.9",
                    "Nombre": "Producto Test",
                    "Cantidad": 10.0,
                    "PrecioUnitario": 4.65,
                    "TotalLinea": 46.5
                }
            ]
        }
    }


@pytest.fixture
def sample_linea_factura():
    """Fixture con datos de ejemplo de línea de factura."""
    return {
        "Codigo": "5-0012.9",
        "Nombre": "Producto Test",
        "Cantidad": 10.0,
        "PrecioUnitario": 4.65,
        "TotalLinea": 46.5,
        "Descuento": 0.0,
        "Impuesto": 8.37
    }


@pytest.fixture
def sample_sap_info():
    """Fixture con información SAP de ejemplo."""
    return {
        "pack_sap": "X3",
        "unidad_conversion": 4.0,
        "pack_id": "X3"
    }

