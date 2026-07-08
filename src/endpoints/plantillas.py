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

_PERM_MABEL = 'mabel.view'
_PERM_ODCSAP = 'odcsap.view'
_DEFAULT_FILENAME = "sin_nombre.xlsx"
_KEY_TAMANO_BYTES = "tamaño_bytes"


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


def _check_sincronizar_maestro(modo_tiendas: str, confirmar_sincronizacion: bool, user: Dict) -> None:
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

def _check_sincronizar_maestro_async(modo_tiendas: str, confirmar_sincronizacion: bool) -> None:
    if modo_tiendas == "sincronizar_maestro" and not confirmar_sincronizacion:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "confirmation_required",
                "message": "El modo 'sincronizar_maestro' requiere confirmar_sincronizacion=true."
            }
        )

def _check_file_size(file_size: int) -> None:
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

def _parse_correcciones_codigos(correcciones_codigos: Optional[str]) -> Optional[Dict[str, str]]:
    if not correcciones_codigos:
        return None
    try:
        correcciones_dict = json.loads(correcciones_codigos)
        if not isinstance(correcciones_dict, dict):
            raise ValueError("correcciones_codigos debe ser un objeto JSON")
        logger.info(f"Correcciones de códigos recibidas: {len(correcciones_dict)} código(s) a corregir")
        for codigo_orig, codigo_corr in correcciones_dict.items():
            logger.info(f"   • {codigo_orig} -> {codigo_corr}")
        return correcciones_dict
    except ValueError as e:  # json.JSONDecodeError ya es subclase de ValueError
        logger.warning(f"Error al parsear correcciones_codigos JSON: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Formato JSON inválido en correcciones_codigos: {str(e)}"
        )

def _intentar_guardar_original(content: bytes, filename: str, pedido_id: str, file_size: int,
                                user_id: str, log_warning: bool) -> dict:
    """Intenta guardar el archivo original en storage y su registro en BD. Retorna el dict archivo_original."""
    try:
        from src.services.file_storage_service import get_file_storage, FileStorageError
        storage = get_file_storage()
        storage_path = storage.guardar_archivo(
            contenido=content,
            pedido_id=pedido_id,
            nombre_original=filename,
            usuario_id=user_id
        )
        with get_db_connection_context() as conn:
            archivo_repo = ArchivoPlantillaRepository(conn)
            archivo_repo.crear(
                pedido_id=pedido_id,
                nombre_original=filename,
                storage_path=storage_path,
                tamano_bytes=file_size,
                subido_por=user_id
            )
        if log_warning:
            logger.info(f"✅ Archivo Excel original guardado en storage: {storage_path}")
        return {
            "guardado": True,
            "storage_path": storage_path,
            "descarga_disponible": True
        }
    except Exception as e:
        if log_warning:
            logger.warning(f"⚠️ No se pudo guardar archivo en storage: {e}")
        else:
            logger.warning("No se pudo guardar archivo en storage (fallback): %s", e)
        return {
            "guardado": False,
            "error": str(e) if "FileStorageError" in str(type(e)) else "Error interno al guardar archivo",
            "descarga_disponible": False
        }


def _save_original_file(content: bytes, filename: str, pedido_id: Optional[str], file_size: int, user_id: str, response_data: dict, log_warning: bool = True) -> None:
    if ENABLE_FILE_STORAGE and pedido_id:
        response_data["archivo_original"] = _intentar_guardar_original(
            content, filename, pedido_id, file_size, user_id, log_warning
        )
    else:
        response_data["archivo_original"] = {
            "guardado": False,
            "mensaje": "Almacenamiento deshabilitado o no aplicable" if not ENABLE_FILE_STORAGE else "No guardado",
            "descarga_disponible": False
        }

