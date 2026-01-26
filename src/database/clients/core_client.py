"""
Cliente para interactuar con la API de SCNexus.Core (Active Directory).

Este cliente maneja las llamadas a la API del Core, que gestiona la integración
con Active Directory. El Core:
- Gestiona usuarios y roles desde Active Directory
- Asigna permisos a usuarios y roles de AD según las páginas a las que pueden tener acceso
- Emite tokens JWT con los permisos del usuario para autenticación en las aplicaciones

Endpoints principales:
- POST /api/Permissions - Registrar nuevos permisos
- GET /api/Permissions - Obtener permisos existentes
- POST /api/Permissions/assign - Asignar permisos a roles de AD
"""

import logging
import requests
from typing import Optional, Dict, Any, List
from src.config import CORE_API_URL, CORE_API_TIMEOUT

logger = logging.getLogger(__name__)


class CoreAPIClient:
    """
    Cliente para interactuar con la API de SCNexus.Core (Active Directory).
    
    El Core actúa como intermediario entre Active Directory y las aplicaciones:
    - Los usuarios y roles vienen de Active Directory
    - Los permisos se crean y asignan en el Core
    - El Core emite tokens JWT con los permisos del usuario
    """
    
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[int] = None):
        """
        Inicializa el cliente del Core.
        
        Args:
            base_url: URL base del Core (por defecto usa CORE_API_URL de config)
            timeout: Timeout en segundos (por defecto usa CORE_API_TIMEOUT de config)
        """
        self.base_url = (base_url or CORE_API_URL).rstrip('/')
        self.timeout = timeout or CORE_API_TIMEOUT
        self.session = requests.Session()
        
        logger.debug(f"CoreAPIClient inicializado con URL: {self.base_url}")
    
    def _get_headers(self, admin_token: str) -> Dict[str, str]:
        """Genera headers para las peticiones al Core."""
        return {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def register_permission(
        self,
        admin_token: str,
        key: str,
        description: str,
        module: str
    ) -> Optional[Dict[str, Any]]:
        """
        Registra un nuevo permiso en el Core.
        
        Los permisos se asignan luego a roles de Active Directory mediante
        assign_permission_to_role().
        
        Args:
            admin_token: Token JWT de administrador (obtenido del Core)
            key: Clave del permiso (ej: "mba3-consultas.plantillas.upload")
            description: Descripción del permiso
            module: Módulo al que pertenece (ej: "mba3-consultas")
            
        Returns:
            Diccionario con la respuesta del Core (incluye 'id' del permiso) o None si hay error
            
        Raises:
            requests.RequestException: Si hay error en la petición HTTP
        """
        url = f"{self.base_url}/api/Permissions"
        headers = self._get_headers(admin_token)
        
        payload = {
            "key": key,
            "description": description,
            "module": module
        }
        
        try:
            logger.info(f"📤 Registrando permiso en Core (AD): {key}")
            response = self.session.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code in (200, 201):
                result = response.json()
                permission_id = result.get("id")
                logger.info(f"✅ Permiso registrado con ID: {permission_id}")
                return result
            elif response.status_code == 409:
                logger.warning(f"⚠️ Permiso '{key}' ya existe en el Core")
                # Intentar obtener el permiso existente
                return self.get_permission_by_key(admin_token, key)
            else:
                error_msg = f"Error al registrar permiso: {response.status_code}"
                try:
                    error_body = response.json()
                    error_msg = error_body.get("message", error_body.get("error", error_msg))
                except:
                    error_msg = f"{error_msg} - {response.text}"
                
                logger.error(f"❌ {error_msg}")
                raise requests.RequestException(f"{error_msg} (Status: {response.status_code})")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error al registrar permiso '{key}': {e}")
            raise
    
    def get_permission_by_key(
        self,
        admin_token: str,
        key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene un permiso por su clave desde el Core.
        
        Args:
            admin_token: Token JWT de administrador
            key: Clave del permiso a buscar
            
        Returns:
            Diccionario con la información del permiso o None si no se encuentra
        """
        url = f"{self.base_url}/api/Permissions"
        headers = self._get_headers(admin_token)
        
        try:
            logger.debug(f"🔍 Buscando permiso en Core: {key}")
            response = self.session.get(
                url,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                permissions = response.json()
                # Si es una lista, buscar el permiso por key
                if isinstance(permissions, list):
                    for perm in permissions:
                        if perm.get("key") == key:
                            logger.debug(f"✅ Permiso encontrado: ID={perm.get('id')}")
                            return perm
                # Si es un diccionario único
                elif isinstance(permissions, dict) and permissions.get("key") == key:
                    return permissions
                
                logger.warning(f"⚠️ Permiso '{key}' no encontrado en el Core")
                return None
            else:
                logger.error(f"❌ Error al obtener permisos del Core: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error al obtener permiso '{key}': {e}")
            return None
    
    def get_all_permissions(
        self,
        admin_token: str
    ) -> List[Dict[str, Any]]:
        """
        Obtiene todos los permisos registrados en el Core.
        
        Args:
            admin_token: Token JWT de administrador
            
        Returns:
            Lista de permisos
        """
        url = f"{self.base_url}/api/Permissions"
        headers = self._get_headers(admin_token)
        
        try:
            logger.debug("🔍 Obteniendo todos los permisos del Core (AD)")
            response = self.session.get(
                url,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                permissions = response.json()
                if isinstance(permissions, list):
                    logger.debug(f"✅ Se obtuvieron {len(permissions)} permisos del Core")
                    return permissions
                elif isinstance(permissions, dict):
                    return [permissions]
                return []
            else:
                logger.error(f"❌ Error al obtener permisos del Core: {response.status_code}")
                return []
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error al obtener permisos del Core: {e}")
            return []
    
    def assign_permission_to_role(
        self,
        admin_token: str,
        role_name: str,
        permission_id: int
    ) -> bool:
        """
        Asigna un permiso a un rol de Active Directory.
        
        El rol debe existir en Active Directory. El Core gestiona la relación
        entre roles de AD y permisos de la aplicación.
        
        Args:
            admin_token: Token JWT de administrador
            role_name: Nombre del rol de Active Directory (ej: "Ventas", "EL_RAYO_OPERADOR")
            permission_id: ID del permiso a asignar
            
        Returns:
            True si se asignó correctamente, False en caso contrario
        """
        url = f"{self.base_url}/api/Permissions/assign"
        headers = self._get_headers(admin_token)
        
        payload = {
            "roleName": role_name,
            "permissionId": permission_id
        }
        
        try:
            logger.info(f"📤 Asignando permiso ID {permission_id} al rol de AD '{role_name}'")
            response = self.session.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code in (200, 201):
                logger.info(f"✅ Permiso asignado al rol de AD exitosamente")
                return True
            elif response.status_code == 409:
                logger.warning(f"⚠️ Permiso ya está asignado a este rol de AD")
                return True  # Consideramos éxito si ya está asignado
            else:
                error_msg = f"Error al asignar permiso: {response.status_code}"
                try:
                    error_body = response.json()
                    error_msg = error_body.get("message", error_body.get("error", error_msg))
                except:
                    error_msg = f"{error_msg} - {response.text}"
                
                logger.error(f"❌ {error_msg}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error al asignar permiso a rol de AD: {e}")
            return False
