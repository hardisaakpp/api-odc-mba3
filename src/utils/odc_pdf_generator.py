"""
Generador de PDF para Órdenes de Compra (ODC).

Genera un documento PDF profesional con la información de la ODC
para enviar al proveedor adjunto al correo de notificación.

Estructura del PDF:
  - Tarjeta de cabecera: banner "ORDEN DE COMPRA N.° X" + proveedor/cliente
    (2 columnas) + fechas de creación, entrega y generación
  - Tabla de productos (con código de barras, SKU, descripción, cantidad, costo, total)
  - Resumen financiero (subtotal, descuento, impuesto, total)
  - Sección de firmas (Gerente de Marca, Gerente Financiero)

Uso:
    from src.utils.odc_pdf_generator import generar_odc_pdf

    pdf_bytes = generar_odc_pdf(
        oc_cabecera=oc_cabecera,
        oc_detalles=oc_detalles,
        doc_num=22858,
        pedido_info=pedido_info,  # opcional
    )
"""

import io
import logging
from datetime import datetime

from src.utils.timezone import ahora_naive
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# ─── Constantes de la empresa compradora ─────────────────────────────────────
COMPRADOR_RAZON_SOCIAL = "MABEL TRADING S.A"
COMPRADOR_RUC = "1791915313001"
COMPRADOR_DIRECCION = "Calle Garcia Moreno SN y Panamericana Norte"

# Tasa de IVA en Ecuador (15% desde abril 2024)
TASA_IVA = 0.15

# Ruta del logo (relativa al proyecto)
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
LOGO_PATH = _ASSETS_DIR / "roland_logo.png"

# ─── Colores corporativos ────────────────────────────────────────────────────
# Un único acento navy se reutiliza en el banner de título, el encabezado de
# la tabla de productos y la fila de TOTAL del resumen financiero.
COLOR_ACCENT = colors.HexColor("#173650")
COLOR_ACCENT_TEXT = colors.white
COLOR_ROW_ALT = colors.HexColor("#eef2f6")
COLOR_ROW_WHITE = colors.white
COLOR_BORDER = colors.HexColor("#bdc3c7")
COLOR_TEXT_DARK = colors.HexColor("#2c3e50")
COLOR_TEXT_MUTED = colors.HexColor("#7f8c8d")

# ─── Tipografía ───────────────────────────────────────────────────────────────
# Solo dos tamaños de letra en todo el documento: el "grande" es exactamente
# 1pt mayor que el "pequeño". La jerarquía visual se logra con negrita/color,
# no con más tamaños de fuente.
FONT_SIZE_SMALL = 7
FONT_SIZE_LARGE = FONT_SIZE_SMALL + 1

# Interlineado (leading) explícito y ajustado: si no se fija, ReportLab hereda
# un valor fijo de 12pt del estilo "Normal" sin importar el tamaño de fuente,
# lo que deja el texto de 7-8pt con un espaciado interlineal excesivo (~1.7x).
LEADING_SMALL = FONT_SIZE_SMALL + 1
LEADING_LARGE = FONT_SIZE_LARGE + 1


def _format_number(value: float, decimals: int = 4, use_thousands: bool = True) -> str:
    """Formatea un número con separador de miles (punto) y decimal (coma).

    Ejemplo: 3242.646 -> '3.242,6460' (con 4 decimales)
    """
    if value is None:
        return "0,00"
    # Formatear con N decimales
    formatted = f"{value:,.{decimals}f}"
    # Python usa coma como separador de miles y punto decimal
    # Necesitamos: punto = miles, coma = decimal (formato EC)
    # Paso intermedio: reemplazar , -> X, . -> , , X -> .
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    if not use_thousands:
        # Quitar separadores de miles
        formatted = formatted.replace(".", "", formatted.count(".") - 0)
        # Actually, more reliable:
        parts = formatted.rsplit(",", 1)
        if len(parts) == 2:
            integer_part = parts[0].replace(".", "")
            formatted = f"{integer_part},{parts[1]}"
    return formatted


