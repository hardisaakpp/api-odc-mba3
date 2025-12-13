"""
Endpoints para gestión de preferencias de usuario.
"""

import logging
from typing import Dict
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse

from database.repositories.user_preferences_repository import UserPreferencesRepository
from database.connection import get_db_connection
from security.jwt_auth import verify_jwt_token
from models import (
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
VALID_TABLE_IDS = ["despachos", "ordenes-compra", "historial-ordenes"]

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


def register_user_preferences_endpoints(app: FastAPI):
    """
    Registra los endpoints de preferencias de usuario en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
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
        - `table_id`: ID de la tabla (despachos, ordenes-compra, historial-ordenes)
        
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
        
        user_id = user.get('id')
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="No se pudo obtener el ID del usuario del token"
            )
        
        conn = None
        try:
            conn = get_db_connection()
            repository = UserPreferencesRepository(conn)
            preferences = repository.get_table_preferences(user_id, table_id)
            
            if preferences:
                return PreferencesResponse(
                    preferences=TablePreferencesDto(**preferences)
                )
            else:
                return PreferencesResponse(preferences=None)
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error al obtener preferencias: {e}")
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
        - `table_id`: ID de la tabla (despachos, ordenes-compra, historial-ordenes)
        
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
        
        user_id = user.get('id')
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="No se pudo obtener el ID del usuario del token"
            )
        
        # Validar datos
        prefs = request_body.preferences
        if not prefs.visibleColumns or not prefs.columnOrder:
            raise HTTPException(
                status_code=400,
                detail="visibleColumns y columnOrder son requeridos"
            )
        
        conn = None
        try:
            conn = get_db_connection()
            repository = UserPreferencesRepository(conn)
            
            repository.save_table_preferences(
                user_id,
                table_id,
                prefs.dict(exclude_none=True)
            )
            
            return {
                "success": True,
                "message": "Preferencias guardadas correctamente"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error al guardar preferencias: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al guardar preferencias: {str(e)}"
            )
        finally:
            if conn:
                conn.close()
    
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
        user_id = user.get('id')
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="No se pudo obtener el ID del usuario del token"
            )
        
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
        - `table_id`: ID de la tabla (despachos, ordenes-compra, historial-ordenes)
        
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
        
        user_id = user.get('id')
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="No se pudo obtener el ID del usuario del token"
            )
        
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
        user_id = user.get('id')
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="No se pudo obtener el ID del usuario del token"
            )
        
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
        user_id = user.get('id')
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="No se pudo obtener el ID del usuario del token"
            )
        
        # Validar datos
        prefs = request_body.preferences
        if prefs.collapsed is None:
            raise HTTPException(
                status_code=400,
                detail="collapsed es requerido"
            )
        
        conn = None
        try:
            conn = get_db_connection()
            repository = UserPreferencesRepository(conn)
            
            repository.save_sidebar_preferences(
                user_id,
                prefs.dict(exclude_none=True)
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

