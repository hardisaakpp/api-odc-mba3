"""
Módulo para generar archivos Excel de pedidos.

Este módulo extrae la lógica de generación de Excel desde pedidos_crud.py
para mejorar la mantensibilidad y permitir testing independiente.
"""

import logging
import re
import io
from typing import Tuple
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


from src.utils.timezone import ahora_naive
from src.database.pedido_estados import ESTADO_REDISTRIBUCION

logger = logging.getLogger(__name__)

# Literales reutilizados (evita duplicación)
_COL_CODIGO_PRODUCTO = "Código Producto"
_COL_DESCRIPCION = "Descripción"
_FMT_MONEDA = '#,##0.00'


def _crear_estilos() -> dict:
    """Crea los estilos reutilizables del libro de Excel."""
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    return {
        "header_fill": PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid"),
        "header_font": Font(bold=True, color="FFFFFF", size=12),
        "title_fill": PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid"),
        "title_font": Font(bold=True, size=14),
        "border": border,
    }


def _escribir_encabezados(ws, headers, estilos) -> None:
    """Escribe una fila de encabezados (fila 3) con el estilo estándar."""
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col_num)
        cell.value = header
        cell.font = estilos["header_font"]
        cell.fill = estilos["header_fill"]
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = estilos["border"]


def _escribir_hoja_cabecera(wb, pedido_id, cabecera, estilos):
    """Crea y llena la hoja de información de cabecera. Retorna la hoja."""
    ws_cabecera = wb.create_sheet("Información del Pedido")

    # Título
    ws_cabecera['A1'] = "INFORMACIÓN DEL PEDIDO"
    ws_cabecera['A1'].font = estilos["title_font"]
    ws_cabecera['A1'].fill = estilos["title_fill"]
    ws_cabecera.merge_cells('A1:B1')

    # Datos de cabecera
    row = 3
    info_fields = [
        ("Número de Pedido", cabecera.get("numero_pedido", "N/A")),
        ("Pedido ID", pedido_id),
        ("Estado", cabecera.get("estado_nombre", "N/A")),
        ("Fecha Pedido", cabecera.get("fecha_pedido", "N/A")),
        ("Fecha Entrega", cabecera.get("fecha_entrega", "N/A")),
        ("Proveedor", cabecera.get("proveedor_nombre", "N/A")),
        ("Comprador", cabecera.get("comprador_nombre", "N/A")),
        ("Código Comprador", cabecera.get("comprador_codigo", "N/A")),
        ("Mensaje", cabecera.get("mensaje", "N/A")),
        ("Forma de Pago", cabecera.get("forma_pago", "N/A")),
        ("Origen Traslado", cabecera.get("origen_traslado", "N/A")),
        ("Serie", cabecera.get("serie", "N/A")),
        ("Archivo", cabecera.get("archivo_nombre", "N/A")),
        ("Creado Por", cabecera.get("creado_por", "N/A")),
        ("Fecha de Creación", cabecera.get("creado_en", "N/A")),
    ]

    for field, value in info_fields:
        ws_cabecera[f'A{row}'] = field
        ws_cabecera[f'A{row}'].font = Font(bold=True)
        ws_cabecera[f'B{row}'] = value
        row += 1

    # Ajustar anchos de columna
    ws_cabecera.column_dimensions['A'].width = 25
    ws_cabecera.column_dimensions['B'].width = 50

    return ws_cabecera


