"""Endpoints de borrador y datos iniciales de redistribución."""

import asyncio
import json
import logging
from typing import Dict, Optional

from fastapi import FastAPI, Depends, HTTPException, Path, Query, Body, status, Request

from src.utils.timezone import ahora_naive
from src.utils.audit_context import get_audit_context, ORIGEN_WEB

from src.database.connection import get_db_connection_context
from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.repositories.redistribucion_borrador_repository import RedistribucionBorradorRepository
from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission
from src.models import (
    GuardarBorradorRequest,
    GuardarBorradorResponse,
    BorradorResponse,
    AjusteDetalle,
    DistribucionTiendaFrontend,
)
from ..utils import get_user_id
from ._helpers import obtener_pedido_o_404, obtener_respuestas_proveedor
from ._converters import construir_distribucion_proporcional, enriquecer_distribucion_tiendas_con_nombre

logger = logging.getLogger(__name__)

_PERM_MABEL = 'mabel.view'
_PERM_ODCSAP = 'odcsap.view'
_DESC_NUMERO_PEDIDO = "Número del pedido"


def _sincronizar_costos_borrador(ajuste_dict: dict, detalle_pedido: dict) -> None:
    costo_actual = detalle_pedido.get("costo_doc_sin_iva")
    if costo_actual is not None:
        ajuste_dict["costo_original"] = costo_actual
        ajuste_dict["costo_ajustado"] = costo_actual
    total_actual = detalle_pedido.get("total")
    if total_actual is not None:
        try:
            cantidad_confirmada_actual = float(total_actual)
            ajuste_dict["cantidad_confirmada"] = cantidad_confirmada_actual
            cantidad_ajustada_actual = float(ajuste_dict.get("cantidad_ajustada", 0) or 0)
            if cantidad_ajustada_actual > cantidad_confirmada_actual:
                ajuste_dict["cantidad_ajustada"] = cantidad_confirmada_actual
        except (ValueError, TypeError):
            pass


def _sincronizar_ajuste_con_pedido(
    ajuste_dict: dict, detalles_pedido_map: dict, tienda_repo
) -> None:
    codigo_producto = ajuste_dict.get("codigo_producto")
    detalle_pedido = detalles_pedido_map.get(codigo_producto)
    if detalle_pedido:
        _sincronizar_costos_borrador(ajuste_dict, detalle_pedido)
    dist_tiendas = ajuste_dict.get("distribucion_tiendas", [])
    if dist_tiendas:
        ajuste_dict["distribucion_tiendas"] = enriquecer_distribucion_tiendas_con_nombre(
            dist_tiendas, tienda_repo
        )


def _calcular_costo_desde_distribucion(detalle: dict, p: dict):
    costo = detalle.get("costo_doc_sin_iva")
    if costo is not None:
        return round(float(costo), 4)
    primer_d = p.get("distribuciones", [{}])[0]
    if primer_d.get("costo_unitario_ajustado") is not None:
        return round(float(primer_d["costo_unitario_ajustado"]), 4)
    if primer_d.get("costo_unitario_original") is not None:
        return round(float(primer_d["costo_unitario_original"]), 4)
    return None


def _construir_dist_tiendas_confirmada(p: dict, tienda_repo) -> Optional[list]:
    dist_tiendas = [
        DistribucionTiendaFrontend(
            tienda_codigo=d.get("tienda_codigo") or "",
            tienda_nombre=d.get("tienda_nombre") or "",
            cantidad=float(d.get("cantidad_asignada", 0)),
            es_bodega=bool(d.get("es_bodega", False)),
            agregada_manualmente=bool(d.get("agregada_manualmente", False)),
        )
        for d in p.get("distribuciones", [])
    ]
    if not dist_tiendas:
        return None
    return enriquecer_distribucion_tiendas_con_nombre(dist_tiendas, tienda_repo)


def _construir_ajustes_solo_lectura(
    distribucion_data: dict, detalles_by_id: dict, tienda_repo
) -> list:
    ajustes = []
    for p in distribucion_data.get("productos", []):
        pedido_detalle_id = p.get("pedido_detalle_id")
        detalle = detalles_by_id.get(pedido_detalle_id, {})
        codigo = detalle.get("codigo_interno") or ""
        descripcion = detalle.get("descripcion_sap") or ""
        if not codigo:
            continue
        dist_tiendas = _construir_dist_tiendas_confirmada(p, tienda_repo)
        if not dist_tiendas:
            continue
        costo = _calcular_costo_desde_distribucion(detalle, p)
        ajustes.append(AjusteDetalle(
            codigo_producto=codigo,
            descripcion=descripcion,
            cantidad_solicitada=float(p.get("cantidad_solicitada_total", 0)),
            cantidad_confirmada=float(p.get("cantidad_confirmada_total", 0)),
            cantidad_ajustada=float(p.get("cantidad_asignada_total", 0)),
            distribucion_tiendas=dist_tiendas,
            costo_original=costo,
            costo_ajustado=costo,
            cambio_precio=False,
            pedido_detalle_id=pedido_detalle_id,
            costo_modificado_manual=bool(detalle.get("costo_modificado_manual", False)),
            total_modificado_manual=bool(detalle.get("total_modificado_manual", False)),
        ))
    ajustes.sort(key=lambda a: (a.codigo_producto or "", a.pedido_detalle_id or ""))
    return ajustes


