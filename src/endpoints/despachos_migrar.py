"""
Endpoint para migrar despachos desde MBA3 a SQL Server.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Union
from fastapi import FastAPI, Request, Depends, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.services.mba3_service import MBA3Service
from src.utils import get_source_from_headers
from src.security.jwt_auth import verify_jwt_token, require_permission
from src.exceptions import MBA3ConnectionError, MBA3QueryError
from src.config import MBA3_QUERY_PREDEFINIDA, MIGRATE_DATE_FILTER_DAYS

logger = logging.getLogger(__name__)


def build_query_with_date_filter(base_query: str, days: int = 30) -> str:
    """
    Agrega un filtro de fecha a la query base para obtener registros de los últimos N días.
    Mantiene todos los filtros existentes de la consulta.
    
    Args:
        base_query: Query SQL base
        days: Número de días hacia atrás para filtrar (por defecto 30 días = 1 mes)
    
    Returns:
        Query SQL con filtro de fecha agregado
    """
    # Calcular fecha límite (hace N días) - solo fecha, sin hora
    # MBA3/4D espera formato de fecha simple (YYYY-MM-DD) sin hora
    fecha_limite = datetime.now() - timedelta(days=days)
    fecha_limite_str = fecha_limite.strftime("%Y-%m-%d")
    
    # Verificar si la query ya tiene WHERE
    if "WHERE" in base_query.upper():
        # Agregar filtro de fecha al WHERE existente (mantiene todos los filtros)
        # Usar >= con formato de fecha simple (sin hora) para compatibilidad con MBA3/4D
        query_with_filter = f"{base_query} AND FECHA_FACTURA >= '{fecha_limite_str}'"
    else:
        # Agregar WHERE con filtro de fecha
        query_with_filter = f"{base_query} WHERE FECHA_FACTURA >= '{fecha_limite_str}'"
    
    return query_with_filter


def register_migrar_endpoint(app: FastAPI):
    """
    Registra los endpoints de migración en la aplicación FastAPI.
    
    Endpoints registrados:
    - GET /migrar/completo: Consulta y guarda (endpoint original para el frontend)
    - GET /consultar: Solo consulta MBA3
    - POST /migrar: Solo guarda en base de datos
    
    Args:
        app: Instancia de FastAPI
    """
    # ============================================================================
    # Modelo Pydantic para el endpoint de guardado
    # ============================================================================
    class SaveDataRequest(BaseModel):
        """Modelo para recibir datos a guardar en la base de datos."""
        data: Union[List[Dict[str, Any]], Dict[str, Any]]
        upsert: bool = True  # Por defecto, actualizar si existe
        
        class Config:
            json_schema_extra = {
                "example": {
                    "data": [
                        {
                            "CODIGO_FACTURA": "REMSI-900125250-TRAYO",
                            "NUMERO_FACTURA": 900125250,
                            "EMPRESA": "TRAYO",
                            "CODIGO_CLIENTE": "CLI0024",
                            "FECHA_FACTURA": "2025-10-14",
                            "NUMERO_ORDEN": 129065,
                            "ANULADA": False,
                            "CODIGO_DESPACHO": 0,
                            "CONFIRMADO": True,
                            "CODIGO_BODEGA": "BPT",
                            "TIPO_DOCUMENTO": "REM",
                            "NUMERO_PEDIDO_SISTEMA": 175975,
                            "ORDEN_COMPRA_CLIENTE": "",
                            "ORDEN_COMPRA": "1-10432",
                            "ObjDatosFactura": {
                                "CtrlEliminados4": [
                                    {
                                        "Codigo": "5640.10.BD",
                                        "Nombre": "MDS REF.5640 T.10-12 BCO DIS",
                                        "Cantidad": 50,
                                        "Descuento": 0,
                                        "PrecioUnitario": 6.09,
                                        "TotalLinea": 304.5
                                    }
                                ]
                            },
                            "Remision_Facturada": False,
                            "NumIDFacturaRelacionada": 0
                        }
                    ],
                    "upsert": True
                }
            }
    
    # ============================================================================
    # Endpoint original /migrar/completo (consulta + guarda para el frontend)
    # ============================================================================
    @app.get("/migrar/completo", tags=["Consultas MBA3"])
    async def migrar_despachos(
        request: Request,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Endpoint MIGRAR COMPLETO: Ejecuta consulta predefinida y guarda en despacho_cabecera/detalle.
        
        **Responsabilidad:** MIGRAR COMPLETO (consulta + guarda en un solo paso)
        
        Este endpoint realiza:
        1. ✅ Consulta datos desde MBA3 usando query predefinida con filtro de fecha (último año)
        2. ✅ Guarda resultados en SQL Server (despacho_cabecera/detalle)
        3. ❌ NO copia a orden_compra (ese paso lo hace el endpoint PROCESAR)
        
        **Características:**
        - ✅ Filtro automático: siempre trae los últimos 365 días (1 año) desde hoy
        - ✅ Sin parámetros: solo ejecutar el endpoint
        - ✅ Fecha relativa: calcula automáticamente desde hoy hacia atrás
        - ✅ Configurable: se puede cambiar en .env con MIGRATE_DATE_FILTER_DAYS
        
        **Nota:** Este endpoint realiza ambas operaciones (consulta y guardado).
        Para operaciones separadas, usar:
        - GET /consultar (solo consulta)
        - POST /migrar (solo guarda)
        
        **Ejemplo de uso:**
        ```
        GET /migrar/completo
        ```
        
        **Nota:** Este endpoint solo migra a despacho.
        Para proceso completo (consulta + guarda + copia a ODC), usar GET /consulta/predefinida.
        
        Returns:
            JSON con los datos de MBA3 y metadata del guardado en despacho
        """
        # Construir query con filtro de fecha fijo (1 año desde hoy)
        query_predefinida = build_query_with_date_filter(
            MBA3_QUERY_PREDEFINIDA, 
            days=MIGRATE_DATE_FILTER_DAYS
        )
        
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de usuario autenticado
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"👤 Usuario autenticado: {username}")
        
        # Log de la consulta predefinida
        logger.info("=" * 70)
        logger.info(f"🔄 MIGRAR COMPLETO: Proceso iniciado a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"📅 Proceso manual: filtrando últimos {MIGRATE_DATE_FILTER_DAYS} días (1 año)")
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
                "X-Endpoint": "MIGRAR_COMPLETO",
                "X-Date-Filter": f"{MIGRATE_DATE_FILTER_DAYS}d"
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
                    "date_filter": {
                        "enabled": True,
                        "days": MIGRATE_DATE_FILTER_DAYS
                    },
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
            logger.info(f"✅ MIGRAR COMPLETO completado:")
            if save_status:
                logger.info(f"   Facturas guardadas: {save_status.get('facturas_guardadas', 0)}")
                logger.info(f"   Facturas actualizadas: {save_status.get('facturas_actualizadas', 0)}")
                logger.info(f"   Total detalles: {save_status.get('total_detalles', 0)}")
            logger.info(f"   Total registros: {response_content['metadata']['count']}")
            logger.info("=" * 70)
            
            # NUEVO: Verificar productos no homologados y notificar EN TIEMPO REAL
            # Solo si hay facturas nuevas guardadas
            if save_status and save_status.get('facturas_guardadas', 0) > 0:
                try:
                    from src.database.services.homologacion_service import HomologacionService
                    from src.utils.email_notifier import send_homologacion_notification
                    
                    logger.info("🔍 Verificando productos no homologados en migración manual...")
                    
                    # Usar context manager para conexión
                    from src.database.connection import get_db_connection_context
                    with get_db_connection_context() as conn:
                        homologacion_service = HomologacionService(conn)
                        
                        # Detectar productos no homologados
                        productos_no_homologados = homologacion_service.get_productos_no_homologados()
                        
                        if productos_no_homologados and len(productos_no_homologados) > 0:
                            logger.info(f"⚠️ Se detectaron {len(productos_no_homologados)} productos no homologados")
                            
                            # Enviar notificación FILTRANDO productos ya notificados
                            email_enviado = send_homologacion_notification(
                                productos_no_homologados=productos_no_homologados,
                                estadisticas=None,
                                fecha_ejecucion=datetime.now(),
                                filtrar_ya_notificados=True,  # ← CLAVE: Filtrar ya notificados
                                homologacion_repository=homologacion_service.repository
                            )
                            
                            if email_enviado:
                                logger.info("✅ Notificación de homologación enviada (solo productos nuevos)")
                            else:
                                logger.info("⏭️ No se envió notificación (todos ya fueron notificados)")
                        else:
                            logger.info("✅ No hay productos no homologados")
                            
                except Exception as homolog_error:
                    logger.warning(f"⚠️ Error al verificar homologaciones: {homolog_error}")
                    # No afectar la respuesta principal
            
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
                        "date_filter": {
                            "enabled": True,
                            "days": MIGRATE_DATE_FILTER_DAYS
                        },
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
                        "date_filter": {
                            "enabled": True,
                            "days": MIGRATE_DATE_FILTER_DAYS
                        },
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
                        "date_filter": {
                            "enabled": True,
                            "days": MIGRATE_DATE_FILTER_DAYS
                        },
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
    
    # ============================================================================
    # Nuevos endpoints separados: consultar y guardar
    # ============================================================================
    
    @app.get("/consultar", tags=["Consultas MBA3"])
    async def consultar_mba3(
        request: Request,
        use_date_filter: bool = False,
        days: int = 30,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Endpoint CONSULTAR MBA3: Solo consulta datos desde MBA3, NO guarda en base de datos.
        
        **Responsabilidad:** Solo consulta, separada del guardado.
        
        Este endpoint realiza:
        1. ✅ Consulta datos desde MBA3 usando query predefinida
        2. ❌ NO guarda en base de datos (usar /migrar para eso)
        
        **Parámetros:**
        - use_date_filter: Si es True, filtra registros de los últimos N días
        - days: Número de días hacia atrás para filtrar (solo si use_date_filter=True)
        
        **Ejemplo de uso:**
        ```
        GET /consultar
        GET /consultar?use_date_filter=true&days=30
        ```
        
        **Flujo recomendado:**
        1. Llamar este endpoint para obtener datos de MBA3
        2. Usar los datos retornados para llamar a `/migrar`
        
        Returns:
            JSON con los datos de MBA3 (sin guardar en BD)
        """
        # Construir query según parámetros
        if use_date_filter:
            query_predefinida = build_query_with_date_filter(MBA3_QUERY_PREDEFINIDA, days=days)
            logger.info(f"📅 Usando filtro de fecha: últimos {days} días")
        else:
            query_predefinida = MBA3_QUERY_PREDEFINIDA
        
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de usuario autenticado
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"👤 Usuario autenticado: {username}")
        
        # Log de la consulta
        logger.info("=" * 70)
        logger.info(f"📡 CONSULTAR MBA3: Iniciado a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        if use_date_filter:
            logger.info(f"Filtro de fecha: últimos {days} días")
        logger.info(f"Query: {query_predefinida[:200]}...")
        logger.info("=" * 70)
        
        try:
            # Ejecutar consulta usando el servicio
            result = MBA3Service.execute_query(query_predefinida)
            
            # Normalizar resultado
            if result is None:
                logger.warning("⚠️ La consulta retornó None. Usando lista vacía.")
                result = []
            elif not isinstance(result, (list, dict)):
                logger.warning(f"⚠️ Tipo de resultado inesperado: {type(result)}. Convirtiendo a lista.")
                result = [result] if result else []
            
            # Log del resultado
            count = len(result) if isinstance(result, list) else (1 if isinstance(result, dict) and result else 0)
            logger.info(f"✅ Consulta MBA3 exitosa: {count} registros obtenidos")
            logger.info("=" * 70)
            
            # Preparar headers de respuesta
            headers = {
                "X-Query": query_predefinida[:100],
                "X-Source": source,
                "X-Method": "GET",
                "X-Endpoint": "CONSULTAR_MBA3"
            }
            
            if use_date_filter:
                headers["X-Date-Filter"] = f"{days}d"
            
            # Preparar respuesta
            response_content = {
                "status": "success",
                "data": result if result else [],
                "metadata": {
                    "query": query_predefinida,
                    "count": count,
                    "date_filter": {
                        "enabled": use_date_filter,
                        "days": days if use_date_filter else None
                    },
                    "note": "Estos datos NO han sido guardados en la base de datos. Use /migrar para guardarlos."
                }
            }
            
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
                    "data": [],
                    "metadata": {
                        "query": query_predefinida
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
                    "data": [],
                    "metadata": {
                        "query": query_predefinida
                    }
                }
            )
        except Exception as e:
            logger.error(f"❌ Error inesperado en consulta MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error inesperado: {str(e)}",
                    "detail": str(e),
                    "type": "internal_error",
                    "data": [],
                    "metadata": {
                        "query": query_predefinida
                    }
                }
            )


    @app.post("/migrar", tags=["Consultas MBA3"])
    async def guardar_datos(
        request: Request,
        save_request: SaveDataRequest = Body(...),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Endpoint GUARDAR: Guarda datos en SQL Server (despacho_cabecera/detalle).
    
    **Responsabilidad:** Solo guarda en base de datos, NO consulta MBA3.
    
    Este endpoint realiza:
    1. ✅ Guarda datos en SQL Server (despacho_cabecera/detalle)
    2. ❌ NO consulta MBA3 (usar /consultar para eso)
    
    **Body (JSON):**
    ```json
    {
        "data": [
            {
                "CODIGO_FACTURA": "...",
                "ANULADA": "...",
                ...
            }
        ],
        "upsert": true
    }
    ```
    
    - data: Lista o diccionario con los datos a guardar (formato MBA3)
    - upsert: Si es True, actualiza si existe; si False, inserta siempre
    
    **Ejemplo de uso:**
    ```bash
    POST /migrar
    Content-Type: application/json
    
    {
        "data": [...],
        "upsert": true
    }
    ```
    
    **Flujo recomendado:**
    1. Llamar `/consultar` para obtener datos de MBA3
    2. Usar los datos retornados en el body de este endpoint
    
        Returns:
            JSON con el status del guardado
        """
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de usuario autenticado
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"👤 Usuario autenticado: {username}")
        
        # Obtener datos del request
        data = save_request.data
        upsert = save_request.upsert
        
        # Validar que hay datos
        if not data or (isinstance(data, list) and len(data) == 0):
            logger.warning("⚠️ No hay datos para guardar")
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "No se proporcionaron datos para guardar",
                    "type": "validation_error",
                    "save_status": {
                        "status": "error",
                        "facturas_guardadas": 0,
                        "facturas_actualizadas": 0,
                        "total_detalles": 0
                    }
                }
            )
        
        # Log del proceso
        logger.info("=" * 70)
        logger.info(f"💾 GUARDAR DATOS: Iniciado a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"Upsert: {upsert}")
        data_count = len(data) if isinstance(data, list) else 1
        logger.info(f"Registros a guardar: {data_count}")
        logger.info("=" * 70)
        
        try:
            # Guardar en SQL Server
            save_status = MBA3Service.save_to_database(data, upsert=upsert)
            
            if save_status:
                facturas_guardadas = save_status.get('facturas_guardadas', 0)
                facturas_actualizadas = save_status.get('facturas_actualizadas', 0)
                total_detalles = save_status.get('total_detalles', 0)
                
                logger.info("=" * 70)
                logger.info(f"✅ GUARDAR completado:")
                logger.info(f"   Facturas guardadas: {facturas_guardadas}")
                logger.info(f"   Facturas actualizadas: {facturas_actualizadas}")
                logger.info(f"   Total detalles: {total_detalles}")
                logger.info("=" * 70)
                
                # Preparar headers
                headers = {
                    "X-Source": source,
                    "X-Method": "POST",
                    "X-Endpoint": "GUARDAR_DATOS",
                    "X-Saved-To-DB": save_status.get("status", "unknown"),
                    "X-DB-Facturas": str(facturas_guardadas + facturas_actualizadas),
                    "X-DB-Detalles": str(total_detalles)
                }
                
                # Preparar respuesta
                response_content = {
                    "status": "success",
                    "message": "Datos guardados exitosamente",
                    "save_status": save_status,
                    "metadata": {
                        "registros_recibidos": data_count,
                        "upsert": upsert
                    }
                }
                
                return JSONResponse(
                    status_code=200,
                    content=response_content,
                    headers=headers
                )
            else:
                logger.warning("⚠️ No se pudo guardar (save_status es None)")
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": "No se pudo guardar en la base de datos",
                        "save_status": {
                            "status": "error",
                            "facturas_guardadas": 0,
                            "facturas_actualizadas": 0,
                            "total_detalles": 0
                        }
                    }
                )
                
        except Exception as e:
            logger.error(f"❌ Error al guardar en SQL Server: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al guardar en SQL Server: {str(e)}",
                    "detail": str(e),
                    "type": "save_error",
                    "save_status": {
                        "status": "error",
                        "facturas_guardadas": 0,
                        "facturas_actualizadas": 0,
                        "total_detalles": 0,
                        "errors": [str(e)]
                    }
                }
            )

