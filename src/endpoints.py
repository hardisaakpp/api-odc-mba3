"""
Endpoints FastAPI para la API de consultas MBA3.
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import Request, HTTPException, Form
from fastapi.responses import JSONResponse

from models import QueryResponse, HealthResponse
from utils import (
    get_source_from_headers,
    validate_query,
    parse_query,
    save_query_to_file,
    build_query_from_parts
)
from query_handler import get_mba3_client

logger = logging.getLogger(__name__)


def create_endpoints(app):
    """
    Registra todos los endpoints en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
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
    
    
    @app.post("/consulta")
    async def ejecutar_consulta(request: Request):
        """
        Endpoint para ejecutar consultas SQL dinámicas contra MBA3.
        
        Recibe una consulta SQL desde Postman, la valida, la ejecuta en MBA3
        y retorna el resultado JSON que devuelve MBA3.
        
        Acepta:
        - JSON: {"query": "SELECT * FROM tabla WHERE condicion"}
        - Form-data: campo "query" con la consulta SQL
        - URL-encoded: campo "query" con la consulta SQL
        
        Valida que sea solo SELECT y bloquea operaciones peligrosas.
        Usa el cliente MBA3APIClient para ejecutar la consulta.
        
        Returns:
            JSON con el resultado de MBA3 o error si falla
        """
        try:
            content_type = request.headers.get("Content-Type", "").lower()
            
            # Determinar fuente
            source = get_source_from_headers(request)
            
            # Obtener consulta según el tipo de contenido
            query_text = None
            metodo_usado = None
            
            # Si Content-Type es JSON, leer del body
            if "application/json" in content_type:
                try:
                    body = await request.json()
                    query_text = body.get("query")
                    metodo_usado = "JSON"
                    logger.debug(f"Consulta recibida via JSON: {query_text[:100] if query_text else None}...")
                except Exception as e:
                    logger.error(f"Error al leer JSON body: {e}")
                    raise HTTPException(status_code=400, detail="Error al leer JSON body")
            
            # Si viene en form-data o url-encoded
            elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
                try:
                    form_data = await request.form()
                    
                    # Debug: mostrar qué campos recibimos
                    form_dict = dict(form_data)
                    logger.debug(f"Form data recibido - campos: {list(form_data.keys())}")
                    logger.debug(f"Form data completo: {form_dict}")
                    
                    # Buscar el campo "query" (case-insensitive)
                    query_text = form_data.get("query")
                    if not query_text:
                        # Intentar otros nombres posibles (case variations)
                        for key in form_data.keys():
                            if key.lower() == "query":
                                query_text = form_data.get(key)
                                logger.info(f"⚠️ Campo 'query' encontrado con diferente capitalización: '{key}'")
                                break
                        # Si aún no, intentar mayúsculas
                        if not query_text:
                            query_text = form_data.get("Query") or form_data.get("QUERY")
                    
                    metodo_usado = "FORM-DATA" if "multipart" in content_type else "URL-ENCODED"
                    
                    # Si aún no encontramos query, mostrar campos disponibles para debug
                    if not query_text:
                        campos_recibidos = list(form_data.keys())
                        logger.warning(f"No se encontró campo 'query' en form-data. Campos recibidos: {campos_recibidos}")
                        
                        # Intentar obtener cualquier campo de texto que parezca SQL como último recurso
                        for key in form_data.keys():
                            valor = form_data.get(key)
                            if isinstance(valor, str) and valor.strip():
                                valor_upper = valor.upper().strip()
                                if valor_upper.startswith("SELECT"):
                                    query_text = valor
                                    logger.info(f"⚠️ Usando campo '{key}' como query (auto-detectado por contenido SQL)")
                                    break
                        
                        # Si aún no encontramos nada, dar información detallada del error
                        if not query_text:
                            raise HTTPException(
                                status_code=400,
                                detail={
                                    "error": "No se encontró el campo 'query' en el form-data",
                                    "campos_recibidos": campos_recibidos,
                                    "instrucciones": {
                                        "paso_1": "En Postman, selecciona 'form-data' en la pestaña Body",
                                        "paso_2": "Agrega un nuevo campo con Key = 'query' (sin comillas, minúsculas)",
                                        "paso_3": f"En Value, escribe tu consulta SQL, ejemplo: SELECT * FROM tabla"
                                    },
                                    "ejemplo_postman": {
                                        "key": "query",
                                        "value": "SELECT * FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'"
                                    }
                                }
                            )
                    
                except HTTPException:
                    # Re-lanzar excepciones HTTP (como la que acabamos de crear)
                    raise
                except Exception as e:
                    logger.error(f"Error al leer form data: {e}", exc_info=True)
                    
                    # Intentar obtener información adicional del error
                    try:
                        body_raw = await request.body()
                        logger.debug(f"Body crudo recibido (primeros 500 chars): {body_raw[:500] if body_raw else None}")
                    except:
                        pass
                    
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": f"Error al leer form data: {str(e)}",
                            "content_type": content_type,
                            "sugerencia": "Asegúrate de que el campo Key en Postman se llame exactamente 'query' (minúsculas)"
                        }
                    )
            
            # Si no identificamos el tipo, intentar leer el body directamente
            else:
                logger.warning(f"Content-Type no reconocido: {content_type}")
                try:
                    # Intentar leer como JSON de todas formas
                    try:
                        body = await request.json()
                        query_text = body.get("query")
                        metodo_usado = "JSON (auto-detectado)"
                    except:
                        # Si no es JSON, intentar como texto plano
                        body_raw = await request.body()
                        if body_raw:
                            query_text = body_raw.decode('utf-8')
                            metodo_usado = "TEXTO PLANO"
                except Exception as e:
                    logger.warning(f"No se pudo leer body: {e}")
            
            # Validar que tenemos una consulta
            if not query_text or (isinstance(query_text, str) and not query_text.strip()):
                # Preparar información de debug más detallada
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
                        "error": "Se requiere una consulta SQL en el campo 'query'",
                        "ejemplo_json": {"query": "SELECT * FROM tabla"},
                        "ejemplo_form_data": "Key: 'query', Value: 'SELECT * FROM tabla'",
                        "ejemplo_url_encoded": "query=SELECT * FROM tabla",
                        "debug": debug_info if debug_info else None
                    }
                )
            
            # Validar consulta (solo SELECT, sin operaciones peligrosas)
            is_valid, validation_message = validate_query(query_text)
            if not is_valid:
                raise HTTPException(status_code=400, detail=validation_message)
            
            # Log de la consulta recibida
            logger.info("=" * 70)
            logger.info(f"Consulta dinámica recibida a las {datetime.now().isoformat()}")
            logger.info(f"Fuente: {source}")
            logger.info(f"Método: {metodo_usado or 'desconocido'}")
            logger.info(f"Consulta: {query_text}")
            logger.info("Ejecutando consulta contra MBA3...")
            logger.info("=" * 70)
            
            # Obtener cliente MBA3
            client = get_mba3_client()
            
            # Ejecutar consulta contra MBA3
            try:
                result = client.execute_query(query_text, require_jwt=True)
                
                if result is None:
                    logger.error("La consulta no retornó resultados (resultado None)")
                    raise HTTPException(
                        status_code=500,
                        detail="La consulta no retornó resultados. Verifica la consulta SQL y la conexión con MBA3."
                    )
                
                # Log de éxito
                logger.info("=" * 70)
                logger.info("✅ Consulta ejecutada exitosamente contra MBA3")
                logger.info(f"Resultado tipo: {type(result)}")
                if isinstance(result, list):
                    logger.info(f"Total de registros: {len(result)}")
                elif isinstance(result, dict):
                    logger.info(f"Campos en resultado: {list(result.keys())[:5]}...")
                logger.info("=" * 70)
                
                # Guardar en SQL Server (si está habilitado)
                save_status = None
                try:
                    from database import save_mba3_data_to_sql_server
                    logger.info("💾 Guardando datos en SQL Server...")
                    save_status = save_mba3_data_to_sql_server(
                        result,
                        upsert=False,  # Cambiar a True si quieres actualizar facturas existentes
                        continue_on_error=True  # Continuar aunque falle una factura
                    )
                    
                    if save_status.get("status") == "success":
                        logger.info(f"✅ Datos guardados exitosamente en SQL Server")
                        logger.info(f"   Facturas guardadas: {save_status.get('facturas_guardadas', 0)}")
                        logger.info(f"   Total detalles: {save_status.get('total_detalles', 0)}")
                    elif save_status.get("status") == "partial":
                        logger.warning(f"⚠️ Datos guardados parcialmente en SQL Server")
                        logger.warning(f"   Guardadas: {save_status.get('facturas_guardadas', 0)}")
                        logger.warning(f"   Errores: {save_status.get('facturas_error', 0)}")
                        if save_status.get("errors"):
                            for error in save_status["errors"][:3]:  # Mostrar primeros 3 errores
                                logger.warning(f"   - {error}")
                    elif save_status.get("status") == "disabled":
                        logger.info("⏭️ Guardado en SQL Server deshabilitado")
                    else:
                        logger.error(f"❌ Error al guardar en SQL Server: {save_status.get('errors', [])}")
                        
                except ImportError:
                    logger.warning("⚠️ Módulo database no disponible. Saltando guardado en SQL Server.")
                except Exception as e:
                    logger.error(f"❌ Error inesperado al guardar en SQL Server: {e}", exc_info=True)
                    # No fallar la petición si falla el guardado, solo loguear el error
                
                # Preparar headers de respuesta
                headers = {
                    "X-Query": query_text[:100],  # Primeros 100 caracteres de la query
                    "X-Source": source
                }
                
                # Agregar información de guardado si existe
                if save_status:
                    headers["X-Saved-To-DB"] = save_status.get("status", "unknown")
                    headers["X-DB-Facturas"] = str(save_status.get("facturas_guardadas", 0))
                
                # Retornar resultado JSON de MBA3 directamente
                return JSONResponse(
                    status_code=200,
                    content=result,
                    headers=headers
                )
                
            except HTTPException:
                # Re-lanzar excepciones HTTP
                raise
            except Exception as e:
                logger.error(f"Error al ejecutar consulta contra MBA3: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Error al ejecutar consulta contra MBA3: {str(e)}"
                )
            
        except HTTPException:
            # Re-lanzar excepciones HTTP (validaciones, etc.)
            raise
        except Exception as e:
            logger.error(f"Error inesperado en /consulta: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno del servidor: {str(e)}"
            )

