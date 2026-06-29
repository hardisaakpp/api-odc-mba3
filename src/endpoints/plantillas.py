"""
Endpoints para gestión de plantillas Excel.

Incluye:
- Upload de plantillas Excel con almacenamiento en MinIO/S3
- Descarga del archivo Excel original
- Consulta del último pedido
"""

import logging
import base64
import json
import asyncio
from typing import Dict, Optional

from src.utils.timezone import ahora_naive
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query, Form, Path, Request
from fastapi.responses import JSONResponse, StreamingResponse
import io

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.repositories.pedido_respuesta_repository import PedidoRespuestaRepository
from src.database.repositories.common.serialization import make_json_serializable
from src.database.repositories.archivo_plantilla_repository import ArchivoPlantillaRepository
from src.database.pedido_estados import ESTADOS_PUEDE_DESCARTAR, ESTADOS_PUEDE_CONFIRMAR_REDISTRIBUCION
from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission
from src.exceptions import BusinessException
from src.endpoints.pedidos.utils import validate_excel_file, get_user_id, MAX_FILE_SIZE
from src.config import ENABLE_FILE_STORAGE
from src.database.services.proceso_estado_service import ProcesoEstadoService

logger = logging.getLogger(__name__)

# Exportar función principal para el linter
__all__ = ["register_plantillas_endpoints"]

# Timeout para comprobar si hay workers Celery disponibles (evitar colgar si Redis responde pero no hay worker)
CELERY_WORKER_PING_TIMEOUT = 2.5


