"""
Módulo de utilidades para la API de consultas MBA3.
"""

# Nota: Este __init__.py permite que el directorio utils/ sea reconocido como un paquete
# Las funciones principales están en utils.py (archivo en src/)
# Este directorio contiene módulos adicionales como email_notifier

# Importar funciones del módulo utils.py (archivo en el nivel padre)
# Usamos importlib para evitar conflictos entre el módulo utils.py y el paquete utils/
import sys
import importlib.util
from pathlib import Path

# Obtener la ruta del módulo utils.py (archivo en src/)
_parent_dir = Path(__file__).parent.parent
_utils_module_path = _parent_dir / "utils.py"

# Cargar el módulo utils.py dinámicamente
if _utils_module_path.exists():
    spec = importlib.util.spec_from_file_location("utils_module", _utils_module_path)
    if spec and spec.loader:
        utils_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(utils_module)
        
        # Re-exportar funciones del módulo utils.py
        get_source_from_headers = utils_module.get_source_from_headers
        normalize_query = utils_module.normalize_query
        validate_query = utils_module.validate_query
        parse_query = utils_module.parse_query
        save_query_to_file = utils_module.save_query_to_file
        normalizar_codigo_producto = utils_module.normalizar_codigo_producto
        validar_longitud_minima_codigo = utils_module.validar_longitud_minima_codigo
    else:
        # Fallback: intentar importación directa
        import utils as utils_module
        get_source_from_headers = utils_module.get_source_from_headers
        normalize_query = utils_module.normalize_query
        validate_query = utils_module.validate_query
        parse_query = utils_module.parse_query
        save_query_to_file = utils_module.save_query_to_file
else:
    raise ImportError("No se pudo encontrar el módulo utils.py")

# Exportar funciones del módulo email_notifier
from .email_notifier import (
    send_migration_notification,
    send_error_notification,
    send_homologacion_notification,
    send_oc_ready_for_dispatch_notification,
    send_plantilla_upload_notification
)

# Exportar helpers de respuestas estandarizadas (Buenas Prácticas - Sección 4)
from .response_helpers import (
    success_response,
    error_response,
    paginated_response,
    validation_error_response,
    not_found_response,
    business_error_response,
    ErrorCodes
)

__all__ = [
    # Funciones de utils.py
    "get_source_from_headers",
    "normalize_query",
    "validate_query",
    "parse_query",
    "save_query_to_file",
    "normalizar_codigo_producto",
    "validar_longitud_minima_codigo",
    # Email notifier
    "send_migration_notification",
    "send_error_notification",
    "send_homologacion_notification",
    "send_oc_ready_for_dispatch_notification",
    "send_plantilla_upload_notification",
    # Response helpers (Buenas Prácticas)
    "success_response",
    "error_response",
    "paginated_response",
    "validation_error_response",
    "not_found_response",
    "business_error_response",
    "ErrorCodes",
]
