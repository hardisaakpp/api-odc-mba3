"""
Función adicional para enviar notificaciones de confirmación de pedidos.
"""

import logging
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, Dict, Any
from src.config import (
    EMAIL_SMTP_SERVER,
    EMAIL_SMTP_PORT,
    EMAIL_SMTP_USER,
    EMAIL_SMTP_PASSWORD,
    EMAIL_FROM,
    EMAIL_FROM_NAME,
    EMAIL_MABEL_TRADING,
    ENABLE_EMAIL_NOTIFICATIONS
)

logger = logging.getLogger(__name__)


def send_pedido_confirmacion_notification(
    pedido_data: Dict[str, Any],
    numero_pedido: str,
    usuario_origen: str = "EL RAYO",
    usuario_destino: str = "MABEL TRADING",
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
        usuario_destino: Usuario que debe confirmar (default: "MABEL TRADING")
        email_destino: Email del destinatario (opcional, usa EMAIL_MABEL_TRADING si no se proporciona)
        url_confirmacion: URL directa para confirmar el pedido
        fecha_ejecucion: Fecha y hora de la ejecución (por defecto ahora)
    
    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        logger.debug("⏭️ Notificaciones por email deshabilitadas")
        return False
    
    if not fecha_ejecucion:
        fecha_ejecucion = datetime.now()
    
    try:
        # Determinar destinatario
        if email_destino:
            recipients = [email_destino.strip()]
        else:
            recipients = [EMAIL_MABEL_TRADING] if EMAIL_MABEL_TRADING else []
            if not recipients:
                logger.warning("⚠️ No hay email configurado para MABEL TRADING")
                return False
        
        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados")
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
        
        # Crear mensaje
        msg = MIMEMultipart()
        msg['From'] = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = f"✅ Confirmación de Pedido Requerida - {numero_pedido}"
        
        # Crear cuerpo del mensaje HTML
        body_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #7c3aed; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9f9f9; padding: 20px; border: 1px solid #ddd; }}
                .info-box {{ background-color: white; padding: 15px; margin: 20px 0; border-left: 4px solid #7c3aed; border-radius: 3px; }}
                .info-box h3 {{ margin-top: 0; color: #7c3aed; }}
                .info-box ul {{ list-style: none; padding: 0; }}
                .info-box li {{ padding: 8px 0; border-bottom: 1px solid #eee; }}
                .info-box li:last-child {{ border-bottom: none; }}
                .info-box strong {{ color: #555; }}
                .button-container {{ text-align: center; margin: 30px 0; }}
                .button {{ background-color: #7c3aed; color: white; padding: 12px 30px; 
                          text-decoration: none; border-radius: 5px; display: inline-block; 
                          font-weight: bold; font-size: 16px; }}
                .button:hover {{ background-color: #6d28d9; }}
                .url-text {{ background-color: #f5f5f5; padding: 10px; border-radius: 3px; 
                            font-size: 12px; color: #666; word-break: break-all; 
                            margin: 10px 0; }}
                .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 30px; 
                          padding-top: 20px; border-top: 1px solid #ddd; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>✅ Confirmación de Pedido Requerida</h2>
                </div>
                <div class="content">
                    <p>El usuario <strong>{usuario_origen}</strong> ha solicitado la confirmación del siguiente pedido:</p>
                    
                    <div class="info-box">
                        <h3>📋 Información del Pedido</h3>
                        <ul>
                            <li><strong>Número de Pedido:</strong> {numero_pedido}</li>
                            <li><strong>Fecha:</strong> {fecha_pedido}</li>
                            <li><strong>Proveedor:</strong> {proveedor_nombre}</li>
                            <li><strong>Comprador:</strong> {comprador_nombre}</li>
                            <li><strong>Estado:</strong> {estado}</li>
                            <li><strong>Total Productos:</strong> {total_productos}</li>
                            <li><strong>Total Cantidad:</strong> {total_cantidad}</li>
                            <li><strong>Total Valor:</strong> ${total_valor:,.2f}</li>
                        </ul>
                    </div>
                    
                    <div class="button-container">
                        <p>Por favor, accede a la siguiente URL para confirmar el pedido:</p>
                        <a href="{url_confirmacion}" class="button">🔗 Confirmar Pedido</a>
                    </div>
                    
                    <p>O copia y pega este enlace en tu navegador:</p>
                    <div class="url-text">{url_confirmacion}</div>
                    
                    <p><strong>Fecha y Hora de Solicitud:</strong> {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                <div class="footer">
                    <p>Este es un correo automático del sistema MBA3 Consultas.</p>
                    <p>Por favor, no responder a este correo.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Crear cuerpo de texto plano
        body_text = f"""
Confirmación de Pedido Requerida

El usuario {usuario_origen} ha solicitado la confirmación del siguiente pedido:

Información del Pedido:
- Número de Pedido: {numero_pedido}
- Fecha: {fecha_pedido}
- Proveedor: {proveedor_nombre}
- Comprador: {comprador_nombre}
- Estado: {estado}
- Total Productos: {total_productos}
- Total Cantidad: {total_cantidad}
- Total Valor: ${total_valor:,.2f}

Por favor, accede a la siguiente URL para confirmar el pedido:
{url_confirmacion}

Fecha y Hora de Solicitud: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}

Este es un correo automático del sistema MBA3 Consultas.
Por favor, no responder a este correo.
        """
        
        # Agregar cuerpo al mensaje
        msg.attach(MIMEText(body_text, 'plain'))
        msg.attach(MIMEText(body_html, 'html'))
        
        # Enviar email
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            # Solo usar TLS si el puerto es 587 (no para puerto 25 - relay interno)
            if EMAIL_SMTP_PORT == 587:
                server.starttls()
            
            # Solo autenticar si hay password configurada (no para relay interno)
            if EMAIL_SMTP_PASSWORD:
                server.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
            
            server.send_message(msg, to_addrs=recipients)
        
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
        logger.debug("⏭️ Notificaciones por email deshabilitadas")
        return False
    
    if not fecha_ejecucion:
        fecha_ejecucion = datetime.now()
    
    try:
        # Determinar destinatario
        if email_destino:
            recipients = [email_destino.strip()]
        else:
            recipients = [EMAIL_MABEL_TRADING] if EMAIL_MABEL_TRADING else []
            if not recipients:
                logger.warning("⚠️ No hay email configurado para MABEL TRADING")
                return False
        
        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados")
            return False
        
        # Construir URL del pedido
        base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        numero_pedido_encoded = numero_pedido.replace(" ", "%20")
        url_pedido = f"{base_url}/mba3-consultas/pedidos/{numero_pedido_encoded}"
        
        # Crear mensaje
        msg = MIMEMultipart()
        msg['From'] = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = f"✅ Pedido Confirmado por El Rayo - {numero_pedido}"
        
        # Crear cuerpo del mensaje HTML
        body_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9f9f9; padding: 20px; border: 1px solid #ddd; }}
                .info-box {{ background-color: white; padding: 15px; margin: 20px 0; border-left: 4px solid #4CAF50; border-radius: 3px; }}
                .info-box h3 {{ margin-top: 0; color: #4CAF50; }}
                .info-box ul {{ list-style: none; padding: 0; }}
                .info-box li {{ padding: 8px 0; border-bottom: 1px solid #eee; }}
                .info-box li:last-child {{ border-bottom: none; }}
                .info-box strong {{ color: #555; }}
                .button-container {{ text-align: center; margin: 30px 0; }}
                .button {{ background-color: #4CAF50; color: white; padding: 12px 30px; 
                          text-decoration: none; border-radius: 5px; display: inline-block; 
                          font-weight: bold; font-size: 16px; }}
                .button:hover {{ background-color: #45a049; }}
                .url-text {{ background-color: #f5f5f5; padding: 10px; border-radius: 3px; 
                            font-size: 12px; color: #666; word-break: break-all; 
                            margin: 10px 0; }}
                .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 30px; 
                          padding-top: 20px; border-top: 1px solid #ddd; }}
                .success-badge {{ background-color: #e8f5e9; color: #2e7d32; padding: 10px; 
                                border-radius: 5px; margin: 15px 0; text-align: center; 
                                font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>✅ Pedido Confirmado por El Rayo</h2>
                </div>
                <div class="content">
                    <div class="success-badge">
                        ✓ El usuario <strong>EL RAYO</strong> ha confirmado el pedido exitosamente
                    </div>
                    
                    <p>Se ha procesado la confirmación del pedido y se ha creado la respuesta del proveedor correspondiente.</p>
                    
                    <div class="info-box">
                        <h3>📋 Información del Pedido</h3>
                        <ul>
                            <li><strong>Número de Pedido:</strong> {numero_pedido}</li>
                            <li><strong>Pedido ID:</strong> {pedido_id}</li>
                            {f'<li><strong>Usuario El Rayo:</strong> {usuario_rayo}</li>' if usuario_rayo else ''}
                            <li><strong>Detalles Modificados:</strong> {detalles_modificados}</li>
                            <li><strong>Estado:</strong> REDISTRIBUCION</li>
                        </ul>
                    </div>
                    
                    <div class="button-container">
                        <p>Puedes revisar el pedido en el siguiente enlace:</p>
                        <a href="{url_pedido}" class="button">🔗 Ver Pedido</a>
                    </div>
                    
                    <p>O copia y pega este enlace en tu navegador:</p>
                    <div class="url-text">{url_pedido}</div>
                    
                    <p><strong>Fecha y Hora de Confirmación:</strong> {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}</p>
                    
                    <p><em>El pedido está ahora listo para que MABEL TRADING proceda con la redistribución y ajustes necesarios.</em></p>
                </div>
                <div class="footer">
                    <p>Este es un correo automático del sistema MBA3 Consultas.</p>
                    <p>Por favor, no responder a este correo.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Crear cuerpo de texto plano
        body_text = f"""
Pedido Confirmado por El Rayo

El usuario EL RAYO ha confirmado el pedido exitosamente.

Se ha procesado la confirmación del pedido y se ha creado la respuesta del proveedor correspondiente.

Información del Pedido:
- Número de Pedido: {numero_pedido}
- Pedido ID: {pedido_id}
{f'- Usuario El Rayo: {usuario_rayo}' if usuario_rayo else ''}
- Detalles Modificados: {detalles_modificados}
- Estado: REDISTRIBUCION

Puedes revisar el pedido en el siguiente enlace:
{url_pedido}

Fecha y Hora de Confirmación: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}

El pedido está ahora listo para que MABEL TRADING proceda con la redistribución y ajustes necesarios.

Este es un correo automático del sistema MBA3 Consultas.
Por favor, no responder a este correo.
        """
        
        # Agregar cuerpo al mensaje
        msg.attach(MIMEText(body_text, 'plain'))
        msg.attach(MIMEText(body_html, 'html'))
        
        # Enviar email
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            # Solo usar TLS si el puerto es 587 (no para puerto 25 - relay interno)
            if EMAIL_SMTP_PORT == 587:
                server.starttls()
            
            # Solo autenticar si hay password configurada (no para relay interno)
            if EMAIL_SMTP_PASSWORD:
                server.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
            
            server.send_message(msg, to_addrs=recipients)
        
        logger.info(f"✅ Email de confirmación de El Rayo enviado a {', '.join(recipients)} (Pedido: {numero_pedido})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al enviar email de confirmación de El Rayo: {e}", exc_info=True)
        return False
