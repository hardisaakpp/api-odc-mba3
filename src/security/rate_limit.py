"""
Rate limiting opcional para la aplicación.

Esta funcionalidad está deshabilitada por defecto y se activa
configurando ENABLE_RATE_LIMITING=true en .env
"""

import os
import logging
from typing import Optional

from src.config import ENABLE_RATE_LIMITING

logger = logging.getLogger(__name__)

# Rate limiter (se inicializa solo si está habilitado)
_limiter: Optional[object] = None


def setup_rate_limiting(app):
    """
    Configura rate limiting si está habilitado.
    
    Args:
        app: Instancia de FastAPI
    """
    if not ENABLE_RATE_LIMITING:
        logger.info("ℹ️ Rate limiting deshabilitado (ENABLE_RATE_LIMITING=false)")
        return None
    
    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler  # type: ignore[reportMissingImports]
        from slowapi.util import get_remote_address  # type: ignore[reportMissingImports]
        from slowapi.errors import RateLimitExceeded  # type: ignore[reportMissingImports]
        from slowapi.middleware import SlowAPIMiddleware  # type: ignore[reportMissingImports]

        global _limiter

        # Configurar límites desde variables de entorno
        default_limit = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")

        # Crear limiter con default_limits: sin esto, el Limiter no aplica
        # ningún límite a rutas que no tengan un @limiter.limit(...) explícito
        # (ninguna ruta lo tiene hoy). SlowAPIMiddleware es lo que hace que
        # default_limits se evalúe en cada request sin decorar cada endpoint.
        _limiter = Limiter(key_func=get_remote_address, default_limits=[default_limit])
        app.state.limiter = _limiter
        app.add_middleware(SlowAPIMiddleware)
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

        logger.info(f"✅ Rate limiting habilitado: {default_limit}")
        logger.info("   Configura RATE_LIMIT_DEFAULT en .env para cambiar el límite")
        
        return _limiter
        
    except ImportError:
        logger.warning("⚠️ slowapi no está instalado. Rate limiting no disponible.")
        logger.warning("   Instala con: pip install slowapi")
        return None


def get_limiter():
    """
    Obtiene el rate limiter si está disponible.
    
    Returns:
        Limiter instance o None si está deshabilitado
    """
    return _limiter

