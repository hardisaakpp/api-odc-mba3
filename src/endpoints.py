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
from database.services.sap_service import SAPService
from database.clients.sap_client import SAPClient
from database.repositories.despacho_repository import DespachoRepository
from database.repositories.orden_compra_repository import OrdenCompraRepository
from database.services.orden_compra_service import copy_despacho_to_orden_compra
from database.connection import get_db_connection
from config import ENABLE_SAP_QUERIES, SAP_LINKED_SERVER

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
    
    
    @app.get("/consultar")
    async def consultar_despachos(request: Request):
        """
        Endpoint CONSULTAR: Ejecuta consulta predefinida y muestra resultados.
        
        **Responsabilidad:** Solo consulta, NO guarda en base de datos.
        Usa la query predefinida configurada en el backend.
        
        **Características:**
        - ✅ Query predefinida integrada en el backend
        - ✅ Solo consulta datos desde MBA3
        - ✅ NO guarda en SQL Server
        - ✅ Retorna resultados para visualización en Swagger/Postman
        
        **Ejemplo de uso:**
        ```
        GET /consultar
        ```
        
        **Query predefinida:**
        ```sql
        SELECT CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada,CONFIRMADO,CODIGO_BODEGA FROM CLNT_FACTURA_PRINCIPAL WHERE TIPO_DOCUMENTO='REM' AND ANULADA='false' AND CONFIRMADO='true' AND Remision_Facturada='false' AND CODIGO_DESPACHO=0 AND NUMERO_FACTURA > 0 AND ObjDatosFactura IS NOT NULL
        ```
        
        **Nota:** Este endpoint es solo para consultar y visualizar datos.
        Para guardar en despacho, usar endpoint MIGRAR.
        Para proceso completo (consulta + guarda + copia a ODC), usar GET /consulta/predefinida.
        
        Returns:
            JSON con los datos consultados de MBA3 (sin guardar)
        """
        # Query predefinida (la misma que usa /consulta/predefinida)
        query_predefinida = "SELECT CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada,CONFIRMADO,CODIGO_BODEGA FROM CLNT_FACTURA_PRINCIPAL WHERE TIPO_DOCUMENTO='REM' AND ANULADA='false' AND CONFIRMADO='true' AND Remision_Facturada='false' AND CODIGO_DESPACHO=0 AND NUMERO_FACTURA > 0 AND ObjDatosFactura IS NOT NULL"
        
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de la consulta
        logger.info("=" * 70)
        logger.info(f"🔍 CONSULTAR: Consulta ejecutada a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"Query predefinida: {query_predefinida}")
        logger.info("Ejecutando consulta contra MBA3 (SOLO CONSULTA, NO GUARDA)...")
        logger.info("=" * 70)
        
        try:
            # Ejecutar consulta usando el servicio (SOLO consulta, NO guarda)
            result = MBA3Service.execute_query(query_predefinida)
            
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
            
            # Preparar headers de respuesta
            headers = {
                "X-Query": query_predefinida[:100],  # Primeros 100 caracteres de la query
                "X-Source": source,
                "X-Method": "GET",
                "X-Endpoint": "CONSULTAR",
                "X-Saved-To-DB": "false"  # Indica que NO se guardó
            }
            
            # Retornar resultado JSON de MBA3 directamente (solo para visualización)
            return JSONResponse(
                status_code=200,
                content=result,
                headers=headers
            )
            
        except Exception as e:
            logger.error(f"❌ Error al ejecutar consulta: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al ejecutar consulta: {str(e)}"
                }
            )
    
    
    @app.get("/migrar")
    async def migrar_despachos(request: Request):
        """
        Endpoint MIGRAR: Ejecuta consulta predefinida y guarda en despacho_cabecera/detalle.
        
        **Responsabilidad:** MIGRAR (endpoint #2 de los 4 requeridos)
        
        Este endpoint realiza:
        1. ✅ Consulta datos desde MBA3 usando query predefinida
        2. ✅ Guarda resultados en SQL Server (despacho_cabecera/detalle)
        3. ❌ NO copia a orden_compra (ese paso lo hace el endpoint PROCESAR)
        
        **Características:**
        - ✅ Query predefinida integrada en el backend
        - ✅ Ejecuta consultas contra MBA3 automáticamente
        - ✅ Guarda resultados en SQL Server (upsert)
        - ✅ NO copia a orden_compra_cabecera/detalle
        
        **Ejemplo de uso:**
        ```
        GET /migrar
        ```
        
        **Query predefinida:**
        ```sql
        SELECT CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada,CONFIRMADO,CODIGO_BODEGA FROM CLNT_FACTURA_PRINCIPAL WHERE TIPO_DOCUMENTO='REM' AND ANULADA='false' AND CONFIRMADO='true' AND Remision_Facturada='false' AND CODIGO_DESPACHO=0 AND NUMERO_FACTURA > 0 AND ObjDatosFactura IS NOT NULL
        ```
        
        **Nota:** Este endpoint solo migra a despacho.
        Para proceso completo (consulta + guarda + copia a ODC), usar GET /consulta/predefinida.
        
        Returns:
            JSON con los datos de MBA3 y metadata del guardado en despacho
        """
        # Query predefinida (la misma que usa /consulta/predefinida)
        query_predefinida = "SELECT CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada,CONFIRMADO,CODIGO_BODEGA FROM CLNT_FACTURA_PRINCIPAL WHERE TIPO_DOCUMENTO='REM' AND ANULADA='false' AND CONFIRMADO='true' AND Remision_Facturada='false' AND CODIGO_DESPACHO=0 AND NUMERO_FACTURA > 0 AND ObjDatosFactura IS NOT NULL"
        
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de la consulta predefinida
        logger.info("=" * 70)
        logger.info(f"🔄 MIGRAR: Proceso iniciado a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"Query predefinida: {query_predefinida}")
        logger.info("Ejecutando consulta contra MBA3...")
        logger.info("=" * 70)
        
        try:
            # Ejecutar consulta usando el servicio
            result = MBA3Service.execute_query(query_predefinida)
            
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
            
            # Guardar en SQL Server (despacho_cabecera/detalle)
            # upsert=True: Actualiza si existe, inserta si no existe
            logger.info("💾 Guardando en despacho_cabecera/detalle...")
            save_status = MBA3Service.save_to_database(result, upsert=True)
            
            # Preparar headers de respuesta
            headers = {
                "X-Query": query_predefinida[:100],  # Primeros 100 caracteres de la query
                "X-Source": source,
                "X-Method": "GET",
                "X-Endpoint": "MIGRAR"
            }
            
            # Agregar información de guardado si existe
            if save_status:
                headers["X-Saved-To-DB"] = save_status.get("status", "unknown")
                headers["X-DB-Facturas"] = str(save_status.get("facturas_guardadas", 0) + save_status.get("facturas_actualizadas", 0))
                headers["X-DB-Detalles"] = str(save_status.get("total_detalles", 0))
            
            # Preparar respuesta con metadata
            response_content = {
                "data": result,  # Datos de MBA3
                "metadata": {
                    "query": query_predefinida,
                    "save_status": save_status  # Estado del guardado en despacho
                }
            }
            
            logger.info("=" * 70)
            logger.info(f"✅ MIGRAR completado:")
            if save_status:
                logger.info(f"   Facturas guardadas: {save_status.get('facturas_guardadas', 0)}")
                logger.info(f"   Facturas actualizadas: {save_status.get('facturas_actualizadas', 0)}")
                logger.info(f"   Total detalles: {save_status.get('total_detalles', 0)}")
            logger.info("=" * 70)
            
            # Retornar respuesta con metadata
            return JSONResponse(
                status_code=200,
                content=response_content,
                headers=headers
            )
            
        except Exception as e:
            logger.error(f"❌ Error al ejecutar migración: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al ejecutar migración: {str(e)}"
                }
            )
    
    
    @app.get("/pruebas")
    async def ejecutar_pruebas(request: Request):
        """
        Endpoint de PRUEBAS: Ejecuta consulta predefinida, guarda en despacho y copia a orden de compra.
        
        Este endpoint realiza el proceso completo (para pruebas):
        1. ✅ Consulta datos desde MBA3 usando query predefinida
        2. ✅ Guarda resultados en SQL Server (despacho_cabecera/detalle)
        3. ✅ Copia despachos a orden_compra_cabecera/detalle
        
        **Uso:** Endpoint de pruebas que ejecuta todo el flujo completo.
        
        **Características:**
        - ✅ Query integrada en el backend (no requiere SQL del frontend)
        - ✅ Ejecuta consultas contra MBA3 automáticamente
        - ✅ Guarda resultados en SQL Server (upsert)
        - ✅ Copia automáticamente a orden_compra_cabecera/detalle
        - ✅ Logs detallados para debugging
        
        **Ejemplo de uso:**
        ```
        GET /pruebas
        ```
        
        **Query predefinida:**
        ```sql
        SELECT CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada,CONFIRMADO,CODIGO_BODEGA FROM CLNT_FACTURA_PRINCIPAL WHERE TIPO_DOCUMENTO='REM' AND ANULADA='false' AND CONFIRMADO='true' AND Remision_Facturada='false' AND CODIGO_DESPACHO=0 AND NUMERO_FACTURA > 0 AND ObjDatosFactura IS NOT NULL
        ```
        
        **Respuesta incluye:**
        - `data`: Resultados de MBA3
        - `metadata.save_status`: Estado del guardado en despacho
        - `metadata.oc_status`: Estado de copia a orden de compra
        
        **Headers de respuesta:**
        - `X-Saved-To-DB`: Estado del guardado
        - `X-DB-Facturas`: Número de facturas guardadas
        - `X-OC-Status`: Estado de copia a ODC
        - `X-OC-Creadas`: Número de OCs creadas
        
        Returns:
            JSON con datos de MBA3 y metadata del proceso completo
        """
        # Query predefinida integrada en el backend
        query_predefinida = "SELECT CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada,CONFIRMADO,CODIGO_BODEGA FROM CLNT_FACTURA_PRINCIPAL WHERE TIPO_DOCUMENTO='REM' AND ANULADA='false' AND CONFIRMADO='true' AND Remision_Facturada='false' AND CODIGO_DESPACHO=0 AND NUMERO_FACTURA > 0 AND ObjDatosFactura IS NOT NULL"
        
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de la consulta predefinida
        logger.info("=" * 70)
        logger.info(f"Consulta predefinida ejecutada a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"Query predefinida: {query_predefinida}")
        logger.info("Ejecutando consulta contra MBA3...")
        logger.info("=" * 70)
        
        try:
            # Ejecutar consulta usando el servicio
            result = MBA3Service.execute_query(query_predefinida)
            
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
            
            # PROCESAR: Copiar despachos a orden_compra_cabecera/detalle
            oc_status = None
            if save_status and save_status.get("status") in ["success", "partial"]:
                try:
                    logger.info("=" * 70)
                    logger.info("🔄 PROCESANDO: Copiando despachos a orden de compra...")
                    logger.info("=" * 70)
                    
                    # Obtener conexión y repositorios
                    conn = get_db_connection()
                    despacho_repo = DespachoRepository(conn)
                    oc_repo = OrdenCompraRepository(conn)
                    
                    # Obtener despacho_ids de las facturas guardadas
                    facturas = result if isinstance(result, list) else [result]
                    oc_resultados = []
                    oc_exitosas = 0
                    oc_errores = 0
                    
                    for factura in facturas:
                        codigo_factura = factura.get("CODIGO_FACTURA")
                        if not codigo_factura:
                            continue
                        
                        # Buscar despacho_id por código_factura
                        despacho_id = despacho_repo.find_by_codigo_factura(codigo_factura)
                        if not despacho_id:
                            logger.warning(f"⚠️ No se encontró despacho_id para factura: {codigo_factura}")
                            continue
                        
                        try:
                            # Copiar despacho a orden de compra (con upsert)
                            oc_resultado = copy_despacho_to_orden_compra(
                                despacho_repo=despacho_repo,
                                oc_repo=oc_repo,
                                despacho_id=despacho_id,
                                upsert=True
                            )
                            
                            if oc_resultado:
                                oc_exitosas += 1
                                accion = "actualizada" if oc_resultado.get("cabecera_actualizada") else "creada"
                                oc_resultados.append({
                                    "despacho_id": despacho_id,
                                    "oc_id": oc_resultado.get("oc_id"),
                                    "proveedor": oc_resultado.get("proveedor"),
                                    "detalles_insertados": oc_resultado.get("detalles_insertados", 0),
                                    "accion": accion
                                })
                            else:
                                logger.warning(f"⚠️ No se pudo crear/actualizar OC para despacho: {despacho_id}")
                                
                        except Exception as oc_error:
                            oc_errores += 1
                            logger.error(f"❌ Error al copiar despacho {despacho_id} a OC: {oc_error}")
                            oc_resultados.append({
                                "despacho_id": despacho_id,
                                "error": str(oc_error)
                            })
                    
                    # Cerrar conexión
                    conn.close()
                    
                    oc_status = {
                        "status": "success" if oc_errores == 0 else "partial",
                        "oc_creadas": oc_exitosas,
                        "oc_errores": oc_errores,
                        "total_procesadas": len(oc_resultados),
                        "detalles": oc_resultados
                    }
                    
                    logger.info("=" * 70)
                    logger.info(f"✅ PROCESO COMPLETO:")
                    logger.info(f"   OCs creadas: {oc_exitosas}")
                    logger.info(f"   Errores: {oc_errores}")
                    logger.info("=" * 70)
                    
                except Exception as e:
                    logger.error(f"❌ Error al procesar copia a ODC: {e}", exc_info=True)
                    oc_status = {
                        "status": "error",
                        "message": str(e),
                        "oc_creadas": 0,
                        "oc_errores": 0
                    }
            
            # Preparar headers de respuesta
            headers = {
                "X-Query": query_predefinida[:100],  # Primeros 100 caracteres de la query
                "X-Source": source,
                "X-Method": "GET",
                "X-Predefined": "true"
            }
            
            # Agregar información de guardado si existe
            if save_status:
                headers["X-Saved-To-DB"] = save_status.get("status", "unknown")
                headers["X-DB-Facturas"] = str(save_status.get("facturas_guardadas", 0) + save_status.get("facturas_actualizadas", 0))
            
            # Agregar información de ODC si existe
            if oc_status:
                headers["X-OC-Status"] = oc_status.get("status", "unknown")
                headers["X-OC-Creadas"] = str(oc_status.get("oc_creadas", 0))
            
            # Preparar respuesta con metadata completa
            response_content = {
                "data": result,  # Datos de MBA3
                "metadata": {
                    "query": query_predefinida,
                    "save_status": save_status,
                    "oc_status": oc_status  # Estado de copia a ODC
                }
            }
            
            # Retornar respuesta con metadata
            return JSONResponse(
                status_code=200,
                content=response_content,
                headers=headers
            )
            
        except Exception as e:
            logger.error(f"❌ Error al ejecutar consulta predefinida: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al ejecutar consulta predefinida: {str(e)}"
                }
            )
    
    
    @app.get("/procesar-oc")
    async def procesar_orden_compra(request: Request):
        """
        Endpoint PROCESAR-OC: Copia despachos existentes a orden_compra_cabecera/detalle.
        
        **Responsabilidad:** Copiar despachos a orden de compra (paso 3 del proceso completo)
        
        Este endpoint realiza:
        1. ❌ NO consulta (ya lo hizo CONSULTAR)
        2. ❌ NO guarda en despacho (ya lo hizo MIGRAR)
        3. ✅ Copia despachos existentes a orden_compra_cabecera/detalle
        
        **Características:**
        - ✅ Busca despachos en despacho_cabecera que NO tienen OC asociada
        - ✅ Copia cada despacho a orden_compra_cabecera/detalle
        - ✅ Mapea empresa → proveedor desde tabla cliente
        - ✅ Omite despachos que ya tienen OC (skip_if_exists=True)
        
        **Ejemplo de uso:**
        ```
        GET /procesar-oc
        ```
        
        **Nota:** Este endpoint asume que los despachos ya están guardados en despacho_cabecera/detalle.
        Para proceso completo (consulta + guarda + copia), usar GET /consulta/predefinida.
        
        **Flujo recomendado:**
        1. GET /consultar - Solo consulta
        2. GET /migrar - Consulta + Guarda en despacho
        3. GET /procesar-oc - Copia despachos a ODC
        
        Returns:
            JSON con metadata del proceso de copia a orden de compra
        """
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log del proceso
        logger.info("=" * 70)
        logger.info(f"🔄 PROCESAR-OC: Iniciado a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info("Buscando despachos sin orden de compra asociada...")
        logger.info("=" * 70)
        
        try:
            # Obtener conexión y repositorios
            conn = get_db_connection()
            despacho_repo = DespachoRepository(conn)
            oc_repo = OrdenCompraRepository(conn)
            
            # Obtener despachos que no tienen OC asociada
            despachos_sin_oc = despacho_repo.get_despachos_sin_oc()
            
            if not despachos_sin_oc:
                logger.info("ℹ️ No se encontraron despachos sin orden de compra")
                conn.close()
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "message": "No hay despachos pendientes de copiar a orden de compra",
                        "oc_creadas": 0,
                        "oc_errores": 0,
                        "total_despachos": 0
                    },
                    headers={
                        "X-Source": source,
                        "X-Endpoint": "PROCESAR-OC"
                    }
                )
            
            logger.info(f"📦 Encontrados {len(despachos_sin_oc)} despachos sin OC")
            logger.info("=" * 70)
            logger.info("🔄 PROCESANDO: Copiando despachos a orden de compra...")
            logger.info("=" * 70)
            
            # Procesar cada despacho
            oc_resultados = []
            oc_exitosas = 0
            oc_errores = 0
            
            for idx, despacho_id in enumerate(despachos_sin_oc, 1):
                try:
                    logger.info(f"[{idx}/{len(despachos_sin_oc)}] Procesando despacho: {despacho_id}")
                    
                    # Copiar despacho a orden de compra (con upsert)
                    oc_resultado = copy_despacho_to_orden_compra(
                        despacho_repo=despacho_repo,
                        oc_repo=oc_repo,
                        despacho_id=despacho_id,
                        upsert=True
                    )
                    
                    if oc_resultado:
                        oc_exitosas += 1
                        accion = "actualizada" if oc_resultado.get("cabecera_actualizada") else "creada"
                        oc_resultados.append({
                            "despacho_id": despacho_id,
                            "oc_id": oc_resultado.get("oc_id"),
                            "proveedor": oc_resultado.get("proveedor"),
                            "detalles_insertados": oc_resultado.get("detalles_insertados", 0),
                            "accion": accion
                        })
                        logger.info(f"   ✅ OC {accion}: {oc_resultado.get('oc_id')}")
                    else:
                        logger.warning(f"   ⚠️ No se pudo crear/actualizar OC para despacho: {despacho_id}")
                        
                except Exception as oc_error:
                    oc_errores += 1
                    logger.error(f"   ❌ Error al copiar despacho {despacho_id} a OC: {oc_error}")
                    oc_resultados.append({
                        "despacho_id": despacho_id,
                        "error": str(oc_error)
                    })
            
            # Cerrar conexión
            conn.close()
            
            oc_status = {
                "status": "success" if oc_errores == 0 else "partial",
                "oc_creadas": oc_exitosas,
                "oc_errores": oc_errores,
                "total_procesadas": len(oc_resultados),
                "total_despachos": len(despachos_sin_oc),
                "detalles": oc_resultados
            }
            
            logger.info("=" * 70)
            logger.info(f"✅ PROCESAR-OC completado:")
            logger.info(f"   Total despachos encontrados: {len(despachos_sin_oc)}")
            logger.info(f"   OCs creadas: {oc_exitosas}")
            logger.info(f"   Errores: {oc_errores}")
            logger.info("=" * 70)
            
            # Preparar headers de respuesta
            headers = {
                "X-Source": source,
                "X-Endpoint": "PROCESAR-OC",
                "X-OC-Status": oc_status.get("status", "unknown"),
                "X-OC-Creadas": str(oc_exitosas),
                "X-OC-Errores": str(oc_errores),
                "X-Total-Despachos": str(len(despachos_sin_oc))
            }
            
            # Retornar respuesta con metadata
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": f"Proceso completado: {oc_exitosas} OCs creadas de {len(despachos_sin_oc)} despachos",
                    "metadata": oc_status
                },
                headers=headers
            )
            
        except Exception as e:
            logger.error(f"❌ Error al procesar orden de compra: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al procesar orden de compra: {str(e)}"
                }
            )
    
    
    @app.get("/sap/test")
    async def test_sap_query(
        request: Request,
        sku: str = FastAPIQuery(..., description="SKU del producto a consultar en SAP (ej: 5-0012.9)")
    ):
        """
        Endpoint de prueba para consultar información de un producto desde SAP.
        
        Este endpoint permite probar la integración con SAP sin necesidad de procesar
        una factura completa. Consulta información del producto y muestra el resultado.
        
        **Parámetros:**
        - `sku`: SKU del producto a consultar (requerido)
        
        **Ejemplo de uso:**
        ```
        GET /sap/test?sku=5-0012.9
        ```
        
        **Respuesta:**
        - Información del producto desde SAP (ItemCode, ItemName, U_IXX_PACK)
        - Información del cache si está disponible
        - Unidad de conversión calculada
        
        Returns:
            JSON con información del producto desde SAP o error si falla
        """
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log
        logger.info("=" * 70)
        logger.info(f"Prueba de consulta SAP recibida a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"SKU: {sku}")
        logger.info("=" * 70)
        
        try:
            # Verificar si SAP está habilitado
            if not ENABLE_SAP_QUERIES:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": "Consultas SAP están deshabilitadas",
                        "hint": "Configura ENABLE_SAP_QUERIES=true en .env"
                    }
                )
            
            # Inicializar servicio SAP
            sap_service = SAPService()
            
            # Obtener información del producto (consultará SAP o usará cache)
            producto_info = sap_service.get_or_fetch_producto_info(sku)
            
            if producto_info:
                # Preparar respuesta detallada
                response_data = {
                    "status": "success",
                    "sku": sku,
                    "sap_info": {
                        "item_code": producto_info.get("item_code"),
                        "item_name": producto_info.get("item_name"),
                        "pack_sap": producto_info.get("pack_sap"),
                        "pack_id": producto_info.get("pack_id"),
                        "unidad_conversion": producto_info.get("unidad_conversion"),
                    },
                    "config": {
                        "sap_linked_server": SAP_LINKED_SERVER,
                        "sap_enabled": ENABLE_SAP_QUERIES,
                    },
                    "message": "Producto encontrado en SAP",
                    "timestamp": datetime.now().isoformat()
                }
                
                # Agregar información de conversión si está disponible
                unidad = producto_info.get("unidad_conversion")
                if unidad:
                    response_data["conversion_info"] = {
                        "unidad_conversion": unidad,
                        "formula": "1 docena = {unidad} packs".format(unidad=unidad),
                        "ejemplo": {
                            "docenas": 456,
                            "packs": 456 * unidad,
                            "formula_ejemplo": f"456 docenas × {unidad} = {456 * unidad} packs"
                        }
                    }
                
                logger.info(f"✅ Consulta SAP exitosa para SKU: {sku}")
                logger.info(f"   Pack: {producto_info.get('pack_sap')}, Unidad: {producto_info.get('unidad_conversion')}")
                
                return JSONResponse(
                    status_code=200,
                    content=response_data,
                    headers={
                        "X-Source": source,
                        "X-SKU": sku,
                        "X-Pack-SAP": producto_info.get("pack_sap") or "N/A"
                    }
                )
            else:
                logger.warning(f"⚠️ Producto no encontrado en SAP: {sku}")
                return JSONResponse(
                    status_code=404,
                    content={
                        "status": "not_found",
                        "message": f"Producto no encontrado en SAP para SKU: {sku}",
                        "sku": sku,
                        "hint": "Verifica que el SKU exista en SAP y que el servidor vinculado esté configurado correctamente",
                        "timestamp": datetime.now().isoformat()
                    }
                )
                
        except Exception as e:
            logger.error(f"❌ Error al consultar SAP: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al consultar SAP: {str(e)}",
                    "sku": sku,
                    "timestamp": datetime.now().isoformat()
                }
            )
    
    
    @app.get("/sap/test/direct")
    async def test_sap_direct(
        request: Request,
        sku: str = FastAPIQuery(..., description="SKU del producto a consultar directamente en SAP")
    ):
        """
        Endpoint de prueba para consulta directa a SAP (sin usar cache).
        
        Este endpoint consulta directamente a SAP sin verificar el cache primero.
        Útil para forzar una consulta nueva y verificar que la conexión funciona.
        
        **Parámetros:**
        - `sku`: SKU del producto a consultar (requerido)
        
        **Ejemplo de uso:**
        ```
        GET /sap/test/direct?sku=5-0012.9
        ```
        
        Returns:
            JSON con información del producto desde SAP (sin cache)
        """
        source = get_source_from_headers(request)
        
        logger.info("=" * 70)
        logger.info(f"Prueba de consulta SAP directa recibida a las {datetime.now().isoformat()}")
        logger.info(f"SKU: {sku}")
        logger.info("=" * 70)
        
        try:
            if not ENABLE_SAP_QUERIES:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": "Consultas SAP están deshabilitadas"
                    }
                )
            
            # Consulta directa sin cache
            client = SAPClient()
            resultado = client.get_producto_info(sku)
            
            if resultado:
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "sku": sku,
                        "sap_direct_result": resultado,
                        "message": "Consulta directa a SAP exitosa",
                        "timestamp": datetime.now().isoformat()
                    },
                    headers={
                        "X-Source": source,
                        "X-SKU": sku
                    }
                )
            else:
                return JSONResponse(
                    status_code=404,
                    content={
                        "status": "not_found",
                        "message": f"Producto no encontrado en SAP: {sku}",
                        "sku": sku
                    }
                )
                
        except Exception as e:
            logger.error(f"❌ Error en consulta directa SAP: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al consultar SAP: {str(e)}",
                    "sku": sku
                }
            )