def _build_response_message(resultado: dict, tiene_pedido_guardado: bool) -> str:
    mensaje_respuesta = "Plantilla procesada y guardada exitosamente"
    if resultado["status"] == "validation_error":
        if tiene_pedido_guardado:
            mensaje_respuesta = "Plantilla procesada y guardada con advertencias. Revisa el detalle si lo deseas."
        else:
            errores = resultado.get("errores", [])
            mensaje_respuesta = errores[0] if errores else "Plantilla validada pero tiene errores críticos"
    elif resultado["status"] == "error":
        mensaje_respuesta = resultado.get("message", "Error al procesar plantilla")
    return mensaje_respuesta

def _enqueue_async_task(
    content: bytes, filename: str, user_id: str, validar: bool, 
    bloquea_con_errores: bool, modo_tiendas: str, correcciones_dict: Optional[Dict[str, str]]
) -> JSONResponse:
    from src.services.file_storage_service import get_file_storage
    estado_service = ProcesoEstadoService()
    process_id = estado_service.crear_proceso_plantilla(user_id=user_id)
    storage = get_file_storage()
    storage_path = storage.guardar_archivo_temporal(
        contenido=content,
        process_id=process_id,
        nombre_original=filename
    )
    from src.tasks.celery_plantilla_upload import procesar_plantilla_upload
    procesar_plantilla_upload.delay(
        process_id=process_id,
        user_id=user_id,
        storage_path=storage_path,
        filename=filename,
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

def _generate_stream_payload(estado_actual: dict) -> dict:
    payload = {
        "process_id": estado_actual["process_id"],
        "status": estado_actual["status"],
        "step": estado_actual["step"],
        "progress": estado_actual["progress"],
        "message": estado_actual["message"],
        "updated_at": estado_actual.get("updated_at"),
        "version": estado_actual.get("version", 0)
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
    return payload

def _get_archivo_info_by_id(conn, archivo_id: int) -> Optional[dict]:
    cursor = conn.cursor()
    cursor.execute('''
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
    ''', (archivo_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "archivo_id": row[0],
        "pedido_id": row[1],
        "nombre_original": row[2],
        "storage_path": row[3],
        "content_type": row[4],
        _KEY_TAMANO_BYTES: row[5],
        "subido_por": row[6],
        "fecha_subida": row[7].isoformat() if row[7] else None,
        "activo": row[8],
        "descargas": row[9],
        "ultima_descarga": row[10].isoformat() if row[10] else None,
        "ultimo_descargador": row[11],
    }

def _get_archivo_info(pedido_id: Optional[str], archivo_id: Optional[int]) -> dict:
    if not pedido_id and archivo_id is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": "Debes enviar pedido_id o archivo_id para descargar."}
        )
    with get_db_connection_context() as conn:
        archivo_repo = ArchivoPlantillaRepository(conn)
        archivo_info = None
        if archivo_id is not None:
            archivo_info = _get_archivo_info_by_id(conn, archivo_id)
        else:
            if pedido_id is None:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "bad_request", "message": "Debes enviar pedido_id o archivo_id para descargar."}
                )
            archivo_info = archivo_repo.obtener_por_pedido_id(pedido_id)

        if not archivo_info:
            identificador = f"archivo_id={archivo_id}" if archivo_id is not None else f"pedido_id={pedido_id}"
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"No se encontró archivo original para {identificador}"}
            )
        return archivo_info


