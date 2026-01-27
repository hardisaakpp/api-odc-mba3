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
        # Capability: Subir plantillas Excel.
        # Permiso específico: mba3-consultas.plantillas.upload
        # Backward compatibility: mba3-consultas.proceso.execute (temporal)
        "can_upload_templates": is_admin or has_permission(
            'mba3-consultas.plantillas.upload',
            legacy_perm='mba3-consultas.proceso.execute'
        ),
        # Capability: Botón "Cargar Plantilla Excel" (alias).
        "can_cargar_plantilla_excel": is_admin or has_permission(
            'mba3-consultas.plantillas.upload',
            legacy_perm='mba3-consultas.proceso.execute'
        ),
        # Capability: Ver plantillas y pedidos
        # Permiso específico: mba3-consultas.plantillas.view
        "can_view_templates": is_admin or has_permission(
            'mba3-consultas.plantillas.view',
            legacy_perm='mba3-consultas.facturas.view'
        ),
        # Capability: Operar pedidos (redistribuir, exportar, Descargar para MBA)
        # Permiso específico: mba3-consultas.pedidos.operate
        "can_operate_pedidos": is_admin or has_permission(
            'mba3-consultas.pedidos.operate',
            legacy_perm='mba3-consultas.proceso.execute'
        ),
        # Capability: Ver botón "Gestión ODC SAP" en el sidebar.
        # Única responsabilidad: solo el permiso odc.view habilita visibilidad y acceso.
        # Sin admin override ni otros permisos.
        "can_view_odc_sap": has_permission('odc.view'),
        # Capability: Ver botón "Gestionar Pedido". Solo permiso odcsap.view.
        # No afecta al sidebar ni a otros botones.
        "can_manage_order": has_permission('odcsap.view'),
        # Capability: Ver botón/link "Listado de Pedidos". Solo permiso odcsap.view.
        # No afecta al sidebar ni a otros botones.
        "can_view_order_list": has_permission('odcsap.view'),
        # Capability: Ver órdenes de compra (ODC). Solo admin.
        "can_view_odc": is_admin,
        # Capability: Revisar pedido (no hay botón en UI; se mantiene por compatibilidad).
        "can_review_pedido": (
            is_admin or
            has_permission('mba3-consultas.plantillas.view', legacy_perm='mba3-consultas.facturas.view') or
            has_permission('mba3-consultas.pedidos.operate', legacy_perm='mba3-consultas.proceso.execute')
        ),
        # Capability: Confirmar pedido.
        # Frontend: can_confirm_pedido SOLO para "Confirmar"; can_operate_pedidos para el resto.
        "can_confirm_pedido": (
            is_admin or
            has_permission('mba3-consultas.pedidos.operate', legacy_perm='mba3-consultas.proceso.execute') or
            has_permission('mba3-consultas.plantillas.view', legacy_perm='mba3-consultas.facturas.view')
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
    @app.get("/api/Auth/me", tags=["Autenticación"])  # Alias: mismo contenido, incluye capabilities
    async def get_current_user(
        user: Dict[str, Any] = Depends(verify_jwt_token)
    ):
        """
        Obtiene información del usuario autenticado actual.
        
        Este endpoint es la **fuente de verdad única** para el frontend.
        El frontend debe llamar a este endpoint al iniciar la app y usar
        las capabilities para decidir qué UI mostrar.
        
        **⚠️ Cuándo llamar a /api/auth/me:**
        - Al **iniciar la app** (p. ej. en initializeAuth).
        - Tras **login** y al **restaurar sesión** (token en localStorage).
        - Si no se llama (o falla 401), `capabilities` queda sin cargar y botones
          como "Cargar Plantilla Excel" no se mostrarán aunque el backend los permita.
        
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
            "can_upload_templates": true,
            "can_cargar_plantilla_excel": true,
            "can_view_templates": true,
            "can_operate_pedidos": true,
            "can_view_odc_sap": false,
            "can_manage_order": false,
            "can_view_order_list": false,
            "can_view_odc": false,
            "can_review_pedido": true,
            "can_confirm_pedido": true
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
        {capabilities.can_cargar_plantilla_excel && <Button>Cargar Plantilla Excel</Button>}
        
        // ❌ INCORRECTO: No usar permissions directamente
        {permissions.includes('mba3-consultas.plantillas.upload') && <Button>...</Button>}
        ```
        
        **Pantalla detalle pedido** (`/mba3-consultas/pedidos/{id}`):
        - "Cargar Plantilla Excel": `capabilities.can_cargar_plantilla_excel`
        - Sidebar "Gestión ODC SAP": `capabilities.can_view_odc_sap` (true solo si permiso `odc.view`; sin admin override)
        - Redistribuir, Exportar, Descargar para MBA: `capabilities.can_operate_pedidos`
        - Botón "Confirmar": `capabilities.can_confirm_pedido`

        **Botones "Gestionar Pedido" y "Listado de Pedidos":**
        - "Gestionar Pedido": `capabilities.can_manage_order` (true solo si permiso `odcsap.view`)
        - "Listado de Pedidos": `capabilities.can_view_order_list` (true solo si permiso `odcsap.view`)
        """
        try:
            # Extraer roles y permisos
            roles = user.get("roles", [])
            permissions = user.get("permissions", [])

            # Mapear permisos a capabilities (SIEMPRE debe ejecutarse)
            capabilities = _map_permissions_to_capabilities(permissions, roles)

            # Validar que capabilities se calculó correctamente
            if not isinstance(capabilities, dict):
                logger.error(f"❌ [AUTH/ME] ERROR: capabilities no es un dict, es: {type(capabilities)}")
                capabilities = {}

            # user_info: compatible con Core (userName, fullName) y con permisos/roles dentro de user
            # para que el frontend que usa data.user?.permissions y data.capabilities funcione sin cambios
            username_val = user.get("username") or user.get("userName")
            user_info = {
                "id": user.get("id"),
                "username": username_val,
                "userName": username_val,
                "email": user.get("email"),
                "fullName": user.get("fullName") or username_val or "",
                "roles": roles,
                "permissions": permissions,
            }

            # Construir respuesta - SIEMPRE incluir capabilities (Opción A: requerido por el frontend)
            response_data = {
                "user": user_info,
                "roles": roles,
                "permissions": permissions,
                "capabilities": capabilities,
            }
            
            # Logging detallado para debugging
            username = user_info.get('username', 'unknown')
            logger.info(
                f"✅ [AUTH/ME] Usuario: {username}, "
                f"Roles: {len(roles)}, Permisos: {len(permissions)}, "
                f"Capabilities: {len(capabilities)}"
            )
            logger.debug(f"🔍 [AUTH/ME] Capabilities detalladas: {capabilities}")
            
            # Validar que la respuesta incluye capabilities antes de enviar
            if "capabilities" not in response_data:
                logger.error("❌ [AUTH/ME] ERROR CRÍTICO: capabilities no está en response_data")
                # Forzar inclusión de capabilities vacías si falta
                response_data["capabilities"] = capabilities if capabilities else {}
            
            return JSONResponse(status_code=200, content=response_data)
            
        except Exception as e:
            logger.error(f"❌ [AUTH/ME] Error al obtener información del usuario: {e}", exc_info=True)
            # En caso de error, devolver respuesta con capabilities vacías para no romper el frontend
            err_roles = user.get("roles", []) if user else []
            err_perms = user.get("permissions", []) if user else []
            err_username = (user.get("username") or user.get("userName")) if user else None
            error_response = {
                "user": {
                    "id": user.get("id") if user else None,
                    "username": err_username,
                    "userName": err_username,
                    "email": user.get("email") if user else None,
                    "fullName": (user.get("fullName") or err_username or "") if user else "",
                    "roles": err_roles,
                    "permissions": err_perms,
                },
                "roles": err_roles,
                "permissions": err_perms,
                "capabilities": {},
            }
            logger.warning("⚠️ [AUTH/ME] Devolviendo respuesta con capabilities vacías debido a error")
            return JSONResponse(status_code=200, content=error_response)
