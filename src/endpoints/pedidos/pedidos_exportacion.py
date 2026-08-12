"""
Endpoints de exportación de pedidos.
"""

import io
import logging
import uuid
from typing import Dict
from src.utils.timezone import ahora_naive
from fastapi import FastAPI, Depends, HTTPException, Path, Query, status
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.pedido_estados import ESTADO_GESTIONAR_PEDIDO, ESTADO_CONFIRMADO_ENVIADO
from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission

logger = logging.getLogger(__name__)

_PERM_ODCSAP_VIEW = 'odcsap.view'
_PERM_MABEL_VIEW = 'mabel.view'
DESC_UUID_PEDIDO = "UUID del pedido"
MEDIA_TYPE_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _agregar_logo_roland(ws) -> None:
    """Inserta el logo ROLAND en la hoja si el archivo existe."""
    import os
    from openpyxl.drawing.image import Image as XlImage

    logo_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "roland_logo.png"))
    if not os.path.exists(logo_path):
        logger.warning(f"⚠️ Logo ROLAND no encontrado en {logo_path}")
        return
    img = XlImage(logo_path)
    img.width = 180
    img.height = 45
    ws.add_image(img, "B3")


def _formatear_fecha_pedido(fecha_pedido) -> str:
    """Normaliza la fecha de pedido, agregando hora 00:00:00 si viene sin hora (10 caracteres)."""
    if not fecha_pedido:
        return ""
    if len(str(fecha_pedido)) == 10:
        fecha_pedido = f"{fecha_pedido} 00:00:00"
    return str(fecha_pedido)


def _escribir_cabecera_pedido(ws, cabecera: dict, bold_font) -> None:
    """Escribe las etiquetas y valores del formulario de cabecera (filas 1-11)."""
    ws["D1"] = "PEDIDO ROLAND NO."
    ws["E1"] = cabecera.get("numero_pedido", "")
    ws["D2"] = "FECHA DE PEDIDO"
    ws["E2"] = _formatear_fecha_pedido(cabecera.get("fecha_pedido", ""))
    ws["D3"] = "FECHA DE ENTREGA"
    ws["E3"] = cabecera.get("fecha_entrega", "")
    ws["D4"] = "FORMA DE PAGO"
    ws["E4"] = cabecera.get("forma_pago", "")
    ws["D6"] = "MENSAJE"
    ws["E6"] = cabecera.get("mensaje", "")
    ws["D7"] = "NOMBRE PROVEEDOR"
    ws["E7"] = cabecera.get("proveedor_nombre", "")
    ws["D8"] = "COMPRADOR NOMBRE"
    ws["E8"] = cabecera.get("comprador_nombre", "")
    ws["D9"] = "COD COMPRADOR"
    ws["E9"] = cabecera.get("comprador_codigo", "")
    ws["D10"] = "ORIGEN TRASLADO"
    ws["E10"] = cabecera.get("origen_traslado", "")
    ws["D11"] = "SERIE"
    ws["E11"] = cabecera.get("serie", "")
    for row_num in (1, 2, 3, 4, 6, 7, 8, 9, 10, 11):
        ws[f"D{row_num}"].font = bold_font


def _aplicar_estilos_cabecera(ws, label_fill, label_font, thin_border) -> None:
    """Aplica relleno, fuente y bordes a las celdas del formulario de cabecera."""
    for row_num in range(2, 12):
        if row_num != 5:
            cell = ws[f"D{row_num}"]
            cell.fill = label_fill
            cell.font = label_font
    for row_num in (1, 2, 3, 4, 6, 7, 8, 9, 10, 11):
        ws[f"D{row_num}"].border = thin_border
        ws[f"E{row_num}"].border = thin_border


def _escribir_encabezados_tabla(ws, bold_font, thin_border) -> None:
    """Escribe y estiliza los encabezados de la tabla de detalle (fila 13)."""
    headers = {
        "B13": "CODIGO INTERNO", "C13": "MARCA", "D13": "CODIGO DE BARRAS",
        "E13": "DESCRIPCION SAP", "F13": "PACK", "G13": "PRECIO DE LISTA",
        "H13": "DSCTO", "I13": "PVP", "J13": "TOTAL",
    }
    table_header_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    for cell_ref, header_text in headers.items():
        cell = ws[cell_ref]
        cell.value = header_text
        cell.font = bold_font
        cell.fill = table_header_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border


def _set_valor_numerico_celda(ws, col: str, row: int, val) -> None:
    """Asigna un valor numérico a una celda, con fallback a texto si no es convertible."""
    if val is None:
        ws[f"{col}{row}"] = ""
        return
    try:
        ws[f"{col}{row}"] = float(val)
    except (ValueError, TypeError):
        ws[f"{col}{row}"] = val


