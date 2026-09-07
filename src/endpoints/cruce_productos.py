"""
Endpoint para realizar cruce de productos entre MBA3 y SAP.
"""

import logging
import re
import pyodbc
import asyncio
import time
import json
from datetime import datetime
from typing import Any, Dict, Optional

from src.utils.timezone import ahora_naive
from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import StreamingResponse

from src.database.services.cruce_productos_service import CruceProductosService
from src.database.services.sugerencias_homologacion_service import SugerenciasHomologacionService
from src.database.services.producto_staging_sync_service import ProductoStagingSyncService
from src.database.services.proceso_estado_service import ProcesoEstadoService
from src.database.repositories.sync_control_repository import SyncControlRepository
from src.security.jwt_auth import verify_jwt_token, require_permission
from src.config import SAP_LINKED_SERVER, SAP_DATABASE, SAP_USE_MIDDLEWARE
from src.database.connection import get_sap_db_connection, get_db_connection
from src.database.clients.sap_service_layer_client import SAPServiceLayerClient

logger = logging.getLogger(__name__)

_PERM_MABEL = 'mabel.view'
_MSG_SKU_VACIO = "SKU no puede estar vacío"
_MSG_SKU_INVALIDO = (
    "SKU contiene caracteres no permitidos. "
    "Solo se permiten letras, números, guiones, puntos y espacios."
)
_SKU_PATTERN = re.compile(r'^[A-Za-z0-9.\- ]{1,50}$')


def _validar_sku(sku_clean: str) -> None:
    """Lanza HTTPException 400 si el SKU está vacío o tiene caracteres inválidos."""
    if not sku_clean:
        raise HTTPException(status_code=400, detail=_MSG_SKU_VACIO)
    if not _SKU_PATTERN.match(sku_clean):
        raise HTTPException(status_code=400, detail=_MSG_SKU_INVALIDO)


async def _realizar_cruce_productos_handler():
    try:
        logger.info("🔍 Iniciando cruce de productos MBA3 vs SAP...")
        service = CruceProductosService()
        resultado = service.realizar_cruce()
        return {
            "status": "success",
            "data": resultado,
            "message": "Cruce de productos completado exitosamente"
        }
    except Exception as e:
        logger.error(f"❌ Error al realizar cruce de productos: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al realizar cruce: {str(e)}")


