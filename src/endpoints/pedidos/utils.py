"""
Utilidades comunes para endpoints de pedidos.
"""

import logging
from typing import Dict
from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)

# Constantes
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
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
    
    Args:
        user: Diccionario del JWT decodificado
        
    Returns:
        ID del usuario normalizado
        
    Raises:
        HTTPException: Si el usuario no tiene ID válido
    """
    user_id = user.get('id') or user.get('username')
    
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Usuario inválido: no se pudo obtener el ID del usuario"
        )
    
    return user_id
