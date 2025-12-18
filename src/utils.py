"""
Funciones de utilidad para procesamiento de consultas SQL.
"""

import json
import re
import logging
from typing import Dict, Any, Tuple
from pathlib import Path

from src.config import QUERY_STORAGE_FILE, MAX_QUERY_LENGTH

logger = logging.getLogger(__name__)


def get_source_from_headers(request) -> str:
    """
    Determina la fuente de la consulta desde los headers.
    
    Args:
        request: Request object de FastAPI
        
    Returns:
        String con la fuente (Postman, API, etc.)
    """
    # Primero verificar X-Source header
    x_source = request.headers.get("X-Source")
    if x_source:
        return x_source
    
    # Luego verificar User-Agent para detectar Postman
    user_agent = request.headers.get("User-Agent", "").lower()
    if "postman" in user_agent:
        return "Postman"
    
    # Por defecto
    return "API"


def normalize_query(query: str) -> str:
    """
    Normaliza una consulta SQL: recorta espacios y colapsa espacios múltiples.
    
    Args:
        query: Consulta SQL original
        
    Returns:
        Consulta normalizada
    """
    # Recortar espacios al inicio y final
    normalized = query.strip()
    
    # Colapsar múltiples espacios en uno solo (excepto dentro de comillas)
    # Estrategia simple: reemplazar múltiples espacios fuera de comillas
    # Nota: Esto es una aproximación, no maneja todos los casos edge de SQL
    normalized = re.sub(r'\s+', ' ', normalized)
    
    return normalized


def validate_query(query: str) -> Tuple[bool, str]:
    """
    Valida que la consulta sea segura (solo SELECT permitido).
    
    Args:
        query: Consulta SQL a validar
        
    Returns:
        Tupla (es_válida, mensaje)
    """
    if not query or not query.strip():
        return False, "La consulta no puede estar vacía"
    
    if len(query) > MAX_QUERY_LENGTH:
        return False, f"La consulta excede la longitud máxima de {MAX_QUERY_LENGTH} caracteres"
    
    # Normalizar para buscar palabras reservadas
    query_upper = query.upper().strip()
    
    # Verificar que no contenga múltiples statements separados por punto y coma
    # Contar puntos y coma que no estén dentro de comillas simples o dobles
    semicolon_count = 0
    in_single_quote = False
    in_double_quote = False
    
    for char in query:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == ';' and not in_single_quote and not in_double_quote:
            semicolon_count += 1
    
    if semicolon_count > 0:
        return False, "No se permiten múltiples statements separados por punto y coma. Solo una consulta a la vez."
    
    # Verificar que comience con SELECT (caso-insensible)
    if not query_upper.strip().startswith("SELECT"):
        return False, "Solo se permiten consultas SELECT"
    
    # Lista de palabras reservadas peligrosas a bloquear
    dangerous_keywords = [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
        "CREATE", "EXEC", "EXECUTE", "CALL", "GRANT", "REVOKE"
    ]
    
    # Buscar palabras reservadas peligrosas como palabras completas
    # Usar regex para encontrar palabras completas, no substrings
    for keyword in dangerous_keywords:
        # Buscar palabra completa con límites de palabra
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, query_upper):
            return False, f"No se permiten operaciones de modificación de datos. Palabra bloqueada: {keyword}"
    
    return True, "OK"


