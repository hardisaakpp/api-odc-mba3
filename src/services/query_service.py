"""
Servicio para procesamiento de consultas SQL.

Maneja la validación, parsing y almacenamiento de consultas.
"""

import logging
from typing import Optional
from datetime import datetime

from utils import (
    validate_query,
    parse_query,
    save_query_to_file,
    get_source_from_headers
)
from models import QueryResponse
from exceptions import QueryValidationError

logger = logging.getLogger(__name__)


class QueryService:
    """Servicio para procesar consultas SQL."""
    
    @staticmethod
    def process_query(
        query_text: str,
        source: str,
        received_at: Optional[str] = None
    ) -> QueryResponse:
        """
        Procesa una consulta SQL: valida, parsea y guarda.
        
        Args:
            query_text: Consulta SQL a procesar
            source: Fuente de la consulta (Postman, API, etc.)
            received_at: Timestamp ISO8601 (opcional, se genera si no se proporciona)
            
        Returns:
            QueryResponse con la consulta procesada
            
        Raises:
            ValueError: Si la consulta no es válida
        """
        if not received_at:
            received_at = datetime.now().isoformat()
        
        # Validar consulta
        is_valid, validation_message = validate_query(query_text)
        if not is_valid:
            raise QueryValidationError(validation_message)
        
        # Parsear consulta
        parsed_dict, parse_note = parse_query(query_text)
        
        # Construir respuesta
        response_data = {
            "original": query_text,
            "parsed": parsed_dict,
            "received_at": received_at,
            "source": source,
            "note": parse_note
        }
        
        # Log resumido
        logger.info(f"📝 Consulta recibida desde {source}: {parse_note}")
        
        # Guardar en archivo
        save_query_to_file(response_data)
        
        return QueryResponse(**response_data)