def _fetch_rows_confirmada(conn, pedido_id):
    """
    Obtiene los datos agregados desde distribucion_confirmada.
    Retorna (rows_data, version_actual). Vacío si no hay versión o falla.
    """
    version_actual = None
    try:
        from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository

        dist_repo = DistribucionConfirmadaRepository(conn)
        version_actual = dist_repo.get_version_actual(pedido_id)

        if not version_actual:
            return [], version_actual

        logger.info(f"📊 Intentando usar datos de distribucion_confirmada (versión {version_actual})")

        # Query directo para obtener datos agregados con costos
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                dc.pedido_detalle_id,
                pd.codigo_interno,
                pd.descripcion_sap,
                pd.codigo_barras,
                pd.pack,
                SUM(dc.cantidad_asignada) AS total_asignada,
                MAX(dc.costo_unitario_ajustado) AS costo_unitario_ajustado,
                SUM(dc.subtotal_ajustado) AS subtotal_ajustado,
                ps.item_code_sap,
                ps.unidad_sap,
                pd.comentario
            FROM distribucion_confirmada dc
            INNER JOIN pedido_detalle pd ON dc.pedido_detalle_id = pd.pedido_detalle_id
            LEFT JOIN pedido_sap_procesamiento_detalle ps ON pd.pedido_detalle_id = ps.pedido_detalle_id
            WHERE dc.pedido_id = ? AND dc.version = ?
            GROUP BY dc.pedido_detalle_id, pd.codigo_interno, pd.descripcion_sap,
                     pd.codigo_barras, pd.pack, ps.item_code_sap, ps.unidad_sap, pd.comentario
            ORDER BY pd.codigo_interno
        """, (pedido_id, version_actual))

        rows_data = cursor.fetchall()
        cursor.close()
        return rows_data, version_actual
    except Exception as e:
        logger.warning(f"⚠️ No se pudo obtener datos de distribucion_confirmada: {e}")
        return [], version_actual


def _fetch_rows_fallback(conn, pedido_id):
    """FALLBACK: obtiene los datos directamente desde pedido_detalle."""
    logger.info("⚠️ No hay datos en distribucion_confirmada, usando pedido_detalle directamente")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            pd.pedido_detalle_id,
            pd.codigo_interno,
            pd.descripcion_sap,
            pd.codigo_barras,
            pd.pack,
            ISNULL(SUM(pdt.cantidad), 0) AS total_cantidad,
            pd.costo_doc_sin_iva AS costo_unitario,
            pd.total AS total_linea,
            ps.item_code_sap,
            ps.unidad_sap,
            pd.comentario
        FROM pedido_detalle pd
        LEFT JOIN pedido_detalle_tienda pdt ON pd.pedido_detalle_id = pdt.pedido_detalle_id
        LEFT JOIN pedido_sap_procesamiento_detalle ps ON pd.pedido_detalle_id = ps.pedido_detalle_id
        WHERE pd.pedido_id = ?
        GROUP BY pd.pedido_detalle_id, pd.codigo_interno, pd.descripcion_sap,
                 pd.codigo_barras, pd.pack, pd.costo_doc_sin_iva, pd.total,
                 ps.item_code_sap, ps.unidad_sap, pd.comentario
        ORDER BY pd.codigo_interno
    """, (pedido_id,))

    rows_data = cursor.fetchall()
    cursor.close()
    return rows_data


def _fetch_distribuciones(conn, pedido_detalle_id, pedido_id, version_actual):
    """Obtiene las distribuciones por tienda de un detalle (confirmada o fallback)."""
    distribuciones = []
    try:
        cursor_dist = conn.cursor()
        if version_actual:
            cursor_dist.execute("""
                SELECT
                    t.codigo AS tienda_codigo,
                    t.nombre AS tienda_nombre,
                    dc.cantidad_asignada,
                    dc.costo_unitario_ajustado,
                    dc.subtotal_ajustado
                FROM distribucion_confirmada dc
                INNER JOIN tienda t ON dc.tienda_id = t.tienda_id
                WHERE dc.pedido_detalle_id = ? AND dc.pedido_id = ? AND dc.version = ?
                ORDER BY t.codigo
            """, (pedido_detalle_id, pedido_id, version_actual))
        else:
            # FALLBACK
            cursor_dist.execute("""
                SELECT
                    t.codigo AS tienda_codigo,
                    t.nombre AS tienda_nombre,
                    pdt.cantidad,
                    pd.costo_doc_sin_iva AS costo_unitario,
                    (pdt.cantidad * pd.costo_doc_sin_iva) AS subtotal
                FROM pedido_detalle_tienda pdt
                INNER JOIN tienda t ON pdt.tienda_id = t.tienda_id
                INNER JOIN pedido_detalle pd ON pdt.pedido_detalle_id = pd.pedido_detalle_id
                WHERE pdt.pedido_detalle_id = ?
                ORDER BY t.codigo
            """, (pedido_detalle_id,))

        for dist_row in cursor_dist.fetchall():
            distribuciones.append({
                "tienda_codigo": dist_row[0],
                "tienda_nombre": dist_row[1],
                "cantidad_asignada": dist_row[2],
                "costo_unitario_ajustado": float(dist_row[3]) if dist_row[3] is not None else 0.0,
                "subtotal_ajustado": float(dist_row[4]) if dist_row[4] is not None else 0.0
            })
        cursor_dist.close()
    except Exception as e:
        logger.warning(f"⚠️ No se pudieron obtener distribuciones para detalle {pedido_detalle_id}: {e}")

    return distribuciones


