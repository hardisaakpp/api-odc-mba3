"""
Módulo para enviar notificaciones por correo electrónico usando Outlook.
"""

import logging
import csv
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

from src.utils.timezone import ahora_naive
from typing import List, Optional, Dict, Any
from src.config import (
    EMAIL_SMTP_USER,
    EMAIL_FROM,
    ENABLE_EMAIL_NOTIFICATIONS,
)
from src.utils.notificacion_destinatarios import get_destinatarios_por_correo
from src.utils.smtp_sender import send_smtp_message

logger = logging.getLogger(__name__)

_MSG_EMAIL_DESHABILITADO = "⏭️ Notificaciones por email deshabilitadas"
_DEFAULT_NOMBRE_PRODUCTO = "Sin nombre"
_PROBLEMA_ERROR_CONSULTAR = "Error al consultar"
_PROBLEMA_NO_EXISTE = "No existe en SAP"
_SECCION_INFO_PEDIDO = "Informaci&oacute;n del Pedido"
_LABEL_NUMERO_PEDIDO = "N&uacute;mero de Pedido"
_LABEL_PEDIDO_ID = "Pedido ID"

# Asuntos exactos del catálogo (notificacion_tipo_correo.tipo_correo): deben
# coincidir con el seed en scripts/migrations/create_notificacion_tipo_correo.sql
# para que get_destinatarios_por_correo() resuelva destinatarios reales.
_CORREO_MIGRACION = "Nuevos Registros Migrados"
_CORREO_ERROR_MIGRACION = "Error en Migración Automática"
_CORREO_HOMOLOGACION = "Productos NO Homologados Detectados"
_CORREO_CAPACITY_WARNING = "Advertencia de Capacidad"
_CORREO_OC_PROVEEDOR = "Orden de Compra Generada"
_CORREO_DESPACHO = "OC y Solicitudes de Transferencia - Listo para Despacho"
_CORREO_OC_ST_ERROR = "Error en OC y Solicitudes de Transferencia"
_CORREO_PLANTILLA = "Plantilla Excel Procesada (Pedido Enviado)"
_CORREO_PEDIDO_CANCELADO = "Pedido Cancelado"
_CORREO_PEDIDO_DESCARTADO = "Pedido Descartado"
_CORREO_REDISTRIBUCION_CONFIRMADA = "Redistribución Confirmada por MABEL TRADING"
_CORREO_PEDIDO_ELIMINADO = "Pedido Eliminado"
_CORREO_PEDIDO_CONFIRMADO_PRODUCCION = "Pedido Confirmado por Producción"


# ─── Helpers privados ────────────────────────────────────────────────────────

def _filtrar_productos_a_notificar(productos, filtrar_ya_notificados, homologacion_repository):
    if not filtrar_ya_notificados or not homologacion_repository:
        return productos
    try:
        skus_ya_notificados = homologacion_repository.get_skus_ya_notificados()
        filtrados = [p for p in productos if p.get("sku") not in skus_ya_notificados]
        if not filtrados:
            logger.info("⏭️ Todos los productos no homologados ya fueron notificados")
            return []
        logger.info(f"📧 Productos a notificar: {len(filtrados)} (filtrados: {len(skus_ya_notificados)})")
        return filtrados
    except Exception as e:
        logger.warning(f"⚠️ No se pudo filtrar productos ya notificados: {e}")
        return productos


def _get_estadisticas_homologacion(estadisticas, n_productos):
    if estadisticas:
        return (
            estadisticas.get("total_productos_mba3", 0),
            estadisticas.get("productos_homologados", 0),
            estadisticas.get("productos_no_homologados", 0),
            estadisticas.get("porcentaje_homologacion", 0.0),
        )
    return 0, 0, n_productos, 0.0


def _tipo_badge_homologacion(tipo_problema, badge_html_fn):
    if tipo_problema == "mismatch":
        return badge_html_fn("MISMATCH", "#fff3e0", "#e65100")
    if tipo_problema == "error":
        return badge_html_fn("Error", "#ffebee", "#c62828")
    return badge_html_fn("No existe", "#e3f2fd", "#1565c0")


def _build_homologacion_table_rows(productos_mostrar, badge_html_fn):
    table_rows = []
    for idx, producto in enumerate(productos_mostrar, 1):
        sku = producto.get("sku", "N/A")
        nombre = producto.get("nombre_producto", _DEFAULT_NOMBRE_PRODUCTO)
        veces_usado = producto.get("veces_usado", 0)
        total_docenas_val = producto.get("total_docenas", 0.0)
        total_valor_val = producto.get("total_valor", 0.0)
        ultima_aparicion = producto.get("ultima_aparicion", "N/A")
        tipo_problema = producto.get("tipo_problema", "no_existe")
        tipo_badge = _tipo_badge_homologacion(tipo_problema, badge_html_fn)
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
    return table_rows


def _build_homologacion_resumen_items(productos_mismatch, productos_no_existen, productos_error, productos_sin_tipo, badge_html_fn):
    items = []
    if productos_mismatch:
        items.append(("Mismatch (SKU ≠ ItemCode)", f'{badge_html_fn(str(len(productos_mismatch)), "#fff3e0", "#e65100")} producto(s)'))
    if productos_no_existen:
        items.append((_PROBLEMA_NO_EXISTE, f'{badge_html_fn(str(len(productos_no_existen)), "#e3f2fd", "#1565c0")} producto(s)'))
    if productos_error:
        items.append((_PROBLEMA_ERROR_CONSULTAR, f'{badge_html_fn(str(len(productos_error)), "#ffebee", "#c62828")} producto(s)'))
    if productos_sin_tipo:
        items.append(("Sin clasificar", f'{badge_html_fn(str(len(productos_sin_tipo)), "#f5f5f5", "#616161")} producto(s)'))
    return items


def _tipo_problema_desc_texto(tipo_problema, item_code_sap):
    if tipo_problema == "mismatch":
        return f"MISMATCH - ItemCode SAP: {item_code_sap}"
    if tipo_problema == "error":
        return _PROBLEMA_ERROR_CONSULTAR
    return _PROBLEMA_NO_EXISTE


def _tipo_problema_desc_csv(tipo_problema):
    if tipo_problema == "mismatch":
        return "MISMATCH"
    if tipo_problema == "error":
        return _PROBLEMA_ERROR_CONSULTAR
    return _PROBLEMA_NO_EXISTE


