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
# Producción registra "Cantidad a producir" y confirma (req. 1.8); entre
# GESTIONAR_PEDIDO (3) y REDISTRIBUCION/"CONFIRMADO POR EL RAYO" (4)
ESTADO_CONFIRMADO_POR_PRODUCCION = 23
ESTADO_RESPUESTA_PROVEEDOR_CARGADA = 5
ESTADO_CONFIRMADO_PROVEEDOR = 6
ESTADO_REDISTRIBUIDO = 9
ESTADO_PEDIDO_CONFIRMADO = 10
ESTADO_CONFIRMADO_ENVIADO = 12
ESTADO_PENDIENTE_LOGISTICA = 13
ESTADO_ERROR_DATOS_MAESTROS = 14
ESTADO_DESPACHAR_Y_FACTURAR = 17  # Manual: desde Confirmado y Enviado (ODC enviada a SAP)
ESTADO_FINALIZADO = 18  # Estado final del flujo; solo desde Despachar y Facturar
ESTADO_CANCELADO = 19  # Pedido cancelado por MABEL TRADING desde Redistribución
ESTADO_CANCELADO_POR_EL_RAYO = 20  # Pedido cancelado por EL RAYO desde Gestionar Pedido
# Fallo al enviar ODC a SAP (p. ej. prevalidación / conexión); se puede reintentar
ESTADO_ERROR_ENVIO_SAP_REINTENTO = 21
ESTADO_PRODUCCION_POSPUESTA = 22
# Mabel Trading rechaza el pedido "hijo" pospuesto (botón "Rechazar", ex "Cancelar
# Pedido Pospuesto"): queda registrado, sin más acción posible (terminal, como CANCELADO).
ESTADO_RECHAZADO = 24
# Mabel Trading acepta la diferencia pospuesta (botón "Aceptar"): pasa a la cola de
# redistribución sin haber sido "Confirmado por El Rayo" (4) -- solo visible en el
# listado de Redistribución (ver _filtro_redistribucion / excluir_listo_para_redistribucion).
ESTADO_LISTO_PARA_REDISTRIBUCION = 25


# Filtro rápido "solo pendientes" específico de Cargar Plantilla (Mabel Trading, mabel.view):
# estados en los que el pedido ya fue "transaccionado" por otro actor (Producción confirma/pospone,
# Administración El Rayo envía la ODC a SAP) y vuelve a la cancha de Mabel Trading para una decisión
# o acción final (botón Aceptar/Rechazar en Producción Pospuesta, botón Finalizado en Despachar y
# Facturar -- ambos solo disponibles desde CargarPlantillaView.vue). Distinto de
# ESTADOS_REQUIERE_ACCION_PEDIDOS_*/_REDISTRIBUCION_* (otros listados). El histórico "estados de
# respuesta del proveedor" (PENDIENTE_CONFIRMACION_PROVEEDOR/RESPUESTA_PROVEEDOR_CARGADA/
# CONFIRMADO_PROVEEDOR) se eliminó de este archivo: ese flujo de aprobación quedó sin conectar a
# ningún endpoint (PedidoAjusteService.procesar_confirmacion_proveedor huérfano) y sus 2 estados con
# id propio ya están desactivados (migraciones 654/656) -- no se alcanzan en la práctica.
ESTADOS_REQUIERE_ACCION_CARGAR_PLANTILLA_IDS = frozenset({
    ESTADO_PRODUCCION_POSPUESTA,
    ESTADO_DESPACHAR_Y_FACTURAR,
})
ESTADOS_REQUIERE_ACCION_CARGAR_PLANTILLA_NOMBRES = (
    "PRODUCCION_POSPUESTA",
    "DESPACHAR_Y_FACTURAR",
)

# Filtro rápido "solo pendientes" específico del listado de Pedidos (EL RAYO, odcsap.view): el
# pedido ya fue confirmado por Producción o enviado a SAP y vuelve a la cancha de Administración
# El Rayo para revisar/continuar el flujo. Distinto de ESTADOS_REQUIERE_ACCION_CARGAR_PLANTILLA_*
# (propio de Mabel Trading) y de ESTADOS_REQUIERE_ACCION_REDISTRIBUCION_* (propio de la vista de
# Redistribución, aunque comparten el mismo endpoint /api/pedidos) -- cada listado tiene su propio
# significado de "requiere acción" y su propio flag en PedidosFiltros.
ESTADOS_REQUIERE_ACCION_PEDIDOS_IDS = frozenset({
    ESTADO_CONFIRMADO_POR_PRODUCCION,
    ESTADO_CONFIRMADO_ENVIADO,
})
ESTADOS_REQUIERE_ACCION_PEDIDOS_NOMBRES = (
    "CONFIRMADO POR PRODUCCION",
    "CONFIRMADO_POR_PRODUCCION",
    "CONFIRMADO_ENVIADO",
)