def _escribir_fila_detalle(ws, row, codigo_interno, descripcion, cantidad,
                           costo_unitario, total_linea, unidad, codigo_barras, comentario) -> None:
    """Escribe una fila de la tabla de detalles y aplica el formato numérico."""
    ws.cell(row=row, column=1, value=codigo_interno)
    ws.cell(row=row, column=2, value=descripcion)
    ws.cell(row=row, column=3, value=cantidad)
    ws.cell(row=row, column=4, value=costo_unitario)
    ws.cell(row=row, column=5, value=total_linea)
    ws.cell(row=row, column=6, value=unidad)
    ws.cell(row=row, column=7, value=codigo_barras)
    ws.cell(row=row, column=8, value=comentario)
    ws.cell(row=row, column=4).number_format = _FMT_MONEDA
    ws.cell(row=row, column=5).number_format = _FMT_MONEDA


def _procesar_detalles_confirmada(ws_detalles, conn, rows_data, pedido_id, version_actual, row):
    """Procesa filas de distribucion_confirmada. Retorna (total_cantidad, total_valor, detalles, row)."""
    total_cantidad = 0
    total_valor = 0.0
    detalles_para_distribucion = []

    for row_data in rows_data:
        pedido_detalle_id = str(row_data[0])
        codigo_interno = row_data[1] or ""
        descripcion = row_data[2] or ""
        codigo_barras = row_data[3] or ""
        pack_original = row_data[4] or ""
        cantidad = row_data[5] or 0
        costo_unitario = float(row_data[6]) if row_data[6] is not None else 0.0
        total_linea = float(row_data[7]) if row_data[7] is not None else 0.0
        unidad_sap = row_data[9] or ""
        comentario = row_data[10] or ""

        # Usar códigos SAP si existen
        unidad = unidad_sap if unidad_sap else pack_original

        total_cantidad += cantidad
        total_valor += total_linea

        _escribir_fila_detalle(
            ws_detalles, row, codigo_interno, descripcion, cantidad,
            costo_unitario, total_linea, unidad, codigo_barras, comentario
        )
        row += 1

        # Obtener distribuciones por tienda y guardarlas para la sección de distribución
        distribuciones = _fetch_distribuciones(conn, pedido_detalle_id, pedido_id, version_actual)
        detalles_para_distribucion.append({
            "codigo_interno": codigo_interno,
            "descripcion": descripcion,
            "distribuciones": distribuciones
        })

    return total_cantidad, total_valor, detalles_para_distribucion, row


def _procesar_detalles_no_confirmada(ws_detalles, detalles, row):
    """Procesa detalles originales de pedido_detalle. Retorna (total_cantidad, total_valor, detalles, row)."""
    total_cantidad = 0
    total_valor = 0.0
    detalles_para_distribucion = []

    for detalle in detalles:
        codigo_interno = detalle.get("codigo_interno", "")
        descripcion = detalle.get("descripcion_sap", detalle.get("nombre_producto", ""))
        cantidad = detalle.get("cantidad_total", 0)
        precio_unitario = detalle.get("precio_unitario", 0.0)
        total_linea = cantidad * precio_unitario
        unidad = detalle.get("unidad_sap", "")
        codigo_barras = detalle.get("codigo_barras", "")
        comentario = detalle.get("comentario", "")

        total_cantidad += cantidad
        total_valor += total_linea

        _escribir_fila_detalle(
            ws_detalles, row, codigo_interno, descripcion, cantidad,
            precio_unitario, total_linea, unidad, codigo_barras, comentario
        )
        row += 1

        # Guardar para sección de distribución
        detalles_para_distribucion.append({
            "codigo_interno": codigo_interno,
            "descripcion": descripcion,
            "distribuciones": detalle.get("distribuciones", [])
        })

    return total_cantidad, total_valor, detalles_para_distribucion, row


def _ajustar_anchos_detalles(ws) -> None:
    """Ajusta los anchos de columna de la hoja de detalles."""
    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 40
    ws.column_dimensions['C'].width = 14
    ws.column_dimensions['D'].width = 15
    ws.column_dimensions['E'].width = 16
    ws.column_dimensions['F'].width = 12
    ws.column_dimensions['G'].width = 20
    ws.column_dimensions['H'].width = 30


