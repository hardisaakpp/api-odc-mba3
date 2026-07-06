"""
Funciones de utilidad para procesamiento de consultas SQL.
"""

import json
import re
import logging
from typing import Dict, Any, Tuple, Optional

from src.config import QUERY_STORAGE_FILE, MAX_QUERY_LENGTH

logger = logging.getLogger(__name__)


def normalizar_codigo_producto(codigo: Optional[str]) -> str:
    """
    Normaliza código de producto eliminando separadores comunes.
    
    Función centralizada para normalización de códigos de producto.
    Debe usarse en TODAS las partes del sistema para asegurar consistencia.
    
    Separadores eliminados: . - / _ espacio
    Conversión: a mayúsculas
    
    Ejemplos:
        R225.1012.BCO -> R2251012BCO
        R225-1012-BCO -> R2251012BCO
        R225/1012/BCO -> R2251012BCO
        R225_1012_BCO -> R2251012BCO
        R225 1012 BCO -> R2251012BCO
    
    Args:
        codigo: Código a normalizar (puede ser None)
        
    Returns:
        Código normalizado (string vacío si codigo es None o vacío)
    
    Note:
        Existe versión SQL equivalente: dbo.fn_normalizar_codigo
        Ver: scripts/migrations/create_fn_normalizar_codigo.sql
        Mantener ambas sincronizadas si se modifica la lógica.
    """
    if not codigo:
        return ""
    
    # Eliminar todos los separadores comunes y convertir a mayúsculas
    # IMPORTANTE: Incluir todos los separadores posibles (., -, /, _, espacio)
    # NOTA: El guión (-) debe estar al final de la clase para que sea literal, no rango
    codigo_normalizado = re.sub(r'[.\s/_-]', '', codigo.strip().upper())
    
    return codigo_normalizado


def validar_longitud_minima_codigo(codigo_normalizado: str, longitud_minima: int = 3) -> bool:
    """
    Valida que un código normalizado tenga longitud mínima.
    
    Útil para evitar búsquedas demasiado genéricas que pueden devolver
    demasiados resultados.
    
    Args:
        codigo_normalizado: Código ya normalizado
        longitud_minima: Longitud mínima requerida (default: 3)
        
    Returns:
        True si cumple la longitud mínima, False en caso contrario
    """
    return len(codigo_normalizado) >= longitud_minima


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


def _contar_semicolons_fuera_de_comillas(query: str) -> int:
    count = 0
    in_single = False
    in_double = False
    for char in query:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == ';' and not in_single and not in_double:
            count += 1
    return count


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
    if _contar_semicolons_fuera_de_comillas(query) > 0:
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
    for keyword in dangerous_keywords:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, query_upper):
            return False, f"No se permiten operaciones de modificación de datos. Palabra bloqueada: {keyword}"

    return True, "OK"


def _buscar_clausulas_sql(query_upper: str):
    return (
        re.search(r'\bSELECT\b', query_upper),
        re.search(r'\bFROM\b', query_upper, re.IGNORECASE),
        re.search(r'\bWHERE\b', query_upper, re.IGNORECASE),
        re.search(r'\bORDER\s+BY\b', query_upper, re.IGNORECASE),
        re.search(r'\bLIMIT\b', query_upper, re.IGNORECASE),
    )


def _extraer_posiciones_clausulas(where_m, order_m, limit_m) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    return (
        where_m.end() if where_m else None,
        order_m.end() if order_m else None,
        limit_m.end() if limit_m else None,
    )


def _extraer_select(normalized: str, select_start: int, from_start: int) -> str:
    select_part = normalized[select_start:from_start].strip()
    return select_part if select_part else "*"


def _extraer_from(normalized: str, from_start: int, where_m, order_m, limit_m) -> Optional[str]:
    from_end = min(
        where_m.start() if where_m else len(normalized),
        order_m.start() if order_m else len(normalized),
        limit_m.start() if limit_m else len(normalized),
    )
    from_part = normalized[from_start:from_end].strip()
    return from_part if from_part else None


def _extraer_where(normalized: str, where_start: int, order_m, limit_m) -> Optional[str]:
    where_end = min(
        order_m.start() if order_m else len(normalized),
        limit_m.start() if limit_m else len(normalized),
    )
    where_part = normalized[where_start:where_end].strip()
    return where_part if where_part else None


def _extraer_order_by(normalized: str, order_by_start: int, limit_m) -> Optional[str]:
    order_by_end = limit_m.start() if limit_m else len(normalized)
    order_by_part = normalized[order_by_start:order_by_end].strip()
    return order_by_part if order_by_part else None


def _extraer_limit(normalized: str, limit_start: int) -> Optional[str]:
    limit_part = normalized[limit_start:].strip()
    num_match = re.match(r'^(\d+)', limit_part)
    if num_match:
        return num_match.group(1)
    parts = limit_part.split()
    return parts[0] if parts else None


def _construir_partes_sql(normalized, select_m, from_m, where_m, order_m, limit_m) -> Tuple[Dict[str, Any], str]:
    parsed: Dict[str, Any] = {"select": None, "from": None, "where": None, "orderBy": None, "limit": None}
    where_start, order_by_start, limit_start = _extraer_posiciones_clausulas(where_m, order_m, limit_m)
    parsed["select"] = _extraer_select(normalized, select_m.end(), from_m.start())
    parsed["from"] = _extraer_from(normalized, from_m.end(), where_m, order_m, limit_m)
    if not parsed["from"]:
        return parsed, "No se pudo extraer la tabla FROM"
    if where_start:
        parsed["where"] = _extraer_where(normalized, where_start, order_m, limit_m)
    if order_by_start:
        parsed["orderBy"] = _extraer_order_by(normalized, order_by_start, limit_m)
    if limit_start:
        parsed["limit"] = _extraer_limit(normalized, limit_start)
    return parsed, "PARSE_OK"


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
    parsed: Dict[str, Any] = {"select": None, "from": None, "where": None, "orderBy": None, "limit": None}
    try:
        normalized = normalize_query(query)
        query_upper = normalized.upper()
        if "FROM" not in query_upper:
            return parsed, "Falta FROM en la consulta"
        select_m, from_m, where_m, order_m, limit_m = _buscar_clausulas_sql(query_upper)
        if not select_m:
            return parsed, "No se encontró SELECT"
        if not from_m:
            return parsed, "No se encontró FROM"
        return _construir_partes_sql(normalized, select_m, from_m, where_m, order_m, limit_m)
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

