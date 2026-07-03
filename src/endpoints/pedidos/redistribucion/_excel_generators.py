"""Generadores de archivos Excel para redistribución."""

from io import BytesIO
from typing import Any, Dict, List, Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


def generar_excel_reporte_diferencias(
    diferencias: Dict[str, Any],
    pedido_data: Dict[str, Any],
) -> BytesIO:
    """Genera el libro Excel de reporte de diferencias."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        resumen_data = {
            "Concepto": [
                "Total Productos",
                "Total Cantidad Solicitada",
                "Total Cantidad Confirmada",
                "Total Cantidad Asignada",
                "Total Diferencia Cantidad",
                "Total Costo Original",
                "Total Costo Ajustado",
                "Total Diferencia Costo",
            ],
            "Valor": [
                diferencias.get("total_productos"),
                diferencias.get("total_cantidad_solicitada"),
                diferencias.get("total_cantidad_confirmada"),
                diferencias.get("total_cantidad_asignada"),
                diferencias.get("total_diferencia_cantidad"),
                diferencias.get("total_costo_original") or 0,
                diferencias.get("total_costo_ajustado") or 0,
                diferencias.get("total_diferencia_costo") or 0,
            ],
        }
        pd.DataFrame(resumen_data).to_excel(writer, sheet_name="Resumen", index=False)

        if diferencias.get("diferencias_productos"):
            df_productos = pd.DataFrame(diferencias["diferencias_productos"])
            df_productos.to_excel(writer, sheet_name="Diferencias por Producto", index=False)

        if diferencias.get("diferencias_tiendas"):
            df_tiendas = pd.DataFrame(diferencias["diferencias_tiendas"])
            df_tiendas.to_excel(writer, sheet_name="Diferencias por Tienda", index=False)

    output.seek(0)
    return output


def _costos_detalle_por_pedido_detalle_id(pedido_data: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Mapa pedido_detalle_id -> costo_doc_sin_iva (misma fuente que vista normal/solo lectura)."""
    out = {}
    for d in pedido_data.get("detalles", []):
        pid = d.get("pedido_detalle_id")
        if not pid:
            continue
        costo = d.get("costo_doc_sin_iva")
        out[pid] = round(float(costo), 4) if costo is not None else None
    return out


def _crear_estilos() -> Dict[str, Any]:
    return {
        "header_fill": PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid"),
        "header_font": Font(bold=True, color="FFFFFF", size=12),
        "title_fill": PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid"),
        "title_font": Font(bold=True, size=14),
        "border": Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        ),
    }


def _hoja_cabecera(
    wb,
    pedido_id: str,
    cabecera: Dict[str, Any],
    distribucion_data: Dict[str, Any],
    user: Dict[str, Any],
    estilos: Dict[str, Any],
):
    from src.utils.timezone import ahora_naive
    ws = wb.create_sheet("Información del Pedido")
    ws["A1"] = "INFORMACIÓN DEL PEDIDO - DISTRIBUCIÓN CONFIRMADA"
    ws["A1"].font = estilos["title_font"]
    ws["A1"].fill = estilos["title_fill"]
    ws.merge_cells("A1:B1")
    row = 3
    info_fields = [
        ("Número de Pedido", cabecera.get("numero_pedido", "N/A")),
        ("Pedido ID", pedido_id),
        ("Versión Redistribución", distribucion_data.get("version_actual", "N/A")),
        ("Estado", cabecera.get("estado_nombre", "N/A")),
        ("Fecha Pedido", cabecera.get("fecha_pedido", "N/A")),
        ("Fecha Entrega", cabecera.get("fecha_entrega", "N/A")),
        ("Proveedor", cabecera.get("proveedor_nombre", "N/A")),
        ("Comprador", cabecera.get("comprador_nombre", "N/A")),
        ("Forma de Pago", cabecera.get("forma_pago", "N/A")),
        ("Mensaje", cabecera.get("mensaje", "N/A")),
        ("Creado Por", cabecera.get("creado_por", "N/A")),
    ]
    for field, value in info_fields:
        ws[f"A{row}"] = field
        ws[f"A{row}"].font = Font(bold=True)
        ws[f"B{row}"] = value
        row += 1
    ws.column_dimensions["A"].width = 25
    ws.column_dimensions["B"].width = 50
    row = ws.max_row + 2
    ws[f"A{row}"] = "Descargado por:"
    ws[f"A{row}"].font = Font(bold=True)
    ws[f"B{row}"] = user.get("username", "Desconocido")
    row += 1
    ws[f"A{row}"] = "Fecha de descarga:"
    ws[f"A{row}"].font = Font(bold=True)
    ws[f"B{row}"] = ahora_naive().strftime("%Y-%m-%d %H:%M:%S")