def _build_homologacion_body_text(productos_mostrar, productos_a_notificar, total_mba3, homologados, no_homologados, porcentaje, fecha_ejecucion):
    body = f"""
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
        nombre = producto.get("nombre_producto", _DEFAULT_NOMBRE_PRODUCTO)
        veces_usado = producto.get("veces_usado", 0)
        total_docenas = producto.get("total_docenas", 0.0)
        total_valor = producto.get("total_valor", 0.0)
        ultima_aparicion = producto.get("ultima_aparicion", "N/A")
        tipo_problema = producto.get("tipo_problema", "no_existe")
        item_code_sap = producto.get("item_code_sap")
        problema_desc = _tipo_problema_desc_texto(tipo_problema, item_code_sap)
        body += f"""
        {idx}. SKU: {sku}
           Nombre: {nombre}
           Tipo de Problema: {problema_desc}
           Veces Usado: {veces_usado}
           Total Docenas: {total_docenas:.2f}
           Total Valor: ${total_valor:.2f}
           Última Aparición: {ultima_aparicion}
        """
    if len(productos_a_notificar) > 20:
        body += f"\n        ... y {len(productos_a_notificar) - 20} producto(s) más\n"
    body += f"""

        Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}

        Nota: Este es un mensaje automático del sistema de migración MBA3.
        Se adjunta un archivo CSV con el detalle completo de todos los productos no homologados.
        """
    return body


def _build_homologacion_csv(productos_a_notificar, fecha_ejecucion):
    try:
        csv_buffer = io.StringIO()
        csv_writer = csv.writer(csv_buffer)
        csv_writer.writerow([
            'SKU', 'Nombre Producto', 'Tipo de Problema', 'ItemCode SAP',
            'Veces Usado', 'Total Docenas', 'Total Valor',
            'Primera Aparición', 'Última Aparición'
        ])
        for producto in productos_a_notificar:
            tipo_problema = producto.get("tipo_problema", "no_existe")
            item_code_sap = producto.get("item_code_sap", "")
            problema_desc = _tipo_problema_desc_csv(tipo_problema)
            csv_writer.writerow([
                producto.get("sku", "N/A"),
                producto.get("nombre_producto", _DEFAULT_NOMBRE_PRODUCTO),
                problema_desc,
                item_code_sap,
                producto.get("veces_usado", 0),
                f"{producto.get('total_docenas', 0.0):.2f}",
                f"{producto.get('total_valor', 0.0):.2f}",
                producto.get("primera_aparicion", "N/A"),
                producto.get("ultima_aparicion", "N/A")
            ])
        csv_bytes = csv_buffer.getvalue().encode('utf-8-sig')
        csv_attachment = MIMEBase('text', 'csv')
        csv_attachment.set_payload(csv_bytes)
        encoders.encode_base64(csv_attachment)
        fecha_str = fecha_ejecucion.strftime('%Y%m%d_%H%M%S')
        filename = f"productos_no_homologados_{fecha_str}.csv"
        csv_attachment.add_header('Content-Disposition', f'attachment; filename= {filename}')
        logger.debug(f"✅ Archivo CSV generado y adjuntado: {filename}")
        return [csv_attachment]
    except Exception as csv_error:
        logger.warning(f"⚠️ Error al generar CSV adjunto: {csv_error}")
        return []


def _registrar_notificados(homologacion_repository, productos_a_notificar):
    if not homologacion_repository:
        return
    try:
        skus = [p.get("sku") for p in productos_a_notificar if p.get("sku")]
        registrados = homologacion_repository.registrar_productos_notificados(skus)
        logger.info(f"✅ Registrados {registrados} productos como notificados")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo registrar productos notificados: {e}")


def _generate_odc_pdf_attachment(oc_cabecera, oc_detalles, doc_num, numero_oc_sap, pedido_info):
    try:
        from src.utils.odc_pdf_generator import generar_odc_pdf
        pdf_bytes = generar_odc_pdf(
            oc_cabecera=oc_cabecera,
            oc_detalles=oc_detalles,
            doc_num=doc_num,
            pedido_info=pedido_info,
        )
        pdf_attachment = MIMEBase("application", "pdf")
        pdf_attachment.set_payload(pdf_bytes)
        encoders.encode_base64(pdf_attachment)
        pdf_filename = f"ODC {numero_oc_sap}.pdf"
        pdf_attachment.add_header("Content-Disposition", "attachment", filename=pdf_filename)
        logger.info(f"📎 PDF adjunto generado: {pdf_filename} ({len(pdf_bytes):,} bytes)")
        return pdf_attachment
    except Exception as e:
        logger.warning(f"⚠️ No se pudo generar PDF adjunto (se enviará email sin PDF): {e}")
        return None


def _build_unique_recipients(tipos, tipo_correo):
    seen = set()
    recipients = []
    for tipo in tipos:
        for email in get_destinatarios_por_correo(tipo, tipo_correo):
            e = (email or "").strip().lower()
            if e and e not in seen:
                seen.add(e)
                recipients.append(email.strip())
    return recipients


def _extract_transferencias_data(solicitudes_transferencia):
    if not solicitudes_transferencia:
        return 0, 0, 0, ""
    total = solicitudes_transferencia.get("total_tiendas", 0)
    exitosas = solicitudes_transferencia.get("transferencias_creadas", 0)
    fallidas = solicitudes_transferencia.get("transferencias_errores", 0)
    lineas_texto = []
    for resultado in solicitudes_transferencia.get("resultados", []):
        tienda_codigo = resultado.get("tienda_codigo", "N/A")
        tienda_nombre = resultado.get("tienda_nombre") or tienda_codigo
        success = resultado.get("success", False)
        doc_num_transf = resultado.get("doc_num", "N/A")
        error = resultado.get("error")
        if success:
            estado_txt = "Creada"
            doc_info = f"DocNum: {doc_num_transf}"
        elif resultado.get("queued"):
            estado_txt = "Encolada"
            doc_info = "SAP saturado, en cola (no es un error definitivo)"
        else:
            estado_txt = "Error"
            doc_info = f"Error: {error or 'Desconocido'}"
        lineas_texto.append(f"  {tienda_codigo}\t{tienda_nombre}\t{estado_txt}\t{doc_info}")
    return total, exitosas, fallidas, "\n".join(lineas_texto)


def _build_filas_tabla_despacho(solicitudes_transferencia):
    if not solicitudes_transferencia or not solicitudes_transferencia.get("resultados"):
        return ""
    filas = ""
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
        elif resultado.get("queued"):
            badge = '<span style="display:inline-block;background-color:#fff3cd;color:#856404;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">Encolada</span>'
            info_html = '<span style="color:#856404;">SAP saturado, en cola (no es un error definitivo)</span>'
        else:
            badge = '<span style="display:inline-block;background-color:#f8d7da;color:#721c24;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">Error</span>'
            info_html = f'<span style="color:#721c24;">{error or "Desconocido"}</span>'
        filas += f'''
                <tr style="background-color:{bg_color};">
                    <td style="padding:12px 16px;border-bottom:1px solid #e8e8e8;font-weight:600;color:#2c3e50;">{tienda_codigo}</td>
                    <td style="padding:12px 16px;border-bottom:1px solid #e8e8e8;color:#555;">{tienda_nombre}</td>
                    <td style="padding:12px 16px;border-bottom:1px solid #e8e8e8;text-align:center;">{badge}</td>
                    <td style="padding:12px 16px;border-bottom:1px solid #e8e8e8;text-align:center;">{info_html}</td>
                </tr>'''
    return filas


def _build_seccion_transferencias_despacho(solicitudes, exitosas, total, fallidas, filas_tabla_html):
    if not solicitudes:
        return ""
    errores_html = f'<span style="color:#dc3545;font-weight:600;margin-left:16px;">{fallidas} con error</span>' if fallidas > 0 else ""
    seccion = f'''
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;">
                <tr>
                    <td style="background:linear-gradient(135deg,#e8f5e9 0%,#c8e6c9 100%);border-radius:8px;padding:20px;">
                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                            <tr>
                                <td style="font-size:16px;font-weight:700;color:#2e7d32;">
                                    Solicitudes de Transferencia
                                </td>
                                <td style="text-align:right;">
                                    <span style="display:inline-block;background-color:#2e7d32;color:#fff;padding:6px 16px;border-radius:20px;font-size:14px;font-weight:700;">{exitosas}/{total} creadas</span>
                                    {errores_html}
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>'''
    if filas_tabla_html:
        seccion += f'''
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
    return seccion


def _build_pedido_html_row(pedido_numero):
    if not pedido_numero:
        return ""
    return f'''
                            <tr>
                                <td style="padding:8px 0;color:#7f8c8d;font-size:13px;width:160px;">Pedido</td>
                                <td style="padding:8px 0;font-weight:600;color:#2c3e50;">{pedido_numero}</td>
                            </tr>'''


def _build_despacho_html_body(numero_oc_sap, doc_entry, proveedor, referencia, pedido_html, seccion_transferencias_html, fecha_ejecucion):
    return f"""<!DOCTYPE html>
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
                    <tr>
                        <td style="padding:32px 40px;">
                            <p style="margin:0 0 24px;color:#2c3e50;font-size:15px;line-height:1.6;">
                                Se ha generado exitosamente la <strong>Orden de Compra</strong> y las
                                <strong>Solicitudes de Transferencia</strong> en SAP.
                                Pueden proceder con el despacho y facturaci&oacute;n.
                            </p>
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
                            {seccion_transferencias_html}
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


