"""
Endpoints relacionados con consulta, migración y procesamiento de despachos.
"""

import logging
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, Query, Depends
from fastapi.responses import JSONResponse

from services.mba3_service import MBA3Service
from utils import get_source_from_headers
from database.repositories.despacho_repository import DespachoRepository
from database.repositories.orden_compra_repository import OrdenCompraRepository
from database.services.orden_compra_service import copy_despacho_to_orden_compra
from database.connection import get_db_connection
from security.jwt_auth import verify_jwt_token, require_permission
from exceptions import MBA3ConnectionError, MBA3QueryError

logger = logging.getLogger(__name__)


def register_despachos_endpoints(app: FastAPI):
    """
    Registra los endpoints de despachos en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
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
          "despachos": [...]
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
          "detalles": [...],
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

