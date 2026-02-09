"""Notificaciones relacionadas a redistribución."""

from src.utils.email_notifier import send_mabel_redistribucion_confirmacion_notification


async def notificar_redistribucion_confirmada(pedido_id: str, numero_pedido: str) -> None:
    """Envía notificación en tiempo real a EL RAYO."""
    from src.utils.notification_manager import notification_manager, NotificationType

    await notification_manager.notify(
        target_permission="odcsap.view",
        title="Redistribución confirmada por MABEL TRADING",
        message=f"La redistribución del pedido {numero_pedido} ha sido confirmada.",
        notification_type=NotificationType.SUCCESS,
        metadata={
            "pedido_id": pedido_id,
            "numero_pedido": numero_pedido,
            "accion": "redistribucion_confirmada",
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