async def _upload_plantilla_handler(
    file: UploadFile,
    validar: bool,
    bloquea_con_errores: bool,
    exportar_log: bool,
    modo_tiendas: str,
    confirmar_sincronizacion: bool,
    correcciones_codigos: Optional[str],
    user: Dict,
) -> JSONResponse:
    try:
        _check_sincronizar_maestro(modo_tiendas, confirmar_sincronizacion, user)
        validate_excel_file(file)

        content = await file.read()
        file_size = len(content)
        _check_file_size(file_size)

        user_id = get_user_id(user)
        correcciones_dict = _parse_correcciones_codigos(correcciones_codigos)

        logger.info(
            f"Iniciando procesamiento de plantilla '{file.filename}' "
            f"(tamaño: {file_size / 1024:.1f} KB). Esto puede tomar hasta 2 minutos."
        )

        from src.database.services.pedido_service import PedidoService
        service = PedidoService()

        filename_to_use = file.filename or _DEFAULT_FILENAME
        resultado = service.validar_y_procesar_archivo_excel(
            file_content=content,
            filename=filename_to_use,
            usuario_id=user_id,
            validar_antes_de_guardar=validar,
            bloquea_con_errores=bloquea_con_errores,
            tiendas_permitidas=None,
            correcciones_codigos=correcciones_dict
        )

        tiene_pedido_guardado = bool(resultado.get("pedido_id"))
        mensaje_respuesta = _build_response_message(resultado, tiene_pedido_guardado)
        
        status_respuesta = "success" if resultado["status"] == "validation_error" and tiene_pedido_guardado else resultado["status"]

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

        if exportar_log and resultado.get("validation"):
            from src.database.services.pedido_validation_exporter import PedidoValidationExporter
            excel_bytes = PedidoValidationExporter.export_to_excel_bytes(resultado["validation"])
            response_data["validation_log_excel_base64"] = base64.b64encode(excel_bytes).decode('utf-8')
            response_data["validation_log_filename"] = f"validation_log_{ahora_naive().strftime('%Y%m%d_%H%M%S')}.xlsx"

        if resultado["status"] == "validation_error" and not tiene_pedido_guardado:
            return JSONResponse(status_code=400, content=response_data)

        if resultado["status"] == "error":
            raise HTTPException(
                status_code=400,
                detail=f"Error al procesar plantilla: {resultado.get('errores', ['Error desconocido'])}"
            )

        _save_original_file(content, filename_to_use, resultado.get("pedido_id"), file_size, user_id, response_data, log_warning=True)

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


async def _procesar_plantilla_sync_fallback(
    content: bytes, filename_to_use: str, filename_original: Optional[str], user_id: str,
    validar: bool, bloquea_con_errores: bool, correcciones_dict: Optional[Dict[str, str]], file_size: int,
) -> JSONResponse:
    """Procesa la plantilla en primer plano (fallback cuando no hay Celery/storage o force_sync=True)."""
    from src.database.services.pedido_service import PedidoService
    service = PedidoService()
    resultado = await asyncio.to_thread(
        service.validar_y_procesar_archivo_excel,
        file_content=content,
        filename=filename_to_use,
        usuario_id=user_id,
        validar_antes_de_guardar=validar,
        bloquea_con_errores=bloquea_con_errores,
        tiendas_permitidas=None,
        correcciones_codigos=correcciones_dict
    )
    tiene_pedido_guardado = bool(resultado.get("pedido_id"))
    mensaje_respuesta = _build_response_message(resultado, tiene_pedido_guardado)
    status_respuesta = "success" if resultado["status"] == "validation_error" and tiene_pedido_guardado else resultado["status"]

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
            "filename": filename_original,
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

    _save_original_file(content, filename_to_use, resultado.get("pedido_id"), file_size, user_id, response_data, log_warning=False)
    return JSONResponse(status_code=200, content=response_data)


