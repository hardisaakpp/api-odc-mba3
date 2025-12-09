"""
Endpoints para consultar información de despachos (solo lectura).
"""

import logging
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, Query, Depends
from fastapi.responses import JSONResponse

from utils import get_source_from_headers
from database.repositories.despacho_repository import DespachoRepository
from database.repositories.orden_compra_repository import OrdenCompraRepository
from database.connection import get_db_connection
from security.jwt_auth import verify_jwt_token, require_permission

logger = logging.getLogger(__name__)


def register_info_endpoints(app: FastAPI):
    """
    Registra los endpoints de información de despachos en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    @app.get("/despachos/count", tags=["Procesamiento"])
    async def get_despachos_count(
        request: Request,
        limit: Optional[int] = Query(None, description="Número máximo de registros a retornar (opcional)"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Endpoint para obtener el conteo y información detallada de despachos con sus órdenes de compra.
        
        **Responsabilidad:** Consultar estado (solo lectura)
        
        **Características:**
        - ✅ Cuenta despachos en despacho_cabecera que NO tienen OC asociada
        - ✅ Devuelve información detallada de todas las tablas relacionadas:
          - despacho_cabecera (información de cabecera del despacho)
          - despacho_detalle (líneas de detalle del despacho)
          - orden_compra_cabecera (información de cabecera de OC si existe)
          - orden_compra_detalle (líneas de detalle de OC si existe)
        - ✅ Útil para mostrar información completa en el frontend
        - ✅ Permisos: solo lectura (view), no requiere execute
        
        **Query Parameters:**
        - `limit` (int, opcional) - Número máximo de registros a retornar
        
        **Ejemplo de uso:**
        ```
        GET /despachos/count
        GET /despachos/count?limit=10
        ```
        
        **Respuesta:**
        ```json
        {
          "count": 5,
          "disponible": true,
          "despachos": [...]
        }
        ```
        
        **Nota:** Este endpoint solo consulta el estado, no ejecuta ningún proceso.
        Para procesar los despachos, usar el endpoint GET /procesar-oc.
        
        Returns:
            JSON con conteo, disponibilidad e información detallada de despachos y OCs
        """
        source = get_source_from_headers(request)
        
        try:
            conn = get_db_connection()
            despacho_repo = DespachoRepository(conn)
            oc_repo = OrdenCompraRepository(conn)
            
            # Contar despachos sin OC (misma lógica que usa /procesar-oc)
            count = despacho_repo.count_despachos_sin_oc()
            
            # Obtener información detallada de despachos con sus OCs
            despachos_info = despacho_repo.get_despachos_con_info_oc(limit=limit)
            
            # Agregar detalles de OC para cada despacho que tenga OC
            for despacho in despachos_info:
                if despacho.get("orden_compra_info") and despacho["orden_compra_info"].get("oc_id"):
                    oc_id = despacho["orden_compra_info"]["oc_id"]
                    try:
                        oc_detalles = oc_repo.get_detalles(oc_id)
                        despacho["orden_compra_info"]["oc_detalles"] = oc_detalles
                    except Exception as e:
                        logger.warning(f"⚠️ Error al obtener detalles de OC {oc_id}: {e}")
                        despacho["orden_compra_info"]["oc_detalles"] = []
            
            conn.close()
            
            disponible = count > 0
            
            logger.debug(f"📊 GET /despachos/count: {count} despachos disponibles, {len(despachos_info)} registros retornados")
            
            return JSONResponse(
                status_code=200,
                content={
                    "count": count,
                    "disponible": disponible,
                    "despachos": despachos_info
                },
                headers={
                    "X-Source": source,
                    "X-Endpoint": "DESPACHOS-COUNT",
                    "X-Count": str(count)
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Error al obtener información de despachos: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al obtener información de despachos: {str(e)}",
                    "count": 0,
                    "disponible": False,
                    "despachos": []
                }
            )
    
    @app.get("/despachos/{despacho_id}/detalles", tags=["Procesamiento"])
    async def get_despacho_detalles(
        request: Request,
        despacho_id: str,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Endpoint para obtener los detalles de un despacho específico.
        
        **Responsabilidad:** Consultar estado (solo lectura)
        
        **Características:**
        - ✅ Obtiene todos los detalles (líneas) de un despacho específico
        - ✅ Retorna información completa de cada línea de detalle
        - ✅ Permisos: solo lectura (view), no requiere execute
        
        **Path Parameters:**
        - `despacho_id` (string, requerido) - UUID del despacho
        
        **Ejemplo de uso:**
        ```
        GET /despachos/DD7D7A51-9E57-44D4-9A8F-4A05427A8325/detalles
        ```
        
        **Respuesta:**
        ```json
        {
          "status": "success",
          "despacho_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325",
          "detalles": [...],
          "count": 1
        }
        ```
        
        Returns:
            JSON con los detalles del despacho
        """
        source = get_source_from_headers(request)
        
        logger.info("=" * 70)
        logger.info(f"📋 GET /despachos/{despacho_id}/detalles: Consulta ejecutada a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info("=" * 70)
        
        try:
            conn = get_db_connection()
            despacho_repo = DespachoRepository(conn)
            
            # Obtener detalles del despacho
            detalles = despacho_repo.get_detalles(despacho_id)
            
            conn.close()
            
            logger.debug(f"📊 GET /despachos/{despacho_id}/detalles: {len(detalles)} detalles encontrados")
            
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "despacho_id": despacho_id,
                    "detalles": detalles,
                    "count": len(detalles)
                },
                headers={
                    "X-Source": source,
                    "X-Endpoint": "DESPACHO-DETALLES",
                    "X-Despacho-ID": despacho_id,
                    "X-Count": str(len(detalles))
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Error al obtener detalles del despacho {despacho_id}: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al obtener detalles del despacho: {str(e)}",
                    "despacho_id": despacho_id,
                    "detalles": [],
                    "count": 0
                }
            )

