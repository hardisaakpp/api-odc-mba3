"""
Endpoints relacionados con gestión de órdenes de compra.
"""

import logging
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, Query, Depends
from fastapi.responses import JSONResponse

from utils import get_source_from_headers
from database.repositories.orden_compra_repository import OrdenCompraRepository
from database.repositories.sap_integration_log_repository import SAPIntegrationLogRepository
from database.connection import get_db_connection
from security.jwt_auth import verify_jwt_token, require_permission

logger = logging.getLogger(__name__)


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
                # Obtener todas las OCs sin filtro de estado
                oc_list = oc_repo.get_all()
            
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
            
            # Validar que la ODC no fue creada desde un despacho (no se puede eliminar)
            if existing.get("despacho_id"):
                conn.close()
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
            
            conn = get_db_connection()
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
            
            conn.close()
            
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