def _celery_workers_available() -> bool:
    """
    Comprueba si hay al menos un worker Celery disponible.
    Si no hay workers o hay error/timeout, retorna False (priorizar flujo síncrono).
    """
    try:
        from src.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=CELERY_WORKER_PING_TIMEOUT)
        result = inspect.ping()
        available = bool(result and len(result) > 0)
        if not available:
            logger.debug("No hay workers Celery disponibles (ping sin respuesta)")
        return available
    except Exception as e:
        logger.debug("Comprobación de workers Celery fallida: %s", e)
        return False


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
        _: None = Depends(require_permission('mabel.view'))
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
            # Si se guardó el pedido (hay pedido_id), considerar éxito para mensaje y redirección
            tiene_pedido_guardado = bool(resultado.get("pedido_id"))
            mensaje_respuesta = "Plantilla procesada y guardada exitosamente"
            if resultado["status"] == "validation_error":
                if tiene_pedido_guardado:
                    mensaje_respuesta = "Plantilla procesada y guardada con advertencias. Revisa el detalle si lo deseas."
                else:
                    errores = resultado.get("errores", [])
                    mensaje_respuesta = errores[0] if errores else "Plantilla validada pero tiene errores críticos"
            elif resultado["status"] == "error":
                mensaje_respuesta = resultado.get("message", "Error al procesar plantilla")
            
            # Para que el frontend redirija a cargar-plantilla/{numero_pedido}, devolver status "success" cuando hubo persistencia
            status_respuesta = resultado["status"]
            if resultado["status"] == "validation_error" and tiene_pedido_guardado:
                status_respuesta = "success"
            
            # Construir respuesta
            response_data = {
                "status": status_respuesta,
                "message": mensaje_respuesta,
                "pedido_id": resultado.get("pedido_id"),
                "numero_pedido": resultado.get("numero_pedido"),
                "formato_detectado": resultado.get("formato_detectado"),
                "articulos_cargados": resultado.get("articulos_cargados", 0),
                "distribuciones_cargadas": resultado.get("distribuciones_cargadas", 0),
                "validation": resultado.get("validation"),
                "correcciones_aplicadas": resultado.get("correcciones_aplicadas", []),
                "file_info": {
                    "filename": file.filename,
                    "size_mb": round(file_size / (1024 * 1024), 2)
                },
                "metadata": {
                    "uploaded_by": user_id,
                    "uploaded_at": ahora_naive().isoformat()
                }
            }
            
            # Si se solicita, incluir log de validación en base64
            if exportar_log and resultado.get("validation"):
                from src.database.services.pedido_validation_exporter import PedidoValidationExporter
                
                excel_bytes = PedidoValidationExporter.export_to_excel_bytes(resultado["validation"])
                response_data["validation_log_excel_base64"] = base64.b64encode(excel_bytes).decode('utf-8')
                response_data["validation_log_filename"] = f"validation_log_{ahora_naive().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            # Si hay errores de validación y NO se guardó pedido, retornar 400 con detalles
            if resultado["status"] == "validation_error" and not tiene_pedido_guardado:
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
            
            # ================================================================
            # NUEVO: Guardar archivo original en storage (MinIO/S3)
            # ================================================================
            if ENABLE_FILE_STORAGE and resultado.get("pedido_id"):
                try:
                    from src.services.file_storage_service import get_file_storage, FileStorageError
                    
                    storage = get_file_storage()
                    
                    # Guardar archivo en MinIO/S3
                    storage_path = storage.guardar_archivo(
                        contenido=content,
                        pedido_id=resultado["pedido_id"],
                        nombre_original=file.filename or "sin_nombre.xlsx",
                        usuario_id=user_id
                    )
                    
                    # Registrar referencia en BD
                    with get_db_connection_context() as conn:
                        archivo_repo = ArchivoPlantillaRepository(conn)
                        archivo_repo.crear(
                            pedido_id=resultado["pedido_id"],
                            nombre_original=file.filename or "sin_nombre.xlsx",
                            storage_path=storage_path,
                            tamano_bytes=file_size,
                            subido_por=user_id
                        )
                    
                    response_data["archivo_original"] = {
                        "guardado": True,
                        "storage_path": storage_path,
                        "descarga_disponible": True
                    }
                    
                    logger.info(
                        f"✅ Archivo Excel original guardado en storage: {storage_path}"
                    )
                    
                except FileStorageError as e:
                    # El storage falló pero el pedido se procesó correctamente
                    # No bloqueamos la respuesta, solo advertimos
                    logger.warning(f"⚠️ No se pudo guardar archivo en storage: {e}")
                    response_data["archivo_original"] = {
                        "guardado": False,
                        "error": str(e),
                        "descarga_disponible": False
                    }
                except Exception as e:
                    logger.warning(f"⚠️ Error inesperado al guardar archivo: {e}")
                    response_data["archivo_original"] = {
                        "guardado": False,
                        "error": "Error interno al guardar archivo",
                        "descarga_disponible": False
                    }
            elif not ENABLE_FILE_STORAGE:
                response_data["archivo_original"] = {
                    "guardado": False,
                    "mensaje": "Almacenamiento de archivos deshabilitado (ENABLE_FILE_STORAGE=false)",
                    "descarga_disponible": False
                }
            
            # La carga Excel solo crea BORRADOR. El correo a EL RAYO se envía al hacer clic en "Enviar".
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

    # -------------------------------------------------------------------------
    # Upload asíncrono (Celery + storage temporal) - no bloquea la app
    # -------------------------------------------------------------------------
    @app.post("/api/plantillas/upload-async", tags=["Plantillas"])
    async def upload_plantilla_async(
        file: UploadFile = File(..., description="Archivo Excel (.xlsx o .xls)"),
        validar: bool = Query(True, description="Validar datos antes de guardar"),
        bloquea_con_errores: bool = Query(True, description="Bloquear guardado si hay errores críticos"),
        modo_tiendas: str = Query(
            "validar_estricto",
            description="Modo de validación de tiendas",
            pattern="^(validar_estricto|crear_si_no_existe|sincronizar_maestro)$"
        ),
        confirmar_sincronizacion: bool = Query(False, description="Requerido si modo_tiendas='sincronizar_maestro'"),
        force_sync: bool = Query(
            False,
            description="Si True, ejecuta en primer plano y devuelve 200 con el resultado (útil si el worker no está disponible)"
        ),
        correcciones_codigos: Optional[str] = Form(None, description="JSON con mapa de correcciones de códigos"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Sube una plantilla Excel para procesamiento en segundo plano (Celery).
        Responde de inmediato con process_id; el resultado se consulta con
        GET /api/plantillas/resultado/{process_id} o GET /api/plantillas/stream/{process_id}.

        Si Redis/Celery, el worker o el almacenamiento temporal no están disponibles,
        ejecuta el procesamiento en primer plano como fallback sync. Con force_sync=true
        se ejecuta siempre en primer plano (200 + resultado, misma forma que sync).
        """
        if modo_tiendas == "sincronizar_maestro" and not confirmar_sincronizacion:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "confirmation_required",
                    "message": "El modo 'sincronizar_maestro' requiere confirmar_sincronizacion=true."
                }
            )
        validate_excel_file(file)
        content = await file.read()
        file_size = len(content)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"El archivo es demasiado grande. Tamaño máximo: {MAX_FILE_SIZE / (1024*1024):.1f} MB"
            )
        if file_size == 0:
            raise HTTPException(status_code=400, detail="El archivo está vacío")
        user_id = get_user_id(user)
        correcciones_dict: Optional[Dict[str, str]] = None
        if correcciones_codigos:
            try:
                correcciones_dict = json.loads(correcciones_codigos)
                if not isinstance(correcciones_dict, dict):
                    raise ValueError("correcciones_codigos debe ser un objeto JSON")
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"Formato JSON inválido en correcciones_codigos: {str(e)}")

        run_async = not force_sync
        if run_async and not _celery_workers_available():
            logger.info(
                "No hay workers Celery disponibles. Procesando plantilla en primer plano (fallback sync)."
            )
            run_async = False

        if not ENABLE_FILE_STORAGE and run_async:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "storage_required",
                    "message": (
                        "La carga en segundo plano requiere ENABLE_FILE_STORAGE=true. "
                        "Activa el storage temporal o usa force_sync=true de forma explícita."
                    )
                }
            )

        if run_async:
            try:
                from src.services.file_storage_service import get_file_storage
                estado_service = ProcesoEstadoService()
                process_id = estado_service.crear_proceso_plantilla(user_id=user_id)
                storage = get_file_storage()
                storage_path = storage.guardar_archivo_temporal(
                    contenido=content,
                    process_id=process_id,
                    nombre_original=file.filename or "sin_nombre.xlsx"
                )
                from src.tasks.celery_plantilla_upload import procesar_plantilla_upload
                procesar_plantilla_upload.delay(
                    process_id=process_id,
                    user_id=user_id,
                    storage_path=storage_path,
                    filename=file.filename or "sin_nombre.xlsx",
                    validar=validar,
                    bloquea_con_errores=bloquea_con_errores,
                    modo_tiendas=modo_tiendas,
                    correcciones_codigos=correcciones_dict
                )
                logger.info(f"📤 Plantilla encolada: {process_id} (usuario: {user_id})")
                return JSONResponse(
                    status_code=202,
                    content={
                        "status": "accepted",
                        "process_id": process_id,
                        "message": "Plantilla en procesamiento. Consulta GET /api/plantillas/resultado/{process_id} o GET /api/plantillas/stream/{process_id}.",
                        "resultado_url": f"/api/plantillas/resultado/{process_id}",
                        "stream_url": f"/api/plantillas/stream/{process_id}"
                    }
                )
            except Exception as e:
                logger.warning(
                    "No se pudo iniciar procesamiento de plantilla en segundo plano (%s). "
                    "Procesando en primer plano (fallback sync).",
                    e,
                    exc_info=True,
                )
                run_async = False

        if not run_async:
            from src.database.services.pedido_service import PedidoService
            service = PedidoService()
            resultado = await asyncio.to_thread(
                service.validar_y_procesar_archivo_excel,
                file_content=content,
                filename=file.filename or "sin_nombre.xlsx",
                usuario_id=user_id,
                validar_antes_de_guardar=validar,
                bloquea_con_errores=bloquea_con_errores,
                tiendas_permitidas=None,
                modo_tiendas=modo_tiendas,
                correcciones_codigos=correcciones_dict
            )
            # Misma lógica que upload sync: si se guardó el pedido, éxito para mensaje y redirección
            tiene_pedido_guardado = bool(resultado.get("pedido_id"))
            mensaje_respuesta = "Plantilla procesada y guardada exitosamente"
            if resultado["status"] == "validation_error":
                if tiene_pedido_guardado:
                    mensaje_respuesta = "Plantilla procesada y guardada con advertencias. Revisa el detalle si lo deseas."
                else:
                    mensaje_respuesta = resultado.get("errores", ["Error de validación"])[0] if resultado.get("errores") else "Plantilla validada pero tiene errores críticos"
            elif resultado["status"] == "error":
                mensaje_respuesta = resultado.get("message", "Error al procesar plantilla")
            status_respuesta = resultado["status"]
            if resultado["status"] == "validation_error" and tiene_pedido_guardado:
                status_respuesta = "success"
            response_data = {
                "status": status_respuesta,
                "message": mensaje_respuesta,
                "pedido_id": resultado.get("pedido_id"),
                "numero_pedido": resultado.get("numero_pedido"),
                "formato_detectado": resultado.get("formato_detectado"),
                "articulos_cargados": resultado.get("articulos_cargados", 0),
                "distribuciones_cargadas": resultado.get("distribuciones_cargadas", 0),
                "validation": resultado.get("validation"),
                "correcciones_aplicadas": resultado.get("correcciones_aplicadas", []),
                "file_info": {
                    "filename": file.filename,
                    "size_mb": round(file_size / (1024 * 1024), 2)
                },
                "metadata": {
                    "uploaded_by": user_id,
                    "uploaded_at": ahora_naive().isoformat()
                },
                "fallback": "sync",
                "process_id": None,
                "async": False,
            }
            if resultado["status"] == "validation_error" and not tiene_pedido_guardado:
                return JSONResponse(status_code=400, content=response_data)
            if resultado["status"] == "error":
                raise HTTPException(
                    status_code=400,
                    detail=f"Error al procesar plantilla: {resultado.get('errores', ['Error desconocido'])}"
                )
            if ENABLE_FILE_STORAGE and resultado.get("pedido_id"):
                try:
                    from src.services.file_storage_service import get_file_storage
                    storage = get_file_storage()
                    storage_path = storage.guardar_archivo(
                        contenido=content,
                        pedido_id=resultado["pedido_id"],
                        nombre_original=file.filename or "sin_nombre.xlsx",
                        usuario_id=user_id
                    )
                    with get_db_connection_context() as conn:
                        archivo_repo = ArchivoPlantillaRepository(conn)
                        archivo_repo.crear(
                            pedido_id=resultado["pedido_id"],
                            nombre_original=file.filename or "sin_nombre.xlsx",
                            storage_path=storage_path,
                            tamano_bytes=file_size,
                            subido_por=user_id
                        )
                    response_data["archivo_original"] = {
                        "guardado": True,
                        "storage_path": storage_path,
                        "descarga_disponible": True
                    }
                except Exception as storage_err:
                    logger.warning("No se pudo guardar archivo en storage (fallback): %s", storage_err)
                    response_data["archivo_original"] = {
                        "guardado": False,
                        "error": str(storage_err),
                        "descarga_disponible": False
                    }
            else:
                response_data["archivo_original"] = {
                    "guardado": False,
                    "mensaje": "Almacenamiento deshabilitado o no aplicable" if not ENABLE_FILE_STORAGE else "No guardado",
                    "descarga_disponible": False
                }
            return JSONResponse(status_code=200, content=response_data)

    @app.get("/api/plantillas/resultado/{process_id}", tags=["Plantillas"])
    async def obtener_resultado_plantilla(
        process_id: str,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Obtiene el resultado del procesamiento async de una plantilla.
        Usar el process_id devuelto por POST /api/plantillas/upload-async.
        """
        if not process_id.startswith("plantilla-"):
            raise HTTPException(status_code=400, detail="process_id debe ser de tipo plantilla (plantilla-xxx)")
        estado_service = ProcesoEstadoService()
        estado = estado_service.obtener_estado(process_id)
        if not estado:
            raise HTTPException(status_code=404, detail="Proceso no encontrado")
        user_id = get_user_id(user)
        if estado.get("user_id") and estado["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="No tienes acceso a este proceso")
        if estado["status"] == "completed":
            resultado = estado.get("resultado") or {}
            if not isinstance(resultado, dict):
                resultado = {}
            resultado.setdefault("correcciones_aplicadas", [])
            correcciones = resultado.get("correcciones_aplicadas") or []
            if correcciones:
                logger.info(f"GET resultado {process_id}: enviando correcciones_aplicadas con {len(correcciones)} código(s) para resaltado")
            return resultado
        if estado["status"] == "error":
            content = {
                "status": "error",
                "message": estado.get("message", estado.get("error", "Error desconocido")),
                "error": estado.get("error")
            }
            # Incluir datos estructurados para UI de corrección de códigos SAP (validacion_sap, sugerencias)
            error_data = estado.get("error_data")
            if error_data:
                content["validacion"] = error_data.get("validacion")
                content["validacion_sap"] = error_data.get("validacion_sap")
                logger.debug(f"GET resultado {process_id}: enviando validacion_sap con detalle_validacion")
            else:
                logger.warning(f"GET resultado {process_id}: no hay error_data en estado (reiniciar Celery worker si se esperaban sugerencias SAP)")
            return JSONResponse(status_code=400, content=content)
        return {
            "status": estado["status"],
            "step": estado.get("step"),
            "progress": estado.get("progress", 0),
            "message": estado.get("message"),
            "process_id": process_id
        }

    @app.get("/api/plantillas/stream/{process_id}", tags=["Plantillas"])
    async def stream_progreso_plantilla(
        process_id: str,
        request: Request,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Stream SSE del progreso del procesamiento de plantilla.
        Mismo formato que cruce-productos/stream.
        """
        if not process_id.startswith("plantilla-"):
            raise HTTPException(status_code=400, detail="process_id debe ser de tipo plantilla (plantilla-xxx)")
        estado_service = ProcesoEstadoService()
        estado = estado_service.obtener_estado(process_id)
        if not estado:
            raise HTTPException(status_code=404, detail="Proceso no encontrado")
        user_id = get_user_id(user)
        if estado.get("user_id") and estado["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="No tienes acceso a este proceso")

        async def event_stream():
            ultimo_updated_at = None
            ultima_version = None
            while True:
                if await request.is_disconnected():
                    break
                estado_actual = estado_service.obtener_estado(process_id)
                if not estado_actual:
                    yield f"data: {json.dumps({'error': 'Proceso no encontrado'})}\n\n"
                    break
                updated_at = estado_actual.get("updated_at")
                version = estado_actual.get("version", 0)
                if updated_at != ultimo_updated_at or version != ultima_version:
                    payload = {
                        "process_id": estado_actual["process_id"],
                        "status": estado_actual["status"],
                        "step": estado_actual["step"],
                        "progress": estado_actual["progress"],
                        "message": estado_actual["message"],
                        "updated_at": updated_at,
                        "version": version
                    }
                    if "data" in estado_actual:
                        payload["data"] = estado_actual["data"]
                    if estado_actual["status"] == "completed":
                        res = estado_actual.get("resultado") or {}
                        if isinstance(res, dict):
                            res.setdefault("correcciones_aplicadas", [])
                        payload["resultado"] = res
                    if estado_actual["status"] == "error":
                        payload["error"] = estado_actual.get("error")
                    yield f"data: {json.dumps(payload)}\n\n"
                    ultimo_updated_at = updated_at
                    ultima_version = version
                if estado_actual["status"] in ("completed", "error"):
                    break
                await asyncio.sleep(1)
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
        )
    
    @app.get("/api/plantillas/ultimo", tags=["Plantillas"])
    async def get_ultimo_pedido(
        incluir_respuesta: bool = Query(False, description="Incluir respuesta del proveedor si existe"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
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

                # Para cargar-plantilla: habilitar Descartar solo en BORRADOR o NUEVO PEDIDO (normalizar estado_id por si viene string)
                _eid = pedido_completo.get("cabecera", {}).get("estado_id")
                try:
                    _eid = int(_eid) if _eid is not None else None
                except (TypeError, ValueError):
                    _eid = None
                pedido_completo["puede_descartar"] = _eid in ESTADOS_PUEDE_DESCARTAR
                pedido_completo["puede_confirmar_redistribucion"] = _eid in ESTADOS_PUEDE_CONFIRMAR_REDISTRIBUCION

                content = make_json_serializable(pedido_completo)
                return JSONResponse(status_code=200, content=content)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error al obtener último pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al obtener último pedido: {str(e)}"
            )
    
    # ========================================================================
    # NUEVO ENDPOINT: Listar pedidos para cargar-plantilla (incluye BORRADOR)
    # ========================================================================
    @app.get("/api/plantillas/pedidos", tags=["Plantillas"])
    async def listar_pedidos_plantillas(
        estado: Optional[str] = Query(None, description="Filtrar por estado del pedido"),
        numero_pedido: Optional[str] = Query(None, description="Buscar por número de pedido (parcial)"),
        limit: int = Query(10, ge=1, le=100, description="Límite de registros por página"),
        offset: int = Query(0, ge=0, description="Offset para paginación"),
        solo_pendientes_accion: Optional[str] = Query(
            None,
            description="Si 'true', solo pedidos que requieren acción del proveedor",
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Lista pedidos para la página cargar-plantilla.
        
        **IMPORTANTE:** Este endpoint INCLUYE pedidos en estado BORRADOR, 
        a diferencia de /api/pedidos que los excluye.
        
        **Uso:** Este endpoint está diseñado para el contenedor "Pedidos" de la página
        cargar-plantilla. Muestra todos los pedidos de todos los usuarios, incluyendo
        los que están en estado BORRADOR.
        
        **Query Parameters:**
        - `estado` (string, opcional) - Filtrar por estado (ej: "BORRADOR", "NUEVO_PEDIDO")
        - `numero_pedido` (string, opcional) - Búsqueda parcial por número de pedido
        - `limit` (int, default: 10) - Límite de registros por página
        - `offset` (int, default: 0) - Offset para paginación
        
        **Ejemplo:**
        ```
        GET /api/plantillas/pedidos?limit=10&offset=0
        GET /api/plantillas/pedidos?estado=BORRADOR&limit=10&offset=0
        GET /api/plantillas/pedidos?numero_pedido=P-12.08
        ```
        
        **Respuesta:**
        ```json
        {
            "status": "success",
            "data": [
                {
                    "pedido_id": "uuid",
                    "numero_pedido": "P-12.08 - 12 - 2025",
                    "fecha_pedido": "2025-01-21",
                    "estado": "BORRADOR",
                    "estado_id": 1,
                    "proveedor_nombre": "TEXTILES EL RAYO S.A.",
                    "creado_en": "2025-01-21T10:30:00"
                }
            ],
            "metadata": {
                "total": 5,
                "limit": 10,
                "offset": 0,
                "has_more": false
            }
        }
        ```
        
        Returns:
            JSON con lista de pedidos y metadata de paginación
        """
        try:
            user_id = get_user_id(user)
            filtrar_pendientes = (
                solo_pendientes_accion is not None
                and str(solo_pendientes_accion).lower() in ("true", "1")
            )
            
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Listar TODOS los pedidos INCLUYENDO BORRADOR (visibles para cualquier usuario con mabel.view)
                resultado = repo.get_pedidos_con_filtros(
                    estado=estado,
                    numero_pedido=numero_pedido.strip() if numero_pedido else None,
                    creado_por=None,  # Todos los pedidos, sin filtrar por usuario
                    limit=limit,
                    offset=offset,
                    excluir_borrador=False,  # INCLUIR BORRADOR para cargar-plantilla
                    solo_pendientes_accion=filtrar_pendientes,
                )
                
                logger.info(
                    f"📋 Listando pedidos para cargar-plantilla: "
                    f"usuario={user_id}, total={resultado['total']}, "
                    f"limit={limit}, offset={offset}"
                )
                
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "data": resultado["data"],
                        "metadata": {
                            "total": resultado["total"],
                            "limit": resultado["limit"],
                            "offset": resultado["offset"],
                            "has_more": resultado["has_more"]
                        }
                    }
                )
                
        except Exception as e:
            logger.error(f"❌ Error al listar pedidos para plantillas: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al listar pedidos: {str(e)}"
            )
    
    # ========================================================================
    # NUEVO ENDPOINT: Descargar archivo Excel original
    # ========================================================================
    async def _descargar_plantilla(
        *,
        user: Dict,
        pedido_id: Optional[str] = None,
        archivo_id: Optional[int] = None
    ):
        """
        Descarga el archivo Excel original que fue subido para un pedido.
        
        Este endpoint permite a usuarios autorizados descargar el archivo Excel
        tal como fue subido originalmente, sin modificaciones.
        
        **Requisitos:**
        - El archivo debe existir en el storage (MinIO/S3)
        - El usuario debe tener permiso 'mabel.view'
        - ENABLE_FILE_STORAGE debe estar habilitado
        
        **Returns:**
        - Archivo Excel (.xlsx) como descarga
        - 404 si el archivo no existe
        - 503 si el storage está deshabilitado
        """
        try:
            # Verificar que el storage esté habilitado
            if not ENABLE_FILE_STORAGE:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "storage_disabled",
                        "message": "El almacenamiento de archivos está deshabilitado. Contacta al administrador."
                    }
                )
            
            user_id = get_user_id(user)

            if not pedido_id and archivo_id is None:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "bad_request",
                        "message": "Debes enviar pedido_id o archivo_id para descargar."
                    }
                )

            # Buscar referencia del archivo en BD
            with get_db_connection_context() as conn:
                archivo_repo = ArchivoPlantillaRepository(conn)
                archivo_info = None
                if archivo_id is not None:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT
                            archivo_id,
                            pedido_id,
                            nombre_original,
                            storage_path,
                            content_type,
                            tamaño_bytes,
                            subido_por,
                            fecha_subida,
                            activo,
                            descargas,
                            ultima_descarga,
                            ultimo_descargador
                        FROM archivo_plantilla
                        WHERE archivo_id = ? AND activo = 1
                    """, (archivo_id,))
                    row = cursor.fetchone()
                    if row:
                        archivo_info = {
                            "archivo_id": row[0],
                            "pedido_id": row[1],
                            "nombre_original": row[2],
                            "storage_path": row[3],
                            "content_type": row[4],
                            "tamaño_bytes": row[5],
                            "subido_por": row[6],
                            "fecha_subida": row[7].isoformat() if row[7] else None,
                            "activo": row[8],
                            "descargas": row[9],
                            "ultima_descarga": row[10].isoformat() if row[10] else None,
                            "ultimo_descargador": row[11],
                        }
                else:
                    if pedido_id is None:
                        raise HTTPException(
                            status_code=400,
                            detail={
                                "error": "bad_request",
                                "message": "Debes enviar pedido_id o archivo_id para descargar."
                            }
                        )
                    archivo_info = archivo_repo.obtener_por_pedido_id(pedido_id)
                
                if not archivo_info:
                    identificador = f"archivo_id={archivo_id}" if archivo_id is not None else f"pedido_id={pedido_id}"
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "error": "not_found",
                            "message": f"No se encontró archivo original para {identificador}"
                        }
                    )
            
            # Descargar archivo del storage
            from src.services.file_storage_service import get_file_storage, FileStorageError
            
            try:
                storage = get_file_storage()
                contenido, metadata = storage.descargar_archivo(archivo_info["storage_path"])
            except FileStorageError as e:
                logger.error(f"Error al descargar archivo del storage: {e}")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "storage_error",
                        "message": f"Error al recuperar el archivo: {str(e)}"
                    }
                )
            
            # Registrar la descarga
            with get_db_connection_context() as conn:
                archivo_repo = ArchivoPlantillaRepository(conn)
                archivo_repo.registrar_descarga(
                    archivo_id=archivo_info["archivo_id"],
                    descargado_por=user_id
                )
            
            logger.info(
                f"✅ Archivo descargado: pedido_id={archivo_info['pedido_id']}, "
                f"archivo={archivo_info['nombre_original']}, usuario={user_id}"
            )
            
            # Preparar nombre de descarga
            nombre_descarga = archivo_info["nombre_original"]
            
            # Retornar archivo como stream
            return StreamingResponse(
                io.BytesIO(contenido),
                media_type=archivo_info.get("content_type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                headers={
                    "Content-Disposition": f'attachment; filename="{nombre_descarga}"',
                    "Content-Length": str(len(contenido)),
                    "X-Archivo-Id": str(archivo_info["archivo_id"]),
                    "X-Pedido-Id": str(archivo_info["pedido_id"]),
                    "X-Subido-Por": archivo_info["subido_por"],
                    "X-Fecha-Subida": archivo_info["fecha_subida"] or ""
                }
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error al descargar plantilla original: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al descargar el archivo: {str(e)}"
            )

    @app.get("/api/plantillas/{pedido_id}/descargar-original", tags=["Plantillas"])
    async def descargar_plantilla_original(
        pedido_id: str = Path(..., description="ID del pedido (GUID)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['mabel.view', 'odcsap.view']))
    ):
        return await _descargar_plantilla(
            user=user,
            pedido_id=pedido_id
        )

    @app.get("/api/plantillas/archivos/{archivo_id}/descargar-original", tags=["Plantillas"])
    async def descargar_plantilla_original_por_archivo(
        archivo_id: int = Path(..., description="ID del archivo original"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['mabel.view', 'odcsap.view']))
    ):
        return await _descargar_plantilla(
            user=user,
            archivo_id=archivo_id
        )
    
    # ========================================================================
    # NUEVO ENDPOINT: Verificar si existe archivo original
    # ========================================================================
    @app.get("/api/plantillas/{pedido_id}/info-archivo", tags=["Plantillas"])
    async def info_archivo_plantilla(
        pedido_id: str = Path(..., description="ID del pedido (GUID)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['mabel.view', 'odcsap.view']))
    ):
        """
        Obtiene información sobre el archivo Excel original de un pedido.
        
        Útil para verificar si existe el archivo antes de mostrar el botón
        de descarga en el frontend.
        
        **Returns:**
        - JSON con información del archivo o null si no existe
        """
        try:
            if not ENABLE_FILE_STORAGE:
                return JSONResponse(
                    status_code=200,
                    content={
                        "existe": False,
                        "storage_habilitado": False,
                        "mensaje": "Almacenamiento de archivos deshabilitado"
                    }
                )
            
            with get_db_connection_context() as conn:
                archivo_repo = ArchivoPlantillaRepository(conn)
                archivo_info = archivo_repo.obtener_por_pedido_id(pedido_id)
                
                if not archivo_info:
                    return JSONResponse(
                        status_code=200,
                        content={
                            "existe": False,
                            "storage_habilitado": True,
                            "mensaje": "No hay archivo original disponible para este pedido"
                        }
                    )
                
                return JSONResponse(
                    status_code=200,
                    content={
                        "existe": True,
                        "storage_habilitado": True,
                        "archivo": {
                            "archivo_id": archivo_info["archivo_id"],
                            "nombre_original": archivo_info["nombre_original"],
                            "tamaño_bytes": archivo_info["tamaño_bytes"],
                            "tamaño_mb": round(archivo_info["tamaño_bytes"] / (1024 * 1024), 2),
                            "subido_por": archivo_info["subido_por"],
                            "fecha_subida": archivo_info["fecha_subida"],
                            "descargas": archivo_info["descargas"],
                            "ultima_descarga": archivo_info["ultima_descarga"]
                        },
                        "url_descarga": f"/api/plantillas/{pedido_id}/descargar-original"
                    }
                )
                
        except Exception as e:
            logger.error(f"Error al obtener info de archivo: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno: {str(e)}"
            )
    
    # ========================================================================
    # NUEVO ENDPOINT: Buscar pedidos por número (para Filtros de búsqueda)
    # ========================================================================
    @app.get("/api/plantillas/buscar", tags=["Plantillas"])
    async def buscar_pedidos_por_numero(
        numero_pedido: Optional[str] = Query(None, description="Número de pedido a buscar (búsqueda parcial)"),
        limit: int = Query(20, ge=1, le=100, description="Límite de resultados"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Busca pedidos por número de pedido (búsqueda parcial).
        
        **Uso:** Este endpoint está diseñado para el input de búsqueda en la sección
        "Filtros de búsqueda" de la página cargar-plantilla. Permite buscar pedidos
        de forma independiente sin requerir otros filtros.
        
        **Comportamiento:**
        - Si `numero_pedido` está vacío o no se proporciona, devuelve los últimos pedidos.
        - Si `numero_pedido` tiene valor, busca pedidos cuyo número contenga el texto ingresado.
        - Incluye pedidos en estado BORRADOR (útil para cargar-plantilla).
        - Ordena por fecha de creación descendente.
        
        **Ejemplo de uso:**
        ```
        GET /api/plantillas/buscar?numero_pedido=P-12.08
        GET /api/plantillas/buscar?numero_pedido=12 - 2025
        GET /api/plantillas/buscar  (sin parámetro - devuelve últimos pedidos)
        ```
        
        **Respuesta:**
        ```json
        {
            "status": "success",
            "data": [
                {
                    "pedido_id": "uuid",
                    "numero_pedido": "P-12.08 - 12 - 2025",
                    "fecha_pedido": "2025-01-21",
                    "estado": "BORRADOR",
                    "estado_id": 1,
                    "proveedor_nombre": "...",
                    "creado_en": "2025-01-21T10:30:00"
                }
            ],
            "total": 5,
            "query": "P-12.08"
        }
        ```
        
        Returns:
            JSON con lista de pedidos que coinciden con la búsqueda
        """
        try:
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Buscar en TODOS los pedidos, incluyendo BORRADOR (visibles para cualquier usuario con mabel.view)
                resultado = repo.get_pedidos_con_filtros(
                    numero_pedido=numero_pedido.strip() if numero_pedido else None,
                    creado_por=None,  # Todos los pedidos, sin filtrar por usuario
                    limit=limit,
                    offset=0,
                    excluir_borrador=False,  # Incluir BORRADOR para cargar-plantilla
                )
                
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "data": resultado["data"],
                        "total": resultado["total"],
                        "query": numero_pedido.strip() if numero_pedido else None
                    }
                )
                
        except Exception as e:
            logger.error(f"❌ Error al buscar pedidos: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al buscar pedidos: {str(e)}"
            )
    
    # ========================================================================
    # NUEVO ENDPOINT: Listar archivos Excel originales del usuario
    # ========================================================================
    @app.get("/api/plantillas/archivos", tags=["Plantillas - Archivos Originales"])
    async def listar_archivos_originales(
        limit: int = Query(50, ge=1, le=200, description="Límite de registros"),
        solo_activos: bool = Query(True, description="Solo mostrar archivos activos"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['mabel.view', 'odcsap.view']))
    ):
        """
        Lista los archivos Excel originales subidos por el usuario.
        
        **Uso:** Este endpoint está diseñado para el botón "Listado Pedidos Originales"
        en la sección "Información ODC". Muestra todos los archivos Excel que el usuario
        ha subido y que están almacenados en MinIO/S3.
        
        **Funcionalidad:**
        - Lista archivos del usuario autenticado
        - Incluye información del pedido asociado (número de pedido)
        - Permite filtrar solo archivos activos o todos
        - Ordena por fecha de subida descendente (más recientes primero)
        
        **Query Parameters:**
        - `limit` (int, default: 50) - Cantidad máxima de archivos a retornar
        - `solo_activos` (bool, default: true) - Si es true, solo retorna archivos no eliminados
        
        **Ejemplo de uso:**
        ```
        GET /api/plantillas/archivos
        GET /api/plantillas/archivos?limit=100&solo_activos=false
        ```
        
        **Respuesta:**
        ```json
        {
            "status": "success",
            "data": [
                {
                    "archivo_id": 1,
                    "pedido_id": "uuid-del-pedido",
                    "numero_pedido": "P-12.08 - 12 - 2025",
                    "nombre_original": "plantilla_enero.xlsx",
                    "tamaño_bytes": 45678,
                    "tamaño_mb": 0.04,
                    "subido_por": "usuario@empresa.com",
                    "fecha_subida": "2025-01-21T10:30:00",
                    "activo": true,
                    "descargas": 3,
                    "ultima_descarga": "2025-01-22T15:00:00",
                    "url_descarga": "/api/plantillas/{pedido_id}/descargar-original"
                }
            ],
            "metadata": {
                "total": 15,
                "limit": 50,
                "storage_habilitado": true
            }
        }
        ```
        
        **Returns:**
        - JSON con lista de archivos y metadata
        - 503 si el storage está deshabilitado
        """
        try:
            # Verificar que el storage esté habilitado
            if not ENABLE_FILE_STORAGE:
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "warning",
                        "message": "El almacenamiento de archivos está deshabilitado",
                        "data": [],
                        "metadata": {
                            "total": 0,
                            "limit": limit,
                            "storage_habilitado": False
                        }
                    }
                )
            
            user_id = get_user_id(user)
            permissions = user.get('permissions', [])
            
            with get_db_connection_context() as conn:
                archivo_repo = ArchivoPlantillaRepository(conn)
                
                # odcsap.view ve TODOS los archivos (necesita ver los subidos por Mabel)
                # mabel.view ve solo sus propios archivos
                has_odcsap = any('odcsap.view' in str(p).lower() for p in permissions)
                roles = user.get('roles', [])
                is_admin = any('admin' in str(r).lower() for r in roles)
                
                if has_odcsap or is_admin:
                    archivos = archivo_repo.listar_todos(
                        limit=limit,
                        solo_activos=solo_activos
                    )
                else:
                    archivos = archivo_repo.listar_por_usuario(
                        usuario_id=user_id,
                        limit=limit,
                        solo_activos=solo_activos
                    )
                
                # Enriquecer datos para el frontend
                archivos_enriquecidos = []
                for archivo in archivos:
                    archivos_enriquecidos.append({
                        "archivo_id": archivo["archivo_id"],
                        "pedido_id": archivo["pedido_id"],
                        "numero_pedido": archivo.get("numero_pedido"),
                        "nombre_original": archivo["nombre_original"],
                        "tamaño_bytes": archivo["tamaño_bytes"],
                        "tamaño_mb": round(archivo["tamaño_bytes"] / (1024 * 1024), 2) if archivo["tamaño_bytes"] else 0,
                        "subido_por": archivo["subido_por"],
                        "fecha_subida": archivo["fecha_subida"],
                        "activo": archivo["activo"],
                        "descargas": archivo["descargas"],
                        "ultima_descarga": archivo["ultima_descarga"],
                        "url_descarga": f"/api/plantillas/archivos/{archivo['archivo_id']}/descargar-original"
                    })
                
                logger.info(
                    f"📋 Listando archivos originales: usuario={user_id}, "
                    f"total={len(archivos_enriquecidos)}, limit={limit}, solo_activos={solo_activos}"
                )
                
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "data": archivos_enriquecidos,
                        "metadata": {
                            "total": len(archivos_enriquecidos),
                            "limit": limit,
                            "storage_habilitado": True
                        }
                    }
                )
                
        except Exception as e:
            logger.error(f"❌ Error al listar archivos originales: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al listar archivos: {str(e)}"
            )
    
    # ========================================================================
    # NUEVO ENDPOINT: Eliminar archivo Excel original
    # ========================================================================
    @app.delete("/api/plantillas/archivos/{archivo_id}", tags=["Plantillas - Archivos Originales"])
    async def eliminar_archivo_original(
        archivo_id: int = Path(..., description="ID del archivo a eliminar"),
        eliminar_fisicamente: bool = Query(False, description="Si es true, elimina también del storage (MinIO)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['mabel.view', 'odcsap.view']))
    ):
        """
        Elimina un archivo Excel original.
        
        **Comportamiento por defecto (soft delete):**
        - Marca el archivo como inactivo en la base de datos (activo=0)
        - El archivo permanece en MinIO/S3 para auditoría
        - El archivo ya no aparecerá en el listado
        
        **Eliminación física (opcional):**
        - Si `eliminar_fisicamente=true`, también se elimina del storage MinIO/S3
        - Esta operación es irreversible
        - Usar con precaución
        
        **Validaciones:**
        - Solo el usuario que subió el archivo puede eliminarlo
        - El archivo debe existir y estar activo
        
        **Query Parameters:**
        - `eliminar_fisicamente` (bool, default: false) - Si es true, elimina también del storage
        
        **Ejemplo de uso:**
        ```
        DELETE /api/plantillas/archivos/123
        DELETE /api/plantillas/archivos/123?eliminar_fisicamente=true
        ```
        
        **Respuesta exitosa:**
        ```json
        {
            "status": "success",
            "message": "Archivo eliminado correctamente",
            "archivo_id": 123,
            "eliminacion_fisica": false
        }
        ```
        
        **Returns:**
        - JSON con confirmación de eliminación
        - 404 si el archivo no existe
        - 403 si el usuario no tiene permiso para eliminar el archivo
        """
        try:
            # Verificar que el storage esté habilitado
            if not ENABLE_FILE_STORAGE:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "storage_disabled",
                        "message": "El almacenamiento de archivos está deshabilitado"
                    }
                )
            
            user_id = get_user_id(user)
            
            with get_db_connection_context() as conn:
                archivo_repo = ArchivoPlantillaRepository(conn)
                
                # Buscar el archivo por ID
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT archivo_id, pedido_id, nombre_original, storage_path, 
                           subido_por, activo
                    FROM archivo_plantilla
                    WHERE archivo_id = ?
                """, (archivo_id,))
                row = cursor.fetchone()
                
                if not row:
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "error": "not_found",
                            "message": f"Archivo con ID {archivo_id} no encontrado"
                        }
                    )
                
                archivo_info = {
                    "archivo_id": row[0],
                    "pedido_id": row[1],
                    "nombre_original": row[2],
                    "storage_path": row[3],
                    "subido_por": row[4],
                    "activo": row[5]
                }
                
                # Verificar que el usuario sea el dueño del archivo
                if archivo_info["subido_por"] != user_id:
                    # Verificar si es admin (puede eliminar cualquier archivo)
                    user_roles = user.get("roles", [])
                    is_admin = any('admin' in str(r).lower() for r in user_roles)
                    
                    if not is_admin:
                        raise HTTPException(
                            status_code=403,
                            detail={
                                "error": "forbidden",
                                "message": "No tienes permiso para eliminar este archivo. Solo el usuario que lo subió puede eliminarlo."
                            }
                        )
                
                # Verificar que el archivo esté activo
                if not archivo_info["activo"]:
                    return JSONResponse(
                        status_code=200,
                        content={
                            "status": "warning",
                            "message": "El archivo ya estaba eliminado",
                            "archivo_id": archivo_id
                        }
                    )
                
                # Soft delete en BD
                archivo_repo.eliminar(archivo_id)
                
                # Si se solicita eliminación física, eliminar del storage
                eliminacion_storage = False
                if eliminar_fisicamente and archivo_info["storage_path"]:
                    try:
                        from src.services.file_storage_service import get_file_storage, FileStorageError
                        
                        storage = get_file_storage()
                        storage.eliminar_archivo(archivo_info["storage_path"])
                        eliminacion_storage = True
                        
                        logger.info(
                            f"🗑️ Archivo eliminado físicamente del storage: {archivo_info['storage_path']}"
                        )
                    except FileStorageError as e:
                        logger.warning(f"⚠️ No se pudo eliminar del storage: {e}")
                        # No fallar si el storage ya no tiene el archivo
                
                logger.info(
                    f"🗑️ Archivo eliminado: archivo_id={archivo_id}, "
                    f"nombre={archivo_info['nombre_original']}, usuario={user_id}, "
                    f"eliminacion_fisica={eliminar_fisicamente}"
                )
                
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "message": "Archivo eliminado correctamente",
                        "archivo_id": archivo_id,
                        "nombre_archivo": archivo_info["nombre_original"],
                        "eliminacion_fisica": eliminacion_storage
                    }
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al eliminar archivo: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al eliminar archivo: {str(e)}"
            )
    
    # ========================================================================
    # NUEVO ENDPOINT: Health check del storage
    # ========================================================================
    @app.get("/api/plantillas/storage/health", tags=["Plantillas"])
    async def storage_health_check(
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Verifica el estado del servicio de almacenamiento de archivos.
        
        **Returns:**
        - JSON con estado del storage (healthy/unhealthy/disabled)
        """
        try:
            if not ENABLE_FILE_STORAGE:
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "disabled",
                        "message": "Almacenamiento de archivos deshabilitado (ENABLE_FILE_STORAGE=false)"
                    }
                )
            
            from src.services.file_storage_service import get_file_storage
            
            storage = get_file_storage()
            health = storage.health_check()
            
            return JSONResponse(status_code=200, content=health)
            
        except Exception as e:
            logger.error(f"Error en health check de storage: {e}")
            return JSONResponse(
                status_code=200,
                content={
                    "status": "error",
                    "message": str(e)
                }
            )
