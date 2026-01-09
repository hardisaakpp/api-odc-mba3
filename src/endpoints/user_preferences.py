"""
Endpoints para gestión de preferencias de usuario.
"""

import logging
from typing import Dict
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse

from src.database.repositories.user_preferences_repository import UserPreferencesRepository
from src.database.connection import get_db_connection
from src.security.jwt_auth import verify_jwt_token
from src.models import (
    SavePreferencesRequest,
    PreferencesResponse,
    AllPreferencesResponse,
    TablePreferencesDto,
    SidebarPreferencesDto,
    SaveSidebarPreferencesRequest,
    SidebarPreferencesResponse
)

logger = logging.getLogger(__name__)

# Validar tableId permitidos
VALID_TABLE_IDS = ["despachos", "ordenes-compra", "historial-ordenes", "remisiones", "productos-pedido"]

# Exportar función principal para el linter
__all__ = ["register_user_preferences_endpoints"]


def validate_table_id(table_id: str):
    """Validar que el tableId sea uno de los permitidos"""
    if table_id not in VALID_TABLE_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"tableId inválido. Valores permitidos: {', '.join(VALID_TABLE_IDS)}"
        )
    return table_id


def get_user_id_or_username(user: Dict) -> str:
    """
    Obtiene el ID del usuario, o usa username como fallback.
    
    Esto hace el código más robusto cuando el token JWT no incluye
    el claim 'id' esperado, usando 'username' como identificador alternativo.
    También busca en raw_claims si está disponible.
    
    Args:
        user: Diccionario con información del usuario del JWT
        
    Returns:
        ID del usuario o username como fallback (como string)
        
    Raises:
        HTTPException: Si no hay ni id ni username disponible
    """
    # Logging detallado para diagnóstico
    logger.debug(f"🔍 Buscando user_id. Keys disponibles en user: {list(user.keys())}")
    
    # Intentar obtener id directamente
    user_id = user.get('id')
    if user_id:
        logger.debug(f"✅ user_id encontrado: {user_id}")
        return str(user_id)
    
    # Fallback a username si id no está disponible
    username = user.get('username')
    if username:
        logger.warning(f"⚠️ user.id no disponible, usando username como fallback: {username}")
        return str(username)
    
    # Buscar en raw_claims si está disponible
    raw_claims = user.get('raw_claims', {})
    if raw_claims:
        logger.debug(f"🔍 Buscando en raw_claims. Keys disponibles: {list(raw_claims.keys())[:10]}...")
        
        # Buscar en diferentes claims comunes
        possible_id_keys = [
            'sub',  # Subject (estándar JWT)
            'userId',
            'user_id',
            'id',
            'nameidentifier',
            'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier',
            'http://schemas.microsoft.com/ws/2008/06/identity/claims/nameidentifier',
        ]
        
        for key in possible_id_keys:
            value = raw_claims.get(key)
            if value:
                logger.info(f"✅ user_id encontrado en raw_claims['{key}']: {value}")
                return str(value)
        
        # Buscar username en raw_claims
        possible_username_keys = [
            'name',
            'username',
            'user_name',
            'preferred_username',
            'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name',
            'http://schemas.microsoft.com/ws/2008/06/identity/claims/name',
        ]
        
        for key in possible_username_keys:
            value = raw_claims.get(key)
            if value:
                logger.warning(f"⚠️ user_id no encontrado, usando username de raw_claims['{key}'] como fallback: {value}")
                return str(value)
    
    # Si no se encontró nada, lanzar error con información detallada
    available_keys = list(user.keys())
    logger.error(f"❌ No se pudo obtener user_id. Keys disponibles en user: {available_keys}")
    if raw_claims:
        logger.error(f"   Keys disponibles en raw_claims: {list(raw_claims.keys())[:20]}")
    
    raise HTTPException(
        status_code=401,
        detail=f"No se pudo obtener el ID o username del usuario del token. Keys disponibles: {available_keys}"
    )


