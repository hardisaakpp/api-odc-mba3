"""
API HTTP para recibir, validar y procesar consultas SQL.

Servicio FastAPI que recibe consultas SQL (SELECT), las valida,
las parsea y las guarda en ultima_consulta.json.

Esta es la primera fase: solo recepción, validación y almacenamiento.
La ejecución contra MBA3 se implementará en una siguiente etapa.
"""

import json
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from models import QueryResponse, HealthResponse

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI
app = FastAPI(
    title="MBA3 Query API",
    description="API para recibir, validar y procesar consultas SQL (SELECT)",
    version="1.0.0"
)

# Configurar CORS para permitir pruebas desde Postman y otros clientes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración
MAX_QUERY_LENGTH = 5000  # Longitud máxima de consulta en caracteres

# Ruta para guardar la última consulta (en la raíz del proyecto)
# Si api_server.py está en src/, subir un nivel para llegar a la raíz
_current_file = Path(__file__).resolve()
if _current_file.parent.name == "src":
    QUERY_STORAGE_FILE = _current_file.parent.parent / "ultima_consulta.json"
else:
    QUERY_STORAGE_FILE = _current_file.parent / "ultima_consulta.json"


def get_source_from_headers(request: Request) -> str:
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


def validate_query(query: str) -> tuple[bool, str]:
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


