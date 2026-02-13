"""
Endpoints de exportación de pedidos.
"""

import io
import logging
import uuid
from typing import Dict
from datetime import datetime

from src.utils.timezone import ahora_naive
from fastapi import FastAPI, Depends, HTTPException, Path, Query, status
from fastapi.responses import Response

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.pedido_estados import ESTADO_GESTIONAR_PEDIDO
from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission

logger = logging.getLogger(__name__)


def register_exportacion_endpoints(app: FastAPI):
    """Registra los endpoints de exportación de pedidos."""
    
    @app.get("/api/pedidos/{pedido_id}/exportar-para-proveedor", tags=["Pedidos - Proveedor"])
    async def exportar_pedido_para_proveedor(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Exporta un pedido a Excel para que el proveedor lo complete.
        
        **Formato exportado:**
        - Hoja RESUMEN: Totales solicitados por producto (consolidado) - **OBLIGATORIO completar**
        - Hoja DETALLE_TIENDAS: Distribución por tienda - **OPCIONAL** (solo si el proveedor quiere especificar)
        - Hoja INSTRUCCIONES: Guía de uso
        
        **Modelo de respuesta:**
        - El proveedor responde principalmente por PRODUCTO (consolidado)
        - Puede opcionalmente especificar distribución por tienda
        - Si no especifica por tienda, el sistema distribuye proporcionalmente
        
        Returns:
            Archivo Excel descargable
        """
        try:
            from src.database.services.pedido_proveedor_service import PedidoProveedorService
            
            service = PedidoProveedorService()
            excel_bytes = service.exportar_pedido_para_proveedor(pedido_id)
            
            return Response(
                content=excel_bytes,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": f'attachment; filename="pedido_proveedor_{pedido_id}_{ahora_naive().strftime("%Y%m%d")}.xlsx"'
                }
            )
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"❌ Error al exportar pedido para proveedor: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al exportar pedido: {str(e)}"
            )
    
    @app.get("/api/pedidos/{pedido_id}/exportar-plano-mba", tags=["Pedidos - El Rayo"])
    async def exportar_pedido_plano_mba(
        pedido_id: str = Path(..., description="UUID del pedido o número de pedido"),
        codigo_cliente: str = Query("", description="Código de cliente MBA (ej: CLI0495)"),
        codigo_subcliente: str = Query("", description="Código de subcliente MBA (ej: GO05)"),
        moneda: str = Query("US", description="Código de moneda (ej: US, DOP)"),
        bodega: str = Query("", description="Código de bodega MBA (si vacío, usa origen_traslado del pedido)"),
        vendedor: str = Query("", description="Código de vendedor MBA (ej: JPC)"),
        numero_pedido_mba: int = Query(1, ge=1, description="Número de pedido temporal para agrupar líneas en MBA"),
        consolidado: bool = Query(False, description="Si True, consolida cantidades por producto; si False, genera una línea por tienda/sucursal"),
        incluir_encabezado: bool = Query(True, description="Incluir las 19 líneas de encabezado del formato MBA"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('odcsap.view'))
    ):
        """
        Exporta un pedido en formato plano (.txt) para importar en MBA.
        
        **HU-08**: Permite a usuarios de El Rayo descargar el pedido en archivo plano
        para subirlo en el sistema MBA.
        
        ## Formato de archivo
        
        Genera un archivo .txt compatible con el formato de importación de 
        **Pedidos de Clientes** de MBA (ENTERPRISE SOFTWARE SOLUTIONS):
        
        - **35 columnas** separadas por TAB
        - **19 líneas de encabezado** (se eliminan automáticamente al importar en MBA)
        - Una línea por cada combinación producto-tienda (o consolidado por producto)
        
        ## Parámetros de configuración
        
        Los siguientes campos deben configurarse según los datos del cliente en MBA:
        
        | Parámetro | Ejemplo | Descripción |
        |-----------|---------|-------------|
        | codigo_cliente | CLI0495 | Código del cliente en MBA |
        | codigo_subcliente | GO05 | Subcategoría del cliente (opcional) |
        | moneda | US | Código de moneda (US, DOP, etc.) |
        | bodega | BPT | Código de bodega en MBA |
        | vendedor | JPC | Código del vendedor |
        
        ## Modos de exportación
        
        - **consolidado=False** (predeterminado): Genera una línea por cada tienda/sucursal.
          Útil cuando el pedido tiene distribución por tiendas.
        - **consolidado=True**: Consolida las cantidades y genera una línea por producto.
          Útil cuando no se necesita distinguir por tienda.
        
        ## Ejemplo de línea generada
        
        ```
        91	3	CLI0495	GO05	29/10/2025	31/10/2025	US	BPT	JPC			CQ287341						TRUE	FALSE	PRI	R469.911.CCL	6	FALSE	6.16	TRUE								0	FALSE	91
        ```
        
        Returns:
            Archivo .txt descargable en formato MBA
        """
        try:
            from src.database.services.mba_pedido_exporter import MBAPedidoExporter, MBAExportConfig
            
            # Determinar si es UUID o numero_pedido
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                try:
                    # Si es un UUID válido, intentar obtener por pedido_id
                    uuid.UUID(pedido_id)
                    pedido = repo.get_pedido_completo(pedido_id)
                    if not pedido:
                        raise ValueError(f"Pedido no encontrado: {pedido_id}")
                    pedido_id_real = pedido_id
                    numero_pedido = pedido["cabecera"].get("numero_pedido", pedido_id[:8])
                except (ValueError, TypeError):
                    # No es UUID, intentar obtener por numero_pedido
                    pedido = repo.get_pedido_completo_por_numero(pedido_id)
                    if not pedido:
                        raise ValueError(f"Pedido no encontrado: {pedido_id}")
                    pedido_id_real = pedido["cabecera"]["pedido_id"]
                    numero_pedido = pedido_id
            
            # Configurar exportación
            config = MBAExportConfig(
                codigo_cliente=codigo_cliente,
                codigo_subcliente=codigo_subcliente,
                moneda=moneda,
                bodega=bodega,
                vendedor=vendedor,
                numero_pedido_temporal=numero_pedido_mba,
            )
            
            # Exportar según el modo seleccionado
            exporter = MBAPedidoExporter()
            
            if consolidado:
                file_bytes = exporter.exportar_pedido_formato_mba_consolidado(
                    pedido_id=pedido_id_real,
                    config=config,
                    incluir_encabezado=incluir_encabezado
                )
            else:
                file_bytes = exporter.exportar_pedido_formato_mba(
                    pedido_id=pedido_id_real,
                    config=config,
                    incluir_encabezado=incluir_encabezado
                )
            
            # Limpiar número de pedido para nombre de archivo
            numero_pedido_limpio = numero_pedido.replace(" ", "_").replace("-", "_").replace("/", "_")
            filename = f"pedido_mba_{numero_pedido_limpio}_{ahora_naive().strftime('%Y%m%d')}.txt"
            
            logger.info(f"✅ Pedido {numero_pedido} exportado a formato MBA: {filename}")
            
            return Response(
                content=file_bytes,
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"❌ Error al exportar pedido plano para MBA: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al exportar pedido: {str(e)}"
            )

    @app.get("/api/pedidos/{pedido_id}/descargar-pedido", tags=["Pedidos - Exportación"])
    async def descargar_pedido(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['mabel.view', 'odcsap.view']))
    ):
        """
        Descarga un pedido como archivo Excel con el formato de "Descargar Pedido".

        Genera un archivo Excel (.xlsx) con una sola hoja llamada "datos" que combina
        una cabecera tipo formulario con una tabla de detalle de productos.

        **Uso:**
        - Interfaz: Detalle del Pedido (`/pedidos/{pedido_id}`)
        - Botón: "Descargar Pedido"
        - Estado requerido: **GESTIONAR PEDIDO (3)** o superior

        **Estructura del Excel:**
        - Filas 1-4: Cabecera del pedido (columnas D y E)
        - Filas 5-11: Información complementaria (columnas D y E)
        - Fila 13: Encabezados de la tabla de productos (columnas B a J)
        - Fila 14+: Datos de productos

        **Respuestas:**
        - **200**: Archivo Excel descargado correctamente
        - **400**: Pedido no está en estado GESTIONAR PEDIDO o superior
        - **404**: Pedido no encontrado
        """
        try:
            import os
            from openpyxl import Workbook
            from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
            from openpyxl.drawing.image import Image as XlImage

            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)

                # Obtener pedido completo
                pedido_data = repo.get_pedido_completo(pedido_id)

                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={"error": "not_found", "message": "Pedido no encontrado"}
                    )

                cabecera = pedido_data.get("cabecera", {})
                estado_id = cabecera.get("estado_id")

                # Validar que esté en estado GESTIONAR PEDIDO (3) o superior
                if estado_id is None or int(estado_id) < ESTADO_GESTIONAR_PEDIDO:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "estado_no_permitido",
                            "message": f"El pedido debe estar en estado GESTIONAR PEDIDO o superior para descargar. "
                                       f"Estado actual: {cabecera.get('estado_nombre', 'Desconocido')}"
                        }
                    )

                detalles = pedido_data.get("detalles", [])

                # Crear libro de Excel
                wb = Workbook()
                ws = wb.active
                assert ws is not None  # wb.active always returns a worksheet for new workbooks
                ws.title = "datos"

                # --- Estilos ---
                bold_font = Font(bold=True)
                label_fill = PatternFill(start_color="588894", end_color="588894", fill_type="solid")
                label_font = Font(bold=True, color="FFFFFF")
                thin_border = Border(
                    left=Side(style="thin"),
                    right=Side(style="thin"),
                    top=Side(style="thin"),
                    bottom=Side(style="thin"),
                )

                # --- Logo ROLAND en B3 ---
                logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "roland_logo.png")
                logo_path = os.path.normpath(logo_path)
                if os.path.exists(logo_path):
                    img = XlImage(logo_path)
                    # Ajustar tamaño para que encaje bien en la celda (~2.5 cm alto)
                    img.width = 180
                    img.height = 45
                    ws.add_image(img, "B3")
                else:
                    logger.warning(f"⚠️ Logo ROLAND no encontrado en {logo_path}")

                # --- 1. Cabecera del pedido (filas 1-4, columnas D y E) ---
                ws["D1"] = "PEDIDO ROLAND NO."
                ws["D1"].font = bold_font
                ws["E1"] = cabecera.get("numero_pedido", "")

                ws["D2"] = "FECHA DE PEDIDO"
                ws["D2"].font = bold_font
                fecha_pedido = cabecera.get("fecha_pedido", "")
                # Formatear fecha: si es solo fecha (YYYY-MM-DD), agregar 00:00:00
                if fecha_pedido and len(str(fecha_pedido)) == 10:
                    fecha_pedido = f"{fecha_pedido} 00:00:00"
                ws["E2"] = str(fecha_pedido) if fecha_pedido else ""

                ws["D3"] = "FECHA DE ENTREGA"
                ws["D3"].font = bold_font
                ws["E3"] = cabecera.get("fecha_entrega", "")

                ws["D4"] = "FORMA DE PAGO"
                ws["D4"].font = bold_font
                ws["E4"] = cabecera.get("forma_pago", "")

                # --- 2. Información complementaria (filas 5-11) ---
                # Fila 5: vacía (separador visual)

                ws["D6"] = "MENSAJE"
                ws["D6"].font = bold_font
                ws["E6"] = cabecera.get("mensaje", "")

                ws["D7"] = "NOMBRE PROVEEDOR"
                ws["D7"].font = bold_font
                ws["E7"] = cabecera.get("proveedor_nombre", "")

                ws["D8"] = "COMPRADOR NOMBRE"
                ws["D8"].font = bold_font
                ws["E8"] = cabecera.get("comprador_nombre", "")

                ws["D9"] = "COD COMPRADOR"
                ws["D9"].font = bold_font
                ws["E9"] = cabecera.get("comprador_codigo", "")

                ws["D10"] = "ORIGEN TRASLADO"
                ws["D10"].font = bold_font
                ws["E10"] = cabecera.get("origen_traslado", "")

                ws["D11"] = "SERIE"
                ws["D11"].font = bold_font
                ws["E11"] = cabecera.get("serie", "")

                # Aplicar color de fondo #588894 con texto blanco a D2:D11 (excepto D5 que va vacía)
                for row_num in range(2, 12):
                    if row_num == 5:
                        continue
                    cell = ws[f"D{row_num}"]
                    cell.fill = label_fill
                    cell.font = label_font

                # Bordes en la zona de cabecera e info complementaria (D:E, filas 1-4 y 6-11)
                for row_num in [1, 2, 3, 4, 6, 7, 8, 9, 10, 11]:
                    ws[f"D{row_num}"].border = thin_border
                    ws[f"E{row_num}"].border = thin_border

                # Fila 12: separador visual (vacía)

                # --- 3. Tabla de productos (desde fila 13) ---
                # Encabezados de la tabla (fila 13, columnas B a J)
                headers = {
                    "B13": "CODIGO INTERNO",
                    "C13": "MARCA",
                    "D13": "CODIGO DE BARRAS",
                    "E13": "DESCRIPCION SAP",
                    "F13": "PACK",
                    "G13": "PRECIO DE LISTA",
                    "H13": "DSCTO",
                    "I13": "PVP",
                    "J13": "TOTAL",
                }
                table_header_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
                for cell_ref, header_text in headers.items():
                    cell = ws[cell_ref]
                    cell.value = header_text
                    cell.font = bold_font
                    cell.fill = table_header_fill
                    cell.alignment = Alignment(horizontal="center")
                    cell.border = thin_border

                # Determinar marca a partir de ORIGEN TRASLADO de la cabecera
                MARCA_POR_ORIGEN = {
                    "RL-CD": "ROLAND",
                    "OUT-CD": "DESCUENTON",
                    "RG-CD": "REGIONS",
                }
                origen_traslado = (cabecera.get("origen_traslado") or "").strip().upper()
                marca_excel = MARCA_POR_ORIGEN.get(origen_traslado, "")

                # Datos de productos (desde fila 14)
                for idx, detalle in enumerate(detalles):
                    row = 14 + idx

                    ws[f"B{row}"] = detalle.get("codigo_interno", "")
                    ws[f"C{row}"] = marca_excel
                    ws[f"D{row}"] = detalle.get("codigo_barras", "")
                    ws[f"E{row}"] = detalle.get("descripcion_sap", "")
                    ws[f"F{row}"] = detalle.get("pack", "")

                    # PRECIO DE LISTA: costo_doc_sin_iva
                    costo = detalle.get("costo_doc_sin_iva")
                    if costo is not None:
                        try:
                            ws[f"G{row}"] = float(costo)
                        except (ValueError, TypeError):
                            ws[f"G{row}"] = costo
                    else:
                        ws[f"G{row}"] = ""

                    # DSCTO: descuento_1 (formato porcentaje)
                    descuento = detalle.get("descuento_1")
                    if descuento is not None:
                        try:
                            ws[f"H{row}"] = float(descuento)
                        except (ValueError, TypeError):
                            ws[f"H{row}"] = descuento
                    else:
                        ws[f"H{row}"] = ""
                    ws[f"H{row}"].number_format = '0.00%'

                    # PVP
                    pvp = detalle.get("pvp")
                    if pvp is not None:
                        try:
                            ws[f"I{row}"] = float(pvp)
                        except (ValueError, TypeError):
                            ws[f"I{row}"] = pvp
                    else:
                        ws[f"I{row}"] = ""

                    # TOTAL (cantidad solicitada)
                    total = detalle.get("total")
                    if total is not None:
                        try:
                            ws[f"J{row}"] = float(total)
                        except (ValueError, TypeError):
                            ws[f"J{row}"] = total
                    else:
                        ws[f"J{row}"] = ""

                    # Bordes en cada celda de la fila de producto (B a J)
                    for col_letter in ["B", "C", "D", "E", "F", "G", "H", "I", "J"]:
                        ws[f"{col_letter}{row}"].border = thin_border

                # --- Fila de TOTAL al final de la columna J ---
                if detalles:
                    ultima_fila_datos = 14 + len(detalles) - 1
                    fila_total = ultima_fila_datos + 1

                    ws[f"I{fila_total}"] = "TOTAL"
                    ws[f"I{fila_total}"].font = bold_font
                    ws[f"I{fila_total}"].alignment = Alignment(horizontal="right")
                    ws[f"I{fila_total}"].border = thin_border

                    ws[f"J{fila_total}"] = f"=SUM(J14:J{ultima_fila_datos})"
                    ws[f"J{fila_total}"].font = bold_font
                    ws[f"J{fila_total}"].border = thin_border

                # Ajustar anchos de columna para mejor legibilidad
                ws.column_dimensions["B"].width = 18
                ws.column_dimensions["C"].width = 12
                ws.column_dimensions["D"].width = 18
                ws.column_dimensions["E"].width = 50
                ws.column_dimensions["F"].width = 8
                ws.column_dimensions["G"].width = 16
                ws.column_dimensions["H"].width = 10
                ws.column_dimensions["I"].width = 10
                ws.column_dimensions["J"].width = 10

                # Guardar en memoria
                output = io.BytesIO()
                wb.save(output)
                output.seek(0)
                excel_bytes = output.getvalue()
                output.close()

                logger.info(
                    f"✅ Pedido {cabecera.get('numero_pedido', pedido_id)} descargado como Excel "
                    f"({len(detalles)} productos)"
                )

                return Response(
                    content=excel_bytes,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={
                        "Content-Disposition": 'attachment; filename="Descargar Pedido.xlsx"'
                    }
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al descargar pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={"error": "internal_error", "message": f"Error interno al generar Excel: {str(e)}"}
            )

    # ========================================================================
    # Descargar Pedido Original (desde tablas pedido_original)
    # ========================================================================
    @app.get("/api/pedidos/{pedido_id}/descargar-pedido-original", tags=["Pedidos - Exportación"])
    async def descargar_pedido_original(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['mabel.view', 'odcsap.view']))
    ):
        """
        Descarga el pedido **con los valores originales** (antes de ediciones).

        Genera un archivo Excel (.xlsx) idéntico en formato al de "Descargar Pedido"
        (logo ROLAND, colores corporativos, misma estructura), pero lee los datos
        de las tablas `pedido_original` y `pedido_detalle_original`, que almacenan
        una copia inmutable de los valores al momento del envío.

        **Uso:**
        - Interfaz: Detalle del Pedido (`/pedidos/{pedido_id}`)
        - Botón: "Descargar Pedido Original"
        - Estado requerido: **GESTIONAR PEDIDO (3)** o superior

        **Estructura del Excel:**
        - Filas 1-4: Cabecera del pedido (columnas D y E)
        - Filas 5-11: Información complementaria (columnas D y E)
        - Fila 13: Encabezados de la tabla de productos (columnas B a J)
        - Fila 14+: Datos de productos con valores originales

        **Respuestas:**
        - **200**: Archivo Excel descargado correctamente
        - **404**: Pedido no encontrado o sin snapshot original
        """
        try:
            import os
            from openpyxl import Workbook
            from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
            from openpyxl.drawing.image import Image as XlImage
            from src.database.repositories.pedido_original_repository import PedidoOriginalRepository

            with get_db_connection_context() as conn:
                original_repo = PedidoOriginalRepository(conn)
                pedido_original = original_repo.get_pedido_original(pedido_id)

                if not pedido_original:
                    # Verificar si el pedido existe para dar un mensaje más claro
                    repo = PedidoRepository(conn)
                    pedido_vivo = repo.get_pedido_completo(pedido_id)
                    if not pedido_vivo:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": "not_found", "message": "Pedido no encontrado"}
                        )
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "sin_snapshot_original",
                            "message": (
                                "No se encontraron datos originales para este pedido. "
                                "Solo los pedidos enviados después de la activación de esta "
                                "funcionalidad tienen snapshot original disponible."
                            )
                        }
                    )

                cabecera = pedido_original["cabecera"]
                detalles = pedido_original["detalles"]

                # Crear libro de Excel (mismo formato que descargar-pedido)
                wb = Workbook()
                ws = wb.active
                assert ws is not None  # wb.active always returns a worksheet for new workbooks
                ws.title = "datos"

                # --- Estilos ---
                bold_font = Font(bold=True)
                label_fill = PatternFill(start_color="588894", end_color="588894", fill_type="solid")
                label_font = Font(bold=True, color="FFFFFF")
                thin_border = Border(
                    left=Side(style="thin"),
                    right=Side(style="thin"),
                    top=Side(style="thin"),
                    bottom=Side(style="thin"),
                )

                # --- Logo ROLAND en B3 ---
                logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "roland_logo.png")
                logo_path = os.path.normpath(logo_path)
                if os.path.exists(logo_path):
                    img = XlImage(logo_path)
                    img.width = 180
                    img.height = 45
                    ws.add_image(img, "B3")
                else:
                    logger.warning(f"⚠️ Logo ROLAND no encontrado en {logo_path}")

                # --- 1. Cabecera del pedido (filas 1-4, columnas D y E) ---
                ws["D1"] = "PEDIDO ROLAND NO."
                ws["D1"].font = bold_font
                ws["E1"] = cabecera.get("numero_pedido", "")

                ws["D2"] = "FECHA DE PEDIDO"
                ws["D2"].font = bold_font
                fecha_pedido = cabecera.get("fecha_pedido", "")
                if fecha_pedido and len(str(fecha_pedido)) == 10:
                    fecha_pedido = f"{fecha_pedido} 00:00:00"
                ws["E2"] = str(fecha_pedido) if fecha_pedido else ""

                ws["D3"] = "FECHA DE ENTREGA"
                ws["D3"].font = bold_font
                ws["E3"] = cabecera.get("fecha_entrega", "")

                ws["D4"] = "FORMA DE PAGO"
                ws["D4"].font = bold_font
                ws["E4"] = cabecera.get("forma_pago", "")

                # --- 2. Información complementaria (filas 5-11) ---
                ws["D6"] = "MENSAJE"
                ws["D6"].font = bold_font
                ws["E6"] = cabecera.get("mensaje", "")

                ws["D7"] = "NOMBRE PROVEEDOR"
                ws["D7"].font = bold_font
                ws["E7"] = cabecera.get("proveedor_nombre", "")

                ws["D8"] = "COMPRADOR NOMBRE"
                ws["D8"].font = bold_font
                ws["E8"] = cabecera.get("comprador_nombre", "")

                ws["D9"] = "COD COMPRADOR"
                ws["D9"].font = bold_font
                ws["E9"] = cabecera.get("comprador_codigo", "")

                ws["D10"] = "ORIGEN TRASLADO"
                ws["D10"].font = bold_font
                ws["E10"] = cabecera.get("origen_traslado", "")

                ws["D11"] = "SERIE"
                ws["D11"].font = bold_font
                ws["E11"] = cabecera.get("serie", "")

                # Aplicar color de fondo #588894 con texto blanco a D2:D11
                for row_num in range(2, 12):
                    if row_num == 5:
                        continue
                    cell = ws[f"D{row_num}"]
                    cell.fill = label_fill
                    cell.font = label_font

                # Bordes en la zona de cabecera e info complementaria
                for row_num in [1, 2, 3, 4, 6, 7, 8, 9, 10, 11]:
                    ws[f"D{row_num}"].border = thin_border
                    ws[f"E{row_num}"].border = thin_border

                # --- 3. Tabla de productos (desde fila 13) ---
                headers = {
                    "B13": "CODIGO INTERNO",
                    "C13": "MARCA",
                    "D13": "CODIGO DE BARRAS",
                    "E13": "DESCRIPCION SAP",
                    "F13": "PACK",
                    "G13": "PRECIO DE LISTA",
                    "H13": "DSCTO",
                    "I13": "PVP",
                    "J13": "TOTAL",
                }
                table_header_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
                for cell_ref, header_text in headers.items():
                    cell = ws[cell_ref]
                    cell.value = header_text
                    cell.font = bold_font
                    cell.fill = table_header_fill
                    cell.alignment = Alignment(horizontal="center")
                    cell.border = thin_border

                # Determinar marca a partir de ORIGEN TRASLADO de la cabecera
                MARCA_POR_ORIGEN = {
                    "RL-CD": "ROLAND",
                    "OUT-CD": "DESCUENTON",
                    "RG-CD": "REGIONS",
                }
                origen_traslado = (cabecera.get("origen_traslado") or "").strip().upper()
                marca_excel = MARCA_POR_ORIGEN.get(origen_traslado, "")

                # Datos de productos (desde fila 14) — valores ORIGINALES
                for idx, detalle in enumerate(detalles):
                    row = 14 + idx

                    ws[f"B{row}"] = detalle.get("codigo_interno", "")
                    ws[f"C{row}"] = marca_excel
                    ws[f"D{row}"] = detalle.get("codigo_barras", "")
                    ws[f"E{row}"] = detalle.get("descripcion_sap", "")
                    ws[f"F{row}"] = detalle.get("pack", "")

                    costo = detalle.get("costo_doc_sin_iva")
                    if costo is not None:
                        try:
                            ws[f"G{row}"] = float(costo)
                        except (ValueError, TypeError):
                            ws[f"G{row}"] = costo
                    else:
                        ws[f"G{row}"] = ""

                    descuento = detalle.get("descuento_1")
                    if descuento is not None:
                        try:
                            ws[f"H{row}"] = float(descuento)
                        except (ValueError, TypeError):
                            ws[f"H{row}"] = descuento
                    else:
                        ws[f"H{row}"] = ""
                    ws[f"H{row}"].number_format = '0.00%'

                    pvp = detalle.get("pvp")
                    if pvp is not None:
                        try:
                            ws[f"I{row}"] = float(pvp)
                        except (ValueError, TypeError):
                            ws[f"I{row}"] = pvp
                    else:
                        ws[f"I{row}"] = ""

                    total = detalle.get("total")
                    if total is not None:
                        try:
                            ws[f"J{row}"] = float(total)
                        except (ValueError, TypeError):
                            ws[f"J{row}"] = total
                    else:
                        ws[f"J{row}"] = ""

                    for col_letter in ["B", "C", "D", "E", "F", "G", "H", "I", "J"]:
                        ws[f"{col_letter}{row}"].border = thin_border

                # --- Fila de TOTAL al final de la columna J ---
                if detalles:
                    ultima_fila_datos = 14 + len(detalles) - 1
                    fila_total = ultima_fila_datos + 1

                    ws[f"I{fila_total}"] = "TOTAL"
                    ws[f"I{fila_total}"].font = bold_font
                    ws[f"I{fila_total}"].alignment = Alignment(horizontal="right")
                    ws[f"I{fila_total}"].border = thin_border

                    ws[f"J{fila_total}"] = f"=SUM(J14:J{ultima_fila_datos})"
                    ws[f"J{fila_total}"].font = bold_font
                    ws[f"J{fila_total}"].border = thin_border

                # Ajustar anchos de columna
                ws.column_dimensions["B"].width = 18
                ws.column_dimensions["C"].width = 12
                ws.column_dimensions["D"].width = 18
                ws.column_dimensions["E"].width = 50
                ws.column_dimensions["F"].width = 8
                ws.column_dimensions["G"].width = 16
                ws.column_dimensions["H"].width = 10
                ws.column_dimensions["I"].width = 10
                ws.column_dimensions["J"].width = 10

                # Guardar en memoria
                output = io.BytesIO()
                wb.save(output)
                output.seek(0)
                excel_bytes = output.getvalue()
                output.close()

                logger.info(
                    f"✅ Pedido ORIGINAL {cabecera.get('numero_pedido', pedido_id)} descargado como Excel "
                    f"({len(detalles)} productos)"
                )

                return Response(
                    content=excel_bytes,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={
                        "Content-Disposition": 'attachment; filename="Descargar Pedido Original.xlsx"'
                    }
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al descargar pedido original: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={"error": "internal_error", "message": f"Error interno al generar Excel original: {str(e)}"}
            )
