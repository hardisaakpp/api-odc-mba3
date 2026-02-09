"""Endpoints de borrador y datos iniciales de redistribución."""

import json
import logging
from typing import Dict, Optional

from fastapi import FastAPI, Depends, HTTPException, Path, Query, Body, status
from datetime import datetime

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
from ._converters import construir_distribucion_proporcional

logger = logging.getLogger(__name__)


def register_borrador_endpoints(app: FastAPI):
    """Endpoints de borrador y datos iniciales."""

    @app.post("/api/pedidos/{numero_pedido}/redistribucion/borrador",
             response_model=GuardarBorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def guardar_borrador_redistribucion(
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: GuardarBorradorRequest = Body(..., description="Datos del borrador de redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """Guarda un borrador de redistribución."""
        try:
            user_id = get_user_id(user)

            with get_db_connection_context() as conn:
                repo_pedido = PedidoRepository(conn)
                repo_borrador = RedistribucionBorradorRepository(conn)

                pedido_data = obtener_pedido_o_404(repo_pedido, numero_pedido, es_numero=True)

                pedido_id = pedido_data["cabecera"]["pedido_id"]

                ajustes_json = json.dumps([ajuste.dict() for ajuste in request_body.ajustes_detalle])
                repo_borrador.upsert_borrador(pedido_id, numero_pedido, ajustes_json, user_id)

                return GuardarBorradorResponse(
                    pedido_id=pedido_id,
                    numero_pedido=numero_pedido,
                    fecha_guardado=datetime.now(),
                    message="Borrador guardado exitosamente"
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al guardar borrador: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al guardar borrador: {str(e)}"
                }
            )

    @app.get("/api/pedidos/{numero_pedido}/redistribucion/borrador",
             response_model=BorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_borrador_redistribucion(
        numero_pedido: str = Path(..., description="Número del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """Obtiene el borrador de redistribución guardado."""
        try:
            with get_db_connection_context() as conn:
                repo_pedido = PedidoRepository(conn)
                repo_borrador = RedistribucionBorradorRepository(conn)

                pedido_data = obtener_pedido_o_404(repo_pedido, numero_pedido, es_numero=True)

                pedido_id = pedido_data["cabecera"]["pedido_id"]

                borrador = repo_borrador.get_borrador(pedido_id)

                if not borrador:
                    return BorradorResponse(
                        status="success",
                        ajustes_detalle=[],
                        fecha_guardado=None,
                        message="No hay borrador guardado para este pedido"
                    )

                ajustes_json = borrador["ajustes_detalle"]
                fecha_guardado = borrador["fecha_guardado"]

                ajustes_list = json.loads(ajustes_json)

                detalles_pedido_map = {
                    detalle.get("codigo_interno"): detalle
                    for detalle in pedido_data.get("detalles", [])
                }

                ajustes_detalle_sincronizados = []
                for ajuste_dict in ajustes_list:
                    codigo_producto = ajuste_dict.get("codigo_producto")
                    detalle_pedido = detalles_pedido_map.get(codigo_producto)

                    if detalle_pedido:
                        costo_actual = detalle_pedido.get("costo_doc_sin_iva")
                        if costo_actual is not None:
                            ajuste_dict["costo_original"] = costo_actual
                            ajuste_dict["costo_ajustado"] = costo_actual

                        total_actual = detalle_pedido.get("total")
                        if total_actual is not None:
                            try:
                                cantidad_confirmada_actual = int(float(total_actual))
                                ajuste_dict["cantidad_confirmada"] = cantidad_confirmada_actual
                                if ajuste_dict.get("cantidad_ajustada", 0) > cantidad_confirmada_actual:
                                    ajuste_dict["cantidad_ajustada"] = cantidad_confirmada_actual
                            except (ValueError, TypeError):
                                pass

                    ajustes_detalle_sincronizados.append(AjusteDetalle(**ajuste_dict))

                return BorradorResponse(
                    ajustes_detalle=ajustes_detalle_sincronizados,
                    fecha_guardado=fecha_guardado
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener borrador: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al obtener borrador: {str(e)}"
                }
            )

    @app.get("/api/pedidos/{numero_pedido}/redistribucion/inicial",
             response_model=BorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_datos_iniciales_redistribucion(
        numero_pedido: str = Path(..., description="Número del pedido"),
        solo_lectura: Optional[str] = Query(None, description="Si es '1' o 'true', devuelve la última redistribución confirmada (para vista solo lectura)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """Obtiene los datos iniciales para la redistribución sincronizados con el pedido actualizado."""
        try:
            with get_db_connection_context() as conn:
                repo_pedido = PedidoRepository(conn)

                pedido_data = obtener_pedido_o_404(repo_pedido, numero_pedido, es_numero=True)

                pedido_id = pedido_data["cabecera"]["pedido_id"]

                if str(solo_lectura or "").lower() in ("1", "true"):
                    repo_dist = DistribucionConfirmadaRepository(conn)
                    version_actual = repo_dist.get_version_actual(pedido_id)
                    if version_actual >= 1:
                        distribucion_data = repo_dist.get_distribucion_completa(pedido_id)
                        detalles_by_id = {d.get("pedido_detalle_id"): d for d in pedido_data.get("detalles", []) if d.get("pedido_detalle_id")}
                        ajustes_detalle_confirmada = []
                        for p in distribucion_data.get("productos", []):
                            pedido_detalle_id = p.get("pedido_detalle_id")
                            detalle = detalles_by_id.get(pedido_detalle_id, {})
                            codigo = detalle.get("codigo_interno") or ""
                            descripcion = detalle.get("descripcion_sap") or ""
                            if not codigo:
                                continue
                            dist_tiendas = [
                                DistribucionTiendaFrontend(
                                    tienda_codigo=d.get("tienda_codigo") or "",
                                    tienda_nombre=d.get("tienda_nombre") or "",
                                    cantidad=int(d.get("cantidad_asignada", 0)),
                                    es_bodega=bool(d.get("es_bodega", False)),
                                )
                                for d in p.get("distribuciones", [])
                            ]
                            if not dist_tiendas:
                                continue
                            primer_d = p.get("distribuciones", [{}])[0]
                            costo = None
                            if primer_d.get("costo_unitario_ajustado") is not None:
                                costo = float(primer_d["costo_unitario_ajustado"])
                            elif primer_d.get("costo_unitario_original") is not None:
                                costo = float(primer_d["costo_unitario_original"])
                            ajustes_detalle_confirmada.append(
                                AjusteDetalle(
                                    codigo_producto=codigo,
                                    descripcion=descripcion,
                                    cantidad_solicitada=int(p.get("cantidad_solicitada_total", 0)),
                                    cantidad_confirmada=int(p.get("cantidad_confirmada_total", 0)),
                                    cantidad_ajustada=int(p.get("cantidad_asignada_total", 0)),
                                    distribucion_tiendas=dist_tiendas,
                                    costo_original=costo,
                                    costo_ajustado=costo,
                                    cambio_precio=False,
                                    pedido_detalle_id=pedido_detalle_id,
                                    costo_modificado_manual=bool(detalle.get("costo_modificado_manual", False)),
                                    total_modificado_manual=bool(detalle.get("total_modificado_manual", False)),
                                )
                            )
                        return BorradorResponse(
                            ajustes_detalle=ajustes_detalle_confirmada,
                            fecha_guardado=datetime.now(),
                        )

                respuestas_map = obtener_respuestas_proveedor(repo_pedido, pedido_id, top_one=True)

                ajustes_detalle = []
                for detalle in pedido_data.get("detalles", []):
                    pedido_detalle_id = detalle.get("pedido_detalle_id")
                    codigo_producto = detalle.get("codigo_interno")

                    if not codigo_producto:
                        continue

                    respuesta = respuestas_map.get(pedido_detalle_id, {})
                    cantidad_solicitada = respuesta.get("cantidad_solicitada_total", 0)
                    cantidad_confirmada = respuesta.get("cantidad_confirmada_total", 0)

                    if cantidad_solicitada == 0:
                        cantidad_solicitada = sum(t.get("cantidad", 0) for t in detalle.get("tiendas", []))

                    if cantidad_confirmada == 0:
                        total_value = detalle.get("total")
                        if total_value is not None:
                            try:
                                cantidad_confirmada = int(float(total_value))
                            except (ValueError, TypeError):
                                cantidad_confirmada = cantidad_solicitada
                        else:
                            cantidad_confirmada = cantidad_solicitada

                    costo_actual = detalle.get("costo_doc_sin_iva")

                    tiendas_del_detalle = detalle.get("tiendas", [])
                    cantidad_total_original = sum(t.get("cantidad", 0) for t in tiendas_del_detalle)
                    distribucion_tiendas = construir_distribucion_proporcional(
                        tiendas=tiendas_del_detalle,
                        cantidad_confirmada=cantidad_confirmada,
                        cantidad_total_original=cantidad_total_original,
                    )

                    costo_modificado = detalle.get("costo_modificado_manual", False)
                    total_modificado = detalle.get("total_modificado_manual", False)

                    ajuste = AjusteDetalle(
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
                        costo_modificado_manual=costo_modificado,
                        total_modificado_manual=total_modificado,
                    )

                    ajustes_detalle.append(ajuste)

                return BorradorResponse(
                    ajustes_detalle=ajustes_detalle,
                    fecha_guardado=datetime.now()
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener datos iniciales de redistribución: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al obtener datos iniciales: {str(e)}"
                }
            )