async def _upload_plantilla_async_handler(
    file: UploadFile,
    validar: bool,
    bloquea_con_errores: bool,
    modo_tiendas: str,
    confirmar_sincronizacion: bool,
    force_sync: bool,
    correcciones_codigos: Optional[str],
    user: Dict,
) -> JSONResponse:
    _check_sincronizar_maestro_async(modo_tiendas, confirmar_sincronizacion)
    validate_excel_file(file)
    content = await file.read()
    file_size = len(content)
    _check_file_size(file_size)
    user_id = get_user_id(user)
    correcciones_dict = _parse_correcciones_codigos(correcciones_codigos)

    run_async = not force_sync
    if run_async and not _celery_workers_available():
        logger.info("No hay workers Celery disponibles. Procesando plantilla en primer plano (fallback sync).")
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

    filename_to_use = file.filename or _DEFAULT_FILENAME

    if run_async:
        try:
            return _enqueue_async_task(
                content=content, filename=filename_to_use, user_id=user_id,
                validar=validar, bloquea_con_errores=bloquea_con_errores,
                modo_tiendas=modo_tiendas, correcciones_dict=correcciones_dict
            )
        except Exception as e:
            logger.warning("No se pudo iniciar procesamiento de plantilla en segundo plano (%s). Procesando en primer plano.", e, exc_info=True)

    return await _procesar_plantilla_sync_fallback(
        content, filename_to_use, file.filename, user_id,
        validar, bloquea_con_errores, correcciones_dict, file_size
    )


async def _obtener_resultado_plantilla_handler(process_id: str, user: Dict):
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


async def _event_stream_progreso_plantilla(process_id: str, request: Request, estado_service: ProcesoEstadoService):
    """Generador SSE que emite el progreso de un proceso de plantilla hasta que finalice o el cliente se desconecte."""
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
            payload = _generate_stream_payload(estado_actual)
            yield f"data: {json.dumps(payload)}\n\n"
            ultimo_updated_at = updated_at
            ultima_version = version
        if estado_actual["status"] in ("completed", "error"):
            break
        await asyncio.sleep(1)


async def _stream_progreso_plantilla_handler(
    process_id: str, request: Request, user: Dict
) -> StreamingResponse:
    if not process_id.startswith("plantilla-"):
        raise HTTPException(status_code=400, detail="process_id debe ser de tipo plantilla (plantilla-xxx)")
    estado_service = ProcesoEstadoService()
    estado = estado_service.obtener_estado(process_id)
    if not estado:
        raise HTTPException(status_code=404, detail="Proceso no encontrado")
    user_id = get_user_id(user)
    if estado.get("user_id") and estado["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a este proceso")

    return StreamingResponse(
        _event_stream_progreso_plantilla(process_id, request, estado_service),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )


async def _get_ultimo_pedido_handler(incluir_respuesta: bool, user: Dict):
    try:
        user_id = get_user_id(user)

        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)

            ultimo_pedido = repo.get_ultimo_pedido(user_id)

            if not ultimo_pedido:
                return JSONResponse(status_code=200, content=None)

            pedido_completo = repo.get_pedido_completo(ultimo_pedido["pedido_id"])

            if not pedido_completo:
                raise HTTPException(
                    status_code=500,
                    detail="Error al obtener detalles del último pedido"
                )

            if incluir_respuesta:
                respuesta_repo = PedidoRespuestaRepository(conn)
                pedido_id = pedido_completo["cabecera"]["pedido_id"]
                respuesta = respuesta_repo.obtener_respuesta_activa(pedido_id)
                if respuesta:
                    pedido_completo["respuesta_proveedor"] = respuesta

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


async def _listar_pedidos_plantillas_handler(
    estado: Optional[str],
    numero_pedido: Optional[str],
    limit: int,
    offset: int,
    solo_pendientes_accion: Optional[str],
    user: Dict,
):
    try:
        user_id = get_user_id(user)
        filtrar_pendientes = (
            solo_pendientes_accion is not None
            and str(solo_pendientes_accion).lower() in ("true", "1")
        )

        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)

            resultado = repo.get_pedidos_con_filtros(
                estado=estado,
                numero_pedido=numero_pedido.strip() if numero_pedido else None,
                creado_por=None,  # Sin filtrar por usuario — visibles para mabel.view
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


async def _descargar_plantilla(
    *,
    user: Dict,
    pedido_id: Optional[str] = None,
    archivo_id: Optional[int] = None
):
    """Descarga el archivo Excel original que fue subido para un pedido."""
    try:
        if not ENABLE_FILE_STORAGE:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "storage_disabled",
                    "message": "El almacenamiento de archivos está deshabilitado. Contacta al administrador."
                }
            )

        user_id = get_user_id(user)
        archivo_info = _get_archivo_info(pedido_id, archivo_id)

        from src.services.file_storage_service import get_file_storage, FileStorageError

        try:
            storage = get_file_storage()
            contenido, _ = storage.descargar_archivo(archivo_info["storage_path"])
        except FileStorageError as e:
            logger.error(f"Error al descargar archivo del storage: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "storage_error",
                    "message": f"Error al recuperar el archivo: {str(e)}"
                }
            )

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

        nombre_descarga = archivo_info["nombre_original"]

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


