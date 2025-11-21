"""
Excepciones personalizadas para la aplicación.
"""


class QueryValidationError(Exception):
    """Excepción para errores de validación de consultas SQL."""
    pass


class MBA3ConnectionError(Exception):
    """Excepción para errores de conexión con MBA3."""
    pass


class MBA3QueryError(Exception):
    """Excepción para errores al ejecutar consultas en MBA3."""
    pass

