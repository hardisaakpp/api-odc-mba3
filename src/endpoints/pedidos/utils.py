"""
Utilidades comunes para endpoints de pedidos.
"""

import logging
from typing import Dict
from fastapi import HTTPException, UploadFile
from src.config import MAX_EXCEL_UPLOAD_SIZE_BYTES

logger = logging.getLogger(__name__)

# Constantes
MAX_FILE_SIZE = MAX_EXCEL_UPLOAD_SIZE_BYTES
ALLOWED_EXTENSIONS = {'.xlsx', '.xls'}
ALLOWED_MIME_TYPES = {
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
    'application/vnd.ms-excel'  # .xls
}


def validate_excel_file(file: UploadFile) -> None:
    """
    Valida que el archivo sea un Excel válido.
    
    Args:
        file: Archivo subido
        
    Raises:
        HTTPException: Si el archivo no es válido
    """
    # Validar extensión
    file_name = file.filename.lower() if file.filename else ""
    if not any(file_name.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Formato de archivo no permitido. Solo se permiten archivos Excel (.xlsx, .xls)"
        )
    
    # Validar tipo MIME (opcional, algunos navegadores no lo envían correctamente)
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        logger.warning(f"⚠️ Tipo MIME no reconocido: {file.content_type}, pero continuando con validación de extensión")


def get_user_id(user: Dict) -> str:
    """
    Normaliza y obtiene el ID del usuario del JWT.
    
    Usa el mismo identificador que se usa al guardar pedidos (creado_por).
    Esto asegura consistencia entre creación y consulta.
    
    IMPORTANTE: Prioriza información legible (email, username) sobre IDs técnicos (UUID)
    para que los campos de auditoría sean comprensibles para los usuarios.
    
    Args:
        user: Diccionario del JWT decodificado
        
    Returns:
        ID del usuario normalizado (email preferido, luego username, luego UUID)
        
    Raises:
        HTTPException: Si el usuario no tiene ID válido
    """
    # Priorizar información legible para auditoría
    user_id = (
        user.get('email') or      # PRIMERO: Email (más legible para usuarios AD)
        user.get('username') or   # Segundo: Username (para usuarios no-AD)
        user.get('id')            # ÚLTIMO RECURSO: UUID (solo si no hay email/username)
    )
    
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Usuario inválido: no se pudo obtener el ID del usuario"
        )
    
    return user_id
