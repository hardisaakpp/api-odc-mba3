"""
Tarea Celery para procesar plantilla Excel en segundo plano.

El archivo se sube a storage temporal (MinIO/S3); esta tarea lo descarga,
ejecuta validar_y_procesar_archivo_excel y guarda el resultado en Redis.
Opcionalmente guarda el archivo original en la ruta definitiva y elimina el temporal.

La respuesta guardada en Redis tiene la misma estructura que el upload síncrono
(archivo_original, file_info.size_mb, metadata.uploaded_at) para paridad con el flujo sync.
"""
import logging
from typing import Optional, Dict, Any

from celery import Task
from src.celery_app import celery_app
from src.database.services.pedido_service import PedidoService
from src.database.services.proceso_estado_service import ProcesoEstadoService
from src.exceptions import BusinessException
from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)


def _sanitize_resultado_for_redis(resultado: Dict[str, Any]) -> Dict[str, Any]:
    """Asegura que el resultado sea JSON-serializable para Redis."""
    if not resultado:
        return resultado
    out = dict(resultado)
    # Evitar objetos no serializables (pandas, etc.)
    if "validation" in out and out["validation"] is not None:
        if hasattr(out["validation"], "to_dict"):
            out["validation"] = out["validation"].to_dict()
    return out


@celery_app.task(
    name='src.tasks.celery_plantilla_upload.procesar_plantilla_upload',
    bind=True,
    max_retries=0,
    time_limit=600,   # 10 min máximo
    soft_time_limit=540
)
def procesar_plantilla_upload(
    self: Task,
    process_id: str,
    user_id: str,
    storage_path: str,
    filename: str,
    validar: bool = True,
    bloquea_con_errores: bool = True,
    modo_tiendas: str = "validar_estricto",
    correcciones_codigos: Optional[Dict[str, str]] = None
):
    """
    Procesa una plantilla Excel en background: descarga del storage temporal,
    valida/procesa y actualiza estado en Redis. Elimina el archivo temporal al final.
    """
    estado_service = ProcesoEstadoService()
    file_content: Optional[bytes] = None

    try:
        logger.info(f"🚀 Iniciando procesamiento plantilla Celery: {process_id}")

        estado_service.actualizar_progreso(
            process_id, "leyendo_archivo", 10,
            "Descargando archivo desde almacenamiento temporal..."
        )

        from src.services.file_storage_service import get_file_storage, FileStorageError
        storage = get_file_storage()
        file_content, _ = storage.descargar_archivo(storage_path)

        estado_service.actualizar_progreso(
            process_id, "procesando", 30,
            "Validando y procesando plantilla Excel..."
        )

        service = PedidoService()
        resultado = service.validar_y_procesar_archivo_excel(
            file_content=file_content,
            filename=filename,
            usuario_id=user_id,
            validar_antes_de_guardar=validar,
            bloquea_con_errores=bloquea_con_errores,
            tiendas_permitidas=None,
            modo_tiendas=modo_tiendas,
            correcciones_codigos=correcciones_codigos
        )

        # Guardar archivo original en ruta definitiva si procesamiento OK y está habilitado
        # (misma lógica que upload síncrono; respuesta con archivo_original para paridad)
        from src.config import ENABLE_FILE_STORAGE
        archivo_original: Dict[str, Any] = {
            "guardado": False,
            "mensaje": "Almacenamiento deshabilitado o no aplicable" if not ENABLE_FILE_STORAGE else "No guardado",
            "descarga_disponible": False
        }
        if ENABLE_FILE_STORAGE and resultado.get("pedido_id"):
            try:
                path_final = storage.guardar_archivo(
                    contenido=file_content,
                    pedido_id=resultado["pedido_id"],
                    nombre_original=filename,
                    usuario_id=user_id
                )
                from src.database.connection import get_db_connection_context
                from src.database.repositories.archivo_plantilla_repository import ArchivoPlantillaRepository
                with get_db_connection_context() as conn:
                    archivo_repo = ArchivoPlantillaRepository(conn)
                    archivo_repo.crear(
                        pedido_id=resultado["pedido_id"],
                        nombre_original=filename,
                        storage_path=path_final,
                        tamaño_bytes=len(file_content),
                        subido_por=user_id
                    )
                logger.info(f"✅ Archivo original guardado en storage definitivo: {path_final}")
                archivo_original = {
                    "guardado": True,
                    "storage_path": path_final,
                    "descarga_disponible": True
                }
            except Exception as e:
                logger.warning(f"⚠️ No se pudo guardar archivo original en storage definitivo: {e}")
                archivo_original = {
                    "guardado": False,
                    "error": str(e),
                    "descarga_disponible": False
                }

        # Resultado para el cliente (misma forma que el upload síncrono: paridad async/sync)
        file_size = len(file_content)
        response_result = {
            "status": resultado.get("status", "error"),
            "message": _mensaje_respuesta(resultado),
            "pedido_id": resultado.get("pedido_id"),
            "numero_pedido": resultado.get("numero_pedido"),
            "formato_detectado": resultado.get("formato_detectado"),
            "articulos_cargados": resultado.get("articulos_cargados", 0),
            "distribuciones_cargadas": resultado.get("distribuciones_cargadas", 0),
            "validation": resultado.get("validation"),
            "correcciones_aplicadas": resultado.get("correcciones_aplicadas", []),
            "file_info": {
                "filename": filename,
                "size_mb": round(file_size / (1024 * 1024), 2)
            },
            "metadata": {
                "uploaded_by": user_id,
                "uploaded_at": ahora_naive().isoformat()
            },
            "archivo_original": archivo_original
        }
        response_result = _sanitize_resultado_for_redis(response_result)

        estado_service.actualizar_progreso(
            process_id, "completado", 100,
            "Plantilla procesada correctamente."
        )
        estado_service.completar_proceso(process_id, response_result)
        logger.info(f"✅ Plantilla Celery completada: {process_id}")

    except FileStorageError as e:
        logger.error(f"❌ Error storage en plantilla {process_id}: {e}", exc_info=True)
        estado_service.marcar_error(process_id, f"Error al acceder al archivo: {str(e)}")
        raise
    except BusinessException as e:
        logger.error(f"❌ Error de negocio en plantilla {process_id}: {e}", exc_info=True)
        error_data = _sanitize_resultado_for_redis(e.data) if e.data else None
        if error_data:
            logger.info(f"📋 Guardando error_data para {process_id} (validacion_sap={bool(error_data.get('validacion_sap'))})")
        estado_service.marcar_error(process_id, e.message, error_data=error_data)
        raise
    except Exception as e:
        logger.error(f"❌ Error en plantilla Celery {process_id}: {e}", exc_info=True)
        # Por si la excepción es BusinessException pero no fue capturada (ej. worker con código antiguo)
        error_data = None
        data_attr = getattr(e, "data", None)
        if data_attr and isinstance(data_attr, dict):
            error_data = _sanitize_resultado_for_redis(data_attr)
            logger.info(f"📋 Error con .data detectado, guardando error_data para {process_id}")
        estado_service.marcar_error(process_id, str(e), error_data=error_data)
        raise
    finally:
        # Eliminar archivo temporal
        try:
            from src.services.file_storage_service import get_file_storage, FileStorageError
            storage = get_file_storage()
            if storage.archivo_existe(storage_path):
                storage.eliminar_archivo(storage_path)
                logger.info(f"🗑️ Archivo temporal eliminado: {storage_path}")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo eliminar archivo temporal {storage_path}: {e}")


def _mensaje_respuesta(resultado: Dict[str, Any]) -> str:
    if resultado.get("status") == "validation_error":
        errores = resultado.get("errores", [])
        return errores[0] if errores else "Plantilla validada pero tiene errores críticos"
    if resultado.get("status") == "error":
        return resultado.get("message", "Error al procesar plantilla")
    return "Plantilla procesada y guardada exitosamente"