def _build_despacho_body_text(numero_oc_sap, doc_entry, proveedor, referencia, pedido_numero, solicitudes, exitosas, total, fallidas, detalle_texto, fecha_ejecucion):
    seccion_st = ""
    if solicitudes:
        errores_line = f"- Errores: {fallidas} solicitud(es) fallaron" if fallidas > 0 else ""
        seccion_st = f"""
Solicitudes de Transferencia Generadas:
- Total: {exitosas}/{total} creadas exitosamente
{errores_line}"""
        if detalle_texto:
            seccion_st += f"""

Detalle de Solicitudes de Transferencia:
  Tienda\tNombre\tEstado\tDocNum
{detalle_texto}"""
    pedido_line = f"- Numero de Pedido: {pedido_numero}" if pedido_numero else ""
    return f"""OC y Solicitudes de Transferencia Generadas
{'=' * 50}

Se ha generado exitosamente la Orden de Compra y las Solicitudes de Transferencia en SAP.
Pueden proceder con el despacho y facturacion.

Informacion de la Orden de Compra:
- Numero OC SAP: {numero_oc_sap}
- DocEntry: {doc_entry or 'N/A'}
- Proveedor: {proveedor}
- Referencia: {referencia}
{pedido_line}
{seccion_st}

Accion Requerida:
El personal de El Rayo puede proceder con:
- Despacho de mercaderia
- Facturacion correspondiente

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
Mensaje automatico del sistema de integracion SAP - Mabel Trading
"""


def _extract_errores_st(solicitudes_transferencia):
    """Extrae totales y lista de errores de solicitudes de transferencia."""
    if not solicitudes_transferencia:
        return 0, 0, 0, []
    total = solicitudes_transferencia.get("total_tiendas", 0)
    exitosas = solicitudes_transferencia.get("transferencias_creadas", 0)
    fallidas = solicitudes_transferencia.get("transferencias_errores", 0)
    errores = []
    if solicitudes_transferencia.get("error"):
        errores.append(str(solicitudes_transferencia.get("error")))
    for r in solicitudes_transferencia.get("resultados", []):
        if not r.get("success") and r.get("error"):
            tienda = r.get("tienda_codigo", "N/A")
            errores.append(f"{tienda}: {r.get('error')}")
    return total, exitosas, fallidas, errores


# ─── Constructores de HTML puros (sin I/O) ───────────────────────────────────
# Extraídos de cada send_*() para que la vista previa administrativa
# (notificacion_tipo_correo, endpoint /preview) pueda reconstruir el mismo
# HTML que se envía realmente, sin duplicar la lógica de composición. Cada
# send_*() sigue siendo quien resuelve destinatarios y hace el envío por SMTP.

def _build_migracion_email(facturas_guardadas, facturas_actualizadas, total_detalles, fecha_ejecucion):
    """Construye (subject, body_html) para 'Nuevos Registros Migrados' (OPERACIONES)."""
    from src.utils.email_template import build_email, info_section, paragraph

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
    subject = f"Nuevos Registros Migrados - {facturas_guardadas} factura(s) nueva(s)"
    return subject, body_html


def _build_error_migracion_email(error_message, fecha_ejecucion):
    """Construye (subject, body_html) para 'Error en Migración Automática' (TECNICOS)."""
    from src.utils.email_template import build_email, info_section, warning_section, paragraph

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
    subject = "Error en Migracion Automatica MBA3"
    return subject, body_html


def _build_homologacion_email(productos_a_notificar, estadisticas, fecha_ejecucion):
    """Construye (subject, body_html) para 'Productos NO Homologados Detectados' (HOMOLOGACIONES)."""
    from src.utils.email_template import (
        build_email, info_section, table_section, warning_section,
        paragraph, badge_html,
    )

    total_mba3, homologados, no_homologados, porcentaje = _get_estadisticas_homologacion(
        estadisticas, len(productos_a_notificar)
    )

    productos_no_existen = [p for p in productos_a_notificar if p.get("tipo_problema") == "no_existe"]
    productos_mismatch = [p for p in productos_a_notificar if p.get("tipo_problema") == "mismatch"]
    productos_error = [p for p in productos_a_notificar if p.get("tipo_problema") == "error"]
    productos_sin_tipo = [p for p in productos_a_notificar if not p.get("tipo_problema")]

    productos_mostrar = productos_a_notificar[:20]
    table_rows = _build_homologacion_table_rows(productos_mostrar, badge_html)
    footer_note = f"... y {len(productos_a_notificar) - 20} producto(s) m&aacute;s" if len(productos_a_notificar) > 20 else None
    resumen_items = _build_homologacion_resumen_items(
        productos_mismatch, productos_no_existen, productos_error, productos_sin_tipo, badge_html
    )

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
    subject = f"Productos NO Homologados Detectados - {len(productos_a_notificar)} producto(s) NUEVOS"
    return subject, body_html


