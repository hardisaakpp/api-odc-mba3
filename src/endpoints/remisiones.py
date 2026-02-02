"""
Endpoint para consultar y guardar documentos de remisión desde MBA3.

Estos documentos de remisión son diferentes a los despachos normales:
- No tienen detalles (ObjDatosFactura IS NULL)
- Solo se guardan cabeceras en remision_cabecera (tabla exclusiva)
- No se crean registros en despacho_detalle
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Union, Optional
from fastapi import FastAPI, Request, Depends, Query
from fastapi.responses import JSONResponse

from src.services.mba3_service import MBA3Service
from src.utils import get_source_from_headers
from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission
from src.exceptions import MBA3ConnectionError, MBA3QueryError
from src.config import MBA3_QUERY_REMISIONES, MIGRATE_DATE_FILTER_DAYS

logger = logging.getLogger(__name__)


def build_query_with_date_filter(base_query: str, days: int = 30) -> str:
    """
    Agrega un filtro de fecha a la query base para obtener registros de los últimos N días.
    Mantiene todos los filtros existentes de la consulta.
    
    Args:
        base_query: Query SQL base
        days: Número de días hacia atrás para filtrar (por defecto 30 días)
    
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


def register_remisiones_endpoints(app: FastAPI):
    """
    Registra los endpoints de remisiones en la aplicación FastAPI.
    
    Endpoints registrados:
    - GET /remisiones/consultar: Consulta documentos de remisión desde MBA3 y guarda solo cabeceras
    - GET /remisiones: Obtiene remisiones desde la base de datos con paginación
    
    Args:
        app: Instancia de FastAPI
    """
    
    @app.get("/remisiones", tags=["Remisiones"])
    async def get_remisiones(
        request: Request,
        page: int = Query(1, ge=1, description="Número de página (empezando en 1)"),
        pageSize: int = Query(10, ge=1, le=100, description="Tamaño de página (máximo 100)"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Endpoint para obtener remisiones desde la base de datos con paginación.
        
        **Características:**
        - ✅ Consulta desde la tabla `remision_cabecera` (ya guardada)
        - ✅ Paginación con `page` y `pageSize`
        - ✅ Ordenamiento por fecha más reciente primero
        - ✅ Permisos: `odcsap.view` o `mabel.view`
        
        **Query Parameters:**
        - `page` (int, default: 1) - Número de página (empezando en 1)
        - `pageSize` (int, default: 10, max: 100) - Tamaño de página
        
        **Ejemplo:**
        ```
        GET /remisiones?page=1&pageSize=10
        GET /remisiones?page=2&pageSize=20
        ```
        
        **Respuesta:**
        ```json
        {
          "status": "success",
          "data": [...],
          "metadata": {
            "count": 100
          },
          "total": 100,
          "page": 1,
          "pageSize": 10,
          "totalPages": 10
        }
        ```
        
        Returns:
            JSON con remisiones paginadas
        """
        source = get_source_from_headers(request)
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"👤 Usuario autenticado: {username}")
        
        try:
            from database.connection import get_db_connection
            from database.repositories.remision_repository import RemisionRepository
            
            # Conectar a la base de datos
            conn = get_db_connection()
            repository = RemisionRepository(conn)
            
            try:
                # Obtener remisiones paginadas
                result = repository.get_remisiones_paginadas(page=page, page_size=pageSize)
                
                # Preparar respuesta en el formato esperado por el frontend
                response_content = {
                    "status": "success",
                    "data": result["data"],
                    "metadata": {
                        "count": result["total"]
                    },
                    "total": result["total"],
                    "page": result["page"],
                    "pageSize": result["page_size"],
                    "totalPages": result["total_pages"]
                }
                
                logger.info(
                    f"✅ GET /remisiones: página {page}, tamaño {pageSize}, "
                    f"{len(result['data'])} registros de {result['total']} totales"
                )
                
                return JSONResponse(
                    status_code=200,
                    content=response_content,
                    headers={
                        "X-Source": source,
                        "X-Endpoint": "GET_REMISIONES",
                        "X-Page": str(page),
                        "X-PageSize": str(pageSize),
                        "X-Total": str(result["total"])
                    }
                )
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"❌ Error al obtener remisiones: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al obtener remisiones: {str(e)}",
                    "detail": str(e),
                    "data": [],
                    "metadata": {
                        "count": 0
                    },
                    "total": 0,
                    "page": page,
                    "pageSize": pageSize,
                    "totalPages": 0
                }
            )
    
    @app.get("/remisiones/consultar", tags=["Remisiones"])
    async def consultar_remisiones(
        request: Request,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Endpoint para consultar documentos de remisión desde MBA3 y guardar solo cabeceras.
        
        **Características:**
        - ✅ Consulta documentos de remisión desde MBA3 (sin detalles)
        - ✅ Guarda solo cabeceras en `remision_cabecera` (NO guarda detalles)
        - ✅ Filtro automático: siempre trae los últimos N días desde hoy (configurado en MIGRATE_DATE_FILTER_DAYS)
        - ✅ Sin parámetros: solo ejecutar el endpoint
        - ✅ Fecha relativa: calcula automáticamente desde hoy hacia atrás
        - ✅ Configurable: se puede cambiar en .env con MIGRATE_DATE_FILTER_DAYS
        - ✅ Estos documentos no tienen `ObjDatosFactura`, por lo que no se crean registros en `despacho_detalle`
        
        **Query utilizada:**
        Consulta documentos de remisión con:
        - TIPO_DOCUMENTO='REM'
        - CONFIRMADO='false'
        - Remision_Facturada='false'
        - ObjDatosFactura IS NULL (sin detalles)
        - FACTURA_IMPRESA='false'
        - ANULADA='false'
        - FECHA_FACTURA >= (fecha calculada según MIGRATE_DATE_FILTER_DAYS)
        
        **Ejemplo de uso:**
        ```
        GET /remisiones/consultar
        ```
        
        **Nota:** Este endpoint guarda automáticamente en la base de datos.
        Usa la misma configuración de filtro de fecha que los procesos manual y automático.
        
        Returns:
            JSON con los datos de remisiones y metadata del guardado
        """
        # Construir query con filtro de fecha fijo (usando la misma configuración que migrar)
        query_predefinida = build_query_with_date_filter(
            MBA3_QUERY_REMISIONES, 
            days=MIGRATE_DATE_FILTER_DAYS
        )
        
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de usuario autenticado
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"👤 Usuario autenticado: {username}")
        
        # Log de la consulta
        logger.info("=" * 70)
        logger.info(f"📡 CONSULTAR REMISIONES: Iniciado a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"📅 Proceso: filtrando últimos {MIGRATE_DATE_FILTER_DAYS} días")
        logger.info(f"Query: {query_predefinida[:200]}...")
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
            
            # Log del resultado
            count = len(result) if isinstance(result, list) else (1 if isinstance(result, dict) and result else 0)
            logger.info(f"✅ Consulta MBA3 exitosa: {count} documentos de remisión obtenidos")
            
            # Guardar en SQL Server (solo cabeceras en remision_cabecera, sin detalles)
            # upsert=True: Actualiza si existe, inserta si no existe
            logger.info("💾 Guardando cabeceras en remision_cabecera (sin detalles)...")
            save_status = None
            try:
                # Usar el método específico para remisiones que guarda en remision_cabecera
                save_status = MBA3Service.save_remisiones_to_database(result, upsert=True)
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
                "X-Endpoint": "CONSULTAR_REMISIONES",
                "X-Date-Filter": f"{MIGRATE_DATE_FILTER_DAYS}d"
            }
            
            # Agregar información de guardado si existe
            if save_status:
                headers["X-Saved-To-DB"] = save_status.get("status", "unknown")
                headers["X-DB-Facturas"] = str(save_status.get("facturas_guardadas", 0) + save_status.get("facturas_actualizadas", 0))
                headers["X-DB-Detalles"] = str(save_status.get("total_detalles", 0))
            
            # Preparar respuesta con metadata
            response_content = {
                "status": "success",
                "data": result if result else [],  # Datos de MBA3, siempre lista o dict
                "metadata": {
                    "query": query_predefinida,
                    "count": count,
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
                    },
                    "note": "Estos documentos de remisión no tienen detalles. Solo se guardan cabeceras en remision_cabecera."
                }
            }
            
            logger.info("=" * 70)
            logger.info(f"✅ CONSULTAR REMISIONES completado:")
            if save_status:
                logger.info(f"   Documentos guardados: {save_status.get('facturas_guardadas', 0)}")
                logger.info(f"   Documentos actualizados: {save_status.get('facturas_actualizadas', 0)}")
                logger.info(f"   Total detalles: {save_status.get('total_detalles', 0)} (debe ser 0 para remisiones)")
            logger.info(f"   Total registros: {count}")
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
            logger.error(f"❌ Error inesperado en consulta de remisiones: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error inesperado: {str(e)}",
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

