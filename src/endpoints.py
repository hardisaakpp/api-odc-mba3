"""
Endpoints FastAPI para la API de consultas MBA3.

Esta versión usa servicios y helpers para separar la lógica de negocio.
"""

import logging
from datetime import datetime

from fastapi import Request, Query as FastAPIQuery, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional

from models import HealthResponse
from services.mba3_service import MBA3Service
from utils import get_source_from_headers
from database.services.sap_service import SAPService
from database.clients.sap_client import SAPClient
from database.repositories.despacho_repository import DespachoRepository
from database.repositories.orden_compra_repository import OrdenCompraRepository
from database.services.orden_compra_service import copy_despacho_to_orden_compra
from database.services.oc_sap_service import OCSAPService
from database.connection import get_db_connection
from config import ENABLE_SAP_QUERIES, SAP_LINKED_SERVER, ENABLE_SAP_SERVICE_LAYER
from security.auth import optional_auth
from security.jwt_auth import verify_jwt_token, require_permission
from fastapi import Depends, Query
from exceptions import MBA3ConnectionError, MBA3QueryError

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
    
    
    @app.get("/facturas")
    async def get_facturas(
        request: Request,
        anulada: Optional[bool] = Query(None, description="Filtrar por facturas anuladas (false = no anuladas, true = anuladas, null = todas)"),
        confirmado: Optional[bool] = Query(None, description="Filtrar por facturas confirmadas (true = confirmadas, false = no confirmadas, null = todas)"),
        remision_facturada: Optional[bool] = Query(None, description="Filtrar por remisión facturada (false = sin remisión, true = con remisión, null = todas)"),
        include_obj_datos: bool = Query(True, description="Incluir solo facturas con ObjDatosFactura no nulo"),
        save_to_db: bool = Query(True, description="Guardar resultados en SQL Server"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Endpoint FACTURAS: Obtiene facturas desde MBA3 con filtros configurables.
        
        ⭐ **Recomendado para Frontend**
        
        Este endpoint obtiene facturas desde MBA3 usando filtros configurables.
        La query está integrada en el backend, no requiere SQL del frontend.
        
        **Query Parameters:**
        - `anulada` (boolean, opcional) - Filtrar por facturas anuladas
        - `confirmado` (boolean, opcional) - Filtrar por facturas confirmadas
        - `remision_facturada` (boolean, opcional) - Filtrar por remisión facturada
        - `include_obj_datos` (boolean, default: true) - Incluir solo facturas con ObjDatosFactura
        - `save_to_db` (boolean, default: true) - Guardar en SQL Server
        
        **Ejemplo:**
        ```
        GET /facturas?anulada=false&confirmado=true&save_to_db=true
        ```
        
        **Respuesta:**
        ```json
        {
          "status": "success",
          "data": [...],
          "metadata": {
            "count": 10,
            "filters": {...},
            "save_status": {...}
          }
        }
        ```
        
        Returns:
            JSON con facturas y metadata
        """
        source = get_source_from_headers(request)
        
        logger.info("=" * 70)
        logger.info(f"📋 GET /facturas: Consulta ejecutada a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"Filtros: anulada={anulada}, confirmado={confirmado}, remision_facturada={remision_facturada}, include_obj_datos={include_obj_datos}, save_to_db={save_to_db}")
        logger.info("=" * 70)
        
        try:
            # Usar valores por defecto si no se proporcionan
            anulada_filter = anulada if anulada is not None else False
            confirmado_filter = confirmado if confirmado is not None else True
            remision_facturada_filter = remision_facturada if remision_facturada is not None else False
            
            # Obtener facturas usando el servicio
            result = MBA3Service.get_facturas(
                anulada=anulada_filter,
                confirmado=confirmado_filter,
                remision_facturada=remision_facturada_filter,
                include_obj_datos=include_obj_datos,
                save_to_db=save_to_db,
                upsert=True
            )
            
            # Preparar respuesta
            response_data = {
                "status": "success",
                "data": result.get("data", []),
                "metadata": {
                    "count": result.get("count", 0),
                    "filters": result.get("filters", {}),
                    "save_status": result.get("save_status")
                }
            }
            
            logger.info(f"✅ GET /facturas: {result.get('count', 0)} facturas encontradas")
            
            return JSONResponse(
                status_code=200,
                content=response_data,
                headers={
                    "X-Source": source,
                    "X-Endpoint": "FACTURAS",
                    "X-Count": str(result.get("count", 0))
                }
            )
            
        except MBA3ConnectionError as e:
            logger.error(f"❌ Error de conexión con MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "message": f"No se pudo conectar al servidor MBA3",
                    "detail": str(e),
                    "type": "connection_error",
                    "hint": "Verifica que el servidor MBA3 esté disponible y accesible. Revisa la configuración de MBA3_BASE_URL en tu archivo .env"
                }
            )
        except MBA3QueryError as e:
            logger.error(f"❌ Error al ejecutar consulta en MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al ejecutar consulta en MBA3",
                    "detail": str(e),
                    "type": "query_error"
                }
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
    
    
    @app.get("/consultar")
    async def consultar_despachos(
        request: Request,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
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
        
        # Log de usuario autenticado
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"👤 Usuario autenticado: {username}")
        
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
                    first_item = result[0]  # type: ignore[reportArgumentType]
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
            
        except MBA3ConnectionError as e:
            logger.error(f"❌ Error de conexión con MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "message": f"No se pudo conectar al servidor MBA3",
                    "detail": str(e),
                    "type": "connection_error",
                    "hint": "Verifica que el servidor MBA3 esté disponible y accesible. Revisa la configuración de MBA3_BASE_URL en tu archivo .env"
                }
            )
        except MBA3QueryError as e:
            logger.error(f"❌ Error al ejecutar consulta en MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al ejecutar consulta en MBA3",
                    "detail": str(e),
                    "type": "query_error"
                }
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
    async def migrar_despachos(
        request: Request,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
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
        
        # Log de usuario autenticado
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"👤 Usuario autenticado: {username}")
        
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
                    first_item = result[0]  # type: ignore[reportArgumentType]
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
            
        except MBA3ConnectionError as e:
            logger.error(f"❌ Error de conexión con MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "message": f"No se pudo conectar al servidor MBA3",
                    "detail": str(e),
                    "type": "connection_error",
                    "hint": "Verifica que el servidor MBA3 esté disponible y accesible. Revisa la configuración de MBA3_BASE_URL en tu archivo .env"
                }
            )
        except MBA3QueryError as e:
            logger.error(f"❌ Error al ejecutar consulta en MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al ejecutar consulta en MBA3",
                    "detail": str(e),
                    "type": "query_error"
                }
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
    async def ejecutar_pruebas(
        request: Request,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Endpoint de PRUEBAS: Ejecuta el proceso completo de los 3 primeros endpoints.
        
        Este endpoint realiza el proceso completo (para pruebas):
        1. ✅ Consulta datos desde MBA3 usando query predefinida (CONSULTAR)
        2. ✅ Guarda resultados en SQL Server (despacho_cabecera/detalle) (MIGRAR)
        3. ✅ Copia despachos a orden_compra_cabecera/detalle (PROCESAR)
        4. ❌ NO envía a SAP (ese paso lo hace el endpoint INTEGRAR)
        
        **Uso:** Endpoint de pruebas que ejecuta todo el flujo completo de los 3 primeros endpoints.
        
        **Características:**
        - ✅ Query integrada en el backend (no requiere SQL del frontend)
        - ✅ Ejecuta consultas contra MBA3 automáticamente
        - ✅ Guarda resultados en SQL Server (upsert)
        - ✅ Copia automáticamente a orden_compra_cabecera/detalle
        - ✅ Crea las ODC con estado "PENDIENTE" (listas para enviar a SAP)
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
        
        **Nota:** Este endpoint ejecuta los 3 primeros pasos del flujo completo.
        Para enviar a SAP, usar el endpoint POST /integrar-sap (cuando esté disponible).
        
        Returns:
            JSON con datos de MBA3 y metadata del proceso completo
        """
        # Query predefinida integrada en el backend
        query_predefinida = "SELECT CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada,CONFIRMADO,CODIGO_BODEGA FROM CLNT_FACTURA_PRINCIPAL WHERE TIPO_DOCUMENTO='REM' AND ANULADA='false' AND CONFIRMADO='true' AND Remision_Facturada='false' AND CODIGO_DESPACHO=0 AND NUMERO_FACTURA > 0 AND ObjDatosFactura IS NOT NULL"
        
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de usuario autenticado
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"👤 Usuario autenticado: {username}")
        
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
                    first_item = result[0]  # type: ignore[reportArgumentType]
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
                    if isinstance(result, list):
                        facturas = result
                    elif isinstance(result, dict):
                        facturas = [result]
                    else:
                        facturas = []
                    
                    oc_resultados = []
                    oc_exitosas = 0
                    oc_errores = 0
                    
                    for factura in facturas:
                        if not isinstance(factura, dict):
                            continue
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
                                oc_id = oc_resultado.get("oc_id")
                                accion = "actualizada" if oc_resultado.get("cabecera_actualizada") else "creada"
                                
                                resultado_item = {
                                    "despacho_id": despacho_id,
                                    "oc_id": oc_id,
                                    "proveedor": oc_resultado.get("proveedor"),
                                    "detalles_insertados": oc_resultado.get("detalles_insertados", 0),
                                    "accion": accion,
                                    "estado": "PENDIENTE"  # Estado inicial de la ODC
                                }
                                
                                logger.info(f"   ✅ OC {accion}: {oc_id} (estado: PENDIENTE)")
                                
                                oc_resultados.append(resultado_item)
                            else:
                                oc_errores += 1
                                logger.warning(f"⚠️ No se pudo crear/actualizar OC para despacho: {despacho_id}")
                                oc_resultados.append({
                                    "despacho_id": despacho_id,
                                    "error": "No se pudo crear/actualizar OC"
                                })
                                
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
                    logger.info(f"   Estado de OCs creadas: PENDIENTE (listas para enviar a SAP)")
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
            
        except MBA3ConnectionError as e:
            logger.error(f"❌ Error de conexión con MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "message": f"No se pudo conectar al servidor MBA3",
                    "detail": str(e),
                    "type": "connection_error",
                    "hint": "Verifica que el servidor MBA3 esté disponible y accesible. Revisa la configuración de MBA3_BASE_URL en tu archivo .env"
                }
            )
        except MBA3QueryError as e:
            logger.error(f"❌ Error al ejecutar consulta en MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al ejecutar consulta en MBA3",
                    "detail": str(e),
                    "type": "query_error"
                }
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
    async def procesar_orden_compra(
        request: Request,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Endpoint PROCESAR-OC: Copia despachos a orden de compra.
        
        **Responsabilidad:** PROCESAR (endpoint #3 de los 4 requeridos)
        
        Este endpoint realiza:
        1. ❌ NO consulta (ya lo hizo CONSULTAR)
        2. ❌ NO guarda en despacho (ya lo hizo MIGRAR)
        3. ✅ Copia despachos existentes a orden_compra_cabecera/detalle
        4. ❌ NO envía a SAP (ese paso lo hace el endpoint INTEGRAR)
        
        **Características:**
        - ✅ Busca despachos en despacho_cabecera que NO tienen OC asociada
        - ✅ Copia cada despacho a orden_compra_cabecera/detalle
        - ✅ Mapea empresa → proveedor desde tabla cliente
        - ✅ Omite despachos que ya tienen OC (skip_if_exists=True)
        - ✅ Crea las ODC con estado "PENDIENTE" (listas para enviar a SAP)
        
        **Ejemplo de uso:**
        ```
        GET /procesar-oc
        ```
        
        **Nota:** Este endpoint asume que los despachos ya están guardados en despacho_cabecera/detalle.
        Para proceso completo (consulta + guarda + copia + integración), usar los 4 endpoints en secuencia.
        
        **Flujo recomendado:**
        1. GET /consultar - Solo consulta
        2. GET /migrar - Consulta + Guarda en despacho
        3. GET /procesar-oc - Copia despachos a ODC (estado: PENDIENTE)
        4. POST /integrar-sap - Envía ODC a SAP usando middleware
        
        **Estados de ODC:**
        - `PENDIENTE`: Creada pero no enviada a SAP (estado inicial)
        - `ENVIADA`: Enviada exitosamente a SAP (se actualiza en endpoint INTEGRAR)
        - `ERROR`: Error al enviar a SAP (se actualiza en endpoint INTEGRAR)
        
        Returns:
            JSON con metadata del proceso de creación de ODC
        """
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de usuario autenticado
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"👤 Usuario autenticado: {username}")
        
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
                        oc_id = oc_resultado.get("oc_id")
                        accion = "actualizada" if oc_resultado.get("cabecera_actualizada") else "creada"
                        
                        resultado_item = {
                            "despacho_id": despacho_id,
                            "oc_id": oc_id,
                            "proveedor": oc_resultado.get("proveedor"),
                            "detalles_insertados": oc_resultado.get("detalles_insertados", 0),
                            "accion": accion,
                            "estado": "PENDIENTE"  # Estado inicial de la ODC
                        }
                        
                        logger.info(f"   ✅ OC {accion}: {oc_id} (estado: PENDIENTE)")
                        
                        oc_resultados.append(resultado_item)
                    else:
                        oc_errores += 1
                        logger.warning(f"   ⚠️ No se pudo crear/actualizar OC para despacho: {despacho_id}")
                        oc_resultados.append({
                            "despacho_id": despacho_id,
                            "error": "No se pudo crear/actualizar OC"
                        })
                        
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
            logger.info(f"   Estado de OCs creadas: PENDIENTE (listas para enviar a SAP)")
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
            
            # Construir mensaje
            mensaje = f"Proceso completado: {oc_exitosas} OCs creadas de {len(despachos_sin_oc)} despachos (estado: PENDIENTE)"
            
            # Retornar respuesta con metadata
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": mensaje,
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
    
    @app.post("/integrar-sap")
    async def integrar_sap(
        request: Request,
        referencia_despacho: Optional[str] = FastAPIQuery(None, description="Referencia del despacho (número de factura) para buscar una OC específica. Si no se proporciona, se procesa la primera OC pendiente."),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Endpoint INTEGRAR-SAP: Envía órdenes de compra a SAP Service Layer.
        
        **Responsabilidad:** INTEGRAR (endpoint #4 de los 4 requeridos)
        
        Este endpoint realiza:
        1. ❌ NO consulta (ya lo hizo CONSULTAR)
        2. ❌ NO guarda en despacho (ya lo hizo MIGRAR)
        3. ❌ NO copia a OC (ya lo hizo PROCESAR)
        4. ✅ Envía ODCs con estado "PENDIENTE" a SAP Service Layer
        5. ✅ Actualiza estado a "ENVIADA" o "ERROR" según resultado
        
        **Características:**
        - ✅ Si se proporciona `referencia_despacho`: busca esa OC específica y la envía
        - ✅ Si NO se proporciona `referencia_despacho`: busca la primera ODC pendiente y la envía
        - ✅ Envía UNA SOLA ODC por cada llamada al endpoint
        - ✅ Convierte la ODC a formato JSON de SAP Service Layer
        - ✅ Envía la ODC directamente a SAP Service Layer (sin middleware)
        - ✅ Actualiza estado a "ENVIADA" o "ERROR" según resultado
        - ✅ Retorna información de la ODC procesada y cantidad de pendientes restantes
        
        **Query Parameters:**
        - `referencia_despacho` (opcional): Número de factura/despacho para buscar una OC específica
        
        **Ejemplos de uso:**
        ```
        # Buscar OC específica por referencia
        POST /integrar-sap?referencia_despacho=900125353
        
        # Procesar primera OC pendiente (comportamiento por defecto)
        POST /integrar-sap
        ```
        
        **Nota:** Este endpoint asume que las ODCs ya están creadas con estado "PENDIENTE".
        Para proceso completo (consulta + guarda + copia + integración), usar los 4 endpoints en secuencia.
        
        **Flujo recomendado:**
        1. GET /consultar - Solo consulta
        2. GET /migrar - Consulta + Guarda en despacho
        3. GET /procesar-oc - Copia despachos a ODC (estado: PENDIENTE)
        4. POST /integrar-sap - Envía ODC a SAP Service Layer
        
        **Estados de ODC:**
        - `PENDIENTE`: Creada pero no enviada a SAP (estado inicial)
        - `ENVIADA`: Enviada exitosamente a SAP (se actualiza aquí)
        - `ERROR`: Error al enviar a SAP (se actualiza aquí)
        
        **Configuración requerida:**
        - Variables de entorno en `.env`:
          - `SAP_SERVICE_LAYER_URL`
          - `SAP_SERVICE_LAYER_USERNAME`
          - `SAP_SERVICE_LAYER_PASSWORD`
          - `SAP_SERVICE_LAYER_DATABASE`
          - `ENABLE_SAP_SERVICE_LAYER=true`
        
        Returns:
            JSON con metadata del proceso de envío a SAP
        """
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de usuario autenticado
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"👤 Usuario autenticado: {username}")
        
        # Log del proceso
        logger.info("=" * 70)
        logger.info(f"🚀 INTEGRAR-SAP: Iniciado a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        if referencia_despacho:
            logger.info(f"Buscando OC por referencia_despacho: {referencia_despacho}")
        else:
            logger.info("Buscando órdenes de compra pendientes de enviar a SAP...")
        logger.info("=" * 70)
        
        try:
            # Verificar si SAP Service Layer está habilitado
            if not ENABLE_SAP_SERVICE_LAYER:
                logger.warning("⚠️ SAP Service Layer está deshabilitado")
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": "SAP Service Layer está deshabilitado",
                        "hint": "Configura ENABLE_SAP_SERVICE_LAYER=true en .env"
                    },
                    headers={
                        "X-Source": source,
                        "X-Endpoint": "INTEGRAR-SAP"
                    }
                )
            
            # Obtener conexión y repositorios
            conn = get_db_connection()
            oc_repo = OrdenCompraRepository(conn)
            
            # Inicializar servicio SAP
            oc_sap_service = OCSAPService()
            
            # Determinar qué OC procesar
            if referencia_despacho:
                # Buscar OC específica por referencia_despacho
                oc_pendiente = oc_repo.find_by_referencia_despacho(referencia_despacho)
                
                if not oc_pendiente:
                    conn.close()
                    logger.warning(f"⚠️ No se encontró OC con referencia_despacho: {referencia_despacho}")
                    return JSONResponse(
                        status_code=404,
                        content={
                            "status": "not_found",
                            "message": f"No se encontró orden de compra con referencia: {referencia_despacho}"
                        },
                        headers={
                            "X-Source": source,
                            "X-Endpoint": "INTEGRAR-SAP"
                        }
                    )
                
                oc_id = oc_pendiente.get("oc_id")
                estado_oc = oc_pendiente.get("estado")
                
                # Verificar que la OC esté en estado PENDIENTE
                if estado_oc != "PENDIENTE":
                    conn.close()
                    logger.warning(f"⚠️ OC {oc_id} no está en estado PENDIENTE (estado actual: {estado_oc})")
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": f"La OC con referencia {referencia_despacho} no está en estado PENDIENTE (estado actual: {estado_oc})",
                            "oc_id": oc_id,
                            "estado_actual": estado_oc
                        },
                        headers={
                            "X-Source": source,
                            "X-Endpoint": "INTEGRAR-SAP"
                        }
                    )
                
                # Para referencia específica, no calculamos total_pendientes
                total_pendientes = None
                
            else:
                # Obtener la primera ODC pendiente (comportamiento por defecto)
                ocs_pendientes = oc_repo.get_by_estado("PENDIENTE")
                
                if not ocs_pendientes:
                    conn.close()
                    logger.info("ℹ️ No hay órdenes de compra pendientes de enviar a SAP")
                    return JSONResponse(
                        status_code=200,
                        content={
                            "status": "success",
                            "message": "No hay órdenes de compra pendientes de enviar a SAP",
                            "metadata": {
                                "total_pendientes": 0,
                                "enviadas": 0,
                                "errores": 0,
                                "pendientes_restantes": 0,
                                "detalles": []
                            }
                        },
                        headers={
                            "X-Source": source,
                            "X-Endpoint": "INTEGRAR-SAP"
                        }
                    )
                
                # Tomar solo la primera ODC pendiente
                oc_pendiente = ocs_pendientes[0]
                oc_id = oc_pendiente.get("oc_id")
                total_pendientes = len(ocs_pendientes)
            
            if oc_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="No se pudo obtener oc_id de la ODC pendiente"
                )
            
            logger.info(f"📤 Enviando ODC a SAP Service Layer...")
            logger.info(f"   ODC seleccionada: {oc_id}")
            if referencia_despacho:
                logger.info(f"   Referencia despacho: {referencia_despacho}")
            if total_pendientes is not None:
                logger.info(f"   Total pendientes restantes: {total_pendientes - 1}")
            logger.info("=" * 70)
            
            # Enviar solo esta ODC
            resultado = oc_sap_service.enviar_oc_a_sap(
                oc_repo=oc_repo,
                oc_id=oc_id,
                warehouse_code=None  # Se puede agregar como parámetro opcional en el futuro
            )
            
            conn.close()
            
            # Preparar respuesta
            success = resultado.get("success", False)
            error = resultado.get("error")
            doc_entry = resultado.get("doc_entry")
            doc_num = resultado.get("doc_num")
            
            # Determinar status y mensaje
            if success:
                status_general = "success"
                mensaje = f"ODC enviada exitosamente a SAP (DocNum: {doc_num})"
                status_code = 200
            else:
                status_general = "error"
                mensaje = f"Error al enviar ODC a SAP: {error}"
                status_code = 500
            
            logger.info("=" * 70)
            logger.info(f"✅ INTEGRAR-SAP completado:")
            logger.info(f"   ODC procesada: {oc_id}")
            if referencia_despacho:
                logger.info(f"   Referencia despacho: {referencia_despacho}")
            logger.info(f"   Resultado: {'✅ Enviada' if success else '❌ Error'}")
            if success:
                logger.info(f"   DocEntry: {doc_entry}, DocNum: {doc_num}")
            else:
                logger.info(f"   Error: {error}")
            if total_pendientes is not None:
                logger.info(f"   Total pendientes restantes: {total_pendientes - 1}")
            logger.info("=" * 70)
            
            # Preparar detalles
            detalles = [{
                "oc_id": oc_id,
                "proveedor": oc_pendiente.get("proveedor"),
                "success": success,
                "doc_entry": doc_entry,
                "doc_num": doc_num,
                "error": error
            }]
            
            # Preparar headers de respuesta
            headers = {
                "X-Source": source,
                "X-Endpoint": "INTEGRAR-SAP",
                "X-OC-Status": status_general,
                "X-OC-ID": oc_id,
            }
            
            if referencia_despacho:
                headers["X-Referencia-Despacho"] = referencia_despacho
            
            if total_pendientes is not None:
                headers["X-Total-Pendientes"] = str(total_pendientes)
                headers["X-Pendientes-Restantes"] = str(total_pendientes - 1)
            
            # Preparar metadata
            metadata = {
                "enviadas": 1 if success else 0,
                "errores": 1 if not success else 0,
                "detalles": detalles
            }
            
            if total_pendientes is not None:
                metadata["total_pendientes"] = total_pendientes
                metadata["pendientes_restantes"] = total_pendientes - 1
            
            if referencia_despacho:
                metadata["referencia_despacho"] = referencia_despacho
            
            # Retornar respuesta
            return JSONResponse(
                status_code=status_code,
                content={
                    "status": status_general,
                    "message": mensaje,
                    "metadata": metadata
                },
                headers=headers
            )
            
        except Exception as e:
            logger.error(f"❌ Error al integrar con SAP: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al integrar con SAP: {str(e)}"
                },
                headers={
                    "X-Source": source,
                    "X-Endpoint": "INTEGRAR-SAP"
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
    
    
    @app.get("/ordenes-compra")
    async def get_ordenes_compra(
        request: Request,
        estado: Optional[str] = Query(None, description="Filtrar por estado (PENDIENTE, ENVIADA, ERROR)"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.ordenes-compra.view'))
    ):
        """
        Endpoint ORDENES-COMPRA: Obtiene órdenes de compra desde la base de datos.
        
        **Query Parameters:**
        - `estado` (string, opcional) - Filtrar por estado (PENDIENTE, ENVIADA, ERROR)
        
        **Ejemplo:**
        ```
        GET /ordenes-compra?estado=PENDIENTE
        ```
        
        **Respuesta:**
        ```json
        {
          "status": "success",
          "data": [
            {
              "oc_id": "uuid",
              "despacho_id": "uuid",
              "proveedor": "PROVEEDOR001",
              "fecha_generacion": "2025-01-21",
              "estado": "PENDIENTE",
              "numero_oc_sap": null,
              "referencia_despacho": "900125353",
              "created_at": "2025-01-21T12:00:00"
            }
          ],
          "metadata": {
            "count": 10,
            "estado_filter": "PENDIENTE"
          }
        }
        ```
        
        Returns:
            JSON con órdenes de compra y metadata
        """
        source = get_source_from_headers(request)
        
        logger.info("=" * 70)
        logger.info(f"📋 GET /ordenes-compra: Consulta ejecutada a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"Filtro estado: {estado or 'Todos'}")
        logger.info("=" * 70)
        
        try:
            conn = get_db_connection()
            oc_repo = OrdenCompraRepository(conn)
            
            if estado:
                # Obtener OCs por estado
                oc_list = oc_repo.get_by_estado(estado)
            else:
                # Obtener todas las OCs (usando un estado común o todos)
                # Por ahora, obtenemos todas las pendientes como default
                oc_list = oc_repo.get_by_estado("PENDIENTE")
                # TODO: Agregar método para obtener todas las OCs sin filtro de estado
            
            conn.close()
            
            response_data = {
                "status": "success",
                "data": oc_list,
                "metadata": {
                    "count": len(oc_list),
                    "estado_filter": estado or "PENDIENTE"
                }
            }
            
            logger.info(f"✅ GET /ordenes-compra: {len(oc_list)} órdenes encontradas")
            
            return JSONResponse(
                status_code=200,
                content=response_data,
                headers={
                    "X-Source": source,
                    "X-Endpoint": "ORDENES-COMPRA",
                    "X-Count": str(len(oc_list))
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Error al obtener órdenes de compra: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al obtener órdenes de compra: {str(e)}"
                }
            )
