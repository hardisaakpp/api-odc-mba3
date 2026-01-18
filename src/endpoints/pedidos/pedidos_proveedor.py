"""
Endpoints de gestión de respuestas de proveedores.
"""

import logging
from typing import Dict
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Path, Body, status
from fastapi.responses import JSONResponse

from src.security.jwt_auth import verify_jwt_token, require_permission
from src.models import (
    FormularioProveedorResponse,
    RespuestaProveedorRequest,
    RespuestaProveedorResponse
)
from .utils import validate_excel_file, get_user_id, MAX_FILE_SIZE

logger = logging.getLogger(__name__)


def register_proveedor_endpoints(app: FastAPI):
    """Registra los endpoints de gestión de proveedores."""
    
    @app.post("/api/pedidos/{pedido_id}/cargar-respuesta-proveedor", tags=["Pedidos - Proveedor"])
    async def cargar_respuesta_proveedor(
        pedido_id: str = Path(..., description="UUID del pedido"),
        file: UploadFile = File(..., description="Archivo Excel con respuesta del proveedor"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """Carga la respuesta del proveedor desde un archivo Excel."""
        try:
            validate_excel_file(file)
            
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"El archivo excede el tamaño máximo permitido de {MAX_FILE_SIZE / 1024 / 1024} MB"
                )
            
            from src.database.services.pedido_proveedor_service import PedidoProveedorService
            
            service = PedidoProveedorService()
            usuario_id = get_user_id(user)
            
            resultado = service.importar_respuesta_proveedor(
                pedido_id=pedido_id,
                file_content=content,
                filename=file.filename or "respuesta.xlsx",
                usuario_id=usuario_id
            )
            
            status_code = 200
            if resultado["status"] == "validation_error":
                status_code = 400
            
            return JSONResponse(status_code=status_code, content=resultado)
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al cargar respuesta del proveedor: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al procesar respuesta: {str(e)}"
            )
    
    @app.get("/api/pedidos/{pedido_id}/formulario-proveedor", 
             response_model=FormularioProveedorResponse,
             tags=["Pedidos - Proveedor"])
    async def obtener_formulario_proveedor(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """Obtiene los datos del pedido formateados para el formulario web del proveedor."""
        try:
            from src.database.services.pedido_proveedor_web_service import PedidoProveedorWebService
            
            service = PedidoProveedorWebService()
            formulario = service.obtener_formulario_proveedor(pedido_id)
            
            return JSONResponse(status_code=200, content=formulario)
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"❌ Error al obtener formulario proveedor: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al obtener formulario: {str(e)}"
            )
    
    @app.post("/api/pedidos/{pedido_id}/enviar-respuesta-proveedor",
              response_model=RespuestaProveedorResponse,
              tags=["Pedidos - Proveedor"])
    async def enviar_respuesta_proveedor(
        pedido_id: str = Path(..., description="UUID del pedido"),
        respuesta: RespuestaProveedorRequest = Body(...),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """Recibe la respuesta del proveedor desde el formulario web."""
        try:
            from src.database.services.pedido_proveedor_web_service import PedidoProveedorWebService
            
            service = PedidoProveedorWebService()
            usuario_id = get_user_id(user)
            
            # Convertir productos a formato dict
            productos_dict = [producto.model_dump() for producto in respuesta.productos]
            
            resultado = service.procesar_respuesta_proveedor_web(
                pedido_id=pedido_id,
                productos=productos_dict,
                observaciones_generales=respuesta.observaciones_generales,
                estado=respuesta.estado,
                usuario_id=usuario_id
            )
            
            status_code = 200
            if resultado["status"] == "validation_error":
                status_code = 400
            
            return JSONResponse(status_code=status_code, content=resultado)
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"❌ Error al enviar respuesta del proveedor: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al procesar respuesta: {str(e)}"
            )
    
    @app.post("/api/pedidos/{pedido_id}/crear-respuesta-desde-pedido",
              response_model=RespuestaProveedorResponse,
              tags=["Pedidos - Proveedor"])
    async def crear_respuesta_desde_pedido(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """Guarda los cambios realizados por EL RAYO y crea la respuesta del proveedor."""
        try:
            from src.database.services.pedido_proveedor_web_service import PedidoProveedorWebService
            
            usuario_id = get_user_id(user)
            observaciones_generales = None
            
            logger.info(f"Guardando cambios y creando respuesta para pedido {pedido_id} (usuario: {usuario_id})")
            
            web_service = PedidoProveedorWebService()
            resultado = web_service.crear_respuesta_desde_pedido(
                pedido_id=pedido_id,
                usuario_id=usuario_id,
                observaciones_generales=observaciones_generales
            )
            
            logger.info(f"✅ Cambios guardados y respuesta creada para pedido {pedido_id}. Estado: RESPUESTA_PROVEEDOR_CARGADA")
            
            return JSONResponse(status_code=200, content=resultado)
            
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"❌ Error de validación al guardar cambios: {e}")
            raise HTTPException(status_code=400, detail=error_msg)
        except Exception as e:
            logger.error(f"❌ Error al guardar cambios del pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al guardar cambios del pedido: {str(e)}"
            )
