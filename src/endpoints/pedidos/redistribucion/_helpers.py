"""Helpers reutilizables para endpoints de redistribución."""

from typing import Any, Dict, List

from fastapi import HTTPException, status

from src.database.pedido_estados import ESTADO_LIMITE_CANCELAR_PEDIDO, estado_id_desde_legacy


def obtener_pedido_o_404(repo_pedido, pedido_id: str, *, es_numero: bool = False) -> Dict[str, Any]:
    """Obtiene pedido por UUID o número, lanza HTTP 404 si no existe."""
    if es_numero:
        pedido_data = repo_pedido.get_pedido_completo_por_numero(pedido_id)
        mensaje = f"No se encontró el pedido con número: {pedido_id}"
    else:
        pedido_data = repo_pedido.get_pedido_completo(pedido_id)
        mensaje = f"No se encontró el pedido con ID: {pedido_id}"

    if not pedido_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "pedido_not_found",
                "message": mensaje,
            },
        )

    return pedido_data


def obtener_respuestas_proveedor(
    repo_pedido,
    pedido_id: str,
    *,
    top_one: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Obtiene respuestas del proveedor usando repositorio."""
    return repo_pedido.get_respuestas_proveedor(pedido_id, top_one=top_one)


def enriquecer_productos_con_pedido(
    distribucion_productos: List[Dict[str, Any]],
    pedido_detalles: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Enriquece productos de distribución con info del pedido (código, descripción)."""
    detalles_por_id = {
        detalle.get("pedido_detalle_id"): detalle
        for detalle in pedido_detalles
        if detalle.get("pedido_detalle_id")
    }

    productos_enriquecidos: List[Dict[str, Any]] = []
    for producto_dist in distribucion_productos:
        pedido_detalle_id = producto_dist.get("pedido_detalle_id")
        detalle_pedido = detalles_por_id.get(pedido_detalle_id)

        if detalle_pedido:
            productos_enriquecidos.append(
                {
                    **producto_dist,
                    "codigo_interno": detalle_pedido.get("codigo_interno"),
                    "descripcion_sap": detalle_pedido.get("descripcion_sap"),
                    "codigo_barras": detalle_pedido.get("codigo_barras"),
                }
            )
        else:
            productos_enriquecidos.append(producto_dist)

    return productos_enriquecidos


def calcular_estado_puede_descartar(cabecera: Dict[str, Any]) -> bool:
    """Calcula si el pedido puede ser descartado según su estado."""
    estado_id = cabecera.get("estado_id")
    if estado_id is None and cabecera.get("estado"):
        estado_id = estado_id_desde_legacy(cabecera.get("estado"))

    try:
        estado_id = int(estado_id) if estado_id is not None else None
    except (TypeError, ValueError):
        estado_id = None

    return estado_id is not None and estado_id < ESTADO_LIMITE_CANCELAR_PEDIDO
