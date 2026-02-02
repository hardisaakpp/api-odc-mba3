"""
Endpoints relacionados con pruebas y ejecución de procesos completos.
"""

import logging
from datetime import datetime
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse

from src.services.mba3_service import MBA3Service
from src.utils import get_source_from_headers
from src.database.repositories.despacho_repository import DespachoRepository
from src.database.repositories.orden_compra_repository import OrdenCompraRepository
from src.database.services.orden_compra_service import copy_despacho_to_orden_compra
from src.database.connection import get_db_connection
from src.security.jwt_auth import verify_jwt_token, require_permission
from src.exceptions import MBA3ConnectionError, MBA3QueryError
from src.config import MBA3_QUERY_PREDEFINIDA

logger = logging.getLogger(__name__)


def register_pruebas_endpoints(app: FastAPI):
    """
    Registra los endpoints de pruebas en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
    @app.get("/pruebas", tags=["Pruebas"])
    async def ejecutar_pruebas(
        request: Request,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
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
        # Usar query predefinida desde configuración
        query_predefinida = MBA3_QUERY_PREDEFINIDA
        
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

