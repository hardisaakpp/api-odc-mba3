"""
Funciones auxiliares para pedidos_crud.py.

Este módulo contiene helpers puros extraídos para reducir duplicación
y mejorar la mantenibilidad del código de endpoints CRUD de pedidos.
"""

from typing import Optional, Dict, Any
from src.database.pedido_estados import (
    ESTADO_REDISTRIBUCION,
    ESTADO_DESPACHAR_Y_FACTURAR,
    ESTADOS_PUEDE_DESCARTAR,
    ESTADOS_PUEDE_CANCELAR_POR_EL_RAYO,
    ESTADO_LIMITE_CANCELAR_PEDIDO,
    ESTADOS_PUEDE_CONFIRMAR_REDISTRIBUCION,
)


def get_estado_id_from_pedido(pedido: Dict[str, Any]) -> Optional[int]:
    """
    Extrae y normaliza el estado_id desde un diccionario de pedido.
    
    Maneja el caso donde estado_id puede ser string, int, None, o estar ausente.
    
    Args:
        pedido: Diccionario con estructura {"cabecera": {"estado_id": ...}, ...}
    
    Returns:
        int si se pudo convertir a entero, None en caso contrario.
    
    Ejemplo:
        >>> pedido = {"cabecera": {"estado_id": "2"}}
        >>> get_estado_id_from_pedido(pedido)
        2
    """
    estado_id = pedido.get("cabecera", {}).get("estado_id")
    try:
        return int(estado_id) if estado_id is not None else None
    except (TypeError, ValueError):
        return None


def enrich_pedido_with_ui_flags(pedido: Dict[str, Any]) -> None:
    """
    Agrega flags de UI (puede_descartar, puede_cancelar, etc.) al pedido.
    
    Modifica el diccionario pedido in-place, agregando los siguientes campos:
    - puede_descartar: bool - Si el pedido puede descartarse (estados BORRADOR o NUEVO_PEDIDO)
    - puede_cancelar_por_el_rayo: bool - Si El Rayo puede cancelar el pedido
    - puede_cancelar_pedido: bool - Si MABEL puede cancelar el pedido
    - puede_descargar_csv: bool - Si se puede descargar CSV (solo estado REDISTRIBUCION)
    - puede_confirmar_redistribucion: bool - Si se puede confirmar para redistribución
    - puede_finalizar: bool - Si se puede marcar como finalizado (solo DESPACHAR_Y_FACTURAR)
    
    Args:
        pedido: Diccionario de pedido que se modificará in-place.
    
    Ejemplo:
        >>> pedido = {"cabecera": {"estado_id": 2}}
        >>> enrich_pedido_with_ui_flags(pedido)
        >>> pedido["puede_descargar_csv"]
        True
    """
    estado_id = get_estado_id_from_pedido(pedido)
    
    # Flags basados en el estado del pedido
    pedido["puede_descartar"] = estado_id in ESTADOS_PUEDE_DESCARTAR
    pedido["puede_cancelar_por_el_rayo"] = estado_id in ESTADOS_PUEDE_CANCELAR_POR_EL_RAYO
    pedido["puede_cancelar_pedido"] = estado_id is not None and estado_id < ESTADO_LIMITE_CANCELAR_PEDIDO
    pedido["puede_descargar_csv"] = estado_id == ESTADO_REDISTRIBUCION
    pedido["puede_confirmar_redistribucion"] = estado_id in ESTADOS_PUEDE_CONFIRMAR_REDISTRIBUCION
    pedido["puede_finalizar"] = estado_id == ESTADO_DESPACHAR_Y_FACTURAR
