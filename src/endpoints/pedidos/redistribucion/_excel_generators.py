"""Generadores de archivos Excel para redistribución."""

import re
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

    wb = Workbook()
    default_sheet = wb.active
    if default_sheet is not None:
        wb.remove(default_sheet)

    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    title_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    title_font = Font(bold=True, size=14)
    border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    ws_cabecera = wb.create_sheet("Información del Pedido")
    ws_cabecera["A1"] = "INFORMACIÓN DEL PEDIDO - DISTRIBUCIÓN CONFIRMADA"
    ws_cabecera["A1"].font = title_font
    ws_cabecera["A1"].fill = title_fill
    ws_cabecera.merge_cells("A1:B1")

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
        ws_cabecera[f"A{row}"] = field
        ws_cabecera[f"A{row}"].font = Font(bold=True)
        ws_cabecera[f"B{row}"] = value
        row += 1

    ws_cabecera.column_dimensions["A"].width = 25
    ws_cabecera.column_dimensions["B"].width = 50

    ws_resumen = wb.create_sheet("Resumen de Productos")
    ws_resumen["A1"] = "RESUMEN DE PRODUCTOS - CANTIDADES"
    ws_resumen["A1"].font = title_font
    ws_resumen["A1"].fill = title_fill
    ws_resumen.merge_cells("A1:E1")

    headers_resumen = [
        "Código Producto",
        "Descripción",
        "Cantidad Solicitada",
        "Cantidad Confirmada",
        "Diferencia",
    ]

    for col_num, header in enumerate(headers_resumen, 1):
        cell = ws_resumen.cell(row=3, column=col_num)
        cell.value = header
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    row = 4
    total_solicitada = 0
    total_confirmada = 0
    total_diferencia = 0

    for producto in productos_enriquecidos:
        codigo_interno = producto.get("codigo_interno", "")
        descripcion = producto.get("descripcion_sap", "")
        cantidad_solicitada = float(producto.get("cantidad_solicitada_total", 0) or 0)
        cantidad_confirmada = float(producto.get("cantidad_confirmada_total", 0) or 0)
        cantidad_asignada = float(producto.get("cantidad_asignada_total", 0) or 0)
        diferencia = cantidad_confirmada - cantidad_asignada

        total_solicitada += cantidad_solicitada
        total_confirmada += cantidad_confirmada
        total_diferencia += diferencia

        ws_resumen.cell(row=row, column=1, value=codigo_interno)
        ws_resumen.cell(row=row, column=2, value=descripcion)
        ws_resumen.cell(row=row, column=3, value=cantidad_solicitada)
        ws_resumen.cell(row=row, column=4, value=cantidad_confirmada)
        ws_resumen.cell(row=row, column=5, value=diferencia)

        row += 1

    row += 1
    ws_resumen.cell(row=row, column=1, value="TOTALES").font = Font(bold=True)
    ws_resumen.cell(row=row, column=3, value=total_solicitada).font = Font(bold=True)
    ws_resumen.cell(row=row, column=4, value=total_confirmada).font = Font(bold=True)
    ws_resumen.cell(row=row, column=5, value=total_diferencia).font = Font(bold=True)

    ws_resumen.column_dimensions["A"].width = 20
    ws_resumen.column_dimensions["B"].width = 45
    ws_resumen.column_dimensions["C"].width = 18
    ws_resumen.column_dimensions["D"].width = 18
    ws_resumen.column_dimensions["E"].width = 15

    if itr_por_tienda is None:
        itr_por_tienda = {}

    ws_detalle = wb.create_sheet("Distribución por Tienda")
    ws_detalle["A1"] = "DISTRIBUCIÓN DETALLADA POR TIENDA"
    ws_detalle["A1"].font = title_font
    ws_detalle["A1"].fill = title_fill
    ws_detalle.merge_cells("A1:H1")

    headers_detalle = [
        "Código Producto",
        "Descripción",
        "Código Tienda",
        "Nombre Tienda",
        "Cantidad Asignada",
        "Costo Unitario",
        "Observaciones",
        "Número Solicitud Transferencia",
    ]

    for col_num, header in enumerate(headers_detalle, 1):
        cell = ws_detalle.cell(row=3, column=col_num)
        cell.value = header
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    row = 4
    for producto in productos_enriquecidos:
        codigo_interno = producto.get("codigo_interno", "")
        descripcion = producto.get("descripcion_sap", "")
        distribuciones = producto.get("distribuciones", [])
        # Costo unitario: misma fuente que vista normal/solo lectura (pedido_detalle.costo_doc_sin_iva)
        pedido_detalle_id = producto.get("pedido_detalle_id")
        costo_unitario = costos_detalle.get(pedido_detalle_id) if pedido_detalle_id else None
        if costo_unitario is None and distribuciones:
            primer_dist = distribuciones[0]
            costo_unitario = primer_dist.get("costo_unitario_ajustado") or primer_dist.get("costo_unitario_original")
        costo_unitario = round(float(costo_unitario), 4) if costo_unitario is not None else 0.0

        if distribuciones:
            for dist in distribuciones:
                ws_detalle.cell(row=row, column=1, value=codigo_interno)
                ws_detalle.cell(row=row, column=2, value=descripcion)
                tienda_codigo = dist.get("tienda_codigo", "")
                ws_detalle.cell(row=row, column=3, value=tienda_codigo)
                ws_detalle.cell(row=row, column=4, value=dist.get("tienda_nombre", ""))
                ws_detalle.cell(row=row, column=5, value=dist.get("cantidad_asignada", 0))
                ws_detalle.cell(row=row, column=6, value=costo_unitario)
                ws_detalle.cell(row=row, column=7, value=dist.get("observaciones", ""))
                # Número Solicitud Transferencia (DocNum del ITR en SAP)
                doc_num_itr = itr_por_tienda.get(tienda_codigo)
                ws_detalle.cell(row=row, column=8, value=doc_num_itr if doc_num_itr else "")
                ws_detalle.cell(row=row, column=6).number_format = "#,##0.0000"
                row += 1
        else:
            ws_detalle.cell(row=row, column=1, value=codigo_interno)
            ws_detalle.cell(row=row, column=2, value=descripcion)
            ws_detalle.cell(row=row, column=3, value="Sin distribución")
            row += 1

    ws_detalle.column_dimensions["A"].width = 20
    ws_detalle.column_dimensions["B"].width = 45
    ws_detalle.column_dimensions["C"].width = 15
    ws_detalle.column_dimensions["D"].width = 30
    ws_detalle.column_dimensions["E"].width = 18
    ws_detalle.column_dimensions["F"].width = 15
    ws_detalle.column_dimensions["G"].width = 30
    ws_detalle.column_dimensions["H"].width = 30

    row = ws_cabecera.max_row + 2
    ws_cabecera[f"A{row}"] = "Descargado por:"
    ws_cabecera[f"A{row}"].font = Font(bold=True)
    ws_cabecera[f"B{row}"] = user.get("username", "Desconocido")

    row += 1
    ws_cabecera[f"A{row}"] = "Fecha de descarga:"
    ws_cabecera[f"A{row}"].font = Font(bold=True)
    from src.utils.timezone import ahora_naive

    ws_cabecera[f"B{row}"] = ahora_naive().strftime("%Y-%m-%d %H:%M:%S")

    excel_buffer = BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)
    return excel_buffer
