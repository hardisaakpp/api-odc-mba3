"""
Endpoint de procesamiento SAP.
"""

import asyncio
import logging
import re
from typing import Dict, List, Optional
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Path, status

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.repositories.pedido_sap_procesamiento_repository import PedidoSAPProcesamientoRepository
from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
from src.security.jwt_auth import verify_jwt_token, require_permission
from src.models import (
    ProcesamientoSAPResponse,
    ProductoSAPProcesamientoItem,
    EstadisticasProcesamientoSAP,
    ConversionPorTiendaItem,
)

logger = logging.getLogger(__name__)

_UUID_PATTERN = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
)


def _resolver_pedido(pedido_id: str, pedido_repo: PedidoRepository):
    es_uuid = _UUID_PATTERN.match(pedido_id.strip()) is not None
    if es_uuid:
        logger.info(f"🔍 Detectado UUID: {pedido_id}, usando get_pedido_completo")
        pedido_data = pedido_repo.get_pedido_completo(pedido_id)
    else:
        logger.info(f"🔍 Detectado numero_pedido: {pedido_id}, usando get_pedido_completo_por_numero")
        pedido_data = pedido_repo.get_pedido_completo_por_numero(pedido_id)
    if not pedido_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "pedido_not_found",
                "message": f"No se encontró el pedido con {'ID' if es_uuid else 'número'}: {pedido_id}",
            },
        )
    pedido_id_real = pedido_data["cabecera"]["pedido_id"]
    numero_pedido = pedido_data["cabecera"].get("numero_pedido")
    return pedido_id_real, numero_pedido


def _parsear_fecha_procesamiento(fecha_raw) -> Optional[datetime]:
    if not fecha_raw:
        return None
    if isinstance(fecha_raw, datetime):
        return fecha_raw
    if isinstance(fecha_raw, str):
        try:
            return datetime.fromisoformat(fecha_raw.replace('Z', '+00:00'))
        except ValueError:
            return None
    return None


def _calcular_unidad_conversion(proc) -> float:
    if proc and proc.get("unidad_conversion"):
        val = float(proc["unidad_conversion"])
        if val > 0:
            return val
    return 1.0


def _construir_lineas_conversion(prod_dist, unidad_conversion: float) -> List[ConversionPorTiendaItem]:
    lineas: List[ConversionPorTiendaItem] = []
    for d in prod_dist.get("distribuciones", []):
        cantidad_asignada = float(d.get("cantidad_asignada", 0) or 0)
        if cantidad_asignada <= 0:
            continue
        cantidad_sap = round(cantidad_asignada * unidad_conversion, 4)
        lineas.append(ConversionPorTiendaItem(
            tienda_codigo=d.get("tienda_codigo") or "",
            tienda_nombre=d.get("tienda_nombre"),
            es_bodega=bool(d.get("es_bodega", False)),
            cantidad_asignada=cantidad_asignada,
            cantidad_sap=cantidad_sap,
        ))
    return lineas


def _cargar_distribucion_conversion(
    conn, pedido_id_real: str, procesamientos: list
) -> Dict[str, List[ConversionPorTiendaItem]]:
    distribucion_conversion_por_producto: Dict[str, List[ConversionPorTiendaItem]] = {}
    try:
        dist_repo = DistribucionConfirmadaRepository(conn)
        version_actual = dist_repo.get_version_actual(pedido_id_real)
        if version_actual > 0:
            distribucion_data = dist_repo.get_distribucion_completa(pedido_id_real, version_actual)
            proc_por_detalle = {p["pedido_detalle_id"]: p for p in procesamientos}
            for prod_dist in distribucion_data.get("productos", []):
                pedido_detalle_id = prod_dist["pedido_detalle_id"]
                proc = proc_por_detalle.get(pedido_detalle_id)
                unidad_conversion = _calcular_unidad_conversion(proc)
                lineas = _construir_lineas_conversion(prod_dist, unidad_conversion)
                if lineas:
                    distribucion_conversion_por_producto[pedido_detalle_id] = lineas
    except Exception as e:
        logger.warning(f"⚠️ No se pudo cargar distribución para conversión por tienda: {e}")
    return distribucion_conversion_por_producto


def _actualizar_fecha_max(
    fecha_proc: Optional[datetime], fecha_max: Optional[datetime]
) -> Optional[datetime]:
    if fecha_proc and (fecha_max is None or fecha_proc > fecha_max):
        return fecha_proc
    return fecha_max


def _acumular_totales(proc, totales: dict) -> None:
    if proc.get("producto_homologado", True):
        totales["homologados"] += 1
    else:
        totales["no_homologados"] += 1
    if proc.get("tipo_problema") == "error" or proc.get("mensaje_error"):
        totales["con_error"] += 1
    if proc.get("cantidad_original"):
        totales["cantidad_original"] += float(proc["cantidad_original"])
    if proc.get("cantidad_sap"):
        totales["cantidad_sap"] += float(proc["cantidad_sap"])
    if proc.get("total_linea_original"):
        totales["precio_original"] += float(proc["total_linea_original"])
    if proc.get("total_linea_sap"):
        totales["precio_sap"] += float(proc["total_linea_sap"])


