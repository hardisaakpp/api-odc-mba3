"""
Endpoints FastAPI para la API de consultas MBA3.

Esta versión usa servicios y helpers para separar la lógica de negocio.
"""

import logging
import uuid
from datetime import datetime

from fastapi import Request, Query as FastAPIQuery, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List

from models import HealthResponse
from services.mba3_service import MBA3Service
from utils import get_source_from_headers
from database.services.sap_service import SAPService
from database.clients.sap_client import SAPClient
from database.repositories.despacho_repository import DespachoRepository
from database.repositories.orden_compra_repository import OrdenCompraRepository
from database.repositories.sap_integration_log_repository import SAPIntegrationLogRepository
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
    
    @app.get("/health", response_model=HealthResponse, tags=["Sistema"])
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
    
    
    @app.get("/facturas", tags=["Consultas MBA3"])
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
    
    
    @app.get("/consultar", tags=["Consultas MBA3"])
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
    
    
    @app.get("/migrar", tags=["Consultas MBA3"])
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
            
            # Normalizar resultado: asegurar que siempre sea una lista o dict válido
            if result is None:
                logger.warning("⚠️ La consulta retornó None. Usando lista vacía.")
                result = []
            elif not isinstance(result, (list, dict)):
                logger.warning(f"⚠️ Tipo de resultado inesperado: {type(result)}. Convirtiendo a lista.")
                result = [result] if result else []
            
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
                else:
                    logger.warning("   ⚠️ La lista está vacía")
            elif isinstance(result, dict):
                logger.info(f"   Tipo: Diccionario")
                campos = list(result.keys())
                logger.info(f"   Campos: {campos}")
            logger.info("=" * 70)
            
            # Guardar en SQL Server (despacho_cabecera/detalle)
            # upsert=True: Actualiza si existe, inserta si no existe
            logger.info("💾 Guardando en despacho_cabecera/detalle...")
            save_status = None
            try:
                save_status = MBA3Service.save_to_database(result, upsert=True)
            except Exception as save_error:
                # Si hay un error al guardar, registrarlo pero no afectar la respuesta
                logger.error(f"❌ Error al intentar guardar en SQL Server (no afecta la respuesta): {save_error}", exc_info=True)
                save_status = {
                    "status": "error",
                    "message": f"Error al guardar en SQL Server: {str(save_error)}",
                    "facturas_guardadas": 0,
                    "facturas_actualizadas": 0,
                    "total_detalles": 0,
                    "errors": [str(save_error)]
                }
            
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
            
            # Preparar respuesta con metadata - asegurar formato consistente
            response_content = {
                "status": "success",
                "data": result if result else [],  # Datos de MBA3, siempre lista o dict
                "metadata": {
                    "query": query_predefinida,
                    "count": len(result) if isinstance(result, list) else (1 if isinstance(result, dict) and result else 0),
                    "save_status": save_status if save_status else {
                        "status": "disabled",
                        "message": "Guardado no disponible",
                        "facturas_guardadas": 0,
                        "facturas_actualizadas": 0,
                        "total_detalles": 0
                    }
                }
            }
            
            logger.info("=" * 70)
            logger.info(f"✅ MIGRAR completado:")
            if save_status:
                logger.info(f"   Facturas guardadas: {save_status.get('facturas_guardadas', 0)}")
                logger.info(f"   Facturas actualizadas: {save_status.get('facturas_actualizadas', 0)}")
                logger.info(f"   Total detalles: {save_status.get('total_detalles', 0)}")
            logger.info(f"   Total registros: {response_content['metadata']['count']}")
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
                    "message": "No se pudo conectar al servidor MBA3",
                    "detail": str(e),
                    "type": "connection_error",
                    "hint": "Verifica que el servidor MBA3 esté disponible y accesible. Revisa la configuración de MBA3_BASE_URL en tu archivo .env",
                    "data": [],  # Asegurar que data siempre esté presente
                    "metadata": {
                        "query": query_predefinida,
                        "save_status": {
                            "status": "error",
                            "message": "No se pudo conectar a MBA3",
                            "facturas_guardadas": 0,
                            "facturas_actualizadas": 0,
                            "total_detalles": 0
                        }
                    }
                }
            )
        except MBA3QueryError as e:
            logger.error(f"❌ Error al ejecutar consulta en MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": "Error al ejecutar consulta en MBA3",
                    "detail": str(e),
                    "type": "query_error",
                    "data": [],  # Asegurar que data siempre esté presente
                    "metadata": {
                        "query": query_predefinida,
                        "save_status": {
                            "status": "error",
                            "message": "No se pudo ejecutar la consulta",
                            "facturas_guardadas": 0,
                            "facturas_actualizadas": 0,
                            "total_detalles": 0
                        }
                    }
                }
            )
        except Exception as e:
            logger.error(f"❌ Error al ejecutar migración: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al ejecutar migración: {str(e)}",
                    "detail": str(e),
                    "type": "internal_error",
                    "data": [],  # Asegurar que data siempre esté presente
                    "metadata": {
                        "query": query_predefinida,
                        "save_status": {
                            "status": "error",
                            "message": "Error interno del servidor",
                            "facturas_guardadas": 0,
                            "facturas_actualizadas": 0,
                            "total_detalles": 0
                        }
                    }
                }
            )
    
    
    @app.get("/pruebas", tags=["Pruebas"])
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
        logger.info(f"🔍 Ejecutando consulta de pruebas (usuario: {username}, fuente: {source})")
        
        try:
            # Ejecutar consulta usando el servicio
            result = MBA3Service.execute_query(query_predefinida)
            
            # Log resumido de la respuesta
            if isinstance(result, list):
                logger.info(f"✅ Consulta completada: {len(result)} registros obtenidos")
            elif isinstance(result, dict):
                logger.info(f"✅ Consulta completada: resultado tipo diccionario")
            else:
                logger.warning(f"⚠️ Tipo inesperado: {type(result)}")
            
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
    
    
    @app.get("/procesar-oc", tags=["Procesamiento"])
    async def procesar_orden_compra(
        request: Request,
        despacho_id: Optional[List[str]] = Query(None, description="UUID(s) del despacho a procesar. Puede especificarse múltiples veces (ej: ?despacho_id=xxx&despacho_id=yyy). Si no se proporciona, procesa todos los despachos sin OC."),
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
        
        **Modo de uso:**
        1. **Sin parámetros**: Procesa TODOS los despachos sin OC
           ```
           GET /procesar-oc
           ```
        
        2. **Con un despacho_id**: Procesa solo un despacho específico
           ```
           GET /procesar-oc?despacho_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325
           ```
        
        3. **Con múltiples despacho_id**: Procesa varios despachos seleccionados
           ```
           GET /procesar-oc?despacho_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325&despacho_id=ABC123-DEF456-GHI789
           ```
        
        **Query Parameters:**
        - `despacho_id` (string, opcional, múltiple) - UUID del despacho. Puede especificarse múltiples veces.
        
        **Características:**
        - ✅ Busca despachos en despacho_cabecera que NO tienen OC asociada (modo todos)
        - ✅ Permite procesar despachos específicos seleccionados (modo selectivo)
        - ✅ Copia cada despacho a orden_compra_cabecera/detalle
        - ✅ Mapea empresa → proveedor desde tabla cliente
        - ✅ Usa upsert: actualiza si existe OC, crea si no existe
        - ✅ Crea las ODC con estado "PENDIENTE" (listas para enviar a SAP)
        
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
        
        try:
            # Obtener conexión y repositorios
            conn = get_db_connection()
            despacho_repo = DespachoRepository(conn)
            oc_repo = OrdenCompraRepository(conn)
            
            # Determinar qué despachos procesar
            if despacho_id:
                # Modo: Procesar despachos específicos
                despacho_ids_list = [id.strip() for id in despacho_id if id and id.strip()]
                logger.info(f"📋 Modo: Procesar despachos específicos ({len(despacho_ids_list)} despachos)")
                logger.info(f"   IDs: {despacho_ids_list}")
                
                # Validar que los despachos existan
                despachos_a_procesar = []
                despachos_no_encontrados = []
                
                for despacho_id_item in despacho_ids_list:
                    # Verificar que el despacho existe
                    cabecera = despacho_repo.get_existing_cabecera(despacho_id_item)
                    if not cabecera:
                        logger.warning(f"⚠️ Despacho {despacho_id_item} no encontrado, se omitirá")
                        despachos_no_encontrados.append(despacho_id_item)
                        continue
                    
                    # Verificar si ya tiene OC (solo informativo)
                    existing_oc_id = oc_repo.find_by_despacho_id(despacho_id_item)
                    if existing_oc_id:
                        logger.info(f"ℹ️ Despacho {despacho_id_item} ya tiene OC ({existing_oc_id}), se actualizará")
                    
                    despachos_a_procesar.append(despacho_id_item)
                
                if not despachos_a_procesar:
                    conn.close()
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "No se encontraron despachos válidos para procesar",
                            "despacho_ids_provistos": despacho_ids_list,
                            "despachos_no_encontrados": despachos_no_encontrados,
                            "oc_creadas": 0,
                            "oc_errores": 0
                        },
                        headers={
                            "X-Source": source,
                            "X-Endpoint": "PROCESAR-OC"
                        }
                    )
                
                if despachos_no_encontrados:
                    logger.warning(f"⚠️ {len(despachos_no_encontrados)} despachos no encontrados: {despachos_no_encontrados}")
            else:
                # Modo: Procesar todos los despachos sin OC (comportamiento original)
                logger.info("📋 Modo: Procesar todos los despachos sin OC")
                despachos_a_procesar = despacho_repo.get_despachos_sin_oc()
                despachos_no_encontrados = []
                
                if not despachos_a_procesar:
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
            
            logger.info(f"📦 Total despachos a procesar: {len(despachos_a_procesar)}")
            logger.info("=" * 70)
            logger.info("🔄 PROCESANDO: Copiando despachos a orden de compra...")
            logger.info("=" * 70)
            
            # Procesar cada despacho
            oc_resultados = []
            oc_exitosas = 0
            oc_errores = 0
            
            for idx, despacho_id_item in enumerate(despachos_a_procesar, 1):
                try:
                    logger.info(f"[{idx}/{len(despachos_a_procesar)}] Procesando despacho: {despacho_id_item}")
                    
                    # Copiar despacho a orden de compra (con upsert)
                    oc_resultado = copy_despacho_to_orden_compra(
                        despacho_repo=despacho_repo,
                        oc_repo=oc_repo,
                        despacho_id=despacho_id_item,
                        upsert=True
                    )
                    
                    if oc_resultado:
                        oc_exitosas += 1
                        oc_id = oc_resultado.get("oc_id")
                        accion = "actualizada" if oc_resultado.get("cabecera_actualizada") else "creada"
                        
                        resultado_item = {
                            "despacho_id": despacho_id_item,
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
                        logger.warning(f"   ⚠️ No se pudo crear/actualizar OC para despacho: {despacho_id_item}")
                        oc_resultados.append({
                            "despacho_id": despacho_id_item,
                            "error": "No se pudo crear/actualizar OC"
                        })
                        
                except Exception as oc_error:
                    oc_errores += 1
                    logger.error(f"   ❌ Error al copiar despacho {despacho_id_item} a OC: {oc_error}")
                    oc_resultados.append({
                        "despacho_id": despacho_id_item,
                        "error": str(oc_error)
                    })
            
            # Cerrar conexión
            conn.close()
            
            oc_status = {
                "status": "success" if oc_errores == 0 else "partial",
                "oc_creadas": oc_exitosas,
                "oc_errores": oc_errores,
                "total_procesadas": len(oc_resultados),
                "total_despachos": len(despachos_a_procesar),
                "detalles": oc_resultados
            }
            
            # Agregar información de despachos no encontrados si aplica
            if despachos_no_encontrados:
                oc_status["despachos_no_encontrados"] = despachos_no_encontrados
            
            logger.info("=" * 70)
            logger.info(f"✅ PROCESAR-OC completado:")
            logger.info(f"   Total despachos procesados: {len(despachos_a_procesar)}")
            logger.info(f"   OCs creadas: {oc_exitosas}")
            logger.info(f"   Errores: {oc_errores}")
            if despachos_no_encontrados:
                logger.info(f"   Despachos no encontrados: {len(despachos_no_encontrados)}")
            logger.info(f"   Estado de OCs creadas: PENDIENTE (listas para enviar a SAP)")
            logger.info("=" * 70)
            
            # Preparar headers de respuesta
            headers = {
                "X-Source": source,
                "X-Endpoint": "PROCESAR-OC",
                "X-OC-Status": oc_status.get("status", "unknown"),
                "X-OC-Creadas": str(oc_exitosas),
                "X-OC-Errores": str(oc_errores),
                "X-Total-Despachos": str(len(despachos_a_procesar))
            }
            
            if despacho_id:
                headers["X-Modo"] = "selectivo"
            else:
                headers["X-Modo"] = "todos"
            
            # Construir mensaje
            mensaje = f"Proceso completado: {oc_exitosas} OCs creadas de {len(despachos_a_procesar)} despachos (estado: PENDIENTE)"
            if despachos_no_encontrados:
                mensaje += f". {len(despachos_no_encontrados)} despachos no encontrados."
            
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
    
    @app.get("/despachos/count", tags=["Procesamiento"])
    async def get_despachos_count(
        request: Request,
        limit: Optional[int] = Query(None, description="Número máximo de registros a retornar (opcional)"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Endpoint para obtener el conteo y información detallada de despachos con sus órdenes de compra.
        
        **Responsabilidad:** Consultar estado (solo lectura)
        
        **Características:**
        - ✅ Cuenta despachos en despacho_cabecera que NO tienen OC asociada
        - ✅ Devuelve información detallada de todas las tablas relacionadas:
          - despacho_cabecera (información de cabecera del despacho)
          - despacho_detalle (líneas de detalle del despacho)
          - orden_compra_cabecera (información de cabecera de OC si existe)
          - orden_compra_detalle (líneas de detalle de OC si existe)
        - ✅ Útil para mostrar información completa en el frontend
        - ✅ Permisos: solo lectura (view), no requiere execute
        
        **Query Parameters:**
        - `limit` (int, opcional) - Número máximo de registros a retornar
        
        **Ejemplo de uso:**
        ```
        GET /despachos/count
        GET /despachos/count?limit=10
        ```
        
        **Respuesta:**
        ```json
        {
          "count": 5,
          "disponible": true,
          "despachos": [
            {
              "despacho_id": "uuid",
              "empresa": "EMPRESA001",
              "numero_factura": "FAC-001",
              "fecha_despacho": "2025-01-21",
              "despacho_detalles": [
                {
                  "detalle_id": "uuid",
                  "sku": "SKU001",
                  "cantidad_docena_mba3": 10,
                  "precio_unitario_mba3": 100.0,
                  "total_linea_mba3": 1000.0
                }
              ],
              "orden_compra_info": {
                "oc_id": "uuid",
                "proveedor": "PROVEEDOR001",
                "estado": "PENDIENTE",
                "numero_oc_sap": null,
                "oc_detalles": [
                  {
                    "oc_detalle_id": "uuid",
                    "sku_sap": "SKU001",
                    "cantidad_sap": 40.0,
                    "precio_unitario": 25.0,
                    "total_linea": 1000.0
                  }
                ]
              }
            }
          ]
        }
        ```
        
        **Nota:** Este endpoint solo consulta el estado, no ejecuta ningún proceso.
        Para procesar los despachos, usar el endpoint GET /procesar-oc.
        
        Returns:
            JSON con conteo, disponibilidad e información detallada de despachos y OCs
        """
        source = get_source_from_headers(request)
        
        try:
            conn = get_db_connection()
            despacho_repo = DespachoRepository(conn)
            oc_repo = OrdenCompraRepository(conn)
            
            # Contar despachos sin OC (misma lógica que usa /procesar-oc)
            count = despacho_repo.count_despachos_sin_oc()
            
            # Obtener información detallada de despachos con sus OCs
            despachos_info = despacho_repo.get_despachos_con_info_oc(limit=limit)
            
            # Agregar detalles de OC para cada despacho que tenga OC
            for despacho in despachos_info:
                if despacho.get("orden_compra_info") and despacho["orden_compra_info"].get("oc_id"):
                    oc_id = despacho["orden_compra_info"]["oc_id"]
                    try:
                        oc_detalles = oc_repo.get_detalles(oc_id)
                        despacho["orden_compra_info"]["oc_detalles"] = oc_detalles
                    except Exception as e:
                        logger.warning(f"⚠️ Error al obtener detalles de OC {oc_id}: {e}")
                        despacho["orden_compra_info"]["oc_detalles"] = []
            
            conn.close()
            
            disponible = count > 0
            
            logger.debug(f"📊 GET /despachos/count: {count} despachos disponibles, {len(despachos_info)} registros retornados")
            
            return JSONResponse(
                status_code=200,
                content={
                    "count": count,
                    "disponible": disponible,
                    "despachos": despachos_info
                },
                headers={
                    "X-Source": source,
                    "X-Endpoint": "DESPACHOS-COUNT",
                    "X-Count": str(count)
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Error al obtener información de despachos: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al obtener información de despachos: {str(e)}",
                    "count": 0,
                    "disponible": False,
                    "despachos": []
                }
            )
    
    @app.get("/despachos/{despacho_id}/detalles", tags=["Procesamiento"])
    async def get_despacho_detalles(
        request: Request,
        despacho_id: str,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Endpoint para obtener los detalles de un despacho específico.
        
        **Responsabilidad:** Consultar estado (solo lectura)
        
        **Características:**
        - ✅ Obtiene todos los detalles (líneas) de un despacho específico
        - ✅ Retorna información completa de cada línea de detalle
        - ✅ Permisos: solo lectura (view), no requiere execute
        
        **Path Parameters:**
        - `despacho_id` (string, requerido) - UUID del despacho
        
        **Ejemplo de uso:**
        ```
        GET /despachos/DD7D7A51-9E57-44D4-9A8F-4A05427A8325/detalles
        ```
        
        **Respuesta:**
        ```json
        {
          "status": "success",
          "despacho_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325",
          "detalles": [
            {
              "detalle_id": "uuid",
              "despacho_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325",
              "sku": "SKU001",
              "cantidad_docena_mba3": 10,
              "subtotal_sap": 1000.0,
              "cantidad_pack_sap": 40.0,
              "unidad_sap": "X3",
              "precio_unitario_mba3": 100.0,
              "descuento": 0.0,
              "total_linea_mba3": 1000.0,
              "impuesto": 0.0,
              "nombre_producto": "Producto Ejemplo",
              "tipo_linea": "GrabarLineasProd",
              "precio_unitario_sap": 25.0
            }
          ],
          "count": 1
        }
        ```
        
        Returns:
            JSON con los detalles del despacho
        """
        source = get_source_from_headers(request)
        
        logger.info("=" * 70)
        logger.info(f"📋 GET /despachos/{despacho_id}/detalles: Consulta ejecutada a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info("=" * 70)
        
        try:
            conn = get_db_connection()
            despacho_repo = DespachoRepository(conn)
            
            # Obtener detalles del despacho
            detalles = despacho_repo.get_detalles(despacho_id)
            
            conn.close()
            
            logger.debug(f"📊 GET /despachos/{despacho_id}/detalles: {len(detalles)} detalles encontrados")
            
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "despacho_id": despacho_id,
                    "detalles": detalles,
                    "count": len(detalles)
                },
                headers={
                    "X-Source": source,
                    "X-Endpoint": "DESPACHO-DETALLES",
                    "X-Despacho-ID": despacho_id,
                    "X-Count": str(len(detalles))
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Error al obtener detalles del despacho {despacho_id}: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al obtener detalles del despacho: {str(e)}",
                    "despacho_id": despacho_id,
                    "detalles": [],
                    "count": 0
                }
            )
    
    @app.post("/integrar-sap", tags=["Integración SAP"])
    async def integrar_sap(
        request: Request,
        oc_id: Optional[List[str]] = Query(None, description="UUID(s) de la(s) orden(es) de compra a enviar. Puede especificarse múltiples veces (ej: ?oc_id=xxx&oc_id=yyy)."),
        referencia_despacho: Optional[List[str]] = Query(None, description="Referencia(s) del despacho (número de factura) para buscar OC(s) específica(s). Puede especificarse múltiples veces (ej: ?referencia_despacho=xxx&referencia_despacho=yyy). Si no se proporciona oc_id ni referencia_despacho, se procesa la primera OC pendiente."),
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
        - ✅ Puede enviar 1 o varios ODC en una sola llamada
        - ✅ Si se proporciona `oc_id`: envía las ODC(s) especificada(s) por UUID
        - ✅ Si se proporciona `referencia_despacho`: busca y envía las ODC(s) por referencia
        - ✅ Si NO se proporciona ningún parámetro: busca y envía la primera ODC pendiente
        - ✅ Convierte cada ODC a formato JSON de SAP Service Layer
        - ✅ Envía cada ODC directamente a SAP Service Layer (sin middleware)
        - ✅ Actualiza estado a "ENVIADA" o "ERROR" según resultado
        - ✅ Retorna información detallada de cada ODC procesada
        
        **Query Parameters:**
        - `oc_id` (opcional, múltiple): UUID de la orden de compra. Puede especificarse múltiples veces.
        - `referencia_despacho` (opcional, múltiple): Número de factura/despacho. Puede especificarse múltiples veces.
        
        **Ejemplos de uso:**
        ```
        # Enviar una OC específica por UUID
        POST /integrar-sap?oc_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325
        
        # Enviar múltiples OC por UUID
        POST /integrar-sap?oc_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325&oc_id=ABC123-DEF456-GHI789
        
        # Buscar OC específica por referencia
        POST /integrar-sap?referencia_despacho=900125353
        
        # Buscar múltiples OC por referencia
        POST /integrar-sap?referencia_despacho=900125353&referencia_despacho=900125354
        
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
        
        # Log del proceso
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"🚀 INTEGRAR-SAP iniciado (usuario: {username}, fuente: {source})")
        
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
            
            # Generar ID único para este proceso
            proceso_id = str(uuid.uuid4())
            
            # Obtener conexión y repositorios
            conn = get_db_connection()
            oc_repo = OrdenCompraRepository(conn)
            log_repo = SAPIntegrationLogRepository(conn)
            
            # Guardar log de inicio
            try:
                log_repo.guardar_log(
                    proceso_id=proceso_id,
                    nivel_log="INFO",
                    mensaje=f"INTEGRAR-SAP iniciado (usuario: {username}, fuente: {source})",
                    usuario=username,
                    fuente=source
                )
            except Exception as e:
                logger.warning(f"No se pudo guardar log de inicio: {e}")
            
            # Guardar log de conexión
            try:
                log_repo.guardar_log(
                    proceso_id=proceso_id,
                    nivel_log="INFO",
                    mensaje="Conexión a SQL Server establecida",
                    usuario=username,
                    fuente=source
                )
            except Exception as e:
                logger.warning(f"No se pudo guardar log de conexión: {e}")
            
            # Inicializar servicio SAP
            oc_sap_service = OCSAPService()
            
            # Determinar qué OC procesar
            oc_ids_a_procesar = []
            referencias_usadas = []
            
            # Normalizar parámetros: convertir string único a lista si es necesario
            # FastAPI debería hacer esto automáticamente, pero por si acaso
            if oc_id and not isinstance(oc_id, list):
                oc_id = [oc_id]
            if referencia_despacho and not isinstance(referencia_despacho, list):
                referencia_despacho = [referencia_despacho]
            
            if oc_id:
                # Modo: Procesar OCs específicas por UUID
                oc_ids_list = [id.strip() for id in oc_id if id and id.strip()]
                logger.info(f"📋 Procesando {len(oc_ids_list)} OCs por UUID")
                
                # Validar que las OCs existan y estén en estado PENDIENTE
                for oc_id_item in oc_ids_list:
                    oc_cabecera = oc_repo.get_existing_cabecera(oc_id_item)
                    if not oc_cabecera:
                        logger.warning(f"⚠️ OC {oc_id_item[:8]}... no encontrada, omitiendo")
                        continue
                    
                    estado_actual = oc_cabecera.get("estado")
                    if estado_actual != "PENDIENTE":
                        logger.warning(f"⚠️ OC {oc_id_item[:8]}... no está en estado PENDIENTE (estado: {estado_actual}), omitiendo")
                        continue
                    
                    oc_ids_a_procesar.append(oc_id_item)
                
                if not oc_ids_a_procesar:
                    conn.close()
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "No se encontraron OCs válidas para procesar",
                            "oc_ids_provistos": oc_ids_list,
                            "enviadas": 0,
                            "errores": 0
                        },
                        headers={
                            "X-Source": source,
                            "X-Endpoint": "INTEGRAR-SAP"
                        }
                    )
            
            elif referencia_despacho:
                # Modo: Procesar OCs específicas por referencia
                referencias_list = [ref.strip() for ref in referencia_despacho if ref and ref.strip()]
                logger.info(f"📋 Procesando OCs por referencia ({len(referencias_list)} referencias)")
                
                # Buscar OCs por referencia
                for referencia in referencias_list:
                    oc_encontrada = oc_repo.find_by_referencia_despacho(referencia)
                    if not oc_encontrada:
                        logger.warning(f"⚠️ No se encontró OC con referencia: {referencia}")
                        continue
                    
                    oc_id_encontrado = oc_encontrada.get("oc_id")
                    estado_actual = oc_encontrada.get("estado")
                    
                    if estado_actual != "PENDIENTE":
                        logger.warning(f"⚠️ OC con ref {referencia} no está en estado PENDIENTE (estado: {estado_actual})")
                        continue
                    
                    oc_ids_a_procesar.append(oc_id_encontrado)
                    referencias_usadas.append(referencia)
                
                if not oc_ids_a_procesar:
                    conn.close()
                    return JSONResponse(
                        status_code=404,
                        content={
                            "status": "not_found",
                            "message": "No se encontraron OCs válidas con las referencias proporcionadas",
                            "referencias_provistas": referencias_list,
                            "enviadas": 0,
                            "errores": 0
                        },
                        headers={
                            "X-Source": source,
                            "X-Endpoint": "INTEGRAR-SAP"
                        }
                    )
            
            else:
                # Modo: Procesar primera OC pendiente (comportamiento por defecto)
                logger.info("📋 Procesando primera OC pendiente")
                ocs_pendientes = oc_repo.get_by_estado("PENDIENTE")
                
                if not ocs_pendientes:
                    conn.close()
                    logger.info("ℹ️ No hay OCs pendientes")
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
                oc_id_primera = oc_pendiente.get("oc_id")
                if oc_id_primera:
                    oc_ids_a_procesar = [oc_id_primera]
            
            logger.info(f"📦 Procesando {len(oc_ids_a_procesar)} OCs...")
            
            # Guardar log de procesamiento
            try:
                log_repo.guardar_log(
                    proceso_id=proceso_id,
                    nivel_log="INFO",
                    mensaje=f"Procesando {len(oc_ids_a_procesar)} OCs...",
                    usuario=username,
                    fuente=source
                )
            except Exception as e:
                logger.warning(f"No se pudo guardar log de procesamiento: {e}")
            
            # Procesar cada ODC
            detalles = []
            enviadas = 0
            errores = 0
            
            for idx, oc_id_item in enumerate(oc_ids_a_procesar, 1):
                try:
                    # Obtener información de la OC para el log y respuesta
                    oc_info = oc_repo.get_existing_cabecera(oc_id_item)
                    proveedor = oc_info.get("proveedor") if oc_info else "UNKNOWN"
                    referencia = oc_info.get("referencia_despacho") if oc_info else None
                    
                    # Guardar log de inicio de procesamiento de OC
                    try:
                        log_repo.guardar_log(
                            proceso_id=proceso_id,
                            nivel_log="INFO",
                            mensaje=f"Procesando ODC {oc_id_item[:8]}...",
                            usuario=username,
                            fuente=source,
                            oc_id=oc_id_item,
                            proveedor=proveedor,
                            referencia_despacho=referencia
                        )
                    except Exception as e:
                        logger.warning(f"No se pudo guardar log de OC: {e}")
                    
                    # Enviar ODC a SAP
                    resultado = oc_sap_service.enviar_oc_a_sap(
                        oc_repo=oc_repo,
                        oc_id=oc_id_item,
                        warehouse_code=None  # Se puede agregar como parámetro opcional en el futuro
                    )
                    
                    success = resultado.get("success", False)
                    error = resultado.get("error")
                    doc_entry = resultado.get("doc_entry")
                    doc_num = resultado.get("doc_num")
                    sap_response = resultado.get("sap_response")  # Respuesta completa de SAP
                    error_code = resultado.get("error_code")  # Código de error de SAP
                    error_source = resultado.get("error_source")  # Origen del error (SAP, BACKEND, etc.)
                    sap_error_details = resultado.get("sap_error_details")  # Detalles completos del error de SAP
                    
                    # Guardar log de resultado
                    try:
                        if success:
                            log_repo.guardar_log(
                                proceso_id=proceso_id,
                                nivel_log="INFO",
                                mensaje=f"ODC {oc_id_item[:8]}... enviada exitosamente: DocNum={doc_num}",
                                usuario=username,
                                fuente=source,
                                oc_id=oc_id_item,
                                proveedor=proveedor,
                                referencia_despacho=referencia,
                                doc_entry=doc_entry,
                                doc_num=doc_num,
                                success=True,
                                detalles_adicionales={"sap_response": sap_response} if sap_response else None
                            )
                        else:
                            log_repo.guardar_log(
                                proceso_id=proceso_id,
                                nivel_log="ERROR",
                                mensaje=f"Error ODC {oc_id_item[:8]}...: {error}",
                                usuario=username,
                                fuente=source,
                                oc_id=oc_id_item,
                                proveedor=proveedor,
                                referencia_despacho=referencia,
                                error_code=error_code,
                                error_source=error_source,
                                success=False,
                                detalles_adicionales={"sap_error_details": sap_error_details} if sap_error_details else None
                            )
                    except Exception as e:
                        logger.warning(f"No se pudo guardar log de resultado: {e}")
                    
                    # Preparar detalle con información completa
                    detalle_resultado = {
                        "oc_id": oc_id_item,
                        "proveedor": proveedor,
                        "success": success,
                        "doc_entry": doc_entry,
                        "doc_num": doc_num,
                        "error": error,
                        "error_message": error,  # Alias para compatibilidad con frontend
                        "error_code": error_code,  # Código de error de SAP (ej: -4013)
                        "error_source": error_source,  # Origen: "SAP", "BACKEND", "SAP_CONNECTION", o None si éxito
                        "sap_response": sap_response,  # Respuesta completa de SAP (éxito)
                        "sap_error_details": sap_error_details  # Detalles del error de SAP (si aplica)
                    }
                    
                    # Agregar referencia si está disponible
                    if referencia:
                        detalle_resultado["referencia_despacho"] = referencia
                    
                    detalles.append(detalle_resultado)
                    
                    if success:
                        enviadas += 1
                    else:
                        errores += 1
                        logger.error(f"❌ Error ODC {oc_id_item[:8]}...: {error}")
                        
                except Exception as e:
                    errores += 1
                    logger.error(f"❌ Error al procesar ODC {oc_id_item[:8]}...: {e}", exc_info=True)
                    
                    # Guardar log de error excepcional
                    try:
                        log_repo.guardar_log(
                            proceso_id=proceso_id,
                            nivel_log="ERROR",
                            mensaje=f"Error al procesar ODC {oc_id_item[:8]}...: {str(e)}",
                            usuario=username,
                            fuente=source,
                            oc_id=oc_id_item,
                            proveedor=proveedor if 'proveedor' in locals() else "UNKNOWN",
                            error_source="BACKEND",
                            success=False
                        )
                    except Exception:
                        pass
                    
                    detalles.append({
                        "oc_id": oc_id_item,
                        "proveedor": proveedor if 'proveedor' in locals() else "UNKNOWN",
                        "success": False,
                        "doc_entry": None,
                        "doc_num": None,
                        "error": str(e),
                        "error_message": str(e),  # Alias para compatibilidad con frontend
                        "error_code": None,
                        "error_source": "BACKEND",
                        "sap_response": None,
                        "sap_error_details": None
                    })
            
            conn.close()
            
            # Determinar status general
            status_general = "success" if errores == 0 else "partial"
            if enviadas == 0:
                status_general = "error"
            
            # Preparar mensaje
            if len(oc_ids_a_procesar) == 1:
                if enviadas > 0:
                    mensaje = f"ODC enviada exitosamente a SAP"
                    if detalles[0].get("doc_num"):
                        mensaje += f" (DocNum: {detalles[0].get('doc_num')})"
                else:
                    mensaje = f"Error al enviar ODC a SAP: {detalles[0].get('error', 'Error desconocido')}"
            else:
                mensaje = f"Proceso completado: {enviadas} ODC(s) enviada(s), {errores} error(es) de {len(oc_ids_a_procesar)} procesada(s)"
            
            logger.info(f"✅ INTEGRAR-SAP completado: {enviadas} enviadas, {errores} errores de {len(oc_ids_a_procesar)} procesadas")
            
            # Guardar log de finalización
            try:
                log_repo.guardar_log(
                    proceso_id=proceso_id,
                    nivel_log="INFO",
                    mensaje=f"INTEGRAR-SAP completado: {enviadas} enviadas, {errores} errores de {len(oc_ids_a_procesar)} procesadas",
                    usuario=username,
                    fuente=source
                )
            except Exception as e:
                logger.warning(f"No se pudo guardar log de finalización: {e}")
            
            # Preparar headers de respuesta
            headers = {
                "X-Source": source,
                "X-Endpoint": "INTEGRAR-SAP",
                "X-OC-Status": status_general,
                "X-Enviadas": str(enviadas),
                "X-Errores": str(errores),
                "X-Total-Procesadas": str(len(oc_ids_a_procesar))
            }
            
            # Preparar metadata
            metadata = {
                "enviadas": enviadas,
                "errores": errores,
                "total_procesadas": len(oc_ids_a_procesar),
                "detalles": detalles
            }
            
            if referencias_usadas:
                metadata["referencias_usadas"] = referencias_usadas
            
            # Si no se especificaron OCs, calcular pendientes restantes
            if not oc_id and not referencia_despacho:
                # Obtener total pendientes (sin contar las que acabamos de procesar)
                conn = get_db_connection()
                oc_repo_temp = OrdenCompraRepository(conn)
                ocs_pendientes_restantes = oc_repo_temp.get_by_estado("PENDIENTE")
                conn.close()
                total_pendientes = len(ocs_pendientes_restantes)
                metadata["total_pendientes"] = total_pendientes
                metadata["pendientes_restantes"] = total_pendientes
                headers["X-Total-Pendientes"] = str(total_pendientes)
                headers["X-Pendientes-Restantes"] = str(total_pendientes)
            
            # Retornar respuesta
            # Siempre retornamos 200 con información del error en el contenido
            # El status_code 500 se reserva solo para errores inesperados del servidor
            # Los errores de validación (como ODC sin detalles) se reportan con 200 y status: "error"
            status_code = 200
            
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
    
    
    @app.get("/historial-ordenes", tags=["Historial"])
    async def get_historial_ordenes(
        request: Request,
        oc_id: Optional[str] = Query(None, description="Filtrar por UUID de orden de compra"),
        referencia_despacho: Optional[str] = Query(None, description="Filtrar por referencia de despacho"),
        proveedor: Optional[str] = Query(None, description="Filtrar por código de proveedor"),
        fecha_desde: Optional[str] = Query(None, description="Filtrar desde fecha (YYYY-MM-DD)"),
        fecha_hasta: Optional[str] = Query(None, description="Filtrar hasta fecha (YYYY-MM-DD)"),
        nivel_log: Optional[str] = Query(None, description="Filtrar por nivel (INFO, ERROR, WARNING)"),
        success: Optional[bool] = Query(None, description="Filtrar por éxito (true) o error (false)"),
        limit: Optional[int] = Query(50, description="Límite de registros por página"),
        offset: Optional[int] = Query(0, description="Offset para paginación"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """
        Endpoint HISTORIAL-ORDENES: Obtiene el historial de integración de órdenes de compra con SAP.
        
        ⭐ **Recomendado para Frontend**
        
        Este endpoint permite consultar el historial completo de integraciones con SAP,
        incluyendo éxitos, errores y detalles de cada proceso.
        
        **Query Parameters:**
        - `oc_id` (string, opcional) - Filtrar por UUID de orden de compra
        - `referencia_despacho` (string, opcional) - Filtrar por referencia de despacho
        - `proveedor` (string, opcional) - Filtrar por código de proveedor
        - `fecha_desde` (string, opcional) - Filtrar desde fecha (YYYY-MM-DD)
        - `fecha_hasta` (string, opcional) - Filtrar hasta fecha (YYYY-MM-DD)
        - `nivel_log` (string, opcional) - Filtrar por nivel (INFO, ERROR, WARNING)
        - `success` (boolean, opcional) - Filtrar por éxito (true) o error (false)
        - `limit` (int, default: 50) - Límite de registros por página
        - `offset` (int, default: 0) - Offset para paginación
        
        **Ejemplo:**
        ```
        GET /historial-ordenes?proveedor=P1790389219001&limit=20&offset=0
        GET /historial-ordenes?fecha_desde=2025-12-01&fecha_hasta=2025-12-03&success=true
        ```
        
        **Respuesta:**
        ```json
        {
          "status": "success",
          "data": [
            {
              "log_id": "uuid",
              "timestamp_log": "2025-12-03T13:33:48.722",
              "nivel_log": "INFO",
              "mensaje": "ODC 806A24F6... enviada exitosamente: DocNum=16952",
              "oc_id": "uuid",
              "referencia_despacho": "900126807",
              "proveedor": "P1790389219001",
              "doc_entry": 31893,
              "doc_num": 16952,
              "success": true,
              "usuario": "admin",
              "fuente": "API"
            }
          ],
          "metadata": {
            "total": 150,
            "limit": 50,
            "offset": 0,
            "has_more": true
          }
        }
        ```
        
        Returns:
            JSON con historial de órdenes y metadata de paginación
        """
        source = get_source_from_headers(request)
        
        try:
            conn = get_db_connection()
            log_repo = SAPIntegrationLogRepository(conn)
            
            # Parsear fechas si se proporcionan
            fecha_desde_dt = None
            fecha_hasta_dt = None
            
            if fecha_desde:
                try:
                    fecha_desde_dt = datetime.strptime(fecha_desde, "%Y-%m-%d")
                except ValueError:
                    conn.close()
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "Formato de fecha_desde inválido. Use YYYY-MM-DD"
                        }
                    )
            
            if fecha_hasta:
                try:
                    fecha_hasta_dt = datetime.strptime(fecha_hasta, "%Y-%m-%d")
                    # Agregar 23:59:59 para incluir todo el día
                    fecha_hasta_dt = fecha_hasta_dt.replace(hour=23, minute=59, second=59)
                except ValueError:
                    conn.close()
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "Formato de fecha_hasta inválido. Use YYYY-MM-DD"
                        }
                    )
            
            # Obtener historial
            result = log_repo.get_historial_ordenes(
                oc_id=oc_id,
                referencia_despacho=referencia_despacho,
                proveedor=proveedor,
                fecha_desde=fecha_desde_dt,
                fecha_hasta=fecha_hasta_dt,
                nivel_log=nivel_log,
                success=success,
                limit=limit,
                offset=offset
            )
            
            conn.close()
            
            # Preparar respuesta
            has_more = (offset or 0) + len(result["data"]) < result["total"]
            
            response_data = {
                "status": "success",
                "data": result["data"],
                "metadata": {
                    "total": result["total"],
                    "limit": limit or 50,
                    "offset": offset or 0,
                    "has_more": has_more
                }
            }
            
            logger.info(f"✅ GET /historial-ordenes: {len(result['data'])} registros encontrados (total: {result['total']})")
            
            return JSONResponse(
                status_code=200,
                content=response_data,
                headers={
                    "X-Source": source,
                    "X-Endpoint": "HISTORIAL-ORDENES",
                    "X-Total": str(result["total"])
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Error al obtener historial de órdenes: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al obtener historial de órdenes: {str(e)}"
                },
                headers={
                    "X-Source": source,
                    "X-Endpoint": "HISTORIAL-ORDENES"
                }
            )
    
    
    @app.get("/sap/test", tags=["Integración SAP"])
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
    
    
    @app.get("/sap/test/direct", tags=["Integración SAP"])
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
    
    
    @app.get("/ordenes-compra", tags=["Órdenes de Compra"])
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
    
    
    @app.get("/ordenes-compra/logs", tags=["Órdenes de Compra"])
    async def get_ordenes_compra_logs(
        request: Request,
        page: Optional[int] = Query(1, description="Número de página (empezando en 1)"),
        pageSize: Optional[int] = Query(50, description="Tamaño de página (registros por página)"),
        oc_id: Optional[str] = Query(None, description="Filtrar por UUID de orden de compra"),
        referencia_despacho: Optional[str] = Query(None, description="Filtrar por referencia de despacho"),
        proveedor: Optional[str] = Query(None, description="Filtrar por código de proveedor"),
        fecha_desde: Optional[str] = Query(None, description="Filtrar desde fecha (YYYY-MM-DD)"),
        fecha_hasta: Optional[str] = Query(None, description="Filtrar hasta fecha (YYYY-MM-DD)"),
        nivel_log: Optional[str] = Query(None, description="Filtrar por nivel (INFO, ERROR, WARNING)"),
        success: Optional[bool] = Query(None, description="Filtrar por éxito (true) o error (false)"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.ordenes-compra.view'))
    ):
        """
        Endpoint ORDENES-COMPRA/LOGS: Obtiene el historial de logs de integración de órdenes de compra con SAP.
        
        ⭐ **Endpoint para Frontend - Historial de Órdenes**
        
        Este endpoint permite consultar el historial completo de integraciones con SAP,
        usando paginación basada en página (page/pageSize) en lugar de offset/limit.
        
        **Query Parameters:**
        - `page` (int, default: 1) - Número de página (empezando en 1)
        - `pageSize` (int, default: 50) - Tamaño de página (registros por página)
        - `oc_id` (string, opcional) - Filtrar por UUID de orden de compra
        - `referencia_despacho` (string, opcional) - Filtrar por referencia de despacho
        - `proveedor` (string, opcional) - Filtrar por código de proveedor
        - `fecha_desde` (string, opcional) - Filtrar desde fecha (YYYY-MM-DD)
        - `fecha_hasta` (string, opcional) - Filtrar hasta fecha (YYYY-MM-DD)
        - `nivel_log` (string, opcional) - Filtrar por nivel (INFO, ERROR, WARNING)
        - `success` (boolean, opcional) - Filtrar por éxito (true) o error (false)
        
        **Ejemplo:**
        ```
        GET /ordenes-compra/logs?page=1&pageSize=100
        GET /ordenes-compra/logs?proveedor=P1790389219001&page=1&pageSize=50
        GET /ordenes-compra/logs?fecha_desde=2025-12-01&fecha_hasta=2025-12-03&success=true
        ```
        
        **Respuesta:**
        ```json
        {
          "status": "success",
          "data": [
            {
              "log_id": "uuid",
              "timestamp_log": "2025-12-03T13:33:48.722",
              "nivel_log": "INFO",
              "mensaje": "ODC 806A24F6... enviada exitosamente: DocNum=16952",
              "oc_id": "uuid",
              "referencia_despacho": "900126807",
              "proveedor": "P1790389219001",
              "doc_entry": 31893,
              "doc_num": 16952,
              "success": true,
              "usuario": "admin",
              "fuente": "API"
            }
          ],
          "metadata": {
            "total": 150,
            "page": 1,
            "pageSize": 50,
            "totalPages": 3,
            "has_more": true
          }
        }
        ```
        
        Returns:
            JSON con historial de logs de órdenes y metadata de paginación
        """
        source = get_source_from_headers(request)
        
        try:
            conn = get_db_connection()
            log_repo = SAPIntegrationLogRepository(conn)
            
            # Convertir page/pageSize a offset/limit
            page_num = page or 1
            page_size = pageSize or 50
            offset = (page_num - 1) * page_size
            limit = page_size
            
            # Parsear fechas si se proporcionan
            fecha_desde_dt = None
            fecha_hasta_dt = None
            
            if fecha_desde:
                try:
                    fecha_desde_dt = datetime.strptime(fecha_desde, "%Y-%m-%d")
                except ValueError:
                    conn.close()
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "Formato de fecha_desde inválido. Use YYYY-MM-DD"
                        }
                    )
            
            if fecha_hasta:
                try:
                    fecha_hasta_dt = datetime.strptime(fecha_hasta, "%Y-%m-%d")
                    # Agregar 23:59:59 para incluir todo el día
                    fecha_hasta_dt = fecha_hasta_dt.replace(hour=23, minute=59, second=59)
                except ValueError:
                    conn.close()
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "Formato de fecha_hasta inválido. Use YYYY-MM-DD"
                        }
                    )
            
            # Obtener historial
            result = log_repo.get_historial_ordenes(
                oc_id=oc_id,
                referencia_despacho=referencia_despacho,
                proveedor=proveedor,
                fecha_desde=fecha_desde_dt,
                fecha_hasta=fecha_hasta_dt,
                nivel_log=nivel_log,
                success=success,
                limit=limit,
                offset=offset
            )
            
            conn.close()
            
            # Calcular total de páginas
            total = result["total"]
            total_pages = (total + page_size - 1) // page_size if total > 0 else 0
            has_more = page_num < total_pages
            
            # Preparar respuesta con formato de paginación basada en página
            response_data = {
                "status": "success",
                "data": result["data"],
                "metadata": {
                    "total": total,
                    "page": page_num,
                    "pageSize": page_size,
                    "totalPages": total_pages,
                    "has_more": has_more
                }
            }
            
            logger.info(f"✅ GET /ordenes-compra/logs: {len(result['data'])} registros encontrados (total: {result['total']}, página: {page_num}/{total_pages})")
            
            return JSONResponse(
                status_code=200,
                content=response_data,
                headers={
                    "X-Source": source,
                    "X-Endpoint": "ORDENES-COMPRA-LOGS",
                    "X-Total": str(result["total"]),
                    "X-Page": str(page_num),
                    "X-TotalPages": str(total_pages)
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Error al obtener logs de órdenes de compra: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al obtener logs de órdenes de compra: {str(e)}"
                },
                headers={
                    "X-Source": source,
                    "X-Endpoint": "ORDENES-COMPRA-LOGS"
                }
            )
    
    @app.delete("/ordenes-compra/{oc_id}", tags=["Órdenes de Compra"])
    async def delete_orden_compra(
        request: Request,
        oc_id: str,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.ordenes-compra.delete'))
    ):
        """
        Endpoint para eliminar una orden de compra específica.
        
        **Responsabilidad:** Eliminar orden de compra (solo lectura)
        
        **Características:**
        - ✅ Elimina la orden de compra completa (detalles y cabecera)
        - ✅ Elimina primero los detalles y luego la cabecera (por restricciones FK)
        - ✅ Retorna error si la orden no existe
        - ✅ Permisos: requiere permiso de eliminación
        
        **Path Parameters:**
        - `oc_id` (string, requerido) - UUID de la orden de compra a eliminar
        
        **Ejemplo de uso:**
        ```
        DELETE /ordenes-compra/DD7D7A51-9E57-44D4-9A8F-4A05427A8325
        ```
        
        **Respuesta exitosa:**
        ```json
        {
          "status": "success",
          "message": "Orden de compra eliminada exitosamente",
          "oc_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325",
          "detalles_eliminados": 5
        }
        ```
        
        **Respuesta si no existe:**
        ```json
        {
          "status": "error",
          "message": "Orden de compra no encontrada",
          "oc_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325"
        }
        ```
        
        Returns:
            JSON con el resultado de la eliminación
        """
        source = get_source_from_headers(request)
        
        logger.info("=" * 70)
        logger.info(f"🗑️ DELETE /ordenes-compra/{oc_id}: Eliminación iniciada a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info("=" * 70)
        
        try:
            conn = get_db_connection()
            oc_repo = OrdenCompraRepository(conn)
            
            # Verificar que la OC existe antes de eliminar
            existing = oc_repo.get_existing_cabecera(oc_id)
            if not existing:
                conn.close()
                logger.warning(f"⚠️ Orden de compra no encontrada: {oc_id}")
                return JSONResponse(
                    status_code=404,
                    content={
                        "status": "error",
                        "message": "Orden de compra no encontrada",
                        "oc_id": oc_id
                    },
                    headers={
                        "X-Source": source,
                        "X-Endpoint": "DELETE-ORDEN-COMPRA"
                    }
                )
            
            # Obtener número de detalles antes de eliminar (para el log)
            detalles = oc_repo.get_detalles(oc_id)
            num_detalles = len(detalles)
            
            # Eliminar la orden de compra (detalles y cabecera)
            eliminada = oc_repo.delete_cabecera(oc_id)
            
            conn.close()
            
            if eliminada:
                logger.info(f"✅ Orden de compra eliminada: {oc_id} ({num_detalles} detalles)")
                
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "success",
                        "message": "Orden de compra eliminada exitosamente",
                        "oc_id": oc_id,
                        "detalles_eliminados": num_detalles
                    },
                    headers={
                        "X-Source": source,
                        "X-Endpoint": "DELETE-ORDEN-COMPRA",
                        "X-OC-ID": oc_id,
                        "X-Detalles-Eliminados": str(num_detalles)
                    }
                )
            else:
                logger.warning(f"⚠️ No se pudo eliminar orden de compra: {oc_id}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": "No se pudo eliminar la orden de compra",
                        "oc_id": oc_id
                    },
                    headers={
                        "X-Source": source,
                        "X-Endpoint": "DELETE-ORDEN-COMPRA"
                    }
                )
            
        except Exception as e:
            logger.error(f"❌ Error al eliminar orden de compra {oc_id}: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al eliminar orden de compra: {str(e)}",
                    "oc_id": oc_id
                }
            )
    
    @app.delete("/ordenes-compra", tags=["Órdenes de Compra"])
    async def delete_ordenes_compra(
        request: Request,
        oc_id: Optional[List[str]] = Query(None, description="UUID(s) de la(s) orden(es) de compra a eliminar. Puede especificarse múltiples veces (ej: ?oc_id=id1&oc_id=id2)."),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.ordenes-compra.delete'))
    ):
        """
        Endpoint para eliminar múltiples órdenes de compra.
        
        **Responsabilidad:** Eliminar órdenes de compra (múltiples)
        
        **Características:**
        - ✅ Elimina múltiples órdenes de compra en una sola operación
        - ✅ Elimina primero los detalles y luego las cabeceras (por restricciones FK)
        - ✅ Retorna información detallada de cada eliminación
        - ✅ Continúa procesando aunque alguna falle
        - ✅ Permisos: requiere permiso de eliminación
        
        **Query Parameters:**
        - `oc_id` (string, opcional, múltiple) - UUID de la orden de compra. Puede especificarse múltiples veces.
        
        **Ejemplo de uso:**
        ```
        DELETE /ordenes-compra?oc_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325&oc_id=ABC123-DEF456-GHI789
        ```
        
        **Respuesta:**
        ```json
        {
          "status": "success",
          "message": "Proceso completado: 2 órdenes eliminadas de 2 solicitadas",
          "metadata": {
            "total_solicitadas": 2,
            "eliminadas": 2,
            "errores": 0,
            "no_encontradas": 0,
            "detalles": [
              {
                "oc_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325",
                "status": "success",
                "detalles_eliminados": 5
              },
              {
                "oc_id": "ABC123-DEF456-GHI789",
                "status": "success",
                "detalles_eliminados": 3
              }
            ]
          }
        }
        ```
        
        Returns:
            JSON con el resultado de la eliminación de múltiples órdenes
        """
        source = get_source_from_headers(request)
        
        logger.info("=" * 70)
        logger.info(f"🗑️ DELETE /ordenes-compra: Eliminación múltiple iniciada a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        
        try:
            if not oc_id:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": "Debe especificar al menos un oc_id para eliminar",
                        "hint": "Use ?oc_id=id1&oc_id=id2 para eliminar múltiples órdenes"
                    },
                    headers={
                        "X-Source": source,
                        "X-Endpoint": "DELETE-ORDENES-COMPRA"
                    }
                )
            
            # Limpiar y validar IDs
            oc_ids_list = [id.strip() for id in oc_id if id and id.strip()]
            
            if not oc_ids_list:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": "No se proporcionaron oc_ids válidos"
                    },
                    headers={
                        "X-Source": source,
                        "X-Endpoint": "DELETE-ORDENES-COMPRA"
                    }
                )
            
            logger.info(f"📋 Eliminando {len(oc_ids_list)} órdenes de compra")
            logger.info(f"   IDs: {oc_ids_list}")
            logger.info("=" * 70)
            
            conn = get_db_connection()
            oc_repo = OrdenCompraRepository(conn)
            
            # Procesar cada orden
            resultados = []
            eliminadas = 0
            errores = 0
            no_encontradas = 0
            
            for oc_id_item in oc_ids_list:
                try:
                    # Verificar que existe
                    existing = oc_repo.get_existing_cabecera(oc_id_item)
                    if not existing:
                        no_encontradas += 1
                        logger.warning(f"⚠️ Orden de compra no encontrada: {oc_id_item}")
                        resultados.append({
                            "oc_id": oc_id_item,
                            "status": "not_found",
                            "message": "Orden de compra no encontrada",
                            "detalles_eliminados": 0
                        })
                        continue
                    
                    # Obtener número de detalles antes de eliminar
                    detalles = oc_repo.get_detalles(oc_id_item)
                    num_detalles = len(detalles)
                    
                    # Eliminar
                    eliminada = oc_repo.delete_cabecera(oc_id_item)
                    
                    if eliminada:
                        eliminadas += 1
                        logger.info(f"   ✅ OC eliminada: {oc_id_item} ({num_detalles} detalles)")
                        resultados.append({
                            "oc_id": oc_id_item,
                            "status": "success",
                            "message": "Orden de compra eliminada exitosamente",
                            "detalles_eliminados": num_detalles
                        })
                    else:
                        errores += 1
                        logger.warning(f"   ⚠️ No se pudo eliminar OC: {oc_id_item}")
                        resultados.append({
                            "oc_id": oc_id_item,
                            "status": "error",
                            "message": "No se pudo eliminar la orden de compra",
                            "detalles_eliminados": 0
                        })
                        
                except Exception as e:
                    errores += 1
                    logger.error(f"   ❌ Error al eliminar OC {oc_id_item}: {e}")
                    resultados.append({
                        "oc_id": oc_id_item,
                        "status": "error",
                        "message": str(e),
                        "detalles_eliminados": 0
                    })
            
            conn.close()
            
            # Determinar status general
            status_general = "success" if errores == 0 and no_encontradas == 0 else "partial"
            if eliminadas == 0:
                status_general = "error"
            
            mensaje = f"Proceso completado: {eliminadas} órdenes eliminadas de {len(oc_ids_list)} solicitadas"
            if no_encontradas > 0:
                mensaje += f", {no_encontradas} no encontradas"
            if errores > 0:
                mensaje += f", {errores} errores"
            
            logger.info("=" * 70)
            logger.info(f"✅ DELETE /ordenes-compra completado:")
            logger.info(f"   Total solicitadas: {len(oc_ids_list)}")
            logger.info(f"   Eliminadas: {eliminadas}")
            logger.info(f"   No encontradas: {no_encontradas}")
            logger.info(f"   Errores: {errores}")
            logger.info("=" * 70)
            
            return JSONResponse(
                status_code=200 if status_general != "error" else 500,
                content={
                    "status": status_general,
                    "message": mensaje,
                    "metadata": {
                        "total_solicitadas": len(oc_ids_list),
                        "eliminadas": eliminadas,
                        "errores": errores,
                        "no_encontradas": no_encontradas,
                        "detalles": resultados
                    }
                },
                headers={
                    "X-Source": source,
                    "X-Endpoint": "DELETE-ORDENES-COMPRA",
                    "X-Total-Solicitadas": str(len(oc_ids_list)),
                    "X-Eliminadas": str(eliminadas),
                    "X-Errores": str(errores),
                    "X-No-Encontradas": str(no_encontradas)
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Error al eliminar órdenes de compra: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al eliminar órdenes de compra: {str(e)}"
                }
            )
