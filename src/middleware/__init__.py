"""
Middleware y exception handlers para FastAPI.

Módulos disponibles:
- exception_handlers: Manejo centralizado de excepciones
- request_logging: Logging de tiempo de respuesta y métricas (Buenas Prácticas - Sección 5)
"""

from .exception_handlers import setup_exception_handlers
from .request_logging import setup_request_logging, RequestLoggingMiddleware

__all__ = [
    "setup_exception_handlers",
    "setup_request_logging",
    "RequestLoggingMiddleware",
]

