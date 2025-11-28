"""
Helper para parsear requests HTTP de diferentes formatos.

Centraliza la lógica de lectura de JSON, form-data y url-encoded.
"""

import logging
from typing import Optional, Dict, Any, Tuple
from fastapi import Request, HTTPException, UploadFile

logger = logging.getLogger(__name__)


class RequestParser:
    """Helper para parsear requests HTTP."""
    
    @staticmethod
    async def parse_query_from_request(request: Request) -> Tuple[str, str]:
        """
        Extrae la consulta SQL de un request HTTP.
        
        Soporta múltiples formatos:
        - JSON: {"query": "SELECT ..."} o {"select": "...", "from": "...", ...}
        - Form-data: campo "query" o campos individuales
        - URL-encoded: campo "query" o campos individuales
        
        Args:
            request: Request object de FastAPI
            
        Returns:
            Tupla (query_text, metodo_usado)
            
        Raises:
            HTTPException: Si no se puede extraer la consulta
        """
        content_type = request.headers.get("Content-Type", "").lower()
        query_text = None
        metodo_usado = None
        parsed_parts = None
        
        # JSON
        if "application/json" in content_type:
            try:
                body = await request.json()
                query_text = body.get("query")
                
                # Si no hay query, buscar partes individuales
                if not query_text and (body.get("select") or body.get("from")):
                    parsed_parts = {
                        "select": body.get("select"),
                        "from": body.get("from"),
                        "where": body.get("where"),
                        "orderBy": body.get("orderBy"),
                        "limit": body.get("limit")
                    }
                
                metodo_usado = "JSON"
                
            except Exception as e:
                logger.error(f"Error al leer JSON body: {e}")
                raise HTTPException(status_code=400, detail="Error al leer JSON body")
        
        # Form-data o URL-encoded
        elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            try:
                form_data = await request.form()
                query_value = form_data.get("query")
                
                # Convertir UploadFile a str si es necesario
                if isinstance(query_value, UploadFile):
                    query_text = await query_value.read()
                    query_text = query_text.decode('utf-8')
                elif isinstance(query_value, str):
                    query_text = query_value
                else:
                    query_text = None
                
                # Si no hay query, buscar partes individuales
                if not query_text and form_data.get("from"):
                    def get_form_value(key: str) -> Optional[str]:
                        value = form_data.get(key)
                        if isinstance(value, UploadFile):
                            return None  # No soportamos UploadFile para partes individuales
                        return str(value) if value is not None else None
                    
                    parsed_parts = {
                        "select": get_form_value("select"),
                        "from": get_form_value("from"),
                        "where": get_form_value("where"),
                        "orderBy": get_form_value("orderBy"),
                        "limit": get_form_value("limit")
                    }
                
                metodo_usado = "FORM-DATA" if "multipart" in content_type else "URL-ENCODED"
                
            except Exception as e:
                logger.error(f"Error al leer form data: {e}")
                raise HTTPException(status_code=400, detail="Error al leer form data")
        
        # Auto-detección
        else:
            try:
                body = await request.json()
                query_text = body.get("query")
                metodo_usado = "JSON (auto-detectado)"
            except:
                try:
                    body_raw = await request.body()
                    if body_raw:
                        query_text = body_raw.decode('utf-8')
                        metodo_usado = "TEXTO PLANO"
                except Exception as e:
                    logger.warning(f"No se pudo leer body: {e}")
        
        # Si tenemos partes pero no query_text, construir la query
        if parsed_parts and parsed_parts.get("from"):
            try:
                from utils import build_query_from_parts
                query_text = build_query_from_parts(parsed_parts)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error al construir query desde partes: {str(e)}"
                )
        
        # Validar que tenemos una consulta
        if not query_text or not isinstance(query_text, str) or not query_text.strip():
            # Preparar información de debug
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
                    "error": "Se requiere una consulta SQL. Proporciona 'query' o los campos individuales (select, from, etc.)",
                    "ejemplo_json": {"query": "SELECT * FROM tabla"},
                    "ejemplo_form_data": "Key: 'query', Value: 'SELECT * FROM tabla'",
                    "debug": debug_info if debug_info else None
                }
            )
        
        # Asegurar que metodo_usado no sea None
        if metodo_usado is None:
            metodo_usado = "DESCONOCIDO"
        
        return str(query_text), str(metodo_usado)
    
    @staticmethod
    async def parse_text_from_request(request: Request) -> Tuple[str, str]:
        """
        Extrae texto de un request HTTP (para endpoints de prueba).
        
        Args:
            request: Request object de FastAPI
            
        Returns:
            Tupla (texto, metodo_usado)
            
        Raises:
            HTTPException: Si no se puede extraer el texto
        """
        content_type = request.headers.get("Content-Type", "").lower()
        texto_recibido = None
        metodo_usado = None
        
        # JSON
        if "application/json" in content_type:
            try:
                body = await request.json()
                texto_recibido = body.get("texto") or body.get("text") or body.get("query")
                metodo_usado = "JSON"
            except Exception as e:
                logger.error(f"Error al leer JSON: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Error al leer JSON body: {str(e)}"
                )
        
        # Form-data o URL-encoded
        elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            try:
                form_data = await request.form()
                texto_value = form_data.get("texto") or form_data.get("text")
                
                # Convertir UploadFile a str si es necesario
                if isinstance(texto_value, UploadFile):
                    texto_bytes = await texto_value.read()
                    texto_recibido = texto_bytes.decode('utf-8')
                elif isinstance(texto_value, str):
                    texto_recibido = texto_value
                else:
                    texto_recibido = None
                
                if not texto_recibido:
                    # Buscar cualquier campo de texto
                    for key in form_data.keys():
                        valor = form_data.get(key)
                        if isinstance(valor, str) and valor.strip():
                            texto_recibido = valor
                            break
                        elif isinstance(valor, UploadFile):
                            # Si es UploadFile, leerlo
                            texto_bytes = await valor.read()
                            texto_str = texto_bytes.decode('utf-8')
                            if texto_str.strip():
                                texto_recibido = texto_str
                                break
                
                metodo_usado = "FORM-DATA" if "multipart" in content_type else "URL-ENCODED"
                
            except Exception as e:
                logger.error(f"Error al leer form data: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Error al leer form data: {str(e)}"
                )
        
        # Auto-detección
        else:
            try:
                body = await request.json()
                texto_recibido = body.get("texto") or body.get("text") or body.get("query")
                metodo_usado = "JSON (auto-detectado)"
            except:
                try:
                    body_raw = await request.body()
                    if body_raw:
                        texto_recibido = body_raw.decode('utf-8')
                        metodo_usado = "TEXTO PLANO"
                except Exception as e:
                    logger.warning(f"No se pudo leer body: {e}")
        
        # Validar que tenemos texto
        if not texto_recibido or not isinstance(texto_recibido, str) or not texto_recibido.strip():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Se requiere un campo 'texto' o 'text' en el body",
                    "ejemplo_json": {"texto": "Hola desde Postman"},
                    "ejemplo_form_data": "Key: 'texto', Value: 'Hola desde Postman'"
                }
            )
        
        # Asegurar que metodo_usado no sea None
        if metodo_usado is None:
            metodo_usado = "DESCONOCIDO"
        
        return str(texto_recibido), str(metodo_usado)

