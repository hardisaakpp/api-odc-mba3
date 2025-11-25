"""
Endpoints FastAPI para la API de consultas MBA3.

Esta versión usa servicios y helpers para separar la lógica de negocio.
"""

import logging
from datetime import datetime

from fastapi import Request, Query as FastAPIQuery
from fastapi.responses import JSONResponse
from typing import Optional

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
    
    
    @app.get("/facturas")
    async def obtener_facturas(
        request: Request,
        anulada: Optional[bool] = FastAPIQuery(False, description="Filtrar por facturas anuladas (false=no anuladas, true=anuladas)"),
        confirmado: Optional[bool] = FastAPIQuery(True, description="Filtrar por facturas confirmadas (true=confirmadas, false=no confirmadas)"),
        remision_facturada: Optional[bool] = FastAPIQuery(False, description="Filtrar por remisión facturada (false=sin remisión, true=con remisión)"),
        include_obj_datos: bool = FastAPIQuery(True, description="Incluir solo facturas con ObjDatosFactura no nulo"),
        save_to_db: bool = FastAPIQuery(True, description="Guardar resultados en SQL Server")
    ):
        """
        Endpoint para obtener facturas desde MBA3 sin necesidad de enviar SQL.
        
        Este endpoint está diseñado para ser usado desde el frontend sin que
        el usuario necesite escribir consultas SQL. La query está integrada
        en el backend.
        
        **Filtros disponibles (query parameters):**
        - `anulada`: false (no anuladas) o true (anuladas) - Por defecto: false
        - `confirmado`: true (confirmadas) o false (no confirmadas) - Por defecto: true
        - `remision_facturada`: false (sin remisión) o true (con remisión) - Por defecto: false
        - `include_obj_datos`: true o false - Por defecto: true (solo con ObjDatosFactura)
        - `save_to_db`: true o false - Por defecto: true (guardar en SQL Server)
        
        **Ejemplo de uso:**
        ```
        GET /facturas?anulada=false&confirmado=true&remision_facturada=false
        ```
        
        **Valores por defecto (si no se especifican parámetros):**
        - Facturas NO anuladas (anulada=false)
        - Facturas confirmadas (confirmado=true)
        - Sin remisión facturada (remision_facturada=false)
        - Con ObjDatosFactura (include_obj_datos=true)
        
        Returns:
            JSON con los datos de MBA3, metadata de la consulta y estado del guardado
        """
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log
        logger.info("=" * 70)
        logger.info(f"Solicitud de facturas recibida a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"Filtros: anulada={anulada}, confirmado={confirmado}, remision_facturada={remision_facturada}")
        logger.info("=" * 70)
        
        try:
            # Obtener facturas usando el servicio
            result = MBA3Service.get_facturas(
                anulada=anulada,
                confirmado=confirmado,
                remision_facturada=remision_facturada,
                include_obj_datos=include_obj_datos,
                save_to_db=save_to_db,
                upsert=True
            )
            
            # Obtener los datos completos de MBA3
            data = result.get("data")
            
            # Log para debugging: verificar estructura de datos
            if data:
                if isinstance(data, list) and len(data) > 0:
                    logger.info(f"📊 Datos obtenidos: {len(data)} facturas")
                    # Log del primer elemento para verificar campos
                    first_item = data[0]
                    if isinstance(first_item, dict):
                        campos = list(first_item.keys())
                        logger.info(f"📋 Campos disponibles en primera factura: {campos}")
                        logger.info(f"📋 Ejemplo CODIGO_FACTURA: {first_item.get('CODIGO_FACTURA')}")
                        logger.info(f"📋 Ejemplo NUMERO_FACTURA: {first_item.get('NUMERO_FACTURA')}")
                        logger.info(f"📋 Ejemplo EMPRESA: {first_item.get('EMPRESA')}")
                elif isinstance(data, dict):
                    logger.info(f"📊 Datos obtenidos: objeto único (dict)")
                    campos = list(data.keys())
                    logger.info(f"📋 Campos disponibles: {campos}")
            
            # Preparar headers de respuesta
            headers = {
                "X-Source": source,
                "X-Filters": f"anulada={anulada},confirmado={confirmado},remision_facturada={remision_facturada}",
                "X-Count": str(result.get("count", 0))
            }
            
            # Agregar información de guardado si existe
            save_status = result.get("save_status")
            if save_status:
                headers["X-Saved-To-DB"] = save_status.get("status", "unknown")
                headers["X-DB-Facturas"] = str(save_status.get("facturas_guardadas", 0) + save_status.get("facturas_actualizadas", 0))
            
            # Retornar respuesta con metadata - asegurar que data contiene todos los campos
            response_data = {
                "status": "success",
                "data": data,  # Datos completos de MBA3 con todos los campos
                "metadata": {
                    "count": result.get("count", 0),
                    "filters": result.get("filters", {}),
                    "save_status": save_status
                }
            }
            
            return JSONResponse(
                status_code=200,
                content=response_data,
                headers=headers
            )
            
        except Exception as e:
            logger.error(f"❌ Error al obtener facturas: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al obtener facturas: {str(e)}"
                }
            )
    
    
    @app.get("/consulta")
    async def ejecutar_consulta_get(
        request: Request,
        query: str = FastAPIQuery(..., description="Consulta SQL a ejecutar contra MBA3")
    ):
        """
        Endpoint GET para ejecutar consultas SQL dinámicas contra MBA3.
        
        Equivalente al POST /consulta pero usando método GET con query parameter.
        Útil para pruebas desde el navegador o herramientas que prefieren GET.
        
        **Parámetros:**
        - `query`: Consulta SQL a ejecutar (requerido)
        
        **Ejemplo de uso:**
        ```
        GET /consulta?query=SELECT * FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'
        ```
        
        **Nota:** Las consultas complejas con caracteres especiales pueden requerir encoding URL.
        Para consultas más complejas, se recomienda usar POST /consulta.
        
        Valida que sea solo SELECT y bloquea operaciones peligrosas.
        Usa el cliente MBA3APIClient para ejecutar la consulta.
        
        Returns:
            JSON con el resultado de MBA3 o error si falla
        """
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de la consulta recibida
        logger.info("=" * 70)
        logger.info(f"Consulta GET recibida a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"Consulta: {query}")
        
        # Verificar si la query solo selecciona CODIGO_FACTURA
        query_upper = query.upper().strip()
        if "SELECT" in query_upper:
            select_part = query_upper.split("SELECT")[1].split("FROM")[0].strip() if "FROM" in query_upper else ""
            if select_part and "CODIGO_FACTURA" in select_part and len(select_part.split(",")) == 1:
                logger.warning("⚠️ ADVERTENCIA: La query solo selecciona CODIGO_FACTURA")
                logger.warning("⚠️ Para obtener todos los campos, usa: SELECT * FROM ...")
                logger.warning("⚠️ O especifica todos los campos necesarios")
        
        logger.info("Ejecutando consulta contra MBA3...")
        logger.info("=" * 70)
        
        try:
            # Ejecutar consulta usando el servicio
            result = MBA3Service.execute_query(query)
            
            # Log detallado de la respuesta para debugging
            logger.info("=" * 70)
            logger.info("📊 RESPUESTA DE MBA3:")
            if isinstance(result, list):
                logger.info(f"   Tipo: Lista con {len(result)} elementos")
                if len(result) > 0:
                    first_item = result[0]
                    if isinstance(first_item, dict):
                        campos = list(first_item.keys())
                        logger.info(f"   Campos en primera factura: {campos}")
                        logger.info(f"   Total de campos: {len(campos)}")
                        # Mostrar algunos valores de ejemplo
                        for campo in campos[:5]:  # Primeros 5 campos
                            logger.info(f"   {campo}: {first_item.get(campo)}")
                    else:
                        logger.warning(f"   ⚠️ Primer elemento no es dict: {type(first_item)}")
            elif isinstance(result, dict):
                logger.info(f"   Tipo: Diccionario")
                campos = list(result.keys())
                logger.info(f"   Campos: {campos}")
            else:
                logger.warning(f"   ⚠️ Tipo inesperado: {type(result)}")
            logger.info("=" * 70)
            
            # Guardar en SQL Server (si está habilitado)
            # upsert=True: Actualiza si existe, inserta si no existe
            save_status = MBA3Service.save_to_database(result, upsert=True)
            
            # Preparar headers de respuesta
            headers = {
                "X-Query": query[:100],  # Primeros 100 caracteres de la query
                "X-Source": source,
                "X-Method": "GET"
            }
            
            # Agregar información de guardado si existe
            if save_status:
                headers["X-Saved-To-DB"] = save_status.get("status", "unknown")
                headers["X-DB-Facturas"] = str(save_status.get("facturas_guardadas", 0))
            
            # Retornar resultado JSON de MBA3 directamente (mismo formato que POST)
            return JSONResponse(
                status_code=200,
                content=result,
                headers=headers
            )
            
        except Exception as e:
            logger.error(f"❌ Error al ejecutar consulta GET: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al ejecutar consulta: {str(e)}"
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
        # upsert=True: Actualiza si existe, inserta si no existe
        save_status = MBA3Service.save_to_database(result, upsert=True)
        
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
