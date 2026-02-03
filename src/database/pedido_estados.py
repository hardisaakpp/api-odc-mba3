# =============================================================================
# Estados del pedido: constantes por id (verdad absoluta del sistema)
# =============================================================================
# El estado_id es inmutable; el nombre es solo presentación (editable en
# tabla pedido_estado). Usar siempre estos ids en lógica, validaciones y
# actualizaciones. API devuelve estado_id + estado_nombre (desde BD).
# =============================================================================

# --- Ids semánticos (no depender del "orden" en BD) --------------------------
ESTADO_BORRADOR = 1
ESTADO_NUEVO_PEDIDO = 2  # Enviado a EL RAYO (notificación enviada)
ESTADO_RESPUESTA_PROVEEDOR_CARGADA = 3
ESTADO_EN_REVISION = 4
ESTADO_CONFIRMADO_PROVEEDOR = 5
ESTADO_RECHAZADO_PROVEEDOR = 6
ESTADO_EN_AJUSTE_MABEL = 7
ESTADO_REDISTRIBUIDO = 8
ESTADO_PEDIDO_CONFIRMADO = 9
ESTADO_PROCESADO_SAP = 10
ESTADO_CONFIRMADO_ENVIADO = 11
ESTADO_PENDIENTE_LOGISTICA = 12
ESTADO_ERROR_DATOS_MAESTROS = 13
ESTADO_EN_PROCESO = 14
ESTADO_COMPLETADO = 15
ESTADO_GESTIONAR_PEDIDO = 16  # Al hacer clic en "Ver Detalle" desde la tabla Pedidos

# Estado inicial al subir Excel o crear pedido (siempre id = 1)
ESTADO_INICIAL = ESTADO_BORRADOR

# --- Conjuntos útiles para validaciones --------------------------------------
# Estados en los que el pedido permite redistribución
ESTADOS_PERMITEN_REDISTRIBUCION = frozenset({
    ESTADO_RESPUESTA_PROVEEDOR_CARGADA,
    ESTADO_CONFIRMADO_PROVEEDOR,
    ESTADO_EN_AJUSTE_MABEL,
    ESTADO_BORRADOR,  # por si acaso
})

# Estados válidos para generar ODC (orden de compra)
ESTADOS_VALIDOS_PARA_ODC = frozenset({
    ESTADO_CONFIRMADO_PROVEEDOR,
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_PROCESADO_SAP,
})

# Estados en los que el proveedor no puede modificar (bloqueados)
ESTADOS_BLOQUEADOS_PROVEEDOR = frozenset({
    ESTADO_CONFIRMADO_PROVEEDOR,
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_CONFIRMADO_ENVIADO,
    ESTADO_COMPLETADO,
})

# Todos los ids conocidos (para validar que un id existe)
ESTADO_IDS_VALIDOS = frozenset({
    ESTADO_BORRADOR,
    ESTADO_NUEVO_PEDIDO,
    ESTADO_RESPUESTA_PROVEEDOR_CARGADA,
    ESTADO_EN_REVISION,
    ESTADO_CONFIRMADO_PROVEEDOR,
    ESTADO_RECHAZADO_PROVEEDOR,
    ESTADO_EN_AJUSTE_MABEL,
    ESTADO_REDISTRIBUIDO,
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_PROCESADO_SAP,
    ESTADO_CONFIRMADO_ENVIADO,
    ESTADO_PENDIENTE_LOGISTICA,
    ESTADO_ERROR_DATOS_MAESTROS,
    ESTADO_EN_PROCESO,
    ESTADO_COMPLETADO,
})

# --- Mapping legacy string → id (solo para migración / compat temporal) -------
# Usar en migración de datos o mientras se convierte código a estado_id.
# No usar en lógica nueva: la verdad es el id.
LEGACY_STRING_TO_ID = {
    "PENDIENTE_CONFIRMACION_PROVEEDOR": ESTADO_BORRADOR,
    "BORRADOR": ESTADO_BORRADOR,
    "NUEVO_PEDIDO": ESTADO_NUEVO_PEDIDO,
    "RESPUESTA_PROVEEDOR_CARGADA": ESTADO_RESPUESTA_PROVEEDOR_CARGADA,
    "EN_REVISION": ESTADO_EN_REVISION,
    "CONFIRMADO_PROVEEDOR": ESTADO_CONFIRMADO_PROVEEDOR,
    "RECHAZADO_PROVEEDOR": ESTADO_RECHAZADO_PROVEEDOR,
    "EN_AJUSTE_MABEL": ESTADO_EN_AJUSTE_MABEL,
    "REDISTRIBUIDO": ESTADO_REDISTRIBUIDO,
    "PEDIDO_CONFIRMADO": ESTADO_PEDIDO_CONFIRMADO,
    "PROCESADO_SAP": ESTADO_PROCESADO_SAP,
    "CONFIRMADO_ENVIADO": ESTADO_CONFIRMADO_ENVIADO,
    "PENDIENTE_LOGISTICA": ESTADO_PENDIENTE_LOGISTICA,
    "ERROR_DATOS_MAESTROS": ESTADO_ERROR_DATOS_MAESTROS,
    "EN_PROCESO": ESTADO_EN_PROCESO,
    "COMPLETADO": ESTADO_COMPLETADO,
    "GESTIONAR_PEDIDO": ESTADO_GESTIONAR_PEDIDO,
}


def estado_id_desde_legacy(estado_string: str | None) -> int:
    """Convierte estado legacy (string) a estado_id. Desconocido/NULL → 1 (BORRADOR)."""
    if not estado_string or not estado_string.strip():
        return ESTADO_BORRADOR
    return LEGACY_STRING_TO_ID.get(estado_string.strip().upper(), ESTADO_BORRADOR)


def es_estado_valido(estado_id: int) -> bool:
    """Indica si el id es un estado conocido."""
    return estado_id in ESTADO_IDS_VALIDOS
