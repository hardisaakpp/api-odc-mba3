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
        
        from src.utils.email_template import build_email, info_section, paragraph, create_email_message
        
        body_html = build_email(
            title="Migraci&oacute;n Autom&aacute;tica Completada",
            subtitle="Nuevos registros migrados desde MBA3",
            sections=[
                paragraph("Se han migrado nuevos registros desde MBA3 a la base de datos."),
                info_section("Resumen de la Migraci&oacute;n", [
                    ("Facturas Nuevas", facturas_guardadas),
                    ("Facturas Actualizadas", facturas_actualizadas),
                    ("Total Detalles", total_detalles),
                ], accent="green", highlight_first=True),
            ],
            accent="green",
            timestamp=fecha_ejecucion,
        )
        
        body_text = f"""Migracion Automatica Completada
{'=' * 40}

Se han migrado nuevos registros desde MBA3 a la base de datos.

Resumen de la Migracion:
- Facturas Nuevas: {facturas_guardadas}
- Facturas Actualizadas: {facturas_actualizadas}
- Total Detalles: {total_detalles}

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
Mensaje automatico del sistema - Mabel Trading
"""
        
        msg = create_email_message(
            subject=f"Nuevos Registros Migrados - {facturas_guardadas} factura(s) nueva(s)",
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )
        
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
        
        from src.utils.email_template import build_email, info_section, warning_section, paragraph, create_email_message
        
        body_html = build_email(
            title="Error en Migraci&oacute;n Autom&aacute;tica",
            subtitle="Se requiere atenci&oacute;n t&eacute;cnica",
            sections=[
                paragraph("Se ha producido un error durante la migraci&oacute;n autom&aacute;tica desde MBA3."),
                info_section("Detalles del Error", [
                    ("Error", f'<span style="font-family:Consolas,monospace;font-size:13px;color:#c62828;">{error_message}</span>'),
                ], accent="red"),
                warning_section("Acci&oacute;n Recomendada",
                    '<p style="margin:0;color:#5d4037;font-size:14px;">Por favor, revisa los logs del sistema para m&aacute;s informaci&oacute;n.</p>'),
            ],
            accent="red",
            timestamp=fecha_ejecucion,
        )
        
        body_text = f"""Error en Migracion Automatica
{'=' * 40}

Se ha producido un error durante la migracion automatica desde MBA3.

Detalles del Error:
{error_message}

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
Por favor, revisa los logs del sistema para mas informacion.
"""
        
        msg = create_email_message(
            subject="Error en Migracion Automatica MBA3",
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )
        
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
        
        from src.utils.email_template import (
            build_email, info_section, table_section, warning_section,
            paragraph, badge_html, create_email_message,
        )
        
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
        
        # Construir filas de tabla para el template
        table_rows = []
        for idx, producto in enumerate(productos_mostrar, 1):
            sku = producto.get("sku", "N/A")
            nombre = producto.get("nombre_producto", "Sin nombre")
            veces_usado = producto.get("veces_usado", 0)
            total_docenas_val = producto.get("total_docenas", 0.0)
            total_valor_val = producto.get("total_valor", 0.0)
            ultima_aparicion = producto.get("ultima_aparicion", "N/A")
            tipo_problema = producto.get("tipo_problema", "no_existe")
            item_code_sap = producto.get("item_code_sap")
            
            if tipo_problema == "mismatch":
                tipo_badge = badge_html("MISMATCH", "#fff3e0", "#e65100")
            elif tipo_problema == "error":
                tipo_badge = badge_html("Error", "#ffebee", "#c62828")
            else:
                tipo_badge = badge_html("No existe", "#e3f2fd", "#1565c0")
            
            table_rows.append((
                str(idx),
                f'<strong>{sku}</strong>',
                nombre,
                (tipo_badge, "center"),
                str(veces_usado),
                f"{total_docenas_val:.2f}",
                f"${total_valor_val:.2f}",
                str(ultima_aparicion),
            ))
        
        footer_note = f"... y {len(productos_a_notificar) - 20} producto(s) m&aacute;s" if len(productos_a_notificar) > 20 else None
        
        # Construir resumen HTML por tipo
        resumen_items = []
        if productos_mismatch:
            resumen_items.append(("Mismatch (SKU ≠ ItemCode)", f'{badge_html(str(len(productos_mismatch)), "#fff3e0", "#e65100")} producto(s)'))
        if productos_no_existen:
            resumen_items.append(("No existe en SAP", f'{badge_html(str(len(productos_no_existen)), "#e3f2fd", "#1565c0")} producto(s)'))
        if productos_error:
            resumen_items.append(("Error al consultar", f'{badge_html(str(len(productos_error)), "#ffebee", "#c62828")} producto(s)'))
        if productos_sin_tipo:
            resumen_items.append(("Sin clasificar", f'{badge_html(str(len(productos_sin_tipo)), "#f5f5f5", "#616161")} producto(s)'))
        
        # Secciones del email
        sections = [
            paragraph(f"Se han detectado <strong>{len(productos_a_notificar)}</strong> producto(s) de MBA3 que NO est&aacute;n homologados en SAP o tienen problemas de coincidencia."),
            info_section("Resumen por Tipo de Problema", resumen_items, accent="orange"),
            warning_section("Acci&oacute;n Requerida",
                '<ul style="margin:8px 0;padding-left:20px;color:#5d4037;font-size:14px;line-height:1.6;">'
                '<li><strong>No existen:</strong> Crear en SAP con el mismo ItemCode (SKU).</li>'
                '<li><strong>Mismatch:</strong> Corregir la homologaci&oacute;n para que SKU y ItemCode coincidan.</li></ul>'),
            info_section("Estad&iacute;sticas de Homologaci&oacute;n", [
                ("Total Productos MBA3", total_mba3),
                ("Homologados", homologados),
                ("NO Homologados", no_homologados),
                ("Porcentaje", f"{porcentaje}%"),
            ], accent="orange"),
            table_section("Productos que Requieren Homologaci&oacute;n",
                ["#", "SKU", "Producto", "Problema", "Usos", "Docenas", "Valor", "&Uacute;lt. Aparici&oacute;n"],
                table_rows, accent="orange", footer_note=footer_note),
        ]
        
        body_html = build_email(
            title="Productos NO Homologados Detectados",
            subtitle=f"{len(productos_a_notificar)} producto(s) nuevos requieren atenci&oacute;n",
            sections=sections,
            accent="orange",
            timestamp=fecha_ejecucion,
        )
        
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
            
            csv_attachments = [csv_attachment]
            logger.debug(f"✅ Archivo CSV generado y adjuntado: {filename}")
            
        except Exception as csv_error:
            # No fallar el envío si hay error al generar CSV
            csv_attachments = []
            logger.warning(f"⚠️ Error al generar CSV adjunto: {csv_error}")
        
        msg = create_email_message(
            subject=f"Productos NO Homologados Detectados - {len(productos_a_notificar)} producto(s) NUEVOS",
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
            attachments=csv_attachments if csv_attachments else None,
        )
        
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
        
        from src.utils.email_template import build_email, info_section, warning_section, paragraph, create_email_message
        
        # Mapear tipo de warning a color de acento
        accent_map = {'time_limit': 'orange', 'high_volume': 'blue', 'high_failures': 'red'}
        accent = accent_map.get(warning_type, 'orange')
        
        detail_items = [(key.replace('_', ' ').title(), str(value)) for key, value in details.items()]
        
        body_html = build_email(
            title=titulo,
            subtitle=mensaje_principal,
            sections=[
                paragraph(mensaje_principal),
                info_section("Detalles", detail_items, accent=accent),
                warning_section("Acci&oacute;n Recomendada",
                    '<p style="margin:0;color:#5d4037;font-size:14px;">Revisar los logs del sistema y considerar ajustar la configuraci&oacute;n si es necesario.</p>'),
            ],
            accent=accent,
            timestamp=fecha_ejecucion,
        )
        
        body_text = f"""{titulo}
{'=' * 40}

{mensaje_principal}

Detalles:
"""
        for key, value in details.items():
            body_text += f"- {key.replace('_', ' ').title()}: {value}\n"
        body_text += f"""
Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
Accion Recomendada: Revisar los logs del sistema.
"""
        
        msg = create_email_message(
            subject=titulo,
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )
        
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
    fecha_ejecucion: Optional[datetime] = None,
    pedido_info: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Envía correo al proveedor con la ODC generada, incluyendo PDF adjunto.
    
    DESTINATARIO: proveedor_email (si se proporciona) o EMAIL_TO_OPERACIONES como fallback
    
    Args:
        oc_cabecera: Datos de cabecera de la orden de compra
        oc_detalles: Lista de detalles de la orden de compra.
            Cada detalle puede incluir opcionalmente campos enriquecidos:
            - codigo_barras: Código de barras del producto
            - descripcion / nombre_producto / descripcion_sap: Descripción del producto
        doc_num: Número de documento SAP (DocNum)
        doc_entry: Entry de documento SAP (DocEntry)
        proveedor_email: Email del proveedor (opcional)
        fecha_ejecucion: Fecha y hora de la ejecución (por defecto ahora)
        pedido_info: Información adicional del pedido (opcional).
            - proveedor_nombre: Razón social del proveedor
            - forma_pago: Plazo/forma de pago
            - fecha_entrega: Fecha de entrega
    
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
        
        from src.utils.email_template import (
            build_email, info_section, table_section, summary_section,
            paragraph, create_email_message,
        )
        
        # Calcular totales
        total_lineas = len(oc_detalles)
        total_cantidad = sum(d.get("cantidad_sap", 0) for d in oc_detalles)
        total_valor = sum(d.get("total_linea", 0) or 0 for d in oc_detalles)
        
        # Crear filas de la tabla (máximo 50)
        detalles_mostrar = oc_detalles[:50]
        table_rows = []
        for idx, detalle in enumerate(detalles_mostrar, 1):
            sku = detalle.get("sku_sap", "N/A")
            nombre = detalle.get("nombre_producto", "Sin nombre")
            cantidad = detalle.get("cantidad_sap", 0)
            unidad = detalle.get("unidad_sap", "N/A")
            precio_unit = detalle.get("precio_unitario", 0)
            total_linea = detalle.get("total_linea", 0)
            table_rows.append((
                str(idx), f"<strong>{sku}</strong>", nombre,
                f"{cantidad:.2f}", unidad, f"${precio_unit:.2f}", f"${total_linea:.2f}",
            ))
        
        footer_note = f"... y {len(oc_detalles) - 50} l&iacute;nea(s) m&aacute;s" if len(oc_detalles) > 50 else None
        
        body_html = build_email(
            title="Orden de Compra Generada",
            subtitle=f"ODC #{numero_oc_sap}",
            sections=[
                paragraph("Se ha generado una nueva Orden de Compra en SAP."),
                paragraph(
                    "Adjunto encontrar&aacute; el documento PDF de la Orden de Compra.",
                    italic=True,
                    color="#7f8c8d",
                ),
                info_section("Informaci&oacute;n de la ODC", [
                    ("N&uacute;mero ODC SAP", numero_oc_sap),
                    ("DocEntry", doc_entry or "N/A"),
                    ("Proveedor", proveedor),
                    ("Referencia", referencia),
                    ("Total L&iacute;neas", total_lineas),
                    ("Total Cantidad", f"{total_cantidad:.2f}"),
                    ("Total Valor", f"${total_valor:.2f}"),
                ], accent="green", highlight_first=True),
                table_section("Detalle de la Orden de Compra",
                    ["#", "SKU", "Producto", "Cantidad", "Unidad", "P. Unit.", "Total"],
                    table_rows, accent="green", footer_note=footer_note),
            ],
            accent="green",
            timestamp=fecha_ejecucion,
        )
        
        body_text = f"""Orden de Compra Generada - ODC #{numero_oc_sap}
{'=' * 40}

Adjunto: ODC {numero_oc_sap}.pdf

Informacion de la ODC:
- Numero ODC SAP: {numero_oc_sap}
- DocEntry: {doc_entry or 'N/A'}
- Proveedor: {proveedor}
- Referencia: {referencia}
- Total Lineas: {total_lineas}
- Total Cantidad: {total_cantidad:.2f}
- Total Valor: ${total_valor:.2f}

Detalle:
"""
        for idx, detalle in enumerate(detalles_mostrar, 1):
            sku = detalle.get("sku_sap", "N/A")
            nombre = detalle.get("nombre_producto", "Sin nombre")
            cantidad = detalle.get("cantidad_sap", 0)
            unidad = detalle.get("unidad_sap", "N/A")
            precio_unit = detalle.get("precio_unitario", 0)
            total_linea = detalle.get("total_linea", 0)
            body_text += f"  {idx}. {sku} - {nombre} | {cantidad:.2f} {unidad} | ${total_linea:.2f}\n"
        
        if len(oc_detalles) > 50:
            body_text += f"  ... y {len(oc_detalles) - 50} linea(s) mas\n"
        body_text += f"\nFecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        # ── Generar PDF adjunto ──────────────────────────────────────────
        pdf_attachment = None
        try:
            from src.utils.odc_pdf_generator import generar_odc_pdf
            
            pdf_bytes = generar_odc_pdf(
                oc_cabecera=oc_cabecera,
                oc_detalles=oc_detalles,
                doc_num=doc_num,
                doc_entry=doc_entry,
                pedido_info=pedido_info,
            )
            
            # Crear adjunto MIME
            pdf_attachment = MIMEBase("application", "pdf")
            pdf_attachment.set_payload(pdf_bytes)
            encoders.encode_base64(pdf_attachment)
            pdf_filename = f"ODC {numero_oc_sap}.pdf"
            pdf_attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=pdf_filename,
            )
            logger.info(f"📎 PDF adjunto generado: {pdf_filename} ({len(pdf_bytes):,} bytes)")
        except Exception as e:
            # Si falla la generación del PDF, enviar el email sin adjunto
            logger.warning(f"⚠️ No se pudo generar PDF adjunto (se enviará email sin PDF): {e}")
            pdf_attachment = None
        
        attachments = [pdf_attachment] if pdf_attachment else None
        
        msg = create_email_message(
            subject=f"Orden de Compra Generada - ODC #{numero_oc_sap}",
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
            attachments=attachments,
        )
        
        # Enviar email
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            # Solo usar TLS si el puerto es 587 (no para puerto 25 - relay interno)
            if EMAIL_SMTP_PORT == 587:
                server.starttls()
            
            # Solo autenticar si hay password configurada (no para relay interno)
            if EMAIL_SMTP_PASSWORD:
                server.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
            
            server.send_message(msg, to_addrs=recipients)
        
        pdf_status = "con PDF adjunto" if pdf_attachment else "sin PDF adjunto"
        logger.info(f"✅ Email de ODC enviado a {', '.join(recipients)} (ODC #{numero_oc_sap}) [{pdf_status}]")
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
        transferencias_detalle_texto = ""
        total_transferencias = 0
        transferencias_exitosas = 0
        transferencias_fallidas = 0
        
        if solicitudes_transferencia:
            total_transferencias = solicitudes_transferencia.get("total_tiendas", 0)
            transferencias_exitosas = solicitudes_transferencia.get("transferencias_creadas", 0)
            transferencias_fallidas = solicitudes_transferencia.get("transferencias_errores", 0)
            resultados = solicitudes_transferencia.get("resultados", [])
            
            # Construir tabla de transferencias (HTML y texto plano)
            if resultados:
                lineas_texto = []
                for resultado in resultados:
                    tienda_codigo = resultado.get("tienda_codigo", "N/A")
                    tienda_nombre = resultado.get("tienda_nombre") or tienda_codigo
                    success = resultado.get("success", False)
                    doc_num_transf = resultado.get("doc_num", "N/A")
                    error = resultado.get("error")
                    
                    estado = "Creada" if success else "Error"
                    doc_info = f"DocNum: {doc_num_transf}" if success else f"Error: {error or 'Desconocido'}"
                    
                    # HTML
                    estado_html = "✅ Creada" if success else "❌ Error"
                    transferencias_tabla += f"""
                    <tr>
                        <td>{tienda_codigo}</td>
                        <td>{tienda_nombre}</td>
                        <td>{estado_html}</td>
                        <td>{doc_info}</td>
                    </tr>
                    """
                    
                    # Texto plano
                    estado_txt = "Creada" if success else "Error"
                    lineas_texto.append(f"  {tienda_codigo}\t{tienda_nombre}\t{estado_txt}\t{doc_info}")
                
                transferencias_detalle_texto = "\n".join(lineas_texto)
        
        # Crear mensaje con multipart/alternative para que el cliente prefiera HTML
        msg = MIMEMultipart('alternative')
        msg['From'] = EMAIL_FROM
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = f"OC y Solicitudes de Transferencia - Listo para Despacho #{numero_oc_sap}"
        
        # --- Construir filas HTML de la tabla de transferencias ---
        filas_tabla_html = ""
        if solicitudes_transferencia and solicitudes_transferencia.get("resultados"):
            for idx, resultado in enumerate(solicitudes_transferencia.get("resultados", [])):
                tienda_codigo = resultado.get("tienda_codigo", "N/A")
                tienda_nombre = resultado.get("tienda_nombre") or tienda_codigo
                success = resultado.get("success", False)
                doc_num_transf = resultado.get("doc_num", "N/A")
                error = resultado.get("error")
                
                bg_color = "#f8fffe" if idx % 2 == 0 else "#ffffff"
                if success:
                    badge = '<span style="display:inline-block;background-color:#d4edda;color:#155724;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">Creada</span>'
                    info_html = f'<span style="font-family:Consolas,monospace;font-weight:600;color:#1a5276;">{doc_num_transf}</span>'
                else:
                    badge = '<span style="display:inline-block;background-color:#f8d7da;color:#721c24;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">Error</span>'
                    info_html = f'<span style="color:#721c24;">{error or "Desconocido"}</span>'
                
                filas_tabla_html += f'''
                <tr style="background-color:{bg_color};">
                    <td style="padding:12px 16px;border-bottom:1px solid #e8e8e8;font-weight:600;color:#2c3e50;">{tienda_codigo}</td>
                    <td style="padding:12px 16px;border-bottom:1px solid #e8e8e8;color:#555;">{tienda_nombre}</td>
                    <td style="padding:12px 16px;border-bottom:1px solid #e8e8e8;text-align:center;">{badge}</td>
                    <td style="padding:12px 16px;border-bottom:1px solid #e8e8e8;text-align:center;">{info_html}</td>
                </tr>'''
        
        # --- Sección de resumen de transferencias (HTML) ---
        seccion_transferencias_html = ""
        if solicitudes_transferencia:
            errores_html = ""
            if transferencias_fallidas > 0:
                errores_html = f'<span style="color:#dc3545;font-weight:600;margin-left:16px;">{transferencias_fallidas} con error</span>'
            
            seccion_transferencias_html = f'''
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;">
                <tr>
                    <td style="background:linear-gradient(135deg,#e8f5e9 0%,#c8e6c9 100%);border-radius:8px;padding:20px;">
                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                            <tr>
                                <td style="font-size:16px;font-weight:700;color:#2e7d32;">
                                    Solicitudes de Transferencia
                                </td>
                                <td style="text-align:right;">
                                    <span style="display:inline-block;background-color:#2e7d32;color:#fff;padding:6px 16px;border-radius:20px;font-size:14px;font-weight:700;">{transferencias_exitosas}/{total_transferencias} creadas</span>
                                    {errores_html}
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>'''
            
            if filas_tabla_html:
                seccion_transferencias_html += f'''
            <table width="100%" cellpadding="0" cellspacing="0" style="border-radius:8px;overflow:hidden;border:1px solid #e0e0e0;margin-bottom:24px;">
                <thead>
                    <tr style="background:linear-gradient(135deg,#1a5276 0%,#2980b9 100%);">
                        <th style="padding:14px 16px;text-align:left;color:#fff;font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Tienda</th>
                        <th style="padding:14px 16px;text-align:left;color:#fff;font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Nombre</th>
                        <th style="padding:14px 16px;text-align:center;color:#fff;font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Estado</th>
                        <th style="padding:14px 16px;text-align:center;color:#fff;font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">DocNum</th>
                    </tr>
                </thead>
                <tbody>
                    {filas_tabla_html}
                </tbody>
            </table>'''
        
        # --- Sección de número de pedido (HTML) ---
        pedido_html = ""
        if pedido_numero:
            pedido_html = f'''
                            <tr>
                                <td style="padding:8px 0;color:#7f8c8d;font-size:13px;width:160px;">Pedido</td>
                                <td style="padding:8px 0;font-weight:600;color:#2c3e50;">{pedido_numero}</td>
                            </tr>'''
        
        # Crear cuerpo del mensaje HTML (inline styles para compatibilidad con clientes de correo)
        body_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OC y Solicitudes de Transferencia</title>
