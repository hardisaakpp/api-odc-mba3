"""
Plantilla HTML reutilizable para todos los correos del sistema.

Genera emails con diseño profesional usando inline styles para máxima
compatibilidad con clientes de correo (Outlook, Gmail, etc.).

Uso:
    from src.utils.email_template import build_email, send_email

    html, text = build_email(
        title="Titulo del correo",
        subtitle="Subtitulo opcional",
        sections=[
            info_section("Info", [("Campo", "Valor"), ...]),
            table_section("Detalle", ["Col1", "Col2"], [("A", "B"), ...]),
            warning_section("Accion", "Texto de accion"),
        ],
        accent="blue",
        timestamp=ahora_naive(),
    )
"""

import logging
from datetime import datetime

from src.utils.timezone import ahora_naive
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Tuple, Optional, Any

from src.config import (
    EMAIL_SMTP_USER,
    EMAIL_FROM,
    EMAIL_FROM_NAME,
)
from src.utils.smtp_sender import send_smtp_message

logger = logging.getLogger(__name__)

# ─── Paleta de colores ────────────────────────────────────────────────────────
ACCENTS = {
    "blue":   {"grad1": "#1a5276", "grad2": "#2980b9", "border": "#2980b9", "light": "#eaf2f8"},
    "green":  {"grad1": "#1b5e20", "grad2": "#388e3c", "border": "#2e7d32", "light": "#e8f5e9"},
    "red":    {"grad1": "#b71c1c", "grad2": "#c62828", "border": "#c62828", "light": "#ffebee"},
    "orange": {"grad1": "#e65100", "grad2": "#f57c00", "border": "#f57c00", "light": "#fff3e0"},
    "purple": {"grad1": "#4a148c", "grad2": "#7c3aed", "border": "#7c3aed", "light": "#f3e5f5"},
}


# ─── Secciones HTML ──────────────────────────────────────────────────────────

def info_section(
    title: str,
    items: List[Tuple[str, Any]],
    accent: str = "blue",
    highlight_first: bool = False,
) -> str:
    """Crea una tarjeta informativa con pares etiqueta/valor.

    Args:
        title: Titulo de la seccion.
        items: Lista de tuplas (etiqueta, valor).
        accent: Color de acento (blue, green, red, orange, purple).
        highlight_first: Si True, el primer valor se muestra mas grande.
    """
    c = ACCENTS.get(accent, ACCENTS["blue"])
    rows = ""
    for idx, (label, value) in enumerate(items):
        val_style = "font-weight:700;color:#1a5276;font-size:18px;" if (highlight_first and idx == 0) else "font-weight:600;color:#2c3e50;"
        rows += f'''<tr>
            <td style="padding:8px 0;color:#7f8c8d;font-size:13px;width:180px;">{label}</td>
            <td style="padding:8px 0;{val_style}">{value}</td>
        </tr>'''
    return f'''
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
        <tr><td style="background-color:#f8f9fa;border-radius:8px;padding:20px 24px;border-left:4px solid {c['border']};">
            <h3 style="margin:0 0 12px;color:{c['grad1']};font-size:15px;font-weight:700;">{title}</h3>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                {rows}
            </table>
        </td></tr>
    </table>'''