def _format_currency(value: float, decimals: int = 4) -> str:
    """Formatea un valor monetario."""
    return _format_number(value, decimals=decimals, use_thousands=True)


# Padding horizontal (izq. + der.) aplicado a las celdas de la tabla de
# productos; se reutiliza aquí para calcular el ancho de columna necesario.
_TABLE_CELL_H_PADDING = 8
_TABLE_CELL_WIDTH_BUFFER = 3


def _max_text_width(candidates: List[tuple]) -> float:
    """Ancho máximo (en puntos) entre pares (texto, fuente, tamaño)."""
    if not candidates:
        return 0.0
    return max(stringWidth(text, font_name, font_size) for text, font_name, font_size in candidates)


def _content_col_width(candidates: List[tuple], h_padding: float = _TABLE_CELL_H_PADDING) -> float:
    """Ancho de columna que se ajusta al contenido: máximo texto + padding + margen."""
    return _max_text_width(candidates) + h_padding + _TABLE_CELL_WIDTH_BUFFER


def _format_date(date_value: Any) -> str:
    """Formatea una fecha a dd/mm/yyyy."""
    if date_value is None:
        return "N/A"
    if isinstance(date_value, str):
        try:
            # Intentar parsear formato ISO
            if "T" in date_value:
                dt = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
            elif "-" in date_value:
                dt = datetime.strptime(date_value.split(" ")[0], "%Y-%m-%d")
            elif "/" in date_value:
                return date_value  # Ya está en formato dd/mm/yyyy
            else:
                return date_value
            return dt.strftime("%d/%m/%Y")
        except Exception:
            return str(date_value)
    elif hasattr(date_value, "strftime"):
        return date_value.strftime("%d/%m/%Y")
    return str(date_value)


def _format_datetime(date_value: Any) -> str:
    """Formatea una fecha con hora a dd/mm/yyyy HH:MM:SS."""
    if date_value is None:
        return "N/A"
    if isinstance(date_value, str):
        try:
            if "T" in date_value:
                dt = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
            elif "-" in date_value and " " in date_value:
                dt = datetime.strptime(date_value, "%Y-%m-%d %H:%M:%S")
            elif "-" in date_value:
                dt = datetime.strptime(date_value.split(" ")[0], "%Y-%m-%d")
            else:
                return date_value
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            return str(date_value)
    elif hasattr(date_value, "strftime"):
        return date_value.strftime("%d/%m/%Y %H:%M:%S")
    return str(date_value)