def _hoja_resumen(
    wb,
    productos_enriquecidos: List[Dict[str, Any]],
    estilos: Dict[str, Any],
):
    ws = wb.create_sheet("Resumen de Productos")
    ws["A1"] = "RESUMEN DE PRODUCTOS - CANTIDADES"
    ws["A1"].font = estilos["title_font"]
    ws["A1"].fill = estilos["title_fill"]
    ws.merge_cells("A1:F1")
    headers = [
        "Código Producto",
        "Descripción",
        "CODIGO DE BARRAS",
        "Cantidad Solicitada",
        "Cantidad Confirmada",
        "Diferencia",
    ]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col_num)
        cell.value = header
        cell.font = estilos["header_font"]
        cell.fill = estilos["header_fill"]
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = estilos["border"]
    row = 4
    total_solicitada = 0
    total_confirmada = 0
    total_diferencia = 0
    for producto in productos_enriquecidos:
        codigo_interno = producto.get("codigo_interno", "")
        descripcion = producto.get("descripcion_sap", "")
        codigo_barras = producto.get("codigo_barras") or ""
        cantidad_solicitada = float(producto.get("cantidad_solicitada_total", 0) or 0)
        cantidad_confirmada = float(producto.get("cantidad_confirmada_total", 0) or 0)
        cantidad_asignada = float(producto.get("cantidad_asignada_total", 0) or 0)
        diferencia = cantidad_confirmada - cantidad_asignada
        total_solicitada += cantidad_solicitada
        total_confirmada += cantidad_confirmada
        total_diferencia += diferencia
        ws.cell(row=row, column=1, value=codigo_interno)
        ws.cell(row=row, column=2, value=descripcion)
        ws.cell(row=row, column=3, value=codigo_barras)
        ws.cell(row=row, column=4, value=cantidad_solicitada)
        ws.cell(row=row, column=5, value=cantidad_confirmada)
        ws.cell(row=row, column=6, value=diferencia)
        row += 1
    row += 1
    ws.cell(row=row, column=1, value="TOTALES").font = Font(bold=True)
    ws.cell(row=row, column=4, value=total_solicitada).font = Font(bold=True)
    ws.cell(row=row, column=5, value=total_confirmada).font = Font(bold=True)
    ws.cell(row=row, column=6, value=total_diferencia).font = Font(bold=True)
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 45
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 18
    ws.column_dimensions["F"].width = 15


def _resolver_costo_unitario(
    pedido_detalle_id: Optional[str],
    costos_detalle: Dict[str, Optional[float]],
    distribuciones: List[Dict[str, Any]],
) -> float:
    costo = costos_detalle.get(pedido_detalle_id) if pedido_detalle_id else None
    if costo is None and distribuciones:
        primer_dist = distribuciones[0]
        costo = primer_dist.get("costo_unitario_ajustado") or primer_dist.get("costo_unitario_original")
    return round(float(costo), 4) if costo is not None else 0.0