async def _info_archivo_plantilla_handler(pedido_id: str):
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
                        _KEY_TAMANO_BYTES: archivo_info[_KEY_TAMANO_BYTES],
                        "tamaño_mb": round(archivo_info[_KEY_TAMANO_BYTES] / (1024 * 1024), 2),
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


async def _buscar_pedidos_por_numero_handler(numero_pedido: Optional[str], limit: int):
    try:
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)

            resultado = repo.get_pedidos_con_filtros(
                numero_pedido=numero_pedido.strip() if numero_pedido else None,
                creado_por=None,  # Sin filtrar por usuario — visibles para mabel.view
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


async def _listar_archivos_originales_handler(limit: int, solo_activos: bool, user: Dict):
    try:
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

            has_odcsap = any(_PERM_ODCSAP in str(p).lower() for p in permissions)
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

            archivos_enriquecidos = []
            for archivo in archivos:
                archivos_enriquecidos.append({
                    "archivo_id": archivo["archivo_id"],
                    "pedido_id": archivo["pedido_id"],
                    "numero_pedido": archivo.get("numero_pedido"),
                    "nombre_original": archivo["nombre_original"],
                    _KEY_TAMANO_BYTES: archivo[_KEY_TAMANO_BYTES],
                    "tamaño_mb": round(archivo[_KEY_TAMANO_BYTES] / (1024 * 1024), 2) if archivo[_KEY_TAMANO_BYTES] else 0,
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


async def _eliminar_archivo_original_handler(archivo_id: int, eliminar_fisicamente: bool, user: Dict):
    try:
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

            if archivo_info["subido_por"] != user_id:
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

            if not archivo_info["activo"]:
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "warning",
                        "message": "El archivo ya estaba eliminado",
                        "archivo_id": archivo_id
                    }
                )

            archivo_repo.eliminar(archivo_id)

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


async def _storage_health_check_handler():
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


def register_plantillas_endpoints(app: FastAPI):
    """Registra los endpoints de plantillas Excel en la aplicación FastAPI."""

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
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """Sube y valida una plantilla Excel para procesamiento."""
        return await _upload_plantilla_handler(
            file, validar, bloquea_con_errores, exportar_log,
            modo_tiendas, confirmar_sincronizacion, correcciones_codigos, user
        )

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
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Sube una plantilla Excel para procesamiento en segundo plano (Celery).
        Responde de inmediato con process_id; el resultado se consulta con
        GET /api/plantillas/resultado/{process_id} o GET /api/plantillas/stream/{process_id}.

        Si Redis/Celery, el worker o el almacenamiento temporal no están disponibles,
        ejecuta el procesamiento en primer plano como fallback sync. Con force_sync=true
        se ejecuta siempre en primer plano (200 + resultado, misma forma que sync).
        """
        return await _upload_plantilla_async_handler(
            file, validar, bloquea_con_errores, modo_tiendas,
            confirmar_sincronizacion, force_sync, correcciones_codigos, user
        )

    @app.get("/api/plantillas/resultado/{process_id}", tags=["Plantillas"])
    async def obtener_resultado_plantilla(
        process_id: str,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """Obtiene el resultado del procesamiento async de una plantilla."""
        return await _obtener_resultado_plantilla_handler(process_id, user)

    @app.get("/api/plantillas/stream/{process_id}", tags=["Plantillas"])
    async def stream_progreso_plantilla(
        process_id: str,
        request: Request,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """Stream SSE del progreso del procesamiento de plantilla."""
        return await _stream_progreso_plantilla_handler(process_id, request, user)

    @app.get("/api/plantillas/ultimo", tags=["Plantillas"])
    async def get_ultimo_pedido(
        incluir_respuesta: bool = Query(False, description="Incluir respuesta del proveedor si existe"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """Obtiene el último pedido cargado por el usuario autenticado."""
        return await _get_ultimo_pedido_handler(incluir_respuesta, user)

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
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """Lista pedidos para la página cargar-plantilla (incluye estado BORRADOR)."""
        return await _listar_pedidos_plantillas_handler(
            estado, numero_pedido, limit, offset, solo_pendientes_accion, user
        )

    @app.get("/api/plantillas/{pedido_id}/descargar-original", tags=["Plantillas"])
    async def descargar_plantilla_original(
        pedido_id: str = Path(..., description="ID del pedido (GUID)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_MABEL, _PERM_ODCSAP]))
    ):
        """Descarga el archivo Excel original subido para un pedido."""
        return await _descargar_plantilla(
            user=user,
            pedido_id=pedido_id
        )

    @app.get("/api/plantillas/archivos/{archivo_id}/descargar-original", tags=["Plantillas"])
    async def descargar_plantilla_original_por_archivo(
        archivo_id: int = Path(..., description="ID del archivo original"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_MABEL, _PERM_ODCSAP]))
    ):
        """Descarga un archivo Excel original por su ID de archivo."""
        return await _descargar_plantilla(
            user=user,
            archivo_id=archivo_id
        )

    @app.get("/api/plantillas/{pedido_id}/info-archivo", tags=["Plantillas"])
    async def info_archivo_plantilla(
        pedido_id: str = Path(..., description="ID del pedido (GUID)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_MABEL, _PERM_ODCSAP]))
    ):
        """Obtiene información sobre el archivo Excel original de un pedido."""
        return await _info_archivo_plantilla_handler(pedido_id)

    @app.get("/api/plantillas/buscar", tags=["Plantillas"])
    async def buscar_pedidos_por_numero(
        numero_pedido: Optional[str] = Query(None, description="Número de pedido a buscar (búsqueda parcial)"),
        limit: int = Query(20, ge=1, le=100, description="Límite de resultados"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """Busca pedidos por número de pedido (búsqueda parcial)."""
        return await _buscar_pedidos_por_numero_handler(numero_pedido, limit)

    @app.get("/api/plantillas/archivos", tags=["Plantillas - Archivos Originales"])
    async def listar_archivos_originales(
        limit: int = Query(50, ge=1, le=200, description="Límite de registros"),
        solo_activos: bool = Query(True, description="Solo mostrar archivos activos"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_MABEL, _PERM_ODCSAP]))
    ):
        """Lista los archivos Excel originales subidos por el usuario."""
        return await _listar_archivos_originales_handler(limit, solo_activos, user)

    @app.delete("/api/plantillas/archivos/{archivo_id}", tags=["Plantillas - Archivos Originales"])
    async def eliminar_archivo_original(
        archivo_id: int = Path(..., description="ID del archivo a eliminar"),
        eliminar_fisicamente: bool = Query(False, description="Si es true, elimina también del storage (MinIO)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_MABEL, _PERM_ODCSAP]))
    ):
        """Elimina un archivo Excel original (soft delete por defecto)."""
        return await _eliminar_archivo_original_handler(archivo_id, eliminar_fisicamente, user)

    @app.get("/api/plantillas/storage/health", tags=["Plantillas"])
    async def storage_health_check(
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """Verifica el estado del servicio de almacenamiento de archivos."""
        return await _storage_health_check_handler()
