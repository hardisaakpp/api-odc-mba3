"""
Endpoints para gestión de homologaciones SKU entre MBA3 y SAP.
"""

import logging
from typing import Dict, Optional
from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import JSONResponse

from database.services.homologacion_service import HomologacionService
from security.jwt_auth import verify_jwt_token
from models import (
    HomologacionesSkuListResponse,
    HomologacionSkuResponse,
    HomologacionSkuUpdateRequest,
    HomologacionSkuBulkUpdateRequest,
    HomologacionSkuBulkUpdateResponse,
    HomologacionSkuSincronizarResponse
)

logger = logging.getLogger(__name__)

# Exportar función principal para el linter
__all__ = ["register_homologaciones_sku_endpoints"]


def get_user_id_or_username(user: Dict) -> str:
    """
    Obtiene el ID del usuario, o usa username como fallback.
    
    Args:
        user: Diccionario con información del usuario del JWT
        
    Returns:
        ID del usuario o username como fallback (como string)
        
    Raises:
        HTTPException: Si no hay ni id ni username disponible
    """
    # Intentar obtener id directamente
    user_id = user.get('id')
    if user_id:
        return str(user_id)
    
    # Fallback a username si id no está disponible
    username = user.get('username')
    if username:
        logger.warning(f"⚠️ user.id no disponible, usando username como fallback: {username}")
        return str(username)
    
    # Buscar en raw_claims si está disponible
    raw_claims = user.get('raw_claims', {})
    if raw_claims:
        # Buscar en diferentes claims comunes
        possible_id_keys = ['sub', 'userId', 'user_id', 'id', 'nameidentifier']
        
        for key in possible_id_keys:
            value = raw_claims.get(key)
            if value:
                return str(value)
        
        # Buscar username en raw_claims
        possible_username_keys = ['name', 'username', 'user_name', 'preferred_username']
        
        for key in possible_username_keys:
            value = raw_claims.get(key)
            if value:
                logger.warning(f"⚠️ user_id no encontrado, usando username de raw_claims como fallback: {value}")
                return str(value)
    
    raise HTTPException(
        status_code=401,
        detail="No se pudo obtener el ID o username del usuario del token"
    )


