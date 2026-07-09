"""
Generador de PDF para Órdenes de Compra (ODC).

Genera un documento PDF profesional con la información de la ODC
para enviar al proveedor adjunto al correo de notificación.

Estructura del PDF:
  - Cabecera con número de ODC
  - Información del proveedor y comprador (2 columnas)
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
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
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
COLOR_HEADER_BG = colors.HexColor("#1a5276")
COLOR_HEADER_TEXT = colors.white
COLOR_TABLE_HEADER_BG = colors.HexColor("#2c3e50")
COLOR_TABLE_HEADER_TEXT = colors.white
COLOR_ROW_ALT = colors.HexColor("#f8f9fa")
COLOR_ROW_WHITE = colors.white
COLOR_BORDER = colors.HexColor("#bdc3c7")
COLOR_TEXT_DARK = colors.HexColor("#2c3e50")
COLOR_TEXT_MUTED = colors.HexColor("#7f8c8d")
COLOR_ACCENT_GREEN = colors.HexColor("#27ae60")


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
        "odc_title": ParagraphStyle(
            "odc_title",
            parent=styles["Heading1"],
            fontSize=18,
            textColor=COLOR_HEADER_BG,
            alignment=TA_CENTER,
            spaceAfter=4 * mm,
            fontName="Helvetica-Bold",
        ),
        "section_title": ParagraphStyle(
            "section_title",
            parent=styles["Heading2"],
            fontSize=11,
            textColor=COLOR_HEADER_BG,
            spaceBefore=6 * mm,
            spaceAfter=3 * mm,
            fontName="Helvetica-Bold",
        ),
        "label": ParagraphStyle(
            "label",
            parent=styles["Normal"],
            fontSize=8,
            textColor=COLOR_TEXT_MUTED,
            fontName="Helvetica",
        ),
        "value": ParagraphStyle(
            "value",
            parent=styles["Normal"],
            fontSize=9,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica-Bold",
        ),
        "value_normal": ParagraphStyle(
            "value_normal",
            parent=styles["Normal"],
            fontSize=9,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
        ),
        "table_header": ParagraphStyle(
            "table_header",
            parent=styles["Normal"],
            fontSize=7,
            textColor=COLOR_TABLE_HEADER_TEXT,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            parent=styles["Normal"],
            fontSize=7,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
        ),
        "table_cell_right": ParagraphStyle(
            "table_cell_right",
            parent=styles["Normal"],
            fontSize=7,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
            alignment=TA_RIGHT,
        ),
        "table_cell_center": ParagraphStyle(
            "table_cell_center",
            parent=styles["Normal"],
            fontSize=7,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
            alignment=TA_CENTER,
        ),
        "table_cell_bold": ParagraphStyle(
            "table_cell_bold",
            parent=styles["Normal"],
            fontSize=7,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica-Bold",
        ),
        "summary_label": ParagraphStyle(
            "summary_label",
            parent=styles["Normal"],
            fontSize=9,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
        ),
        "summary_value": ParagraphStyle(
            "summary_value",
            parent=styles["Normal"],
            fontSize=9,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
            alignment=TA_RIGHT,
        ),
        "summary_total_label": ParagraphStyle(
            "summary_total_label",
            parent=styles["Normal"],
            fontSize=10,
            textColor=COLOR_HEADER_BG,
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
        ),
        "summary_total_value": ParagraphStyle(
            "summary_total_value",
            parent=styles["Normal"],
            fontSize=10,
            textColor=COLOR_HEADER_BG,
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
        ),
        "firma_empresa": ParagraphStyle(
            "firma_empresa",
            parent=styles["Normal"],
            fontSize=9,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        ),
        "firma_ruc": ParagraphStyle(
            "firma_ruc",
            parent=styles["Normal"],
            fontSize=7,
            textColor=COLOR_TEXT_MUTED,
            fontName="Helvetica",
            alignment=TA_CENTER,
        ),
        "firma_cargo": ParagraphStyle(
            "firma_cargo",
            parent=styles["Normal"],
            fontSize=8,
            textColor=COLOR_TEXT_DARK,
            fontName="Helvetica",
            alignment=TA_CENTER,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=styles["Normal"],
            fontSize=7,
            textColor=COLOR_TEXT_MUTED,
            fontName="Helvetica",
            alignment=TA_CENTER,
        ),
    }
    return custom


def _build_header_info(
    oc_cabecera: Dict[str, Any],
    pedido_info: Optional[Dict[str, Any]],
    styles: Dict[str, ParagraphStyle],
) -> Table:
    """Construye la tabla de información de cabecera (proveedor | comprador)."""
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

    # Columna izquierda: Proveedor
    left_data = [
        [Paragraph("Proveedor", styles["label"])],
        [Paragraph(str(proveedor_nombre), styles["value"])],
        [Paragraph(f"RUC: {proveedor_code}", styles["value_normal"])],
        [Spacer(1, 3 * mm)],
        [Paragraph("Plazo de pago", styles["label"])],
        [Paragraph(str(forma_pago), styles["value_normal"])],
        [Spacer(1, 3 * mm)],
        [Paragraph("Comentario", styles["label"])],
        [Paragraph(f"PEDIDO {referencia}", styles["value_normal"])],
        [Spacer(1, 3 * mm)],
        [Paragraph("Fecha y hora de generaci&oacute;n", styles["label"])],
        [Paragraph(_format_datetime(fecha_hora_generacion), styles["value_normal"])],
    ]
    left_table = Table(left_data, colWidths=[8 * cm])
    left_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    # Columna derecha: Comprador
    right_data = [
        [Paragraph("Raz&oacute;n Social", styles["label"])],
        [Paragraph(COMPRADOR_RAZON_SOCIAL, styles["value"])],
        [Paragraph(f"RUC: {COMPRADOR_RUC}", styles["value_normal"])],
        [Paragraph(COMPRADOR_DIRECCION, styles["value_normal"])],
        [Spacer(1, 3 * mm)],
        [Paragraph("Fecha de Creaci&oacute;n", styles["label"])],
        [Paragraph(_format_date(fecha_creacion), styles["value_normal"])],
        [Paragraph("Fecha de Entrega", styles["label"])],
        [Paragraph(str(fecha_entrega), styles["value_normal"])],
    ]
    right_table = Table(right_data, colWidths=[8 * cm])
    right_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    # Tabla contenedora de 2 columnas
    header_table = Table(
        [[left_table, right_table]],
        colWidths=[9 * cm, 9 * cm],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, COLOR_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    return header_table


def _build_product_table(
    oc_detalles: List[Dict[str, Any]],
    styles: Dict[str, ParagraphStyle],
) -> Table:
    """Construye la tabla de productos."""
    # Encabezados
    headers = [
        Paragraph("#", styles["table_header"]),
        Paragraph("C&oacute;digo de Barras", styles["table_header"]),
        Paragraph("SKU", styles["table_header"]),
        Paragraph("Descripci&oacute;n", styles["table_header"]),
        Paragraph("Cant.", styles["table_header"]),
        Paragraph("Costo", styles["table_header"]),
        Paragraph("Total", styles["table_header"]),
    ]

    data = [headers]

    total_cantidad = 0.0
    total_valor = 0.0

    for idx, detalle in enumerate(oc_detalles, 1):
        sku = detalle.get("sku_sap", "N/A")
        codigo_barras = detalle.get("codigo_barras", "") or ""
        descripcion = detalle.get("descripcion", "") or detalle.get("nombre_producto", "") or detalle.get("descripcion_sap", "") or ""
        cantidad = float(detalle.get("cantidad_sap", 0))
        precio_unit = float(detalle.get("precio_unitario", 0))
        total_linea = float(detalle.get("total_linea", 0))

        total_cantidad += cantidad
        total_valor += total_linea

        row = [
            Paragraph(str(idx), styles["table_cell_center"]),
            Paragraph(str(codigo_barras), styles["table_cell"]),
            Paragraph(str(sku), styles["table_cell_bold"]),
            Paragraph(str(descripcion), styles["table_cell"]),
            Paragraph(f"{cantidad:,.0f}".replace(",", "."), styles["table_cell_right"]),
            Paragraph(_format_number(precio_unit, decimals=5, use_thousands=False), styles["table_cell_right"]),
            Paragraph(_format_currency(total_linea, decimals=4), styles["table_cell_right"]),
        ]
        data.append(row)

    # Fila de TOTAL
    total_row = [
        "",
        "",
        "",
        Paragraph("<b>TOTAL:</b>", styles["table_cell_bold"]),
        Paragraph(
            f"<b>{total_cantidad:,.0f}</b>".replace(",", "."),
            styles["table_cell_right"],
        ),
        "",
        Paragraph(
            f"<b>{_format_currency(total_valor, decimals=4)}</b>",
            styles["table_cell_right"],
        ),
    ]
    data.append(total_row)

    # Anchos de columna
    col_widths = [1.0 * cm, 3.0 * cm, 3.0 * cm, 4.0 * cm, 1.8 * cm, 2.2 * cm, 2.5 * cm]

    table = Table(data, colWidths=col_widths, repeatRows=1)

    # Estilo de la tabla
    style_cmds = [
        # Encabezado
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_TABLE_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_TABLE_HEADER_TEXT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Padding
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        # Bordes
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 1, COLOR_TABLE_HEADER_BG),
        ("GRID", (0, 0), (-1, -2), 0.25, COLOR_BORDER),
        # Fila total
        ("LINEABOVE", (0, -1), (-1, -1), 1, COLOR_TABLE_HEADER_BG),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eaf2f8")),
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

    data = [
        [
            Paragraph("Sub Total", styles["summary_label"]),
            Paragraph(_format_currency(subtotal, decimals=4), styles["summary_value"]),
        ],
        [
            Paragraph("Descuento", styles["summary_label"]),
            Paragraph(f"%{_format_number(descuento_pct, decimals=2, use_thousands=False)}", styles["summary_value"]),
        ],
        [
            Paragraph("Impuesto", styles["summary_label"]),
            Paragraph(_format_currency(impuesto, decimals=4), styles["summary_value"]),
        ],
        [
            Paragraph("<b>Total</b>", styles["summary_total_label"]),
            Paragraph(f"<b>{_format_currency(total, decimals=4)}</b>", styles["summary_total_value"]),
        ],
    ]

    # Tabla alineada a la derecha
    col_widths = [5 * cm, 4 * cm]
    table = Table(data, colWidths=col_widths, hAlign="RIGHT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("GRID", (0, 0), (-1, -1), 0.25, COLOR_BORDER),
        # Fila Total resaltada
        ("LINEABOVE", (0, -1), (-1, -1), 1, COLOR_HEADER_BG),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eaf2f8")),
    ]))

    return table


def _build_signature_section(
    proveedor_nombre: str,
    proveedor_ruc: str,
    styles: Dict[str, ParagraphStyle],
) -> Table:
    """Construye la sección de firmas."""
    # Línea de firma (simulada)
    linea = "_" * 35

    left_firma = [
        [Paragraph(COMPRADOR_RAZON_SOCIAL, styles["firma_empresa"])],
        [Paragraph(COMPRADOR_RUC, styles["firma_ruc"])],
        [Spacer(1, 15 * mm)],
        [Paragraph(linea, styles["firma_cargo"])],
        [Paragraph("Gerente de Marca", styles["firma_cargo"])],
    ]
    left_table = Table(left_firma, colWidths=[8 * cm])
    left_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    right_firma = [
        [Paragraph(str(proveedor_nombre), styles["firma_empresa"])],
        [Paragraph(str(proveedor_ruc), styles["firma_ruc"])],
        [Spacer(1, 15 * mm)],
        [Paragraph(linea, styles["firma_cargo"])],
        [Paragraph("Gerente Financiero", styles["firma_cargo"])],
    ]
    right_table = Table(right_firma, colWidths=[8 * cm])
    right_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

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

        # ── 1. Título de la ODC ──────────────────────────────────────────
        elements.append(Paragraph(f"ODC {numero_oc_sap}", styles["odc_title"]))
        elements.append(Spacer(1, 4 * mm))

        # ── 2. Información de cabecera (proveedor | comprador) ───────────
        header_table = _build_header_info(oc_cabecera, pedido_info, styles)
        elements.append(header_table)
        elements.append(Spacer(1, 6 * mm))

        # ── 3. Tabla de productos ────────────────────────────────────────
        elements.append(Paragraph("Detalle de la Orden de Compra", styles["section_title"]))
        product_table = _build_product_table(oc_detalles, styles)
        elements.append(product_table)
        elements.append(Spacer(1, 6 * mm))

        # ── 4. Resumen financiero ────────────────────────────────────────
        subtotal = sum(float(d.get("total_linea", 0) or 0) for d in oc_detalles)
        summary_table = _build_financial_summary(subtotal, descuento_pct, styles)
        elements.append(summary_table)
        elements.append(Spacer(1, 12 * mm))

        # ── 5. Sección de firmas ─────────────────────────────────────────
        firma_table = _build_signature_section(proveedor_nombre, proveedor_code, styles)
        elements.append(firma_table)
        elements.append(Spacer(1, 8 * mm))

        # ── 6. Pie de página ─────────────────────────────────────────────
        fecha_gen = ahora_naive().strftime("%Y-%m-%d %H:%M:%S")
        elements.append(
            Paragraph(
                f"Documento generado autom&aacute;ticamente &mdash; {COMPRADOR_RAZON_SOCIAL} &mdash; {fecha_gen}",
                styles["footer"],
            )
        )

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
