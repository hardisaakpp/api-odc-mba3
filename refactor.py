import re
import json

with open('src/endpoints/plantillas.py', 'r', encoding='utf-8') as f:
    code = f.read()

# ADD HELPERS
helpers = '''
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
    except json.JSONDecodeError as e:
        logger.warning(f"Error al parsear correcciones_codigos JSON: {e}")
        raise HTTPException(status_code=400, detail=f"Formato JSON inválido en correcciones_codigos: {str(e)}")

def _validar_archivo_plantilla(file_size: int):
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"El archivo es demasiado grande. Tamaño máximo: {MAX_FILE_SIZE / (1024*1024):.1f} MB"
        )
    if file_size == 0:
        raise HTTPException(status_code=400, detail="El archivo está vacío")

def _guardar_archivo_en_storage(content: bytes, filename: str, file_size: int, pedido_id: str, user_id: str) -> dict:
    try:
        from src.services.file_storage_service import get_file_storage, FileStorageError
        storage = get_file_storage()
        storage_path = storage.guardar_archivo(
            contenido=content, pedido_id=pedido_id, nombre_original=filename, usuario_id=user_id
        )
        with get_db_connection_context() as conn:
            archivo_repo = ArchivoPlantillaRepository(conn)
            archivo_repo.crear(
                pedido_id=pedido_id, nombre_original=filename, storage_path=storage_path,
                tamano_bytes=file_size, subido_por=user_id
            )
        logger.info(f"✅ Archivo Excel original guardado en storage: {storage_path}")
        return {"guardado": True, "storage_path": storage_path, "descarga_disponible": True}
    except Exception as e:
        logger.warning(f"⚠️ Error al guardar archivo: {e}")
        return {"guardado": False, "error": str(e), "descarga_disponible": False}

def _determinar_respuesta_procesamiento(resultado, file, file_size, user_id) -> tuple[int, dict]:
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
        "file_info": {"filename": file.filename, "size_mb": round(file_size / (1024 * 1024), 2)},
        "metadata": {"uploaded_by": user_id, "uploaded_at": ahora_naive().isoformat()}
    }
    status_code = 200
    if resultado["status"] == "validation_error" and not tiene_pedido_guardado:
        status_code = 400
    if resultado["status"] == "error":
        raise HTTPException(
            status_code=400,
            detail=f"Error al procesar plantilla: {resultado.get('errores', ['Error desconocido'])}"
        )
    return status_code, response_data

def _procesar_plantilla_async(content, filename, user_id, validar, bloquea_con_errores, modo_tiendas, correcciones_dict):
    from src.services.file_storage_service import get_file_storage
    estado_service = ProcesoEstadoService()
    process_id = estado_service.crear_proceso_plantilla(user_id=user_id)
    storage = get_file_storage()
    storage_path = storage.guardar_archivo_temporal(contenido=content, process_id=process_id, nombre_original=filename)
    from src.tasks.celery_plantilla_upload import procesar_plantilla_upload
    procesar_plantilla_upload.delay(
        process_id=process_id, user_id=user_id, storage_path=storage_path, filename=filename,
        validar=validar, bloquea_con_errores=bloquea_con_errores, modo_tiendas=modo_tiendas,
        correcciones_codigos=correcciones_dict
    )
    logger.info(f"📤 Plantilla encolada: {process_id} (usuario: {user_id})")
    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted", "process_id": process_id,
            "message": "Plantilla en procesamiento. Consulta GET /api/plantillas/resultado/{process_id} o GET /api/plantillas/stream/{process_id}.",
            "resultado_url": f"/api/plantillas/resultado/{process_id}",
            "stream_url": f"/api/plantillas/stream/{process_id}"
        }
    )

async def _generar_eventos_progreso(process_id, request, estado_service):
    ultimo_updated_at = None
    ultima_version = None
    while True:
        if await request.is_disconnected():
            break
        estado_actual = estado_service.obtener_estado(process_id)
        if not estado_actual:
            yield f"data: {json.dumps({'error': 'Proceso no encontrado'})}\\n\\n"
            break
        updated_at = estado_actual.get("updated_at")
        version = estado_actual.get("version", 0)
        if updated_at != ultimo_updated_at or version != ultima_version:
            payload = _construir_payload_progreso(estado_actual)
            yield f"data: {json.dumps(payload)}\\n\\n"
            ultimo_updated_at = updated_at
            ultima_version = version
        if estado_actual["status"] in ("completed", "error"):
            break
        await asyncio.sleep(1)

def _construir_payload_progreso(estado_actual):
    payload = {
        "process_id": estado_actual["process_id"], "status": estado_actual["status"],
        "step": estado_actual["step"], "progress": estado_actual["progress"],
        "message": estado_actual["message"], "updated_at": estado_actual.get("updated_at"),
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

def _obtener_info_archivo_plantilla(pedido_id: Optional[str], archivo_id: Optional[int]):
    with get_db_connection_context() as conn:
        if archivo_id is not None:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT archivo_id, pedido_id, nombre_original, storage_path, content_type, tamaño_bytes, subido_por, fecha_subida, activo, descargas, ultima_descarga, ultimo_descargador
                FROM archivo_plantilla WHERE archivo_id = ? AND activo = 1
            """, (archivo_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "archivo_id": row[0], "pedido_id": row[1], "nombre_original": row[2],
                    "storage_path": row[3], "content_type": row[4], _KEY_TAMANO_BYTES: row[5],
                    "subido_por": row[6], "fecha_subida": row[7].isoformat() if row[7] else None,
                    "activo": row[8], "descargas": row[9], "ultima_descarga": row[10].isoformat() if row[10] else None,
                    "ultimo_descargador": row[11],
                }
            return None
        return ArchivoPlantillaRepository(conn).obtener_por_pedido_id(pedido_id)

def _generar_streaming_response_archivo(archivo_info, user_id):
    from src.services.file_storage_service import get_file_storage, FileStorageError
    try:
        storage = get_file_storage()
        contenido, _ = storage.descargar_archivo(archivo_info["storage_path"])
    except FileStorageError as e:
        logger.error(f"Error al descargar archivo del storage: {e}")
        raise HTTPException(status_code=500, detail={"error": "storage_error", "message": f"Error al recuperar el archivo: {str(e)}"})
    with get_db_connection_context() as conn:
        archivo_repo = ArchivoPlantillaRepository(conn)
        archivo_repo.registrar_descarga(archivo_id=archivo_info["archivo_id"], descargado_por=user_id)
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
'''