def _escribir_fila_detalle(ws, row: int, detalle: dict, marca_excel: str, thin_border) -> None:
    """Escribe una fila de detalle de producto en la tabla."""
    ws[f"B{row}"] = detalle.get("codigo_interno", "")
    ws[f"C{row}"] = marca_excel
    ws[f"D{row}"] = detalle.get("codigo_barras", "")
    ws[f"E{row}"] = detalle.get("descripcion_sap", "")
    ws[f"F{row}"] = detalle.get("pack", "")
    _set_valor_numerico_celda(ws, "G", row, detalle.get("costo_doc_sin_iva"))
    _set_valor_numerico_celda(ws, "H", row, detalle.get("descuento_1"))
    ws[f"H{row}"].number_format = '0.00%'
    _set_valor_numerico_celda(ws, "I", row, detalle.get("pvp"))
    _set_valor_numerico_celda(ws, "J", row, detalle.get("total"))
    for col_letter in ("B", "C", "D", "E", "F", "G", "H", "I", "J"):
        ws[f"{col_letter}{row}"].border = thin_border


def _escribir_detalles_productos(ws, detalles: list, cabecera: dict, thin_border) -> None:
    """Escribe todas las filas de detalle de productos a partir de la fila 14."""
    marca_por_origen = {"RL-CD": "ROLAND", "OUT-CD": "DESCUENTON", "RG-CD": "REGIONS"}
    origen_traslado = (cabecera.get("origen_traslado") or "").strip().upper()
    marca_excel = marca_por_origen.get(origen_traslado, "")
    for idx, detalle in enumerate(detalles):
        _escribir_fila_detalle(ws, 14 + idx, detalle, marca_excel, thin_border)


def _escribir_fila_total(ws, detalles: list, bold_font, thin_border) -> None:
    """Escribe la fila de totales al final de la tabla de detalle, si hay productos."""
    if not detalles:
        return
    ultima_fila_datos = 14 + len(detalles) - 1
    fila_total = ultima_fila_datos + 1
    ws[f"I{fila_total}"] = "TOTAL"
    ws[f"I{fila_total}"].font = bold_font
    ws[f"I{fila_total}"].alignment = Alignment(horizontal="right")
    ws[f"I{fila_total}"].border = thin_border
    ws[f"J{fila_total}"] = f"=SUM(J14:J{ultima_fila_datos})"
    ws[f"J{fila_total}"].font = bold_font
    ws[f"J{fila_total}"].border = thin_border


def _ajustar_anchos_columnas(ws) -> None:
    """Ajusta el ancho de las columnas de la tabla de detalle."""
    anchos = {"B": 18, "C": 12, "D": 18, "E": 50, "F": 8, "G": 16, "H": 10, "I": 10, "J": 10}
    for col, ancho in anchos.items():
        ws.column_dimensions[col].width = ancho