def table_section(
    title: str,
    headers: List[str],
    rows: List[Tuple[Any, ...]],
    accent: str = "blue",
    footer_note: Optional[str] = None,
) -> str:
    """Crea una tabla estilizada.

    Args:
        title: Titulo sobre la tabla.
        headers: Lista de encabezados.
        rows: Lista de tuplas con valores de cada fila. Cada celda puede ser
              un str (se renderiza directo) o una tupla (html, align) donde
              align es 'left'|'center'|'right'.
        accent: Color de acento.
        footer_note: Nota opcional al pie de la tabla.
    """
    c = ACCENTS.get(accent, ACCENTS["blue"])
    th = "".join(
        f'<th style="padding:14px 16px;text-align:left;color:#fff;font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">{h}</th>'
        for h in headers
    )
    body = ""
    for ridx, row in enumerate(rows):
        bg = "#f8fffe" if ridx % 2 == 0 else "#ffffff"
        cells = ""
        for cell in row:
            if isinstance(cell, tuple):
                html_val, align = cell
                cells += f'<td style="padding:12px 16px;border-bottom:1px solid #e8e8e8;text-align:{align};">{html_val}</td>'
            else:
                cells += f'<td style="padding:12px 16px;border-bottom:1px solid #e8e8e8;">{cell}</td>'
        body += f'<tr style="background-color:{bg};">{cells}</tr>'

    if footer_note:
        body += f'<tr><td colspan="{len(headers)}" style="padding:12px 16px;text-align:center;font-style:italic;color:#7f8c8d;font-size:13px;">{footer_note}</td></tr>'

    return f'''
    <h3 style="margin:0 0 12px;color:{c['grad1']};font-size:15px;font-weight:700;">{title}</h3>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-radius:8px;overflow:hidden;border:1px solid #e0e0e0;margin-bottom:24px;">
        <thead><tr style="background:linear-gradient(135deg,{c['grad1']} 0%,{c['grad2']} 100%);">{th}</tr></thead>
        <tbody>{body}</tbody>
    </table>'''


def summary_section(
    label: str,
    value: str,
    accent: str = "green",
    extra_html: str = "",
) -> str:
    """Crea una barra de resumen (ej: 7/7 creadas)."""
    c = ACCENTS.get(accent, ACCENTS["green"])
    return f'''
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;">
        <tr><td style="background:{c['light']};border-radius:8px;padding:20px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td style="font-size:16px;font-weight:700;color:{c['grad1']};">{label}</td>
                    <td style="text-align:right;">
                        <span style="display:inline-block;background-color:{c['grad1']};color:#fff;padding:6px 16px;border-radius:20px;font-size:14px;font-weight:700;">{value}</span>
                        {extra_html}
                    </td>
                </tr>
            </table>
        </td></tr>
    </table>'''


def warning_section(title: str, content_html: str) -> str:
    """Crea una caja de advertencia / accion requerida amarilla."""
    return f'''
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;">
        <tr><td style="background-color:#fff8e1;border-radius:8px;padding:20px 24px;border-left:4px solid #f9a825;">
            <h3 style="margin:0 0 8px;color:#e65100;font-size:15px;font-weight:700;">{title}</h3>
            {content_html}
        </td></tr>
    </table>'''


def success_badge_section(text: str) -> str:
    """Crea un badge de exito centrado."""
    return f'''
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px;">
        <tr><td style="background-color:#e8f5e9;border-radius:8px;padding:14px 24px;text-align:center;">
            <span style="color:#2e7d32;font-weight:700;font-size:14px;">&#10003; {text}</span>
        </td></tr>
    </table>'''


def button_section(text: str, url: str, accent: str = "blue") -> str:
    """Crea un boton CTA con enlace y URL de fallback."""
    c = ACCENTS.get(accent, ACCENTS["blue"])
    return f'''
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;">
        <tr><td style="text-align:center;padding:8px 0;">
            <p style="margin:0 0 12px;color:#2c3e50;font-size:14px;">Puedes revisarlo en el siguiente enlace:</p>
            <a href="{url}" style="display:inline-block;background:linear-gradient(135deg,{c['grad1']} 0%,{c['grad2']} 100%);color:#ffffff;padding:12px 32px;border-radius:6px;text-decoration:none;font-weight:700;font-size:15px;">{text}</a>
        </td></tr>
        <tr><td style="text-align:center;padding:8px 0;">
            <p style="margin:0;color:#95a5a6;font-size:11px;">O copia este enlace: <span style="color:#7f8c8d;word-break:break-all;">{url}</span></p>
        </td></tr>
    </table>'''


def paragraph(text: str, bold: bool = False, italic: bool = False, color: str = "#2c3e50") -> str:
    """Crea un parrafo simple."""
    style = f"margin:0 0 16px;color:{color};font-size:15px;line-height:1.6;"
    if bold:
        style += "font-weight:700;"
    if italic:
        style += "font-style:italic;"
    return f'<p style="{style}">{text}</p>'


