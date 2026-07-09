"""Conversores entre estructuras del frontend y redistribución interna."""

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from src.models import DistribucionTiendaFrontend


def enriquecer_distribucion_tiendas_con_nombre(
    distribucion_tiendas: List[Any],
    tienda_repo: Any,
) -> List[DistribucionTiendaFrontend]:
    """
    Asegura que cada ítem tenga tienda_nombre; si viene vacío, lo obtiene por tienda_codigo.
    Así la interfaz de redistribución siempre muestra el nombre de la tienda (también para cantidades < 1).
    """
    if not distribucion_tiendas:
        return []
    result: List[DistribucionTiendaFrontend] = []
    for d in distribucion_tiendas:
        codigo = (_get_tienda_value(d, "tienda_codigo") or "").strip()
        nombre = (_get_tienda_value(d, "tienda_nombre") or "").strip()
        cantidad = _get_tienda_value(d, "cantidad", 0)
        es_bodega = _get_tienda_value(d, "es_bodega", False)
        if not nombre and codigo and getattr(tienda_repo, "get_nombre_by_codigo", None):
            nombre = tienda_repo.get_nombre_by_codigo(codigo) or ""
        result.append(
            DistribucionTiendaFrontend(
                tienda_codigo=codigo,
                tienda_nombre=nombre or codigo,
                cantidad=float(cantidad) if cantidad is not None else 0.0,
                es_bodega=bool(es_bodega),
            )
        )
    return result


def sincronizar_costos_con_pedido(ajuste, detalle_pedido: Dict[str, Any]) -> None:
    """Sincroniza costos y cantidades del ajuste con valores actuales del pedido."""
    costo_actual = detalle_pedido.get("costo_doc_sin_iva")
    if costo_actual is not None:
        ajuste.costo_original = costo_actual
        ajuste.costo_ajustado = costo_actual

    total_actual = detalle_pedido.get("total")
    if total_actual is not None:
        try:
            cantidad_confirmada_actual = float(total_actual)
            ajuste.cantidad_confirmada = cantidad_confirmada_actual
        except (ValueError, TypeError):
            pass


def convertir_ajustes_a_redistribucion(
    ajustes_detalle: List[Any],
    pedido_data: Dict[str, Any],
    tienda_repo,
) -> List[Dict[str, Any]]:
    """Convierte AjusteDetalle del frontend a estructura interna de redistribución."""
    productos_redistribucion: List[Dict[str, Any]] = []

    for ajuste in ajustes_detalle:
        detalle_pedido = next(
            (
                d
                for d in pedido_data.get("detalles", [])
                if d.get("codigo_interno") == ajuste.codigo_producto
            ),
            None,
        )

        if not detalle_pedido:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "producto_not_found",
                    "message": f"No se encontró el producto con código: {ajuste.codigo_producto}",
                },
            )

        sincronizar_costos_con_pedido(ajuste, detalle_pedido)

        distribuciones: List[Dict[str, Any]] = []
        for dist_tienda in ajuste.distribucion_tiendas:
            tienda_id = tienda_repo.get_tienda_id_by_codigo(dist_tienda.tienda_codigo)
            if not tienda_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "tienda_not_found",
                        "message": f"No se encontró la tienda con código: {dist_tienda.tienda_codigo}",
                    },
                )

            distribuciones.append(
                {
                    "tienda_id": tienda_id,
                    "cantidad_asignada": dist_tienda.cantidad,
                }
            )

        productos_redistribucion.append(
            {
                "pedido_detalle_id": detalle_pedido["pedido_detalle_id"],
                "distribuciones": distribuciones,
            }
        )

    return productos_redistribucion


def _get_tienda_value(tienda: Any, key: str, default: Optional[Any] = None) -> Any:
    if isinstance(tienda, dict):
        return tienda.get(key, default)
    return getattr(tienda, key, default)


def construir_distribucion_proporcional(
    tiendas: List[Any],
    cantidad_confirmada: float,
    cantidad_total_original: float,
) -> List[DistribucionTiendaFrontend]:
    """Calcula distribución proporcional entre tiendas. Acepta decimales (ej. 0.5)."""
    if cantidad_confirmada <= 0 or cantidad_total_original <= 0:
        return [
            DistribucionTiendaFrontend(
                tienda_codigo=_get_tienda_value(tienda, "codigo", ""),
                tienda_nombre=_get_tienda_value(tienda, "nombre", ""),
                cantidad=0.0,
                es_bodega=_get_tienda_value(tienda, "es_bodega", False),
            )
            for tienda in tiendas
        ]

    factor_proporcion = cantidad_confirmada / cantidad_total_original
    cantidad_asignada_total = 0.0
    distribuciones_calculadas: List[DistribucionTiendaFrontend] = []

    for i, tienda in enumerate(tiendas):
        cantidad_original = float(_get_tienda_value(tienda, "cantidad", 0) or 0)

        if i == len(tiendas) - 1:
            # Última tienda: asignar el resto para que la suma coincida exactamente
            cantidad_calculada = round(cantidad_confirmada - cantidad_asignada_total, 4)
        else:
            cantidad_calculada = round(cantidad_original * factor_proporcion, 4)
            cantidad_asignada_total += cantidad_calculada

        cantidad_calculada = max(0.0, cantidad_calculada)

        distribuciones_calculadas.append(
            DistribucionTiendaFrontend(
                tienda_codigo=_get_tienda_value(tienda, "codigo", ""),
                tienda_nombre=_get_tienda_value(tienda, "nombre", ""),
                cantidad=cantidad_calculada,
                es_bodega=_get_tienda_value(tienda, "es_bodega", False),
            )
        )

    return distribuciones_calculadas
