"""
Endpoints relacionados con gestión de órdenes de compra.
"""

import logging
import threading
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, cast
from fastapi import FastAPI, Request, Query, Depends, Path, Body, HTTPException
from fastapi.responses import JSONResponse

from src.utils import get_source_from_headers
from src.database.repositories.orden_compra_repository import OrdenCompraRepository
from src.database.repositories.sap_integration_log_repository import SAPIntegrationLogRepository
from src.database.connection import get_db_connection, get_db_connection_context
from src.database.clients.sap_client import SAPClient
from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission

logger = logging.getLogger(__name__)

# ============================================================================
# Sistema de Caché para /ordenes-compra
# ============================================================================

# Caché thread-safe para órdenes de compra
_oc_cache_lock = threading.Lock()
_ordenes_compra_cache: Dict[str, Any] = {}
_oc_cache_ttl_seconds = 30  # 30 segundos de caché


def get_cached_ordenes_compra(estado: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Obtiene órdenes de compra del caché si aún es válido.
    
    Args:
        estado: Estado filtrado (para diferenciar cachés)
        
    Returns:
        Datos del caché si son válidos, None en caso contrario
    """
    with _oc_cache_lock:
        cache_key = f"ordenes_compra_{estado or 'all'}"
        now = datetime.now()
        
        if cache_key in _ordenes_compra_cache:
            cached_data = _ordenes_compra_cache[cache_key]
            cached_time = cached_data.get('timestamp')
            
            if cached_time and (now - cached_time).total_seconds() < _oc_cache_ttl_seconds:
                logger.debug(f"📦 Cache HIT para /ordenes-compra (estado={estado})")
                return cached_data.get('data')
            else:
                # Caché expirado, eliminarlo
                del _ordenes_compra_cache[cache_key]
                logger.debug(f"⏰ Cache EXPIRED para /ordenes-compra (estado={estado})")
        
        logger.debug(f"📭 Cache MISS para /ordenes-compra (estado={estado})")
        return None


def set_cached_ordenes_compra(data: Dict[str, Any], estado: Optional[str] = None):
    """
    Guarda datos en el caché.
    
    Args:
        data: Datos a guardar en caché
        estado: Estado filtrado (para diferenciar cachés)
    """
    with _oc_cache_lock:
        cache_key = f"ordenes_compra_{estado or 'all'}"
        _ordenes_compra_cache[cache_key] = {
            'data': data,
            'timestamp': datetime.now()
        }
        logger.debug(f"💾 Cache SAVED para /ordenes-compra (estado={estado})")


def invalidate_ordenes_compra_cache():
    """
    Invalida el caché de órdenes de compra.
    Útil cuando se actualizan datos (migración automática, creación de OC, etc.)
    """
    with _oc_cache_lock:
        _ordenes_compra_cache.clear()
        logger.info("🗑️ Cache invalidado para /ordenes-compra")


def register_ordenes_compra_endpoints(app: FastAPI):
    """
    Registra los endpoints de órdenes de compra en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
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
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
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
          "data": [...],
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
            # Función helper que se ejecutará en thread pool para no bloquear el event loop
            def _query_historial_helper(oc_id_param, referencia_despacho_param, proveedor_param,
                                       fecha_desde_param, fecha_hasta_param, nivel_log_param,
                                       success_param, limit_param, offset_param):
                """Función helper que ejecuta la consulta en thread separado"""
                conn = get_db_connection()
                try:
                    log_repo = SAPIntegrationLogRepository(conn)
                    
                    # Parsear fechas si se proporcionan
                    fecha_desde_dt = None
                    fecha_hasta_dt = None
                    
                    if fecha_desde_param:
                        try:
                            fecha_desde_dt = datetime.strptime(fecha_desde_param, "%Y-%m-%d")
                        except ValueError:
                            return {"error": "Formato de fecha_desde inválido. Use YYYY-MM-DD"}
                    
                    if fecha_hasta_param:
                        try:
                            fecha_hasta_dt = datetime.strptime(fecha_hasta_param, "%Y-%m-%d")
                            # Agregar 23:59:59 para incluir todo el día
                            fecha_hasta_dt = fecha_hasta_dt.replace(hour=23, minute=59, second=59)
                        except ValueError:
                            return {"error": "Formato de fecha_hasta inválido. Use YYYY-MM-DD"}
                    
                    # Obtener historial
                    result = log_repo.get_historial_ordenes(
                        oc_id=oc_id_param,
                        referencia_despacho=referencia_despacho_param,
                        proveedor=proveedor_param,
                        fecha_desde=fecha_desde_dt,
                        fecha_hasta=fecha_hasta_dt,
                        nivel_log=nivel_log_param,
                        success=success_param,
                        limit=limit_param,
                        offset=offset_param
                    )
                    
                    return {"result": result}
                finally:
                    conn.close()
            
            # Ejecutar consulta en thread pool para no bloquear el event loop
            logger.debug("🔄 Ejecutando consulta de historial en thread pool (no bloquea otras peticiones)...")
            query_result = await asyncio.to_thread(
                _query_historial_helper,
                oc_id, referencia_despacho, proveedor,
                fecha_desde, fecha_hasta, nivel_log,
                success, limit, offset
            )
            
            # Verificar si hubo error de validación
            if "error" in query_result:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": query_result["error"]
                    }
                )
            
            # Usar cast para ayudar al type checker
            result_raw = query_result.get("result")
            if not isinstance(result_raw, dict):
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": "Formato de respuesta inválido"
                    }
                )
            
            result = cast(Dict[str, Any], result_raw)
            
            # Extraer valores con validación de tipos
            data = result.get("data", [])
            total_raw = result.get("total", 0)
            
            # Asegurar que total es un entero
            if isinstance(total_raw, int):
                total = total_raw
            else:
                try:
                    total = int(total_raw)
                except (ValueError, TypeError):
                    total = 0
            
            # Asegurar que offset es un entero
            offset_int = int(offset) if offset is not None else 0
            
            # Preparar respuesta
            has_more = offset_int + len(data) < total
            
            response_data = {
                "status": "success",
                "data": data,
                "metadata": {
                    "total": total,
                    "limit": limit or 50,
                    "offset": offset_int,
                    "has_more": has_more
                }
            }
            
            logger.info(f"✅ GET /historial-ordenes: {len(data)} registros encontrados (total: {total})")
            
            return JSONResponse(
                status_code=200,
                content=response_data,
                headers={
                    "X-Source": source,
                    "X-Endpoint": "HISTORIAL-ORDENES",
                    "X-Total": str(total)
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
    
    @app.get("/ordenes-compra", tags=["Órdenes de Compra"])
    async def get_ordenes_compra(
        request: Request,
        estado: Optional[str] = Query(None, description="Filtrar por estado (PENDIENTE, ENVIADA, ERROR)"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
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
          "data": [...],
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
        
        # Intentar obtener del caché primero
        cached_result = get_cached_ordenes_compra(estado=estado)
        if cached_result:
            logger.debug("📦 Retornando datos desde caché")
            return JSONResponse(
                status_code=200,
                content=cached_result,
                headers={
                    "X-Source": source,
                    "X-Endpoint": "ORDENES-COMPRA",
                    "X-Count": str(cached_result.get("metadata", {}).get("count", 0)),
                    "X-Cache": "HIT"
                }
            )
        
        logger.info("=" * 70)
        logger.info(f"📋 GET /ordenes-compra: Consulta ejecutada a las {datetime.now().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"Filtro estado: {estado or 'Todos'}")
        logger.info("=" * 70)
        
        try:
            # Función helper que se ejecutará en thread pool para no bloquear el event loop
            def _query_ordenes_compra(estado_param: Optional[str]):
                """Función helper que ejecuta la consulta en thread separado"""
                conn = get_db_connection()
                try:
                    oc_repo = OrdenCompraRepository(conn)
                    
                    if estado_param:
                        # Obtener OCs por estado
                        oc_list = oc_repo.get_by_estado(estado_param)
                    else:
                        # Obtener todas las OCs sin filtro de estado
                        oc_list = oc_repo.get_all()
                    
                    return oc_list
                finally:
                    conn.close()
            
            # Ejecutar consulta en thread pool para no bloquear el event loop
            logger.debug("🔄 Ejecutando consulta de BD en thread pool (no bloquea otras peticiones)...")
            oc_list = await asyncio.to_thread(_query_ordenes_compra, estado)
            
            response_data = {
                "status": "success",
                "data": oc_list,
                "metadata": {
                    "count": len(oc_list),
                    "estado_filter": estado or "PENDIENTE"
                }
            }
            
            # Guardar en caché
            set_cached_ordenes_compra(response_data, estado=estado)
            
            logger.info(f"✅ GET /ordenes-compra: {len(oc_list)} órdenes encontradas")
            
            return JSONResponse(
                status_code=200,
                content=response_data,
                headers={
                    "X-Source": source,
                    "X-Endpoint": "ORDENES-COMPRA",
                    "X-Count": str(len(oc_list)),
                    "X-Cache": "MISS"
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
        _: None = Depends(require_permission('mabel.view'))
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
          "data": [...],
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
            # Función helper que se ejecutará en thread pool para no bloquear el event loop
            def _query_historial_logs(page_param, page_size_param, oc_id_param, referencia_despacho_param,
                                     proveedor_param, fecha_desde_param, fecha_hasta_param,
                                     nivel_log_param, success_param):
                """Función helper que ejecuta la consulta en thread separado"""
                conn = get_db_connection()
                try:
                    log_repo = SAPIntegrationLogRepository(conn)
                    
                    # Convertir page/pageSize a offset/limit
                    page_num = page_param or 1
                    page_size = page_size_param or 50
                    offset = (page_num - 1) * page_size
                    limit = page_size
                    
                    # Parsear fechas si se proporcionan
                    fecha_desde_dt = None
                    fecha_hasta_dt = None
                    
                    if fecha_desde_param:
                        try:
                            fecha_desde_dt = datetime.strptime(fecha_desde_param, "%Y-%m-%d")
                        except ValueError:
                            return {"error": "Formato de fecha_desde inválido. Use YYYY-MM-DD"}
                    
                    if fecha_hasta_param:
                        try:
                            fecha_hasta_dt = datetime.strptime(fecha_hasta_param, "%Y-%m-%d")
                            # Agregar 23:59:59 para incluir todo el día
                            fecha_hasta_dt = fecha_hasta_dt.replace(hour=23, minute=59, second=59)
                        except ValueError:
                            return {"error": "Formato de fecha_hasta inválido. Use YYYY-MM-DD"}
                    
                    # Obtener historial
                    result = log_repo.get_historial_ordenes(
                        oc_id=oc_id_param,
                        referencia_despacho=referencia_despacho_param,
                        proveedor=proveedor_param,
                        fecha_desde=fecha_desde_dt,
                        fecha_hasta=fecha_hasta_dt,
                        nivel_log=nivel_log_param,
                        success=success_param,
                        limit=limit,
                        offset=offset
                    )
                    
                    return {"result": result, "page_num": page_num, "page_size": page_size}
                finally:
                    conn.close()
            
            # Ejecutar consulta en thread pool para no bloquear el event loop
            logger.debug("🔄 Ejecutando consulta de historial en thread pool (no bloquea otras peticiones)...")
            query_result = await asyncio.to_thread(
                _query_historial_logs,
                page, pageSize, oc_id, referencia_despacho,
                proveedor, fecha_desde, fecha_hasta,
                nivel_log, success
            )
            
            # Verificar si hubo error de validación
            if "error" in query_result:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": query_result["error"]
                    }
                )
            
            # Usar cast para ayudar al type checker
            result_raw = query_result.get("result")
            if not isinstance(result_raw, dict):
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": "Formato de respuesta inválido"
                    }
                )
            
            result = cast(Dict[str, Any], result_raw)
            
            # Extraer page_num y page_size con validación
            page_num_raw = query_result.get("page_num", 1)
            page_size_raw = query_result.get("page_size", 10)
            
            # Asegurar que page_num y page_size son enteros
            if isinstance(page_num_raw, int):
                page_num = page_num_raw
            else:
                try:
                    page_num = int(page_num_raw)
                except (ValueError, TypeError):
                    page_num = 1
            
            if isinstance(page_size_raw, int):
                page_size = page_size_raw
            else:
                try:
                    page_size = int(page_size_raw)
                except (ValueError, TypeError):
                    page_size = 10
            
            # Extraer valores con validación de tipos
            data = result.get("data", [])
            total_raw = result.get("total", 0)
            
            # Asegurar que total es un entero
            if isinstance(total_raw, int):
                total = total_raw
            else:
                try:
                    total = int(total_raw)
                except (ValueError, TypeError):
                    total = 0
            
            # Calcular total de páginas
            total_pages = (total + page_size - 1) // page_size if total > 0 else 0
            has_more = page_num < total_pages
            
            # Preparar respuesta con formato de paginación basada en página
            response_data = {
                "status": "success",
                "data": data,
                "metadata": {
                    "total": total,
                    "page": page_num,
                    "pageSize": page_size,
                    "totalPages": total_pages,
                    "has_more": has_more
                }
            }
            
            logger.info(f"✅ GET /ordenes-compra/logs: {len(data)} registros encontrados (total: {total}, página: {page_num}/{total_pages})")
            
            return JSONResponse(
                status_code=200,
                content=response_data,
                headers={
                    "X-Source": source,
                    "X-Endpoint": "ORDENES-COMPRA-LOGS",
                    "X-Total": str(total),
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
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Endpoint para eliminar una orden de compra específica.
        
        **Responsabilidad:** Eliminar orden de compra (solo lectura)
        
        **Características:**
        - ✅ Elimina la orden de compra completa (detalles y cabecera)
        - ✅ Elimina primero los detalles y luego la cabecera (por restricciones FK)
        - ✅ Retorna error si la orden no existe
        - ✅ No permite eliminar ODC creadas desde despachos (tienen despacho_id)
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
        
        **Respuesta si no se puede eliminar (creada desde despacho):**
        ```json
        {
          "status": "error",
          "message": "No se puede eliminar una orden de compra creada desde un despacho",
          "oc_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325",
          "despacho_id": "ABC123-DEF456-GHI789"
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
            # Usar context manager para garantizar transacción y cierre de conexión
            with get_db_connection_context() as conn:
                oc_repo = OrdenCompraRepository(conn)
                
                # Verificar que la OC existe antes de eliminar
                existing = oc_repo.get_existing_cabecera(oc_id)
                if not existing:
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
                
                # Validar que la ODC no fue creada desde un despacho (no se puede eliminar)
                if existing.get("despacho_id"):
                    logger.warning(f"⚠️ No se puede eliminar orden de compra creada desde despacho: {oc_id}")
                    return JSONResponse(
                        status_code=403,
                        content={
                            "status": "error",
                            "message": "No se puede eliminar una orden de compra creada desde un despacho",
                            "oc_id": oc_id,
                            "despacho_id": existing.get("despacho_id")
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
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Endpoint para eliminar múltiples órdenes de compra.
        
        **Responsabilidad:** Eliminar órdenes de compra (múltiples)
        
        **Características:**
        - ✅ Elimina múltiples órdenes de compra en una sola operación
        - ✅ Elimina primero los detalles y luego las cabeceras (por restricciones FK)
        - ✅ Retorna información detallada de cada eliminación
        - ✅ No permite eliminar ODC creadas desde despachos (tienen despacho_id)
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
            "detalles": [...]
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
            
            # Usar context manager para garantizar transacción y cierre de conexión
            with get_db_connection_context() as conn:
                oc_repo = OrdenCompraRepository(conn)
                
                # Procesar cada orden
                resultados = []
                eliminadas = 0
                errores = 0
                no_encontradas = 0
                no_permitidas = 0
                
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
                        
                        # Validar que la ODC no fue creada desde un despacho (no se puede eliminar)
                        if existing.get("despacho_id"):
                            no_permitidas += 1
                            logger.warning(f"⚠️ No se puede eliminar orden de compra creada desde despacho: {oc_id_item}")
                            resultados.append({
                                "oc_id": oc_id_item,
                                "status": "forbidden",
                                "message": "No se puede eliminar una orden de compra creada desde un despacho",
                                "despacho_id": existing.get("despacho_id"),
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
            
            # Determinar status general
            status_general = "success" if errores == 0 and no_encontradas == 0 and no_permitidas == 0 else "partial"
            if eliminadas == 0:
                status_general = "error"
            
            mensaje = f"Proceso completado: {eliminadas} órdenes eliminadas de {len(oc_ids_list)} solicitadas"
            if no_encontradas > 0:
                mensaje += f", {no_encontradas} no encontradas"
            if no_permitidas > 0:
                mensaje += f", {no_permitidas} no permitidas (creadas desde despacho)"
            if errores > 0:
                mensaje += f", {errores} errores"
            
            logger.info("=" * 70)
            logger.info(f"✅ DELETE /ordenes-compra completado:")
            logger.info(f"   Total solicitadas: {len(oc_ids_list)}")
            logger.info(f"   Eliminadas: {eliminadas}")
            logger.info(f"   No encontradas: {no_encontradas}")
            logger.info(f"   No permitidas (creadas desde despacho): {no_permitidas}")
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
                        "no_permitidas": no_permitidas,
                        "detalles": resultados
                    }
                },
                headers={
                    "X-Source": source,
                    "X-Endpoint": "DELETE-ORDENES-COMPRA",
                    "X-Total-Solicitadas": str(len(oc_ids_list)),
                    "X-Eliminadas": str(eliminadas),
                    "X-Errores": str(errores),
                    "X-No-Encontradas": str(no_encontradas),
                    "X-No-Permitidas": str(no_permitidas)
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
    
    @app.get("/ordenes-compra/{oc_id}/detalles", tags=["Órdenes de Compra"])
    async def get_orden_compra_detalles(
        request: Request,
        oc_id: str = Path(..., description="UUID de la orden de compra"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Endpoint para obtener los detalles (líneas) de una orden de compra específica.
        
        Este endpoint retorna todas las líneas de detalle de una ODC, incluyendo
        información sobre SKUs, cantidades, precios, etc.
        
        **Path Parameters:**
        - `oc_id` (string, requerido) - UUID de la orden de compra
        
        **Ejemplo de uso:**
        ```
        GET /ordenes-compra/DD7D7A51-9E57-44D4-9A8F-4A05427A8325/detalles
        ```
        
        **Respuesta exitosa:**
        ```json
        {
            "status": "success",
            "oc_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325",
            "detalles": [
                {
                    "oc_detalle_id": "ABC123-...",
                    "oc_id": "DD7D7A51-...",
                    "sku_sap": "5-0012.9",
                    "cantidad_sap": 10.0,
                    "unidad_sap": "X3",
                    "precio_unitario": 150.0,
                    "total_linea": 1500.0,
                    "cantidad_origen": 30.0
                },
                ...
            ],
            "count": 5
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
        """
        source = get_source_from_headers(request)
        
        logger.info(f"📋 GET /ordenes-compra/{oc_id}/detalles: Consulta iniciada")
        
        try:
            def obtener_detalles_oc():
                conn = get_db_connection()
                try:
                    oc_repo = OrdenCompraRepository(conn)
                    
                    # Verificar que la OC existe
                    oc_cabecera = oc_repo.get_existing_cabecera(oc_id)
                    if not oc_cabecera:
                        return None
                    
                    # Obtener detalles
                    detalles = oc_repo.get_detalles(oc_id)
                    return detalles
                finally:
                    conn.close()
            
            detalles = await asyncio.to_thread(obtener_detalles_oc)
            
            if detalles is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Orden de compra no encontrada: {oc_id}"
                )
            
            logger.info(f"✅ GET /ordenes-compra/{oc_id}/detalles: {len(detalles)} detalles encontrados")
            
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "oc_id": oc_id,
                    "detalles": detalles,
                    "count": len(detalles)
                },
                headers={
                    "X-Source": source,
                    "X-Endpoint": "GET-ORDEN-COMPRA-DETALLES",
                    "X-Count": str(len(detalles))
                }
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener detalles de OC {oc_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error al obtener detalles de la orden de compra: {str(e)}"
            )
    
    @app.put("/ordenes-compra/{oc_id}/detalle/{oc_detalle_id}/sku", tags=["Órdenes de Compra"])
    async def actualizar_sku_detalle(
        request: Request,
        oc_id: str = Path(..., description="UUID de la orden de compra"),
        oc_detalle_id: str = Path(..., description="UUID del detalle de orden de compra"),
        nuevo_sku: str = Body(..., embed=True, description="Nuevo SKU (ItemCode) de SAP"),
        validar_en_sap: bool = Body(True, embed=True, description="Validar que el SKU exista en SAP antes de actualizar"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Endpoint para actualizar el SKU de un detalle de orden de compra.
        
        Este endpoint permite corregir el SKU de una línea de detalle de una ODC,
        útil cuando hay errores al enviar a SAP debido a SKUs incorrectos.
        
        **Path Parameters:**
        - `oc_id` (string, requerido) - UUID de la orden de compra
        - `oc_detalle_id` (string, requerido) - UUID del detalle de orden de compra
        
        **Body Parameters:**
        - `nuevo_sku` (string, requerido) - Nuevo SKU (ItemCode) de SAP
        - `validar_en_sap` (boolean, default: true) - Si True, valida que el SKU exista en SAP antes de actualizar
        
        **Ejemplo de uso:**
        ```
        PUT /ordenes-compra/DD7D7A51-9E57-44D4-9A8F-4A05427A8325/detalle/ABC123-DEF456-GHI789/sku
        {
            "nuevo_sku": "5-0012.9",
            "validar_en_sap": true
        }
        ```
        
        **Respuesta exitosa:**
        ```json
        {
            "status": "success",
            "message": "SKU actualizado exitosamente",
            "oc_id": "DD7D7A51-9E57-44D4-9A8F-4A05427A8325",
            "oc_detalle_id": "ABC123-DEF456-GHI789",
            "sku_anterior": "5-0012.8",
            "sku_nuevo": "5-0012.9",
            "sku_validado_en_sap": true
        }
        ```
        
        **Respuesta si el SKU no existe en SAP (si validar_en_sap=true):**
        ```json
        {
            "status": "error",
            "message": "El SKU no existe en SAP",
            "sku": "5-0012.9"
        }
        ```
        """
        source = get_source_from_headers(request)
        username = user.get('username', 'unknown') if user else 'unknown'
        
        logger.info(f"📝 Actualizando SKU en detalle {oc_detalle_id[:8]}... de OC {oc_id[:8]}...")
        logger.info(f"   Usuario: {username}, Nuevo SKU: {nuevo_sku}")
        
        try:
            # Validar formato del nuevo SKU
            nuevo_sku_clean = nuevo_sku.strip()
            if not nuevo_sku_clean:
                raise HTTPException(status_code=400, detail="El nuevo SKU no puede estar vacío")
            
            # Validar formato del SKU
            import re
            if not re.match(r'^[A-Za-z0-9.\- ]{1,50}$', nuevo_sku_clean):
                raise HTTPException(
                    status_code=400,
                    detail="El SKU contiene caracteres no permitidos. Solo se permiten letras, números, guiones, puntos y espacios."
                )
            
            # Validar que el SKU exista en SAP si se requiere
            sku_validado_en_sap = False
            if validar_en_sap:
                logger.info(f"🔍 Validando SKU en SAP: {nuevo_sku_clean}")
                
                def validar_sku_en_sap():
                    sap_client = SAPClient()
                    producto_info = sap_client.get_producto_info(nuevo_sku_clean)
                    return producto_info is not None
                
                try:
                    sku_validado_en_sap = await asyncio.to_thread(validar_sku_en_sap)
                except Exception as e:
                    logger.warning(f"⚠️ Error al validar SKU en SAP: {e}")
                    sku_validado_en_sap = False
                
                if not sku_validado_en_sap:
                    raise HTTPException(
                        status_code=404,
                        detail=f"El SKU '{nuevo_sku_clean}' no existe en SAP o no está disponible"
                    )
                
                logger.info(f"✅ SKU validado en SAP: {nuevo_sku_clean}")
            
            # Obtener información del detalle actual antes de actualizar
            def obtener_y_actualizar_sku():
                # Usar context manager para garantizar transacción y cierre de conexión
                with get_db_connection_context() as conn:
                    oc_repo = OrdenCompraRepository(conn)
                    
                    # Obtener detalles para verificar que existe y obtener SKU anterior
                    detalles = oc_repo.get_detalles(oc_id)
                    detalle_encontrado = None
                    
                    for detalle in detalles:
                        if str(detalle.get("oc_detalle_id")) == oc_detalle_id:
                            detalle_encontrado = detalle
                            break
                    
                    if not detalle_encontrado:
                        raise ValueError(f"No se encontró el detalle {oc_detalle_id} en la OC {oc_id}")
                    
                    sku_anterior = detalle_encontrado.get("sku_sap")
                    
                    # Verificar que la OC esté en estado ERROR (o permitir actualizar si está en PENDIENTE también)
                    oc_cabecera = oc_repo.get_existing_cabecera(oc_id)
                    if not oc_cabecera:
                        raise ValueError(f"No se encontró la OC {oc_id}")
                    
                    estado_actual = oc_cabecera.get("estado")
                    if estado_actual not in ["ERROR", "PENDIENTE"]:
                        logger.warning(f"⚠️ OC está en estado '{estado_actual}', permitiendo actualización de SKU")
                    
                    # Actualizar el SKU
                    actualizado = oc_repo.update_sku_detalle(
                        oc_detalle_id=oc_detalle_id,
                        nuevo_sku_sap=nuevo_sku_clean,
                        validar_existencia=True
                    )
                    
                    if not actualizado:
                        raise ValueError(f"No se pudo actualizar el SKU del detalle {oc_detalle_id}")
                    
                    # Invalidar caché de órdenes de compra
                    invalidate_ordenes_compra_cache()
                    
                    return sku_anterior
            
            # Ejecutar actualización en thread pool
            sku_anterior = await asyncio.to_thread(obtener_y_actualizar_sku)
            
            logger.info(f"✅ SKU actualizado exitosamente: '{sku_anterior}' → '{nuevo_sku_clean}'")
            
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "SKU actualizado exitosamente",
                    "oc_id": oc_id,
                    "oc_detalle_id": oc_detalle_id,
                    "sku_anterior": sku_anterior,
                    "sku_nuevo": nuevo_sku_clean,
                    "sku_validado_en_sap": sku_validado_en_sap
                },
                headers={
                    "X-Source": source,
                    "X-Endpoint": "UPDATE-SKU-DETALLE"
                }
            )
            
        except HTTPException:
            raise
        except ValueError as e:
            logger.error(f"❌ Error de validación al actualizar SKU: {e}")
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"❌ Error al actualizar SKU en detalle: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error al actualizar SKU: {str(e)}"
            )