</head>
<body style="margin:0;padding:0;background-color:#f0f2f5;font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f0f2f5;padding:24px 0;">
        <tr>
            <td align="center">
                <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
                    
                    <!-- Header -->
                    <tr>
                        <td style="background:linear-gradient(135deg,#1a5276 0%,#2980b9 100%);padding:32px 40px;text-align:center;">
                            <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;letter-spacing:-0.3px;">
                                OC y Solicitudes de Transferencia Generadas
                            </h1>
                            <p style="margin:8px 0 0;color:rgba(255,255,255,0.85);font-size:14px;">
                                Listo para despacho y facturaci&oacute;n
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Body -->
                    <tr>
                        <td style="padding:32px 40px;">
                            
                            <!-- Mensaje principal -->
                            <p style="margin:0 0 24px;color:#2c3e50;font-size:15px;line-height:1.6;">
                                Se ha generado exitosamente la <strong>Orden de Compra</strong> y las 
                                <strong>Solicitudes de Transferencia</strong> en SAP. 
                                Pueden proceder con el despacho y facturaci&oacute;n.
                            </p>
                            
                            <!-- Info OC -->
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
                                <tr>
                                    <td style="background-color:#f8f9fa;border-radius:8px;padding:20px 24px;border-left:4px solid #2980b9;">
                                        <h3 style="margin:0 0 12px;color:#1a5276;font-size:15px;font-weight:700;">Informaci&oacute;n de la Orden de Compra</h3>
                                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="padding:8px 0;color:#7f8c8d;font-size:13px;width:160px;">N&uacute;mero OC SAP</td>
                                                <td style="padding:8px 0;font-weight:700;color:#1a5276;font-size:18px;">{numero_oc_sap}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding:8px 0;color:#7f8c8d;font-size:13px;">DocEntry</td>
                                                <td style="padding:8px 0;font-weight:600;color:#2c3e50;">{doc_entry or 'N/A'}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding:8px 0;color:#7f8c8d;font-size:13px;">Proveedor</td>
                                                <td style="padding:8px 0;font-weight:600;color:#2c3e50;">{proveedor}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding:8px 0;color:#7f8c8d;font-size:13px;">Referencia</td>
                                                <td style="padding:8px 0;font-weight:600;color:#2c3e50;">{referencia}</td>
                                            </tr>{pedido_html}
                                        </table>
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Solicitudes de Transferencia -->
                            {seccion_transferencias_html}
                            
                            <!-- Accion Requerida -->
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;">
                                <tr>
                                    <td style="background-color:#fff8e1;border-radius:8px;padding:20px 24px;border-left:4px solid #f9a825;">
                                        <h3 style="margin:0 0 8px;color:#e65100;font-size:15px;font-weight:700;">Acci&oacute;n Requerida</h3>
                                        <p style="margin:0 0 8px;color:#5d4037;font-size:14px;line-height:1.5;">
                                            El personal de El Rayo puede proceder con:
                                        </p>
                                        <table role="presentation" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="padding:4px 8px 4px 0;color:#2e7d32;font-size:14px;">&#10003;</td>
                                                <td style="padding:4px 0;color:#5d4037;font-size:14px;">Despacho de mercader&iacute;a</td>
                                            </tr>
                                            <tr>
                                                <td style="padding:4px 8px 4px 0;color:#2e7d32;font-size:14px;">&#10003;</td>
                                                <td style="padding:4px 0;color:#5d4037;font-size:14px;">Facturaci&oacute;n correspondiente</td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                            
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background-color:#f8f9fa;padding:20px 40px;text-align:center;border-top:1px solid #e8e8e8;">
                            <p style="margin:0;color:#95a5a6;font-size:12px;">
                                Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
                            </p>
                            <p style="margin:4px 0 0;color:#bdc3c7;font-size:11px;">
                                Mensaje autom&aacute;tico del sistema de integraci&oacute;n SAP &mdash; Mabel Trading
                            </p>
                        </td>
                    </tr>
                    
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
        
        # --- Versión texto plano (fallback) ---
        seccion_transferencias_texto = ""
        if solicitudes_transferencia:
            seccion_transferencias_texto = f"""
Solicitudes de Transferencia Generadas:
- Total: {transferencias_exitosas}/{total_transferencias} creadas exitosamente
{f'- Errores: {transferencias_fallidas} solicitud(es) fallaron' if transferencias_fallidas > 0 else ''}"""
            if transferencias_detalle_texto:
                seccion_transferencias_texto += f"""

Detalle de Solicitudes de Transferencia:
  Tienda\tNombre\tEstado\tDocNum
{transferencias_detalle_texto}"""
        
        body_text = f"""OC y Solicitudes de Transferencia Generadas
{'=' * 50}

Se ha generado exitosamente la Orden de Compra y las Solicitudes de Transferencia en SAP.
Pueden proceder con el despacho y facturacion.

Informacion de la Orden de Compra:
- Numero OC SAP: {numero_oc_sap}
- DocEntry: {doc_entry or 'N/A'}
- Proveedor: {proveedor}
- Referencia: {referencia}
{f'- Numero de Pedido: {pedido_numero}' if pedido_numero else ''}
{seccion_transferencias_texto}

Accion Requerida:
El personal de El Rayo puede proceder con:
- Despacho de mercaderia
- Facturacion correspondiente

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
Mensaje automatico del sistema de integracion SAP - Mabel Trading
"""
        
        # ⭐ IMPORTANTE: Orden de attach - el último es el preferido por el cliente de correo
        # En multipart/alternative, el cliente de correo elige el formato más rico (HTML)
        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
        msg.attach(MIMEText(body_html, 'html', 'utf-8'))
        
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