def _get_styles() -> Dict[str, ParagraphStyle]:
    """Crea los estilos de párrafo para el PDF."""
    styles = getSampleStyleSheet()

    custom = {
        "card_title": ParagraphStyle(
            "card_title",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_LARGE,
            leading=LEADING_LARGE,
            textColor=COLOR_ACCENT_TEXT,
            fontName="Helvetica-Bold",
        ),
        "card_label": ParagraphStyle(
            "card_label",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_LARGE,
            leading=LEADING_LARGE,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica-Bold",
            spaceAfter=2,
        ),
        "card_value": ParagraphStyle(
            "card_value",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_LARGE,
            leading=LEADING_LARGE,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica-Bold",
        ),
        "card_value_normal": ParagraphStyle(
            "card_value_normal",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
        ),
        "card_meta": ParagraphStyle(
            "card_meta",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
        ),
        "table_header": ParagraphStyle(
            "table_header",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_ACCENT_TEXT,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        ),
        "table_header_left": ParagraphStyle(
            "table_header_left",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_ACCENT_TEXT,
            fontName="Helvetica-Bold",
            alignment=TA_LEFT,
        ),
        "table_header_right": ParagraphStyle(
            "table_header_right",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_ACCENT_TEXT,
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
        ),
        "table_cell_right": ParagraphStyle(
            "table_cell_right",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
            alignment=TA_RIGHT,
        ),
        "table_cell_center": ParagraphStyle(
            "table_cell_center",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
            alignment=TA_CENTER,
        ),
        "table_cell_bold": ParagraphStyle(
            "table_cell_bold",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica-Bold",
        ),
        "summary_label": ParagraphStyle(
            "summary_label",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
            alignment=TA_RIGHT,
        ),
        "summary_value": ParagraphStyle(
            "summary_value",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
            alignment=TA_RIGHT,
        ),
        "summary_total_label": ParagraphStyle(
            "summary_total_label",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_LARGE,
            leading=LEADING_LARGE,
            textColor=COLOR_ACCENT_TEXT,
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
        ),
        "summary_total_value": ParagraphStyle(
            "summary_total_value",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_LARGE,
            leading=LEADING_LARGE,
            textColor=COLOR_ACCENT_TEXT,
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
        ),
        "firma_empresa": ParagraphStyle(
            "firma_empresa",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_LARGE,
            leading=LEADING_LARGE,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        ),
        "firma_ruc": ParagraphStyle(
            "firma_ruc",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_TEXT_MUTED,
            fontName="Helvetica",
            alignment=TA_CENTER,
        ),
        "firma_cargo": ParagraphStyle(
            "firma_cargo",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
            alignment=TA_CENTER,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=styles["Normal"],
            fontSize=FONT_SIZE_SMALL,
            leading=LEADING_SMALL,
            textColor=COLOR_TEXT_MUTED,
            fontName="Helvetica",
            alignment=TA_CENTER,
        ),
    }
    return custom


def _build_header_info(
    oc_cabecera: Dict[str, Any],
    pedido_info: Optional[Dict[str, Any]],
    numero_oc_sap: Any,
    styles: Dict[str, ParagraphStyle],
) -> Table:
    """Construye la tarjeta de cabecera: banner de título, proveedor/cliente y fechas."""
    proveedor_code = oc_cabecera.get("proveedor", "N/A")
    referencia = oc_cabecera.get("referencia_despacho", "N/A")
    fecha_creacion = oc_cabecera.get("fecha_generacion") or oc_cabecera.get("created_at")
    # Fecha/hora del momento en que se generó (envió) la ODC a SAP
    fecha_hora_generacion = oc_cabecera.get("fecha_procesado") or oc_cabecera.get("created_at")

    # Datos del pedido (si existen)
    forma_pago = "N/A"
    fecha_entrega = "N/A"

    if pedido_info:
        proveedor_nombre = pedido_info.get("proveedor_nombre") or proveedor_code
        forma_pago = pedido_info.get("forma_pago") or "N/A"
        fecha_entrega_raw = pedido_info.get("fecha_entrega")
        if fecha_entrega_raw:
            fecha_entrega = _format_date(fecha_entrega_raw)
    else:
        proveedor_nombre = proveedor_code

    proveedor_cell = [
        Paragraph("PROVEEDOR", styles["card_label"]),
        Paragraph(str(proveedor_nombre), styles["card_value"]),
        Paragraph(f"RUC: {proveedor_code} | Plazo: {forma_pago}", styles["card_value_normal"]),
        Paragraph(f"PEDIDO {referencia}", styles["card_value_normal"]),
    ]
    cliente_cell = [
        Paragraph("CLIENTE", styles["card_label"]),
        Paragraph(COMPRADOR_RAZON_SOCIAL, styles["card_value"]),
        Paragraph(f"RUC: {COMPRADOR_RUC}", styles["card_value_normal"]),
        Paragraph(COMPRADOR_DIRECCION, styles["card_value_normal"]),
    ]
    fechas_cell = Paragraph(
        f"<b>Creaci&oacute;n:</b> {_format_date(fecha_creacion)}"
        f"&nbsp;&nbsp;&nbsp;&nbsp;<b>Entrega:</b> {fecha_entrega}"
        f"&nbsp;&nbsp;&nbsp;&nbsp;<b>Generado:</b> {_format_datetime(fecha_hora_generacion)}",
        styles["card_meta"],
    )

    data = [
        [Paragraph(f"ORDEN DE COMPRA N.&deg; {numero_oc_sap}", styles["card_title"]), ""],
        [proveedor_cell, cliente_cell],
        [fechas_cell, ""],
    ]

    table = Table(data, colWidths=[9 * cm, 9 * cm])
    table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("SPAN", (0, 2), (-1, 2)),
        # Banner de título
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_ACCENT),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("LEFTPADDING", (0, 0), (-1, 0), 10),
        ("RIGHTPADDING", (0, 0), (-1, 0), 10),
        # Fila proveedor | cliente
        ("VALIGN", (0, 1), (-1, 1), "TOP"),
        ("TOPPADDING", (0, 1), (-1, 1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
        ("LEFTPADDING", (0, 1), (-1, 2), 10),
        ("RIGHTPADDING", (0, 1), (-1, 2), 10),
        ("LINEAFTER", (0, 1), (0, 1), 0.5, COLOR_BORDER),
        # Fila de fechas
        ("VALIGN", (0, 2), (-1, 2), "MIDDLE"),
        ("TOPPADDING", (0, 2), (-1, 2), 5),
        ("BOTTOMPADDING", (0, 2), (-1, 2), 5),
        ("LINEABOVE", (0, 2), (-1, 2), 0.5, COLOR_BORDER),
        # Marco exterior de la tarjeta
        ("BOX", (0, 0), (-1, -1), 0.75, COLOR_BORDER),
    ]))

    return table


