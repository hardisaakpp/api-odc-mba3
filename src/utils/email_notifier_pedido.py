"""
Función adicional para enviar notificaciones de confirmación de pedidos.
"""

import logging
import os
from datetime import datetime

from src.utils.timezone import ahora_naive
from typing import Optional, Dict, Any
from src.config import (
    ENABLE_EMAIL_NOTIFICATIONS,
)
from src.utils.notificacion_destinatarios import get_destinatarios_por_tipo
from src.utils.smtp_sender import send_smtp_message

logger = logging.getLogger(__name__)

_MSG_NOTIF_DESHABILITADAS = "⏭️ Notificaciones por email deshabilitadas"
_MSG_SIN_EMAIL_MABEL = "⚠️ No hay email configurado para MABEL TRADING"
_MSG_SIN_DESTINATARIOS = "⚠️ No hay destinatarios configurados"
_DEFAULT_FRONTEND_URL = "http://localhost:3000"
_INFO_PEDIDO_TITLE = "Informaci&oacute;n del Pedido"
_LABEL_NUMERO_PEDIDO = "N&uacute;mero de Pedido"
_LABEL_PEDIDO_ID = "Pedido ID"
_LABEL_VER_PEDIDO = "Ver Pedido"


def send_pedido_confirmacion_notification(
    pedido_data: Dict[str, Any],
    numero_pedido: str,
    usuario_origen: str = "EL RAYO",
    email_destino: Optional[str] = None,
    url_confirmacion: Optional[str] = None,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía correo a MABEL TRADING notificando que se requiere confirmación de un pedido.

    DESTINATARIO: email_destino (si se proporciona) o EMAIL_MABEL_TRADING

    Args:
        pedido_data: Datos del pedido (cabecera y detalles)
        numero_pedido: Número del pedido
        usuario_origen: Usuario que solicita la confirmación (default: "EL RAYO")
        email_destino: Email del destinatario (opcional, usa EMAIL_MABEL_TRADING si no se proporciona)
        url_confirmacion: URL directa para confirmar el pedido
        fecha_ejecucion: Fecha y hora de la ejecución (por defecto ahora)

    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        logger.debug(_MSG_NOTIF_DESHABILITADAS)
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        # Determinar destinatario
        recipients: list[str]
        if email_destino:
            recipients = [email_destino.strip()]
        else:
            recipients = get_destinatarios_por_tipo("MABEL_TRADING")
            if not recipients:
                logger.warning(_MSG_SIN_EMAIL_MABEL)
                return False

        if not recipients:
            logger.warning(_MSG_SIN_DESTINATARIOS)
            return False

        # Extraer información del pedido
        cabecera = pedido_data.get("cabecera", {})
        detalles = pedido_data.get("detalles", [])

        fecha_pedido = cabecera.get("fecha_pedido", "N/A")
        proveedor_nombre = cabecera.get("proveedor_nombre", "N/A")
        estado = cabecera.get("estado", "PENDIENTE")
        comprador_nombre = cabecera.get("comprador_nombre", "N/A")

        # Calcular totales
        total_productos = len(detalles)
        total_cantidad = 0
        total_valor = 0

        for detalle in detalles:
            # Sumar cantidades de todas las tiendas
            tiendas = detalle.get("tiendas", [])
            cantidad_detalle = sum(t.get("cantidad", 0) for t in tiendas)
            total_cantidad += cantidad_detalle

            # Sumar totales
            total_detalle = detalle.get("total", 0) or 0
            total_valor += total_detalle

        # Construir URL de confirmación si no se proporciona
        if not url_confirmacion:
            # URL base - debería venir del frontend o config
            base_url = os.getenv("FRONTEND_URL", "https://tu-dominio.com")
            numero_pedido_encoded = numero_pedido.replace(" ", "%20")
            url_confirmacion = f"{base_url}/mba3-consultas/pedidos/{numero_pedido_encoded}?modo=confirmacion&usuario=mabel-trading"

        from src.utils.email_template import (
            build_email, info_section, button_section,
            paragraph, create_email_message,
        )

        body_html = build_email(
            title="Confirmaci&oacute;n de Pedido Requerida",
            subtitle=f"Pedido: {numero_pedido}",
            sections=[
                paragraph(f"El usuario <strong>{usuario_origen}</strong> ha solicitado la confirmaci&oacute;n del siguiente pedido:"),
                info_section(_INFO_PEDIDO_TITLE, [
                    (_LABEL_NUMERO_PEDIDO, numero_pedido),
                    ("Fecha", fecha_pedido),
                    ("Proveedor", proveedor_nombre),
                    ("Comprador", comprador_nombre),
                    ("Estado", estado),
                    ("Total Productos", total_productos),
                    ("Total Cantidad", total_cantidad),
                    ("Total Valor", f"${total_valor:,.2f}"),
                ], accent="purple"),
                button_section("Confirmar Pedido", url_confirmacion, accent="purple"),
            ],
            accent="purple",
            timestamp=fecha_ejecucion,
        )

        body_text = f"""Confirmacion de Pedido Requerida - {numero_pedido}
{'=' * 40}

El usuario {usuario_origen} solicita confirmacion:

- Numero de Pedido: {numero_pedido}
- Fecha: {fecha_pedido}
- Proveedor: {proveedor_nombre}
- Comprador: {comprador_nombre}
- Estado: {estado}
- Total Productos: {total_productos}
- Total Cantidad: {total_cantidad}
- Total Valor: ${total_valor:,.2f}

Confirmar en: {url_confirmacion}

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
"""

        msg = create_email_message(
            subject=f"Confirmacion de Pedido Requerida - {numero_pedido}",
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        # Enviar email
        send_smtp_message(msg, recipients)

        logger.info(f"✅ Email de confirmación de pedido enviado a {', '.join(recipients)} (Pedido: {numero_pedido})")
        return True

    except Exception as e:
        logger.error(f"❌ Error al enviar email de confirmación de pedido: {e}", exc_info=True)
        return False


def send_rayo_confirmacion_notification(
    pedido_id: str,
    numero_pedido: str,
    usuario_rayo: Optional[str] = None,
    detalles_modificados: int = 0,
    email_destino: Optional[str] = None,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía correo a MABEL TRADING notificando que El Rayo confirmó un pedido.

    DESTINATARIO: email_destino (si se proporciona) o EMAIL_MABEL_TRADING

    Args:
        pedido_id: UUID del pedido confirmado
        numero_pedido: Número del pedido
        usuario_rayo: ID del usuario de El Rayo que confirmó (opcional)
        detalles_modificados: Cantidad de detalles modificados en la confirmación
        email_destino: Email del destinatario (opcional, usa EMAIL_MABEL_TRADING si no se proporciona)
        fecha_ejecucion: Fecha y hora de la ejecución (por defecto ahora)

    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        logger.debug(_MSG_NOTIF_DESHABILITADAS)
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        # Determinar destinatario
        recipients: list[str]
        if email_destino:
            recipients = [email_destino.strip()]
        else:
            recipients = get_destinatarios_por_tipo("MABEL_TRADING")
            if not recipients:
                logger.warning(_MSG_SIN_EMAIL_MABEL)
                return False

        if not recipients:
            logger.warning(_MSG_SIN_DESTINATARIOS)
            return False

        # Construir URL del pedido
        base_url = os.getenv("FRONTEND_URL", _DEFAULT_FRONTEND_URL)
        numero_pedido_encoded = numero_pedido.replace(" ", "%20")
        url_pedido = f"{base_url}/mba3-consultas/pedidos/{numero_pedido_encoded}"

        from src.utils.email_template import (
            build_email, info_section, success_badge_section,
            button_section, paragraph, badge_html, create_email_message,
        )

        info_items = [
            (_LABEL_NUMERO_PEDIDO, numero_pedido),
            (_LABEL_PEDIDO_ID, pedido_id),
        ]
        if usuario_rayo:
            info_items.append(("Usuario El Rayo", usuario_rayo))
        info_items.extend([
            ("Detalles Modificados", str(detalles_modificados)),
            ("Estado", badge_html("CONFIRMADO", "#e8f5e9", "#2e7d32")),
        ])

        body_html = build_email(
            title="Pedido Confirmado por El Rayo",
            subtitle=f"Pedido: {numero_pedido}",
            sections=[
                success_badge_section("EL RAYO ha confirmado el pedido exitosamente"),
                paragraph("Se ha procesado la confirmaci&oacute;n del pedido y se ha creado la respuesta del proveedor correspondiente."),
                info_section(_INFO_PEDIDO_TITLE, info_items, accent="green"),
                button_section(_LABEL_VER_PEDIDO, url_pedido, accent="green"),
                paragraph("El pedido est&aacute; ahora listo para que MABEL TRADING proceda con la redistribuci&oacute;n y ajustes necesarios.", italic=True),
            ],
            accent="green",
            timestamp=fecha_ejecucion,
        )

        body_text = f"""Pedido Confirmado por El Rayo - {numero_pedido}
{'=' * 40}

Informacion del Pedido:
- Numero de Pedido: {numero_pedido}
- Pedido ID: {pedido_id}
{f'- Usuario El Rayo: {usuario_rayo}' if usuario_rayo else ''}
- Detalles Modificados: {detalles_modificados}
- Estado: CONFIRMADO

Ver Pedido: {url_pedido}

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
"""

        msg = create_email_message(
            subject=f"Pedido Confirmado por El Rayo - {numero_pedido}",
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        # Enviar email
        send_smtp_message(msg, recipients)

        logger.info(f"✅ Email de confirmación de El Rayo enviado a {', '.join(recipients)} (Pedido: {numero_pedido})")
        return True

    except Exception as e:
        logger.error(f"❌ Error al enviar email de confirmación de El Rayo: {e}", exc_info=True)
        return False


def send_despachar_y_facturar_notification(
    pedido_id: str,
    numero_pedido: str,
    usuario_rayo: Optional[str] = None,
    email_destino: Optional[str] = None,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía correo a MABEL TRADING notificando que EL RAYO marcó el pedido como "Despachar y Facturar".

    Se usa cuando un usuario con permiso odcsap.view (EL RAYO) hace clic en
    "Despachar y Facturar" en el detalle del pedido.

    DESTINATARIO: email_destino (si se proporciona) o EMAIL_MABEL_TRADING

    Args:
        pedido_id: UUID del pedido
        numero_pedido: Número del pedido
        usuario_rayo: Username o identificador del usuario EL RAYO que realizó la acción (opcional)
        email_destino: Email del destinatario (opcional, usa EMAIL_MABEL_TRADING si no se proporciona)
        fecha_ejecucion: Fecha y hora de la ejecución (por defecto ahora)

    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        logger.debug(_MSG_NOTIF_DESHABILITADAS)
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        recipients: list[str]
        if email_destino:
            recipients = [email_destino.strip()]
        else:
            recipients = get_destinatarios_por_tipo("MABEL_TRADING")
            if not recipients:
                logger.warning(_MSG_SIN_EMAIL_MABEL)
                return False

        if not recipients:
            logger.warning(_MSG_SIN_DESTINATARIOS)
            return False

        base_url = os.getenv("FRONTEND_URL", _DEFAULT_FRONTEND_URL)
        url_pedido = f"{base_url}/mba3-consultas/pedidos/{pedido_id}"

        from src.utils.email_template import (
            build_email, info_section, success_badge_section,
            button_section, paragraph, badge_html, create_email_message,
        )

        info_items = [
            (_LABEL_NUMERO_PEDIDO, numero_pedido),
            (_LABEL_PEDIDO_ID, pedido_id),
        ]
        if usuario_rayo:
            info_items.append(("Usuario EL RAYO", usuario_rayo))
        info_items.append(("Estado", badge_html("DESPACHAR Y FACTURAR", "#e3f2fd", "#1565c0")))

        body_html = build_email(
            title="Pedido marcado como Despachar y Facturar",
            subtitle=f"Pedido: {numero_pedido}",
            sections=[
                success_badge_section("EL RAYO ha marcado el pedido como Despachar y Facturar"),
                paragraph("El pedido est&aacute; listo para despacho y facturaci&oacute;n. MABEL TRADING puede proceder con los pasos finales del flujo."),
                info_section(_INFO_PEDIDO_TITLE, info_items, accent="blue"),
                button_section(_LABEL_VER_PEDIDO, url_pedido, accent="blue"),
            ],
            accent="blue",
            timestamp=fecha_ejecucion,
        )

        body_text = f"""Pedido marcado como Despachar y Facturar - {numero_pedido}
{'=' * 40}

EL RAYO ha marcado el pedido como Despachar y Facturar.

Informacion del Pedido:
- Numero de Pedido: {numero_pedido}
- Pedido ID: {pedido_id}
{f'- Usuario EL RAYO: {usuario_rayo}' if usuario_rayo else ''}
- Estado: DESPACHAR Y FACTURAR

Ver Pedido: {url_pedido}

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
"""

        msg = create_email_message(
            subject=f"Pedido Despachar y Facturar - {numero_pedido}",
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        send_smtp_message(msg, recipients)

        logger.info(f"✅ Email Despachar y Facturar enviado a {', '.join(recipients)} (Pedido: {numero_pedido})")
        return True

    except Exception as e:
        logger.error(f"❌ Error al enviar email Despachar y Facturar: {e}", exc_info=True)
        return False


def send_finalizar_pedido_notification(
    pedido_id: str,
    numero_pedido: str,
    usuario_mabel: Optional[str] = None,
    email_destino: Optional[str] = None,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía correo a EL RAYO (Operaciones) notificando que MABEL TRADING finalizó el pedido.

    Se usa cuando un usuario con permiso mabel.view (MABEL TRADING) hace clic en
    "Finalizar Pedido" en la pantalla cargar-plantilla (ej. /cargar-plantilla/PREG-02.04.2026).

    DESTINATARIO: email_destino (si se proporciona) o EMAIL_TO_OPERACIONES (EL RAYO).

    Args:
        pedido_id: UUID del pedido
        numero_pedido: Número del pedido
        usuario_mabel: Username o identificador del usuario MABEL TRADING que realizó la acción (opcional)
        email_destino: Email del destinatario (opcional, usa EMAIL_TO_OPERACIONES si no se proporciona)
        fecha_ejecucion: Fecha y hora de la ejecución (por defecto ahora)

    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        logger.debug(_MSG_NOTIF_DESHABILITADAS)
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        recipients: list[str]
        if email_destino:
            recipients = [email_destino.strip()]
        else:
            recipients = get_destinatarios_por_tipo("OPERACIONES")
            if not recipients:
                logger.warning("⚠️ No hay email configurado para EL RAYO (OPERACIONES)")
                return False

        if not recipients:
            logger.warning(_MSG_SIN_DESTINATARIOS)
            return False

        base_url = os.getenv("FRONTEND_URL", _DEFAULT_FRONTEND_URL)
        url_pedido = f"{base_url}/mba3-consultas/pedidos/{pedido_id}"

        from src.utils.email_template import (
            build_email, info_section, success_badge_section,
            button_section, paragraph, badge_html, create_email_message,
        )

        info_items = [
            (_LABEL_NUMERO_PEDIDO, numero_pedido),
            (_LABEL_PEDIDO_ID, pedido_id),
        ]
        if usuario_mabel:
            info_items.append(("Usuario MABEL TRADING", usuario_mabel))
        info_items.append(("Estado", badge_html("FINALIZADO", "#e8f5e9", "#2e7d32")))

        body_html = build_email(
            title="Pedido finalizado",
            subtitle=f"Pedido: {numero_pedido}",
            sections=[
                success_badge_section("MABEL TRADING ha finalizado el pedido"),
                paragraph("El pedido ha sido marcado como <strong>Finalizado</strong>. Es el estado final del flujo."),
                info_section(_INFO_PEDIDO_TITLE, info_items, accent="green"),
                button_section(_LABEL_VER_PEDIDO, url_pedido, accent="green"),
            ],
            accent="green",
            timestamp=fecha_ejecucion,
        )

        body_text = f"""Pedido finalizado - {numero_pedido}
{'=' * 40}

MABEL TRADING ha finalizado el pedido.

Informacion del Pedido:
- Numero de Pedido: {numero_pedido}
- Pedido ID: {pedido_id}
{f'- Usuario MABEL TRADING: {usuario_mabel}' if usuario_mabel else ''}
- Estado: FINALIZADO

Ver Pedido: {url_pedido}

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
"""

        msg = create_email_message(
            subject=f"Pedido finalizado - {numero_pedido}",
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        send_smtp_message(msg, recipients)

        logger.info(f"✅ Email Pedido finalizado enviado a EL RAYO {', '.join(recipients)} (Pedido: {numero_pedido})")
        return True

    except Exception as e:
        logger.error(f"❌ Error al enviar email Pedido finalizado a EL RAYO: {e}", exc_info=True)
        return False
