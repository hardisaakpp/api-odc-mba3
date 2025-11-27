"""
Módulo de seguridad opcional para la aplicación.

Todas las funcionalidades de seguridad están deshabilitadas por defecto
y se pueden activar mediante variables de entorno.
"""

from .auth import optional_auth, verify_api_key
from .rate_limit import setup_rate_limiting

__all__ = ["optional_auth", "verify_api_key", "setup_rate_limiting"]

