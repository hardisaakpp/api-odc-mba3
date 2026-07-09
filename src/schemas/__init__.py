"""
Módulo de esquemas para la aplicación.

Este módulo contiene:
- api_responses: Modelos de respuesta estándar para OpenAPI
"""

from .api_responses import (
    ValidationErrorResponse,
    ValidationErrorDetail,
    HTTPErrorResponse,
    BusinessErrorResponse,
    InternalErrorResponse,
    ServiceUnavailableResponse,
    RateLimitResponse,
    COMMON_RESPONSES,
    READ_RESPONSES,
    WRITE_RESPONSES,
    EXTERNAL_SERVICE_RESPONSES,
)

__all__ = [
    "ValidationErrorResponse",
    "ValidationErrorDetail",
    "HTTPErrorResponse",
    "BusinessErrorResponse",
    "InternalErrorResponse",
    "ServiceUnavailableResponse",
    "RateLimitResponse",
    "COMMON_RESPONSES",
    "READ_RESPONSES",
    "WRITE_RESPONSES",
    "EXTERNAL_SERVICE_RESPONSES",
]