# Filtro rápido "solo pendientes" específico del listado de Redistribución (Mabel Trading,
# mabel.view): el pedido ya fue confirmado por EL RAYO (4) o aceptado desde Producción Pospuesta
# (25, botón "Aceptar") y está listo para que Mabel Trading distribuya cantidades por tienda. Ver
# ESTADOS_REQUIERE_ACCION_PEDIDOS_* arriba para el porqué de no compartir un único array entre las
# 3 vistas.
ESTADOS_REQUIERE_ACCION_REDISTRIBUCION_IDS = frozenset({
    ESTADO_REDISTRIBUCION,
    ESTADO_LISTO_PARA_REDISTRIBUCION,
})
ESTADOS_REQUIERE_ACCION_REDISTRIBUCION_NOMBRES = (
    "CONFIRMADO POR EL RAYO",
    "LISTO PARA REDISTRIBUCION",
    "LISTO_PARA_REDISTRIBUCION",
)

# Estados visibles para el perfil Producción El Rayo (req. 1.8, permiso
# produccion-elrayo.view): solo mientras el pedido está en NUEVO_PEDIDO o
# GESTIONAR_PEDIDO; a partir de ahí lo gestiona Administración El Rayo (odcsap.view).
ESTADOS_PRODUCCION_EL_RAYO_IDS = frozenset({
    ESTADO_NUEVO_PEDIDO,
    ESTADO_GESTIONAR_PEDIDO,
})
ESTADOS_PRODUCCION_EL_RAYO_NOMBRES = (
    "NUEVO_PEDIDO",
    "GESTIONAR_PEDIDO",
)

# Estado inicial al subir Excel o crear pedido (siempre id = 1)
ESTADO_INICIAL = ESTADO_BORRADOR

# Estados en los que se permite "Descartar" (Cargar Plantilla): solo Borrador y Nuevo Pedido.
# - Borrador (1): sin notificar
# - Nuevo Pedido (2): notifica a EL RAYO
ESTADOS_PUEDE_DESCARTAR = (ESTADO_BORRADOR, ESTADO_NUEVO_PEDIDO)

# Estados en los que se permite "Cancelar Pedido" por EL RAYO (Detalle del Pedido): solo Confirmado
# por Producción, una vez que Producción ya confirmó el pedido (req. 1.8 segunda fase). Exclusivo
# de odcsap.view (Administración El Rayo); Producción y MABEL ya no pueden usar este botón.
# Cambia estado a CANCELADO POR EL RAYO (20) en lugar de eliminar de la BD.
ESTADOS_PUEDE_CANCELAR_POR_EL_RAYO = (ESTADO_CONFIRMADO_POR_PRODUCCION,)

# Botón "Aceptar" (Producción Pospuesta -> Listo para Redistribución): exclusivo de
# mabel.view, solo desde PRODUCCION_POSPUESTA (mismo estado en el que ya se permite
# "Rechazar", ver ESTADOS_PUEDE_DESCARTAR/puede_cancelar_pedido).
ESTADOS_PUEDE_ACEPTAR_PRODUCCION_POSPUESTA = (ESTADO_PRODUCCION_POSPUESTA,)

# "Cancelar Pedido" (Redistribución): deshabilitar desde Confirmado redistribución (10) en adelante.
# El botón debe estar habilitado solo cuando estado_id < ESTADO_PEDIDO_CONFIRMADO (10).
ESTADO_LIMITE_CANCELAR_PEDIDO: int = ESTADO_PEDIDO_CONFIRMADO  # 10 - Confirmado redistribución