import sys
# Insert helpers
parts = code.split('async def _upload_plantilla_handler(', 1)
code = parts[0] + helpers + '\\nasync def _upload_plantilla_handler(' + parts[1]

# Replace _upload_plantilla_handler
replacement_upload = '''async def _upload_plantilla_handler(
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
        if modo_tiendas == "sincronizar_maestro":
            if not confirmar_sincronizacion:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "confirmation_required",
                        "message": "El modo 'sincronizar_maestro' requiere confirmar_sincronizacion=true.",
                    }
                )
            logger.warning(f"OPERACION DESTRUCTIVA CONFIRMADA por usuario {get_user_id(user)}")
        
        validate_excel_file(file)
        content = await file.read()
        file_size = len(content)
        _validar_archivo_plantilla(file_size)
        user_id = get_user_id(user)
        correcciones_dict = _parse_correcciones_codigos(correcciones_codigos)
        
        logger.info(f"Iniciando procesamiento de plantilla '{file.filename}'")
        from src.database.services.pedido_service import PedidoService
        service = PedidoService()
        resultado = service.validar_y_procesar_archivo_excel(
            file_content=content, filename=file.filename or _DEFAULT_FILENAME,
            usuario_id=user_id, validar_antes_de_guardar=validar,
            bloquea_con_errores=bloquea_con_errores, tiendas_permitidas=None,
            correcciones_codigos=correcciones_dict
        )
        
        status_code, response_data = _determinar_respuesta_procesamiento(resultado, file, file_size, user_id)
        
        if exportar_log and resultado.get("validation"):
            from src.database.services.pedido_validation_exporter import PedidoValidationExporter
            excel_bytes = PedidoValidationExporter.export_to_excel_bytes(resultado["validation"])
            response_data["validation_log_excel_base64"] = base64.b64encode(excel_bytes).decode('utf-8')
            response_data["validation_log_filename"] = f"validation_log_{ahora_naive().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
        if status_code != 200:
            return JSONResponse(status_code=status_code, content=response_data)
            
        if ENABLE_FILE_STORAGE and resultado.get("pedido_id"):
            response_data["archivo_original"] = _guardar_archivo_en_storage(
                content, file.filename or _DEFAULT_FILENAME, file_size, resultado["pedido_id"], user_id
            )
        elif not ENABLE_FILE_STORAGE:
            response_data["archivo_original"] = {
                "guardado": False, "mensaje": "Almacenamiento deshabilitado", "descarga_disponible": False
            }
            
        return JSONResponse(status_code=200, content=response_data)
    except HTTPException:
        raise
    except BusinessException:
        raise
    except Exception as e:
        logger.error(f"Error al procesar plantilla: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")'''

code = re.sub(r'async def _upload_plantilla_handler\(.*?\nasync def _upload_plantilla_async_handler\(', 
              replacement_upload + '\n\n\nasync def _upload_plantilla_async_handler(', code, flags=re.DOTALL)

