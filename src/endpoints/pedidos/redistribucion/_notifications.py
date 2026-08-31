"""Notificaciones relacionadas a redistribución."""

from src.utils.email_notifier import send_mabel_redistribucion_confirmacion_notification

# Permiso destinatario de todas las notificaciones SSE de este módulo (evita
# duplicar el literal, SonarQube python:S1192).
_PERMISO_ODCSAP_VIEW = "odcsap.view"


async def notificar_redistribucion_confirmada(pedido_id: str, numero_pedido: str) -> None:
    """Envía notificación en tiempo real a EL RAYO."""
    from src.utils.notification_manager import notification_manager, NotificationType

    await notification_manager.notify(
        target_permission=_PERMISO_ODCSAP_VIEW,
        title="Redistribución confirmada por MABEL TRADING",
        message=f"La redistribución del pedido {numero_pedido} ha sido confirmada.",
        notification_type=NotificationType.SUCCESS,
        metadata={
            "pedido_id": pedido_id,
            "numero_pedido": numero_pedido,
            "accion": "redistribucion_confirmada",
        },
    )


async def notificar_redistribucion_creada(pedido_id: str, numero_pedido: str) -> None:
    """Envía notificación en tiempo real a EL RAYO cuando MABEL TRADING crea/edita una
    propuesta de redistribución (antes de confirmarla)."""
    from src.utils.notification_manager import notification_manager, NotificationType

    await notification_manager.notify(
        target_permission=_PERMISO_ODCSAP_VIEW,
        title="Nueva redistribución de pedido",
        message=f"MABEL TRADING redistribuyó las cantidades del pedido {numero_pedido} entre tiendas.",
        notification_type=NotificationType.INFO,
        metadata={
            "pedido_id": pedido_id,
            "numero_pedido": numero_pedido,
            "accion": "redistribucion_creada",
        },
    )


async def notificar_redistribucion_procesada_sap(pedido_id: str, numero_pedido: str) -> None:
    """Envía notificación en tiempo real a EL RAYO cuando el pedido queda confirmado tras
    el procesamiento/homologación en SAP posterior a la confirmación de redistribución."""
    from src.utils.notification_manager import notification_manager, NotificationType

    await notification_manager.notify(
        target_permission=_PERMISO_ODCSAP_VIEW,
        title="Pedido confirmado tras redistribución",
        message=f"El pedido {numero_pedido} fue confirmado tras el procesamiento en SAP y está listo para continuar el flujo.",
        notification_type=NotificationType.SUCCESS,
        metadata={
            "pedido_id": pedido_id,
            "numero_pedido": numero_pedido,
            "accion": "redistribucion_procesada_sap",
        },
    )


def construir_mensaje_error_envio_odc_sap(mensaje: str, es_error_real: bool = True):
    """Constructor puro (sin I/O) del título/mensaje/tipo de la notificación de error de
    envío de ODC a SAP. Reutilizado tanto por notificar_error_envio_odc_sap (camino
    síncrono en el proceso FastAPI) como por el publisher del lado Celery (ver
    src/utils/sse_redis_bridge.py) para que el texto no diverja entre ambos caminos."""
    titulo = "Error al enviar ODC a SAP" if es_error_real else "ODC pendiente de confirmación en SAP"
    tipo = "error" if es_error_real else "warning"
    return titulo, mensaje, tipo


async def notificar_error_envio_odc_sap(
    pedido_id: str, numero_pedido: str, mensaje: str, es_error_real: bool = True,
) -> None:
    """Envía notificación en tiempo real a EL RAYO cuando el envío de la ODC a SAP falla
    (o queda encolada por saturación) y el pedido queda pendiente de reintento manual."""
    from src.utils.notification_manager import notification_manager, NotificationType

    titulo, mensaje, tipo = construir_mensaje_error_envio_odc_sap(mensaje, es_error_real)
    await notification_manager.notify(
        target_permission=_PERMISO_ODCSAP_VIEW,
        title=titulo,
        message=mensaje,
        notification_type=NotificationType(tipo),
        metadata={
            "pedido_id": pedido_id,
            "numero_pedido": numero_pedido,
            "accion": "error_envio_odc_sap",
        },
    )


def construir_mensaje_odc_enviada_a_sap(numero_pedido: str, doc_num: str | None = None, st_error: bool = False):
    """Constructor puro (sin I/O) del título/mensaje/tipo de la notificación de ODC enviada
    a SAP. Reutilizado tanto por notificar_odc_enviada_a_sap (camino síncrono en el proceso
    FastAPI) como por el publisher del lado Celery (ver src/utils/sse_redis_bridge.py) para
    que el texto no diverja entre ambos caminos (el async/Celery es el camino preferido en
    producción cuando hay workers disponibles)."""
    mensaje = f"La ODC del pedido {numero_pedido} se envió exitosamente a SAP"
    if doc_num:
        mensaje += f" (DocNum: {doc_num})"

    if st_error:
        mensaje += ", pero algunas Solicitudes de Transferencia no se pudieron crear. Revisa el detalle."
        return "ODC enviada con problemas en Solicitudes de Transferencia", mensaje, "warning"
    return "ODC enviada a SAP exitosamente", mensaje, "success"


async def notificar_odc_enviada_a_sap(
    pedido_id: str, numero_pedido: str, doc_num: str | None = None, st_error: bool = False,
) -> None:
    """Envía notificación en tiempo real a EL RAYO cuando la ODC se envía exitosamente a SAP.
    Una sola notificación con 2 variantes: normal, o con aviso si alguna Solicitud de
    Transferencia (ITR) de esa ODC no se pudo crear (ver OCSAPService._detectar_error_en_st)."""
    from src.utils.notification_manager import notification_manager, NotificationType

    titulo, mensaje, tipo = construir_mensaje_odc_enviada_a_sap(numero_pedido, doc_num, st_error)
    await notification_manager.notify(
        target_permission=_PERMISO_ODCSAP_VIEW,
        title=titulo,
        message=mensaje,
        notification_type=NotificationType(tipo),
        metadata={
            "pedido_id": pedido_id,
            "numero_pedido": numero_pedido,
            "doc_num": doc_num,
            "st_error": st_error,
            "accion": "odc_enviada_sap",
        },
    )


def enviar_email_confirmacion_redistribucion(
    pedido_id: str,
    numero_pedido: str,
    user_id: str,
    version: int,
    resumen,
) -> bool:
    """Envía email de confirmación de redistribución."""
    return send_mabel_redistribucion_confirmacion_notification(
        pedido_id=pedido_id,
        numero_pedido=numero_pedido,
        usuario_mabel=user_id,
        version_confirmada=version,
        total_productos=resumen.total_productos if resumen else 0,
        total_cantidad_ajustada=resumen.total_cantidad_ajustada if resumen else 0,
    )