# "Confirmar Redistribución": habilitar solo cuando el pedido está en estado que permite redistribución.
# Estados que permiten confirmar redistribución (antes de CONFIRMADO REDISTRIBUCION y no CANCELADO)
# NOTA: estado_id debe ser >= 4 (REDISTRIBUCION/CONFIRMADO) y < 10 (PEDIDO_CONFIRMADO)
# y NO debe ser CANCELADO (19) -- excepto LISTO_PARA_REDISTRIBUCION (25), que por ser un
# estado añadido después queda fuera de ese rango numérico pero es la misma etapa del
# flujo (pedido "hijo" aceptado directo a la cola de redistribución, ver
# ESTADOS_PUEDE_ACEPTAR_PRODUCCION_POSPUESTA).
ESTADOS_PUEDE_CONFIRMAR_REDISTRIBUCION = frozenset({
    ESTADO_REDISTRIBUCION,  # 4 - CONFIRMADO POR EL RAYO
    ESTADO_RESPUESTA_PROVEEDOR_CARGADA,  # 5
    ESTADO_CONFIRMADO_PROVEEDOR,  # 6
    ESTADO_REDISTRIBUIDO,  # 9
    ESTADO_LISTO_PARA_REDISTRIBUCION,  # 25
})

# "Proceso completo SAP" (endpoints_proceso.py): estados que indican que la
# redistribución YA fue confirmada en un intento anterior (PASO 1 ya corrió con
# éxito). El pedido solo llega a alguno de estos dos estados si un paso POSTERIOR
# (generar ODC o enviar a SAP) falló y quedó pendiente de reintento -- un reintento
# de "Proceso completo SAP" debe continuar desde ahí, no repetir PASO 1: ninguno de
# estos dos estados está en ESTADOS_PUEDE_CONFIRMAR_REDISTRIBUCION, así que
# RedistribucionValidator._validar_estado_pedido lo rechazaría con "La
# redistribución no cumple con las reglas de negocio".
ESTADOS_REDISTRIBUCION_YA_CONFIRMADA = frozenset({
    ESTADO_PEDIDO_CONFIRMADO,  # 10 - PASO 1 recién confirmado, falló PASO 2 (generar ODC)
    ESTADO_ERROR_ENVIO_SAP_REINTENTO,  # 21 - PASO 1 y 2 ok, falló PASO 3 (envío a SAP)
})

# Desde Confirmado Enviado (12) en adelante no se permite ni Descartar ni Cancelar Pedido (DELETE rechazado).

# --- Conjuntos útiles para validaciones --------------------------------------
# Estados en los que el pedido permite redistribución
ESTADOS_PERMITEN_REDISTRIBUCION = frozenset({
    ESTADO_RESPUESTA_PROVEEDOR_CARGADA,
    ESTADO_CONFIRMADO_PROVEEDOR,
    ESTADO_BORRADOR,  # por si acaso
})

# Estados válidos para generar ODC (orden de compra)
ESTADOS_VALIDOS_PARA_ODC = frozenset({
    ESTADO_CONFIRMADO_PROVEEDOR,
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_ERROR_ENVIO_SAP_REINTENTO,
})

# Estados en los que el proveedor no puede modificar (bloqueados)
ESTADOS_BLOQUEADOS_PROVEEDOR = frozenset({
    ESTADO_CONFIRMADO_PROVEEDOR,
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_ERROR_ENVIO_SAP_REINTENTO,
    ESTADO_CONFIRMADO_ENVIADO,
    ESTADO_PRODUCCION_POSPUESTA,
})

# Ids conocidos del sistema (para validar que un id existe)
ESTADO_IDS_VALIDOS = frozenset({
    ESTADO_BORRADOR,
    ESTADO_NUEVO_PEDIDO,
    ESTADO_GESTIONAR_PEDIDO,
    ESTADO_REDISTRIBUCION,
    ESTADO_RESPUESTA_PROVEEDOR_CARGADA,
    ESTADO_CONFIRMADO_PROVEEDOR,
    ESTADO_REDISTRIBUIDO,
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_CONFIRMADO_ENVIADO,
    ESTADO_PENDIENTE_LOGISTICA,
    ESTADO_ERROR_DATOS_MAESTROS,
    ESTADO_DESPACHAR_Y_FACTURAR,
    ESTADO_FINALIZADO,
    ESTADO_CANCELADO,
    ESTADO_CANCELADO_POR_EL_RAYO,
    ESTADO_ERROR_ENVIO_SAP_REINTENTO,
    ESTADO_PRODUCCION_POSPUESTA,
    ESTADO_CONFIRMADO_POR_PRODUCCION,
    ESTADO_RECHAZADO,
    ESTADO_LISTO_PARA_REDISTRIBUCION,
})