def parse_query(query: str) -> Tuple[Dict[str, Any], str]:
    """
    Parsea una consulta SQL SELECT y extrae sus componentes.
    
    Esta función usa heurísticas simples para parsear SQL SELECT:
    - Busca palabras reservadas (SELECT, FROM, WHERE, ORDER BY, LIMIT)
    - Extrae el contenido entre estas palabras
    - No es un parser SQL completo, pero es robusto para casos comunes
    
    Args:
        query: Consulta SQL SELECT
        
    Returns:
        Tupla (parsed_dict, note) donde parsed_dict contiene los campos parseados
        y note es "PARSE_OK" o motivo de error
    """
    parsed: Dict[str, Any] = {
        "select": None,
        "from": None,
        "where": None,
        "orderBy": None,
        "limit": None
    }
    
    try:
        # Normalizar consulta para análisis
        normalized = normalize_query(query)
        query_upper = normalized.upper()
        
        # Verificar que tenga FROM (obligatorio)
        if "FROM" not in query_upper:
            return parsed, "Falta FROM en la consulta"
        
        # Buscar posiciones de palabras reservadas usando regex con límites de palabra
        # Esto evita encontrar substrings dentro de identificadores o strings
        
        # SELECT
        select_match = re.search(r'\bSELECT\b', query_upper)
        if not select_match:
            return parsed, "No se encontró SELECT"
        
        select_start = select_match.end()
        
        # FROM
        from_match = re.search(r'\bFROM\b', query_upper, re.IGNORECASE)
        if not from_match:
            return parsed, "No se encontró FROM"
        
        from_start = from_match.end()
        
        # WHERE
        where_match = re.search(r'\bWHERE\b', query_upper, re.IGNORECASE)
        where_start = where_match.end() if where_match else None
        
        # ORDER BY
        order_by_match = re.search(r'\bORDER\s+BY\b', query_upper, re.IGNORECASE)
        order_by_start = order_by_match.end() if order_by_match else None
        
        # LIMIT
        limit_match = re.search(r'\bLIMIT\b', query_upper, re.IGNORECASE)
        limit_start = limit_match.end() if limit_match else None
        
        # Extraer SELECT (entre SELECT y FROM)
        if from_match:
            select_part = normalized[select_start:from_match.start()].strip()
            parsed["select"] = select_part if select_part else "*"
        else:
            parsed["select"] = "*"
        
        # Extraer FROM (entre FROM y WHERE/ORDER BY/LIMIT/END)
        from_end = min(
            where_match.start() if where_match and where_start else len(normalized),
            order_by_match.start() if order_by_match and order_by_start else len(normalized),
            limit_match.start() if limit_match and limit_start else len(normalized)
        )
        from_part = normalized[from_start:from_end].strip()
        parsed["from"] = from_part if from_part else None
        
        if not parsed["from"]:
            return parsed, "No se pudo extraer la tabla FROM"
        
        # Extraer WHERE (entre WHERE y ORDER BY/LIMIT/END)
        if where_start:
            where_end = min(
                order_by_match.start() if order_by_match and order_by_start else len(normalized),
                limit_match.start() if limit_match and limit_start else len(normalized)
            )
            where_part = normalized[where_start:where_end].strip()
            parsed["where"] = where_part if where_part else None
        
        # Extraer ORDER BY (entre ORDER BY y LIMIT/END)
        if order_by_start:
            order_by_end = limit_match.start() if limit_match and limit_start else len(normalized)
            order_by_part = normalized[order_by_start:order_by_end].strip()
            parsed["orderBy"] = order_by_part if order_by_part else None
        
        # Extraer LIMIT (entre LIMIT y END)
        if limit_start:
            limit_part = normalized[limit_start:].strip()
            # Solo tomar el número, ignorar resto
            limit_match_num = re.match(r'^(\d+)', limit_part)
            if limit_match_num:
                parsed["limit"] = limit_match_num.group(1)
            else:
                parsed["limit"] = limit_part.split()[0] if limit_part.split() else None
        
        return parsed, "PARSE_OK"
        
    except Exception as e:
        logger.error(f"Error al parsear consulta: {e}")
        return parsed, f"Error al parsear: {str(e)}"


def save_query_to_file(response_data: Dict[str, Any]) -> None:
    """
    Guarda la respuesta de la consulta en ultima_consulta.json.
    
    Args:
        response_data: Diccionario con los datos de respuesta a guardar
    """
    try:
        with open(QUERY_STORAGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(response_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Consulta guardada en {QUERY_STORAGE_FILE}")
    except Exception as e:
        logger.error(f"Error al guardar consulta en archivo: {e}")


def build_query_from_parts(parts: Dict[str, Any]) -> str:
    """
    Construye una consulta SQL SELECT a partir de partes individuales.
    
    Args:
        parts: Diccionario con select, from, where, orderBy, limit
        
    Returns:
        Consulta SQL construida
    """
    if not parts.get("from"):
        raise ValueError("El campo 'from' es obligatorio")
    
    select = parts.get("select") or "*"
    from_table = parts["from"]
    where = parts.get("where")
    order_by = parts.get("orderBy")
    limit = parts.get("limit")
    
    query = f"SELECT {select} FROM {from_table}"
    
    if where:
        query += f" WHERE {where}"
    if order_by:
        query += f" ORDER BY {order_by}"
    if limit:
        query += f" LIMIT {limit}"
    
    return query