def _generar_excel_pedido(cabecera: dict, detalles: list) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "datos"

    bold_font = Font(bold=True)
    label_fill = PatternFill(start_color="588894", end_color="588894", fill_type="solid")
    label_font = Font(bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    _agregar_logo_roland(ws)
    _escribir_cabecera_pedido(ws, cabecera, bold_font)
    _aplicar_estilos_cabecera(ws, label_fill, label_font, thin_border)
    _escribir_encabezados_tabla(ws, bold_font, thin_border)
    _escribir_detalles_productos(ws, detalles, cabecera, thin_border)
    _escribir_fila_total(ws, detalles, bold_font, thin_border)
    _ajustar_anchos_columnas(ws)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    excel_bytes = output.getvalue()
    output.close()
    return excel_bytes


def _logic_exportar_pedido_para_proveedor(pedido_id: str):
    try:
        from src.database.services.pedido_proveedor_service import PedidoProveedorService
        service = PedidoProveedorService()
        excel_bytes = service.exportar_pedido_para_proveedor(pedido_id)
        return Response(
            content=excel_bytes,
            media_type=MEDIA_TYPE_EXCEL,
            headers={"Content-Disposition": f'attachment; filename="pedido_proveedor_{pedido_id}_{ahora_naive().strftime("%Y%m%d")}.xlsx"'}
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Error al exportar pedido para proveedor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al exportar pedido: {str(e)}")

def _logic_exportar_pedido_plano_mba(pedido_id: str, codigo_cliente: str, codigo_subcliente: str, moneda: str, vendedor: str, numero_pedido_mba: int, consolidado: bool, incluir_encabezado: bool):
    try:
        from src.database.services.mba_pedido_exporter import MBAPedidoExporter, MBAExportConfig
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            try:
                uuid.UUID(pedido_id)
                pedido = repo.get_pedido_completo(pedido_id)
                if not pedido:
                    raise ValueError(f"Pedido no encontrado: {pedido_id}")
                pedido_id_real = pedido_id
                numero_pedido = pedido["cabecera"].get("numero_pedido", pedido_id[:8])
            except (ValueError, TypeError):
                pedido = repo.get_pedido_completo_por_numero(pedido_id)
                if not pedido:
                    raise ValueError(f"Pedido no encontrado: {pedido_id}")
                pedido_id_real = pedido["cabecera"]["pedido_id"]
                numero_pedido = pedido_id

        cabecera = pedido.get("cabecera", {})
        estado_id = cabecera.get("estado_id")
        if estado_id != ESTADO_CONFIRMADO_ENVIADO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "estado_no_permitido",
                    "message": f"El pedido debe estar en estado CONFIRMADO Y ENVIADO para generar el TXT MBA3. Estado actual: {cabecera.get('estado_nombre', 'Desconocido')}"
                }
            )

        config = MBAExportConfig(
            codigo_cliente=codigo_cliente, codigo_subcliente=codigo_subcliente, moneda=moneda,
            vendedor=vendedor, numero_pedido_temporal=numero_pedido_mba,
        )
        exporter = MBAPedidoExporter()
        if consolidado:
            file_bytes = exporter.exportar_pedido_formato_mba_consolidado(
                pedido_id=pedido_id_real, config=config, incluir_encabezado=incluir_encabezado)
        else:
            file_bytes = exporter.exportar_pedido_formato_mba(
                pedido_id=pedido_id_real, config=config, incluir_encabezado=incluir_encabezado)
        
        numero_pedido_limpio = numero_pedido.replace(" ", "_").replace("-", "_").replace("/", "_")
        filename = f"pedido_mba_{numero_pedido_limpio}_{ahora_naive().strftime('%Y%m%d')}.txt"
        logger.info(f"✅ Pedido {numero_pedido} exportado a formato MBA: {filename}")
        
        return Response(
            content=file_bytes, media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al exportar pedido plano para MBA: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al exportar pedido: {str(e)}")


def _logic_descargar_pedido(pedido_id: str):
    try:
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido_data = repo.get_pedido_completo(pedido_id)

            if not pedido_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"error": "not_found", "message": "Pedido no encontrado"}
                )

            cabecera = pedido_data.get("cabecera", {})
            estado_id = cabecera.get("estado_id")

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
            excel_bytes = _generar_excel_pedido(cabecera, detalles)

            logger.info(f"✅ Pedido {cabecera.get('numero_pedido', pedido_id)} descargado como Excel ({len(detalles)} productos)")

            return Response(
                content=excel_bytes,
                media_type=MEDIA_TYPE_EXCEL,
                headers={"Content-Disposition": 'attachment; filename="Descargar Pedido.xlsx"'}
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al descargar pedido: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": f"Error interno al generar Excel: {str(e)}"})

def _logic_descargar_pedido_original(pedido_id: str):
    try:
        from src.database.repositories.pedido_original_repository import PedidoOriginalRepository
        with get_db_connection_context() as conn:
            original_repo = PedidoOriginalRepository(conn)
            pedido_original = original_repo.get_pedido_original(pedido_id)

            if not pedido_original:
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
            excel_bytes = _generar_excel_pedido(cabecera, detalles)

            logger.info(f"✅ Pedido ORIGINAL {cabecera.get('numero_pedido', pedido_id)} descargado como Excel ({len(detalles)} productos)")

            return Response(
                content=excel_bytes,
                media_type=MEDIA_TYPE_EXCEL,
                headers={"Content-Disposition": 'attachment; filename="Descargar Pedido Original.xlsx"'}
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al descargar pedido original: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": f"Error interno al generar Excel original: {str(e)}"})


def register_exportacion_endpoints(app: FastAPI):
    """Registra los endpoints de exportación de pedidos."""
    
    @app.get("/api/pedidos/{pedido_id}/exportar-para-proveedor", tags=["Pedidos - Proveedor"])
    async def exportar_pedido_para_proveedor(
        pedido_id: str = Path(..., description=DESC_UUID_PEDIDO),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL_VIEW))
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
        return _logic_exportar_pedido_para_proveedor(pedido_id)
    
    @app.get("/api/pedidos/{pedido_id}/exportar-plano-mba", tags=["Pedidos - El Rayo"])
    async def exportar_pedido_plano_mba(
        pedido_id: str = Path(..., description="UUID del pedido o número de pedido"),
        codigo_cliente: str = Query("CLI1795", description="Código de cliente MBA (por defecto CLI1795)"),
        codigo_subcliente: str = Query("", description="Código de subcliente MBA (dejar vacío si no aplica)"),
        moneda: str = Query("US", description="Moneda/divisa local (por defecto US dólar)"),
        vendedor: str = Query("", description="Código de vendedor MBA"),
        numero_pedido_mba: int = Query(1, ge=1, description="Número de pedido temporal para agrupar líneas en MBA (col. B)"),
        consolidado: bool = Query(True, description="Si True, consolida cantidades por producto; si False, una línea por tienda/sucursal"),
        incluir_encabezado: bool = Query(True, description="Incluir las 19 líneas de encabezado del formato MBA"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_ODCSAP_VIEW))
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
        - Una línea por producto, con la cantidad consolidada de todas sus tiendas
          (o una línea por combinación producto-tienda si se pide `consolidado=false`)
        
        ## Parámetros de configuración (valores por defecto para "Descargar para MBA")

        Del sistema se toman: Pedido Manual, Orden Compra Cliente, Código Producto,
        Precio Final. Columnas fijas: A=secuencial, B=número pedido (agrupa),
        C=CLI1795, G=moneda US, AI=secuencial.

        | Parámetro | Default | Descripción |
        |-----------|---------|-------------|
        | codigo_cliente | CLI1795 | Código del cliente en MBA |
        | codigo_subcliente | (vacío) | Subcategoría del cliente (opcional) |
        | moneda | US | Divisa local (dólar) |
        | vendedor | (vacío) | Código del vendedor |

        Requiere que el pedido esté en estado **CONFIRMADO Y ENVIADO** (la ODC ya fue
        enviada y aceptada por SAP), ya que la columna 12 depende del DocNum de SAP.

        Columna H (Bodega) es fija: siempre se exporta como `BPT`.
        Columna 20 (Sucursal) es fija: siempre se exporta como `PRI`.
        Columna 10 (Pedido Manual): número de pedido interno.
        Columna 12 (Orden Compra Cliente): DocNum de la Orden de Compra ya enviada a SAP
        (tabla orden_compra_cabecera.numero_oc_sap). Vacía si el pedido no tiene una OC
        con DocNum registrado.
        Columnas 5 y 6 (Fecha Pedido / Fecha Entrega): ambas usan la fecha en que el
        pedido pasó a estado CONFIRMADO POR EL RAYO (clic en "Confirmar" en el detalle
        del pedido), no la fecha capturada originalmente en el Excel. Si el pedido no
        tiene ese registro en la bitácora de estados, se exportan vacías (00/00/0000).
        
        ## Modos de exportación

        - **consolidado=True** (predeterminado): Consolida las cantidades y genera una
          línea por producto. Como la columna Sucursal es fija (`PRI`), una línea por
          tienda ya no aporta información distinguible entre tiendas.
        - **consolidado=False**: Genera una línea por cada combinación producto-tienda
          (sin agrupar), por si se necesita esa granularidad para otro fin.
        
        ## Ejemplo de línea generada
        
        ```
        91	3	CLI0495	GO05	29/10/2025	31/10/2025	US	BPT	JPC	CQ287341		1524						TRUE	FALSE	PRI	R469.911.CCL	6	FALSE	6.16	TRUE								0	FALSE	91
        ```
        
        Returns:
            Archivo .txt descargable en formato MBA
        """
        return _logic_exportar_pedido_plano_mba(pedido_id, codigo_cliente, codigo_subcliente, moneda, vendedor, numero_pedido_mba, consolidado, incluir_encabezado)

    @app.get("/api/pedidos/{pedido_id}/descargar-pedido", tags=["Pedidos - Exportación"])
    async def descargar_pedido(
        pedido_id: str = Path(..., description=DESC_UUID_PEDIDO),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_MABEL_VIEW, _PERM_ODCSAP_VIEW]))
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
        return _logic_descargar_pedido(pedido_id)

    # ========================================================================
    # Descargar Pedido Original (desde tablas pedido_original)
    # ========================================================================
    @app.get("/api/pedidos/{pedido_id}/descargar-pedido-original", tags=["Pedidos - Exportación"])
    async def descargar_pedido_original(
        pedido_id: str = Path(..., description=DESC_UUID_PEDIDO),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_MABEL_VIEW, _PERM_ODCSAP_VIEW]))
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
        return _logic_descargar_pedido_original(pedido_id)