# Replace _upload_plantilla_async_handler
replacement_async = '''async def _upload_plantilla_async_handler(
    file: UploadFile,
    validar: bool,
    bloquea_con_errores: bool,
    modo_tiendas: str,
    confirmar_sincronizacion: bool,
    force_sync: bool,
    correcciones_codigos: Optional[str],
    user: Dict,
) -> JSONResponse:
    if modo_tiendas == "sincronizar_maestro" and not confirmar_sincronizacion:
        raise HTTPException(status_code=400, detail={"error": "confirmation_required", "message": "El modo 'sincronizar_maestro' requiere confirmar_sincronizacion=true."})
    
    validate_excel_file(file)
    content = await file.read()
    file_size = len(content)
    _validar_archivo_plantilla(file_size)
    user_id = get_user_id(user)
    correcciones_dict = _parse_correcciones_codigos(correcciones_codigos)
    
    run_async = not force_sync
    if run_async and not _celery_workers_available():
        logger.info("No hay workers Celery. Procesando en primer plano.")
        run_async = False
        
    if not ENABLE_FILE_STORAGE and run_async:
        raise HTTPException(status_code=503, detail={"error": "storage_required", "message": "Activa storage o usa force_sync"})
        
    if run_async:
        try:
            return _procesar_plantilla_async(
                content, file.filename or _DEFAULT_FILENAME, user_id, 
                validar, bloquea_con_errores, modo_tiendas, correcciones_dict
            )
        except Exception as e:
            logger.warning("Fallo inicio async (%s). Usando fallback sync.", e, exc_info=True)
            run_async = False
            
    if not run_async:
        from src.database.services.pedido_service import PedidoService
        service = PedidoService()
        resultado = await asyncio.to_thread(
            service.validar_y_procesar_archivo_excel,
            file_content=content, filename=file.filename or _DEFAULT_FILENAME,
            usuario_id=user_id, validar_antes_de_guardar=validar,
            bloquea_con_errores=bloquea_con_errores, tiendas_permitidas=None,
            correcciones_codigos=correcciones_dict
        )
        status_code, response_data = _determinar_respuesta_procesamiento(resultado, file, file_size, user_id)
        response_data.update({"fallback": "sync", "process_id": None, "async": False})
        
        if status_code != 200:
            return JSONResponse(status_code=status_code, content=response_data)
            
        if ENABLE_FILE_STORAGE and resultado.get("pedido_id"):
            response_data["archivo_original"] = _guardar_archivo_en_storage(
                content, file.filename or _DEFAULT_FILENAME, file_size, resultado["pedido_id"], user_id
            )
        else:
            response_data["archivo_original"] = {
                "guardado": False, "mensaje": "No guardado", "descarga_disponible": False
            }
        return JSONResponse(status_code=200, content=response_data)'''

code = re.sub(r'async def _upload_plantilla_async_handler\(.*?\nasync def _obtener_resultado_plantilla_handler\(', 
              replacement_async + '\n\n\nasync def _obtener_resultado_plantilla_handler(', code, flags=re.DOTALL)

# Replace _stream_progreso_plantilla_handler
replacement_stream = '''async def _stream_progreso_plantilla_handler(
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
        _generar_eventos_progreso(process_id, request, estado_service),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )'''

code = re.sub(r'async def _stream_progreso_plantilla_handler\(.*?\nasync def _get_ultimo_pedido_handler\(', 
              replacement_stream + '\n\n\nasync def _get_ultimo_pedido_handler(', code, flags=re.DOTALL)

# Replace _descargar_plantilla
replacement_descargar = '''async def _descargar_plantilla(
    *,
    user: Dict,
    pedido_id: Optional[str] = None,
    archivo_id: Optional[int] = None
):
    """Descarga el archivo Excel original que fue subido para un pedido."""
    try:
        if not ENABLE_FILE_STORAGE:
            raise HTTPException(status_code=503, detail={"error": "storage_disabled", "message": "El almacenamiento de archivos está deshabilitado."})
        user_id = get_user_id(user)
        if not pedido_id and archivo_id is None:
            raise HTTPException(status_code=400, detail={"error": "bad_request", "message": "Debes enviar pedido_id o archivo_id para descargar."})
        archivo_info = _obtener_info_archivo_plantilla(pedido_id, archivo_id)
        if not archivo_info:
            identificador = f"archivo_id={archivo_id}" if archivo_id is not None else f"pedido_id={pedido_id}"
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"No se encontró archivo original para {identificador}"})
        return _generar_streaming_response_archivo(archivo_info, user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al descargar plantilla original: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al descargar el archivo: {str(e)}")'''

code = re.sub(r'async def _descargar_plantilla\(.*$', replacement_descargar + '\n', code, flags=re.DOTALL)

with open('src/endpoints/plantillas.py', 'w', encoding='utf-8') as f:
    f.write(code)

print('Done')
