"""
Autenticación JWT para integración con SCNexus.Core.

Este módulo valida tokens JWT emitidos por el Core y extrae
información del usuario, roles y permisos.
"""

import os
import logging
from typing import Optional, Dict, Any
import jwt
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import JWT_SECRET, JWT_ISSUER, JWT_AUDIENCE

logger = logging.getLogger(__name__)

# Esquema de autenticación Bearer
security = HTTPBearer(auto_error=False)


async def verify_jwt_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Dict[str, Any]:
    """
    Verifica y decodifica un token JWT.
    
    Extrae el token del header Authorization: Bearer <token>
    y valida que sea un JWT válido emitido por el Core.
    
    Args:
        request: Request de FastAPI
        credentials: Credenciales del header Authorization (Bearer token)
        
    Returns:
        Diccionario con información del usuario decodificada del token
        
    Raises:
        HTTPException: Si el token es inválido, expirado o falta
    """
    # Extraer token del header Authorization
    token = None
    
    if credentials:
        token = credentials.credentials
    elif 'Authorization' in request.headers:
        auth_header = request.headers['Authorization']
        try:
            # Formato: "Bearer TOKEN"
            token = auth_header.split(' ')[1] if ' ' in auth_header else None
        except (IndexError, AttributeError):
            token = None
    
    if not token:
        client_host = request.client.host if request.client else "unknown"
        logger.warning(f"❌ Token JWT faltante desde {client_host}")
        raise HTTPException(
            status_code=401,
            detail="Token JWT requerido. Proporciona Authorization: Bearer <token> en el header."
        )
    
    try:
        # Decodificar y validar token
        data = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE
        )
        
        # Extraer información del usuario
        current_user = {
            'id': data.get('http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier'),
            'username': data.get('http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name'),
            'email': data.get('http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress'),
            'roles': _extract_roles(data),
            'permissions': _extract_permissions(data),
            'raw_claims': data  # Para debugging o acceso a otros claims
        }
        
        # Almacenar usuario en el request state (FastAPI)
        request.state.current_user = current_user
        
        logger.debug(f"✅ Token JWT válido para usuario: {current_user.get('username')}")
        return current_user
        
    except jwt.ExpiredSignatureError:
        client_host = request.client.host if request.client else "unknown"
        logger.warning(f"❌ Token JWT expirado desde {client_host}")
        raise HTTPException(
            status_code=401,
            detail="Token JWT ha expirado"
        )
    except jwt.InvalidTokenError as e:
        client_host = request.client.host if request.client else "unknown"
        logger.warning(f"❌ Token JWT inválido desde {client_host}: {e}")
        raise HTTPException(
            status_code=401,
            detail=f"Token JWT inválido: {str(e)}"
        )


def _extract_roles(data: Dict[str, Any]) -> list:
    """
    Extrae roles del token JWT.
    
    Busca claims que contengan 'role' en su nombre.
    
    Args:
        data: Datos decodificados del token
        
    Returns:
        Lista de roles encontrados
    """
    roles = []
    for key, value in data.items():
        if 'role' in key.lower():
            if isinstance(value, list):
                roles.extend(value)
            elif isinstance(value, str):
                roles.append(value)
    return roles


def _extract_permissions(data: Dict[str, Any]) -> list:
    """
    Extrae permisos del token JWT.
    
    Busca claims relacionados con permisos.
    
    Args:
        data: Datos decodificados del token
        
    Returns:
        Lista de permisos encontrados
    """
    permissions = []
    
    # Buscar en diferentes formatos posibles
    permission_keys = [
        'permission',
        'permissions',
        'http://schemas.microsoft.com/ws/2008/06/identity/claims/role'
    ]
    
    for key in permission_keys:
        if key in data:
            value = data[key]
            if isinstance(value, list):
                permissions.extend(value)
            elif isinstance(value, str):
                permissions.append(value)
    
    return permissions


async def optional_jwt_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Optional[Dict[str, Any]]:
    """
    Dependency opcional para autenticación JWT.
    
    Similar a verify_jwt_token pero retorna None si no hay token
    en lugar de lanzar excepción. Útil para endpoints que pueden
    funcionar con o sin autenticación.
    
    Args:
        request: Request de FastAPI
        credentials: Credenciales del header Authorization
        
    Returns:
        Diccionario con información del usuario o None si no hay token
    """
    try:
        return await verify_jwt_token(request, credentials)
    except HTTPException:
        # Si no hay token o es inválido, retornar None (no lanzar excepción)
        return None


def require_permission(permission_key: str):
    """
    Dependency factory para validar permisos específicos.
    
    Uso:
        @app.get("/endpoint")
        async def my_endpoint(
            user: Dict = Depends(verify_jwt_token),
            _: None = Depends(require_permission('mba3_consultas.migrar'))
        ):
            ...
    
    Args:
        permission_key: Clave del permiso requerido
        
    Returns:
        Dependency que valida el permiso
    """
    async def permission_checker(
        request: Request,
        user: Dict[str, Any] = Security(verify_jwt_token)
    ) -> None:
        if not hasattr(request.state, 'current_user'):
            raise HTTPException(
                status_code=401,
                detail="Autenticación requerida"
            )
        
        permissions = user.get('permissions', [])
        
        if permission_key not in permissions:
            username = user.get('username', 'unknown')
            logger.warning(
                f"❌ Permiso denegado: usuario {username} "
                f"intentó acceder sin permiso '{permission_key}'"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Permiso denegado: se requiere '{permission_key}'"
            )
    
    return permission_checker


def require_role(role_name: str):
    """
    Dependency factory para validar roles específicos.
    
    Uso:
        @app.get("/endpoint")
        async def my_endpoint(
            user: Dict = Depends(verify_jwt_token),
            _: None = Depends(require_role('Admin'))
        ):
            ...
    
    Args:
        role_name: Nombre del rol requerido
        
    Returns:
        Dependency que valida el rol
    """
    async def role_checker(
        request: Request,
        user: Dict[str, Any] = Security(verify_jwt_token)
    ) -> None:
        if not hasattr(request.state, 'current_user'):
            raise HTTPException(
                status_code=401,
                detail="Autenticación requerida"
            )
        
        roles = user.get('roles', [])
        
        if role_name not in roles:
            username = user.get('username', 'unknown')
            logger.warning(
                f"❌ Rol denegado: usuario {username} "
                f"intentó acceder sin rol '{role_name}'"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Rol denegado: se requiere rol '{role_name}'"
            )
    
    return role_checker

