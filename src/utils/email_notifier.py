"""
Módulo para enviar notificaciones por correo electrónico usando Outlook.
"""

import logging
import smtplib
import csv
import io
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import List, Optional, Dict, Any
from src.config import (
    EMAIL_SMTP_SERVER,
    EMAIL_SMTP_PORT,
    EMAIL_SMTP_USER,
    EMAIL_SMTP_PASSWORD,
    EMAIL_FROM,
    EMAIL_FROM_NAME,
    EMAIL_TO,
    EMAIL_TO_OPERACIONES,
    EMAIL_TO_HOMOLOGACIONES,
    EMAIL_TO_TECNICOS,
    EMAIL_MABEL_TRADING,
    ENABLE_EMAIL_NOTIFICATIONS,
    EMAIL_WARNING_TIME_LIMIT_PERCENT,
    EMAIL_WARNING_HIGH_VOLUME_THRESHOLD,
    EMAIL_WARNING_FAILURES_THRESHOLD
)

logger = logging.getLogger(__name__)


def send_migration_notification(
    facturas_guardadas: int,
    facturas_actualizadas: int,
    total_detalles: int,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía notificación de nuevos despachos al USUARIO DE OPERACIONES.
    
    DESTINATARIO: EMAIL_TO_OPERACIONES
    
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
        # USAR EMAIL_TO_OPERACIONES en lugar de EMAIL_TO
        recipients = EMAIL_TO_OPERACIONES if isinstance(EMAIL_TO_OPERACIONES, list) else [EMAIL_TO_OPERACIONES] if EMAIL_TO_OPERACIONES else []
        
        if not recipients:
            logger.warning("⚠️ No hay destinatarios de OPERACIONES configurados")
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
    Envía notificación de errores al USUARIO TÉCNICO.
    
    DESTINATARIO: EMAIL_TO_TECNICOS
    
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
        # USAR EMAIL_TO_TECNICOS en lugar de EMAIL_TO
        recipients = EMAIL_TO_TECNICOS if isinstance(EMAIL_TO_TECNICOS, list) else [EMAIL_TO_TECNICOS] if EMAIL_TO_TECNICOS else []
        
        if not recipients:
            logger.warning("⚠️ No hay destinatarios TÉCNICOS configurados")
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
    fecha_ejecucion: Optional[datetime] = None,
    filtrar_ya_notificados: bool = True,
    homologacion_repository = None
) -> bool:
    """
    Envía notificación de productos no homologados al USUARIO DE HOMOLOGACIONES.
    
    DESTINATARIO: EMAIL_TO_HOMOLOGACIONES
    
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
        filtrar_ya_notificados: Si True, filtra productos ya notificados anteriormente
        homologacion_repository: Repository para acceder a registros de notificaciones
    
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
    
    # FILTRAR productos ya notificados si se solicita
    productos_a_notificar = productos_no_homologados
    skus_ya_notificados = set()
    
    if filtrar_ya_notificados and homologacion_repository:
        try:
            skus_ya_notificados = homologacion_repository.get_skus_ya_notificados()
            productos_a_notificar = [
                p for p in productos_no_homologados 
                if p.get("sku") not in skus_ya_notificados
            ]
            
            if not productos_a_notificar:
                logger.info("⏭️ Todos los productos no homologados ya fueron notificados")
                return False
            
            logger.info(f"📧 Productos a notificar: {len(productos_a_notificar)} (filtrados: {len(skus_ya_notificados)})")
            
        except Exception as e:
            logger.warning(f"⚠️ No se pudo filtrar productos ya notificados: {e}")
            # En caso de error, notificar todos
            productos_a_notificar = productos_no_homologados
    
    try:
        # USAR EMAIL_TO_HOMOLOGACIONES en lugar de EMAIL_TO
        recipients = EMAIL_TO_HOMOLOGACIONES if isinstance(EMAIL_TO_HOMOLOGACIONES, list) else [EMAIL_TO_HOMOLOGACIONES] if EMAIL_TO_HOMOLOGACIONES else []
        
        if not recipients:
            logger.warning("⚠️ No hay destinatarios de HOMOLOGACIONES configurados")
            return False
        
        # Crear mensaje
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = f"⚠️ Productos NO Homologados Detectados - {len(productos_a_notificar)} producto(s) NUEVOS"
        
        # Preparar estadísticas
        if estadisticas:
            total_mba3 = estadisticas.get("total_productos_mba3", 0)
            homologados = estadisticas.get("productos_homologados", 0)
            no_homologados = estadisticas.get("productos_no_homologados", 0)
            porcentaje = estadisticas.get("porcentaje_homologacion", 0.0)
        else:
            total_mba3 = 0
            homologados = 0
            no_homologados = len(productos_a_notificar)
            porcentaje = 0.0
        
        # Separar productos por tipo de problema
        productos_no_existen = [p for p in productos_a_notificar if p.get("tipo_problema") == "no_existe"]
        productos_mismatch = [p for p in productos_a_notificar if p.get("tipo_problema") == "mismatch"]
        productos_error = [p for p in productos_a_notificar if p.get("tipo_problema") == "error"]
        productos_sin_tipo = [p for p in productos_a_notificar if not p.get("tipo_problema")]
        
        # Crear tabla HTML de productos con distinción de tipo (máximo 20 para no saturar el email)
        productos_mostrar = productos_a_notificar[:20]
        productos_tabla = ""
        for idx, producto in enumerate(productos_mostrar, 1):
            sku = producto.get("sku", "N/A")
            nombre = producto.get("nombre_producto", "Sin nombre")
            veces_usado = producto.get("veces_usado", 0)
            total_docenas = producto.get("total_docenas", 0.0)
            total_valor = producto.get("total_valor", 0.0)
            ultima_aparicion = producto.get("ultima_aparicion", "N/A")
            tipo_problema = producto.get("tipo_problema", "no_existe")
            item_code_sap = producto.get("item_code_sap")
            
            # Determinar descripción del problema y color
            if tipo_problema == "mismatch":
                problema_desc = f"MISMATCH<br><small>ItemCode SAP: {item_code_sap}</small>"
                problema_color = "#ff9800"  # Naranja
            elif tipo_problema == "error":
                problema_desc = "Error al consultar"
                problema_color = "#f44336"  # Rojo
            else:
                problema_desc = "No existe en SAP"
                problema_color = "#2196F3"  # Azul
            
            productos_tabla += f"""
            <tr>
                <td>{idx}</td>
                <td><strong>{sku}</strong></td>
                <td>{nombre}</td>
                <td style="background-color: {problema_color}; color: white; font-weight: bold; padding: 5px; border-radius: 3px;">{problema_desc}</td>
                <td>{veces_usado}</td>
                <td>{total_docenas:.2f}</td>
                <td>${total_valor:.2f}</td>
                <td>{ultima_aparicion}</td>
            </tr>
            """
        
        if len(productos_a_notificar) > 20:
            productos_tabla += f"""
            <tr>
                <td colspan="8" style="text-align: center; font-style: italic;">
                    ... y {len(productos_a_notificar) - 20} producto(s) más
                </td>
            </tr>
            """
        
        # Crear resumen por tipo de problema
        resumen_tipos = ""
        if productos_mismatch:
            resumen_tipos += f"<li><strong style='color: #ff9800;'>Mismatch (SKU ≠ ItemCode):</strong> {len(productos_mismatch)} producto(s)</li>"
        if productos_no_existen:
            resumen_tipos += f"<li><strong style='color: #2196F3;'>No existe en SAP:</strong> {len(productos_no_existen)} producto(s)</li>"
        if productos_error:
            resumen_tipos += f"<li><strong style='color: #f44336;'>Error al consultar:</strong> {len(productos_error)} producto(s)</li>"
        if productos_sin_tipo:
            resumen_tipos += f"<li><strong>Sin clasificar:</strong> {len(productos_sin_tipo)} producto(s)</li>"
        
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
                .mismatch-warning {{ background-color: #ffe0b2; border: 1px solid #ff9800; padding: 15px; margin: 15px 0; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>⚠️ Productos NO Homologados Detectados</h2>
                </div>
                <div class="content">
                    <p>Se han detectado productos de MBA3 que <strong>NO están homologados en SAP</strong> o tienen problemas de coincidencia.</p>
                    
                    <div class="stats">
                        <h3>📊 Resumen por Tipo de Problema</h3>
                        <ul>
                            {resumen_tipos if resumen_tipos else "<li>Sin productos para mostrar</li>"}
                        </ul>
                    </div>
                    
                    <div class="warning">
                        <strong>⚠️ ACCIÓN REQUERIDA:</strong><br>
                        <ul>
                            <li><strong>Productos que no existen:</strong> Deben ser creados en SAP con el mismo ItemCode (SKU) para que el sistema pueda procesar las órdenes de compra correctamente.</li>
                            <li><strong>Productos con Mismatch:</strong> El SKU de MBA3 no coincide con el ItemCode de SAP. Se requiere corregir la homologación para que coincidan exactamente.</li>
                        </ul>
                    </div>
                    
                    {f'<div class="mismatch-warning"><strong>🔴 ATENCIÓN - Productos con Mismatch:</strong><br>Los productos marcados como "MISMATCH" tienen un SKU en MBA3 que no coincide con el ItemCode en SAP. Estos productos <strong>NO recibirán conversiones automáticas</strong> hasta que se corrija la homologación.</div>' if productos_mismatch else ''}
                    
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
                                    <th>Tipo de Problema</th>
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
            tipo_problema = producto.get("tipo_problema", "no_existe")
            item_code_sap = producto.get("item_code_sap")
            
            # Determinar descripción del problema
            if tipo_problema == "mismatch":
                problema_desc = f"MISMATCH - ItemCode SAP: {item_code_sap}"
            elif tipo_problema == "error":
                problema_desc = "Error al consultar"
            else:
                problema_desc = "No existe en SAP"
            
            body_text += f"""
        {idx}. SKU: {sku}
           Nombre: {nombre}
           Tipo de Problema: {problema_desc}
           Veces Usado: {veces_usado}
           Total Docenas: {total_docenas:.2f}
           Total Valor: ${total_valor:.2f}
           Última Aparición: {ultima_aparicion}
        """
        
        if len(productos_a_notificar) > 20:
            body_text += f"\n        ... y {len(productos_a_notificar) - 20} producto(s) más\n"
        
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
                'Tipo de Problema',
                'ItemCode SAP',
                'Veces Usado',
                'Total Docenas',
                'Total Valor',
                'Primera Aparición',
                'Última Aparición'
            ])
            
            # Escribir datos de todos los productos (no solo los primeros 20)
            for producto in productos_a_notificar:
                tipo_problema = producto.get("tipo_problema", "no_existe")
                item_code_sap = producto.get("item_code_sap", "")
                
                # Determinar descripción del problema
                if tipo_problema == "mismatch":
                    problema_desc = "MISMATCH"
                elif tipo_problema == "error":
                    problema_desc = "Error al consultar"
                else:
                    problema_desc = "No existe en SAP"
                
                csv_writer.writerow([
                    producto.get("sku", "N/A"),
                    producto.get("nombre_producto", "Sin nombre"),
                    problema_desc,
                    item_code_sap,
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
        logger.info(f"   Productos no homologados reportados: {len(productos_a_notificar)}")
        
        # REGISTRAR productos notificados
        if homologacion_repository:
            try:
                skus_notificados = [p.get("sku") for p in productos_a_notificar if p.get("sku")]
                registrados = homologacion_repository.registrar_productos_notificados(skus_notificados)
                logger.info(f"✅ Registrados {registrados} productos como notificados")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo registrar productos notificados: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al enviar email de homologación: {e}", exc_info=True)
        return False


def send_capacity_warning_notification(
    warning_type: str,
    details: dict,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía notificación de advertencia de capacidad al USUARIO TÉCNICO.
    
    DESTINATARIO: EMAIL_TO_TECNICOS
    
    Args:
        warning_type: Tipo de advertencia ('time_limit', 'high_volume', 'high_failures')
        details: Detalles de la advertencia
        fecha_ejecucion: Fecha de ejecución
    
    Returns:
        True si se envió correctamente, False en caso contrario
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        return False
    
    if not fecha_ejecucion:
        fecha_ejecucion = datetime.now()
    
    try:
        recipients = EMAIL_TO_TECNICOS if isinstance(EMAIL_TO_TECNICOS, list) else [EMAIL_TO_TECNICOS] if EMAIL_TO_TECNICOS else []
        
        if not recipients:
            logger.warning("⚠️ No hay destinatarios TÉCNICOS configurados")
            return False
        
        # Determinar título y mensaje según el tipo
        if warning_type == 'time_limit':
            titulo = "⚠️ Advertencia: Tiempo de Ejecución Alto"
            mensaje_principal = f"La migración está usando {details.get('porcentaje_usado', 0)}% del tiempo límite."
            color = "#ff9800"  # Naranja
        elif warning_type == 'high_volume':
            titulo = "📊 Advertencia: Volumen Alto de Registros"
            mensaje_principal = f"Se detectaron {details.get('num_facturas', 0)} facturas (umbral: {details.get('umbral', 0)})."
            color = "#2196F3"  # Azul
        elif warning_type == 'high_failures':
            titulo = "🔴 Advertencia: Múltiples Fallos Detectados"
            mensaje_principal = f"Se detectaron {details.get('num_fallos', 0)} fallos en las últimas 24 horas."
            color = "#f44336"  # Rojo
        else:
            titulo = "⚠️ Advertencia del Sistema"
            mensaje_principal = "Se detectó una condición de advertencia."
            color = "#ff9800"
        
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = titulo
        
        # Crear tabla de detalles
        detalles_html = ""
        for key, value in details.items():
            detalles_html += f"<li><strong>{key.replace('_', ' ').title()}:</strong> {value}</li>"
        
        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: {color}; color: white; padding: 15px; text-align: center; }}
                .content {{ background-color: #f9f9f9; padding: 20px; }}
                .warning {{ background-color: white; padding: 15px; margin: 10px 0; border-left: 4px solid {color}; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>{titulo}</h2>
                </div>
                <div class="content">
                    <p>{mensaje_principal}</p>
                    
                    <div class="warning">
                        <h3>📋 Detalles:</h3>
                        <ul>
                            {detalles_html}
                        </ul>
                    </div>
                    
                    <p><strong>Fecha y Hora:</strong> {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}</p>
                    
                    <p><strong>Acción Recomendada:</strong> Revisar los logs del sistema y considerar ajustar la configuración si es necesario.</p>
                </div>
                <div class="footer">
                    <p>Sistema MBA3 Consultas - Notificación Técnica</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        body_text = f"""
        {titulo}
        
        {mensaje_principal}
        
        Detalles:
        """
        for key, value in details.items():
            body_text += f"- {key.replace('_', ' ').title()}: {value}\n"
        
        body_text += f"""
        
        Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
        
        Acción Recomendada: Revisar los logs del sistema y considerar ajustar la configuración si es necesario.
        """
        
        msg.attach(MIMEText(body_text, 'plain'))
        msg.attach(MIMEText(body_html, 'html'))
        
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            if EMAIL_SMTP_PORT == 587:
                server.starttls()
            if EMAIL_SMTP_PASSWORD:
                server.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
            server.send_message(msg, to_addrs=recipients)
        
        logger.info(f"✅ Email de advertencia de capacidad enviado a {', '.join(recipients)}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al enviar email de advertencia: {e}", exc_info=True)
        return False


def send_oc_to_supplier(
    oc_cabecera: Dict[str, Any],
    oc_detalles: List[Dict[str, Any]],
    doc_num: Optional[int] = None,
    doc_entry: Optional[int] = None,
    proveedor_email: Optional[str] = None,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía correo al proveedor con la ODC generada.
    
    DESTINATARIO: proveedor_email (si se proporciona) o EMAIL_TO_OPERACIONES como fallback
    
    Args:
        oc_cabecera: Datos de cabecera de la orden de compra
        oc_detalles: Lista de detalles de la orden de compra
        doc_num: Número de documento SAP (DocNum)
        doc_entry: Entry de documento SAP (DocEntry)
        proveedor_email: Email del proveedor (opcional)
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
        if proveedor_email:
            recipients = [proveedor_email.strip()]
        else:
            # Fallback: enviar a operaciones para que lo reenvíen manualmente
            recipients = EMAIL_TO_OPERACIONES if isinstance(EMAIL_TO_OPERACIONES, list) else [EMAIL_TO_OPERACIONES] if EMAIL_TO_OPERACIONES else []
            logger.warning(f"⚠️ No se proporcionó email del proveedor, enviando a operaciones: {recipients}")
        
        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados")
            return False
        
        # Extraer información de la ODC
        oc_id = oc_cabecera.get("oc_id", "N/A")
        proveedor = oc_cabecera.get("proveedor", "N/A")
        numero_oc_sap = doc_num or oc_cabecera.get("numero_oc_sap", "N/A")
        referencia = oc_cabecera.get("referencia_despacho", "N/A")
        
        # Crear mensaje
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = f"📦 Orden de Compra Generada - ODC #{numero_oc_sap}"
        
        # Calcular totales
        total_lineas = len(oc_detalles)
        total_cantidad = sum(d.get("cantidad_sap", 0) for d in oc_detalles)
        total_valor = sum(d.get("total_linea", 0) or 0 for d in oc_detalles)
        
        # Crear tabla HTML de detalles (máximo 50 líneas para no saturar)
        detalles_mostrar = oc_detalles[:50]
        detalles_tabla = ""
        for idx, detalle in enumerate(detalles_mostrar, 1):
            sku = detalle.get("sku_sap", "N/A")
            nombre = detalle.get("nombre_producto", "Sin nombre")
            cantidad = detalle.get("cantidad_sap", 0)
            unidad = detalle.get("unidad_sap", "N/A")
            precio_unit = detalle.get("precio_unitario", 0)
            total_linea = detalle.get("total_linea", 0)
            
            detalles_tabla += f"""
            <tr>
                <td>{idx}</td>
                <td><strong>{sku}</strong></td>
                <td>{nombre}</td>
                <td>{cantidad:.2f}</td>
                <td>{unidad}</td>
                <td>${precio_unit:.2f}</td>
                <td>${total_linea:.2f}</td>
            </tr>
            """
        
        if len(oc_detalles) > 50:
            detalles_tabla += f"""
            <tr>
                <td colspan="7" style="text-align: center; font-style: italic;">
                    ... y {len(oc_detalles) - 50} línea(s) más
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
                .header {{ background-color: #4CAF50; color: white; padding: 15px; text-align: center; }}
                .content {{ background-color: #f9f9f9; padding: 20px; }}
                .info-box {{ background-color: white; padding: 15px; margin: 10px 0; border-left: 4px solid #4CAF50; }}
                .table-container {{ overflow-x: auto; margin: 20px 0; }}
                table {{ width: 100%; border-collapse: collapse; background-color: white; }}
                th {{ background-color: #4CAF50; color: white; padding: 10px; text-align: left; }}
                td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
                tr:hover {{ background-color: #f5f5f5; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
                .total {{ font-weight: bold; background-color: #e8f5e9; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>📦 Orden de Compra Generada</h2>
                </div>
                <div class="content">
                    <p>Se ha generado una nueva Orden de Compra en SAP.</p>
                    
                    <div class="info-box">
                        <h3>📋 Información de la Orden de Compra</h3>
                        <ul>
                            <li><strong>Número ODC SAP:</strong> {numero_oc_sap}</li>
                            <li><strong>DocEntry:</strong> {doc_entry or 'N/A'}</li>
                            <li><strong>Proveedor:</strong> {proveedor}</li>
                            <li><strong>Referencia:</strong> {referencia}</li>
                            <li><strong>Total Líneas:</strong> {total_lineas}</li>
                            <li><strong>Total Cantidad:</strong> {total_cantidad:.2f}</li>
                            <li><strong>Total Valor:</strong> ${total_valor:.2f}</li>
                        </ul>
                    </div>
                    
                    <div class="table-container">
                        <h3>📋 Detalle de la Orden de Compra</h3>
                        <table>
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>SKU</th>
                                    <th>Producto</th>
                                    <th>Cantidad</th>
                                    <th>Unidad</th>
                                    <th>Precio Unit.</th>
                                    <th>Total</th>
                                </tr>
                            </thead>
                            <tbody>
                                {detalles_tabla}
                            </tbody>
                        </table>
                    </div>
                    
                    <p><strong>Fecha y Hora:</strong> {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}</p>
                    
                    <p>Este es un mensaje automático del sistema de integración SAP.</p>
                </div>
                <div class="footer">
                    <p>Sistema MBA3 Consultas - Notificación de Orden de Compra</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Crear cuerpo de texto plano
        body_text = f"""
        Orden de Compra Generada
        
        Se ha generado una nueva Orden de Compra en SAP.
        
        Información de la Orden de Compra:
        - Número ODC SAP: {numero_oc_sap}
        - DocEntry: {doc_entry or 'N/A'}
        - Proveedor: {proveedor}
        - Referencia: {referencia}
        - Total Líneas: {total_lineas}
        - Total Cantidad: {total_cantidad:.2f}
        - Total Valor: ${total_valor:.2f}
        
        Detalle de la Orden de Compra:
        """
        
        for idx, detalle in enumerate(detalles_mostrar, 1):
            sku = detalle.get("sku_sap", "N/A")
            nombre = detalle.get("nombre_producto", "Sin nombre")
            cantidad = detalle.get("cantidad_sap", 0)
            unidad = detalle.get("unidad_sap", "N/A")
            precio_unit = detalle.get("precio_unitario", 0)
            total_linea = detalle.get("total_linea", 0)
            
            body_text += f"""
        {idx}. SKU: {sku}
           Producto: {nombre}
           Cantidad: {cantidad:.2f} {unidad}
           Precio Unit.: ${precio_unit:.2f}
           Total: ${total_linea:.2f}
        """
        
        if len(oc_detalles) > 50:
            body_text += f"\n        ... y {len(oc_detalles) - 50} línea(s) más\n"
        
        body_text += f"""
        
        Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
        
        Este es un mensaje automático del sistema de integración SAP.
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
        
        logger.info(f"✅ Email de ODC enviado a {', '.join(recipients)} (ODC #{numero_oc_sap})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al enviar email de ODC al proveedor: {e}", exc_info=True)
        return False


def send_oc_ready_for_dispatch_notification(
    oc_cabecera: Dict[str, Any],
    doc_num: Optional[int] = None,
    doc_entry: Optional[int] = None,
    solicitudes_transferencia: Optional[Dict[str, Any]] = None,
    pedido_numero: Optional[str] = None,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía notificación a El Rayo indicando que la OC y Solicitudes de Transferencia
    han sido generadas en SAP y pueden proceder con despacho y facturación.
    
    HU-04: Alertar al personal de El Rayo para proceder con el despacho y facturación
    
    DESTINATARIO: EMAIL_TO_OPERACIONES (Operaciones/Despachos)
    
    Args:
        oc_cabecera: Datos de cabecera de la orden de compra
        doc_num: Número de documento SAP (DocNum) de la OC
        doc_entry: Entry de documento SAP (DocEntry) de la OC
        solicitudes_transferencia: Resultado de creación de solicitudes de transferencia (opcional)
        pedido_numero: Número de pedido relacionado (opcional)
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
        # Usar EMAIL_TO_OPERACIONES (Operaciones/Despachos) para notificar a El Rayo
        recipients = EMAIL_TO_OPERACIONES if isinstance(EMAIL_TO_OPERACIONES, list) else [EMAIL_TO_OPERACIONES] if EMAIL_TO_OPERACIONES else []
        
        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados para notificación de despacho")
            return False
        
        # Extraer información de la OC
        oc_id = oc_cabecera.get("oc_id", "N/A")
        proveedor = oc_cabecera.get("proveedor", "N/A")
        numero_oc_sap = doc_num or oc_cabecera.get("numero_oc_sap", "N/A")
        referencia = oc_cabecera.get("referencia_despacho", "N/A")
        
        # Información de Solicitudes de Transferencia
        transferencias_info = ""
        transferencias_tabla = ""
        total_transferencias = 0
        transferencias_exitosas = 0
        transferencias_fallidas = 0
        
        if solicitudes_transferencia:
            total_transferencias = solicitudes_transferencia.get("total_tiendas", 0)
            transferencias_exitosas = solicitudes_transferencia.get("transferencias_creadas", 0)
            transferencias_fallidas = solicitudes_transferencia.get("transferencias_errores", 0)
            resultados = solicitudes_transferencia.get("resultados", [])
            
            # Construir tabla de transferencias
            if resultados:
                for resultado in resultados:
                    tienda_codigo = resultado.get("tienda_codigo", "N/A")
                    success = resultado.get("success", False)
                    doc_num_transf = resultado.get("doc_num", "N/A")
                    error = resultado.get("error")
                    
                    estado = "✅ Creada" if success else "❌ Error"
                    doc_info = f"DocNum: {doc_num_transf}" if success else f"Error: {error or 'Desconocido'}"
                    
                    transferencias_tabla += f"""
                    <tr>
                        <td>{tienda_codigo}</td>
                        <td>{estado}</td>
                        <td>{doc_info}</td>
                    </tr>
                    """
        
        # Crear mensaje
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = f"✅ OC y Solicitudes de Transferencia Generadas - Listo para Despacho #{numero_oc_sap}"
        
        # Crear cuerpo del mensaje HTML
        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #2196F3; color: white; padding: 15px; text-align: center; }}
                .content {{ background-color: #f9f9f9; padding: 20px; }}
                .info-box {{ background-color: white; padding: 15px; margin: 10px 0; border-left: 4px solid #2196F3; }}
                .success-box {{ background-color: #e8f5e9; padding: 15px; margin: 10px 0; border-left: 4px solid #4CAF50; }}
                .table-container {{ overflow-x: auto; margin: 20px 0; }}
                table {{ width: 100%; border-collapse: collapse; background-color: white; }}
                th {{ background-color: #2196F3; color: white; padding: 10px; text-align: left; }}
                td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
                tr:hover {{ background-color: #f5f5f5; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
                .action-box {{ background-color: #fff3cd; padding: 15px; margin: 20px 0; border-left: 4px solid #ffc107; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>✅ OC y Solicitudes de Transferencia Generadas</h2>
                </div>
                <div class="content">
                    <p>Se ha generado exitosamente la Orden de Compra y las Solicitudes de Transferencia en SAP.</p>
                    <p><strong>Pueden proceder con el despacho y facturación.</strong></p>
                    
                    <div class="info-box">
                        <h3>📋 Información de la Orden de Compra</h3>
                        <ul>
                            <li><strong>Número OC SAP:</strong> {numero_oc_sap}</li>
                            <li><strong>DocEntry:</strong> {doc_entry or 'N/A'}</li>
                            <li><strong>Proveedor:</strong> {proveedor}</li>
                            <li><strong>Referencia:</strong> {referencia}</li>
                            {("<li><strong>Número de Pedido:</strong> " + str(pedido_numero) + "</li>") if pedido_numero else ""}
                        </ul>
                    </div>
                    
                    {('<div class="success-box"><h3>📦 Solicitudes de Transferencia Generadas</h3><p><strong>Total:</strong> ' + str(transferencias_exitosas) + '/' + str(total_transferencias) + ' creadas exitosamente</p>' + ('<p style="color: #f44336;"><strong>⚠️ Errores:</strong> ' + str(transferencias_fallidas) + ' solicitud(es) fallaron</p>' if transferencias_fallidas > 0 else '') + '</div>') if solicitudes_transferencia else ""}
                    
                    {('<div class="table-container"><h3>📋 Detalle de Solicitudes de Transferencia</h3><table><thead><tr><th>Tienda</th><th>Estado</th><th>Información</th></tr></thead><tbody>' + transferencias_tabla + '</tbody></table></div>') if transferencias_tabla else ""}
                    
                    <div class="action-box">
                        <h3>🎯 Acción Requerida</h3>
                        <p>La Orden de Compra y las Solicitudes de Transferencia han sido registradas exitosamente en SAP.</p>
                        <p><strong>El personal de El Rayo puede proceder con:</strong></p>
                        <ul>
                            <li>✅ Despacho de mercancía</li>
                            <li>✅ Facturación correspondiente</li>
                        </ul>
                    </div>
                    
                    <div class="footer">
                        <p>Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}</p>
                        <p>Este es un mensaje automático del sistema de integración SAP.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Versión texto plano
        body_text = f"""
Orden de Compra y Solicitudes de Transferencia Generadas

Se ha generado exitosamente la Orden de Compra y las Solicitudes de Transferencia en SAP.
Pueden proceder con el despacho y facturación.

Información de la Orden de Compra:
- Número OC SAP: {numero_oc_sap}
- DocEntry: {doc_entry or 'N/A'}
- Proveedor: {proveedor}
- Referencia: {referencia}
{f'- Número de Pedido: {pedido_numero}' if pedido_numero else ''}

{f'''
Solicitudes de Transferencia Generadas:
- Total: {transferencias_exitosas}/{total_transferencias} creadas exitosamente
{f'- Errores: {transferencias_fallidas} solicitud(es) fallaron' if transferencias_fallidas > 0 else ''}
''' if solicitudes_transferencia else ''}

Acción Requerida:
La Orden de Compra y las Solicitudes de Transferencia han sido registradas exitosamente en SAP.
El personal de El Rayo puede proceder con:
- Despacho de mercancía
- Facturación correspondiente

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}

Este es un mensaje automático del sistema de integración SAP.
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
        
        logger.info(f"✅ Notificación de OC lista para despacho enviada a {', '.join(recipients)} (OC #{numero_oc_sap})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al enviar notificación de OC lista para despacho: {e}", exc_info=True)
        return False

