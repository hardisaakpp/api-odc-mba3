"""
Endpoints de autenticación y autorización.

Proporciona información del usuario autenticado incluyendo roles,
permisos y capacidades para control de UI en el frontend.
"""

import logging
from typing import Dict, Any
from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse

from src.security.jwt_auth import verify_jwt_token

logger = logging.getLogger(__name__)

# Exportar función principal para el linter
__all__ = ["register_auth_endpoints"]


def _map_permissions_to_capabilities(permissions: list, roles: list) -> Dict[str, bool]:
    """
    Mapea permisos y roles a capacidades (capabilities) para el frontend.
    
    Las capabilities son booleanos simples que indican si el usuario
    puede realizar una acción específica. La UI usa estas capabilities
    para decidir qué botones/acciones mostrar.
    
    Regla mental: Si una capacidad no existe, el botón no existe.
    No se deshabilita, no se oculta por CSS, no se renderiza.
    
    Args:
        permissions: Lista de permisos del usuario
        roles: Lista de roles del usuario
        
    Returns:
        Diccionario con capabilities booleanas
    """
    # Normalizar permisos y roles a listas de strings
    perms = [str(p).lower() for p in permissions] if permissions else []
    user_roles = [str(r).lower() for r in roles] if roles else []
    
    # Verificar si es Admin (acceso total)
    is_admin = any('admin' in r for r in user_roles) or any('admin' in p for p in perms)
    
    # Helper para verificar permiso (con backward compatibility temporal)
    def has_permission(specific_perm: str, legacy_perm: str = None) -> bool:
        """
        Verifica si el usuario tiene un permiso específico.
        
        Args:
            specific_perm: Permiso específico (ej: 'mba3-consultas.plantillas.upload')
            legacy_perm: Permiso legacy para backward compatibility (opcional)
        """
        # Buscar permiso específico
        has_specific = any(specific_perm.lower() in p for p in perms)
        
        # Si no tiene el específico y hay legacy, verificar legacy (backward compatibility)
        if not has_specific and legacy_perm:
            has_legacy = any(legacy_perm.lower() in p for p in perms)
            if has_legacy:
                logger.debug(
                    f"⚠️ [BACKWARD COMPAT] Usuario tiene permiso legacy '{legacy_perm}' "
                    f"pero no tiene '{specific_perm}'. Considerar migrar permisos en el Core."
                )
            return has_legacy
        
        return has_specific
    
    # Mapeo de permisos específicos a capabilities
    # IMPORTANTE: Cada capability mapea a un permiso específico por intención de negocio
    # Las capabilities NO son mutuamente excluyentes - un usuario puede tener múltiples
    capabilities = {
        # Capability: Subir plantillas Excel
        # Permiso específico: mba3-consultas.plantillas.upload
        # Backward compatibility: mba3-consultas.proceso.execute (temporal)
        "can_upload_templates": is_admin or has_permission(
            'mba3-consultas.plantillas.upload',
            legacy_perm='mba3-consultas.proceso.execute'
        ),
        
        # Capability: Ver plantillas y pedidos
        # Permiso específico: mba3-consultas.plantillas.view
        # Backward compatibility: mba3-consultas.facturas.view (temporal)
        "can_view_templates": is_admin or has_permission(
            'mba3-consultas.plantillas.view',
            legacy_perm='mba3-consultas.facturas.view'
        ),
        
        # Capability: Operar pedidos (redistribuir, confirmar, exportar, etc.)
        # Permiso específico: mba3-consultas.pedidos.operate
        # Backward compatibility: mba3-consultas.proceso.execute (temporal)
        # NOTA: Esta capability es independiente de can_upload_templates
        # Un usuario puede tener ambas, solo una, o ninguna
        "can_operate_pedidos": is_admin or has_permission(
            'mba3-consultas.pedidos.operate',
            legacy_perm='mba3-consultas.proceso.execute'
        ),
    }
    
    # Logging de debug solo en desarrollo
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"🔍 [CAPABILITIES] Permisos: {permissions}")
        logger.debug(f"🔍 [CAPABILITIES] Roles: {roles}")
        logger.debug(f"🔍 [CAPABILITIES] Is Admin: {is_admin}")
        logger.debug(f"🔍 [CAPABILITIES] Capabilities mapeadas: {capabilities}")
    
    return capabilities


def register_auth_endpoints(app: FastAPI):
    """
    Registra los endpoints de autenticación en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
    @app.get("/api/auth/me", tags=["Autenticación"])
    async def get_current_user(
        user: Dict[str, Any] = Depends(verify_jwt_token)
    ):
        """
        Obtiene información del usuario autenticado actual.
        
        Este endpoint es la **fuente de verdad única** para el frontend.
        El frontend debe llamar a este endpoint al iniciar la app y usar
        las capabilities para decidir qué UI mostrar.
        
        **Headers requeridos:**
        - `Authorization: Bearer {token}` - Token JWT válido
        
        **Respuesta exitosa (200):**
        ```json
        {
          "user": {
            "id": "123",
            "username": "juan.perez",
            "email": "juan@example.com"
          },
          "roles": ["EL_RAYO_OPERADOR"],
          "permissions": [
            "mba3-consultas.plantillas.upload",
            "mba3-consultas.plantillas.view",
            "mba3-consultas.pedidos.operate"
          ],
          "capabilities": {
            "can_upload_templates": false,
            "can_view_templates": true,
            "can_operate_pedidos": true
          }
        }
        ```
        
        **⚠️ IMPORTANTE PARA EL FRONTEND:**
        
        El frontend debe usar **SOLO** el campo `capabilities` para decidir qué UI mostrar.
        
        Los campos `permissions` y `roles` se incluyen **SOLO para auditoría y debugging**.
        **NO deben usarse para lógica de UI.**
        
        **Regla mental para el frontend:**
        > La UI no depende del usuario ni del modo, depende de capacidades.
        > Si una capacidad no existe, el botón no existe.
        
        No se deshabilita, no se oculta por CSS, no se valida por nombre de empresa.
        **No se renderiza.**
        
        **Ejemplo correcto:**
        ```tsx
        // ✅ CORRECTO: Usar capabilities
        {capabilities.can_upload_templates && <Button>Subir Excel</Button>}
        
        // ❌ INCORRECTO: No usar permissions directamente
        {permissions.includes('mba3-consultas.plantillas.upload') && <Button>...</Button>}
        ```
        """
        try:
            # Extraer información del usuario
            user_info = {
                "id": user.get("id"),
                "username": user.get("username"),
                "email": user.get("email")
            }
            
            # Extraer roles y permisos
            roles = user.get("roles", [])
            permissions = user.get("permissions", [])
            
            # Mapear permisos a capabilities
            capabilities = _map_permissions_to_capabilities(permissions, roles)
            
            # Construir respuesta
            response_data = {
                "user": user_info,
                "roles": roles,
                "permissions": permissions,
                "capabilities": capabilities
            }
            
            logger.debug(f"✅ [AUTH/ME] Usuario: {user_info.get('username')}, Capabilities: {capabilities}")
            
            return JSONResponse(status_code=200, content=response_data)
            
        except Exception as e:
            logger.error(f"Error al obtener información del usuario: {e}", exc_info=True)
            raise