async def _obtener_sugerencias_homologacion_handler():
    try:
        logger.info("🔍 Obteniendo sugerencias de homologación...")

        # ✅ CORRECTO: Buscar último cruce completado en Redis (O(1))
        estado_service = ProcesoEstadoService()
        ultimo_estado = estado_service.obtener_ultimo_completado(max_age_minutes=15)

        if not ultimo_estado or "resultado" not in ultimo_estado:
            # ✅ AJUSTE 3: Error 412 bien documentado
            logger.warning("⚠️ No hay cruce reciente para generar sugerencias")
            raise HTTPException(
                status_code=412,  # Precondition Failed
                detail={
                    "error": "no_cruce_reciente",
                    "message": "No existe un cruce reciente. Ejecute el cruce primero usando POST /cruce-productos/iniciar",
                    "action_required": "Ejecutar cruce primero",
                    "endpoint": "/cruce-productos/iniciar",
                    "ttl_minutes": 15
                }
            )

        cruce = ultimo_estado["resultado"]

        # Obtener datos del cruce
        productos_solo_mba3 = cruce.get("solo_en_mba3", [])

        # ✅ AJUSTE 2: Usar productos_sap_base (payload reducido)
        productos_sap = cruce.get("productos_sap_base", [])

        if not productos_sap:
            # Fallback: si no están guardados, obtenerlos (solo para compatibilidad)
            logger.warning("⚠️ productos_sap_base no encontrados en resultado, obteniendo...")
            cruce_service = CruceProductosService()
            productos_sap_completos = cruce_service.obtener_productos_sap()
            # Convertir al formato esperado
            productos_sap = [
                {
                    "item_code": p.get("item_code", ""),
                    "item_name": p.get("item_name", ""),
                    "item_code_normalizado": p.get("item_code_normalizado", ""),
                    "active": p.get("active", True)
                }
                for p in productos_sap_completos
            ]

        # Obtener códigos ya homologados
        homologados_exactos = cruce.get("homologados_exactos", [])
        homologables = cruce.get("homologables", [])

        productos_ya_homologados = set()
        for item in homologados_exactos:
            codigo_sap = item.get("codigo_sap")
            if codigo_sap:
                productos_ya_homologados.add(codigo_sap)
        for item in homologables:
            codigo_sap = item.get("codigo_sap")
            if codigo_sap:
                productos_ya_homologados.add(codigo_sap)

        # Generar sugerencias
        sugerencias_service = SugerenciasHomologacionService()
        sugerencias = sugerencias_service.obtener_sugerencias(
            productos_solo_mba3,
            productos_sap,
            productos_ya_homologados
        )

        # Calcular edad del cruce usado
        completed_at_str = ultimo_estado.get("completed_at")
        age_minutes = None
        if completed_at_str:
            completed_at = datetime.fromisoformat(completed_at_str)
            age_minutes = round(
                (ahora_naive() - completed_at).total_seconds() / 60, 1
            )

        return {
            "status": "success",
            "data": sugerencias,
            "message": f"Sugerencias generadas para {len(sugerencias)} productos",
            "metadata": {
                "total_productos": len(sugerencias),
                "productos_con_sugerencias": sum(1 for s in sugerencias if s["sugerencias"]),
                "productos_sin_sugerencias": sum(1 for s in sugerencias if not s["sugerencias"]),
                "min_score": SugerenciasHomologacionService.MIN_SCORE_SUGERENCIA,
                "max_sugerencias_por_producto": SugerenciasHomologacionService.MAX_SUGERENCIAS_POR_PRODUCTO,
                "cruce_usado": {
                    "process_id": ultimo_estado.get("process_id"),
                    "completed_at": completed_at_str,
                    "age_minutes": age_minutes
                }
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al obtener sugerencias: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al obtener sugerencias: {str(e)}")


async def _sincronizar_maestros_mba3_handler():
    try:
        logger.info("🔄 Iniciando sincronización manual de maestros MBA3 (modo reemplazo completo)...")
        service = ProductoStagingSyncService()
        # Siempre forzar sincronización completa para reemplazar información
        # batch_size=4000 para traer 4000 elementos en un solo lote
        resultado = service.sync_mba3_products(batch_size=4000, force_full_sync=True)
        return {
            "status": "success",
            "data": resultado,
            "message": "Sincronización MBA3 completada exitosamente (información reemplazada)"
        }
    except Exception as e:
        logger.error(f"❌ Error al sincronizar maestros MBA3: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al sincronizar MBA3: {str(e)}")


async def _sincronizar_maestros_sap_handler():
    try:
        logger.info("🔄 Iniciando sincronización manual de maestros SAP...")
        service = ProductoStagingSyncService()
        resultado = service.sync_sap_products()
        return {
            "status": "success",
            "data": resultado,
            "message": "Sincronización SAP completada exitosamente"
        }
    except Exception as e:
        logger.error(f"❌ Error al sincronizar maestros SAP: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al sincronizar SAP: {str(e)}")


async def _sincronizar_maestros_handler(force_full: bool):
    try:
        logger.info(f"🔄 Iniciando sincronización manual de maestros (MBA3 y SAP)... force_full={force_full}")
        service = ProductoStagingSyncService()
        resultado = service.sync_all(force_full_sync=force_full)
        return {
            "status": "success",
            "data": resultado,
            "message": "Sincronización completada exitosamente"
        }
    except Exception as e:
        logger.error(f"❌ Error al sincronizar maestros: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al sincronizar: {str(e)}")


async def _ejecutar_query_mba3(mba3_service, query: str, sku_clean: str):
    """Ejecuta la consulta MBA3 en thread pool con timeout. Lanza HTTPException ante timeout/error."""
    start_time = time.time()
    try:
        # Timeout de 50 segundos para dar margen a:
        # - Delays de JWT (hasta 5s: 2s post-login + 3s si JWT reciente)
        # - Consultas que pueden tardar 30-40s en MBA3
        # El frontend tiene timeout de 60s, así que 50s da margen suficiente
        result = await asyncio.wait_for(
            asyncio.to_thread(mba3_service.execute_query, query),
            timeout=50.0
        )
        elapsed_time = time.time() - start_time
        logger.info(f"⏱️ Consulta MBA3 completada en {elapsed_time:.2f}s para SKU: {sku_clean}")
        return result
    except asyncio.TimeoutError:
        elapsed_time = time.time() - start_time
        logger.error(
            f"❌ Timeout al buscar SKU en MBA3: {sku_clean} "
            f"(más de 50 segundos, tiempo transcurrido: {elapsed_time:.2f}s)"
        )
        raise HTTPException(
            status_code=504,
            detail="Timeout al buscar SKU en MBA3. La consulta tardó más de 50 segundos. Verifique la conexión con MBA3."
        )
    except Exception as e:
        logger.error(f"❌ Error al ejecutar consulta MBA3: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al buscar SKU en MBA3: {str(e)}")


def _normalizar_productos_mba3(result) -> list:
    """Normaliza la respuesta del API MBA3 a una lista de productos."""
    if isinstance(result, list):
        return result
    if not isinstance(result, dict):
        return []
    productos = []
    for value in result.values():
        if isinstance(value, list):
            productos = value
            break
    if not productos and result:
        productos = [result]
    return productos


def _mapear_producto_info_mba3(producto: dict, sku_clean: str) -> dict:
    """Mapea los campos del producto MBA3 (múltiples formatos) al formato esperado por el frontend."""
    return {
        "codigo": producto.get("PRODUCT_ID") or producto.get("product_id") or producto.get("Product_ID") or sku_clean,
        "nombre": producto.get("PRODUCT_NAME") or producto.get("product_name") or producto.get("Product_Name") or "",
        "corp": producto.get("CORP") or producto.get("corp") or producto.get("Corp") or "",
        "grupo_prenda": producto.get("GrupoPrenda") or producto.get("grupoPrenda") or producto.get("grupo_prenda") or "",
        "talla": producto.get("Talla") or producto.get("talla") or "",
        "presentacion": producto.get("PRESENTACION") or producto.get("presentacion") or producto.get("Presentacion") or "",
        "group_code": producto.get("GROUP_CODE") or producto.get("group_code") or producto.get("Group_Code") or "",
        "tipo_origen": producto.get("Tipo_Origen") or producto.get("tipo_origen") or "",
        "descontinuado": producto.get("Descontinuado") or producto.get("descontinuado") or "",
        "inactive": producto.get("INACTIVE") or producto.get("inactive") or producto.get("Inactive") or ""
    }


def _formatear_sugerencias_sap(productos_sap: list, producto_info: dict, sku_clean: str, limite_sugerencias: int) -> list:
    """Calcula y formatea las sugerencias SAP a partir de los productos SAP similares."""
    producto_mba3_ref = {
        "codigo_mba3": producto_info.get("codigo", sku_clean),
        "nombre_mba3": producto_info.get("nombre", ""),
    }
    productos_sap_formateados = [
        {
            "item_code": prod.get("ItemCode", ""),
            "item_name": prod.get("ItemName", ""),
            "pack": prod.get("U_IXX_PACK", ""),
            "active": prod.get("validFor", "N").upper() == "Y"
        }
        for prod in productos_sap
    ]

    sugerencias_service = SugerenciasHomologacionService()
    sugerencias = sugerencias_service.buscar_sugerencias_para_producto(
        producto_mba3=producto_mba3_ref,
        productos_sap=productos_sap_formateados,
        productos_ya_homologados=set()  # No excluir ningún producto
    )

    sugerencias_formateadas = []
    productos_sap_dict = {p.get("ItemCode"): p for p in productos_sap}
    for sugerencia in sugerencias:
        codigo_sap = sugerencia.get("codigo_sap")
        producto_sap = productos_sap_dict.get(codigo_sap, {})
        valid_for = producto_sap.get("validFor", "N")
        estado = "activo" if valid_for.upper() == "Y" else "inactivo"
        sugerencias_formateadas.append({
            "codigo": codigo_sap,
            "nombre": producto_sap.get("ItemName", ""),
            "pack": producto_sap.get("U_IXX_PACK", ""),
            "group_code": producto_sap.get("ItmsGrpCod"),
            "group_name": producto_sap.get("ItmsGrpNam", ""),
            "estado": estado,
            "valid_for": valid_for,
            "score": sugerencia.get("score", 0.0),
            "score_porcentaje": round(sugerencia.get("score", 0.0) * 100, 1),
            "motivos": sugerencia.get("motivos", [])
        })

    return sugerencias_formateadas[:limite_sugerencias]


async def _agregar_sugerencias_sap(respuesta: dict, producto_info: dict, sku_clean: str, limite_sugerencias: int) -> None:
    """Agrega (in-place) sugerencias SAP a la respuesta. Nunca falla la respuesta principal."""
    logger.info(f"🔍 Buscando sugerencias SAP para SKU MBA3: {sku_clean}")
    try:
        from src.database.clients.sap_client import SAPClient
        sap_client = SAPClient()

        def buscar_sugerencias_en_sap():
            return sap_client.buscar_skus_similares(
                sku_referencia=sku_clean,
                limite=limite_sugerencias * 2,  # Buscar más para tener mejor selección
                solo_activos=True
            )

        try:
            # Ejecutar búsqueda en thread pool con timeout
            productos_sap = await asyncio.wait_for(
                asyncio.to_thread(buscar_sugerencias_en_sap),
                timeout=50.0
            )
            if productos_sap:
                sugerencias_formateadas = _formatear_sugerencias_sap(
                    productos_sap, producto_info, sku_clean, limite_sugerencias
                )
                respuesta["sugerencias_sap"] = sugerencias_formateadas
                respuesta["total_sugerencias_sap"] = len(sugerencias_formateadas)
                logger.info(f"✅ Encontradas {len(sugerencias_formateadas)} sugerencias SAP para {sku_clean}")
            else:
                respuesta["sugerencias_sap"] = []
                respuesta["total_sugerencias_sap"] = 0
                logger.info(f"⚠️ No se encontraron sugerencias SAP para {sku_clean}")
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Timeout al buscar sugerencias SAP para {sku_clean}")
            respuesta["sugerencias_sap"] = []
            respuesta["total_sugerencias_sap"] = 0
            respuesta["sugerencias_sap_timeout"] = True
        except Exception as e:
            logger.warning(f"⚠️ Error al buscar sugerencias SAP para {sku_clean}: {e}")
            respuesta["sugerencias_sap"] = []
            respuesta["total_sugerencias_sap"] = 0
            respuesta["sugerencias_sap_error"] = str(e)
    except Exception as e:
        # Si hay error al buscar sugerencias, no fallar la respuesta principal
        logger.warning(f"⚠️ Error al buscar sugerencias SAP: {e}", exc_info=True)
        respuesta["sugerencias_sap"] = []
        respuesta["total_sugerencias_sap"] = 0
        respuesta["sugerencias_sap_error"] = str(e)


async def _buscar_sku_mba3_handler(sku: str, incluir_sugerencias_sap: bool, limite_sugerencias: int):
    try:
        sku_clean = sku.strip()
        _validar_sku(sku_clean)

        logger.info(f"🔍 Buscando SKU en MBA3: {sku_clean}")

        # Escapar comillas simples para la query (aunque ya está validado)
        # Nota: MBA3 usa API REST que parsea SQL, no soporta parámetros preparados tradicionales
        sku_escaped = sku_clean.replace("'", "''")

        # Consulta optimizada: solo campos usados por el frontend + LIMIT 1
        # Reducción de 18 a 10 campos (44% menos datos)
        # Mantiene simplicidad (sin filtros) para obtener cualquier producto
        query = (
            "SELECT PRODUCT_ID, PRODUCT_NAME, CORP, GrupoPrenda, Talla, PRESENTACION, "
            "GROUP_CODE, Tipo_Origen, Descontinuado, INACTIVE "
            "FROM INVT_FICHA_PRINCIPAL "
            f"WHERE PRODUCT_ID = '{sku_escaped}' "
            "LIMIT 1"
        )

        # Ejecutar en thread pool para no bloquear el event loop
        from src.services.mba3_service import MBA3Service
        mba3_service = MBA3Service()

        result = await _ejecutar_query_mba3(mba3_service, query, sku_clean)

        productos = _normalizar_productos_mba3(result)
        if not productos:
            return {
                "status": "not_found",
                "message": f"SKU no encontrado en MBA3: {sku_clean}",
                "sku": sku_clean,
                "data": None
            }

        producto_info = _mapear_producto_info_mba3(productos[0], sku_clean)

        # Preparar respuesta base
        respuesta = {
            "status": "success",
            "message": "SKU encontrado en MBA3",
            "sku": sku_clean,
            "data": producto_info
        }

        # Si se solicita, buscar sugerencias similares en SAP
        if incluir_sugerencias_sap:
            await _agregar_sugerencias_sap(respuesta, producto_info, sku_clean, limite_sugerencias)

        return respuesta

    except HTTPException:
        # Re-lanzar excepciones HTTP (validaciones)
        raise
    except Exception as e:
        logger.error(f"❌ Error al buscar SKU en MBA3: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al buscar SKU en MBA3: {str(e)}")


async def _ejecutar_query_sap(query: str, sku_clean: str):
    """Ejecuta la consulta SAP (OPENQUERY) en thread pool con timeout. Lanza HTTPException ante error."""
    def execute_sap_query():
        conn = None
        try:
            conn = get_sap_db_connection()
            cursor = conn.cursor()
            cursor.execute(query)
            return cursor.fetchone()
        finally:
            if conn:
                try:
                    cursor.close()
                    conn.close()
                except Exception:
                    pass

    try:
        # Timeout de 50 segundos (consistente con MBA3)
        # SAP suele ser más rápido, pero mantener mismo timeout para consistencia
        # El frontend tiene timeout de 60s, así que 50s da margen suficiente
        return await asyncio.wait_for(
            asyncio.to_thread(execute_sap_query),
            timeout=50.0
        )
    except asyncio.TimeoutError:
        logger.error(f"❌ Timeout al buscar SKU en SAP: {sku_clean} (más de 50 segundos)")
        raise HTTPException(
            status_code=504,
            detail="Timeout al buscar SKU en SAP. La consulta tardó más de 50 segundos. Verifique la conexión con SAP."
        )
    except pyodbc.Error as e:
        logger.error(f"❌ Error de base de datos al consultar SAP: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al consultar SAP: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Error al ejecutar consulta SAP: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al buscar SKU en SAP: {str(e)}")


def _mapear_producto_info_sap(result, sku_clean: str) -> dict:
    """Normaliza una fila cruda de SAP al formato de respuesta esperado."""
    valid_for_raw = result[5] if len(result) > 5 and result[5] is not None else 'N'
    valid_for = str(valid_for_raw).upper() == 'Y'
    return {
        "codigo": result[0] if result[0] else sku_clean,
        "nombre": result[1] if result[1] else "",
        "pack": result[2] if result[2] else "",
        "group_code": result[3] if result[3] else None,
        "card_code": result[4] if result[4] else None,
        "valid_for": valid_for_raw,
        "estado": "activo" if valid_for else "inactivo"
    }


def _mapear_item_middleware_a_producto(item: Dict[str, Any], sku_clean: str) -> Dict[str, Any]:
    """Traduce la respuesta de GET /items/{code} del middleware al formato de este endpoint."""
    valid_for = (item.get("Valid") or "N") == "tYES"
    return {
        "codigo": item.get("ItemCode") or sku_clean,
        "nombre": item.get("ItemName") or "",
        "pack": item.get("U_IXX_PACK") or "",
        "group_code": item.get("ItmsGrpCod"),
        "card_code": item.get("CardCode"),
        # Normalizado al formato del canal OPENQUERY ("Y"/"N") para que el
        # campo crudo sea idéntico entre canales de cara al frontend.
        "valid_for": "Y" if valid_for else "N",
        "estado": "activo" if valid_for else "inactivo",
    }


async def _buscar_sku_via_middleware(sku_clean: str) -> Optional[Dict[str, Any]]:
    """
    Busca el SKU vía middleware (GET /api/v1/items/{code}).

    Returns la respuesta final del endpoint si el middleware pudo resolverlo
    (encontrado o no encontrado), o None si no está disponible y el caller
    debe hacer fallback a OPENQUERY.
    """
    client = SAPServiceLayerClient()
    item = await asyncio.to_thread(client.get_item, sku_clean)

    if item is None:
        return None  # sin conexión al middleware: fallback

    if item.get("_error"):
        if item.get("_error_type") == "no_existe":
            return {
                "status": "not_found",
                "message": f"SKU no encontrado en SAP: {sku_clean}",
                "sku": sku_clean,
                "data": None,
            }
        return None  # otro error del middleware: fallback a OPENQUERY

    return {
        "status": "success",
        "message": "SKU encontrado en SAP",
        "sku": sku_clean,
        "data": _mapear_item_middleware_a_producto(item, sku_clean),
    }


async def _buscar_sku_via_openquery(sku_clean: str) -> Dict[str, Any]:
    """Busca el SKU directo en SAP HANA por OPENQUERY (vía por defecto / fallback)."""
    try:
        # Escapar comillas simples para la query (aunque ya está validado)
        # En OPENQUERY, las comillas simples dentro de la query remota se escapan duplicándolas
        sku_escaped = sku_clean.replace("'", "''")

        # Consulta directa a SAP usando OPENQUERY
        # CORRECCIÓN: El formato correcto para OPENQUERY es usar comillas simples dobles ('')
        # dentro de la query remota para representar una comilla simple
        query = f"""
        SELECT
            T0."ItemCode",
            T0."ItemName",
            T0."U_IXX_PACK",
            T0."ItmsGrpCod",
            T0."CardCode",
            T0."validFor"
        FROM OPENQUERY([{SAP_LINKED_SERVER}], '
            SELECT
                "ItemCode",
                "ItemName",
                "U_IXX_PACK",
                "ItmsGrpCod",
                "CardCode",
                "validFor"
            FROM "{SAP_DATABASE}"."OITM"
            WHERE "ItemCode" = ''{sku_escaped}''
        ') T0;
        """

        result = await _ejecutar_query_sap(query, sku_clean)

        if not result:
            return {
                "status": "not_found",
                "message": f"SKU no encontrado en SAP: {sku_clean}",
                "sku": sku_clean,
                "data": None
            }

        producto_info = _mapear_producto_info_sap(result, sku_clean)

        return {
            "status": "success",
            "message": "SKU encontrado en SAP",
            "sku": sku_clean,
            "data": producto_info
        }

    except HTTPException:
        # Re-lanzar excepciones HTTP (validaciones)
        raise
    except Exception as e:
        logger.error(f"❌ Error al buscar SKU en SAP: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al buscar SKU en SAP: {str(e)}")


async def _buscar_sku_sap_handler(sku: str):
    try:
        sku_clean = sku.strip()
        _validar_sku(sku_clean)

        logger.info(f"🔍 Buscando SKU en SAP: {sku_clean}")

        if SAP_USE_MIDDLEWARE:
            resultado = await _buscar_sku_via_middleware(sku_clean)
            if resultado is not None:
                return resultado
            logger.warning(
                f"⚠️ Middleware no disponible para SKU {sku_clean}; fallback a OPENQUERY"
            )

        return await _buscar_sku_via_openquery(sku_clean)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al buscar SKU en SAP: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al buscar SKU en SAP: {str(e)}")


async def _buscar_sugerencias_sku_sap_handler(sku: str, limite: int):
    try:
        sku_clean = sku.strip()
        _validar_sku(sku_clean)

        logger.info(f"🔍 Buscando sugerencias para SKU en SAP: {sku_clean}")

        # Importar cliente SAP y servicio de sugerencias
        from src.database.clients.sap_client import SAPClient
        sap_client = SAPClient()
        sugerencias_service = SugerenciasHomologacionService()

        # Buscar SKUs similares en SAP
        def buscar_en_sap():
            return sap_client.buscar_skus_similares(
                sku_referencia=sku_clean,
                limite=limite * 2,  # Buscar más para tener mejor selección
                solo_activos=True
            )

        try:
            # Ejecutar búsqueda en thread pool con timeout
            productos_sap = await asyncio.wait_for(
                asyncio.to_thread(buscar_en_sap),
                timeout=50.0
            )
        except asyncio.TimeoutError:
            logger.error(f"❌ Timeout al buscar sugerencias SKU en SAP: {sku_clean}")
            raise HTTPException(
                status_code=504,
                detail="Timeout al buscar sugerencias en SAP. La consulta tardó más de 50 segundos."
            )

        if not productos_sap:
            return {
                "status": "not_found",
                "sku_referencia": sku_clean,
                "message": f"No se encontraron SKUs similares en SAP para: {sku_clean}",
                "sugerencias": [],
                "total_encontrados": 0
            }

        # Preparar producto de referencia (simulando estructura MBA3 para usar servicio de sugerencias)
        producto_referencia = {
            "codigo_mba3": sku_clean,
            "nombre_mba3": "",  # No tenemos nombre, pero el servicio puede funcionar solo con código
        }

        # Convertir productos SAP al formato esperado por el servicio
        productos_sap_formateados = []
        for prod in productos_sap:
            productos_sap_formateados.append({
                "item_code": prod.get("ItemCode", ""),
                "item_name": prod.get("ItemName", ""),
                "pack": prod.get("U_IXX_PACK", ""),
                "active": prod.get("validFor", "N").upper() == "Y"
            })

        # Usar servicio de sugerencias para calcular scores y motivos
        sugerencias = sugerencias_service.buscar_sugerencias_para_producto(
            producto_mba3=producto_referencia,
            productos_sap=productos_sap_formateados,
            productos_ya_homologados=set()  # No excluir ningún producto
        )

        # Formatear respuesta con información adicional de SAP
        sugerencias_formateadas = []
        productos_sap_dict = {p.get("ItemCode"): p for p in productos_sap}

        for sugerencia in sugerencias:
            codigo_sap = sugerencia.get("codigo_sap")
            producto_sap = productos_sap_dict.get(codigo_sap, {})

            valid_for = producto_sap.get("validFor", "N")
            estado = "activo" if valid_for.upper() == "Y" else "inactivo"

            sugerencias_formateadas.append({
                "codigo": codigo_sap,
                "nombre": producto_sap.get("ItemName", ""),
                "pack": producto_sap.get("U_IXX_PACK", ""),
                "group_code": producto_sap.get("ItmsGrpCod"),
                "group_name": producto_sap.get("ItmsGrpNam", ""),
                "estado": estado,
                "valid_for": valid_for,
                "score": sugerencia.get("score", 0.0),
                "score_porcentaje": round(sugerencia.get("score", 0.0) * 100, 1),
                "motivos": sugerencia.get("motivos", [])
            })

        # Limitar a la cantidad solicitada
        sugerencias_formateadas = sugerencias_formateadas[:limite]

        return {
            "status": "success",
            "sku_referencia": sku_clean,
            "message": f"Encontradas {len(sugerencias_formateadas)} sugerencias similares",
            "sugerencias": sugerencias_formateadas,
            "total_encontrados": len(sugerencias_formateadas)
        }

    except HTTPException:
        # Re-lanzar excepciones HTTP (validaciones)
        raise
    except Exception as e:
        logger.error(f"❌ Error al buscar sugerencias SKU en SAP: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al buscar sugerencias SKU en SAP: {str(e)}")


async def _obtener_estado_sincronizacion_handler():
    try:
        conn = get_db_connection()
        try:
            sync_control_repo = SyncControlRepository(conn)

            # Obtener estado para MBA3
            estado_mba3 = sync_control_repo.get_estado_sincronizacion('MBA3')

            # Obtener estado para SAP
            estado_sap = sync_control_repo.get_estado_sincronizacion('SAP')

            return {
                "status": "success",
                "data": {
                    "mba3": {
                        "ultima_sync": estado_mba3.get("ultima_sync"),
                        "estado": estado_mba3.get("estado"),
                        "mensaje": estado_mba3.get("mensaje")
                    },
                    "sap": {
                        "ultima_sync": estado_sap.get("ultima_sync"),
                        "estado": estado_sap.get("estado"),
                        "mensaje": estado_sap.get("mensaje")
                    }
                }
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"❌ Error al obtener estado de sincronización: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al obtener estado: {str(e)}")


def _encolar_cruce_productos(user_id: str) -> dict:
    """
    Crea el registro de proceso y encola la tarea en Celery.

    Bloqueante (SQL Server + Redis): debe invocarse via asyncio.to_thread para
    no congelar el event loop si alguno de los dos responde lento.
    """
    estado_service = ProcesoEstadoService()
    process_id = estado_service.crear_proceso(user_id=user_id)
    from src.tasks.celery_cruce_productos import ejecutar_cruce_productos
    ejecutar_cruce_productos.delay(process_id, user_id)
    logger.info(f"🚀 Cruce iniciado: {process_id} (usuario: {user_id})")
    return {
        "status": "success",
        "process_id": process_id,
        "message": "Cruce iniciado. Usa GET /cruce-productos/stream/{process_id} para ver progreso."
    }


async def _iniciar_cruce_productos_handler(user: dict):
    user_id = user.get('id') or user.get('username', 'unknown')
    try:
        return await asyncio.to_thread(_encolar_cruce_productos, user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(
            "Cruce en segundo plano no disponible (%s). Ejecutando en primer plano (fallback sync).",
            e,
        )
        service = CruceProductosService()
        resultado = await asyncio.to_thread(service.realizar_cruce)
        return {
            "status": "success",
            "data": resultado,
            "message": "Cruce de productos completado exitosamente (ejecutado en primer plano)",
            "fallback": "sync",
        }


def _construir_evento_estado(estado_actual: dict) -> dict:
    """Construye el payload SSE con los campos necesarios del estado actual."""
    # Enviar solo campos necesarios (no incluir resultado completo hasta completar)
    estado_enviar = {
        "process_id": estado_actual["process_id"],
        "status": estado_actual["status"],
        "step": estado_actual["step"],
        "progress": estado_actual["progress"],
        "message": estado_actual["message"],
        "updated_at": estado_actual.get("updated_at"),
        "version": estado_actual.get("version", 0)
    }
    # Incluir data parcial si existe
    if "data" in estado_actual:
        estado_enviar["data"] = estado_actual["data"]
    # Si completó, incluir resultado completo
    if estado_actual["status"] == "completed":
        estado_enviar["resultado"] = estado_actual.get("resultado")
    # Si error, incluir error
    if estado_actual["status"] == "error":
        estado_enviar["error"] = estado_actual.get("error")
    return estado_enviar


async def _event_stream_cruce(process_id: str, request: Request, estado_service):
    """Generador de eventos SSE para el progreso del cruce."""
    ultimo_updated_at = None
    ultima_version = None

    while True:
        # Verificar si el cliente se desconectó
        if await request.is_disconnected():
            logger.info(f"🔌 Cliente desconectado del stream {process_id}")
            break

        estado_actual = estado_service.obtener_estado(process_id)

        if not estado_actual:
            yield f"data: {json.dumps({'error': 'Proceso no encontrado'})}\n\n"
            break

        # Comparar por updated_at y version (más robusto que comparar dict completo)
        updated_at = estado_actual.get("updated_at")
        version = estado_actual.get("version", 0)

        if updated_at != ultimo_updated_at or version != ultima_version:
            estado_enviar = _construir_evento_estado(estado_actual)
            yield f"data: {json.dumps(estado_enviar)}\n\n"
            ultimo_updated_at = updated_at
            ultima_version = version

        # Si completó o error, cerrar stream
        if estado_actual["status"] in ("completed", "error"):
            break

        await asyncio.sleep(1)  # Poll cada segundo


async def _stream_progreso_cruce_handler(process_id: str, request: Request, user: dict):
    try:
        estado_service = ProcesoEstadoService()

        # Validar que el proceso pertenece al usuario (opcional pero recomendado)
        estado = estado_service.obtener_estado(process_id)
        if not estado:
            raise HTTPException(status_code=404, detail="Proceso no encontrado")

        if estado.get("user_id"):
            user_id = user.get('id') or user.get('username', 'unknown')
            if estado["user_id"] != user_id:
                raise HTTPException(
                    status_code=403,
                    detail="No tienes acceso a este proceso"
                )

        return StreamingResponse(
            _event_stream_cruce(process_id, request, estado_service),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Nginx: deshabilitar buffering
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error en stream de progreso: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error en stream: {str(e)}")


async def _obtener_resultado_cruce_handler(process_id: str, user: dict):
    try:
        estado_service = ProcesoEstadoService()
        estado = estado_service.obtener_estado(process_id)

        if not estado:
            raise HTTPException(status_code=404, detail="Proceso no encontrado")

        # Validar acceso
        if estado.get("user_id"):
            user_id = user.get('id') or user.get('username', 'unknown')
            if estado["user_id"] != user_id:
                raise HTTPException(status_code=403, detail="No tienes acceso a este proceso")

        if estado["status"] == "completed":
            return {
                "status": "success",
                "process_id": process_id,
                "data": estado.get("resultado")
            }
        elif estado["status"] == "error":
            raise HTTPException(
                status_code=500,
                detail=estado.get("error", "Error desconocido")
            )
        else:
            return {
                "status": "processing",
                "process_id": process_id,
                "estado": {
                    "step": estado["step"],
                    "progress": estado["progress"],
                    "message": estado["message"],
                    "updated_at": estado.get("updated_at")
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al obtener resultado: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al obtener resultado: {str(e)}")


def register_cruce_productos_endpoints(app: FastAPI):
    """
    Registra los endpoints de cruce de productos en la aplicación FastAPI.

    Args:
        app: Instancia de FastAPI
    """

    @app.get("/cruce-productos/realizar-cruce", tags=["Cruce de Productos"])
    async def realizar_cruce_productos(
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Realiza un cruce completo entre productos de MBA3 y SAP.

        Identifica:
        - Homologados exactos: PRODUCT_ID === ItemCode
        - Homologables: normalizar(PRODUCT_ID) === normalizar(ItemCode) pero códigos diferentes
        - Solo en MBA3: productos que no tienen match en SAP
        - Solo en SAP: productos que no tienen match en MBA3

        Returns:
            Resultado del cruce con estadísticas y listas de productos
        """
        return await _realizar_cruce_productos_handler()

    @app.get("/cruce-productos/sugerencias", tags=["Cruce de Productos"])
    async def obtener_sugerencias_homologacion(
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Obtiene sugerencias de homologación para productos que no tienen match exacto.

        **IMPORTANTE - Flujo requerido:**

        1. **Primero**: Ejecutar `POST /cruce-productos/iniciar` para iniciar el cruce
        2. **Esperar**: El cruce completa (seguir progreso con `GET /cruce-productos/stream/{process_id}`)
        3. **Luego**: Llamar a este endpoint para obtener sugerencias

        **Este endpoint NO ejecuta el cruce.** Reutiliza el último cruce completado
        desde Redis. Si no existe un cruce reciente (menos de 15 minutos), devuelve error 412.

        **Códigos de respuesta:**
        - `200`: Sugerencias generadas exitosamente
        - `412`: No existe cruce reciente (ejecute el cruce primero)
        - `500`: Error al generar sugerencias

        **TTL del cruce:**
        - Los resultados del cruce se mantienen válidos por 15 minutos
        - Un nuevo cruce invalida automáticamente el anterior
        - Si se sincronizan maestros (MBA3/SAP), se recomienda ejecutar nuevo cruce

        **Características de las sugerencias:**
        - Score normalizado (0.0 - 1.0) para usar como porcentaje en frontend
        - Score original (para debugging)
        - Motivos del match (explicación del por qué se sugiere)
        - Máximo 5 sugerencias por producto MBA3
        - Solo sugerencias con score >= 0.5 (umbral mínimo)

        Returns:
            Lista de productos MBA3 con sus sugerencias ordenadas por score
        """
        return await _obtener_sugerencias_homologacion_handler()

    @app.post("/cruce-productos/sincronizar-maestros/mba3", tags=["Cruce de Productos"])
    async def sincronizar_maestros_mba3(
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Sincroniza maestros de productos MBA3 desde API a staging.

        Este endpoint SIEMPRE reemplaza la información existente:
        1. Consulta TODOS los productos MBA3 desde API (tabla INVT_FICHA_PRINCIPAL)
        2. Normaliza códigos y guarda/actualiza en producto_mba3_staging
        3. Elimina productos que ya no existen en MBA3
        4. Registra estadísticas en sync_control

        ⚠️ ADVERTENCIA: Este proceso puede tardar varios minutos dependiendo del volumen.
        No es recomendable ejecutarlo frecuentemente. Usa la tarea programada (Celery) para sincronización automática.

        Returns:
            Estadísticas de sincronización para MBA3 (incluye registros_eliminados)
        """
        return await _sincronizar_maestros_mba3_handler()

    @app.post("/cruce-productos/sincronizar-maestros/sap", tags=["Cruce de Productos"])
    async def sincronizar_maestros_sap(
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Sincroniza maestros de productos SAP desde OPENQUERY a staging.

        Este endpoint:
        1. Consulta productos SAP desde OPENQUERY
        2. Normaliza códigos y guarda/actualiza en producto_sap_staging
        3. Registra estadísticas en sync_control

        ⚠️ ADVERTENCIA: Este proceso puede tardar varios minutos dependiendo del volumen.
        No es recomendable ejecutarlo frecuentemente. Usa la tarea programada (Celery) para sincronización automática.

        Returns:
            Estadísticas de sincronización para SAP
        """
        return await _sincronizar_maestros_sap_handler()

    @app.post("/cruce-productos/sincronizar-maestros", tags=["Cruce de Productos"])
    async def sincronizar_maestros(
        force_full: bool = Query(False, description="Forzar sincronización completa desde el inicio (útil para pruebas o cuando se eliminan datos)"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Sincroniza ambos maestros de productos (MBA3 y SAP) desde ERPs a staging.

        Este endpoint ejecuta ambos procesos en secuencia:
        1. Consulta productos MBA3 desde API
        2. Consulta productos SAP desde OPENQUERY
        3. Normaliza códigos y guarda/actualiza en tablas staging
        4. Registra estadísticas en sync_control

        **Estrategia de sincronización:**
        - Por defecto: Sincronización incremental (continúa desde el último producto procesado)
        - Si la tabla está vacía o tiene < 100 productos: Sincronización completa automática
        - Con `force_full=true`: Fuerza sincronización completa desde el inicio

        ⚠️ ADVERTENCIA: Este proceso puede tardar varios minutos dependiendo del volumen.
        No es recomendable ejecutarlo frecuentemente. Usa la tarea programada (Celery) para sincronización automática.

        **Parámetros:**
        - `force_full` (bool, default: false): Si true, fuerza sincronización completa desde el inicio.
          Útil cuando eliminas datos para pruebas o necesitas re-sincronizar todo.

        **Ejemplos:**
        - Sincronización incremental: `POST /cruce-productos/sincronizar-maestros`
        - Sincronización completa: `POST /cruce-productos/sincronizar-maestros?force_full=true`

        Para sincronizar solo MBA3 o solo SAP, usar los endpoints específicos:
        - POST /cruce-productos/sincronizar-maestros/mba3
        - POST /cruce-productos/sincronizar-maestros/sap

        Returns:
            Estadísticas de sincronización para MBA3 y SAP
        """
        return await _sincronizar_maestros_handler(force_full)

    @app.get("/cruce-productos/buscar-sku/mba3", tags=["Cruce de Productos"])
    async def buscar_sku_mba3(
        sku: str = Query(..., description="SKU del producto a buscar en MBA3"),
        incluir_sugerencias_sap: bool = Query(False, description="Si True, incluye sugerencias similares de SAP basadas en el código de MBA3"),
        limite_sugerencias: int = Query(20, ge=1, le=50, description="Límite máximo de sugerencias SAP a retornar (1-50, solo si incluir_sugerencias_sap=True)"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Busca un SKU directamente en la base de datos de MBA3.

        Consulta directamente la tabla INVT_FICHA_PRINCIPAL de MBA3.

        Si `incluir_sugerencias_sap=True`, además busca sugerencias similares en SAP
        basándose en el código encontrado en MBA3. Esto es útil cuando un código existe
        en MBA3 pero no tiene equivalente exacto en SAP, permitiendo encontrar alternativas similares.

        **Ejemplo de uso:**
        - Búsqueda simple: `GET /cruce-productos/buscar-sku/mba3?sku=R225.1012.BCO`
        - Con sugerencias: `GET /cruce-productos/buscar-sku/mba3?sku=R225.1012.BCO&incluir_sugerencias_sap=true&limite_sugerencias=20`

        Args:
            sku: Código del producto (PRODUCT_ID) a buscar
            incluir_sugerencias_sap: Si True, busca sugerencias similares en SAP
            limite_sugerencias: Límite de sugerencias a retornar (solo si incluir_sugerencias_sap=True)

        Returns:
            Información del producto en MBA3 y opcionalmente sugerencias similares en SAP
        """
        return await _buscar_sku_mba3_handler(sku, incluir_sugerencias_sap, limite_sugerencias)

    @app.get("/cruce-productos/buscar-sku/sap", tags=["Cruce de Productos"])
    async def buscar_sku_sap(
        sku: str = Query(..., description="SKU (ItemCode) del producto a buscar en SAP"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Busca un SKU directamente en la base de datos de SAP.

        Consulta directamente SAP usando OPENQUERY.

        Args:
            sku: Código del producto (ItemCode) a buscar en SAP

        Returns:
            Información del producto en SAP si se encuentra
        """
        return await _buscar_sku_sap_handler(sku)

    @app.get("/cruce-productos/buscar-sku/sap/sugerencias", tags=["Cruce de Productos"])
    async def buscar_sugerencias_sku_sap(
        sku: str = Query(..., description="SKU (ItemCode) de referencia para buscar sugerencias similares en SAP"),
        limite: int = Query(20, ge=1, le=50, description="Límite máximo de sugerencias a retornar (1-50)"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Busca SKUs similares en SAP basándose en un SKU de referencia.

        Este endpoint realiza búsqueda fuzzy/similar usando:
        1. Búsqueda LIKE en ItemCode de SAP
        2. Algoritmo de scoring basado en similitud de códigos y nombres
        3. Retorna sugerencias ordenadas por relevancia con scores y motivos

        Args:
            sku: SKU de referencia (ItemCode) para buscar sugerencias similares
            limite: Límite máximo de sugerencias (default: 20, máximo: 50)

        Returns:
            Lista de sugerencias con información detallada
        """
        return await _buscar_sugerencias_sku_sap_handler(sku, limite)

    @app.get("/cruce-productos/estado-sincronizacion", tags=["Cruce de Productos"])
    async def obtener_estado_sincronizacion(
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Obtiene el estado actual de sincronización de maestros MBA3 y SAP.

        Retorna información sobre:
        - Última sincronización exitosa (fecha y hora en ISO 8601)
        - Estado actual: "exitoso", "error", "en_proceso", o null si no hay registros
        - Mensaje descriptivo del estado

        ⚠️ Nota: Si hay una sincronización EN_PROGRESO con más de 2 horas,
           se considera inconsistente (proceso colgado) y se retorna como error.

        Returns:
            {
                "status": "success",
                "data": {
                    "mba3": {"ultima_sync": ..., "estado": ..., "mensaje": ...},
                    "sap":  {"ultima_sync": ..., "estado": ..., "mensaje": ...}
                }
            }
        """
        return await _obtener_estado_sincronizacion_handler()

    @app.post("/cruce-productos/iniciar", tags=["Cruce de Productos"])
    async def iniciar_cruce_productos(
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Inicia un cruce de productos en background usando Celery.

        Este endpoint:
        1. Crea un proceso con ID único
        2. Ejecuta el cruce en background usando Celery
        3. Devuelve el process_id para seguir el progreso

        Para seguir el progreso, usa:
        - GET /cruce-productos/stream/{process_id} (SSE)
        - GET /cruce-productos/resultado/{process_id} (polling)

        Si Redis/Celery no están disponibles, se ejecuta el cruce en primer plano
        y se devuelve 200 con el resultado completo ("fallback": "sync").

        Returns:
            Si async: 202 con process_id.
            Si fallback sync: 200 con "data", "message", "fallback": "sync".
        """
        return await _iniciar_cruce_productos_handler(user)

    @app.get("/cruce-productos/stream/{process_id}", tags=["Cruce de Productos"])
    async def stream_progreso_cruce(
        process_id: str,
        request: Request,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Stream de progreso usando Server-Sent Events (SSE).

        Este endpoint envía eventos de progreso en tiempo real mientras
        se ejecuta el cruce de productos.

        **Autenticación:**
        - El token JWT debe enviarse en el header Authorization (no en query string)
        - El frontend debe usar fetch() con ReadableStream o un polyfill de EventSource

        **Eventos enviados:**
        - Cada segundo mientras el proceso está en ejecución
        - Solo cuando hay cambios en el estado (comparación por updated_at y version)
        - Evento final cuando el proceso completa o falla

        **Formato de eventos:**
        ```
        data: {"status": "processing", "step": "exactos", "progress": 50, ...}
        ```

        Args:
            process_id: ID del proceso obtenido de POST /cruce-productos/iniciar

        Returns:
            Stream de eventos SSE con formato text/event-stream
        """
        return await _stream_progreso_cruce_handler(process_id, request, user)

    @app.get("/cruce-productos/resultado/{process_id}", tags=["Cruce de Productos"])
    async def obtener_resultado_cruce(
        process_id: str,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Obtiene el resultado final del cruce (por si se perdió el stream SSE).

        Este endpoint es útil para:
        - Recuperar resultados después de perder conexión SSE
        - Verificar estado de un proceso sin mantener conexión abierta
        - Implementar polling como alternativa a SSE

        Args:
            process_id: ID del proceso obtenido de POST /cruce-productos/iniciar

        Returns:
            - Si completado: resultado completo del cruce
            - Si en proceso: estado actual
            - Si error: mensaje de error
        """
        return await _obtener_resultado_cruce_handler(process_id, user)
