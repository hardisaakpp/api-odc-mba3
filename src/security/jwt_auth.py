"""
Autenticación JWT para integración con SCNexus.Core.

Este módulo valida tokens JWT emitidos por el Core y extrae
información del usuario, roles y permisos.
"""

import logging
from typing import Optional, Dict, Any, List
import jwt
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.config import JWT_SECRET, JWT_ISSUER, JWT_AUDIENCE, ENVIRONMENT

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
        
        # Log resumido de autenticación
        username = current_user.get('username', 'unknown')
        logger.debug(f"✅ Token JWT válido para usuario: {username}")
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


# Mapeo de roles del Core a permisos locales.
# El JWT del Core solo incluye roles, no los permisos expandidos de cada rol.
# Este mapeo debe mantenerse sincronizado con la configuración de roles en SCNexus Core.
_ROLE_PERMISSIONS: Dict[str, List[str]] = {
    'Compras-Mabel': ['mabel.view'],
    'Compras-Rayo':  ['odcsap.view'],
}


def _extract_permissions(data: Dict[str, Any]) -> list:
    """
    Extrae permisos del token JWT.

    Busca claims relacionados con permisos. Si el JWT no incluye permisos
    explícitos, los deriva desde los roles usando _ROLE_PERMISSIONS.
    """
    permissions = []

    # Buscar en diferentes formatos posibles
    permission_keys = [
        'permission',
        'permissions',
        'Permission',
        'Permissions',
        'http://schemas.microsoft.com/ws/2008/06/identity/claims/role',
    ]

    # Primero buscar en claves específicas
    for key in permission_keys:
        if key in data:
            value = data[key]
            if isinstance(value, list):
                permissions.extend(value)
            elif isinstance(value, str):
                permissions.append(value)

    # También buscar en cualquier clave que contenga 'permission' (case insensitive)
    for key, value in data.items():
        if 'permission' in key.lower() and key not in permission_keys:
            if isinstance(value, list):
                permissions.extend(value)
            elif isinstance(value, str):
                permissions.append(value)

    # Si el JWT no trae permisos explícitos, derivarlos desde los roles
    if not permissions:
        roles = _extract_roles(data)
        for role in roles:
            permissions.extend(_ROLE_PERMISSIONS.get(role, []))
        if permissions:
            logger.debug(f"🔑 Permisos derivados desde roles {roles}: {permissions}")
        else:
            logger.debug(f"🔍 No se encontraron permisos en el token ni roles mapeados. Claves: {list(data.keys())}")

    return list(set(permissions))


def require_permission(permission_key: str, legacy_permission: Optional[str] = None):
    """
    Dependency factory para validar permisos específicos.
    
    Soporta backward compatibility: si el usuario no tiene el permiso específico,
    puede usar un permiso legacy (temporal durante la transición).
    
    Uso:
        @app.get("/endpoint")
        async def my_endpoint(
            user: Dict = Depends(verify_jwt_token),
            _: None = Depends(require_permission('mabel.view'))
        ):
            ...
    
    Args:
        permission_key: Clave del permiso requerido (específico)
        legacy_permission: Permiso legacy para backward compatibility (opcional)
        
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
        roles = user.get('roles', [])
        username = user.get('username', 'unknown')
        
        # ✅ Permitir acceso automático a usuarios con rol 'Admin'
        is_admin = 'Admin' in roles or 'Admin' in permissions
        if is_admin:
            return
        
        # Verificar permiso específico primero
        has_specific = permission_key in permissions
        
        # Si no tiene el específico y hay legacy, verificar legacy
        has_legacy = False
        if not has_specific and legacy_permission:
            has_legacy = legacy_permission in permissions
            if has_legacy:
                logger.warning(
                    f"⚠️ [BACKWARD COMPAT] Usuario {username} tiene permiso legacy '{legacy_permission}' "
                    f"pero no tiene '{permission_key}'. Considerar migrar permisos en el Core."
                )
        
        if not (has_specific or has_legacy):
            logger.warning(
                f"❌ Permiso denegado: usuario {username} "
                f"intentó acceder sin permiso '{permission_key}'"
                + (f" ni '{legacy_permission}'" if legacy_permission else "")
            )
            if ENVIRONMENT == "development":
                logger.debug(f"🔍 [DEBUG PERMISSION] Permisos disponibles: {permissions}")
            raise HTTPException(
                status_code=403,
                detail=f"Permiso denegado: se requiere '{permission_key}'. Permisos disponibles: {permissions}"
            )
    
    return permission_checker


def require_any_permission(permission_keys: List[str]):
    """
    Dependency factory que permite acceso si el usuario tiene AL MENOS UNO de los permisos.

    Usado para rutas que aplican a EL RAYO (odcsap.view) o MABEL (mabel.view).

    Uso:
        Depends(require_any_permission(['odcsap.view', 'mabel.view']))

    Args:
        permission_keys: Lista de permisos; basta con tener uno.

    Returns:
        Dependency que valida que el usuario tenga al menos uno de los permisos.
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
        roles = user.get('roles', [])
        username = user.get('username', 'unknown')
        is_admin = 'Admin' in roles or 'Admin' in permissions
        if is_admin:
            return
        has_any = any(p in permissions for p in permission_keys)
        if not has_any:
            logger.warning(
                f"❌ Permiso denegado: usuario {username} requiere uno de {permission_keys}"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Permiso denegado: se requiere uno de {permission_keys}. Permisos: {permissions}"
            )
    return permission_checker
