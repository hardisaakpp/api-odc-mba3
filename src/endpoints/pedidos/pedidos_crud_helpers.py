"""
Funciones auxiliares para pedidos_crud.py.

Este módulo contiene helpers puros extraídos para reducir duplicación
y mejorar la mantenibilidad del código de endpoints CRUD de pedidos.
"""

from typing import Optional, Dict, Any, List

from src.database.pedido_estados import (
    ESTADO_REDISTRIBUCION,
    ESTADO_CONFIRMADO_ENVIADO,
    ESTADO_DESPACHAR_Y_FACTURAR,
    ESTADOS_PUEDE_DESCARTAR,
    ESTADOS_PUEDE_CANCELAR_POR_EL_RAYO,
    ESTADO_LIMITE_CANCELAR_PEDIDO,
    ESTADO_PRODUCCION_POSPUESTA,
    ESTADOS_PUEDE_ACEPTAR_PRODUCCION_POSPUESTA,
    ESTADOS_PUEDE_CONFIRMAR_REDISTRIBUCION,
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_ERROR_ENVIO_SAP_REINTENTO,
    ESTADO_LISTO_PARA_REDISTRIBUCION,
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


def calcular_diferencia_produccion(detalles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Req. 1.2 (pedidos parciales): detecta líneas cuyo "total" vigente quedó por debajo
    de la cantidad que Mabel Trading solicitó originalmente en la plantilla Excel
    (cantidad_solicitada_original, inmutable desde el INSERT -- ver
    PedidoDetalleRepository.insert y PedidoUtils._agregar_cantidad_solicitada_original).

    Ignora líneas sin cantidad_solicitada_original (pedidos anteriores a la migración 641,
    o valor NULL) -- no hay base para comparar.

    Returns:
        {"tiene_diferencia": bool, "detalles": [{pedido_detalle_id, codigo_interno,
         descripcion_sap, cantidad_solicitada_original, total_actual, diferencia}, ...]}
    """
    detalles_con_diferencia = []
    for d in detalles or []:
        original = d.get("cantidad_solicitada_original")
        total_actual = d.get("total")
        if original is None or total_actual is None:
            continue
        original = float(original)
        total_actual = float(total_actual)
        if total_actual < original:
            detalles_con_diferencia.append({
                "pedido_detalle_id": d.get("pedido_detalle_id"),
                "codigo_interno": d.get("codigo_interno"),
                "descripcion_sap": d.get("descripcion_sap"),
                "cantidad_solicitada_original": original,
                "total_actual": total_actual,
                "diferencia": round(original - total_actual, 4),
            })
    return {
        "tiene_diferencia": len(detalles_con_diferencia) > 0,
        "detalles": detalles_con_diferencia,
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
    - puede_cancelar_pedido: bool - Si MABEL puede cancelar el pedido (o "Rechazar" si esta en PRODUCCION_POSPUESTA)
    - puede_aceptar_produccion_pospuesta: bool - Si MABEL puede aceptar la diferencia pospuesta (boton "Aceptar")
    - puede_descargar_csv: bool - Si se puede descargar CSV (solo estado REDISTRIBUCION)
    - puede_generar_txt_mba3: bool - Si se puede generar el TXT MBA3 (solo estado CONFIRMADO_ENVIADO / "CONFIRMADO Y ENVIADO", ver PYTD002_ODC-MABEL-RAYO_SEGUIMIENTO.md 1.7)
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
    # Req. 1.2: PRODUCCION_POSPUESTA (22) es numéricamente mayor al límite pero anterior
    # en el flujo real (pedido "hijo" a la espera de una futura producción) -- mismo
    # motivo por el que ya se excluye de _filtro_redistribucion; Mabel Trading puede
    # cancelarlo si prefiere gestionar la diferencia por su cuenta.
    pedido["puede_cancelar_pedido"] = estado_id is not None and (
        estado_id < ESTADO_LIMITE_CANCELAR_PEDIDO or estado_id == ESTADO_PRODUCCION_POSPUESTA
    )
    # Botón "Aceptar" (Producción Pospuesta -> Listo para Redistribución), exclusivo mabel.view
    pedido["puede_aceptar_produccion_pospuesta"] = estado_id in ESTADOS_PUEDE_ACEPTAR_PRODUCCION_POSPUESTA
    pedido["puede_descargar_csv"] = estado_id == ESTADO_REDISTRIBUCION
    # req. 1.7 / RN-01: el requerimiento pide gatillar con "Confirmado por El Rayo"
    # (ESTADO_REDISTRIBUCION = 4), pero el DocNum de SAP que exige la columna 12 del
    # TXT recién existe en CONFIRMADO_ENVIADO (12) -- ver docs/requeriments/
    # PYTD002_ODC-MABEL-RAYO_SEGUIMIENTO.md, punto 1.7, para el detalle de la decisión.
    pedido["puede_generar_txt_mba3"] = estado_id == ESTADO_CONFIRMADO_ENVIADO
    pedido["puede_confirmar_redistribucion"] = estado_id in ESTADOS_PUEDE_CONFIRMAR_REDISTRIBUCION
    pedido["puede_finalizar"] = estado_id == ESTADO_DESPACHAR_Y_FACTURAR


_PERM_ODCSAP_VIEW = 'odcsap.view'
_PERM_MABEL_VIEW = 'mabel.view'
_PERM_PRODUCCION_ELRAYO_VIEW = 'produccion-elrayo.view'

# RN-03: campos de costo/precio/margen que Producción El Rayo no debe recibir. "total"
# (Cantidad Total solicitada) y "total_total" quedan fuera a propósito: son cantidad, no
# costo, y 1.8 los declara explícitamente visibles para este perfil. "pvp" NO va en esta
# lista porque tiene su propia regla de visibilidad, más amplia: ver
# ocultar_pvp_si_no_mabel (corregido 2026-08-19: revierte la excepción del 2026-08-17;
# ahora también se oculta a odcsap.view, no solo a produccion-elrayo.view).
_CAMPOS_COSTO_DETALLE = ("costo_doc_sin_iva", "descuento_1", "subtotal", "costo_margen", "costo_unitario", "margen")
_CAMPOS_COSTO_TOTALES = ("total_costo_unitario", "total_subtotal")


def es_solo_produccion_el_rayo(user: Dict[str, Any]) -> bool:
    """True si el usuario NO tiene odcsap.view ni mabel.view (los perfiles que sí deben
    ver costos/precios/márgenes), pero sí tiene produccion-elrayo.view."""
    permissions = user.get("permissions") or []
    if _PERM_ODCSAP_VIEW in permissions or _PERM_MABEL_VIEW in permissions:
        return False
    return _PERM_PRODUCCION_ELRAYO_VIEW in permissions


def es_campo_costo_detalle(campo: Optional[str]) -> bool:
    """RN-03: True si `campo` es uno de los campos de costo/precio/margen de
    pedido_detalle que Producción El Rayo no debe ver (ver
    ocultar_costos_para_produccion_el_rayo / _CAMPOS_COSTO_DETALLE)."""
    return campo in _CAMPOS_COSTO_DETALLE


def ocultar_costos_para_produccion_el_rayo(
    user: Dict[str, Any],
    detalles: Optional[List[Dict[str, Any]]] = None,
    totales: Optional[Dict[str, Any]] = None,
) -> None:
    """RN-03: si quien pide la respuesta tiene únicamente produccion-elrayo.view, anula
    (in-place) los campos de costo/precio/margen en `detalles` y `totales` antes de
    serializar la respuesta HTTP.

    Debe llamarse SOLO justo antes de devolver la respuesta al cliente -- nunca antes,
    porque otros pasos de la misma petición (cálculo de OC hacia SAP, notificaciones,
    auditoría) siguen necesitando el valor real. No se elimina la clave (para no romper
    el tipado del frontend, que ya trata estos campos como opcionales/nulos); se deja en
    None, igual que cuando el dato simplemente no existe.
    """
    if not es_solo_produccion_el_rayo(user):
        return
    for detalle in detalles or []:
        for campo in _CAMPOS_COSTO_DETALLE:
            if campo in detalle:
                detalle[campo] = None
    if isinstance(totales, dict):
        for campo in _CAMPOS_COSTO_TOTALES:
            if campo in totales:
                totales[campo] = None


def debe_ocultar_pvp(user: Dict[str, Any]) -> bool:
    """True si el usuario no tiene mabel.view -- el único permiso que debe ver PVP
    (precio de venta al público). Cubre tanto odcsap.view como produccion-elrayo.view,
    aunque el usuario tenga ambos a la vez. Corregido 2026-08-19."""
    permissions = user.get("permissions") or []
    return _PERM_MABEL_VIEW not in permissions


def ocultar_pvp_si_no_mabel(
    user: Dict[str, Any],
    detalles: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Anula (in-place, igual que ocultar_costos_para_produccion_el_rayo) el campo
    "pvp" de cada detalle si el usuario no debe verlo (ver debe_ocultar_pvp)."""
    if not debe_ocultar_pvp(user):
        return
    for detalle in detalles or []:
        if "pvp" in detalle:
            detalle["pvp"] = None


def _oc_permite_reintento_envio_por_detalle_error(oc: Dict[str, Any]) -> bool:
    """Errores SAP/conexión reintentables; maestro puro u otros códigos no listados → False."""
    from src.database.services.retry_utils import (
        _parse_sap_b1_error_code,
        mensaje_sugiere_reintento_transitorio,
    )

    sap_codes_reintento_manual = {-1116}
    msg = f"{oc.get('respuesta_sap') or ''} {oc.get('error_message') or ''}"
    src = (oc.get("error_source") or "").strip().upper()
    sap_code = _parse_sap_b1_error_code(oc.get("error_code"))
    if sap_code in sap_codes_reintento_manual:
        return True
    if src == "SAP_CONNECTION":
        return True
    if mensaje_sugiere_reintento_transitorio(msg):
        return True
    return False


def _es_reintentable_en_estado_confirmado(ordenes_compra: List[Dict[str, Any]]) -> bool:
    """Evalúa si se puede reintentar ODC en estado CONFIRMADO."""
    if not ordenes_compra:
        return True
    for oc in ordenes_compra or []:
        est = (oc.get("estado") or "").strip().upper()
        if est == "PENDIENTE":
            return True
        if est == "ERROR" and _oc_permite_reintento_envio_por_detalle_error(oc):
            return True
    return False

def _es_reintentable_en_estado_error(ordenes_compra: List[Dict[str, Any]]) -> bool:
    """Evalúa si se puede reintentar ODC en estado ERROR ENVÍO SAP."""
    for oc in ordenes_compra or []:
        est = (oc.get("estado") or "").strip().upper()
        if est in ("PENDIENTE", "ERROR"):
            return True
    return False

def pedido_permite_reintento_envio_odc_sap(
    pedido: Dict[str, Any],
    ordenes_compra: List[Dict[str, Any]],
) -> bool:
    """
    Indica si el flag `puede_reintentar_envio_odc_sap` debe ser True.

    Reglas por estado del pedido:

    - Estado 4 (`ESTADO_REDISTRIBUCION` = "CONFIRMADO POR EL RAYO") y estado 25
      (`ESTADO_LISTO_PARA_REDISTRIBUCION`, pedido "hijo" aceptado por el botón "Aceptar"
      que entra directo a la cola de redistribución sin pasar por "Confirmado por El
      Rayo" -- ver ESTADOS_PUEDE_ACEPTAR_PRODUCCION_POSPUESTA): vista de redistribución.
      El botón es solo "Enviar ODC a SAP" (proceso completo). Aquí NO hay reintento —
      esa funcionalidad vive en /proceso. Por eso siempre True; el front decide
      habilitación con `puede_confirmar_redistribucion`.

    - Estado 10 (`ESTADO_PEDIDO_CONFIRMADO` = "CONFIRMADO REDISTRIBUCION"):
      sin ODC → primer envío; PENDIENTE → sí; ERROR → solo si el detalle sugiere
      reintento (conexión, código -1116, etc.). Errores de maestro no reintentables.

    - Estado 21 (`ESTADO_ERROR_ENVIO_SAP_REINTENTO`):
      cualquier ODC PENDIENTE o ERROR puede reintentarse.
    """
    estado_id = get_estado_id_from_pedido(pedido)

    if estado_id in (ESTADO_REDISTRIBUCION, ESTADO_LISTO_PARA_REDISTRIBUCION):
        return True

    if estado_id == ESTADO_PEDIDO_CONFIRMADO:
        return _es_reintentable_en_estado_confirmado(ordenes_compra)

    if estado_id == ESTADO_ERROR_ENVIO_SAP_REINTENTO:
        return _es_reintentable_en_estado_error(ordenes_compra)

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
