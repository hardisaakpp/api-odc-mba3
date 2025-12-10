"""
Módulo para enviar notificaciones por correo electrónico usando Outlook.
"""

import logging
import smtplib
import csv
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
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


def send_homologacion_notification(
    productos_no_homologados: List[dict],
    estadisticas: Optional[dict] = None,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía una notificación por correo electrónico cuando se detectan productos no homologados.
    
    Args:
        productos_no_homologados: Lista de productos no homologados:
            [
                {
                    "sku": "5-0012.9",
                    "nombre_producto": "Nombre del producto",
                    "veces_usado": 15,
                    "total_docenas": 456.0,
                    "total_valor": 2120.4,
                    "primera_aparicion": "2024-01-15",
                    "ultima_aparicion": "2024-03-20"
                },
                ...
            ]
        estadisticas: Diccionario con estadísticas (opcional):
            {
                "total_productos_mba3": 150,
                "productos_homologados": 145,
                "productos_no_homologados": 5,
                "porcentaje_homologacion": 96.67
            }
        fecha_ejecucion: Fecha y hora de la ejecución (por defecto ahora)
    
    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        logger.debug("⏭️ Notificaciones por email deshabilitadas")
        return False
    
    # Solo enviar email si hay productos no homologados
    if not productos_no_homologados or len(productos_no_homologados) == 0:
        logger.debug("⏭️ No hay productos no homologados, no se envía email")
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
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = f"⚠️ Productos NO Homologados Detectados - {len(productos_no_homologados)} producto(s)"
        
        # Preparar estadísticas
        if estadisticas:
            total_mba3 = estadisticas.get("total_productos_mba3", 0)
            homologados = estadisticas.get("productos_homologados", 0)
            no_homologados = estadisticas.get("productos_no_homologados", 0)
            porcentaje = estadisticas.get("porcentaje_homologacion", 0.0)
        else:
            total_mba3 = 0
            homologados = 0
            no_homologados = len(productos_no_homologados)
            porcentaje = 0.0
        
        # Crear tabla HTML de productos (máximo 20 para no saturar el email)
        productos_mostrar = productos_no_homologados[:20]
        productos_tabla = ""
        for idx, producto in enumerate(productos_mostrar, 1):
            sku = producto.get("sku", "N/A")
            nombre = producto.get("nombre_producto", "Sin nombre")
            veces_usado = producto.get("veces_usado", 0)
            total_docenas = producto.get("total_docenas", 0.0)
            total_valor = producto.get("total_valor", 0.0)
            ultima_aparicion = producto.get("ultima_aparicion", "N/A")
            
            productos_tabla += f"""
            <tr>
                <td>{idx}</td>
                <td><strong>{sku}</strong></td>
                <td>{nombre}</td>
                <td>{veces_usado}</td>
                <td>{total_docenas:.2f}</td>
                <td>${total_valor:.2f}</td>
                <td>{ultima_aparicion}</td>
            </tr>
            """
        
        if len(productos_no_homologados) > 20:
            productos_tabla += f"""
            <tr>
                <td colspan="7" style="text-align: center; font-style: italic;">
                    ... y {len(productos_no_homologados) - 20} producto(s) más
                </td>
            </tr>
            """
        
        # Crear cuerpo del mensaje HTML
        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #ff9800; color: white; padding: 15px; text-align: center; }}
                .content {{ background-color: #f9f9f9; padding: 20px; }}
                .stats {{ background-color: white; padding: 15px; margin: 10px 0; border-left: 4px solid #ff9800; }}
                .table-container {{ overflow-x: auto; margin: 20px 0; }}
                table {{ width: 100%; border-collapse: collapse; background-color: white; }}
                th {{ background-color: #ff9800; color: white; padding: 10px; text-align: left; }}
                td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
                tr:hover {{ background-color: #f5f5f5; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
                .warning {{ background-color: #fff3cd; border: 1px solid #ffc107; padding: 15px; margin: 15px 0; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>⚠️ Productos NO Homologados Detectados</h2>
                </div>
                <div class="content">
                    <p>Se han detectado productos de MBA3 que <strong>NO están homologados en SAP</strong>.</p>
                    
                    <div class="warning">
                        <strong>⚠️ ACCIÓN REQUERIDA:</strong><br>
                        Estos productos deben ser creados en SAP con el mismo ItemCode (SKU) para que 
                        el sistema pueda procesar las órdenes de compra correctamente.
                    </div>
                    
                    <div class="stats">
                        <h3>📊 Estadísticas de Homologación</h3>
                        <ul>
                            <li><strong>Total Productos en MBA3:</strong> {total_mba3}</li>
                            <li><strong>Productos Homologados:</strong> {homologados}</li>
                            <li><strong>Productos NO Homologados:</strong> {no_homologados}</li>
                            <li><strong>Porcentaje de Homologación:</strong> {porcentaje}%</li>
                        </ul>
                    </div>
                    
                    <div class="table-container">
                        <h3>📋 Productos que Requieren Homologación</h3>
                        <table>
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>SKU</th>
                                    <th>Nombre Producto</th>
                                    <th>Veces Usado</th>
                                    <th>Total Docenas</th>
                                    <th>Total Valor</th>
                                    <th>Última Aparición</th>
                                </tr>
                            </thead>
                            <tbody>
                                {productos_tabla}
                            </tbody>
                        </table>
                    </div>
                    
                    <p><strong>Fecha y Hora:</strong> {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}</p>
                    
                    <p><strong>Nota:</strong> Este es un mensaje automático del sistema de migración MBA3. 
                    Los productos se detectan automáticamente durante el proceso de migración cuando 
                    no se encuentran en SAP.</p>
                </div>
                <div class="footer">
                    <p>Sistema MBA3 Consultas - Notificación de Homologación</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Crear cuerpo de texto plano
        body_text = f"""
        Productos NO Homologados Detectados
        
        Se han detectado productos de MBA3 que NO están homologados en SAP.
        
        ⚠️ ACCIÓN REQUERIDA:
        Estos productos deben ser creados en SAP con el mismo ItemCode (SKU).
        
        Estadísticas de Homologación:
        - Total Productos en MBA3: {total_mba3}
        - Productos Homologados: {homologados}
        - Productos NO Homologados: {no_homologados}
        - Porcentaje de Homologación: {porcentaje}%
        
        Productos que Requieren Homologación:
        """
        
        for idx, producto in enumerate(productos_mostrar, 1):
            sku = producto.get("sku", "N/A")
            nombre = producto.get("nombre_producto", "Sin nombre")
            veces_usado = producto.get("veces_usado", 0)
            total_docenas = producto.get("total_docenas", 0.0)
            total_valor = producto.get("total_valor", 0.0)
            ultima_aparicion = producto.get("ultima_aparicion", "N/A")
            
            body_text += f"""
        {idx}. SKU: {sku}
           Nombre: {nombre}
           Veces Usado: {veces_usado}
           Total Docenas: {total_docenas:.2f}
           Total Valor: ${total_valor:.2f}
           Última Aparición: {ultima_aparicion}
        """
        
        if len(productos_no_homologados) > 20:
            body_text += f"\n        ... y {len(productos_no_homologados) - 20} producto(s) más\n"
        
        body_text += f"""
        
        Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
        
        Nota: Este es un mensaje automático del sistema de migración MBA3.
        Se adjunta un archivo CSV con el detalle completo de todos los productos no homologados.
        """
        
        # Agregar cuerpo al mensaje
        msg.attach(MIMEText(body_text, 'plain'))
        msg.attach(MIMEText(body_html, 'html'))
        
        # Generar archivo CSV con todos los productos
        try:
            csv_buffer = io.StringIO()
            csv_writer = csv.writer(csv_buffer)
            
            # Escribir encabezados
            csv_writer.writerow([
                'SKU',
                'Nombre Producto',
                'Veces Usado',
                'Total Docenas',
                'Total Valor',
                'Primera Aparición',
                'Última Aparición'
            ])
            
            # Escribir datos de todos los productos (no solo los primeros 20)
            for producto in productos_no_homologados:
                csv_writer.writerow([
                    producto.get("sku", "N/A"),
                    producto.get("nombre_producto", "Sin nombre"),
                    producto.get("veces_usado", 0),
                    f"{producto.get('total_docenas', 0.0):.2f}",
                    f"{producto.get('total_valor', 0.0):.2f}",
                    producto.get("primera_aparicion", "N/A"),
                    producto.get("ultima_aparicion", "N/A")
                ])
            
            # Convertir a bytes para adjuntar
            csv_bytes = csv_buffer.getvalue().encode('utf-8-sig')  # utf-8-sig para Excel
            
            # Crear adjunto CSV
            csv_attachment = MIMEBase('text', 'csv')
            csv_attachment.set_payload(csv_bytes)
            encoders.encode_base64(csv_attachment)
            
            # Nombre del archivo con fecha
            fecha_str = fecha_ejecucion.strftime('%Y%m%d_%H%M%S')
            filename = f"productos_no_homologados_{fecha_str}.csv"
            csv_attachment.add_header(
                'Content-Disposition',
                f'attachment; filename= {filename}'
            )
            
            # Adjuntar CSV al mensaje
            msg.attach(csv_attachment)
            logger.debug(f"✅ Archivo CSV generado y adjuntado: {filename}")
            
        except Exception as csv_error:
            # No fallar el envío si hay error al generar CSV
            logger.warning(f"⚠️ Error al generar CSV adjunto: {csv_error}")
        
        # Enviar email
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            # Solo usar TLS si el puerto es 587 (no para puerto 25 - relay interno)
            if EMAIL_SMTP_PORT == 587:
                server.starttls()
            
            # Solo autenticar si hay password configurada (no para relay interno)
            if EMAIL_SMTP_PASSWORD:
                server.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
            
            server.send_message(msg, to_addrs=recipients)
        
        logger.info(f"✅ Email de homologación enviado a {', '.join(recipients)}")
        logger.info(f"   Productos no homologados reportados: {len(productos_no_homologados)}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al enviar email de homologación: {e}", exc_info=True)
        return False

