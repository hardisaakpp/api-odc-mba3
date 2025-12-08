"""
Endpoints relacionados con consulta de facturas desde MBA3.
"""

import logging
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, Query, Depends
from fastapi.responses import JSONResponse

from services.mba3_service import MBA3Service
from utils import get_source_from_headers
from security.jwt_auth import verify_jwt_token, require_permission
from exceptions import MBA3ConnectionError, MBA3QueryError

logger = logging.getLogger(__name__)


def register_facturas_endpoints(app: FastAPI):
    """
    Registra los endpoints de facturas en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
    @app.get("/facturas", tags=["Consultas MBA3"])
    async def get_facturas(
        request: Request,
        anulada: Optional[bool] = Query(None, description="Filtrar por facturas anuladas (false = no anuladas, true = anuladas, null = todas)"),
        confirmado: Optional[bool] = Query(None, description="Filtrar por facturas confirmadas (true = confirmadas, false = no confirmadas, null = todas)"),
        remision_facturada: Optional[bool] = Query(None, description="Filtrar por remisión facturada (false = sin remisión, true = con remisión, null = todas)"),
        include_obj_datos: bool = Query(True, description="Incluir solo facturas con ObjDatosFactura no nulo"),
        save_to_db: bool = Query(True, description="Guardar resultados en SQL Server"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Endpoint FACTURAS: Obtiene facturas desde MBA3 con filtros configurables.
        
        ⭐ **Recomendado para Frontend**
        
        Este endpoint obtiene facturas desde MBA3 usando filtros configurables.
        La query está integrada en el backend, no requiere SQL del frontend.
        
        **Query Parameters:**
        - `anulada` (boolean, opcional) - Filtrar por facturas anuladas
        - `confirmado` (boolean, opcional) - Filtrar por facturas confirmadas
        - `remision_facturada` (boolean, opcional) - Filtrar por remisión facturada
        - `include_obj_datos` (boolean, default: true) - Incluir solo facturas con ObjDatosFactura
        - `save_to_db` (boolean, default: true) - Guardar en SQL Server
        
        **Ejemplo:**
        ```
        GET /facturas?anulada=false&confirmado=true&save_to_db=true
        ```
        
        **Respuesta:**
        ```json
        {
          "status": "success",
          "data": [...],
          "metadata": {
            "count": 10,
            "filters": {...},
            "save_status": {...}
          }
        }
        ```
        
        Returns:
            JSON con facturas y metadata
        """
        source = get_source_from_headers(request)
        
        logger.info("=" * 70)
        logger.info(f"📋 GET /facturas: Consulta ejecutada a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"Filtros: anulada={anulada}, confirmado={confirmado}, remision_facturada={remision_facturada}, include_obj_datos={include_obj_datos}, save_to_db={save_to_db}")
        logger.info("=" * 70)
        
        try:
            # Usar valores por defecto si no se proporcionan
            anulada_filter = anulada if anulada is not None else False
            confirmado_filter = confirmado if confirmado is not None else True
            remision_facturada_filter = remision_facturada if remision_facturada is not None else False
            
            # Obtener facturas usando el servicio
            result = MBA3Service.get_facturas(
                anulada=anulada_filter,
                confirmado=confirmado_filter,
                remision_facturada=remision_facturada_filter,
                include_obj_datos=include_obj_datos,
                save_to_db=save_to_db,
                upsert=True
            )
            
            # Preparar respuesta
            response_data = {
                "status": "success",
                "data": result.get("data", []),
                "metadata": {
                    "count": result.get("count", 0),
                    "filters": result.get("filters", {}),
                    "save_status": result.get("save_status")
                }
            }
            
            logger.info(f"✅ GET /facturas: {result.get('count', 0)} facturas encontradas")
            
            return JSONResponse(
                status_code=200,
                content=response_data,
                headers={
                    "X-Source": source,
                    "X-Endpoint": "FACTURAS",
                    "X-Count": str(result.get("count", 0))
                }
            )
            
        except MBA3ConnectionError as e:
            logger.error(f"❌ Error de conexión con MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "message": f"No se pudo conectar al servidor MBA3",
                    "detail": str(e),
                    "type": "connection_error",
                    "hint": "Verifica que el servidor MBA3 esté disponible y accesible. Revisa la configuración de MBA3_BASE_URL en tu archivo .env"
                }
            )
        except MBA3QueryError as e:
            logger.error(f"❌ Error al ejecutar consulta en MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al ejecutar consulta en MBA3",
                    "detail": str(e),
                    "type": "query_error"
                }
            )
        except Exception as e:
            logger.error(f"❌ Error al obtener facturas: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al obtener facturas: {str(e)}"
                }
            )

