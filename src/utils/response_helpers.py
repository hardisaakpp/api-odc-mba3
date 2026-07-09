"""
Helpers para respuestas HTTP estandarizadas.

Implementa el estándar de respuestas JSON según la Guía de Buenas Prácticas:
- Sección 4: Respuestas JSON estandarizadas con success, message, data
- Sección 4: Errores con error_code y detalles claros

Uso recomendado:
    from src.utils.response_helpers import success_response, error_response, paginated_response

    # Respuesta exitosa
    return JSONResponse(content=success_response(data=mi_data, message="Operación completada"))
    
    # Respuesta de error
    return JSONResponse(
        status_code=400,
        content=error_response(
            error_code="VALIDATION_ERROR",
            message="El campo X es requerido",
            details={"campo": "X", "tipo": "required"}
        )
    )
    
    # Respuesta paginada
    return JSONResponse(content=paginated_response(
        data=items,
        total=100,
        page=1,
        page_size=20,
        message="Listado obtenido"
    ))
"""

from typing import Any, Dict, List, Optional, Union
from datetime import datetime


def success_response(
    data: Any = None,
    message: str = "Operación exitosa",
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Genera una respuesta JSON exitosa estandarizada.
    
    Formato:
    {
        "success": true,
        "message": "...",
        "data": {...},
        "metadata": {...}  // opcional
    }
    
    Args:
        data: Datos a retornar (cualquier tipo serializable a JSON)
        message: Mensaje descriptivo de la operación
        metadata: Información adicional (timestamps, versiones, etc.)
        
    Returns:
        Diccionario con formato de respuesta exitosa
        
    Example:
        >>> success_response({"id": "123"}, "Usuario creado")
        {"success": True, "message": "Usuario creado", "data": {"id": "123"}}
    """
    response = {
        "success": True,
        "message": message,
        "data": data
    }
    
    if metadata:
        response["metadata"] = metadata
    
    return response


def error_response(
    error_code: str,
    message: str,
    details: Optional[Union[Dict[str, Any], List[Any]]] = None,
    http_status: Optional[int] = None
) -> Dict[str, Any]:
    """
    Genera una respuesta JSON de error estandarizada.
    
    Formato:
    {
        "success": false,
        "error_code": "ERROR_CODE",
        "message": "Mensaje descriptivo",
        "details": {...},  // opcional
        "status_code": 400  // opcional, para referencia
    }
    
    Códigos de error recomendados:
    - VALIDATION_ERROR: Error de validación de datos de entrada
    - NOT_FOUND: Recurso no encontrado
    - UNAUTHORIZED: No autenticado
    - FORBIDDEN: Sin permisos
    - CONFLICT: Conflicto con estado actual (duplicado, etc.)
    - BUSINESS_ERROR: Error de lógica de negocio
    - SAP_ERROR: Error de integración con SAP
    - MBA3_ERROR: Error de integración con MBA3
    - INTERNAL_ERROR: Error interno del servidor
    
    Args:
        error_code: Código único del error (UPPER_SNAKE_CASE)
        message: Mensaje descriptivo para el usuario/desarrollador
        details: Detalles adicionales del error (campos inválidos, etc.)
        http_status: Código HTTP para referencia (no afecta la respuesta)
        
    Returns:
        Diccionario con formato de respuesta de error
        
    Example:
        >>> error_response("VALIDATION_ERROR", "Campo requerido", {"campo": "email"})
        {"success": False, "error_code": "VALIDATION_ERROR", "message": "Campo requerido", "details": {"campo": "email"}}
    """
    response = {
        "success": False,
        "error_code": error_code,
        "message": message,
    }
    
    if details is not None:
        response["details"] = details
    
    if http_status is not None:
        response["status_code"] = http_status
    
    return response


def paginated_response(
    data: List[Any],
    total: int,
    page: int = 1,
    page_size: int = 50,
    message: str = "Listado obtenido exitosamente",
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Genera una respuesta JSON paginada estandarizada.
    
    Formato (camelCase para compatibilidad con frontend):
    {
        "success": true,
        "message": "...",
        "data": [...],
        "pagination": {
            "total": 100,
            "page": 1,
            "pageSize": 20,
            "totalPages": 5,
            "hasNext": true,
            "hasPrev": false
        },
        "metadata": {...}  // opcional
    }
    
    Referencia: docs/NAMING_CONVENTIONS.md
    
    Args:
        data: Lista de items de la página actual
        total: Total de registros (sin paginar)
        page: Número de página actual (1-indexed)
        page_size: Tamaño de página
        message: Mensaje descriptivo
        metadata: Información adicional
        
    Returns:
        Diccionario con formato de respuesta paginada
        
    Example:
        >>> paginated_response([{"id": 1}, {"id": 2}], total=100, page=1, page_size=2)
        {
            "success": True,
            "data": [{"id": 1}, {"id": 2}],
            "pagination": {"total": 100, "page": 1, "pageSize": 2, ...}
        }
    """
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    
    response = {
        "success": True,
        "message": message,
        "data": data,
        "pagination": {
            "total": total,
            "page": page,
            "pageSize": page_size,        # camelCase para frontend
            "totalPages": total_pages,     # camelCase para frontend
            "hasNext": page < total_pages, # camelCase para frontend
            "hasPrev": page > 1            # camelCase para frontend
        }
    }
    
    if metadata:
        response["metadata"] = metadata
    
    return response


def validation_error_response(
    errors: List[Dict[str, Any]],
    message: str = "Error de validación"
) -> Dict[str, Any]:
    """
    Genera una respuesta de error de validación con múltiples errores.
    
    Formato:
    {
        "success": false,
        "error_code": "VALIDATION_ERROR",
        "message": "Error de validación",
        "details": {
            "errors": [
                {"field": "email", "message": "Email inválido", "code": "invalid_format"},
                {"field": "cantidad", "message": "Debe ser >= 0 (acepta decimales)", "code": "min_value"}
            ],
            "error_count": 2
        }
    }
    
    Args:
        errors: Lista de errores con formato {"field": "...", "message": "...", "code": "..."}
        message: Mensaje general de error
        
    Returns:
        Diccionario con formato de respuesta de validación
        
    Example:
        >>> validation_error_response([{"field": "email", "message": "Email requerido"}])
    """
    return error_response(
        error_code="VALIDATION_ERROR",
        message=message,
        details={
            "errors": errors,
            "error_count": len(errors)
        },
        http_status=422
    )


def not_found_response(
    resource: str,
    identifier: Optional[str] = None,
    message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Genera una respuesta de recurso no encontrado.
    
    Args:
        resource: Nombre del recurso (ej: "Pedido", "Usuario")
        identifier: Identificador buscado (opcional)
        message: Mensaje personalizado (opcional)
        
    Returns:
        Diccionario con formato de respuesta 404
        
    Example:
        >>> not_found_response("Pedido", "P-12.48")
        {"success": False, "error_code": "NOT_FOUND", "message": "Pedido no encontrado: P-12.48"}
    """
    if message is None:
        message = f"{resource} no encontrado"
        if identifier:
            message = f"{resource} no encontrado: {identifier}"
    
    return error_response(
        error_code="NOT_FOUND",
        message=message,
        details={"resource": resource, "identifier": identifier} if identifier else None,
        http_status=404
    )


def business_error_response(
    error_code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Genera una respuesta de error de lógica de negocio.
    
    Usado para errores que no son de validación de formato pero sí de reglas de negocio.
    Ejemplos: "El pedido ya fue confirmado", "Stock insuficiente", "Fecha fuera de rango".
    
    Args:
        error_code: Código específico del error de negocio
        message: Mensaje descriptivo
        details: Datos adicionales relevantes
        
    Returns:
        Diccionario con formato de respuesta de error de negocio
        
    Example:
        >>> business_error_response("PEDIDO_YA_CONFIRMADO", "El pedido ya fue confirmado", {"pedido_id": "123"})
    """
    return error_response(
        error_code=error_code,
        message=message,
        details=details,
        http_status=400
    )


# =============================================================================
# Constantes de códigos de error comunes
# =============================================================================

class ErrorCodes:
    """
    Códigos de error estándar para uso en la aplicación.
    
    Uso:
        from src.utils.response_helpers import ErrorCodes, error_response
        
        return error_response(ErrorCodes.VALIDATION_ERROR, "Campo inválido")
    """
    
    # Errores de validación (422)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_FORMAT = "INVALID_FORMAT"
    REQUIRED_FIELD = "REQUIRED_FIELD"
    
    # Errores de autenticación/autorización (401, 403)
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    
    # Errores de recursos (404, 409)
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    DUPLICATE = "DUPLICATE"
    
    # Errores de negocio (400)
    BUSINESS_ERROR = "BUSINESS_ERROR"
    INVALID_STATE = "INVALID_STATE"
    OPERATION_NOT_ALLOWED = "OPERATION_NOT_ALLOWED"
    
    # Errores de integración (502, 503)
    SAP_ERROR = "SAP_ERROR"
    SAP_CONNECTION_ERROR = "SAP_CONNECTION_ERROR"
    MBA3_ERROR = "MBA3_ERROR"
    MBA3_CONNECTION_ERROR = "MBA3_CONNECTION_ERROR"
    
    # Errores internos (500)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