def _construir_item_proc(
    proc, fecha_proc: Optional[datetime], distribucion_conversion_por_producto: dict
) -> ProductoSAPProcesamientoItem:
    return ProductoSAPProcesamientoItem(
        procesamiento_detalle_id=proc["procesamiento_detalle_id"],
        pedido_detalle_id=proc["pedido_detalle_id"],
        codigo_interno=proc["codigo_interno"],
        descripcion_producto=proc.get("descripcion_producto"),
        item_code_sap=proc.get("item_code_sap"),
        pack_sap=proc.get("pack_sap"),
        unidad_conversion=proc.get("unidad_conversion"),
        unidad_original=proc.get("unidad_original"),
        unidad_sap=proc.get("unidad_sap"),
        cantidad_original=proc.get("cantidad_original"),
        cantidad_sap=proc.get("cantidad_sap"),
        precio_unitario_original=proc.get("precio_unitario_original"),
        precio_unitario_sap=proc.get("precio_unitario_sap"),
        total_linea_original=proc.get("total_linea_original"),
        total_linea_sap=proc.get("total_linea_sap"),
        producto_homologado=proc.get("producto_homologado", True),
        tipo_problema=proc.get("tipo_problema"),
        item_code_sap_encontrado=proc.get("item_code_sap_encontrado"),
        mensaje_error=proc.get("mensaje_error"),
        fecha_procesamiento=fecha_proc,
        procesado_por=proc.get("procesado_por"),
        distribucion_conversion=distribucion_conversion_por_producto.get(proc["pedido_detalle_id"]),
    )


def _construir_estadisticas(total_productos: int, totales: dict) -> EstadisticasProcesamientoSAP:
    return EstadisticasProcesamientoSAP(
        total_productos=total_productos,
        productos_homologados=totales["homologados"],
        productos_no_homologados=totales["no_homologados"],
        productos_con_error=totales["con_error"],
        total_cantidad_original=totales["cantidad_original"] if totales["cantidad_original"] > 0 else None,
        total_cantidad_sap=totales["cantidad_sap"] if totales["cantidad_sap"] > 0 else None,
        total_precio_original=totales["precio_original"] if totales["precio_original"] > 0 else None,
        total_precio_sap=totales["precio_sap"] if totales["precio_sap"] > 0 else None,
    )


def _procesar_procesamientos(
    procesamientos: list, distribucion_conversion_por_producto: dict
):
    productos = []
    totales = {
        "homologados": 0, "no_homologados": 0, "con_error": 0,
        "cantidad_original": 0.0, "cantidad_sap": 0.0,
        "precio_original": 0.0, "precio_sap": 0.0,
    }
    fecha_max: Optional[datetime] = None
    for proc in procesamientos:
        fecha_proc = _parsear_fecha_procesamiento(proc.get("fecha_procesamiento"))
        fecha_max = _actualizar_fecha_max(fecha_proc, fecha_max)
        _acumular_totales(proc, totales)
        productos.append(_construir_item_proc(proc, fecha_proc, distribucion_conversion_por_producto))
    estadisticas = _construir_estadisticas(len(procesamientos), totales)
    return productos, estadisticas, fecha_max


def _db_obtener_procesamiento_sap(pedido_id: str) -> ProcesamientoSAPResponse:
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        pedido_repo = PedidoRepository(conn)
        sap_proc_repo = PedidoSAPProcesamientoRepository(conn)
        pedido_id_real, numero_pedido = _resolver_pedido(pedido_id, pedido_repo)
        procesamientos = sap_proc_repo.get_procesamientos_por_pedido(pedido_id_real)
        distribucion = _cargar_distribucion_conversion(conn, pedido_id_real, procesamientos)
        productos, estadisticas, fecha_max = _procesar_procesamientos(procesamientos, distribucion)
        return ProcesamientoSAPResponse(
            status="success",
            pedido_id=pedido_id_real,
            numero_pedido=numero_pedido,
            productos=productos,
            estadisticas=estadisticas,
            fecha_procesamiento=fecha_max,
        )


async def _obtener_procesamiento_sap_handler(pedido_id: str) -> ProcesamientoSAPResponse:
    try:
        return await asyncio.to_thread(_db_obtener_procesamiento_sap, pedido_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al obtener procesamiento SAP: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al obtener procesamiento SAP: {str(e)}",
        )


def register_sap_endpoints(app: FastAPI):
    """Registra el endpoint de procesamiento SAP."""

    @app.get("/api/pedidos/{pedido_id}/procesamiento-sap",
             response_model=ProcesamientoSAPResponse,
             tags=["Pedidos - SAP"])
    async def obtener_procesamiento_sap(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """Obtiene información de procesamiento SAP de un pedido."""
        return await _obtener_procesamiento_sap_handler(pedido_id)