def _build_capacity_warning_email(warning_type, details, fecha_ejecucion):
    """Construye (subject, body_html) para 'Advertencia de Capacidad' (TECNICOS)."""
    if warning_type == 'time_limit':
        titulo = "⚠️ Advertencia: Tiempo de Ejecución Alto"
        mensaje_principal = f"La migración está usando {details.get('porcentaje_usado', 0)}% del tiempo límite."
    elif warning_type == 'high_volume':
        titulo = "📊 Advertencia: Volumen Alto de Registros"
        mensaje_principal = f"Se detectaron {details.get('num_facturas', 0)} facturas (umbral: {details.get('umbral', 0)})."
    elif warning_type == 'high_failures':
        titulo = "🔴 Advertencia: Múltiples Fallos Detectados"
        mensaje_principal = f"Se detectaron {details.get('num_fallos', 0)} fallos en las últimas 24 horas."
    else:
        titulo = "⚠️ Advertencia del Sistema"
        mensaje_principal = "Se detectó una condición de advertencia."

    from src.utils.email_template import build_email, info_section, warning_section, paragraph

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
    return titulo, body_html


def _build_oc_proveedor_email(oc_cabecera, oc_detalles, doc_num, doc_entry, fecha_ejecucion):
    """Construye (subject, body_html) para 'Orden de Compra Generada' (proveedor / OPERACIONES)."""
    proveedor = oc_cabecera.get("proveedor", "N/A")
    numero_oc_sap = doc_num or oc_cabecera.get("numero_oc_sap", "N/A")
    referencia = oc_cabecera.get("referencia_despacho", "N/A")
    doc_entry_str = doc_entry or "N/A"

    from src.utils.email_template import build_email, info_section, table_section, paragraph

    total_lineas = len(oc_detalles)
    total_cantidad = sum(d.get("cantidad_sap", 0) for d in oc_detalles)
    total_valor = sum(d.get("total_linea", 0) or 0 for d in oc_detalles)

    detalles_mostrar = oc_detalles[:50]
    table_rows = []
    for idx, detalle in enumerate(detalles_mostrar, 1):
        sku = detalle.get("sku_sap", "N/A")
        nombre = detalle.get("nombre_producto", _DEFAULT_NOMBRE_PRODUCTO)
        cantidad = detalle.get("cantidad_sap", 0)
        unidad = detalle.get("unidad_sap", "N/A")
        precio_unit = detalle.get("precio_unitario", 0)
        total_linea = detalle.get("total_linea", 0)
        table_rows.append((
            str(idx), f"<strong>{sku}</strong>", nombre,
            f"{cantidad:.2f}", unidad, f"${precio_unit:.4f}", f"${total_linea:.4f}",
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
                ("DocEntry", doc_entry_str),
                ("Proveedor", proveedor),
                ("Referencia", referencia),
                ("Total L&iacute;neas", total_lineas),
                ("Total Cantidad", f"{total_cantidad:.2f}"),
                ("Total Valor", f"${total_valor:.4f}"),
            ], accent="green", highlight_first=True),
            table_section("Detalle de la Orden de Compra",
                ["#", "SKU", "Producto", "Cantidad", "Unidad", "P. Unit.", "Total"],
                table_rows, accent="green", footer_note=footer_note),
        ],
        accent="green",
        timestamp=fecha_ejecucion,
    )
    subject = f"Orden de Compra Generada - ODC #{numero_oc_sap}"
    return subject, body_html


def _build_despacho_email(oc_cabecera, doc_num, doc_entry, solicitudes_transferencia, pedido_numero, fecha_ejecucion):
    """Construye (subject, body_html) para 'OC y Solicitudes de Transferencia - Listo para Despacho'."""
    proveedor = oc_cabecera.get("proveedor", "N/A")
    numero_oc_sap = doc_num or oc_cabecera.get("numero_oc_sap", "N/A")
    referencia = oc_cabecera.get("referencia_despacho", "N/A")

    total, exitosas, fallidas, _detalle_texto = _extract_transferencias_data(solicitudes_transferencia)
    filas_tabla_html = _build_filas_tabla_despacho(solicitudes_transferencia)
    seccion_transferencias_html = _build_seccion_transferencias_despacho(
        solicitudes_transferencia, exitosas, total, fallidas, filas_tabla_html
    )
    pedido_html = _build_pedido_html_row(pedido_numero)

    body_html = _build_despacho_html_body(
        numero_oc_sap, doc_entry, proveedor, referencia,
        pedido_html, seccion_transferencias_html, fecha_ejecucion
    )
    subject = f"OC y Solicitudes de Transferencia - Listo para Despacho #{numero_oc_sap}"
    return subject, body_html


def _build_oc_st_error_email(oc_cabecera, doc_num, doc_entry, solicitudes_transferencia, pedido_numero, fecha_ejecucion):
    """Construye (subject, body_html) para 'Error en OC y Solicitudes de Transferencia' (TECNICOS)."""
    proveedor = oc_cabecera.get("proveedor", "N/A")
    numero_oc_sap = doc_num or oc_cabecera.get("numero_oc_sap", "N/A")
    referencia = oc_cabecera.get("referencia_despacho", "N/A")

    total_transferencias, transferencias_exitosas, transferencias_fallidas, errores = _extract_errores_st(solicitudes_transferencia)

    from src.utils.email_template import build_email, info_section, warning_section, paragraph

    error_html = "<br>".join(errores[:15]) if errores else "Sin detalle adicional"
    body_html = build_email(
        title="Error en OC y Solicitudes de Transferencia",
        subtitle=f"Revisión técnica requerida - ODC #{numero_oc_sap}",
        sections=[
            paragraph("Se detectó un error durante la generación/procesamiento de la Orden de Compra y/o Solicitudes de Transferencia en SAP."),
            info_section("Información de la ODC", [
                ("Número OC SAP", numero_oc_sap),
                ("DocEntry", doc_entry or "N/A"),
                ("Proveedor", proveedor),
                ("Referencia", referencia),
                ("Pedido", pedido_numero or "N/A"),
                ("Solicitudes de Transferencia", f"{transferencias_exitosas}/{total_transferencias} creadas"),
                ("Transferencias con Error", transferencias_fallidas),
            ], accent="red", highlight_first=True),
            warning_section("Detalle del Error", f"<p style='margin:0;color:#5d4037;font-size:14px;line-height:1.6;'>{error_html}</p>"),
        ],
        accent="red",
        timestamp=fecha_ejecucion,
    )
    subject = f"Error en OC y Solicitudes de Transferencia - ODC #{numero_oc_sap}"
    return subject, body_html


def _build_plantilla_email(pedido_id, numero_pedido, filename, usuario_id, articulos_cargados, distribuciones_cargadas, formato_detectado, fecha_ejecucion):
    """Construye (subject, body_html) para 'Plantilla Excel Procesada' (PRODUCCION_ELRAYO)."""
    num_pedido_val = numero_pedido or "N/A"
    pedido_id_val = pedido_id or "N/A"
    filename_val = filename or "N/A"
    usuario_val = usuario_id or "N/A"
    formato_val = formato_detectado or "N/A"

    from src.utils.email_template import build_email, info_section, paragraph

    body_html = build_email(
        title="Plantilla Excel Procesada Exitosamente",
        subtitle=f"Pedido: {num_pedido_val}",
        sections=[
            paragraph("Se ha procesado y guardado exitosamente una plantilla Excel de pedido."),
            info_section(_SECCION_INFO_PEDIDO, [
                (_LABEL_NUMERO_PEDIDO, num_pedido_val),
                (_LABEL_PEDIDO_ID, pedido_id_val),
                ("Archivo", filename_val),
                ("Usuario", usuario_val),
                ("Formato", formato_val),
                ("Art&iacute;culos Cargados", articulos_cargados),
                ("Distribuciones Cargadas", distribuciones_cargadas),
            ], accent="green"),
        ],
        accent="green",
        timestamp=fecha_ejecucion,
    )
    subject = f"Plantilla Excel Procesada - {num_pedido_val}"
    return subject, body_html