def _calcular_cantidades(respuesta: dict, detalle: dict):
    cantidad_solicitada = float(respuesta.get("cantidad_solicitada_total", 0) or 0)
    cantidad_confirmada = float(respuesta.get("cantidad_confirmada_total", 0) or 0)
    if cantidad_solicitada == 0:
        cantidad_solicitada = sum(float(t.get("cantidad", 0) or 0) for t in detalle.get("tiendas", []))
    if cantidad_confirmada == 0:
        total_value = detalle.get("total")
        if total_value is not None:
            try:
                cantidad_confirmada = float(total_value)
            except (ValueError, TypeError):
                cantidad_confirmada = cantidad_solicitada
        else:
            cantidad_confirmada = cantidad_solicitada
    return cantidad_solicitada, cantidad_confirmada


def _construir_ajuste_detalle_normal(detalle: dict, respuesta: dict, tienda_repo) -> AjusteDetalle:
    pedido_detalle_id = detalle.get("pedido_detalle_id")
    codigo_producto = detalle.get("codigo_interno") or ""
    cantidad_solicitada, cantidad_confirmada = _calcular_cantidades(respuesta, detalle)
    costo_actual = detalle.get("costo_doc_sin_iva")
    if costo_actual is not None:
        costo_actual = round(float(costo_actual), 4)
    tiendas_del_detalle = detalle.get("tiendas", [])
    cantidad_total_original = sum(float(t.get("cantidad", 0) or 0) for t in tiendas_del_detalle)
    distribucion_tiendas = construir_distribucion_proporcional(
        tiendas=tiendas_del_detalle,
        cantidad_confirmada=cantidad_confirmada,
        cantidad_total_original=cantidad_total_original,
    )
    distribucion_tiendas = enriquecer_distribucion_tiendas_con_nombre(distribucion_tiendas, tienda_repo)
    return AjusteDetalle(
        codigo_producto=codigo_producto,
        descripcion=detalle.get("descripcion_sap", ""),
        cantidad_solicitada=cantidad_solicitada,
        cantidad_confirmada=cantidad_confirmada,
        cantidad_ajustada=cantidad_confirmada,
        distribucion_tiendas=distribucion_tiendas,
        costo_original=costo_actual,
        costo_ajustado=costo_actual,
        cambio_precio=False,
        pedido_detalle_id=pedido_detalle_id,
        costo_modificado_manual=detalle.get("costo_modificado_manual", False),
        total_modificado_manual=detalle.get("total_modificado_manual", False),
    )


def _construir_ajustes_normales(pedido_data: dict, respuestas_map: dict, tienda_repo) -> list:
    ajustes_detalle = []
    for detalle in pedido_data.get("detalles", []):
        if not detalle.get("codigo_interno"):
            continue
        pedido_detalle_id = detalle.get("pedido_detalle_id")
        respuesta = respuestas_map.get(pedido_detalle_id, {})
        ajustes_detalle.append(_construir_ajuste_detalle_normal(detalle, respuesta, tienda_repo))
    ajustes_detalle.sort(key=lambda a: (a.codigo_producto or "", a.pedido_detalle_id or ""))
    return ajustes_detalle


def _db_guardar_borrador(
    numero_pedido: str, request_body: GuardarBorradorRequest, user_id, audit
) -> GuardarBorradorResponse:
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        repo_pedido = PedidoRepository(conn)
        repo_borrador = RedistribucionBorradorRepository(conn)
        pedido_data = obtener_pedido_o_404(repo_pedido, numero_pedido, es_numero=True)
        pedido_id = pedido_data["cabecera"]["pedido_id"]
        ajustes_json = json.dumps([ajuste.dict() for ajuste in request_body.ajustes_detalle])
        repo_borrador.upsert_borrador(pedido_id, numero_pedido, ajustes_json, user_id, audit_context=audit)
        return GuardarBorradorResponse(
            pedido_id=pedido_id,
            numero_pedido=numero_pedido,
            fecha_guardado=ahora_naive(),
            message="Borrador guardado exitosamente"
        )


async def _guardar_borrador_handler(
    request: Request, numero_pedido: str, request_body: GuardarBorradorRequest, user: Dict
) -> GuardarBorradorResponse:
    try:
        user_id = get_user_id(user)
        audit = get_audit_context(request, user, origen=ORIGEN_WEB)
        return await asyncio.to_thread(
            _db_guardar_borrador, numero_pedido, request_body, user_id, audit
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al guardar borrador: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": f"Error interno al guardar borrador: {str(e)}"}
        )