def send_plantilla_upload_notification(
    pedido_id: Optional[str] = None,
    numero_pedido: Optional[str] = None,
    filename: Optional[str] = None,
    usuario_id: Optional[str] = None,
    articulos_cargados: int = 0,
    distribuciones_cargadas: int = 0,
    formato_detectado: Optional[str] = None,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía notificación a El Rayo cuando se sube exitosamente una plantilla Excel.
    
    DESTINATARIO: EMAIL_TO_OPERACIONES (Operaciones/Despachos - El Rayo)
    
    Args:
        pedido_id: UUID del pedido creado
        numero_pedido: Número del pedido
        filename: Nombre del archivo Excel subido
        usuario_id: ID del usuario que subió la plantilla
        articulos_cargados: Cantidad de artículos cargados
        distribuciones_cargadas: Cantidad de distribuciones cargadas
        formato_detectado: Formato detectado del Excel
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
            logger.warning("⚠️ No hay destinatarios configurados para notificación de plantilla")
            return False
        
        from src.utils.email_template import build_email, info_section, paragraph, create_email_message
        
        body_html = build_email(
            title="Plantilla Excel Procesada Exitosamente",
            subtitle=f"Pedido: {numero_pedido or 'N/A'}",
            sections=[
                paragraph("Se ha procesado y guardado exitosamente una plantilla Excel de pedido."),
                info_section("Informaci&oacute;n del Pedido", [
                    ("N&uacute;mero de Pedido", numero_pedido or "N/A"),
                    ("Pedido ID", pedido_id or "N/A"),
                    ("Archivo", filename or "N/A"),
                    ("Usuario", usuario_id or "N/A"),
                    ("Formato", formato_detectado or "N/A"),
                    ("Art&iacute;culos Cargados", articulos_cargados),
                    ("Distribuciones Cargadas", distribuciones_cargadas),
                ], accent="green"),
            ],
            accent="green",
            timestamp=fecha_ejecucion,
        )
        
        body_text = f"""Plantilla Excel Procesada Exitosamente
{'=' * 40}

Informacion del Pedido:
- Numero de Pedido: {numero_pedido or 'N/A'}
- Pedido ID: {pedido_id or 'N/A'}
- Archivo: {filename or 'N/A'}
- Usuario: {usuario_id or 'N/A'}
- Formato: {formato_detectado or 'N/A'}
- Articulos Cargados: {articulos_cargados}
- Distribuciones Cargadas: {distribuciones_cargadas}

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        msg = create_email_message(
            subject=f"Plantilla Excel Procesada - {numero_pedido or 'N/A'}",
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )
        
        # Enviar email
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            # Solo usar TLS si el puerto es 587 (no para puerto 25 - relay interno)
            if EMAIL_SMTP_PORT == 587:
                server.starttls()
            
            # Solo autenticar si hay password configurada (no para relay interno)
            if EMAIL_SMTP_PASSWORD:
                server.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
            
            server.send_message(msg, to_addrs=recipients)
        
        logger.info(f"✅ Notificación de plantilla procesada enviada a {', '.join(recipients)} (Pedido: {numero_pedido or pedido_id or 'N/A'})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al enviar notificación de plantilla procesada: {e}", exc_info=True)
        return False


def send_pedido_cancelado_notification(
    pedido_id: str,
    numero_pedido: Optional[str] = None,
    usuario_id: Optional[str] = None,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía notificación a El Rayo cuando se cancela un pedido (cambia estado a CANCELADO).

    Se usa al procesar POST /api/pedidos/{pedido_id}/cancelar desde Redistribución.
    DESTINATARIO: EMAIL_TO_OPERACIONES (Operaciones/Despachos - El Rayo)

    Args:
        pedido_id: UUID del pedido cancelado
        numero_pedido: Número del pedido (opcional, para identificación)
        usuario_id: Usuario que canceló el pedido (MABEL TRADING)
        fecha_ejecucion: Fecha y hora de la cancelación (por defecto ahora)

    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        logger.debug("⏭️ Notificaciones por email deshabilitadas")
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = datetime.now()

    try:
        recipients = EMAIL_TO_OPERACIONES if isinstance(EMAIL_TO_OPERACIONES, list) else [EMAIL_TO_OPERACIONES] if EMAIL_TO_OPERACIONES else []

        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados para notificación de pedido descartado")
            return False

        from src.utils.email_template import build_email, info_section, paragraph, badge_html, create_email_message
        
        body_html = build_email(
            title="Pedido Cancelado",
            subtitle=f"Pedido: {numero_pedido or pedido_id}",
            sections=[
                paragraph(f"Se ha cancelado un pedido. El estado ha cambiado a {badge_html('CANCELADO', '#ffebee', '#c62828')}."),
                info_section("Informaci&oacute;n del Pedido", [
                    ("N&uacute;mero de Pedido", numero_pedido or "N/A"),
                    ("Pedido ID", pedido_id),
                    ("Usuario que cancel&oacute;", usuario_id or "N/A"),
                    ("Nuevo Estado", badge_html("CANCELADO", "#ffebee", "#c62828")),
                ], accent="red"),
                paragraph("El pedido permanece en el sistema con estado CANCELADO y no ser&aacute; procesado.", italic=True),
            ],
            accent="red",
            timestamp=fecha_ejecucion,
        )
        
        body_text = f"""Pedido Cancelado - {numero_pedido or pedido_id}
{'=' * 40}

- Numero de Pedido: {numero_pedido or 'N/A'}
- Pedido ID: {pedido_id}
- Usuario que cancelo: {usuario_id or 'N/A'}
- Fecha y hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
- Nuevo Estado: CANCELADO

El pedido permanece en el sistema con estado CANCELADO y no sera procesado.
"""
        
        msg = create_email_message(
            subject=f"Pedido Cancelado - {numero_pedido or pedido_id}",
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            if EMAIL_SMTP_PORT == 587:
                server.starttls()
            if EMAIL_SMTP_PASSWORD:
                server.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
            server.send_message(msg, to_addrs=recipients)

        logger.info(f"✅ Notificación de pedido cancelado enviada a {', '.join(recipients)} (Pedido: {numero_pedido or pedido_id})")
        return True

    except Exception as e:
        logger.error(f"❌ Error al enviar notificación de pedido cancelado: {e}", exc_info=True)
        return False


def send_pedido_descartado_notification(
    pedido_id: str,
    numero_pedido: Optional[str] = None,
    usuario_id: Optional[str] = None,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía notificación a El Rayo cuando se descarta (elimina) un pedido.

    Se usa al procesar DELETE /api/pedidos/{pedido_id} desde Cargar Plantilla (solo Borrador/Nuevo Pedido).
    DESTINATARIO: EMAIL_TO_OPERACIONES (Operaciones/Despachos - El Rayo)

    Args:
        pedido_id: UUID del pedido descartado
        numero_pedido: Número del pedido (opcional, para identificación)
        usuario_id: Usuario que descartó el pedido (MABEL TRADING)
        fecha_ejecucion: Fecha y hora del descarte (por defecto ahora)

    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        logger.debug("⏭️ Notificaciones por email deshabilitadas")
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = datetime.now()

    try:
        recipients = EMAIL_TO_OPERACIONES if isinstance(EMAIL_TO_OPERACIONES, list) else [EMAIL_TO_OPERACIONES] if EMAIL_TO_OPERACIONES else []

        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados para notificación de pedido descartado")
            return False

        from src.utils.email_template import build_email, info_section, paragraph, create_email_message
        
        body_html = build_email(
            title="Pedido Descartado",
            subtitle=f"Pedido: {numero_pedido or pedido_id}",
            sections=[
                paragraph("Se ha descartado y eliminado un pedido completamente de la base de datos."),
                info_section("Informaci&oacute;n del Pedido", [
                    ("N&uacute;mero de Pedido", numero_pedido or "N/A"),
                    ("Pedido ID", pedido_id),
                    ("Usuario que descart&oacute;", usuario_id or "N/A"),
                ], accent="red"),
                paragraph("El pedido ya no est&aacute; disponible en el sistema. Podr&aacute;n volver a cargarlo desde cero si lo necesitan.", italic=True),
            ],
            accent="red",
            timestamp=fecha_ejecucion,
        )
        
        body_text = f"""Pedido Descartado - {numero_pedido or pedido_id}
{'=' * 40}

- Numero de Pedido: {numero_pedido or 'N/A'}
- Pedido ID: {pedido_id}
- Usuario que descarto: {usuario_id or 'N/A'}
- Fecha y hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}

