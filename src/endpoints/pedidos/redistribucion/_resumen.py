"""Cálculo de resumen de confirmación de redistribución."""

from typing import List

from src.models import AjusteDetalle, ResumenConfirmacion


def calcular_resumen_confirmacion(ajustes_detalle: List[AjusteDetalle]) -> ResumenConfirmacion:
    """Calcula el resumen de una confirmación de redistribución."""
    total_productos = len(ajustes_detalle)
    total_cantidad_solicitada = sum(a.cantidad_solicitada for a in ajustes_detalle)
    total_cantidad_confirmada = sum(a.cantidad_confirmada for a in ajustes_detalle)
    total_cantidad_ajustada = sum(a.cantidad_ajustada for a in ajustes_detalle)
    diferencia_cantidad = total_cantidad_ajustada - total_cantidad_confirmada

    total_costo_original = sum(
        (a.cantidad_solicitada * (a.costo_original or 0)) for a in ajustes_detalle
    ) or None

    total_costo_ajustado = sum(
        (a.cantidad_ajustada * (a.costo_ajustado or 0)) for a in ajustes_detalle
    ) or None

    diferencia_costo = (
        total_costo_ajustado - total_costo_original
        if total_costo_ajustado is not None and total_costo_original is not None
        else None
    )

    return ResumenConfirmacion(
        total_productos=total_productos,
        total_cantidad_solicitada=total_cantidad_solicitada,
        total_cantidad_confirmada=total_cantidad_confirmada,
        total_cantidad_ajustada=total_cantidad_ajustada,
        total_costo_original=total_costo_original,
        total_costo_ajustado=total_costo_ajustado,
        diferencia_cantidad=diferencia_cantidad,
        diferencia_costo=diferencia_costo,
    )
