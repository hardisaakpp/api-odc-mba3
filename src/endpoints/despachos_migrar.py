"""
Endpoint para migrar despachos desde MBA3 a SQL Server.
"""

import logging
from datetime import datetime
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse

from services.mba3_service import MBA3Service
from utils import get_source_from_headers
from security.jwt_auth import verify_jwt_token, require_permission
from exceptions import MBA3ConnectionError, MBA3QueryError
from config import MBA3_QUERY_PREDEFINIDA

logger = logging.getLogger(__name__)


def register_migrar_endpoint(app: FastAPI):
    """
    Registra el endpoint /migrar en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
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
        # Usar query predefinida desde configuración
        query_predefinida = MBA3_QUERY_PREDEFINIDA
        
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