def _build_pedido_cancelado_email(pedido_id, numero_pedido, usuario_id, fecha_ejecucion):
    """Construye (subject, body_html) para 'Pedido Cancelado' (OPERACIONES)."""
    from src.utils.email_template import build_email, info_section, paragraph, badge_html

    body_html = build_email(
        title="Pedido Cancelado",
        subtitle=f"Pedido: {numero_pedido or pedido_id}",
        sections=[
            paragraph(f"Se ha cancelado un pedido. El estado ha cambiado a {badge_html('CANCELADO', '#ffebee', '#c62828')}."),
            info_section(_SECCION_INFO_PEDIDO, [
                (_LABEL_NUMERO_PEDIDO, numero_pedido or "N/A"),
                (_LABEL_PEDIDO_ID, pedido_id),
                ("Usuario que cancel&oacute;", usuario_id or "N/A"),
                ("Nuevo Estado", badge_html("CANCELADO", "#ffebee", "#c62828")),
            ], accent="red"),
            paragraph("El pedido permanece en el sistema con estado CANCELADO y no ser&aacute; procesado.", italic=True),
        ],
        accent="red",
        timestamp=fecha_ejecucion,
    )
    subject = f"Pedido Cancelado - {numero_pedido or pedido_id}"
    return subject, body_html


def _build_pedido_confirmado_produccion_email(pedido_id, numero_pedido, usuario_id, fecha_ejecucion):
    """Construye (subject, body_html) para 'Pedido Confirmado por Producción' (OPERACIONES, req. 1.8)."""
    from src.utils.email_template import build_email, info_section, paragraph, badge_html

    body_html = build_email(
        title="Pedido Confirmado por Producción",
        subtitle=f"Pedido: {numero_pedido or pedido_id}",
        sections=[
            paragraph(f"Producción confirmó este pedido. El estado ha cambiado a {badge_html('CONFIRMADO POR PRODUCCION', '#fff8e1', '#8a6d00')}."),
            info_section(_SECCION_INFO_PEDIDO, [
                (_LABEL_NUMERO_PEDIDO, numero_pedido or "N/A"),
                (_LABEL_PEDIDO_ID, pedido_id),
                ("Usuario de Producci&oacute;n", usuario_id or "N/A"),
                ("Nuevo Estado", badge_html("CONFIRMADO POR PRODUCCION", "#fff8e1", "#8a6d00")),
            ], accent="orange"),
            paragraph("Queda pendiente de revisi&oacute;n y confirmaci&oacute;n por Administraci&oacute;n El Rayo.", italic=True),
        ],
        accent="orange",
        timestamp=fecha_ejecucion,
    )
    subject = f"Pedido Confirmado por Producción - {numero_pedido or pedido_id}"
    return subject, body_html


def _build_pedido_descartado_email(pedido_id, numero_pedido, usuario_id, fecha_ejecucion):
    """Construye (subject, body_html) para 'Pedido Descartado' (OPERACIONES)."""
    from src.utils.email_template import build_email, info_section, paragraph

    body_html = build_email(
        title="Pedido Descartado",
        subtitle=f"Pedido: {numero_pedido or pedido_id}",
        sections=[
            paragraph("Se ha descartado y eliminado un pedido completamente de la base de datos."),
            info_section(_SECCION_INFO_PEDIDO, [
                (_LABEL_NUMERO_PEDIDO, numero_pedido or "N/A"),
                (_LABEL_PEDIDO_ID, pedido_id),
                ("Usuario que descart&oacute;", usuario_id or "N/A"),
            ], accent="red"),
            paragraph("El pedido ya no est&aacute; disponible en el sistema. Podr&aacute;n volver a cargarlo desde cero si lo necesitan.", italic=True),
        ],
        accent="red",
        timestamp=fecha_ejecucion,
    )
    subject = f"Pedido Descartado - {numero_pedido or pedido_id}"
    return subject, body_html


def _build_redistribucion_confirmada_email(pedido_id, numero_pedido, usuario_mabel, version_confirmada, total_productos, total_cantidad_ajustada, fecha_ejecucion):
    """Construye (subject, body_html) para 'Redistribución Confirmada por MABEL TRADING' (OPERACIONES)."""
    import os
    base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    numero_pedido_encoded = numero_pedido.replace(" ", "%20")
    url_pedido = f"{base_url}/mba3-consultas/pedidos/{numero_pedido_encoded}"

    from src.utils.email_template import (
        build_email, info_section, success_badge_section,
        button_section, paragraph, badge_html,
    )

    info_items = [
        (_LABEL_NUMERO_PEDIDO, numero_pedido),
        (_LABEL_PEDIDO_ID, pedido_id),
    ]
    if usuario_mabel:
        info_items.append(("Usuario MABEL TRADING", usuario_mabel))
    if version_confirmada:
        info_items.append(("Versi&oacute;n Confirmada", str(version_confirmada)))
    info_items.extend([
        ("Total Productos Redistribuidos", str(total_productos)),
        ("Total Cantidad Ajustada", str(total_cantidad_ajustada)),
        ("Estado", badge_html("CONFIRMADO REDISTRIBUCION", "#e8f5e9", "#2e7d32")),
    ])

    body_html = build_email(
        title="Redistribuci&oacute;n Confirmada por MABEL TRADING",
        subtitle=f"Pedido: {numero_pedido}",
        sections=[
            success_badge_section("MABEL TRADING ha confirmado la redistribuci&oacute;n exitosamente"),
            paragraph("Se ha procesado la confirmaci&oacute;n de la redistribuci&oacute;n del pedido y est&aacute; listo para continuar."),
            info_section(_SECCION_INFO_PEDIDO, info_items, accent="blue"),
            button_section("Ver Pedido", url_pedido, accent="blue"),
            paragraph("El pedido est&aacute; ahora listo para la generaci&oacute;n de orden de compra (ODC).", italic=True),
        ],
        accent="blue",
        timestamp=fecha_ejecucion,
    )
    subject = f"Redistribucion Confirmada por MABEL TRADING - {numero_pedido}"
    return subject, body_html