def register_user_preferences_endpoints(app: FastAPI):
    """
    Registra los endpoints de preferencias de usuario en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
    # IMPORTANTE: Las rutas específicas deben registrarse ANTES de las rutas con parámetros dinámicos
    # para que FastAPI las procese correctamente
    
    @app.get("/api/users/preferences",
             response_model=AllPreferencesResponse,
             tags=["Preferencias de Usuario"])
    async def get_all_preferences(
        request: Request,
        user: Dict = Depends(verify_jwt_token)
    ):
        """
        Obtiene todas las preferencias del usuario actual.
        
        **Headers requeridos:**
        - `Authorization: Bearer {token}` - Token JWT válido
        
        **Respuesta exitosa (200):**
        ```json
        {
          "preferences": {
            "despachos": {
              "visibleColumns": ["codigo_factura", "numero_factura"],
              "columnOrder": ["codigo_factura", "numero_factura"],
              "filters": {},
              "pageSize": 10
            },
            "ordenes-compra": {
              "visibleColumns": ["oc_id", "fecha_generacion"],
              "columnOrder": ["oc_id", "fecha_generacion"],
              "filters": {},
              "pageSize": 10
            }
          }
        }
        ```
        """
        # Logging para diagnóstico
        logger.info(f"🔍 GET /api/users/preferences: Iniciado")
        logger.debug(f"   User object keys: {list(user.keys()) if user else 'None'}")
        
        # Usar función helper para obtener user_id con fallback a username
        try:
            user_id = get_user_id_or_username(user)
            logger.debug(f"   User ID obtenido: {user_id}")
        except HTTPException as e:
            logger.error(f"❌ Error al obtener user_id: {e.detail}")
            raise
        
        conn = None
        try:
            conn = get_db_connection()
            repository = UserPreferencesRepository(conn)
            all_prefs = repository.get_all_preferences(user_id)
            
            # Convertir a DTOs
            preferences_dict = {
                table_id: TablePreferencesDto(**prefs)
                for table_id, prefs in all_prefs.items()
            }
            
            return AllPreferencesResponse(preferences=preferences_dict)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error al obtener todas las preferencias: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al obtener preferencias: {str(e)}"
            )
        finally:
            if conn:
                conn.close()
    
    @app.get("/api/users/preferences/sidebar",
             response_model=SidebarPreferencesResponse,
             tags=["Preferencias de Usuario"])
    async def get_sidebar_preferences(
        request: Request,
        user: Dict = Depends(verify_jwt_token)
    ):
        """
        Obtiene las preferencias del sidebar para el usuario actual.
        
        **Headers requeridos:**
        - `Authorization: Bearer {token}` - Token JWT válido
        
        **Respuesta exitosa (200):**
        ```json
        {
          "preferences": {
            "collapsed": true
          }
        }
        ```
        
        **Si no existen preferencias:**
        ```json
        {
          "preferences": null
        }
        ```
        """
        # Logging para diagnóstico
        logger.info(f"🔍 GET /api/users/preferences/sidebar: Iniciado")
        logger.debug(f"   User object keys: {list(user.keys()) if user else 'None'}")
        
        # Usar función helper para obtener user_id con fallback a username
        try:
            user_id = get_user_id_or_username(user)
            logger.debug(f"   User ID obtenido: {user_id}")
        except HTTPException as e:
            logger.error(f"❌ Error al obtener user_id: {e.detail}")
            raise
        
        conn = None
        try:
            conn = get_db_connection()
            repository = UserPreferencesRepository(conn)
            preferences = repository.get_sidebar_preferences(user_id)
            
            if preferences:
                return SidebarPreferencesResponse(
                    preferences=SidebarPreferencesDto(**preferences)
                )
            else:
                return SidebarPreferencesResponse(preferences=None)
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error al obtener preferencias del sidebar: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al obtener preferencias del sidebar: {str(e)}"
            )
        finally:
            if conn:
                conn.close()
    
    @app.post("/api/users/preferences/sidebar",
              tags=["Preferencias de Usuario"])
    async def save_sidebar_preferences(
        request_body: SaveSidebarPreferencesRequest,
        request: Request,
        user: Dict = Depends(verify_jwt_token)
    ):
        """
        Guarda o actualiza las preferencias del sidebar.
        
        **Headers requeridos:**
        - `Authorization: Bearer {token}` - Token JWT válido
        - `Content-Type: application/json`
        
        **Body:**
        ```json
        {
          "preferences": {
            "collapsed": false
          }
        }
        ```
        
        **Respuesta exitosa (200):**
        ```json
        {
          "success": true,
          "message": "Preferencias del sidebar guardadas correctamente"
        }
        ```
        """
        # Logging para diagnóstico
        logger.info(f"🔍 POST /api/users/preferences/sidebar: Iniciado")
        logger.debug(f"   User object keys: {list(user.keys()) if user else 'None'}")
        logger.debug(f"   Request body type: {type(request_body)}")
        logger.debug(f"   Request body: {request_body}")
        
        # Usar función helper para obtener user_id con fallback a username
        try:
            user_id = get_user_id_or_username(user)
            logger.debug(f"   User ID obtenido: {user_id}")
        except HTTPException as e:
            logger.error(f"❌ Error al obtener user_id: {e.detail}")
            raise
        
        # Validar datos - el model_validator ya normalizó y validó los datos
        # preferences debería ser un SidebarPreferencesDto después de la validación
        if isinstance(request_body.preferences, SidebarPreferencesDto):
            prefs = request_body.preferences
            logger.debug(f"   Preferences recibidas (SidebarPreferencesDto validado): {prefs}")
        elif isinstance(request_body.preferences, dict):
            # Si todavía es un dict (no debería pasar, pero por seguridad)
            prefs = SidebarPreferencesDto(**request_body.preferences)
            logger.debug(f"   Preferences convertidas desde dict: {prefs}")
        elif request_body.collapsed is not None:
            # Formato alternativo: crear preferences desde collapsed
            prefs = SidebarPreferencesDto(collapsed=request_body.collapsed)
            logger.debug(f"   Preferences creadas desde formato alternativo: {prefs}")
        else:
            raise HTTPException(
                status_code=400,
                detail="Se requiere 'preferences.collapsed' o 'collapsed' en el request"
            )
        
        logger.debug(f"   Collapsed value: {prefs.collapsed} (type: {type(prefs.collapsed)})")
        
        conn = None
        try:
            conn = get_db_connection()
            repository = UserPreferencesRepository(conn)
            
            repository.save_sidebar_preferences(
                user_id,
                prefs.model_dump(exclude_none=True)
            )
            
            return {
                "success": True,
                "message": "Preferencias del sidebar guardadas correctamente"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error al guardar preferencias del sidebar: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al guardar preferencias del sidebar: {str(e)}"
            )
        finally:
            if conn:
                conn.close()
    
    @app.get("/api/users/preferences/{table_id}", 
             response_model=PreferencesResponse,
             tags=["Preferencias de Usuario"])
    async def get_table_preferences(
        table_id: str,
        request: Request,
        user: Dict = Depends(verify_jwt_token)
    ):
        """
        Obtiene las preferencias de una tabla específica para el usuario actual.
        
        **Parámetros:**
        - `table_id`: ID de la tabla (despachos, ordenes-compra, historial-ordenes, remisiones, productos-pedido)
        
        **Headers requeridos:**
        - `Authorization: Bearer {token}` - Token JWT válido
        
        **Respuesta exitosa (200):**
        ```json
        {
          "preferences": {
            "visibleColumns": ["codigo_factura", "numero_factura"],
            "columnOrder": ["codigo_factura", "numero_factura"],
            "filters": {},
            "pageSize": 10
          }
        }
        ```
        
        **Si no existen preferencias:**
        ```json
        {
          "preferences": null
        }
        ```
        """
        validate_table_id(table_id)
        
        # Logging para diagnóstico
        logger.info(f"🔍 GET /api/users/preferences/{table_id}: Iniciado")
        logger.debug(f"   User object keys: {list(user.keys()) if user else 'None'}")
        
        # Usar función helper para obtener user_id con fallback a username
        try:
            user_id = get_user_id_or_username(user)
            logger.debug(f"   User ID obtenido: {user_id}")
        except HTTPException as e:
            logger.error(f"❌ Error al obtener user_id: {e.detail}")
            raise
        
        conn = None
        try:
            conn = get_db_connection()
            repository = UserPreferencesRepository(conn)
            preferences = repository.get_table_preferences(user_id, table_id)
            
            if preferences:
                logger.debug(f"✅ Preferencias encontradas para usuario {user_id}, tabla {table_id}")
                return PreferencesResponse(
                    preferences=TablePreferencesDto(**preferences)
                )
            else:
                logger.debug(f"ℹ️ No se encontraron preferencias para usuario {user_id}, tabla {table_id}")
                return PreferencesResponse(preferences=None)
                
        except HTTPException:
            raise
        except ValueError as ve:
            # Errores de validación/parsing JSON
            logger.error(f"❌ Error de validación al obtener preferencias: {ve}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al parsear preferencias guardadas: {str(ve)}"
            )
        except Exception as e:
            logger.error(f"❌ Error inesperado al obtener preferencias: {e}")
            logger.exception(e)  # Log completo del stack trace
            raise HTTPException(
                status_code=500,
                detail=f"Error al obtener preferencias: {str(e)}"
            )
        finally:
            if conn:
                conn.close()
    
    @app.post("/api/users/preferences/{table_id}",
              tags=["Preferencias de Usuario"])
    async def save_table_preferences(
        table_id: str,
        request_body: SavePreferencesRequest,
        request: Request,
        user: Dict = Depends(verify_jwt_token)
    ):
        """
        Guarda o actualiza las preferencias de una tabla específica.
        
        **Parámetros:**
        - `table_id`: ID de la tabla (despachos, ordenes-compra, historial-ordenes, remisiones, productos-pedido)
        
        **Headers requeridos:**
        - `Authorization: Bearer {token}` - Token JWT válido
        - `Content-Type: application/json`
        
        **Body:**
        ```json
        {
          "preferences": {
            "visibleColumns": ["codigo_factura", "numero_factura", "empresa"],
            "columnOrder": ["codigo_factura", "empresa", "numero_factura"],
            "filters": {},
            "pageSize": 10
          }
        }
        ```
        
        **Respuesta exitosa (200):**
        ```json
        {
          "success": true,
          "message": "Preferencias guardadas correctamente"
        }
        ```
        """
        validate_table_id(table_id)
        
        # Logging para diagnóstico
        logger.info(f"🔍 POST /api/users/preferences/{table_id}: Iniciado")
        logger.debug(f"   User object keys: {list(user.keys()) if user else 'None'}")
        logger.debug(f"   Request body: {request_body}")
        
        # Usar función helper para obtener user_id con fallback a username
        try:
            user_id = get_user_id_or_username(user)
            logger.debug(f"   User ID obtenido: {user_id}")
        except HTTPException as e:
            logger.error(f"❌ Error al obtener user_id: {e.detail}")
            raise
        
        # Validar datos
        prefs = request_body.preferences
        logger.debug(f"   Preferences recibidas: visibleColumns={prefs.visibleColumns}, columnOrder={prefs.columnOrder}")
        
        if not prefs.visibleColumns or not prefs.columnOrder:
            logger.warning(f"⚠️ Intento de guardar preferencias sin visibleColumns o columnOrder")
            raise HTTPException(
                status_code=400,
                detail="visibleColumns y columnOrder son requeridos y no pueden estar vacíos"
            )
        
        if len(prefs.visibleColumns) == 0:
            logger.warning(f"⚠️ Intento de guardar preferencias con visibleColumns vacío")
            raise HTTPException(
                status_code=400,
                detail="Debe haber al menos una columna visible"
            )
        
        conn = None
        try:
            conn = get_db_connection()
            repository = UserPreferencesRepository(conn)
            
            # Convertir a dict para el repositorio
            prefs_dict = prefs.model_dump(exclude_none=True)
            logger.debug(f"   Preferences dict: {prefs_dict}")
            
            repository.save_table_preferences(
                user_id,
                table_id,
                prefs_dict
            )
            
            logger.info(f"✅ Preferencias guardadas exitosamente para usuario {user_id}, tabla {table_id}")
            return {
                "success": True,
                "message": "Preferencias guardadas correctamente"
            }
            
        except HTTPException:
            raise
        except ValueError as ve:
            # Errores de validación/serialización JSON
            logger.error(f"❌ Error de validación al guardar preferencias: {ve}")
            raise HTTPException(
                status_code=400,
                detail=f"Error de validación: {str(ve)}"
            )
        except Exception as e:
            logger.error(f"❌ Error inesperado al guardar preferencias: {e}")
            logger.exception(e)  # Log completo del stack trace
            raise HTTPException(
                status_code=500,
                detail=f"Error al guardar preferencias: {str(e)}"
            )
        finally:
            if conn:
                conn.close()
    
    @app.delete("/api/users/preferences/{table_id}",
                tags=["Preferencias de Usuario"])
    async def delete_table_preferences(
        table_id: str,
        request: Request,
        user: Dict = Depends(verify_jwt_token)
    ):
        """
        Elimina las preferencias de una tabla específica.
        
        **Parámetros:**
        - `table_id`: ID de la tabla (despachos, ordenes-compra, historial-ordenes, remisiones, productos-pedido)
        
        **Headers requeridos:**
        - `Authorization: Bearer {token}` - Token JWT válido
        
        **Respuesta exitosa (200):**
        ```json
        {
          "success": true,
          "message": "Preferencias eliminadas correctamente"
        }
        ```
        """
        validate_table_id(table_id)
        
        # Logging para diagnóstico
        logger.info(f"🔍 DELETE /api/users/preferences/{table_id}: Iniciado")
        logger.debug(f"   User object keys: {list(user.keys()) if user else 'None'}")
        
        # Usar función helper para obtener user_id con fallback a username
        try:
            user_id = get_user_id_or_username(user)
            logger.debug(f"   User ID obtenido: {user_id}")
        except HTTPException as e:
            logger.error(f"❌ Error al obtener user_id: {e.detail}")
            raise
        
        conn = None
        try:
            conn = get_db_connection()
            repository = UserPreferencesRepository(conn)
            deleted = repository.delete_table_preferences(user_id, table_id)
            
            if not deleted:
                raise HTTPException(
                    status_code=404,
                    detail=f"No se encontraron preferencias para la tabla {table_id}"
                )
            
            return {
                "success": True,
                "message": "Preferencias eliminadas correctamente"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error al eliminar preferencias: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al eliminar preferencias: {str(e)}"
            )
        finally:
            if conn:
                conn.close()

