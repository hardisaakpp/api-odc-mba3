"""
Endpoints FastAPI para la API de consultas MBA3.

Esta versión usa servicios y helpers para separar la lógica de negocio.
"""

import logging
from datetime import datetime

from fastapi import Request
from fastapi.responses import JSONResponse

from models import HealthResponse, QueryResponse
from services.query_service import QueryService
from services.mba3_service import MBA3Service
from helpers.request_parser import RequestParser
from utils import get_source_from_headers

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
    async def test_endpoint(request: Request):
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
        # Parsear texto del request
        texto_recibido, metodo_usado = await RequestParser.parse_text_from_request(request)
        
        # Preparar respuesta
        respuesta = {
            "status": "success",
            "mensaje": "¡Comunicación Postman → API funciona correctamente!",
            "texto_recibido": str(texto_recibido),
            "recibido_en": datetime.now().isoformat(),
            "tipo_contenido": request.headers.get("Content-Type", "no especificado"),
            "metodo_identificado": metodo_usado,
            "longitud": len(str(texto_recibido))
        }
        
        # Log
        logger.info("=" * 70)
        logger.info(f"✅ Endpoint /test llamado exitosamente")
        logger.info(f"📥 Texto recibido: {texto_recibido}")
        logger.info(f"📦 Método: {metodo_usado}")
        logger.info(f"⏰ Hora: {datetime.now().isoformat()}")
        logger.info("=" * 70)
        
        return respuesta
    
    
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
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Parsear consulta del request
        query_text, metodo_usado = await RequestParser.parse_query_from_request(request)
        
        # Procesar consulta usando el servicio
        response_data = QueryService.process_query(
            query_text=query_text,
            source=source
        )
        
        return response_data
    
    
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
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Parsear consulta del request
        query_text, metodo_usado = await RequestParser.parse_query_from_request(request)
        
        # Log de la consulta recibida
        logger.info("=" * 70)
        logger.info(f"Consulta dinámica recibida a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"Método: {metodo_usado}")
        logger.info(f"Consulta: {query_text}")
        logger.info("Ejecutando consulta contra MBA3...")
        logger.info("=" * 70)
        
        # Ejecutar consulta usando el servicio
        result = MBA3Service.execute_query(query_text)
        
        # Guardar en SQL Server (si está habilitado)
        save_status = MBA3Service.save_to_database(result, upsert=False)
        
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