def parse_query(query: str) -> tuple[Dict[str, Any], str]:
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
    parsed = {
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
        select_part = normalized[select_start:from_match.start()].strip()
        parsed["select"] = select_part if select_part else "*"
        
        # Extraer FROM (entre FROM y WHERE/ORDER BY/LIMIT/END)
        from_end = min(
            where_match.start() if where_start else len(normalized),
            order_by_match.start() if order_by_start else len(normalized),
            limit_match.start() if limit_start else len(normalized)
        )
        from_part = normalized[from_start:from_end].strip()
        parsed["from"] = from_part if from_part else None
        
        if not parsed["from"]:
            return parsed, "No se pudo extraer la tabla FROM"
        
        # Extraer WHERE (entre WHERE y ORDER BY/LIMIT/END)
        if where_start:
            where_end = min(
                order_by_match.start() if order_by_start else len(normalized),
                limit_match.start() if limit_start else len(normalized)
            )
            where_part = normalized[where_start:where_end].strip()
            parsed["where"] = where_part if where_part else None
        
        # Extraer ORDER BY (entre ORDER BY y LIMIT/END)
        if order_by_start:
            order_by_end = limit_match.start() if limit_start else len(normalized)
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


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Endpoint de health check.
    
    Returns:
        JSON con status "ok" y timestamp ISO8601
    """
    return {
        "status": "ok",
        "time": datetime.now().isoformat()
    }


@app.post("/test")
async def test_endpoint(
    request: Request,
    texto: Optional[str] = Form(None)  # Parámetro para form-data
):
    """
    Endpoint de prueba simple para verificar comunicación Postman → API.
    
    Recibe un texto desde Postman y lo devuelve en JSON sin procesar.
    Útil para probar que la comunicación funciona.
    
    Acepta:
    - JSON: {"texto": "tu mensaje aquí"}
    - Form-data: campo "texto"
    - URL-encoded: campo "texto"
    
    Returns:
        JSON con el texto recibido, timestamp y confirmación
    """
    try:
        # Obtener headers para debug
        content_type = request.headers.get("Content-Type", "").lower()
        all_headers = dict(request.headers)
        
        # Debug: mostrar qué headers estamos recibiendo
        print("=" * 70)
        print("🔍 DEBUG - Headers recibidos:")
        print(f"  Content-Type: {content_type}")
        print(f"  Todos los headers: {all_headers}")
        print("=" * 70)
        
        texto_recibido = None
        metodo_usado = None
        
        # Si Content-Type es JSON
        if "application/json" in content_type:
            try:
                body = await request.json()
                print(f"📦 Body JSON recibido: {body}")
                texto_recibido = body.get("texto") or body.get("text") or body.get("query")
                metodo_usado = "JSON"
            except Exception as e:
                logger.error(f"Error al leer JSON: {e}", exc_info=True)
                raise HTTPException(
                    status_code=400, 
                    detail=f"Error al leer JSON body: {str(e)}"
                )
        
        # Si viene en form-data o url-encoded
        elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            # Primero intentar usar el parámetro Form() de FastAPI
            if texto:
                texto_recibido = texto
                metodo_usado = "FORM-DATA (parámetro Form)"
                print(f"✅ Texto recibido via parámetro Form(): {texto}")
            else:
                # Si no viene por parámetro, intentar leer manualmente
                try:
                    form_data = await request.form()
                    
                    # Debug: mostrar qué campos recibimos
                    form_dict = dict(form_data)
                    print(f"📋 Form data recibido: {form_dict}")
                    print(f"📋 Tipo de form_data: {type(form_data)}")
                    print(f"📋 Claves disponibles: {list(form_data.keys())}")
                    
                    # Buscar el campo texto
                    texto_recibido = form_data.get("texto")
                    if not texto_recibido:
                        texto_recibido = form_data.get("text")
                    if not texto_recibido:
                        # Intentar obtener cualquier campo de texto
                        for key in form_data.keys():
                            valor = form_data.get(key)
                            if isinstance(valor, str) and valor.strip():
                                texto_recibido = valor
                                print(f"⚠️ Usando campo '{key}' como texto")
                                break
                    
                    metodo_usado = "FORM-DATA (manual)" if "multipart" in content_type else "URL-ENCODED (manual)"
                    
                except Exception as e:
                    logger.error(f"Error al leer form data: {e}", exc_info=True)
                    
                    # Intentar leer el body crudo para debug (solo si no se ha consumido)
                    try:
                        # Guardar body antes de leer
                        body_raw = await request.body()
                        print(f"🔍 Body crudo recibido (primeros 500 chars): {body_raw[:500]}")
                    except Exception as body_err:
                        print(f"⚠️ No se pudo leer body crudo: {body_err}")
                    
                    raise HTTPException(
                        status_code=400, 
                        detail={
                            "error": f"Error al leer form data: {str(e)}",
                            "content_type": content_type,
                            "sugerencia": "Asegúrate de que el campo Key en Postman se llame exactamente 'texto'"
                        }
                    )
        
        # Si no identificamos el tipo, intentar leer el body directamente
        else:
            print(f"⚠️ Content-Type no reconocido: {content_type}")
            try:
                # Intentar leer como JSON de todas formas
                try:
                    body = await request.json()
                    texto_recibido = body.get("texto") or body.get("text") or body.get("query")
                    metodo_usado = "JSON (auto-detectado)"
                except:
                    # Si no es JSON, intentar como texto plano
                    body_raw = await request.body()
                    if body_raw:
                        texto_recibido = body_raw.decode('utf-8')
                        metodo_usado = "TEXTO PLANO"
            except Exception as e:
                logger.warning(f"No se pudo leer body: {e}")
        
        # Validar que tenemos texto
        if not texto_recibido or (isinstance(texto_recibido, str) and not texto_recibido.strip()):
            # Si es form-data y no encontramos el campo, mostrar campos disponibles
            debug_info = {}
            if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
                try:
                    form_data = await request.form()
                    debug_info = {
                        "campos_recibidos": list(form_data.keys()) if form_data else [],
                        "content_type": content_type
                    }
                except:
                    pass
            
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Se requiere un campo 'texto' o 'text' en el body",
                    "ejemplo_json": {"texto": "Hola desde Postman"},
                    "ejemplo_form_data": "Key: 'texto', Value: 'Hola desde Postman'",
                    "debug": debug_info if debug_info else None
                }
            )
        
        # Preparar respuesta
        respuesta = {
            "status": "success",
            "mensaje": "¡Comunicación Postman → API funciona correctamente!",
            "texto_recibido": str(texto_recibido),
            "recibido_en": datetime.now().isoformat(),
            "tipo_contenido": content_type or "no especificado",
            "metodo_identificado": metodo_usado or "desconocido",
            "longitud": len(str(texto_recibido))
        }
        
        # Imprimir en consola (servidor)
        print("=" * 70)
        print(f"✅ Endpoint /test llamado exitosamente")
        print(f"📥 Texto recibido: {texto_recibido}")
        print(f"📦 Método: {metodo_usado}")
        print(f"⏰ Hora: {datetime.now().isoformat()}")
        print(f"📊 Longitud: {len(str(texto_recibido))} caracteres")
        print("=" * 70)
        
        logger.info(f"Endpoint /test - Texto recibido: {texto_recibido} (método: {metodo_usado})")
        
        return respuesta
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inesperado en /test: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Error interno: {str(e)}"
        )


@app.post("/query", response_model=QueryResponse)
async def receive_query(request: Request):
    """
    Endpoint para recibir consultas SQL.
    
    Acepta consultas en múltiples formatos:
    - JSON: {"query": "SELECT ..."} o {"select": "...", "from": "...", ...}
    - form-data o url-encoded: query="SELECT ..." o campos individuales
    
    Valida que sea solo SELECT y bloquea operaciones peligrosas.
    Parsea la consulta y guarda el resultado en ultima_consulta.json.
    
    Returns:
        JSON con la consulta original, parseada, timestamp y metadata
    """
    try:
        content_type = request.headers.get("Content-Type", "").lower()
        
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Obtener consulta según el tipo de contenido
        query_text = None
        parsed_parts = None
        
        # Si Content-Type es JSON, leer del body
        if "application/json" in content_type:
            try:
                body = await request.json()
                query_text = body.get("query")
                # También verificar si viene en partes
                if not query_text and (body.get("select") or body.get("from")):
                    parsed_parts = {
                        "select": body.get("select"),
                        "from": body.get("from"),
                        "where": body.get("where"),
                        "orderBy": body.get("orderBy"),
                        "limit": body.get("limit")
                    }
            except Exception as e:
                logger.error(f"Error al leer JSON body: {e}")
                raise HTTPException(status_code=400, detail="Error al leer JSON body")
        
        # Si viene en form-data o url-encoded
        elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            try:
                form_data = await request.form()
                query_text = form_data.get("query")
                # Si no hay query, buscar partes individuales
                if not query_text and form_data.get("from"):
                    parsed_parts = {
                        "select": form_data.get("select"),
                        "from": form_data.get("from"),
                        "where": form_data.get("where"),
                        "orderBy": form_data.get("orderBy"),
                        "limit": form_data.get("limit")
                    }
            except Exception as e:
                logger.error(f"Error al leer form data: {e}")
                raise HTTPException(status_code=400, detail="Error al leer form data")
        
        # Si tenemos partes pero no query_text, construir la query
        if parsed_parts and parsed_parts.get("from"):
            try:
                query_text = build_query_from_parts(parsed_parts)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Error al construir query desde partes: {str(e)}")
        
        # Validar que tenemos una consulta
        if not query_text or not query_text.strip():
            raise HTTPException(
                status_code=400,
                detail="Se requiere una consulta SQL. Proporciona 'query' o los campos individuales (select, from, etc.)"
            )
        
        # Validar consulta (solo SELECT, sin operaciones peligrosas)
        is_valid, validation_message = validate_query(query_text)
        if not is_valid:
            raise HTTPException(status_code=400, detail=validation_message)
        
        # Parsear consulta
        parsed_dict, parse_note = parse_query(query_text)
        
        # Construir respuesta
        received_at = datetime.now().isoformat()
        
        response_data = {
            "original": query_text,
            "parsed": parsed_dict,
            "received_at": received_at,
            "source": source,
            "note": parse_note
        }
        
        # Log en consola
        logger.info("=" * 70)
        logger.info(f"Consulta recibida a las {received_at}")
        logger.info(f"Fuente: {source}")
        logger.info(f"Consulta original: {query_text}")
        logger.info(f"Parseo: {parse_note}")
        logger.info(f"Campos parseados: {json.dumps(parsed_dict, ensure_ascii=False, indent=2)}")
        logger.info("=" * 70)
        
        # Guardar en archivo
        save_query_to_file(response_data)
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inesperado en /query: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")


@app.post("/query/forward")
async def forward_query():
    """
    Endpoint placeholder para reenvío de consultas a MBA3.
    
    Esta funcionalidad se implementará en una siguiente etapa.
    Por ahora devuelve 501 Not Implemented.
    
    Returns:
        JSON con mensaje indicando que no está implementado
    """
    return JSONResponse(
        status_code=501,
        content={
            "status": "not_implemented",
            "message": "La ejecución remota de consultas contra MBA3 se implementará en una siguiente etapa",
            "note": "Este endpoint estará disponible en futuras versiones para ejecutar consultas usando MBA3APIClient"
        }
    )


if __name__ == "__main__":
    # Ejecutar servidor con uvicorn
    # Nota: host="0.0.0.0" significa que escucha en todas las interfaces de red
    # Para acceder desde el navegador, usa: http://localhost:8000 o http://127.0.0.1:8000
    print("=" * 70)
    print("Iniciando servidor FastAPI...")
    print("=" * 70)
    print("URLs disponibles:")
    print("  - http://localhost:8000")
    print("  - http://127.0.0.1:8000")
    print("  - http://0.0.0.0:8000 (solo para escuchar, no para acceder)")
    print("=" * 70)
    print("\nDocumentación interactiva disponible en:")
    print("  - http://localhost:8000/docs (Swagger UI)")
    print("  - http://localhost:8000/redoc (ReDoc)")
    print("\nEndpoint de health check:")
    print("  - http://localhost:8000/health")
    print("\nPresiona Ctrl+C para detener el servidor\n")
    print("=" * 70 + "\n")
    
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",  # Escucha en todas las interfaces
        port=8000,
        reload=True,
        log_level="info"
    )

