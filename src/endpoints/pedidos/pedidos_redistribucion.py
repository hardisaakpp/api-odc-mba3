"""
Endpoints de redistribución de pedidos.

CHANGELOG:
- 2026-02-06: Agregado soporte para AuditContext (Buenas Prácticas - Sección 3)
"""

from fastapi import FastAPI

from .redistribucion.endpoints_core import register_core_endpoints
from .redistribucion.endpoints_borrador import register_borrador_endpoints
from .redistribucion.endpoints_frontend import register_frontend_endpoints
from .redistribucion.endpoints_proceso import register_proceso_completo_endpoints


def register_redistribucion_endpoints(app: FastAPI):
    """Registra los endpoints de redistribución de pedidos."""
    register_core_endpoints(app)
    register_borrador_endpoints(app)
    register_frontend_endpoints(app)
    register_proceso_completo_endpoints(app)
