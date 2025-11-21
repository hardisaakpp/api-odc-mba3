"""
Exception handlers centralizados para FastAPI.
"""

import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from exceptions import QueryValidationError, MBA3ConnectionError, MBA3QueryError

logger = logging.getLogger(__name__)


def setup_exception_handlers(app: FastAPI):
    """Configura los exception handlers para la aplicación."""
    
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