def register_homologaciones_sku_endpoints(app: FastAPI):
    """
    Registra los endpoints de homologaciones SKU en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
    @app.get("/api/homologaciones-sku",
             tags=["Homologaciones SKU"])
    async def get_homologaciones_sku(
        request: Request,
        page: int = Query(1, ge=1, description="Número de página"),
        pageSize: int = Query(10, ge=1, le=100, description="Tamaño de página"),
        estado: Optional[str] = Query(None, description="Filtro por estado (PENDIENTE, HOMOLOGADO, ERROR)"),
        tiene_diferencias: Optional[bool] = Query(None, description="Filtro por diferencias MBA3 vs SAP"),
        tiene_datos_sap: Optional[bool] = Query(None, description="Filtro por presencia de datos SAP"),
        sku: Optional[str] = Query(None, description="Búsqueda por SKU (MBA3 o SAP)"),
        user: Dict = Depends(verify_jwt_token)
    ):
        """
        Obtiene lista de homologaciones SKU con filtros y paginación.
        
        **Headers requeridos:**
        - `Authorization: Bearer {token}` - Token JWT válido
        
        **Parámetros de query:**
        - `page` (int): Número de página (default: 1)
        - `pageSize` (int): Tamaño de página (default: 10, max: 100)
        - `estado` (string): Filtro por estado (PENDIENTE | HOMOLOGADO | ERROR)
        - `tiene_diferencias` (boolean): Filtro por diferencias
        - `tiene_datos_sap` (boolean): Filtro por datos SAP
        - `sku` (string): Búsqueda por SKU (busca en MBA3 y SAP)
        
        **Respuesta exitosa (200):**
        ```json
        {
          "status": "success",
          "data": [
            {
              "homologacion_id": "uuid-123",
              "sku_mba3": "SKU001",
              "nombre_producto_mba3": "Producto Ejemplo",
              "precio_unitario_mba3": 100.50,
              "cantidad_docena_mba3": 12,
              "total_linea_mba3": 1206.00,
              "sku_sap": "SKU001-SAP",
              "nombre_producto_sap": "Producto SAP",
              "precio_unitario_sap": 100.00,
              "cantidad_pack_sap": 10,
              "unidad_sap": "UN",
              "subtotal_sap": 1000.00,
              "estado": "PENDIENTE",
              "tiene_diferencias": true,
              "tiene_datos_sap": true
            }
          ],
          "metadata": {
            "count": 150,
            "total_pendientes": 50,
            "total_homologados": 80,
            "total_errores": 20,
            "filters": {}
          },
          "total": 150,
          "page": 1,
          "pageSize": 10,
          "totalPages": 15
        }
        ```
        """
        try:
            # Validar estado si se proporciona
            if estado and estado not in ['PENDIENTE', 'HOMOLOGADO', 'ERROR']:
                raise HTTPException(
                    status_code=400,
                    detail="Estado inválido. Debe ser PENDIENTE, HOMOLOGADO o ERROR"
                )
            
            service = HomologacionService()
            resultado = service.get_homologaciones_sku_paginadas(
                page=page,
                page_size=pageSize,
                estado=estado,
                tiene_diferencias=tiene_diferencias,
                tiene_datos_sap=tiene_datos_sap,
                sku=sku
            )
            
            if resultado.get('status') == 'error':
                raise HTTPException(
                    status_code=500,
                    detail=resultado.get('message', 'Error al obtener homologaciones')
                )
            
            return resultado
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener homologaciones SKU: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error al obtener homologaciones: {str(e)}"
            )
    
    @app.put("/api/homologaciones-sku/{homologacion_id}",
             tags=["Homologaciones SKU"])
    async def update_homologacion_sku(
        homologacion_id: str,
        request_body: HomologacionSkuUpdateRequest,
        request: Request,
        user: Dict = Depends(verify_jwt_token)
    ):
        """
        Actualiza una homologación SKU específica.
        
        **Parámetros:**
        - `homologacion_id`: UUID de la homologación a actualizar
        
        **Headers requeridos:**
        - `Authorization: Bearer {token}` - Token JWT válido
        - `Content-Type: application/json`
        
        **Body (todos los campos son opcionales):**
        ```json
        {
          "sku_sap": "SKU001-SAP",
          "nombre_producto_sap": "Producto SAP Actualizado",
          "precio_unitario_sap": 105.00,
          "cantidad_pack_sap": 12,
          "unidad_sap": "UN",
          "subtotal_sap": 1260.00,
          "estado": "HOMOLOGADO"
        }
        ```
        
        **Respuesta exitosa (200):**
        ```json
        {
          "status": "success",
          "data": {
            "homologacion_id": "uuid-123",
            // ... objeto completo actualizado
          },
          "message": "Homologación actualizada correctamente"
        }
        ```
        
        **Errores posibles:**
        - 400: Error de validación
        - 401: No autenticado
        - 404: Homologación no encontrada
        - 500: Error interno
        """
        try:
            # Obtener usuario que realiza la modificación
            try:
                modificado_por = get_user_id_or_username(user)
            except HTTPException:
                modificado_por = None  # Continuar sin usuario si falla
            
            # Convertir request a dict (excluyendo None)
            data = request_body.dict(exclude_none=True)
            
            service = HomologacionService()
            resultado = service.update_homologacion_sku(
                homologacion_id=homologacion_id,
                data=data,
                modificado_por=modificado_por
            )
            
            if resultado.get('status') == 'error':
                error_code = resultado.get('error_code')
                if error_code == 'NOT_FOUND':
                    raise HTTPException(status_code=404, detail=resultado.get('message'))
                elif error_code == 'VALIDATION_ERROR':
                    raise HTTPException(status_code=400, detail=resultado.get('message'))
                else:
                    raise HTTPException(status_code=500, detail=resultado.get('message'))
            
            return resultado
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al actualizar homologación {homologacion_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error al actualizar homologación: {str(e)}"
            )
    
    @app.post("/api/homologaciones-sku/bulk-update",
              tags=["Homologaciones SKU"])
    async def bulk_update_homologaciones(
        request_body: HomologacionSkuBulkUpdateRequest,
        request: Request,
        user: Dict = Depends(verify_jwt_token)
    ):
        """
        Actualiza múltiples homologaciones en lote.
        
        **Headers requeridos:**
        - `Authorization: Bearer {token}` - Token JWT válido
        - `Content-Type: application/json`
        
        **Body:**
        ```json
        {
          "updates": [
            {
              "homologacion_id": "uuid-123",
              "data": {
                "sku_sap": "SKU001-SAP",
                "precio_unitario_sap": 105.00,
                "estado": "HOMOLOGADO"
              }
            },
            {
              "homologacion_id": "uuid-456",
              "data": {
                "sku_sap": "SKU002-SAP",
                "estado": "HOMOLOGADO"
              }
            }
          ]
        }
        ```
        
        **Respuesta exitosa (200):**
        ```json
        {
          "status": "success",
          "data": {
            "actualizadas": 2,
            "errores": 0,
            "detalles": [
              {
                "homologacion_id": "uuid-123",
                "success": true
              },
              {
                "homologacion_id": "uuid-456",
                "success": true
              }
            ]
          }
        }
        ```
        """
        try:
            # Obtener usuario que realiza la modificación
            try:
                modificado_por = get_user_id_or_username(user)
            except HTTPException:
                modificado_por = None
            
            # Convertir updates a formato adecuado
            updates = []
            for item in request_body.updates:
                updates.append({
                    'homologacion_id': item.homologacion_id,
                    'data': item.data.dict(exclude_none=True)
                })
            
            service = HomologacionService()
            resultado = service.bulk_update_homologaciones(
                updates=updates,
                modificado_por=modificado_por
            )
            
            if resultado.get('status') == 'error':
                raise HTTPException(
                    status_code=500,
                    detail=resultado.get('message', 'Error al actualizar homologaciones')
                )
            
            return resultado
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al actualizar homologaciones en lote: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error al actualizar homologaciones en lote: {str(e)}"
            )
    
    @app.post("/api/homologaciones-sku/sincronizar",
              tags=["Homologaciones SKU"])
    async def sincronizar_homologaciones(
        request: Request,
        user: Dict = Depends(verify_jwt_token)
    ):
        """
        Sincroniza homologaciones desde los despachos.
        
        Este endpoint analiza todos los productos en `despacho_detalle`,
        compara con datos de SAP, y detecta diferencias para crear o
        actualizar registros de homologación.
        
        **Headers requeridos:**
        - `Authorization: Bearer {token}` - Token JWT válido
        
        **Body:** vacío (no se requiere)
        
        **Respuesta exitosa (200):**
        ```json
        {
          "status": "success",
          "data": {
            "homologaciones_encontradas": 25,
            "homologaciones_nuevas": 10,
            "homologaciones_actualizadas": 15,
            "mensaje": "Sincronización completada"
          }
        }
        ```
        
        **Proceso de sincronización:**
        1. Lee todos los productos de `despacho_detalle`
        2. Busca información SAP correspondiente en `producto_sap_cache`
        3. Detecta diferencias entre SKUs, precios, cantidades
        4. Crea nuevas homologaciones o actualiza existentes
        5. Calcula flags `tiene_diferencias` y `tiene_datos_sap`
        6. Asigna estado (PENDIENTE si hay diferencias, HOMOLOGADO si coincide)
        """
        try:
            service = HomologacionService()
            resultado = service.sincronizar_homologaciones()
            
            if resultado.get('status') == 'error':
                raise HTTPException(
                    status_code=500,
                    detail=resultado.get('message', 'Error al sincronizar homologaciones')
                )
            
            logger.info(f"✅ Sincronización completada: {resultado.get('data', {})}")
            return resultado
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al sincronizar homologaciones: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error al sincronizar homologaciones: {str(e)}"
            )