def _build_pedido_eliminado_email(pedido_id, numero_pedido, usuario_id, fecha_ejecucion):
    """Construye (subject, body_html) para 'Pedido Eliminado' (MABEL_TRADING)."""
    from src.utils.email_template import build_email, info_section, warning_section, paragraph

    body_html = build_email(
        title="Pedido Eliminado Exitosamente",
        subtitle=f"Pedido: {numero_pedido or pedido_id}",
        sections=[
            paragraph("Se ha eliminado un pedido desde la interfaz de Detalle del Pedido."),
            info_section("Informaci&oacute;n del Pedido Eliminado", [
                (_LABEL_NUMERO_PEDIDO, numero_pedido or "N/A"),
                (_LABEL_PEDIDO_ID, pedido_id),
                ("Usuario que elimin&oacute;", usuario_id or "N/A"),
                ("Estado al eliminar", "Gestionar Pedido"),
            ], accent="green"),
            warning_section("Nota Importante",
                '<p style="margin:0;color:#5d4037;font-size:14px;">Esta es una operaci&oacute;n irreversible. Si necesita crear el pedido nuevamente, deber&aacute; cargarlo desde cero.</p>'),
        ],
        accent="green",
        timestamp=fecha_ejecucion,
    )
    subject = f"Pedido Eliminado - {numero_pedido or pedido_id}"
    return subject, body_html


