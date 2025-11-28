"""
Autenticación opcional mediante API Keys.

Esta funcionalidad está deshabilitada por defecto y se activa
configurando ENABLE_AUTH=true en .env
"""

import os
import logging
from typing import Optional
from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader

from config import ENABLE_AUTH

logger = logging.getLogger(__name__)

# Header para API Key
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Security(api_key_header)
) -> Optional[str]:
    """
    Verifica la API Key si la autenticación está habilitada.
    
    Si ENABLE_AUTH=false, retorna None (no requiere autenticación).
    Si ENABLE_AUTH=true, valida la API Key.
    
    Args:
        request: Request de FastAPI
        api_key: API Key del header X-API-Key
        
    Returns:
        API Key si es válida, None si auth está deshabilitado
        
    Raises:
        HTTPException: Si auth está habilitado y la key es inválida
    """
    # Si la autenticación está deshabilitada, permitir acceso
    if not ENABLE_AUTH:
        return None
    
    # Obtener API Key esperada desde variables de entorno
    expected_api_key = os.getenv("API_KEY")
    
    if not expected_api_key:
        logger.warning("⚠️ ENABLE_AUTH=true pero API_KEY no está configurada")
        logger.warning("   Deshabilitando autenticación por seguridad")
        return None
    
    # Si no se proporcionó API Key
    client_host = request.client.host if request.client else "unknown"
    if not api_key:
        logger.warning(f"❌ Intento de acceso sin API Key desde {client_host}")
        raise HTTPException(
            status_code=401,
            detail="API Key requerida. Proporciona X-API-Key en el header."
        )
    
    # Verificar API Key
    if api_key != expected_api_key:
        logger.warning(f"❌ API Key inválida desde {client_host}")
        raise HTTPException(
            status_code=403,
            detail="API Key inválida"
        )
    
    logger.debug(f"✅ API Key válida desde {client_host}")
    return api_key


async def optional_auth(
    request: Request,
    api_key: Optional[str] = Security(api_key_header)
) -> Optional[str]:
    """
    Dependency opcional para autenticación.
    
    Esta función es un alias de verify_api_key para mayor claridad.
    Se puede usar en endpoints como:
    
    @app.get("/endpoint")
    async def my_endpoint(
        request: Request,
        auth: Optional[str] = Depends(optional_auth)
    ):
        # Tu código aquí (funciona igual con o sin auth)
        ...
    """
    return await verify_api_key(request, api_key)