def badge_html(text: str, bg_color: str, text_color: str) -> str:
    """Crea un badge inline."""
    return f'<span style="display:inline-block;background-color:{bg_color};color:{text_color};padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">{text}</span>'


# ─── Constructor principal ────────────────────────────────────────────────────

def build_email(
    title: str,
    subtitle: Optional[str] = None,
    sections: Optional[List[str]] = None,
    accent: str = "blue",
    timestamp: Optional[datetime] = None,
) -> str:
    """Construye el HTML y texto plano del email.

    Args:
        title: Titulo principal del header.
        subtitle: Subtitulo bajo el titulo (opcional).
        sections: Lista de strings HTML generados por las funciones de seccion.
        accent: Color de acento para el header (blue, green, red, orange, purple).
        timestamp: Fecha/hora para el footer (default: ahora).

    Returns:
        Tupla (body_html, body_text_placeholder).
        El body_text se debe construir por separado en cada funcion.
    """
    c = ACCENTS.get(accent, ACCENTS["blue"])
    if timestamp is None:
        timestamp = ahora_naive()
    ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')

    subtitle_html = ""
    if subtitle:
        subtitle_html = f'<p style="margin:8px 0 0;color:rgba(255,255,255,0.85);font-size:14px;">{subtitle}</p>'

    content = "\n".join(sections or [])

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background-color:#f0f2f5;font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f0f2f5;padding:24px 0;">
        <tr><td align="center">
            <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
                <!-- Header -->
                <tr><td style="background:linear-gradient(135deg,{c['grad1']} 0%,{c['grad2']} 100%);padding:32px 40px;text-align:center;">
                    <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;letter-spacing:-0.3px;">{title}</h1>
                    {subtitle_html}
                </td></tr>
                <!-- Body -->
                <tr><td style="padding:32px 40px;">
                    {content}
                </td></tr>
                <!-- Footer -->
                <tr><td style="background-color:#f8f9fa;padding:20px 40px;text-align:center;border-top:1px solid #e8e8e8;">
                    <p style="margin:0;color:#95a5a6;font-size:12px;">Fecha y Hora: {ts_str}</p>
                    <p style="margin:4px 0 0;color:#bdc3c7;font-size:11px;">Mensaje autom&aacute;tico del sistema &mdash; Mabel Trading</p>
                </td></tr>
            </table>
        </td></tr>
    </table>
</body>
</html>"""
    return html


# ─── Envio de email ───────────────────────────────────────────────────────────

def create_email_message(
    subject: str,
    recipients: List[str],
    body_html: str,
    body_text: str,
    from_addr: Optional[str] = None,
    from_name: Optional[str] = None,
    attachments: Optional[List[Any]] = None,
) -> MIMEMultipart:
    """Crea un MIMEMultipart listo para enviar.

    Si hay attachments, usa mixed + alternative anidado.
    Si no hay, usa alternative directo.
    """
    _from = from_addr or EMAIL_SMTP_USER or EMAIL_FROM
    _from_display = f"{from_name or EMAIL_FROM_NAME} <{_from}>"

    if attachments:
        msg = MIMEMultipart('mixed')
        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText(body_text, 'plain', 'utf-8'))
        alt.attach(MIMEText(body_html, 'html', 'utf-8'))
        msg.attach(alt)
        for att in attachments:
            msg.attach(att)
    else:
        msg = MIMEMultipart('alternative')
        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
        msg.attach(MIMEText(body_html, 'html', 'utf-8'))

    msg['From'] = _from_display
    msg['To'] = ", ".join(recipients)
    msg['Subject'] = subject
    return msg


def send_email(msg: MIMEMultipart, recipients: List[str]) -> bool:
    """Envia el mensaje via SMTP."""
    try:
        return send_smtp_message(msg, recipients)
    except Exception as e:
        logger.error(f"Error SMTP al enviar email: {e}", exc_info=True)
        return False