El pedido ya no esta disponible en el sistema.
"""
        
        msg = create_email_message(
            subject=f"Pedido Descartado - {numero_pedido or pedido_id}",
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            if EMAIL_SMTP_PORT == 587:
                server.starttls()
            if EMAIL_SMTP_PASSWORD:
                server.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
            server.send_message(msg, to_addrs=recipients)

        logger.info(f"✅ Notificación de pedido descartado enviada a {', '.join(recipients)} (Pedido: {numero_pedido or pedido_id})")
        return True

    except Exception as e:
        logger.error(f"❌ Error al enviar notificación de pedido descartado: {e}", exc_info=True)
        return False


def send_mabel_redistribucion_confirmacion_notification(
    pedido_id: str,
    numero_pedido: str,
    usuario_mabel: Optional[str] = None,
    version_confirmada: Optional[int] = None,
    total_productos: int = 0,
    total_cantidad_ajustada: int = 0,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía correo a El Rayo notificando que MABEL TRADING confirmó la redistribución de un pedido.
    
    DESTINATARIO: EMAIL_TO_OPERACIONES (Operaciones/Despachos - El Rayo)
    
    Args:
        pedido_id: UUID del pedido
        numero_pedido: Número del pedido
        usuario_mabel: ID del usuario de MABEL TRADING que confirmó (opcional)
        version_confirmada: Versión de la redistribución confirmada (opcional)
        total_productos: Total de productos redistribuidos
        total_cantidad_ajustada: Total de cantidad ajustada en la redistribución
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
            logger.warning("⚠️ No hay destinatarios configurados para notificación de redistribución")
            return False
        
        # Construir URL del pedido
        import os
        base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        numero_pedido_encoded = numero_pedido.replace(" ", "%20")
        url_pedido = f"{base_url}/mba3-consultas/pedidos/{numero_pedido_encoded}"
        
        from src.utils.email_template import (
            build_email, info_section, success_badge_section,
            button_section, paragraph, badge_html, create_email_message,
        )
        
        info_items = [
            ("N&uacute;mero de Pedido", numero_pedido),
            ("Pedido ID", pedido_id),
        ]
        if usuario_mabel:
            info_items.append(("Usuario MABEL TRADING", usuario_mabel))
        if version_confirmada:
            info_items.append(("Versi&oacute;n Confirmada", version_confirmada))
        info_items.extend([
            ("Total Productos Redistribuidos", total_productos),
            ("Total Cantidad Ajustada", total_cantidad_ajustada),
            ("Estado", badge_html("CONFIRMADO REDISTRIBUCION", "#e8f5e9", "#2e7d32")),
        ])
        
        body_html = build_email(
            title="Redistribuci&oacute;n Confirmada por MABEL TRADING",
            subtitle=f"Pedido: {numero_pedido}",
            sections=[
                success_badge_section("MABEL TRADING ha confirmado la redistribuci&oacute;n exitosamente"),
                paragraph("Se ha procesado la confirmaci&oacute;n de la redistribuci&oacute;n del pedido y est&aacute; listo para continuar."),
                info_section("Informaci&oacute;n del Pedido", info_items, accent="blue"),
                button_section("Ver Pedido", url_pedido, accent="blue"),
                paragraph("El pedido est&aacute; ahora listo para la generaci&oacute;n de orden de compra (ODC).", italic=True),
            ],
            accent="blue",
            timestamp=fecha_ejecucion,
        )
        
        body_text = f"""Redistribucion Confirmada por MABEL TRADING
{'=' * 40}

