"""
Exception handlers centralizados para FastAPI.
"""

import logging
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from src.exceptions import QueryValidationError, MBA3ConnectionError, MBA3QueryError, BusinessException

logger = logging.getLogger(__name__)


def setup_exception_handlers(app: FastAPI):
    """Configura los exception handlers para la aplicación."""
    
    # Mensajes amigables para validaciones de longitud (numero_pedido, mensaje)
    _MENSAJES_VALIDACION = {
        "numero_pedido": "El número de pedido no puede superar 100 caracteres.",
        "mensaje": "El mensaje del pedido no puede superar 100 caracteres.",
    }

    def _traducir_error_validacion(err: dict) -> dict:
        """Traduce errores de Pydantic a mensajes amigables para el usuario."""
        loc = err.get("loc", [])
        msg = str(err.get("msg", ""))
        err_type = str(err.get("type", ""))
        ctx = err.get("ctx") or {}
        # loc puede ser ["body", "numero_pedido"] o ["body", "mensaje"]
        field = loc[-1] if (len(loc) >= 1 and isinstance(loc[-1], str) and loc[-1] in _MENSAJES_VALIDACION) else None
        # Detectar error de longitud máxima (Pydantic v1: max_length; v2: string_too_long; ctx.max_length)
        es_longitud = (
            "max_length" in err_type
            or "string_too_long" in err_type
            or "max_length" in msg.lower()
            or "at most" in msg.lower()
            or "100 character" in msg.lower()
            or ctx.get("max_length") == 100
        )
        if field and es_longitud:
            err = {**err, "msg": _MENSAJES_VALIDACION[field]}
        return err

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """
        Maneja errores de validación de Pydantic (422).
        
        Esto ocurre cuando el body del request no coincide con el modelo esperado.
        Traduce mensajes de numero_pedido/mensaje (max_length) al español.
        """
        # Obtener el body del request para logging
        body = None
        try:
            body = await request.body()
            if body:
                body_str = body.decode('utf-8')[:500]  # Primeros 500 caracteres
                logger.error(f"❌ Error de validación de request (422)")
                logger.error(f"   URL: {request.url}")
                logger.error(f"   Method: {request.method}")
                logger.error(f"   Body recibido: {body_str}")
        except Exception:
            pass

        errors = exc.errors()
        logger.error(f"❌ Errores de validación: {errors}")

        # Traducir mensajes para numero_pedido y mensaje (max 100 caracteres)
        details = [_traducir_error_validacion(e) for e in errors]
        # Mensaje principal para el frontend: primero en español si aplica
        first_msg = details[0].get("msg", "Error de validación del request") if details else "Error de validación del request"
        error_summary = first_msg if isinstance(first_msg, str) and len(first_msg) < 200 else "Error de validación del request"

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": error_summary,
                "message": error_summary,
                "type": "validation_error",
                "details": details,
                "body_received": body.decode('utf-8')[:200] if body else None
            }
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """
        Maneja errores HTTPException (401, 403, 404, etc.).
        
        Esto asegura que los errores HTTP se manejen correctamente
        y se logueen apropiadamente.
        """
        # Logging detallado para errores de autenticación/autorización
        if exc.status_code in (401, 403):
            logger.warning(f"❌ Error de autenticación/autorización ({exc.status_code})")
            logger.warning(f"   URL: {request.url}")
            logger.warning(f"   Method: {request.method}")
            logger.warning(f"   Detail: {exc.detail}")
        elif exc.status_code == 404:
            logger.debug(f"🔍 Recurso no encontrado (404): {request.url}")
        else:
            logger.warning(f"⚠️ HTTPException ({exc.status_code}): {exc.detail}")
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "type": "http_exception",
                "status_code": exc.status_code
            }
        )
    
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Maneja errores de validación (ValueError)."""
        logger.warning(f"Error de validación: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": str(exc), "type": "validation_error"}
        )
    
    @app.exception_handler(QueryValidationError)
    async def query_validation_error_handler(request: Request, exc: QueryValidationError):
        """Maneja errores de validación de consultas SQL."""
        logger.warning(f"Error de validación de consulta: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": str(exc), "type": "query_validation_error"}
        )
    
    @app.exception_handler(MBA3ConnectionError)
    async def mba3_connection_error_handler(request: Request, exc: MBA3ConnectionError):
        """Maneja errores de conexión con MBA3."""
        logger.error(f"Error de conexión con MBA3: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": str(exc), "type": "mba3_connection_error"}
        )
    
    @app.exception_handler(MBA3QueryError)
    async def mba3_query_error_handler(request: Request, exc: MBA3QueryError):
        """Maneja errores al ejecutar consultas en MBA3."""
        logger.error(f"Error al ejecutar consulta en MBA3: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": str(exc), "type": "mba3_query_error"}
        )
    
    @app.exception_handler(BusinessException)
    async def business_exception_handler(request: Request, exc: BusinessException):
        """
        Maneja errores de lógica de negocio (BusinessException).
        
        Estos errores representan validaciones críticas que bloquean operaciones,
        como validación SAP obligatoria antes de persistir.
        """
        logger.warning(f"⚠️ Error de negocio: {str(exc)}")
        
        # Construir respuesta estructurada
        response_content = {
            "type": "business_exception",
            "error_code": exc.error_code,
            "message": exc.message,
            "status_code": 400
        }
        
        # Agregar datos estructurados si existen
        if exc.data:
            response_content.update(exc.data)
        
        # Mantener compatibilidad con código antiguo que espera "error"
        if "error" not in response_content:
            response_content["error"] = exc.message
        
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_content
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Maneja errores generales no capturados."""
        logger.error(f"Error inesperado: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Error interno del servidor",
                "type": "internal_server_error",
                "detail": str(exc) if logger.level <= logging.DEBUG else None
            }
        )