# ─── Funciones públicas ───────────────────────────────────────────────────────

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
        logger.debug(_MSG_EMAIL_DESHABILITADO)
        return False

    # Solo enviar email si hay nuevos registros
    if facturas_guardadas == 0:
        logger.debug("⏭️ No hay nuevos registros, no se envía email")
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        recipients: list[str] = get_destinatarios_por_correo("OPERACIONES", _CORREO_MIGRACION)

        if not recipients:
            logger.warning("⚠️ No hay destinatarios de OPERACIONES configurados")
            return False

        from src.utils.email_template import create_email_message

        subject, body_html = _build_migracion_email(
            facturas_guardadas, facturas_actualizadas, total_detalles, fecha_ejecucion
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
            subject=subject,
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        send_smtp_message(msg, recipients)

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
        fecha_ejecucion = ahora_naive()

    try:
        recipients: list[str] = get_destinatarios_por_correo("TECNICOS", _CORREO_ERROR_MIGRACION)

        if not recipients:
            logger.warning("⚠️ No hay destinatarios TÉCNICOS configurados")
            return False

        from src.utils.email_template import create_email_message

        subject, body_html = _build_error_migracion_email(error_message, fecha_ejecucion)

        body_text = f"""Error en Migracion Automatica
{'=' * 40}

Se ha producido un error durante la migracion automatica desde MBA3.

Detalles del Error:
{error_message}

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
Por favor, revisa los logs del sistema para mas informacion.
"""

        msg = create_email_message(
            subject=subject,
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        send_smtp_message(msg, recipients)

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
        logger.debug(_MSG_EMAIL_DESHABILITADO)
        return False

    if not productos_no_homologados:
        logger.debug("⏭️ No hay productos no homologados, no se envía email")
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    productos_a_notificar = _filtrar_productos_a_notificar(
        productos_no_homologados, filtrar_ya_notificados, homologacion_repository
    )
    if not productos_a_notificar:
        return False

    try:
        recipients: list[str] = get_destinatarios_por_correo("HOMOLOGACIONES", _CORREO_HOMOLOGACION)

        if not recipients:
            logger.warning("⚠️ No hay destinatarios de HOMOLOGACIONES configurados")
            return False

        from src.utils.email_template import create_email_message

        subject, body_html = _build_homologacion_email(productos_a_notificar, estadisticas, fecha_ejecucion)

        total_mba3, homologados, no_homologados, porcentaje = _get_estadisticas_homologacion(
            estadisticas, len(productos_a_notificar)
        )
        productos_mostrar = productos_a_notificar[:20]

        body_text = _build_homologacion_body_text(
            productos_mostrar, productos_a_notificar,
            total_mba3, homologados, no_homologados, porcentaje, fecha_ejecucion
        )

        csv_attachments = _build_homologacion_csv(productos_a_notificar, fecha_ejecucion)

        msg = create_email_message(
            subject=subject,
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
            attachments=csv_attachments if csv_attachments else None,
        )

        send_smtp_message(msg, recipients)

        logger.info(f"✅ Email de homologación enviado a {', '.join(recipients)}")
        logger.info(f"   Productos no homologados reportados: {len(productos_a_notificar)}")

        _registrar_notificados(homologacion_repository, productos_a_notificar)

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
        fecha_ejecucion = ahora_naive()

    try:
        recipients: list[str] = get_destinatarios_por_correo("TECNICOS", _CORREO_CAPACITY_WARNING)

        if not recipients:
            logger.warning("⚠️ No hay destinatarios TÉCNICOS configurados")
            return False

        # Determinar título y mensaje según el tipo
        if warning_type == 'time_limit':
            titulo = "⚠️ Advertencia: Tiempo de Ejecución Alto"
            mensaje_principal = f"La migración está usando {details.get('porcentaje_usado', 0)}% del tiempo límite."
        elif warning_type == 'high_volume':
            titulo = "📊 Advertencia: Volumen Alto de Registros"
            mensaje_principal = f"Se detectaron {details.get('num_facturas', 0)} facturas (umbral: {details.get('umbral', 0)})."
        elif warning_type == 'high_failures':
            titulo = "🔴 Advertencia: Múltiples Fallos Detectados"
            mensaje_principal = f"Se detectaron {details.get('num_fallos', 0)} fallos en las últimas 24 horas."
        else:
            titulo = "⚠️ Advertencia del Sistema"
            mensaje_principal = "Se detectó una condición de advertencia."

        from src.utils.email_template import create_email_message

        subject, body_html = _build_capacity_warning_email(warning_type, details, fecha_ejecucion)

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
            subject=subject,
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        send_smtp_message(msg, recipients)

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
        logger.debug(_MSG_EMAIL_DESHABILITADO)
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        if proveedor_email:
            recipients: list[str] = [proveedor_email.strip()]
        else:
            recipients = get_destinatarios_por_correo("OPERACIONES", _CORREO_OC_PROVEEDOR)
            logger.warning(f"⚠️ No se proporcionó email del proveedor, enviando a operaciones: {recipients}")

        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados")
            return False

        proveedor = oc_cabecera.get("proveedor", "N/A")
        numero_oc_sap = doc_num or oc_cabecera.get("numero_oc_sap", "N/A")
        referencia = oc_cabecera.get("referencia_despacho", "N/A")
        doc_entry_str = doc_entry or "N/A"

        from src.utils.email_template import create_email_message

        total_lineas = len(oc_detalles)
        total_cantidad = sum(d.get("cantidad_sap", 0) for d in oc_detalles)
        total_valor = sum(d.get("total_linea", 0) or 0 for d in oc_detalles)

        detalles_mostrar = oc_detalles[:50]

        subject, body_html = _build_oc_proveedor_email(oc_cabecera, oc_detalles, doc_num, doc_entry, fecha_ejecucion)

        body_text = f"""Orden de Compra Generada - ODC #{numero_oc_sap}
{'=' * 40}

Adjunto: ODC {numero_oc_sap}.pdf

Informacion de la ODC:
- Numero ODC SAP: {numero_oc_sap}
- DocEntry: {doc_entry_str}
- Proveedor: {proveedor}
- Referencia: {referencia}
- Total Lineas: {total_lineas}
- Total Cantidad: {total_cantidad:.2f}
- Total Valor: ${total_valor:.4f}

Detalle:
"""
        for idx, detalle in enumerate(detalles_mostrar, 1):
            sku = detalle.get("sku_sap", "N/A")
            nombre = detalle.get("nombre_producto", _DEFAULT_NOMBRE_PRODUCTO)
            cantidad = detalle.get("cantidad_sap", 0)
            unidad = detalle.get("unidad_sap", "N/A")
            precio_unit = detalle.get("precio_unitario", 0)
            total_linea = detalle.get("total_linea", 0)
            body_text += f"  {idx}. {sku} - {nombre} | {cantidad:.2f} {unidad} | ${precio_unit:.4f} | ${total_linea:.4f}\n"

        if len(oc_detalles) > 50:
            body_text += f"  ... y {len(oc_detalles) - 50} linea(s) mas\n"
        body_text += f"\nFecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}\n"

        pdf_attachment = _generate_odc_pdf_attachment(
            oc_cabecera, oc_detalles, doc_num, numero_oc_sap, pedido_info
        )

        msg = create_email_message(
            subject=subject,
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
            attachments=[pdf_attachment] if pdf_attachment else None,
        )

        send_smtp_message(msg, recipients)

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
    Envía notificación a El Rayo y a MABEL TRADING indicando que la OC y Solicitudes de Transferencia
    han sido generadas en SAP y pueden proceder con despacho y facturación.

    HU-04: Alertar al personal de El Rayo para proceder con el despacho y facturación

    DESTINATARIOS: OPERACIONES (El Rayo) + MABEL_TRADING

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
        logger.debug(_MSG_EMAIL_DESHABILITADO)
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        recipients = _build_unique_recipients(["OPERACIONES", "MABEL_TRADING"], _CORREO_DESPACHO)

        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados para notificación de despacho (OPERACIONES ni MABEL_TRADING)")
            return False

        proveedor = oc_cabecera.get("proveedor", "N/A")
        numero_oc_sap = doc_num or oc_cabecera.get("numero_oc_sap", "N/A")
        referencia = oc_cabecera.get("referencia_despacho", "N/A")

        total, exitosas, fallidas, detalle_texto = _extract_transferencias_data(solicitudes_transferencia)

        subject, body_html = _build_despacho_email(
            oc_cabecera, doc_num, doc_entry, solicitudes_transferencia, pedido_numero, fecha_ejecucion
        )
        body_text = _build_despacho_body_text(
            numero_oc_sap, doc_entry, proveedor, referencia, pedido_numero,
            solicitudes_transferencia, exitosas, total, fallidas, detalle_texto, fecha_ejecucion
        )

        # multipart/alternative para que el cliente prefiera HTML
        msg = MIMEMultipart('alternative')
        msg['From'] = EMAIL_SMTP_USER or EMAIL_FROM
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
        msg.attach(MIMEText(body_html, 'html', 'utf-8'))

        send_smtp_message(msg, recipients)

        logger.info(f"✅ Notificación de OC lista para despacho enviada a {', '.join(recipients)} (OC #{numero_oc_sap})")
        return True

    except Exception as e:
        logger.error(f"❌ Error al enviar notificación de OC lista para despacho: {e}", exc_info=True)
        return False


def send_oc_st_error_notification_tecnicos(
    oc_cabecera: Dict[str, Any],
    doc_num: Optional[int] = None,
    doc_entry: Optional[int] = None,
    solicitudes_transferencia: Optional[Dict[str, Any]] = None,
    pedido_numero: Optional[str] = None,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía notificación al USUARIO TÉCNICO cuando hay errores en OC/Solicitudes de Transferencia.

    DESTINATARIO: TECNICOS
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        logger.debug(_MSG_EMAIL_DESHABILITADO)
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        recipients: list[str] = get_destinatarios_por_correo("TECNICOS", _CORREO_OC_ST_ERROR)
        if not recipients:
            logger.warning("⚠️ No hay destinatarios TÉCNICOS configurados para error de ODC/ST")
            return False

        proveedor = oc_cabecera.get("proveedor", "N/A")
        numero_oc_sap = doc_num or oc_cabecera.get("numero_oc_sap", "N/A")
        referencia = oc_cabecera.get("referencia_despacho", "N/A")

        total_transferencias, transferencias_exitosas, transferencias_fallidas, errores = _extract_errores_st(solicitudes_transferencia)

        from src.utils.email_template import create_email_message

        subject, body_html = _build_oc_st_error_email(
            oc_cabecera, doc_num, doc_entry, solicitudes_transferencia, pedido_numero, fecha_ejecucion
        )

        errores_detalle = "\n- ".join(errores[:15]) if errores else "Sin detalle adicional"
        body_text = (
            f"Error en OC y Solicitudes de Transferencia\n"
            f"{'=' * 50}\n\n"
            f"ODC SAP: {numero_oc_sap}\n"
            f"DocEntry: {doc_entry or 'N/A'}\n"
            f"Proveedor: {proveedor}\n"
            f"Referencia: {referencia}\n"
            f"Pedido: {pedido_numero or 'N/A'}\n"
            f"Solicitudes creadas: {transferencias_exitosas}/{total_transferencias}\n"
            f"Transferencias con error: {transferencias_fallidas}\n\n"
            f"Detalle:\n- {errores_detalle}\n\n"
            f"Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Mensaje automático del sistema de integración SAP - Mabel Trading\n"
        )

        msg = create_email_message(
            subject=subject,
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        send_smtp_message(msg, recipients)

        logger.info(f"✅ Notificación de error ODC/ST enviada a técnicos: {', '.join(recipients)}")
        return True

    except Exception as e:
        logger.error(f"❌ Error al enviar notificación de error ODC/ST a técnicos: {e}", exc_info=True)
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
    Envía notificación a Producción El Rayo cuando MABEL TRADING envía un pedido
    (clic en "Enviar" desde cargar-plantilla, o subida de plantilla exitosa).

    DESTINATARIO: EMAIL_TO_PRODUCCION_ELRAYO (req. 1.8; antes iba a EMAIL_TO_OPERACIONES/
    Administración El Rayo, que ya no recibe este correo).

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
        logger.debug(_MSG_EMAIL_DESHABILITADO)
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        recipients: list[str] = get_destinatarios_por_correo("PRODUCCION_ELRAYO", _CORREO_PLANTILLA)

        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados para notificación de plantilla (PRODUCCION_ELRAYO)")
            return False

        num_pedido_val = numero_pedido or "N/A"
        pedido_id_val = pedido_id or "N/A"
        filename_val = filename or "N/A"
        usuario_val = usuario_id or "N/A"
        formato_val = formato_detectado or "N/A"

        from src.utils.email_template import create_email_message

        subject, body_html = _build_plantilla_email(
            pedido_id, numero_pedido, filename, usuario_id,
            articulos_cargados, distribuciones_cargadas, formato_detectado, fecha_ejecucion
        )

        body_text = f"""Plantilla Excel Procesada Exitosamente
{'=' * 40}

Informacion del Pedido:
- Numero de Pedido: {num_pedido_val}
- Pedido ID: {pedido_id_val}
- Archivo: {filename_val}
- Usuario: {usuario_val}
- Formato: {formato_val}
- Articulos Cargados: {articulos_cargados}
- Distribuciones Cargadas: {distribuciones_cargadas}

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
"""

        msg = create_email_message(
            subject=subject,
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        send_smtp_message(msg, recipients)

        logger.info(f"✅ Notificación de plantilla procesada enviada a {', '.join(recipients)} (Pedido: {num_pedido_val})")
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
        logger.debug(_MSG_EMAIL_DESHABILITADO)
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        recipients: list[str] = get_destinatarios_por_correo("OPERACIONES", _CORREO_PEDIDO_CANCELADO)

        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados para notificación de pedido descartado")
            return False

        from src.utils.email_template import create_email_message

        subject, body_html = _build_pedido_cancelado_email(pedido_id, numero_pedido, usuario_id, fecha_ejecucion)

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
            subject=subject,
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        send_smtp_message(msg, recipients)

        logger.info(f"✅ Notificación de pedido cancelado enviada a {', '.join(recipients)} (Pedido: {numero_pedido or pedido_id})")
        return True

    except Exception as e:
        logger.error(f"❌ Error al enviar notificación de pedido cancelado: {e}", exc_info=True)
        return False


def send_pedido_confirmado_produccion_notification(
    pedido_id: str,
    numero_pedido: Optional[str] = None,
    usuario_id: Optional[str] = None,
    fecha_ejecucion: Optional[datetime] = None
) -> bool:
    """
    Envía notificación a Administración El Rayo cuando Producción confirma un pedido
    (cambia estado a CONFIRMADO POR PRODUCCION).

    Se usa al procesar POST /api/pedidos/{pedido_id}/confirmar-produccion (req. 1.8,
    perfil Producción El Rayo, botón "Confirmar Producción").
    DESTINATARIO: EMAIL_TO_OPERACIONES (Administración El Rayo)

    Args:
        pedido_id: UUID del pedido confirmado
        numero_pedido: Número del pedido (opcional, para identificación)
        usuario_id: Usuario de Producción que confirmó el pedido
        fecha_ejecucion: Fecha y hora de la confirmación (por defecto ahora)

    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        logger.debug(_MSG_EMAIL_DESHABILITADO)
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        recipients: list[str] = get_destinatarios_por_correo("OPERACIONES", _CORREO_PEDIDO_CONFIRMADO_PRODUCCION)

        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados para notificación de pedido confirmado por producción")
            return False

        from src.utils.email_template import create_email_message

        subject, body_html = _build_pedido_confirmado_produccion_email(pedido_id, numero_pedido, usuario_id, fecha_ejecucion)

        body_text = f"""Pedido Confirmado por Producción - {numero_pedido or pedido_id}
{'=' * 40}

- Numero de Pedido: {numero_pedido or 'N/A'}
- Pedido ID: {pedido_id}
- Usuario de Produccion: {usuario_id or 'N/A'}
- Fecha y hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
- Nuevo Estado: CONFIRMADO POR PRODUCCION

Queda pendiente de revision y confirmacion por Administracion El Rayo.
"""

        msg = create_email_message(
            subject=subject,
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        send_smtp_message(msg, recipients)

        logger.info(f"✅ Notificación de pedido confirmado por producción enviada a {', '.join(recipients)} (Pedido: {numero_pedido or pedido_id})")
        return True

    except Exception as e:
        logger.error(f"❌ Error al enviar notificación de pedido confirmado por producción: {e}", exc_info=True)
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
        logger.debug(_MSG_EMAIL_DESHABILITADO)
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        recipients: list[str] = get_destinatarios_por_correo("OPERACIONES", _CORREO_PEDIDO_DESCARTADO)

        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados para notificación de pedido descartado")
            return False

        from src.utils.email_template import create_email_message

        subject, body_html = _build_pedido_descartado_email(pedido_id, numero_pedido, usuario_id, fecha_ejecucion)

        body_text = f"""Pedido Descartado - {numero_pedido or pedido_id}
{'=' * 40}

- Numero de Pedido: {numero_pedido or 'N/A'}
- Pedido ID: {pedido_id}
- Usuario que descarto: {usuario_id or 'N/A'}
- Fecha y hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}

El pedido ya no esta disponible en el sistema.
"""

        msg = create_email_message(
            subject=subject,
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        send_smtp_message(msg, recipients)

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
        logger.debug(_MSG_EMAIL_DESHABILITADO)
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        recipients: list[str] = get_destinatarios_por_correo("OPERACIONES", _CORREO_REDISTRIBUCION_CONFIRMADA)

        if not recipients:
            logger.warning("⚠️ No hay destinatarios configurados para notificación de redistribución")
            return False

        import os
        base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        numero_pedido_encoded = numero_pedido.replace(" ", "%20")
        url_pedido = f"{base_url}/mba3-consultas/pedidos/{numero_pedido_encoded}"

        from src.utils.email_template import create_email_message

        subject, body_html = _build_redistribucion_confirmada_email(
            pedido_id, numero_pedido, usuario_mabel, version_confirmada,
            total_productos, total_cantidad_ajustada, fecha_ejecucion
        )

        usuario_line = f"- Usuario MABEL TRADING: {usuario_mabel}" if usuario_mabel else ""
        version_line = f"- Version Confirmada: {version_confirmada}" if version_confirmada else ""
        body_text = f"""Redistribucion Confirmada por MABEL TRADING
{'=' * 40}

Informacion del Pedido:
- Numero de Pedido: {numero_pedido}
- Pedido ID: {pedido_id}
{usuario_line}
{version_line}
- Total Productos: {total_productos}
- Total Cantidad Ajustada: {total_cantidad_ajustada}
- Estado: CONFIRMADO REDISTRIBUCION

Ver Pedido: {url_pedido}

Fecha y Hora: {fecha_ejecucion.strftime('%Y-%m-%d %H:%M:%S')}
"""

        msg = create_email_message(
            subject=subject,
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        send_smtp_message(msg, recipients)

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
        logger.debug(_MSG_EMAIL_DESHABILITADO)
        return False

    if not fecha_ejecucion:
        fecha_ejecucion = ahora_naive()

    try:
        recipients: list[str] = get_destinatarios_por_correo("MABEL_TRADING", _CORREO_PEDIDO_ELIMINADO)

        if not recipients:
            logger.warning("⚠️ No hay destinatarios de MABEL TRADING configurados")
            return False

        from src.utils.email_template import create_email_message

        subject, body_html = _build_pedido_eliminado_email(pedido_id, numero_pedido, usuario_id, fecha_ejecucion)

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
            subject=subject,
            recipients=recipients,
            body_html=body_html,
            body_text=body_text,
        )

        send_smtp_message(msg, recipients)

        logger.info(f"✅ Notificación de pedido eliminado enviada a MABEL TRADING {', '.join(recipients)} (Pedido: {numero_pedido or pedido_id})")
        return True

    except Exception as e:
        logger.error(f"❌ Error al enviar notificación de pedido eliminado a MABEL TRADING: {e}", exc_info=True)
        return False
