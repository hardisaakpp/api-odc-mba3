"""
Módulo para enviar notificaciones por correo electrónico usando Outlook.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Optional
from config import (
    EMAIL_SMTP_SERVER,
    EMAIL_SMTP_PORT,
    EMAIL_SMTP_USER,
    EMAIL_SMTP_PASSWORD,
    EMAIL_FROM,
    EMAIL_FROM_NAME,
    EMAIL_TO,
    ENABLE_EMAIL_NOTIFICATIONS
)

logger = logging.getLogger(__name__)


def send_migration_notification(
    facturas_guardadas: int,
    facturas_actualizadas: int,
    total_detalles: int,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía una notificación por correo electrónico cuando hay nuevos registros migrados.
    
    Args:
        facturas_guardadas: Número de facturas nuevas guardadas
        facturas_actualizadas: Número de facturas actualizadas
        total_detalles: Total de detalles guardados
        fecha_ejecucion: Fecha y hora de la ejecución (por defecto ahora)
    
    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        logger.debug("⏭️ Notificaciones por email deshabilitadas")
        return False
    
    # Solo enviar email si hay nuevos registros
    if facturas_guardadas == 0:
        logger.debug("⏭️ No hay nuevos registros, no se envía email")
        return False
    
    if not fecha_ejecucion:
        fecha_ejecucion = datetime.now()
    
    try:
        # Convertir EMAIL_TO a lista si es string
        recipients = EMAIL_TO if isinstance(EMAIL_TO, list) else [EMAIL_TO] if EMAIL_TO else []
        
        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados para notificaciones por email")
            return False
        
        # Crear mensaje
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = ", ".join(recipients)  # Múltiples destinatarios separados por coma
        msg['Subject'] = f"📦 Nuevos Registros Migrados - {facturas_guardadas} factura(s) nueva(s)"
        
        # Crear cuerpo del mensaje
        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #4CAF50; color: white; padding: 15px; text-align: center; }}
                .content {{ background-color: #f9f9f9; padding: 20px; }}
                .stats {{ background-color: white; padding: 15px; margin: 10px 0; border-left: 4px solid #4CAF50; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🚀 Migración Automática Completada</h2>
                </div>
                <div class="content">
                    <p>Se han migrado nuevos registros desde MBA3 a la base de datos.</p>
                    
                    <div class="stats">
                        <h3>📊 Resumen de la Migración</h3>
                        <ul>
                            <li><strong>Facturas Nuevas:</strong> {facturas_guardadas}</li>
                            <li><strong>Facturas Actualizadas:</strong> {facturas_actualizadas}</li>
                            <li><strong>Total Detalles:</strong> {total_detalles}</li>
                        </ul>
                    </div>
                    
                    <p><strong>Fecha y Hora:</strong> {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}</p>
                    
                    <p>Este es un mensaje automático del sistema de migración MBA3.</p>
                </div>
                <div class="footer">
                    <p>Sistema MBA3 Consultas - Migración Automática</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        body_text = f"""
        Migración Automática Completada
        
        Se han migrado nuevos registros desde MBA3 a la base de datos.
        
        Resumen de la Migración:
        - Facturas Nuevas: {facturas_guardadas}
        - Facturas Actualizadas: {facturas_actualizadas}
        - Total Detalles: {total_detalles}
        
        Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
        
        Este es un mensaje automático del sistema de migración MBA3.
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
        
        logger.info(f"✅ Email de notificación enviado a {', '.join(recipients)}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al enviar email de notificación: {e}", exc_info=True)
        return False


def send_error_notification(
    error_message: str,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía una notificación por correo electrónico cuando hay un error en la migración.
    
    Args:
        error_message: Mensaje de error
        fecha_ejecucion: Fecha y hora de la ejecución (por defecto ahora)
    
    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        return False
    
    if not fecha_ejecucion:
        fecha_ejecucion = datetime.now()
    
    try:
        # Convertir EMAIL_TO a lista si es string
        recipients = EMAIL_TO if isinstance(EMAIL_TO, list) else [EMAIL_TO] if EMAIL_TO else []
        
        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados para notificaciones por email")
            return False
        
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = ", ".join(recipients)  # Múltiples destinatarios separados por coma
        msg['Subject'] = "❌ Error en Migración Automática MBA3"
        
        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #f44336; color: white; padding: 15px; text-align: center; }}
                .content {{ background-color: #f9f9f9; padding: 20px; }}
                .error {{ background-color: white; padding: 15px; margin: 10px 0; border-left: 4px solid #f44336; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>❌ Error en Migración Automática</h2>
                </div>
                <div class="content">
                    <p>Se ha producido un error durante la migración automática desde MBA3.</p>
                    
                    <div class="error">
                        <h3>Detalles del Error:</h3>
                        <pre>{error_message}</pre>
                    </div>
                    
                    <p><strong>Fecha y Hora:</strong> {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}</p>
                    
                    <p>Por favor, revisa los logs del sistema para más información.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        body_text = f"""
        Error en Migración Automática
        
        Se ha producido un error durante la migración automática desde MBA3.
        
        Detalles del Error:
        {error_message}
        
        Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
        
        Por favor, revisa los logs del sistema para más información.
        """
        
        msg.attach(MIMEText(body_text, 'plain'))
        msg.attach(MIMEText(body_html, 'html'))
        
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            # Solo usar TLS si el puerto es 587 (no para puerto 25 - relay interno)
            if EMAIL_SMTP_PORT == 587:
                server.starttls()
            
            # Solo autenticar si hay password configurada (no para relay interno)
            if EMAIL_SMTP_PASSWORD:
                server.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
            
            server.send_message(msg, to_addrs=recipients)
        
        logger.info(f"✅ Email de error enviado a {', '.join(recipients)}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al enviar email de error: {e}", exc_info=True)
        return False