def _build_product_table(
    oc_detalles: List[Dict[str, Any]],
    styles: Dict[str, ParagraphStyle],
) -> Table:
    """Construye la tabla de productos."""
    # Encabezados
    headers = [
        Paragraph("#", styles["table_header"]),
        Paragraph("C&oacute;d. Barras", styles["table_header_left"]),
        Paragraph("SKU", styles["table_header_left"]),
        Paragraph("Descripci&oacute;n", styles["table_header_left"]),
        Paragraph("Cant.", styles["table_header_right"]),
        Paragraph("Costo", styles["table_header_right"]),
        Paragraph("Total", styles["table_header_right"]),
    ]

    data = [headers]

    total_cantidad = 0.0
    total_valor = 0.0

    # Textos planos de #, Código de Barras, SKU, Cant., Costo y Total, para
    # calcular más abajo el ancho mínimo de columna que evita el ajuste de
    # línea (wrap) en cada una. Descripción es la única columna "flexible":
    # recibe todo el espacio que las demás no necesitan.
    idx_texts = []
    barcode_texts = []
    sku_texts = []
    cant_texts = []
    costo_texts = []
    total_texts = []

    for idx, detalle in enumerate(oc_detalles, 1):
        sku = detalle.get("sku_sap", "N/A")
        codigo_barras = detalle.get("codigo_barras", "") or ""
        descripcion = detalle.get("descripcion", "") or detalle.get("nombre_producto", "") or detalle.get("descripcion_sap", "") or ""
        cantidad = float(detalle.get("cantidad_sap", 0))
        precio_unit = float(detalle.get("precio_unitario", 0))
        total_linea = float(detalle.get("total_linea", 0))

        total_cantidad += cantidad
        total_valor += total_linea

        idx_text = str(idx)
        barcode_text = str(codigo_barras)
        sku_text = str(sku)
        cant_text = f"{cantidad:,.0f}".replace(",", ".")
        costo_text = _format_number(precio_unit, decimals=5, use_thousands=False)
        total_text = _format_currency(total_linea, decimals=4)

        idx_texts.append(idx_text)
        barcode_texts.append(barcode_text)
        sku_texts.append(sku_text)
        cant_texts.append(cant_text)
        costo_texts.append(costo_text)
        total_texts.append(total_text)

        row = [
            Paragraph(idx_text, styles["table_cell_center"]),
            Paragraph(barcode_text, styles["table_cell"]),
            Paragraph(sku_text, styles["table_cell_bold"]),
            Paragraph(str(descripcion), styles["table_cell"]),
            Paragraph(cant_text, styles["table_cell_right"]),
            Paragraph(costo_text, styles["table_cell_right"]),
            Paragraph(total_text, styles["table_cell_right"]),
        ]
        data.append(row)

    # Fila de TOTAL
    total_cant_text = f"{total_cantidad:,.0f}".replace(",", ".")
    total_valor_text = _format_currency(total_valor, decimals=4)
    total_row = [
        "",
        "",
        "",
        Paragraph("<b>TOTAL</b>", styles["table_cell_bold"]),
        Paragraph(f"<b>{total_cant_text}</b>", styles["table_cell_right"]),
        "",
        Paragraph(f"<b>{total_valor_text}</b>", styles["table_cell_right"]),
    ]
    data.append(total_row)

    # Anchos de columna: el ancho útil de página es fijo (18 cm con los
    # márgenes actuales). Todas las columnas salvo Descripción se ajustan al
    # contenido real (encabezado + valores, incluida la fila TOTAL en
    # negrita donde aplica) para ocupar solo una línea; Descripción es la
    # única columna flexible y recibe todo el espacio restante.
    normal_font = styles["table_cell"].fontName
    normal_size = styles["table_cell"].fontSize
    bold_font = styles["table_cell_bold"].fontName
    header_font = styles["table_header"].fontName
    header_size = styles["table_header"].fontSize

    w_idx = _content_col_width(
        [("#", header_font, header_size)]
        + [(t, normal_font, normal_size) for t in idx_texts]
    )
    w_barcode = _content_col_width(
        [("Cód. Barras", header_font, header_size)]
        + [(t, normal_font, normal_size) for t in barcode_texts]
    )
    w_sku = _content_col_width(
        [("SKU", header_font, header_size)]
        + [(t, bold_font, normal_size) for t in sku_texts]
    )
    w_cant = _content_col_width(
        [("Cant.", header_font, header_size)]
        + [(t, normal_font, normal_size) for t in cant_texts]
        + [(total_cant_text, bold_font, normal_size)]
    )
    w_costo = _content_col_width(
        [("Costo", header_font, header_size)]
        + [(t, normal_font, normal_size) for t in costo_texts]
    )
    w_total = _content_col_width(
        [("Total", header_font, header_size)]
        + [(t, normal_font, normal_size) for t in total_texts]
        + [(total_valor_text, bold_font, normal_size)]
    )

    usable_width = 18 * cm
    w_desc = max(usable_width - (w_idx + w_barcode + w_sku + w_cant + w_costo + w_total), 3 * cm)

    col_widths = [w_idx, w_barcode, w_sku, w_desc, w_cant, w_costo, w_total]

    table = Table(data, colWidths=col_widths, repeatRows=1)

    # Estilo de la tabla
    style_cmds = [
        # Encabezado
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_ACCENT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), FONT_SIZE_SMALL),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Padding (compactado para reducir la altura de fila)
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        # Bordes
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 1, COLOR_ACCENT),
        ("GRID", (0, 0), (-1, -2), 0.25, COLOR_BORDER),
        # Fila total
        ("LINEABOVE", (0, -1), (-1, -1), 1, COLOR_ACCENT),
        ("BACKGROUND", (0, -1), (-1, -1), COLOR_ROW_ALT),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]

    # Alternar colores de filas (excluyendo header y total)
    for i in range(1, len(data) - 1):
        bg = COLOR_ROW_ALT if i % 2 == 0 else COLOR_ROW_WHITE
        style_cmds.append(("BACKGROUND", (0, i), (-1, i), bg))

    table.setStyle(TableStyle(style_cmds))
    return table


