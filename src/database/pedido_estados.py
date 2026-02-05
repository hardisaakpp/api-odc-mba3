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
ESTADO_GESTIONAR_PEDIDO = 3  # Al hacer clic en "Ver Detalle" desde la tabla Pedidos
ESTADO_REDISTRIBUCION = 4  # "CONFIRMADO POR EL RAYO" - Tras confirmar (EL RAYO)
ESTADO_RESPUESTA_PROVEEDOR_CARGADA = 5
ESTADO_CONFIRMADO_PROVEEDOR = 6
ESTADO_RECHAZADO_PROVEEDOR = 7
ESTADO_EN_AJUSTE_MABEL = 8
ESTADO_REDISTRIBUIDO = 9
ESTADO_PEDIDO_CONFIRMADO = 10
ESTADO_PROCESADO_SAP = 11
ESTADO_CONFIRMADO_ENVIADO = 12
ESTADO_PENDIENTE_LOGISTICA = 13
ESTADO_ERROR_DATOS_MAESTROS = 14
ESTADO_EN_PROCESO = 15
ESTADO_COMPLETADO = 16
ESTADO_DESPACHAR_Y_FACTURAR = 17  # Manual: desde Confirmado y Enviado (ODC enviada a SAP)
ESTADO_FINALIZADO = 18  # Estado final del flujo; solo desde Despachar y Facturar
ESTADO_CANCELADO = 19  # Pedido cancelado por MABEL TRADING desde Redistribución

# Estado inicial al subir Excel o crear pedido (siempre id = 1)
ESTADO_INICIAL = ESTADO_BORRADOR

# Estados en los que se permite "Descartar" (Cargar Plantilla): solo Borrador y Nuevo Pedido.
# - Borrador (1): sin notificar
# - Nuevo Pedido (2): notifica a EL RAYO
ESTADOS_PUEDE_DESCARTAR = (ESTADO_BORRADOR, ESTADO_NUEVO_PEDIDO)

# Estados en los que se permite "Eliminar Pedido" (Detalle del Pedido): solo Gestionar Pedido.
# - Gestionar Pedido (3): sin notificar
ESTADOS_PUEDE_ELIMINAR = (ESTADO_GESTIONAR_PEDIDO,)

# "Cancelar Pedido" (Redistribución): deshabilitar desde Confirmado redistribución (10) en adelante.
# El botón debe estar habilitado solo cuando estado_id < ESTADO_PEDIDO_CONFIRMADO (10).
ESTADO_LIMITE_CANCELAR_PEDIDO = ESTADO_PEDIDO_CONFIRMADO  # 10 - Confirmado redistribución

# "Confirmar Redistribución": habilitar solo cuando el pedido está en estado que permite redistribución.
# Estados que permiten confirmar redistribución (antes de CONFIRMADO REDISTRIBUCION y no CANCELADO)
# NOTA: estado_id debe ser >= 4 (REDISTRIBUCION/CONFIRMADO) y < 10 (PEDIDO_CONFIRMADO) 
# y NO debe ser CANCELADO (19)
ESTADOS_PUEDE_CONFIRMAR_REDISTRIBUCION = frozenset({
    ESTADO_REDISTRIBUCION,  # 4 - CONFIRMADO POR EL RAYO
    ESTADO_RESPUESTA_PROVEEDOR_CARGADA,  # 5
    ESTADO_CONFIRMADO_PROVEEDOR,  # 6
    ESTADO_EN_AJUSTE_MABEL,  # 8
    ESTADO_REDISTRIBUIDO,  # 9
})

# Desde Confirmado Enviado (12) en adelante no se permite ni Descartar ni Cancelar Pedido (DELETE rechazado).

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
    ESTADO_GESTIONAR_PEDIDO,
    ESTADO_REDISTRIBUCION,
    ESTADO_RESPUESTA_PROVEEDOR_CARGADA,
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
    ESTADO_DESPACHAR_Y_FACTURAR,
    ESTADO_FINALIZADO,
    ESTADO_CANCELADO,
})

# --- Mapping legacy string → id (solo para migración / compat temporal) -------
# Usar en migración de datos o mientras se convierte código a estado_id.
# No usar en lógica nueva: la verdad es el id.
LEGACY_STRING_TO_ID = {
    "PENDIENTE_CONFIRMACION_PROVEEDOR": ESTADO_BORRADOR,
    "BORRADOR": ESTADO_BORRADOR,
    "NUEVO_PEDIDO": ESTADO_NUEVO_PEDIDO,
    "GESTIONAR_PEDIDO": ESTADO_GESTIONAR_PEDIDO,
    "EN_REVISION": ESTADO_REDISTRIBUCION,
    "REDISTRIBUCION": ESTADO_REDISTRIBUCION,
    "CONFIRMADO": ESTADO_REDISTRIBUCION,
    "CONFIRMADO POR EL RAYO": ESTADO_REDISTRIBUCION,
    "RESPUESTA_PROVEEDOR_CARGADA": ESTADO_RESPUESTA_PROVEEDOR_CARGADA,
    "CONFIRMADO_PROVEEDOR": ESTADO_CONFIRMADO_PROVEEDOR,
    "RECHAZADO_PROVEEDOR": ESTADO_RECHAZADO_PROVEEDOR,
    "EN_AJUSTE_MABEL": ESTADO_EN_AJUSTE_MABEL,
    "REDISTRIBUIDO": ESTADO_REDISTRIBUIDO,
    "PEDIDO_CONFIRMADO": ESTADO_PEDIDO_CONFIRMADO,
    "CONFIRMADO REDISTRIBUCION": ESTADO_PEDIDO_CONFIRMADO,
    "PROCESADO_SAP": ESTADO_PROCESADO_SAP,
    "CONFIRMADO_ENVIADO": ESTADO_CONFIRMADO_ENVIADO,
    "PENDIENTE_LOGISTICA": ESTADO_PENDIENTE_LOGISTICA,
    "ERROR_DATOS_MAESTROS": ESTADO_ERROR_DATOS_MAESTROS,
    "EN_PROCESO": ESTADO_EN_PROCESO,
    "COMPLETADO": ESTADO_COMPLETADO,
    "DESPACHAR Y FACTURAR": ESTADO_DESPACHAR_Y_FACTURAR,
    "DESPACHAR_Y_FACTURAR": ESTADO_DESPACHAR_Y_FACTURAR,
    "FINALIZADO": ESTADO_FINALIZADO,
    "CANCELADO": ESTADO_CANCELADO,
}


def estado_id_desde_legacy(estado_string: str | None) -> int:
    """Convierte estado legacy (string) a estado_id. Desconocido/NULL → 1 (BORRADOR)."""
    if not estado_string or not estado_string.strip():
        return ESTADO_BORRADOR
    return LEGACY_STRING_TO_ID.get(estado_string.strip().upper(), ESTADO_BORRADOR)


def es_estado_valido(estado_id: int) -> bool:
    """Indica si el id es un estado conocido."""
    return estado_id in ESTADO_IDS_VALIDOS
