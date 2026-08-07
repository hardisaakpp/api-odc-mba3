"""
Endpoints relacionados con gestión de órdenes de compra.
"""

import io
import logging
import threading
import asyncio
from datetime import datetime

from src.utils.timezone import ahora_naive
from typing import Optional, List, Dict, Any, cast
from fastapi import FastAPI, Request, Query, Depends, Path, Body, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from src.utils import get_source_from_headers
from src.database.repositories.orden_compra_repository import OrdenCompraRepository
from src.database.repositories.solicitud_transferencia_repository import SolicitudTransferenciaRepository
from src.database.repositories.envio_odc_sap_repository import EnvioODCSAPRepository
from src.database.repositories.sap_integration_log_repository import SAPIntegrationLogRepository
from src.database.connection import get_db_connection, get_db_connection_context
from src.database.clients.sap_client import SAPClient
from src.database.clients.sap_service_layer_client import SAPServiceLayerClient
from src.database.services.stock_transfer_service import StockTransferService, redis_lock_reintento_st
from src.config import SAP_USE_MIDDLEWARE
from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission

logger = logging.getLogger(__name__)

# Traduce el status interno de StockTransferService.reintentar_pendientes a HTTP + status externo.
_RETRY_ST_STATUS_HTTP = {
    "no_encontrada": 404,
    "estado_invalido": 400,
    "sin_pedido": 400,
}
_RETRY_ST_STATUS_EXTERNO = {
    "no_encontrada": "error",
    "estado_invalido": "error",
    "sin_pedido": "error",
    "no_pendientes": "success",
    "en_cola": "en_cola",
}

# Permisos (evita duplicación de literales)
_PERM_ODCSAP = 'odcsap.view'
_PERM_MABEL = 'mabel.view'

# Mensajes reutilizados
_MSG_OC_NO_ENCONTRADA = "Orden de compra no encontrada"

# Descripciones reutilizadas (OpenAPI)
_DESC_OC_ID = "UUID de la orden de compra"



def _traducir_resultado_reintento_st(resultado: Dict[str, Any]) -> Dict[str, Any]:
    """Traduce el dict de reintentar_pendientes al contrato HTTP ya usado por el frontend."""
    status_interno = resultado.get("status", "error")
    status_code = _RETRY_ST_STATUS_HTTP.get(status_interno, 200)
    body = dict(resultado)
    body["status"] = _RETRY_ST_STATUS_EXTERNO.get(status_interno, status_interno)
    return {"status_code": status_code, "body": body}


def _sku_existe_via_middleware(sku_clean: str) -> Optional[bool]:
    """
    Verifica vía middleware (GET /api/v1/items/{code}) si un SKU existe en SAP.

    Returns:
        True si existe, False si el middleware confirmó que no existe (404),
        None si el middleware no está disponible y el caller debe hacer
        fallback a OPENQUERY.
    """
    item = SAPServiceLayerClient().get_item(sku_clean)
    if item is None:
        return None  # sin conexión al middleware: fallback
    if item.get("_error"):
        if item.get("_error_type") == "no_existe":
            return False
        return None  # otro error del middleware: fallback a OPENQUERY
    return True


def _sku_existe_en_sap(sku_clean: str) -> bool:
    """
    Verifica si un SKU existe en SAP: middleware primero (SAP_USE_MIDDLEWARE),
    con fallback automático a OPENQUERY si el middleware no responde.
    """
    if SAP_USE_MIDDLEWARE:
        existe = _sku_existe_via_middleware(sku_clean)
        if existe is not None:
            return existe
        logger.warning(
            f"⚠️ Middleware no disponible para validar SKU {sku_clean}; fallback a OPENQUERY"
        )
    sap_client = SAPClient()
    return sap_client.get_producto_info(sku_clean) is not None

# ============================================================================
# Sistema de Caché para /ordenes-compra
# ============================================================================

# Caché thread-safe para órdenes de compra
_oc_cache_lock = threading.Lock()
_ordenes_compra_cache: Dict[str, Any] = {}
_oc_cache_ttl_seconds = 30  # 30 segundos de caché


def _ordenes_compra_cache_key(
    estado: Optional[str],
    page: int,
    page_size: int,
    referencia_despacho: Optional[str],
    numero_oc_sap: Optional[str],
    search: Optional[str],
) -> str:
    """Clave de caché que incluye paginación y filtros de listado."""
    return (
        f"ordenes_compra_{estado or 'all'}_p{page}_s{page_size}"
        f"_ref{referencia_despacho or ''}_sap{numero_oc_sap or ''}_q{search or ''}"
    )