def _build_financial_summary(
    subtotal: float,
    descuento_pct: float,
    styles: Dict[str, ParagraphStyle],
) -> Table:
    """Construye la tabla de resumen financiero."""
    descuento_valor = subtotal * (descuento_pct / 100.0)
    base_imponible = subtotal - descuento_valor
    impuesto = base_imponible * TASA_IVA
    total = base_imponible + impuesto

    subtotal_text = _format_currency(subtotal, decimals=4)
    descuento_text = f"{_format_number(descuento_pct, decimals=2, use_thousands=False)}%"
    impuesto_text = _format_currency(impuesto, decimals=4)
    total_text = _format_currency(total, decimals=4)

    data = [
        [
            Paragraph("Sub Total", styles["summary_label"]),
            Paragraph(subtotal_text, styles["summary_value"]),
        ],
        [
            Paragraph("Descuento", styles["summary_label"]),
            Paragraph(descuento_text, styles["summary_value"]),
        ],
        [
            Paragraph("Impuesto", styles["summary_label"]),
            Paragraph(impuesto_text, styles["summary_value"]),
        ],
        [
            Paragraph("TOTAL", styles["summary_total_label"]),
            Paragraph(total_text, styles["summary_total_value"]),
        ],
    ]

    # Anchos de columna ajustados al contenido real (evita el espacio en
    # blanco sobrante que dejaba un ancho fijo mayor al necesario).
    label_font = styles["summary_label"].fontName
    label_size = styles["summary_label"].fontSize
    total_label_font = styles["summary_total_label"].fontName
    total_label_size = styles["summary_total_label"].fontSize
    h_padding = 12  # LEFTPADDING + RIGHTPADDING de esta tabla (6 + 6)

    w_label = _content_col_width(
        [
            ("Sub Total", label_font, label_size),
            ("Descuento", label_font, label_size),
            ("Impuesto", label_font, label_size),
            ("TOTAL", total_label_font, total_label_size),
        ],
        h_padding=h_padding,
    )
    w_value = _content_col_width(
        [
            (subtotal_text, label_font, label_size),
            (descuento_text, label_font, label_size),
            (impuesto_text, label_font, label_size),
            (total_text, total_label_font, total_label_size),
        ],
        h_padding=h_padding,
    )

    # Tabla alineada a la derecha
    col_widths = [w_label, w_value]
    table = Table(data, colWidths=col_widths, hAlign="RIGHT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -2), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 2),
        # Fila TOTAL resaltada con el mismo acento navy del banner/encabezado
        ("BACKGROUND", (0, -1), (-1, -1), COLOR_ACCENT),
        ("TOPPADDING", (0, -1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
    ]))

    return table