def _escribir_hoja_detalles(wb, conn, pedido_id, pedido_data, usar_distribucion_confirmada, estilos):
    """Crea y llena la hoja de detalles de artículos. Retorna detalles_para_distribucion."""
    ws_detalles = wb.create_sheet("Detalles de Artículos")

    # Título
    ws_detalles['A1'] = "DETALLES DE ARTÍCULOS"
    ws_detalles['A1'].font = estilos["title_font"]
    ws_detalles['A1'].fill = estilos["title_fill"]
    ws_detalles.merge_cells('A1:H1')

    # Encabezados de la tabla de detalles
    headers = [
        _COL_CODIGO_PRODUCTO,
        _COL_DESCRIPCION,
        "Total Original",
        "Costo Unitario",
        "Total Confirmado",
        "PACK",
        "Código de Barras",
        "Comentario"
    ]
    _escribir_encabezados(ws_detalles, headers, estilos)

    row = 4

    # Obtener datos: distribucion_confirmada (con fallback a pedido_detalle)
    rows_data = []
    version_actual = None
    if usar_distribucion_confirmada:
        rows_data, version_actual = _fetch_rows_confirmada(conn, pedido_id)
        if len(rows_data) == 0:
            rows_data = _fetch_rows_fallback(conn, pedido_id)

    # Procesar datos (ya sea de distribucion_confirmada o pedido_detalle)
    if usar_distribucion_confirmada and len(rows_data) > 0:
        total_cantidad, total_valor, detalles_para_distribucion, row = _procesar_detalles_confirmada(
            ws_detalles, conn, rows_data, pedido_id, version_actual, row
        )
    else:
        detalles = pedido_data.get("detalles", [])
        total_cantidad, total_valor, detalles_para_distribucion, row = _procesar_detalles_no_confirmada(
            ws_detalles, detalles, row
        )

    # Totales
    row += 1
    ws_detalles.cell(row=row, column=1, value="TOTALES").font = Font(bold=True)
    ws_detalles.cell(row=row, column=3, value=total_cantidad).font = Font(bold=True)
    ws_detalles.cell(row=row, column=5, value=total_valor).font = Font(bold=True)
    ws_detalles.cell(row=row, column=5).number_format = _FMT_MONEDA

    _ajustar_anchos_detalles(ws_detalles)

    return detalles_para_distribucion


def _escribir_distribuciones_articulo(ws, detalle, usar_distribucion_confirmada, row):
    """Escribe las filas de distribución de un artículo. Retorna la siguiente fila."""
    codigo_interno = detalle.get("codigo_interno", "")
    descripcion = detalle.get("descripcion", "")
    distribuciones = detalle.get("distribuciones", [])

    if not distribuciones:
        # Sin distribución
        ws.cell(row=row, column=1, value=codigo_interno)
        ws.cell(row=row, column=2, value=descripcion)
        ws.cell(row=row, column=3, value="Sin distribución")
        return row + 1

    for dist in distribuciones:
        if usar_distribucion_confirmada:
            # Con costos para estado CONFIRMADO
            ws.cell(row=row, column=1, value=codigo_interno)
            ws.cell(row=row, column=2, value=descripcion)
            ws.cell(row=row, column=3, value=dist.get("tienda_codigo", ""))
            ws.cell(row=row, column=4, value=dist.get("tienda_nombre", ""))
            ws.cell(row=row, column=5, value=dist.get("cantidad_asignada", 0))
            ws.cell(row=row, column=6, value=float(dist.get('costo_unitario_ajustado', 0.0) or 0.0))
            ws.cell(row=row, column=6).number_format = _FMT_MONEDA
        else:
            # Sin costos para otros estados
            ws.cell(row=row, column=1, value=codigo_interno)
            ws.cell(row=row, column=2, value=descripcion)
            ws.cell(row=row, column=3, value=dist.get("codigo_tienda", ""))
            ws.cell(row=row, column=4, value=dist.get("nombre_tienda", ""))
            ws.cell(row=row, column=5, value=dist.get("cantidad", 0))

        row += 1

    return row


def _ajustar_anchos_distribucion(ws, usar_distribucion_confirmada) -> None:
    """Ajusta los anchos de columna de la hoja de distribución."""
    ws.column_dimensions['A'].width = 15
    ws.column_dimensions['B'].width = 40
    ws.column_dimensions['C'].width = 15
    ws.column_dimensions['D'].width = 30
    ws.column_dimensions['E'].width = 15
    if usar_distribucion_confirmada:
        ws.column_dimensions['F'].width = 15
        ws.column_dimensions['G'].width = 15