def get_cached_ordenes_compra(cache_key: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene órdenes de compra del caché si aún es válido.

    Args:
        cache_key: Clave compuesta (estado, página, filtros)

    Returns:
        Datos del caché si son válidos, None en caso contrario
    """
    with _oc_cache_lock:
        now = ahora_naive()

        if cache_key in _ordenes_compra_cache:
            cached_data = _ordenes_compra_cache[cache_key]
            cached_time = cached_data.get('timestamp')

            if cached_time and (now - cached_time).total_seconds() < _oc_cache_ttl_seconds:
                logger.debug(f"📦 Cache HIT para /ordenes-compra ({cache_key})")
                return cached_data.get('data')
            else:
                # Caché expirado, eliminarlo
                del _ordenes_compra_cache[cache_key]
                logger.debug(f"⏰ Cache EXPIRED para /ordenes-compra ({cache_key})")

        logger.debug(f"📭 Cache MISS para /ordenes-compra ({cache_key})")
        return None


def set_cached_ordenes_compra(data: Dict[str, Any], cache_key: str):
    """
    Guarda datos en el caché.

    Args:
        data: Datos a guardar en caché
        cache_key: Clave compuesta (estado, página, filtros)
    """
    with _oc_cache_lock:
        _ordenes_compra_cache[cache_key] = {
            'data': data,
            'timestamp': ahora_naive()
        }
        logger.debug(f"💾 Cache SAVED para /ordenes-compra ({cache_key})")


def invalidate_ordenes_compra_cache():
    """
    Invalida el caché de órdenes de compra.
    Útil cuando se actualizan datos (migración automática, creación de OC, etc.)
    """
    with _oc_cache_lock:
        _ordenes_compra_cache.clear()
        logger.info("🗑️ Cache invalidado para /ordenes-compra")


def _enrich_oc_actions(
    oc: Dict[str, Any],
    st_resumen: Optional[Dict[str, Any]] = None,
    st_pendientes_reintento: int = 0,
) -> None:
    """
    Enriquecer acciones de UI por estado de la ODC.

    Regla de negocio:
    - PENDIENTE / ERROR: mostrar botón "Reintentar ODC" en lugar de "Descargar PDF".
    - ENVIADA + ITR/ST aún pendientes (reintento): mostrar botón "Reintentar ST".
    - Resto de estados: mantener botón "Descargar PDF".
    """
    estado = str(oc.get("estado") or "").strip().upper()
    mostrar_reintentar = estado in {"PENDIENTE", "ERROR"}
    transferencias_errores = int((st_resumen or {}).get("transferencias_errores", 0) or 0)
    pendientes = int(st_pendientes_reintento or 0)
    # Botón ST: hay tiendas pendientes reales (tras éxitos parciales o último batch con error).
    mostrar_reintentar_st = estado == "ENVIADA" and pendientes > 0
    oc["mostrar_reintentar"] = mostrar_reintentar
    oc["mostrar_descargar_pdf"] = not mostrar_reintentar
    oc["mostrar_reintentar_st"] = mostrar_reintentar_st
    oc["st_pendientes_reintento"] = pendientes
    oc["st_total_tiendas"] = int((st_resumen or {}).get("total_tiendas", 0) or 0)
    oc["st_transferencias_creadas"] = int((st_resumen or {}).get("transferencias_creadas", 0) or 0)
    oc["st_transferencias_errores"] = transferencias_errores


# ============================================================================
# Helpers de coerción / parseo reutilizados por los handlers
# ============================================================================

def _coerce_int(value: Any, default: int) -> int:
    """Convierte value a int; retorna default si no es posible."""
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _parse_fecha_param(value: Optional[str], campo: str, fin_dia: bool = False):
    """
    Parsea una fecha 'YYYY-MM-DD'. Retorna (dt, None) o (None, mensaje_error).
    Si fin_dia=True, ajusta a 23:59:59 para incluir todo el día.
    """
    if not value:
        return None, None
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None, f"Formato de {campo} inválido. Use YYYY-MM-DD"
    if fin_dia:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt, None


# ============================================================================
# Funciones de consulta (se ejecutan en thread pool)
# ============================================================================

def _query_historial_ordenes(oc_id, referencia_despacho, proveedor,
                             fecha_desde, fecha_hasta, nivel_log,
                             success, limit, offset):
    """Ejecuta la consulta de historial de órdenes (offset/limit) en thread separado."""
    conn = get_db_connection()
    try:
        log_repo = SAPIntegrationLogRepository(conn)

        fecha_desde_dt, error = _parse_fecha_param(fecha_desde, "fecha_desde")
        if error:
            return {"error": error}
        fecha_hasta_dt, error = _parse_fecha_param(fecha_hasta, "fecha_hasta", fin_dia=True)
        if error:
            return {"error": error}

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
        return {"result": result}
    finally:
        conn.close()


def _query_historial_logs(page, page_size, oc_id, referencia_despacho,
                          proveedor, fecha_desde, fecha_hasta,
                          nivel_log, success):
    """Ejecuta la consulta de historial de logs (page/pageSize) en thread separado."""
    conn = get_db_connection()
    try:
        log_repo = SAPIntegrationLogRepository(conn)

        # Convertir page/pageSize a offset/limit
        page_num = page or 1
        page_size_v = page_size or 50
        offset = (page_num - 1) * page_size_v

        fecha_desde_dt, error = _parse_fecha_param(fecha_desde, "fecha_desde")
        if error:
            return {"error": error}
        fecha_hasta_dt, error = _parse_fecha_param(fecha_hasta, "fecha_hasta", fin_dia=True)
        if error:
            return {"error": error}

        result = log_repo.get_historial_ordenes(
            oc_id=oc_id,
            referencia_despacho=referencia_despacho,
            proveedor=proveedor,
            fecha_desde=fecha_desde_dt,
            fecha_hasta=fecha_hasta_dt,
            nivel_log=nivel_log,
            success=success,
            limit=page_size_v,
            offset=offset
        )
        return {"result": result, "page_num": page_num, "page_size": page_size_v}
    finally:
        conn.close()


def _query_ordenes_compra(estado_param, limit_param, offset_param,
                          referencia_param, numero_sap_param, search_param):
    """Ejecuta listado paginado y enriquecimiento ST/ITR solo para la página actual."""
    conn = get_db_connection()
    try:
        oc_repo = OrdenCompraRepository(conn)
        resultado = oc_repo.list_paginated(
            estado=estado_param,
            referencia_despacho=referencia_param,
            numero_oc_sap=numero_sap_param,
            search=search_param,
            limit=limit_param,
            offset=offset_param,
        )
        oc_list = resultado["data"]
        if oc_list:
            st_repo = SolicitudTransferenciaRepository(conn)
            oc_ids_list = [o["oc_id"] for o in oc_list]
            itr_doc = st_repo.get_doc_num_itr_por_oc_ids(oc_ids_list)
            st_resumen_by_oc = st_repo.get_latest_resumen_by_oc_ids(oc_ids_list)
            st_pendientes_by_oc = st_repo.count_st_pendientes_reintento_por_oc_ids(oc_ids_list)
            for o in oc_list:
                if o["oc_id"] in itr_doc:
                    o["doc_num"] = itr_doc[o["oc_id"]]
                _enrich_oc_actions(
                    o,
                    st_resumen=st_resumen_by_oc.get(o["oc_id"]),
                    st_pendientes_reintento=st_pendientes_by_oc.get(o["oc_id"], 0),
                )
        return resultado
    finally:
        conn.close()


def _obtener_detalles_oc(oc_id):
    """Obtiene los detalles de una OC (o None si no existe) en thread separado."""
    conn = get_db_connection()
    try:
        oc_repo = OrdenCompraRepository(conn)
        # Verificar que la OC existe
        oc_cabecera = oc_repo.get_existing_cabecera(oc_id)
        if not oc_cabecera:
            return None
        # Obtener detalles
        return oc_repo.get_detalles(oc_id)
    finally:
        conn.close()


def _fetch_integracion_sap(oc_id):
    """Obtiene el detalle de integración SAP de una OC (o None) en thread separado."""
    conn = get_db_connection()
    try:
        envio_repo = EnvioODCSAPRepository(conn)
        st_repo = SolicitudTransferenciaRepository(conn)

        envio = envio_repo.get_by_oc_id(oc_id)
        if not envio:
            return None

        numero_oc_sap = envio.get("numero_oc_sap")
        doc_entry = envio.get("doc_entry")
        proveedor = envio.get("proveedor")

        # Agregado en vivo sobre TODOS los batches de ST (envío original + reintentos),
        # no el snapshot congelado en envio_odc_sap del primer intento.
        resumen = st_repo.get_resumen_agregado_por_oc_id(oc_id)
        doc_num_first = resumen["itrs_por_tienda"][0]["doc_num"] if resumen["itrs_por_tienda"] else None

        solicitudes_transferencia = {
            "total_tiendas": resumen["total_tiendas"],
            "transferencias_creadas": resumen["transferencias_creadas"],
            "transferencias_errores": resumen["transferencias_errores"],
            "resultados": resumen["resultados"],
            "itrs_por_tienda": resumen["itrs_por_tienda"],
        }

        envio_sap = {
            "oc_id": oc_id,
            "proveedor": proveedor,
            "success": True,
            "numero_oc_sap": numero_oc_sap,
            "doc_entry": doc_entry,
            "doc_num": doc_num_first,
            "solicitudes_transferencia": solicitudes_transferencia,
        }

        return {
            "envio_sap": envio_sap,
            "solicitudes_transferencia": solicitudes_transferencia,
        }
    finally:
        conn.close()


def _generar_pdf_oc(oc_id):
    """Genera el PDF de una OC. Retorna (pdf_bytes, oc_cabecera, error)."""
    conn = get_db_connection()
    try:
        oc_repo = OrdenCompraRepository(conn)

        # 1. Obtener cabecera de la OC
        oc_cabecera = oc_repo.get_existing_cabecera(oc_id)
        if not oc_cabecera:
            return None, None, _MSG_OC_NO_ENCONTRADA

        # 2. Obtener detalles
        oc_detalles = oc_repo.get_detalles(oc_id)
        if not oc_detalles:
            oc_detalles = []

        # 3. Intentar enriquecer con datos del pedido (para PDF)
        pedido_info = None
        pedido_id = oc_cabecera.get("pedido_id")
        if pedido_id:
            try:
                from src.database.services.oc_sap_service import OCSAPService
                pedido_info = OCSAPService._obtener_pedido_info_para_pdf(
                    conn, pedido_id, oc_detalles
                )
            except Exception as e_enrich:
                logger.warning(f"⚠️ No se pudo enriquecer datos para PDF (no crítico): {e_enrich}")

        # 4. Generar PDF
        from src.utils.odc_pdf_generator import generar_odc_pdf

        doc_num = oc_cabecera.get("numero_oc_sap")

        pdf_bytes = generar_odc_pdf(
            oc_cabecera=oc_cabecera,
            oc_detalles=oc_detalles,
            doc_num=doc_num,
            pedido_info=pedido_info,
        )

        return pdf_bytes, oc_cabecera, None
    finally:
        conn.close()


def _eliminar_una_oc(oc_repo, oc_id_item):
    """Elimina una OC individual. Retorna (resultado_dict, categoria_contador)."""
    try:
        # Verificar que existe
        existing = oc_repo.get_existing_cabecera(oc_id_item)
        if not existing:
            logger.warning(f"⚠️ Orden de compra no encontrada: {oc_id_item}")
            return {
                "oc_id": oc_id_item,
                "status": "not_found",
                "message": _MSG_OC_NO_ENCONTRADA,
                "detalles_eliminados": 0
            }, "no_encontradas"

        # Validar que la ODC no fue creada desde un despacho (no se puede eliminar)
        if existing.get("despacho_id"):
            logger.warning(f"⚠️ No se puede eliminar orden de compra creada desde despacho: {oc_id_item}")
            return {
                "oc_id": oc_id_item,
                "status": "forbidden",
                "message": "No se puede eliminar una orden de compra creada desde un despacho",
                "despacho_id": existing.get("despacho_id"),
                "detalles_eliminados": 0
            }, "no_permitidas"

        # Obtener número de detalles antes de eliminar
        detalles = oc_repo.get_detalles(oc_id_item)
        num_detalles = len(detalles)

        # Eliminar
        eliminada = oc_repo.delete_cabecera(oc_id_item)

        if eliminada:
            logger.info(f"   ✅ OC eliminada: {oc_id_item} ({num_detalles} detalles)")
            return {
                "oc_id": oc_id_item,
                "status": "success",
                "message": "Orden de compra eliminada exitosamente",
                "detalles_eliminados": num_detalles
            }, "eliminadas"

        errores_msg = "No se pudo eliminar la orden de compra"
        logger.warning(f"   ⚠️ No se pudo eliminar OC: {oc_id_item}")
        return {
            "oc_id": oc_id_item,
            "status": "error",
            "message": errores_msg,
            "detalles_eliminados": 0
        }, "errores"
    except Exception as e:
        logger.error(f"   ❌ Error al eliminar OC {oc_id_item}: {e}")
        return {
            "oc_id": oc_id_item,
            "status": "error",
            "message": str(e),
            "detalles_eliminados": 0
        }, "errores"


def _construir_mensaje_delete_multiple(eliminadas, total_solicitadas, no_encontradas, no_permitidas, errores):
    """Construye el mensaje de resumen de la eliminación múltiple."""
    mensaje = f"Proceso completado: {eliminadas} órdenes eliminadas de {total_solicitadas} solicitadas"
    if no_encontradas > 0:
        mensaje += f", {no_encontradas} no encontradas"
    if no_permitidas > 0:
        mensaje += f", {no_permitidas} no permitidas (creadas desde despacho)"
    if errores > 0:
        mensaje += f", {errores} errores"
    return mensaje


def _retry_st_only(oc_id, username):
    """Adquiere el lock distribuido por OC y ejecuta el reintento ST de forma idempotente."""
    with redis_lock_reintento_st(oc_id, blocking_timeout=120.0) as acquired:
        if not acquired:
            return {
                "status_code": 409,
                "body": {
                    "status": "error",
                    "message": "Otro reintento de ST está en curso para esta OC. Espere unos segundos e intente de nuevo.",
                    "oc_id": oc_id,
                },
            }
        resultado = StockTransferService().reintentar_pendientes(
            oc_id, usuario_id=username, origen="manual"
        )
        if resultado.get("status") in ("success", "partial"):
            try:
                invalidate_ordenes_compra_cache()
            except Exception:
                pass
        return _traducir_resultado_reintento_st(resultado)


async def _validar_sku_sap(nuevo_sku_clean: str) -> bool:
    """Valida en thread pool si el SKU existe en SAP. False ante error."""
    logger.info(f"🔍 Validando SKU en SAP: {nuevo_sku_clean}")

    def _validar():
        # Dispatcher middleware -> fallback OPENQUERY (SAP_USE_MIDDLEWARE)
        return _sku_existe_en_sap(nuevo_sku_clean)

    try:
        return await asyncio.to_thread(_validar)
    except Exception as e:
        logger.warning(f"⚠️ Error al validar SKU en SAP: {e}")
        return False


def _obtener_y_actualizar_sku(oc_id, oc_detalle_id, nuevo_sku_clean):
    """Actualiza el SKU de un detalle de OC. Retorna el SKU anterior. Lanza ValueError si falla."""
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


# ============================================================================
# Handlers de endpoints (lógica movida fuera del registrador)
# ============================================================================

async def _get_historial_ordenes_handler(request, oc_id, referencia_despacho, proveedor,
                                          fecha_desde, fecha_hasta, nivel_log,
                                          success, limit, offset):
    source = get_source_from_headers(request)

    try:
        # Ejecutar consulta en thread pool para no bloquear el event loop
        logger.debug("🔄 Ejecutando consulta de historial en thread pool (no bloquea otras peticiones)...")
        query_result = await asyncio.to_thread(
            _query_historial_ordenes,
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
        total = _coerce_int(result.get("total", 0), 0)
        offset_int = _coerce_int(offset, 0)

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


async def _get_ordenes_compra_handler(request, page, page_size, page_size_camel, estado,
                                       referencia_despacho, numero_oc_sap, search):
    source = get_source_from_headers(request)
    size = page_size_camel if page_size_camel is not None else page_size
    offset = (page - 1) * size
    estado_norm = estado.strip().upper() if estado else None

    cache_key = _ordenes_compra_cache_key(
        estado_norm, page, size, referencia_despacho, numero_oc_sap, search
    )

    cached_result = get_cached_ordenes_compra(cache_key)
    if cached_result:
        logger.debug("📦 Retornando datos desde caché")
        return JSONResponse(
            status_code=200,
            content=cached_result,
            headers={
                "X-Source": source,
                "X-Endpoint": "ORDENES-COMPRA",
                "X-Count": str(cached_result.get("total", 0)),
                "X-Page": str(cached_result.get("page", page)),
                "X-Cache": "HIT"
            }
        )

    logger.info("=" * 70)
    logger.info(f"📋 GET /ordenes-compra: Consulta ejecutada a las {ahora_naive().isoformat()}")
    logger.info(f"Fuente: {source}")
    logger.info(f"Filtro estado: {estado_norm or 'Todos'} | page={page} pageSize={size}")
    logger.info("=" * 70)

    try:
        logger.debug("🔄 Ejecutando consulta paginada en thread pool...")
        resultado = await asyncio.to_thread(
            _query_ordenes_compra,
            estado_norm,
            size,
            offset,
            referencia_despacho,
            numero_oc_sap,
            search,
        )

        oc_list = resultado["data"]
        total = int(resultado["total"])
        total_pages = (total + size - 1) // size if size else 0

        response_data = {
            "status": "success",
            "data": oc_list,
            "total": total,
            "page": page,
            "pageSize": size,
            "totalPages": total_pages,
            "metadata": {
                "count": len(oc_list),
                "estado_filter": estado_norm,
                "total": total,
                "page": page,
                "pageSize": size,
                "totalPages": total_pages,
                "hasMore": page < total_pages,
            },
        }

        set_cached_ordenes_compra(response_data, cache_key)

        logger.info(
            f"✅ GET /ordenes-compra: {len(oc_list)} órdenes (total={total}, página {page}/{total_pages})"
        )

        return JSONResponse(
            status_code=200,
            content=response_data,
            headers={
                "X-Source": source,
                "X-Endpoint": "ORDENES-COMPRA",
                "X-Count": str(total),
                "X-Page": str(page),
                "X-TotalPages": str(total_pages),
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


async def _get_ordenes_compra_logs_handler(request, page, page_size, oc_id, referencia_despacho,
                                            proveedor, fecha_desde, fecha_hasta,
                                            nivel_log, success):
    source = get_source_from_headers(request)

    try:
        # Ejecutar consulta en thread pool para no bloquear el event loop
        logger.debug("🔄 Ejecutando consulta de historial en thread pool (no bloquea otras peticiones)...")
        query_result = await asyncio.to_thread(
            _query_historial_logs,
            page, page_size, oc_id, referencia_despacho,
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
        page_num = _coerce_int(query_result.get("page_num", 1), 1)
        page_size = _coerce_int(query_result.get("page_size", 10), 10)

        # Extraer valores con validación de tipos
        data = result.get("data", [])
        total = _coerce_int(result.get("total", 0), 0)

        # Calcular total de páginas
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        has_more = page_num < total_pages

        # Preparar respuesta con formato de paginación basada en página
        # Referencia: docs/NAMING_CONVENTIONS.md (camelCase para metadatos de paginación)
        response_data = {
            "status": "success",
            "data": data,
            "metadata": {
                "total": total,
                "page": page_num,
                "pageSize": page_size,
                "totalPages": total_pages,
                "hasMore": has_more
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


async def _delete_orden_compra_handler(request, oc_id):
    source = get_source_from_headers(request)

    logger.info("=" * 70)
    logger.info(f"🗑️ DELETE /ordenes-compra/{oc_id}: Eliminación iniciada a las {ahora_naive().isoformat()}")
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
                        "message": _MSG_OC_NO_ENCONTRADA,
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


async def _delete_ordenes_compra_handler(request, oc_id):
    source = get_source_from_headers(request)

    logger.info("=" * 70)
    logger.info(f"🗑️ DELETE /ordenes-compra: Eliminación múltiple iniciada a las {ahora_naive().isoformat()}")
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
        resultados = []
        contadores = {"eliminadas": 0, "errores": 0, "no_encontradas": 0, "no_permitidas": 0}

        with get_db_connection_context() as conn:
            oc_repo = OrdenCompraRepository(conn)
            for oc_id_item in oc_ids_list:
                resultado, categoria = _eliminar_una_oc(oc_repo, oc_id_item)
                resultados.append(resultado)
                contadores[categoria] += 1

        eliminadas = contadores["eliminadas"]
        errores = contadores["errores"]
        no_encontradas = contadores["no_encontradas"]
        no_permitidas = contadores["no_permitidas"]

        # Determinar status general
        status_general = "success" if errores == 0 and no_encontradas == 0 and no_permitidas == 0 else "partial"
        if eliminadas == 0:
            status_general = "error"

        mensaje = _construir_mensaje_delete_multiple(
            eliminadas, len(oc_ids_list), no_encontradas, no_permitidas, errores
        )

        logger.info("=" * 70)
        logger.info("✅ DELETE /ordenes-compra completado:")
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


async def _get_orden_compra_detalles_handler(request, oc_id):
    source = get_source_from_headers(request)

    logger.info(f"📋 GET /ordenes-compra/{oc_id}/detalles: Consulta iniciada")

    try:
        detalles = await asyncio.to_thread(_obtener_detalles_oc, oc_id)

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


async def _get_orden_compra_integracion_sap_handler(request, oc_id):
    source = get_source_from_headers(request)

    try:
        data = await asyncio.to_thread(_fetch_integracion_sap, oc_id)
    except Exception as e:
        logger.error(f"❌ Error al obtener integración SAP de OC {oc_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener detalle de integración SAP: {str(e)}"
        )

    if data is None:
        raise HTTPException(
            status_code=404,
            detail="No se encontró registro de integración SAP para esta orden de compra. Solo existe para OCs ya enviadas a SAP."
        )

    return JSONResponse(
        status_code=200,
        content=data,
        headers={"X-Source": source, "X-Endpoint": "GET-ORDEN-COMPRA-INTEGRACION-SAP"}
    )


async def _get_orden_compra_pdf_handler(request, oc_id):
    source = get_source_from_headers(request)

    logger.info(f"📄 GET /ordenes-compra/{oc_id}/pdf: Generación de PDF iniciada")

    try:
        pdf_bytes, oc_cabecera, error = await asyncio.to_thread(_generar_pdf_oc, oc_id)

        if error:
            raise HTTPException(status_code=404, detail=error)

        if oc_cabecera is None or pdf_bytes is None:
            raise HTTPException(status_code=404, detail=_MSG_OC_NO_ENCONTRADA)

        # Nombre del archivo
        numero_oc_sap = oc_cabecera.get("numero_oc_sap", "SIN_NUMERO")
        nombre_archivo = f"ODC_{numero_oc_sap}.pdf"

        logger.info(f"✅ GET /ordenes-compra/{oc_id}/pdf: PDF generado exitosamente ({len(pdf_bytes)} bytes)")

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{nombre_archivo}"',
                "Content-Length": str(len(pdf_bytes)),
                "X-Source": source,
                "X-Endpoint": "GET-ORDEN-COMPRA-PDF",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al generar PDF de OC {oc_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al generar PDF de la orden de compra: {str(e)}"
        )


async def _reintentar_st_handler(request, oc_id, user):
    source = get_source_from_headers(request)
    username = user.get("username", "unknown") if user else "unknown"

    try:
        out = await asyncio.to_thread(_retry_st_only, oc_id, username)
        return JSONResponse(
            status_code=int(out.get("status_code", 200)),
            content=out.get("body", {}),
            headers={"X-Source": source, "X-Endpoint": "POST-ORDEN-COMPRA-REINTENTAR-ST"},
        )
    except Exception as e:
        logger.error(f"❌ Error al reintentar ST de OC {oc_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al reintentar Solicitudes de Transferencia: {str(e)}"
        )


async def _actualizar_sku_detalle_handler(request, oc_id, oc_detalle_id, nuevo_sku, validar_en_sap, user):
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
            sku_validado_en_sap = await _validar_sku_sap(nuevo_sku_clean)
            if not sku_validado_en_sap:
                raise HTTPException(
                    status_code=404,
                    detail=f"El SKU '{nuevo_sku_clean}' no existe en SAP o no está disponible"
                )
            logger.info(f"✅ SKU validado en SAP: {nuevo_sku_clean}")

        # Ejecutar actualización en thread pool
        sku_anterior = await asyncio.to_thread(
            _obtener_y_actualizar_sku, oc_id, oc_detalle_id, nuevo_sku_clean
        )

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
        _: None = Depends(require_any_permission([_PERM_ODCSAP, _PERM_MABEL]))
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
        return await _get_historial_ordenes_handler(
            request, oc_id, referencia_despacho, proveedor,
            fecha_desde, fecha_hasta, nivel_log, success, limit, offset
        )

    @app.get("/ordenes-compra", tags=["Órdenes de Compra"])
    async def get_ordenes_compra(
        request: Request,
        page: int = Query(1, ge=1, description="Número de página (1-based)"),
        page_size: int = Query(10, ge=1, le=100, description="Tamaño de página (snake_case)"),
        page_size_camel: Optional[int] = Query(None, ge=1, le=100, alias="pageSize", description="Tamaño de página (camelCase)"),
        estado: Optional[str] = Query(None, description="Filtrar por estado (PENDIENTE, ENVIADA, ERROR)"),
        referencia_despacho: Optional[str] = Query(None, description="Búsqueda parcial por referencia de despacho"),
        numero_oc_sap: Optional[str] = Query(None, description="Búsqueda parcial por número OC SAP / doc_entry"),
        search: Optional[str] = Query(None, description="Búsqueda parcial en referencia o número SAP"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_ODCSAP, _PERM_MABEL]))
    ):
        """
        Endpoint ORDENES-COMPRA: Lista órdenes de compra con paginación en servidor.

        **Query Parameters:**
        - `page` (int, default: 1) - Número de página
        - `pageSize` o `page_size` (int, default: 50, máx. 100) - Registros por página
        - `estado` (string, opcional) - Filtrar por estado (PENDIENTE, ENVIADA, ERROR)
        - `referencia_despacho`, `numero_oc_sap`, `search` - Filtros opcionales en servidor

        **Ejemplo:**
        ```
        GET /ordenes-compra?estado=PENDIENTE&page=1&pageSize=20
        ```

        **Respuesta (compatible con frontend / pedidos confirmados):**
        ```json
        {
          "status": "success",
          "data": [...],
          "total": 150,
          "page": 1,
          "pageSize": 20,
          "totalPages": 8,
          "metadata": {
            "count": 20,
            "estado_filter": "PENDIENTE"
          }
        }
        ```
        """
        return await _get_ordenes_compra_handler(
            request, page, page_size, page_size_camel, estado,
            referencia_despacho, numero_oc_sap, search
        )

    @app.get("/ordenes-compra/logs", tags=["Órdenes de Compra"])
    async def get_ordenes_compra_logs(
        request: Request,
        page: Optional[int] = Query(1, description="Número de página (empezando en 1)"),
        page_size: Optional[int] = Query(50, alias="pageSize", description="Tamaño de página (registros por página)"),
        oc_id: Optional[str] = Query(None, description="Filtrar por UUID de orden de compra"),
        referencia_despacho: Optional[str] = Query(None, description="Filtrar por referencia de despacho"),
        proveedor: Optional[str] = Query(None, description="Filtrar por código de proveedor"),
        fecha_desde: Optional[str] = Query(None, description="Filtrar desde fecha (YYYY-MM-DD)"),
        fecha_hasta: Optional[str] = Query(None, description="Filtrar hasta fecha (YYYY-MM-DD)"),
        nivel_log: Optional[str] = Query(None, description="Filtrar por nivel (INFO, ERROR, WARNING)"),
        success: Optional[bool] = Query(None, description="Filtrar por éxito (true) o error (false)"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
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
        return await _get_ordenes_compra_logs_handler(
            request, page, page_size, oc_id, referencia_despacho,
            proveedor, fecha_desde, fecha_hasta, nivel_log, success
        )

    @app.delete("/ordenes-compra/{oc_id}", tags=["Órdenes de Compra"])
    async def delete_orden_compra(
        request: Request,
        oc_id: str,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
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
        return await _delete_orden_compra_handler(request, oc_id)

    @app.delete("/ordenes-compra", tags=["Órdenes de Compra"])
    async def delete_ordenes_compra(
        request: Request,
        oc_id: Optional[List[str]] = Query(None, description="UUID(s) de la(s) orden(es) de compra a eliminar. Puede especificarse múltiples veces (ej: ?oc_id=id1&oc_id=id2)."),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
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
        return await _delete_ordenes_compra_handler(request, oc_id)

    @app.get("/ordenes-compra/{oc_id}/detalles", tags=["Órdenes de Compra"])
    async def get_orden_compra_detalles(
        request: Request,
        oc_id: str = Path(..., description=_DESC_OC_ID),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
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
        return await _get_orden_compra_detalles_handler(request, oc_id)

    @app.get("/ordenes-compra/{oc_id}/integracion-sap", tags=["Órdenes de Compra"])
    async def get_orden_compra_integracion_sap(
        request: Request,
        oc_id: str = Path(..., description=_DESC_OC_ID),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_ODCSAP, _PERM_MABEL]))
    ):
        """
        Obtiene el detalle de integración SAP de una OC (envío a SAP + solicitudes de transferencia).
        Misma estructura que la respuesta de proceso-completo-sap, para reutilizar en el modal
        cuando se abre desde el botón "Num ODC" en la tabla.

        **Path Parameters:**
        - `oc_id` (string, requerido) - UUID de la orden de compra

        **Respuesta:** envio_sap (con numero_oc_sap, doc_entry, doc_num, solicitudes_transferencia)
        y solicitudes_transferencia (resultados, itrs_por_tienda) para mostrar la sección ITR completa.
        """
        return await _get_orden_compra_integracion_sap_handler(request, oc_id)

    @app.get("/ordenes-compra/{oc_id}/pdf", tags=["Órdenes de Compra"])
    async def get_orden_compra_pdf(
        request: Request,
        oc_id: str = Path(..., description=_DESC_OC_ID),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_ODCSAP, _PERM_MABEL]))
    ):
        """
        Endpoint para descargar el PDF de una orden de compra.

        Genera y retorna el documento PDF de la ODC con toda la información
        de cabecera, detalles de productos, resumen financiero y firmas.

        **Path Parameters:**
        - `oc_id` (string, requerido) - UUID de la orden de compra

        **Ejemplo de uso:**
        ```
        GET /ordenes-compra/DD7D7A51-9E57-44D4-9A8F-4A05427A8325/pdf
        ```
        """
        return await _get_orden_compra_pdf_handler(request, oc_id)

    @app.post("/ordenes-compra/{oc_id}/reintentar-st", tags=["Órdenes de Compra"])
    async def reintentar_solicitudes_transferencia(
        request: Request,
        oc_id: str = Path(..., description=_DESC_OC_ID),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_ODCSAP, _PERM_MABEL]))
    ):
        """
        Reintenta únicamente Solicitudes de Transferencia (ITR) fallidas para una ODC ya enviada.

        Reglas:
        - No reenvía ODC.
        - Solo procesa tiendas fallidas del último batch ST de la OC.
        """
        return await _reintentar_st_handler(request, oc_id, user)

    @app.put("/ordenes-compra/{oc_id}/detalle/{oc_detalle_id}/sku", tags=["Órdenes de Compra"])
    async def actualizar_sku_detalle(
        request: Request,
        oc_id: str = Path(..., description=_DESC_OC_ID),
        oc_detalle_id: str = Path(..., description="UUID del detalle de orden de compra"),
        nuevo_sku: str = Body(..., embed=True, description="Nuevo SKU (ItemCode) de SAP"),
        validar_en_sap: bool = Body(True, embed=True, description="Validar que el SKU exista en SAP antes de actualizar"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
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
        return await _actualizar_sku_detalle_handler(
            request, oc_id, oc_detalle_id, nuevo_sku, validar_en_sap, user
        )
