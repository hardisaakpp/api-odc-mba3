"""
Funciones auxiliares para pedidos_crud.py.

Este módulo contiene helpers puros extraídos para reducir duplicación
y mejorar la mantenibilidad del código de endpoints CRUD de pedidos.
"""

from typing import Optional, Dict, Any, List

from src.database.pedido_estados import (
    ESTADO_REDISTRIBUCION,
    ESTADO_DESPACHAR_Y_FACTURAR,
    ESTADOS_PUEDE_DESCARTAR,
    ESTADOS_PUEDE_CANCELAR_POR_EL_RAYO,
    ESTADO_LIMITE_CANCELAR_PEDIDO,
    ESTADOS_PUEDE_CONFIRMAR_REDISTRIBUCION,
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_ERROR_ENVIO_SAP_REINTENTO,
)


def calcular_totales_detalles(detalles: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calcula los totales de la tabla de detalles (suma de costo_doc_sin_iva, subtotal, total).
    No se persisten en BD; el backend los calcula en cada petición para que el frontend
    muestre siempre la misma fuente de verdad.

    Args:
        detalles: Lista de dicts con keys costo_doc_sin_iva, subtotal, total (pueden ser None).

    Returns:
        {"total_costo_unitario": float, "total_subtotal": float, "total_total": float}
    """
    total_costo = 0.0
    total_subtotal = 0.0
    total_total = 0.0
    for d in detalles or []:
        v = d.get("costo_doc_sin_iva")
        if v is not None:
            total_costo += float(v)
        v = d.get("subtotal")
        if v is not None:
            total_subtotal += float(v)
        v = d.get("total")
        if v is not None:
            total_total += float(v)
    return {
        "total_costo_unitario": round(total_costo, 4),
        "total_subtotal": round(total_subtotal, 4),
        "total_total": round(total_total, 4),
    }


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


def pedido_permite_reintento_envio_odc_sap(
    pedido: Dict[str, Any],
    ordenes_compra: List[Dict[str, Any]],
) -> bool:
    """
    Indica si conviene mostrar "Reintentar envío ODC a SAP" en Confirmado redistribución (10).

    Regla de negocio:
    - Mostrar reintento para cualquier ODC en PENDIENTE o ERROR.
    - No mostrar reintento cuando la ODC ya fue enviada correctamente.
    """
    estado_id = get_estado_id_from_pedido(pedido)
    if estado_id == ESTADO_ERROR_ENVIO_SAP_REINTENTO:
        for oc in ordenes_compra or []:
            est = (oc.get("estado") or "").strip().upper()
            if est in ("PENDIENTE", "ERROR"):
                return True
        return False
    if estado_id != ESTADO_PEDIDO_CONFIRMADO:
        return False
    for oc in ordenes_compra or []:
        est = (oc.get("estado") or "").strip().upper()
        if est in ("PENDIENTE", "ERROR"):
            return True
    return False


def enrich_pedido_reintento_envio_odc_sap(pedido: Dict[str, Any], conn) -> None:
    """
    Agrega `puede_reintentar_envio_odc_sap` al dict del pedido (lectura de ODC en BD).
    """
    from src.database.repositories.orden_compra_repository import OrdenCompraRepository

    cab = pedido.get("cabecera") or {}
    pedido_id = cab.get("pedido_id")
    if not pedido_id:
        pedido["puede_reintentar_envio_odc_sap"] = False
        return
    repo = OrdenCompraRepository(conn)
    ocs = repo.get_by_pedido_id(str(pedido_id))
    pedido["puede_reintentar_envio_odc_sap"] = pedido_permite_reintento_envio_odc_sap(pedido, ocs)
