"""
Módulo de seguridad para la aplicación.

Autenticación JWT y rate limiting. Auth por API Key (auth.py) fue removido
por no estar en uso; los endpoints usan verify_jwt_token y require_permission.
"""

from .rate_limit import setup_rate_limiting
from .jwt_auth import verify_jwt_token, require_permission

__all__ = [
    "setup_rate_limiting",
    "verify_jwt_token",
    "require_permission",
]