def _escribir_distribuciones_producto(
    ws,
    row: int,
    codigo_interno: str,
    descripcion: str,
    codigo_barras: str,
    distribuciones: List[Dict[str, Any]],
    costo_unitario: float,
    itr_por_tienda: Dict[str, int],
) -> int:
    if distribuciones:
        for dist in distribuciones:
            ws.cell(row=row, column=1, value=codigo_interno)
            ws.cell(row=row, column=2, value=descripcion)
            ws.cell(row=row, column=3, value=codigo_barras)
            tienda_codigo = dist.get("tienda_codigo", "")
            ws.cell(row=row, column=4, value=tienda_codigo)
            ws.cell(row=row, column=5, value=dist.get("tienda_nombre", ""))
            ws.cell(row=row, column=6, value=dist.get("cantidad_asignada", 0))
            ws.cell(row=row, column=7, value=costo_unitario)
            ws.cell(row=row, column=8, value=dist.get("observaciones", ""))
            # Número Solicitud Transferencia (DocNum del ITR en SAP)
            doc_num_itr = itr_por_tienda.get(tienda_codigo)
            ws.cell(row=row, column=9, value=doc_num_itr if doc_num_itr else "")
            ws.cell(row=row, column=7).number_format = "#,##0.0000"
            row += 1
    else:
        ws.cell(row=row, column=1, value=codigo_interno)
        ws.cell(row=row, column=2, value=descripcion)
        ws.cell(row=row, column=3, value=codigo_barras)
        ws.cell(row=row, column=4, value="Sin distribución")
        row += 1
    return row


def _hoja_detalle(
    wb,
    productos_enriquecidos: List[Dict[str, Any]],
    costos_detalle: Dict[str, Optional[float]],
    itr_por_tienda: Dict[str, int],
    estilos: Dict[str, Any],
):
    ws = wb.create_sheet("Distribución por Tienda")
    ws["A1"] = "DISTRIBUCIÓN DETALLADA POR TIENDA"
    ws["A1"].font = estilos["title_font"]
    ws["A1"].fill = estilos["title_fill"]
    ws.merge_cells("A1:I1")
    headers = [
        "Código Producto",
        "Descripción",
        "CODIGO DE BARRAS",
        "Código Tienda",
        "Nombre Tienda",
        "Cantidad Asignada",
        "Costo Unitario",
        "Observaciones",
        "Número Solicitud Transferencia",
    ]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col_num)
        cell.value = header
        cell.font = estilos["header_font"]
        cell.fill = estilos["header_fill"]
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = estilos["border"]
    row = 4
    for producto in productos_enriquecidos:
        codigo_interno = producto.get("codigo_interno", "")
        descripcion = producto.get("descripcion_sap", "")
        codigo_barras = producto.get("codigo_barras") or ""
        distribuciones = producto.get("distribuciones", [])
        pedido_detalle_id = producto.get("pedido_detalle_id")
        costo_unitario = _resolver_costo_unitario(pedido_detalle_id, costos_detalle, distribuciones)
        row = _escribir_distribuciones_producto(
            ws, row, codigo_interno, descripcion, codigo_barras,
            distribuciones, costo_unitario, itr_por_tienda,
        )
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 45
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 15
    ws.column_dimensions["E"].width = 30
    ws.column_dimensions["F"].width = 18
    ws.column_dimensions["G"].width = 15
    ws.column_dimensions["H"].width = 30
    ws.column_dimensions["I"].width = 30


def generar_excel_distribucion(
    pedido_id: str,
    pedido_data: Dict[str, Any],
    distribucion_data: Dict[str, Any],
    productos_enriquecidos: List[Dict[str, Any]],
    user: Dict[str, Any],
    itr_por_tienda: Optional[Dict[str, int]] = None,
) -> BytesIO:
    """Genera el libro Excel de distribución confirmada."""
    cabecera = pedido_data.get("cabecera", {})
    costos_detalle = _costos_detalle_por_pedido_detalle_id(pedido_data)
    if itr_por_tienda is None:
        itr_por_tienda = {}

    wb = Workbook()
    default_sheet = wb.active
    if default_sheet is not None:
        wb.remove(default_sheet)

    estilos = _crear_estilos()
    _hoja_cabecera(wb, pedido_id, cabecera, distribucion_data, user, estilos)
    _hoja_resumen(wb, productos_enriquecidos, estilos)
    _hoja_detalle(wb, productos_enriquecidos, costos_detalle, itr_por_tienda, estilos)

    excel_buffer = BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)
    return excel_buffer
