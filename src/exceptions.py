"""
Excepciones personalizadas para la aplicación.
"""
from typing import Optional


class QueryValidationError(Exception):
    """Excepción para errores de validación de consultas SQL."""
    pass


class MBA3ConnectionError(Exception):
    """Excepción para errores de conexión con MBA3."""
    pass


class MBA3QueryError(Exception):
    """Excepción para errores al ejecutar consultas en MBA3."""
    pass


class BusinessException(Exception):
    """
    Excepción para errores de lógica de negocio.
    
    Se usa para validaciones críticas que deben bloquear operaciones,
    como validación SAP obligatoria antes de persistir pedidos.
    
    Attributes:
        message: Mensaje de error legible
        error_code: Código de error para identificación programática
        data: Datos estructurados adicionales (dict) para el frontend
    """
    def __init__(self, message: str, error_code: Optional[str] = None, data: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "BUSINESS_ERROR"
        self.data = data or {}
