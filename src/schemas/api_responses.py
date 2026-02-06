"""
Modelos de respuesta estándar para documentación OpenAPI.

Este módulo define los esquemas de respuesta para errores comunes,
permitiendo documentarlos automáticamente en Swagger/OpenAPI.

Referencia: Guía de Buenas Prácticas - Sección 4 (Prácticas API y Backend)
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ============================================================================
# Modelos de Error
# ============================================================================

class ValidationErrorDetail(BaseModel):
    """Detalle de un error de validación de Pydantic."""
    loc: List[str] = Field(..., description="Ubicación del error (ej: ['body', 'campo'])")
    msg: str = Field(..., description="Mensaje de error")
    type: str = Field(..., description="Tipo de error")


class ValidationErrorResponse(BaseModel):
    """Respuesta de error de validación (422)."""
    error: str = Field(default="Error de validación del request", description="Mensaje de error")
    type: str = Field(default="validation_error", description="Tipo de error")
    details: List[ValidationErrorDetail] = Field(..., description="Detalles de los errores")
    body_received: Optional[str] = Field(None, description="Primeros 200 caracteres del body recibido")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Error de validación del request",
                "type": "validation_error",
                "details": [
                    {
                        "loc": ["body", "numero_pedido"],
                        "msg": "field required",
                        "type": "value_error.missing"
                    }
                ],
                "body_received": "{\"items\": []}"
            }
        }


class HTTPErrorResponse(BaseModel):
    """Respuesta de error HTTP genérico (401, 403, 404, etc.)."""
    error: str = Field(..., description="Mensaje de error")
    type: str = Field(default="http_exception", description="Tipo de error")
    status_code: int = Field(..., description="Código HTTP del error")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Token JWT inválido o expirado",
                "type": "http_exception",
                "status_code": 401
            }
        }


class BusinessErrorResponse(BaseModel):
    """Respuesta de error de negocio (400)."""
    error: str = Field(..., description="Mensaje de error legible")
    type: str = Field(default="business_exception", description="Tipo de error")
    error_code: str = Field(..., description="Código de error para identificación programática")
    status_code: int = Field(default=400, description="Código HTTP")
    data: Optional[Dict[str, Any]] = Field(None, description="Datos adicionales del error")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "No se puede procesar el pedido sin validación SAP",
                "type": "business_exception",
                "error_code": "SAP_VALIDATION_REQUIRED",
                "status_code": 400,
                "data": {
                    "pedido_id": "123e4567-e89b-12d3-a456-426614174000",
                    "items_sin_validar": 5
                }
            }
        }


class InternalErrorResponse(BaseModel):
    """Respuesta de error interno del servidor (500)."""
    error: str = Field(default="Error interno del servidor", description="Mensaje de error")
    type: str = Field(default="internal_server_error", description="Tipo de error")
    detail: Optional[str] = Field(None, description="Detalles (solo en modo DEBUG)")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Error interno del servidor",
                "type": "internal_server_error",
                "detail": None
            }
        }


class ServiceUnavailableResponse(BaseModel):
    """Respuesta de servicio no disponible (503)."""
    error: str = Field(..., description="Mensaje de error")
    type: str = Field(default="mba3_connection_error", description="Tipo de error")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "No se pudo conectar con el servicio MBA3",
                "type": "mba3_connection_error"
            }
        }


class RateLimitResponse(BaseModel):
    """Respuesta de límite de rate excedido (429)."""
    error: str = Field(default="Rate limit exceeded", description="Mensaje de error")
    type: str = Field(default="rate_limit_exceeded", description="Tipo de error")
    retry_after: int = Field(..., description="Segundos hasta poder reintentar")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Rate limit exceeded",
                "type": "rate_limit_exceeded",
                "retry_after": 60
            }
        }


# ============================================================================
# Respuestas estándar para OpenAPI
# ============================================================================

# Diccionario de respuestas comunes para usar en endpoints
COMMON_RESPONSES = {
    400: {
        "model": BusinessErrorResponse,
        "description": "Error de validación o negocio"
    },
    401: {
        "model": HTTPErrorResponse,
        "description": "No autenticado - Token JWT faltante o inválido"
    },
    403: {
        "model": HTTPErrorResponse,
        "description": "No autorizado - Sin permisos para esta operación"
    },
    404: {
        "model": HTTPErrorResponse,
        "description": "Recurso no encontrado"
    },
    422: {
        "model": ValidationErrorResponse,
        "description": "Error de validación de datos de entrada"
    },
    429: {
        "model": RateLimitResponse,
        "description": "Límite de requests excedido"
    },
    500: {
        "model": InternalErrorResponse,
        "description": "Error interno del servidor"
    },
    503: {
        "model": ServiceUnavailableResponse,
        "description": "Servicio externo no disponible"
    }
}

# Respuestas para endpoints de lectura (GET)
READ_RESPONSES = {
    401: COMMON_RESPONSES[401],
    403: COMMON_RESPONSES[403],
    404: COMMON_RESPONSES[404],
    500: COMMON_RESPONSES[500],
}

# Respuestas para endpoints de escritura (POST, PUT, DELETE)
WRITE_RESPONSES = {
    400: COMMON_RESPONSES[400],
    401: COMMON_RESPONSES[401],
    403: COMMON_RESPONSES[403],
    404: COMMON_RESPONSES[404],
    422: COMMON_RESPONSES[422],
    500: COMMON_RESPONSES[500],
}

# Respuestas para endpoints que interactúan con servicios externos (SAP, MBA3)
EXTERNAL_SERVICE_RESPONSES = {
    400: COMMON_RESPONSES[400],
    401: COMMON_RESPONSES[401],
    403: COMMON_RESPONSES[403],
    500: COMMON_RESPONSES[500],
    503: COMMON_RESPONSES[503],
}