def _build_signature_section(
    proveedor_nombre: str,
    proveedor_ruc: str,
    styles: Dict[str, ParagraphStyle],
) -> Table:
    """Construye la sección de firmas, con una línea real (no subrayado de texto)."""

    def _firma_columna(empresa: str, ruc: str, cargo: str) -> Table:
        data = [
            [Paragraph(empresa, styles["firma_empresa"])],
            [Paragraph(ruc, styles["firma_ruc"])],
            [Spacer(1, 9 * mm)],
            [""],
            [Paragraph(cargo, styles["firma_cargo"])],
        ]
        col_table = Table(data, colWidths=[8 * cm])
        col_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LINEBELOW", (0, 3), (0, 3), 0.75, colors.black),
        ]))
        return col_table

    left_table = _firma_columna(COMPRADOR_RAZON_SOCIAL, COMPRADOR_RUC, "Gerente de Marca")
    right_table = _firma_columna(str(proveedor_nombre), str(proveedor_ruc), "Gerente Financiero")

    firma_table = Table(
        [[left_table, right_table]],
        colWidths=[9 * cm, 9 * cm],
    )
    firma_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))

    return firma_table


def generar_odc_pdf(
    oc_cabecera: Dict[str, Any],
    oc_detalles: List[Dict[str, Any]],
    doc_num: Optional[int] = None,
    pedido_info: Optional[Dict[str, Any]] = None,
    descuento_pct: float = 0.0,
) -> bytes:
    """
    Genera un PDF de la Orden de Compra.

    Args:
        oc_cabecera: Datos de cabecera de la orden de compra.
        oc_detalles: Lista de detalles de la orden de compra.
            Cada detalle puede incluir opcionalmente:
            - codigo_barras: Código de barras del producto
            - descripcion / nombre_producto / descripcion_sap: Descripción
        doc_num: Número de documento SAP (DocNum).
        pedido_info: Información adicional del pedido (opcional).
            - proveedor_nombre: Razón social del proveedor
            - forma_pago: Plazo/forma de pago
            - fecha_entrega: Fecha de entrega
        descuento_pct: Porcentaje de descuento global (default: 0.0).

    Returns:
        Bytes del PDF generado (listo para adjuntar o guardar).
    """
    try:
        numero_oc_sap = doc_num or oc_cabecera.get("numero_oc_sap", "N/A")
        proveedor_code = oc_cabecera.get("proveedor", "N/A")

        # Obtener nombre del proveedor
        proveedor_nombre = proveedor_code
        if pedido_info:
            proveedor_nombre = pedido_info.get("proveedor_nombre") or proveedor_code

        styles = _get_styles()

        # Buffer en memoria
        buffer = io.BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.5 * cm,
            leftMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
            title=f"ODC {numero_oc_sap}",
            author=COMPRADOR_RAZON_SOCIAL,
        )

        elements = []

        # ── 1. Tarjeta de cabecera (banner + proveedor/cliente + fechas) ──
        header_table = _build_header_info(oc_cabecera, pedido_info, numero_oc_sap, styles)
        elements.append(header_table)
        elements.append(Spacer(1, 4 * mm))

        # ── 2. Tabla de productos ────────────────────────────────────────
        product_table = _build_product_table(oc_detalles, styles)
        elements.append(product_table)
        elements.append(Spacer(1, 4 * mm))

        # ── 3, 4 y 5. Resumen financiero, firmas y pie de página ──────────
        # Se agrupan en un único bloque con KeepTogether para que, si no caben
        # en el espacio restante de la página actual, se muevan juntos a la
        # siguiente en lugar de quedar fragmentados (p. ej. resumen en una
        # página y firmas solas en la siguiente, dejándola casi en blanco).
        subtotal = sum(float(d.get("total_linea", 0) or 0) for d in oc_detalles)
        summary_table = _build_financial_summary(subtotal, descuento_pct, styles)
        firma_table = _build_signature_section(proveedor_nombre, proveedor_code, styles)
        fecha_gen = ahora_naive().strftime("%Y-%m-%d %H:%M:%S")
        footer_paragraph = Paragraph(
            f"Documento generado autom&aacute;ticamente &mdash; {COMPRADOR_RAZON_SOCIAL} &mdash; {fecha_gen}",
            styles["footer"],
        )

        cierre = [
            summary_table,
            Spacer(1, 4 * mm),
            firma_table,
            Spacer(1, 3 * mm),
            footer_paragraph,
        ]
        elements.append(KeepTogether(cierre))

        # Construir PDF
        doc.build(elements)

        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info(
            f"✅ PDF de ODC #{numero_oc_sap} generado correctamente "
            f"({len(pdf_bytes):,} bytes, {len(oc_detalles)} líneas)"
        )
        return pdf_bytes

    except Exception as e:
        logger.error(f"❌ Error al generar PDF de ODC: {e}", exc_info=True)
        raise
