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
            
            # Enviar notificación por correo electrónico a MABEL TRADING cuando El Rayo confirma el pedido
            if resultado.get("status") == "success" and resultado.get("confirmacion_registrada", False):
                try:
                    from src.utils.email_notifier_pedido import send_rayo_confirmacion_notification
                    from src.database.connection import get_db_connection_context
                    from src.database.repositories.pedido_repository import PedidoRepository
                    from src.database.repositories.pedido_confirmacion_rayo_repository import PedidoConfirmacionRayoRepository
                    
                    # Obtener número de pedido y detalles modificados
                    with get_db_connection_context() as conn:
                        repo_pedido = PedidoRepository(conn)
                        pedido_completo = repo_pedido.get_pedido_completo(pedido_id)
                        
                        if pedido_completo:
                            numero_pedido = pedido_completo["cabecera"].get("numero_pedido", "N/A")
                            
                            # Obtener cantidad de detalles modificados desde la confirmación más reciente
                            detalles_modificados = 0
                            try:
                                repo_confirmacion = PedidoConfirmacionRayoRepository(conn)
                                confirmaciones = repo_confirmacion.obtener_confirmaciones_por_pedido(
                                    pedido_id=pedido_id, limit=1
                                )
                                if confirmaciones:
                                    confirmacion_id = confirmaciones[0]["confirmacion_id"]
                                    confirmacion_completa = repo_confirmacion.obtener_confirmacion(confirmacion_id)
                                    if confirmacion_completa:
                                        detalles_modificados = confirmacion_completa.get("total_detalles_modificados", 0)
                            except Exception as e:
                                logger.warning(f"⚠️ No se pudo obtener detalles modificados de la confirmación: {e}")
                                # Usar un valor aproximado basado en las cantidades y precios guardados
                                detalles_modificados = resultado.get("cantidades_guardadas", 0) + resultado.get("precios_guardados", 0)
                            
                            email_enviado = send_rayo_confirmacion_notification(
                                pedido_id=pedido_id,
                                numero_pedido=numero_pedido,
                                usuario_rayo=usuario_id,
                                detalles_modificados=detalles_modificados
                            )
                            if email_enviado:
                                logger.info(f"📧 Email de confirmación de El Rayo enviado a MABEL TRADING (Pedido: {numero_pedido})")
                            else:
                                logger.warning(f"⚠️ No se pudo enviar email de confirmación de El Rayo (no crítico)")
                        else:
                            logger.warning(f"⚠️ No se pudo obtener información del pedido para enviar notificación (no crítico)")
                except Exception as e:
                    # NO fallar el proceso si el email falla
                    logger.warning(f"⚠️ Error al enviar email de confirmación de El Rayo (no crítico): {e}")
            
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