def _db_obtener_borrador(numero_pedido: str) -> BorradorResponse:
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        repo_pedido = PedidoRepository(conn)
        repo_borrador = RedistribucionBorradorRepository(conn)
        pedido_data = repo_pedido.get_pedido_completo_por_numero(numero_pedido)
        if not pedido_data:
            return BorradorResponse(
                status="success",
                ajustes_detalle=[],
                fecha_guardado=None,
                message="No se encontró el pedido, no hay borrador disponible"
            )
        pedido_id = pedido_data["cabecera"]["pedido_id"]
        borrador = repo_borrador.get_borrador(pedido_id)
        if not borrador:
            return BorradorResponse(
                status="success",
                ajustes_detalle=[],
                fecha_guardado=None,
                message="No hay borrador guardado para este pedido"
            )
        ajustes_list = json.loads(borrador["ajustes_detalle"])
        fecha_guardado = borrador["fecha_guardado"]
        detalles_pedido_map = {
            detalle.get("codigo_interno"): detalle
            for detalle in pedido_data.get("detalles", [])
        }
        ajustes_detalle_sincronizados = []
        for ajuste_dict in ajustes_list:
            _sincronizar_ajuste_con_pedido(ajuste_dict, detalles_pedido_map, repo_pedido.tienda_repo)
            ajustes_detalle_sincronizados.append(AjusteDetalle(**ajuste_dict))
        ajustes_detalle_sincronizados.sort(
            key=lambda a: (a.codigo_producto or "", a.pedido_detalle_id or "")
        )
        return BorradorResponse(
            ajustes_detalle=ajustes_detalle_sincronizados,
            fecha_guardado=fecha_guardado
        )


async def _obtener_borrador_handler(numero_pedido: str) -> BorradorResponse:
    try:
        return await asyncio.to_thread(_db_obtener_borrador, numero_pedido)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al obtener borrador: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": f"Error interno al obtener borrador: {str(e)}"}
        )


def _db_obtener_datos_iniciales(
    numero_pedido: str, solo_lectura: Optional[str]
) -> BorradorResponse:
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    with get_db_connection_context() as conn:
        repo_pedido = PedidoRepository(conn)
        pedido_data = obtener_pedido_o_404(repo_pedido, numero_pedido, es_numero=True)
        pedido_id = pedido_data["cabecera"]["pedido_id"]
        if str(solo_lectura or "").lower() in ("1", "true"):
            repo_dist = DistribucionConfirmadaRepository(conn)
            version_actual = repo_dist.get_version_actual(pedido_id)
            if version_actual >= 1:
                distribucion_data = repo_dist.get_distribucion_completa(pedido_id)
                detalles_by_id = {
                    d.get("pedido_detalle_id"): d
                    for d in pedido_data.get("detalles", [])
                    if d.get("pedido_detalle_id")
                }
                ajustes = _construir_ajustes_solo_lectura(
                    distribucion_data, detalles_by_id, repo_pedido.tienda_repo
                )
                return BorradorResponse(ajustes_detalle=ajustes, fecha_guardado=ahora_naive())
        respuestas_map = obtener_respuestas_proveedor(repo_pedido, pedido_id, top_one=True)
        ajustes_detalle = _construir_ajustes_normales(
            pedido_data, respuestas_map, repo_pedido.tienda_repo
        )
        return BorradorResponse(ajustes_detalle=ajustes_detalle, fecha_guardado=ahora_naive())


async def _obtener_datos_iniciales_handler(
    numero_pedido: str, solo_lectura: Optional[str]
) -> BorradorResponse:
    try:
        return await asyncio.to_thread(_db_obtener_datos_iniciales, numero_pedido, solo_lectura)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al obtener datos iniciales de redistribución: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": f"Error interno al obtener datos iniciales: {str(e)}"}
        )


def register_borrador_endpoints(app: FastAPI):
    """Endpoints de borrador y datos iniciales."""

    @app.post("/api/pedidos/{numero_pedido}/redistribucion/borrador",
             response_model=GuardarBorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def guardar_borrador_redistribucion(
        request: Request,
        numero_pedido: str = Path(..., description=_DESC_NUMERO_PEDIDO),
        request_body: GuardarBorradorRequest = Body(..., description="Datos del borrador de redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """Guarda un borrador de redistribución."""
        return await _guardar_borrador_handler(request, numero_pedido, request_body, user)

    @app.get("/api/pedidos/{numero_pedido}/redistribucion/borrador",
             response_model=BorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_borrador_redistribucion(
        numero_pedido: str = Path(..., description=_DESC_NUMERO_PEDIDO),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_MABEL, _PERM_ODCSAP]))
    ):
        """Obtiene el borrador de redistribución guardado."""
        return await _obtener_borrador_handler(numero_pedido)

    @app.get("/api/pedidos/{numero_pedido}/redistribucion/inicial",
             response_model=BorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_datos_iniciales_redistribucion(
        numero_pedido: str = Path(..., description=_DESC_NUMERO_PEDIDO),
        solo_lectura: Optional[str] = Query(None, description="Si es '1' o 'true', devuelve la última redistribución confirmada (para vista solo lectura)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_ODCSAP, _PERM_MABEL]))
    ):
        """Obtiene los datos iniciales para la redistribución sincronizados con el pedido actualizado."""
        return await _obtener_datos_iniciales_handler(numero_pedido, solo_lectura)