Informacion del Pedido:
- Numero de Pedido: {numero_pedido}
- Pedido ID: {pedido_id}
{f'- Usuario MABEL TRADING: {usuario_mabel}' if usuario_mabel else ''}
{f'- Version Confirmada: {version_confirmada}' if version_confirmada else ''}
- Total Productos: {total_productos}
- Total Cantidad Ajustada: {total_cantidad_ajustada}
- Estado: CONFIRMADO REDISTRIBUCION

Ver Pedido: {url_pedido}

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        msg = create_email_message(
            subject=f"Redistribucion Confirmada por MABEL TRADING - {numero_pedido}",
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )
        
        # Enviar email
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            # Solo usar TLS si el puerto es 587 (no para puerto 25 - relay interno)
            if EMAIL_SMTP_PORT == 587:
                server.starttls()
            
            # Solo autenticar si hay password configurada (no para relay interno)
            if EMAIL_SMTP_PASSWORD:
                server.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
            
            server.send_message(msg, to_addrs=recipients)
        
        logger.info(f"✅ Notificación de redistribución confirmada enviada a {', '.join(recipients)} (Pedido: {numero_pedido})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al enviar notificación de redistribución confirmada: {e}", exc_info=True)
        return False


def send_pedido_eliminado_mabel_notification(
    pedido_id: str,
    numero_pedido: Optional[str] = None,
    usuario_id: Optional[str] = None,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía notificación a MABEL TRADING cuando se elimina un pedido desde Detalle del Pedido.

    Se usa al procesar DELETE /api/pedidos/{pedido_id}/eliminar (botón "Eliminar Pedido").
    DESTINATARIO: EMAIL_MABEL_TRADING (Usuario MABEL TRADING)

    Args:
        pedido_id: UUID del pedido eliminado
        numero_pedido: Número del pedido (opcional, para identificación)
        usuario_id: Usuario que eliminó el pedido (MABEL TRADING)
        fecha_ejecucion: Fecha y hora de la eliminación (por defecto ahora)

    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        logger.debug("⏭️ Notificaciones por email deshabilitadas")
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = datetime.now()

    try:
        # Usar EMAIL_MABEL_TRADING
        recipients = [EMAIL_MABEL_TRADING] if isinstance(EMAIL_MABEL_TRADING, str) else EMAIL_MABEL_TRADING

        if not recipients:
            logger.warning("⚠️ No hay destinatarios de MABEL TRADING configurados")
            return False

        from src.utils.email_template import build_email, info_section, warning_section, paragraph, create_email_message
        
        body_html = build_email(
            title="Pedido Eliminado Exitosamente",
            subtitle=f"Pedido: {numero_pedido or pedido_id}",
            sections=[
                paragraph("Se ha eliminado un pedido desde la interfaz de Detalle del Pedido."),
                info_section("Informaci&oacute;n del Pedido Eliminado", [
                    ("N&uacute;mero de Pedido", numero_pedido or "N/A"),
                    ("Pedido ID", pedido_id),
                    ("Usuario que elimin&oacute;", usuario_id or "N/A"),
                    ("Estado al eliminar", "Gestionar Pedido"),
                ], accent="green"),
                warning_section("Nota Importante",
                    '<p style="margin:0;color:#5d4037;font-size:14px;">Esta es una operaci&oacute;n irreversible. Si necesita crear el pedido nuevamente, deber&aacute; cargarlo desde cero.</p>'),
            ],
            accent="green",
            timestamp=fecha_ejecucion,
        )
        
        body_text = f"""Pedido Eliminado Exitosamente - {numero_pedido or pedido_id}
{'=' * 40}

- Numero de Pedido: {numero_pedido or 'N/A'}
- Pedido ID: {pedido_id}
- Usuario que elimino: {usuario_id or 'N/A'}
- Fecha y hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
- Estado al eliminar: Gestionar Pedido

Nota: Operacion irreversible. Para crear el pedido nuevamente, cargarlo desde cero.
"""
        
        msg = create_email_message(
            subject=f"Pedido Eliminado - {numero_pedido or pedido_id}",
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            if EMAIL_SMTP_PORT == 587:
                server.starttls()
            if EMAIL_SMTP_PASSWORD:
                server.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
            server.send_message(msg, to_addrs=recipients)

        logger.info(f"✅ Notificación de pedido eliminado enviada a MABEL TRADING {', '.join(recipients)} (Pedido: {numero_pedido or pedido_id})")
        return True

    except Exception as e:
        logger.error(f"❌ Error al enviar notificación de pedido eliminado a MABEL TRADING: {e}", exc_info=True)
        return False

