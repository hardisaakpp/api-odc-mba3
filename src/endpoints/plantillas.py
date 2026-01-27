"""
Endpoints para gestión de plantillas Excel.
"""

import logging
import base64
import json
from typing import Dict, Optional
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query, Form
from fastapi.responses import JSONResponse

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.repositories.pedido_respuesta_repository import PedidoRespuestaRepository
from src.security.jwt_auth import verify_jwt_token, require_permission
from src.exceptions import BusinessException
from src.endpoints.pedidos.utils import validate_excel_file, get_user_id, MAX_FILE_SIZE

logger = logging.getLogger(__name__)

# Exportar función principal para el linter
__all__ = ["register_plantillas_endpoints"]


def register_plantillas_endpoints(app: FastAPI):
    """
    Registra los endpoints de plantillas Excel en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
    @app.post("/api/plantillas/upload", tags=["Plantillas"])
    async def upload_plantilla(
        file: UploadFile = File(..., description="Archivo Excel (.xlsx o .xls)"),
        validar: bool = Query(True, description="Validar datos antes de guardar"),
        bloquea_con_errores: bool = Query(True, description="Bloquear guardado si hay errores críticos"),
        exportar_log: bool = Query(False, description="Incluir log de validación en respuesta (base64)"),
        modo_tiendas: str = Query(
            "validar_estricto",
            description="Modo de validación de tiendas: 'validar_estricto' (recomendado) | 'crear_si_no_existe' (legacy) | 'sincronizar_maestro' (admin)",
            pattern="^(validar_estricto|crear_si_no_existe|sincronizar_maestro)$"
        ),
        confirmar_sincronizacion: bool = Query(
            False,
            description="REQUERIDO si modo_tiendas='sincronizar_maestro'. Confirma que deseas DESACTIVAR tiendas no presentes en Excel"
        ),
        correcciones_codigos: Optional[str] = Form(
            None, 
            description="JSON con mapa de correcciones de códigos: {\"codigo_original\": \"codigo_sap_corregido\"}"
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(
            'mba3-consultas.plantillas.upload',
            legacy_permission='mba3-consultas.proceso.execute'
        ))
    ):
        """
        Sube y valida una plantilla Excel para procesamiento.
        
        **Nuevo:** Incluye validación pre-negocio antes de guardar.
        
        Returns:
            JSON con resultado del procesamiento incluyendo validación
        """
        try:
            # Validación explícita para sincronizar
            if modo_tiendas == "sincronizar_maestro":
                if not confirmar_sincronizacion:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "confirmation_required",
                            "message": (
                                "El modo 'sincronizar_maestro' requiere confirmación explícita. "
                                "Esta operación va a DESACTIVAR tiendas no presentes en el Excel. "
                                "Envía el parámetro ?confirmar_sincronizacion=true si estás seguro."
                            ),
                            "modo_tiendas": "sincronizar_maestro",
                            "accion_recomendada": "Revisar Excel antes de confirmar"
                        }
                    )
                
                logger.warning(
                    f"OPERACION DESTRUCTIVA CONFIRMADA - "
                    f"Usuario {get_user_id(user)} activó modo SINCRONIZAR_MAESTRO con confirmación. "
                    f"Se va a actualizar el maestro de tiendas (puede desactivar existentes)."
                )
            
            # Validar archivo
            validate_excel_file(file)
            
            # Leer contenido del archivo
            content = await file.read()
            file_size = len(content)
            
            # Validar tamaño
            if file_size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"El archivo es demasiado grande. Tamaño máximo: {MAX_FILE_SIZE / (1024*1024):.1f} MB"
                )
            
            if file_size == 0:
                raise HTTPException(
                    status_code=400,
                    detail="El archivo está vacío"
                )
            
            # Obtener ID del usuario (normalizado)
            user_id = get_user_id(user)
            
            # Parsear correcciones de códigos si se proporcionan
            correcciones_dict: Optional[Dict[str, str]] = None
            if correcciones_codigos:
                try:
                    correcciones_dict = json.loads(correcciones_codigos)
                    if not isinstance(correcciones_dict, dict):
                        raise ValueError("correcciones_codigos debe ser un objeto JSON")
                    logger.info(f"Correcciones de códigos recibidas: {len(correcciones_dict)} código(s) a corregir")
                    for codigo_orig, codigo_corr in correcciones_dict.items():
                        logger.info(f"   • {codigo_orig} -> {codigo_corr}")
                except json.JSONDecodeError as e:
                    logger.warning(f"Error al parsear correcciones_codigos JSON: {e}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Formato JSON inválido en correcciones_codigos: {str(e)}"
                    )
            
            # Log informativo sobre el procesamiento
            logger.info(
                f"Iniciando procesamiento de plantilla '{file.filename}' "
                f"(tamaño: {file_size / 1024:.1f} KB). Esto puede tomar hasta 2 minutos."
            )
            
            # Procesar el archivo Excel con validación
            from src.database.services.pedido_service import PedidoService
            
            service = PedidoService()
            
            resultado = service.validar_y_procesar_archivo_excel(
                file_content=content,
                filename=file.filename or "sin_nombre.xlsx",
                usuario_id=user_id,
                validar_antes_de_guardar=validar,
                bloquea_con_errores=bloquea_con_errores,
                tiendas_permitidas=None,
                correcciones_codigos=correcciones_dict
            )
            
            # Construir mensaje de respuesta
            mensaje_respuesta = "Plantilla procesada y guardada exitosamente"
            if resultado["status"] == "validation_error":
                errores = resultado.get("errores", [])
                if errores:
                    mensaje_respuesta = errores[0]
                else:
                    mensaje_respuesta = "Plantilla validada pero tiene errores críticos"
            elif resultado["status"] == "error":
                mensaje_respuesta = resultado.get("message", "Error al procesar plantilla")
            
            # Construir respuesta
            response_data = {
                "status": resultado["status"],
                "message": mensaje_respuesta,
                "pedido_id": resultado.get("pedido_id"),
                "numero_pedido": resultado.get("numero_pedido"),
                "formato_detectado": resultado.get("formato_detectado"),
                "articulos_cargados": resultado.get("articulos_cargados", 0),
                "distribuciones_cargadas": resultado.get("distribuciones_cargadas", 0),
                "validation": resultado.get("validation"),
                "file_info": {
                    "filename": file.filename,
                    "size_mb": round(file_size / (1024 * 1024), 2)
                },
                "metadata": {
                    "uploaded_by": user_id,
                    "uploaded_at": datetime.now().isoformat()
                }
            }
            
            # Si se solicita, incluir log de validación en base64
            if exportar_log and resultado.get("validation"):
                from src.database.services.pedido_validation_exporter import PedidoValidationExporter
                
                excel_bytes = PedidoValidationExporter.export_to_excel_bytes(resultado["validation"])
                response_data["validation_log_excel_base64"] = base64.b64encode(excel_bytes).decode('utf-8')
                response_data["validation_log_filename"] = f"validation_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            # Si hay errores de validación, retornar 400 pero con detalles
            if resultado["status"] == "validation_error":
                return JSONResponse(
                    status_code=400,
                    content=response_data
                )
            
            # Si hay error general
            if resultado["status"] == "error":
                raise HTTPException(
                    status_code=400,
                    detail=f"Error al procesar plantilla: {resultado.get('errores', ['Error desconocido'])}"
                )
            
            # Enviar notificación por correo electrónico a El Rayo cuando se procesa exitosamente
            if resultado["status"] == "success":
                try:
                    from src.utils.email_notifier import send_plantilla_upload_notification
                    
                    email_enviado = send_plantilla_upload_notification(
                        pedido_id=resultado.get("pedido_id"),
                        numero_pedido=resultado.get("numero_pedido"),
                        filename=file.filename,
                        usuario_id=user_id,
                        articulos_cargados=resultado.get("articulos_cargados", 0),
                        distribuciones_cargadas=resultado.get("distribuciones_cargadas", 0),
                        formato_detectado=resultado.get("formato_detectado")
                    )
                    if email_enviado:
                        logger.info(f"📧 Email de notificación de plantilla enviado a El Rayo (Pedido: {resultado.get('numero_pedido', 'N/A')})")
                    else:
                        logger.warning(f"⚠️ No se pudo enviar email de notificación de plantilla (no crítico)")
                except Exception as e:
                    # NO fallar el proceso si el email falla
                    logger.warning(f"⚠️ Error al enviar email de notificación de plantilla (no crítico): {e}")
            
            return JSONResponse(status_code=200, content=response_data)
            
        except HTTPException:
            raise
        except BusinessException:
            raise
        except Exception as e:
            logger.error(f"Error al procesar plantilla: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al procesar la plantilla: {str(e)}"
            )
    
    @app.get("/api/plantillas/ultimo", tags=["Plantillas"])
    async def get_ultimo_pedido(
        incluir_respuesta: bool = Query(False, description="Incluir respuesta del proveedor si existe"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(
            'mba3-consultas.plantillas.view',
            legacy_permission='mba3-consultas.facturas.view'
        ))
    ):
        """
        Obtiene el último pedido cargado por el usuario autenticado.
        
        Returns:
            JSON con pedido completo o null si no hay pedidos
        """
        try:
            # Obtener ID del usuario (normalizado, mismo que al subir Excel)
            user_id = get_user_id(user)
            
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Obtener el último pedido DEL USUARIO
                ultimo_pedido = repo.get_ultimo_pedido(user_id)
                
                if not ultimo_pedido:
                    # Retornar 200 con null cuando no hay pedidos
                    return JSONResponse(status_code=200, content=None)
                
                # Obtener pedido completo
                pedido_completo = repo.get_pedido_completo(ultimo_pedido["pedido_id"])
                
                if not pedido_completo:
                    raise HTTPException(
                        status_code=500,
                        detail="Error al obtener detalles del último pedido"
                    )
                
                # Agregar respuesta si se solicita
                if incluir_respuesta:
                    respuesta_repo = PedidoRespuestaRepository(conn)
                    pedido_id = pedido_completo["cabecera"]["pedido_id"]
                    respuesta = respuesta_repo.obtener_respuesta_activa(pedido_id)
                    if respuesta:
                        pedido_completo["respuesta_proveedor"] = respuesta
                
                return JSONResponse(status_code=200, content=pedido_completo)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error al obtener último pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al obtener último pedido: {str(e)}"
            )