def _escribir_hoja_distribucion(wb, detalles_para_distribucion, usar_distribucion_confirmada, estilos) -> None:
    """Crea y llena la hoja de distribución por tiendas."""
    ws_distribucion = wb.create_sheet("Distribución por Tiendas")

    # Título
    ws_distribucion['A1'] = "DISTRIBUCIÓN POR TIENDAS"
    ws_distribucion['A1'].font = estilos["title_font"]
    ws_distribucion['A1'].fill = estilos["title_fill"]
    ws_distribucion.merge_cells('A1:F1' if usar_distribucion_confirmada else 'A1:E1')

    # Encabezados de distribución
    if usar_distribucion_confirmada:
        dist_headers = [
            _COL_CODIGO_PRODUCTO,
            _COL_DESCRIPCION,
            "Código Tienda",
            "Nombre Tienda",
            "Cantidad Asignada",
            "Costo Unitario"
        ]
    else:
        dist_headers = [
            _COL_CODIGO_PRODUCTO,
            _COL_DESCRIPCION,
            "Código Tienda",
            "Nombre Tienda",
            "Cantidad Distribuida"
        ]

    _escribir_encabezados(ws_distribucion, dist_headers, estilos)

    row = 4
    # Agrupar distribuciones por artículo
    for detalle in detalles_para_distribucion:
        row = _escribir_distribuciones_articulo(ws_distribucion, detalle, usar_distribucion_confirmada, row)

    _ajustar_anchos_distribucion(ws_distribucion, usar_distribucion_confirmada)


def _agregar_info_descarga(ws_cabecera, username) -> None:
    """Agrega la información de descarga (usuario y fecha) al final de la hoja de cabecera."""
    row = ws_cabecera.max_row + 2
    ws_cabecera[f'A{row}'] = "Descargado por:"
    ws_cabecera[f'A{row}'].font = Font(bold=True)
    ws_cabecera[f'B{row}'] = username

    row += 1
    ws_cabecera[f'A{row}'] = "Fecha de descarga:"
    ws_cabecera[f'A{row}'].font = Font(bold=True)
    ws_cabecera[f'B{row}'] = ahora_naive().strftime("%Y-%m-%d %H:%M:%S")


def _guardar_y_nombrar(wb, cabecera, pedido_id, username):
    """Guarda el libro en memoria y calcula el nombre de archivo. Retorna (buffer, filename)."""
    excel_buffer = io.BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)

    # Nombre del archivo (\w ya incluye '_', por eso no se repite en la clase)
    numero_pedido = cabecera.get("numero_pedido", pedido_id)
    numero_pedido_safe = re.sub(r'[^\w\-\. ]', '_', numero_pedido)
    filename = f"pedido_{numero_pedido_safe}_{ahora_naive().strftime('%Y%m%d_%H%M%S')}.xlsx"

    logger.info(f"✅ Excel generado para pedido {pedido_id} ({numero_pedido}) por usuario {username}")

    return excel_buffer, filename


def generate_pedido_excel(conn, pedido_id: str, pedido_data: dict, username: str = "UNKNOWN") -> Tuple[io.BytesIO, str]:
    """
    Genera un archivo Excel con la información completa del pedido.

    Args:
        conn: Conexión a la base de datos
        pedido_id: UUID del pedido
        pedido_data: Diccionario con datos del pedido (cabecera, detalles, etc.)
        username: Nombre del usuario que descarga (para metadata)

    Returns:
        Tuple con (BytesIO con contenido del Excel, nombre del archivo sugerido)

    Raises:
        Exception: Si hay error en la generación del Excel
    """
    cabecera = pedido_data.get("cabecera", {})
    estado_id = cabecera.get("estado_id")

    # Determinar si usamos datos de distribucion_confirmada o pedido_detalle
    usar_distribucion_confirmada = estado_id == ESTADO_REDISTRIBUCION

    # Crear libro de Excel
    wb = Workbook()
    default_sheet = wb.active
    if default_sheet is not None:
        wb.remove(default_sheet)  # Eliminar la hoja por defecto

    estilos = _crear_estilos()

    # === HOJA 1: INFORMACIÓN DE CABECERA ===
    ws_cabecera = _escribir_hoja_cabecera(wb, pedido_id, cabecera, estilos)

    # === HOJA 2: DETALLES DE ARTÍCULOS ===
    detalles_para_distribucion = _escribir_hoja_detalles(
        wb, conn, pedido_id, pedido_data, usar_distribucion_confirmada, estilos
    )

    # === HOJA 3: DISTRIBUCIÓN POR TIENDAS ===
    _escribir_hoja_distribucion(wb, detalles_para_distribucion, usar_distribucion_confirmada, estilos)

    # Agregar información de descarga en la hoja de cabecera
    _agregar_info_descarga(ws_cabecera, username)

    # Guardar el libro de Excel en memoria y calcular nombre
    return _guardar_y_nombrar(wb, cabecera, pedido_id, username)