# --- Mapping legacy string → id (solo para migración / compat temporal) -------
# Usar en migración de datos o mientras se convierte código a estado_id.
# No usar en lógica nueva: la verdad es el id.
LEGACY_STRING_TO_ID = {
    "PENDIENTE_CONFIRMACION_PROVEEDOR": ESTADO_BORRADOR,
    "BORRADOR": ESTADO_BORRADOR,
    "NUEVO_PEDIDO": ESTADO_NUEVO_PEDIDO,
    "NUEVO PEDIDO": ESTADO_NUEVO_PEDIDO,
    "GESTIONAR_PEDIDO": ESTADO_GESTIONAR_PEDIDO,
    "GESTIONAR PEDIDO": ESTADO_GESTIONAR_PEDIDO,
    "EN_REVISION": ESTADO_REDISTRIBUCION,
    "REDISTRIBUCION": ESTADO_REDISTRIBUCION,
    "CONFIRMADO": ESTADO_REDISTRIBUCION,
    "CONFIRMADO POR EL RAYO": ESTADO_REDISTRIBUCION,
    "RESPUESTA_PROVEEDOR_CARGADA": ESTADO_RESPUESTA_PROVEEDOR_CARGADA,
    "CONFIRMADO_PROVEEDOR": ESTADO_CONFIRMADO_PROVEEDOR,
    "REDISTRIBUIDO": ESTADO_REDISTRIBUIDO,
    "PEDIDO_CONFIRMADO": ESTADO_PEDIDO_CONFIRMADO,
    "CONFIRMADO REDISTRIBUCION": ESTADO_PEDIDO_CONFIRMADO,
    "CONFIRMADO_ENVIADO": ESTADO_CONFIRMADO_ENVIADO,
    "PENDIENTE_LOGISTICA": ESTADO_PENDIENTE_LOGISTICA,
    "ERROR_DATOS_MAESTROS": ESTADO_ERROR_DATOS_MAESTROS,
    "DESPACHAR Y FACTURAR": ESTADO_DESPACHAR_Y_FACTURAR,
    "DESPACHAR_Y_FACTURAR": ESTADO_DESPACHAR_Y_FACTURAR,
    "FINALIZADO": ESTADO_FINALIZADO,
    "CANCELADO": ESTADO_CANCELADO,
    "CANCELADO POR EL RAYO": ESTADO_CANCELADO_POR_EL_RAYO,
    "CANCELADO_POR_EL_RAYO": ESTADO_CANCELADO_POR_EL_RAYO,
    "ERROR ENVIO SAP REINTENTO": ESTADO_ERROR_ENVIO_SAP_REINTENTO,
    "ERROR_ENVIO_SAP_REINTENTO": ESTADO_ERROR_ENVIO_SAP_REINTENTO,
    "PRODUCCION_POSPUESTA": ESTADO_PRODUCCION_POSPUESTA,
    "PRODUCCION POSPUESTA": ESTADO_PRODUCCION_POSPUESTA,
    "CONFIRMADO POR PRODUCCION": ESTADO_CONFIRMADO_POR_PRODUCCION,
    "CONFIRMADO_POR_PRODUCCION": ESTADO_CONFIRMADO_POR_PRODUCCION,
    "RECHAZADO": ESTADO_RECHAZADO,
    "LISTO PARA REDISTRIBUCION": ESTADO_LISTO_PARA_REDISTRIBUCION,
    "LISTO_PARA_REDISTRIBUCION": ESTADO_LISTO_PARA_REDISTRIBUCION,
}


def estado_id_desde_legacy(estado_string: str | None) -> int:
    """Convierte estado legacy (string) a estado_id. Desconocido/NULL → 1 (BORRADOR)."""
    if not estado_string or not estado_string.strip():
        return ESTADO_BORRADOR
    return LEGACY_STRING_TO_ID.get(estado_string.strip().upper(), ESTADO_BORRADOR)


def es_estado_valido(estado_id: int) -> bool:
    """Indica si el id es un estado conocido."""
    return estado_id in ESTADO_IDS_VALIDOS
