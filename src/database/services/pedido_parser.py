"""
Parser para extraer datos crudos de archivos Excel de pedidos.

Responsabilidad: Solo parsing técnico - lee Excel y extrae datos sin lógica de negocio.
NO normaliza, NO consolida, NO valida reglas de negocio.
"""

import logging
import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime
import io

logger = logging.getLogger(__name__)


class PedidoParser:
    """
    Parser para archivos Excel de pedidos.
    
    Extrae datos crudos del Excel sin aplicar lógica de negocio.
    """
    
    def parsear_excel_pedido(
        self,
        file_content: bytes,
        hoja_cabecera: str = "CABECERA_PEDIDO",
        hoja_detalle: str = "DETALLE_ARTICULO"
    ) -> Dict[str, Any]:
        """
        Parsea un archivo Excel de pedido (FASE 1 - TAREA 2).
        
        Formato esperado:
        - Hoja 1: CABECERA_PEDIDO (formato clave-valor: Campo | Valor | Ejemplo)
        - Hoja 2: DETALLE_ARTICULO (formato tabular con headers)
        
        Solo parsing técnico: lee, normaliza y valida estructura.
        NO aplica reglas de negocio, NO consolida duplicados.
        
        Args:
            file_content: Contenido del archivo Excel en bytes
            hoja_cabecera: Nombre de la hoja de cabecera (default: "CABECERA_PEDIDO")
            hoja_detalle: Nombre de la hoja de detalle (default: "DETALLE_ARTICULO")
            
        Returns:
            Dict con estructura:
            {
                "cabecera": {...},
                "resumen": {...},
                "errores": [...],
                "data": [...]
            }
        """
        resultado = {
            "cabecera": {},
            "resumen": {
                "filasLeidas": 0,
                "filasValidas": 0,
                "filasInvalidas": 0
            },
            "errores": [],
            "data": []
        }
        
        try:
            # Leer Excel y validar hojas
            excel_file = pd.ExcelFile(io.BytesIO(file_content))
            
            # Validar que existan ambas hojas obligatorias
            if hoja_cabecera not in excel_file.sheet_names:
                resultado["errores"].append({
                    "fila": 0,
                    "campo": "Hoja",
                    "tipo": "ERROR",
                    "mensaje": f"La hoja '{hoja_cabecera}' no existe en el archivo. Hojas disponibles: {', '.join(excel_file.sheet_names)}"
                })
                resultado["resumen"]["filasInvalidas"] = 1
                return resultado
            
            if hoja_detalle not in excel_file.sheet_names:
                resultado["errores"].append({
                    "fila": 0,
                    "campo": "Hoja",
                    "tipo": "ERROR",
                    "mensaje": f"La hoja '{hoja_detalle}' no existe en el archivo. Hojas disponibles: {', '.join(excel_file.sheet_names)}"
                })
                resultado["resumen"]["filasInvalidas"] = 1
                return resultado
            
            # PASO 1: Leer y parsear CABECERA_PEDIDO
            resultado["cabecera"] = self._parsear_cabecera(excel_file, hoja_cabecera)
            
            # Validar que campos críticos estén presentes
            campos_criticos = ["numero_pedido", "CODIGO PEDIDO", "CÓDIGO PEDIDO"]
            tiene_codigo_pedido = any(campo in resultado["cabecera"] for campo in campos_criticos)
            if not tiene_codigo_pedido:
                resultado["errores"].append({
                    "fila": 0,
                    "campo": "CODIGO PEDIDO",
                    "tipo": "WARNING",
                    "mensaje": "No se encontró el campo 'CODIGO PEDIDO' en la cabecera. Campos encontrados: " + ", ".join(list(resultado["cabecera"].keys())[:5])
                })
            
            # PASO 2: Leer y parsear DETALLE_ARTICULO
            detalle_resultado = self._parsear_detalle(excel_file, file_content, hoja_detalle)
            resultado["resumen"].update(detalle_resultado["resumen"])
            resultado["errores"].extend(detalle_resultado["errores"])
            resultado["data"] = detalle_resultado["data"]
            
            logger.info(
                f"✅ Parsing completado: {resultado['resumen']['filasLeidas']} filas leídas, "
                f"{resultado['resumen']['filasValidas']} válidas, "
                f"{resultado['resumen']['filasInvalidas']} inválidas"
            )
            
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error al parsear Excel: {e}", exc_info=True)
            resultado["errores"].append({
                "fila": 0,
                "campo": "Archivo",
                "tipo": "ERROR",
                "mensaje": f"Error al leer el archivo Excel: {str(e)}"
            })
            resultado["resumen"]["filasInvalidas"] = resultado["resumen"]["filasLeidas"]
            return resultado
    
    def _parsear_cabecera(self, excel_file: pd.ExcelFile, hoja_cabecera: str) -> Dict[str, Any]:
        """Parsea la hoja de cabecera."""
        cabecera = {}
        df_cabecera = pd.read_excel(excel_file, sheet_name=hoja_cabecera, header=None)
        
        if len(df_cabecera.columns) >= 2:
            primera_fila = df_cabecera.iloc[0] if len(df_cabecera) > 0 else None
            
            tiene_header = False
            col_campo_idx = None
            col_valor_idx = None
            
            if primera_fila is not None:
                primera_fila_str = [str(v).upper().strip() if pd.notna(v) else "" for v in primera_fila.values]
                if "CAMPO" in primera_fila_str or "VALOR" in primera_fila_str:
                    tiene_header = True
                    for idx, val in enumerate(primera_fila_str):
                        if "CAMPO" in val:
                            col_campo_idx = idx
                        elif "VALOR" in val:
                            col_valor_idx = idx
                    start_row = 1
                else:
                    col_campo_idx = 0
                    col_valor_idx = 1
                    start_row = 0
            else:
                col_campo_idx = 0
                col_valor_idx = 1
                start_row = 0
            
            if col_campo_idx is None:
                col_campo_idx = 0
            if col_valor_idx is None:
                col_valor_idx = 1
            
            mapeo_campos_cabecera = {
                "CODIGO PEDIDO": "numero_pedido",
                "CÓDIGO PEDIDO": "numero_pedido",
                "FECHA PEDIDO": "fecha_pedido",
                "FECHA ENTREGA": "fecha_entrega",
                "FORMA PAGO": "forma_pago",
                "FORMA DE PAGO": "forma_pago",
                "ODC": "odc",
                "NOMBRE PROVEEDOR": "proveedor_nombre",
                "COMPRADOR NOMBRE": "comprador_nombre",
                "COD COMPRADOR": "comprador_codigo",
                "CÓD COMPRADOR": "comprador_codigo",
                "CODIGO COMPRADOR": "comprador_codigo",
                "ORIGEN TRASLADO": "origen_traslado",
                "SERIE": "serie"
            }
            
            for idx in range(start_row, len(df_cabecera)):
                campo_raw = df_cabecera.iloc[idx, col_campo_idx] if col_campo_idx < len(df_cabecera.columns) else None
                valor_raw = df_cabecera.iloc[idx, col_valor_idx] if col_valor_idx < len(df_cabecera.columns) else None
                
                if campo_raw is not None and not pd.isna(campo_raw):
                    campo = str(campo_raw).strip()
                    valor = str(valor_raw).strip() if valor_raw is not None and not pd.isna(valor_raw) else None
                    
                    if campo and valor:
                        cabecera[campo] = valor
                        
                        campo_upper = campo.upper().strip()
                        campo_normalizado = None
                        
                        if campo_upper in mapeo_campos_cabecera:
                            campo_normalizado = mapeo_campos_cabecera[campo_upper]
                        else:
                            for campo_excel, campo_bd in mapeo_campos_cabecera.items():
                                if campo_upper == campo_excel.upper() or campo_upper.startswith(campo_excel.upper()):
                                    campo_normalizado = campo_bd
                                    break
                        
                        if campo_normalizado:
                            cabecera[campo_normalizado] = valor
                            logger.debug(f"✓ Campo mapeado: '{campo}' → '{campo_normalizado}' = '{valor}'")
                        else:
                            campo_gen = campo.lower().replace(" ", "_")
                            cabecera[campo_gen] = valor
                            logger.debug(f"⚠️ Campo sin mapeo específico: '{campo}' → '{campo_gen}' = '{valor}'")
        
        logger.info(f"✅ Cabecera parseada: {len(cabecera)} campos encontrados")
        return cabecera
    
    def _parsear_detalle(self, excel_file: pd.ExcelFile, file_content: bytes, hoja_detalle: str) -> Dict[str, Any]:
        """Parsea la hoja de detalle."""
        resultado = {
            "resumen": {
                "filasLeidas": 0,
                "filasValidas": 0,
                "filasInvalidas": 0
            },
            "errores": [],
            "data": []
        }
        
        try:
            df_detalle_raw = pd.read_excel(
                excel_file, 
                sheet_name=hoja_detalle, 
                header=None, 
                keep_default_na=False,
                engine='openpyxl'
            )
        except Exception as e:
            logger.warning(f"⚠️ Error al leer con openpyxl: {e}. Intentando con engine por defecto...")
            df_detalle_raw = pd.read_excel(
                excel_file, 
                sheet_name=hoja_detalle, 
                header=None, 
                keep_default_na=False
            )
        
        logger.info(f"📊 Excel leído sin header: {len(df_detalle_raw)} filas totales, {len(df_detalle_raw.columns)} columnas")
        
        # Verificar si hay filas que pandas considera vacías pero que tienen datos
        if len(df_detalle_raw) <= 1:
            logger.warning(f"⚠️ Solo se leyeron {len(df_detalle_raw)} fila(s). Verificando si hay más datos...")
            try:
                from openpyxl import load_workbook
                wb = load_workbook(io.BytesIO(file_content), data_only=True)
                if hoja_detalle in wb.sheetnames:
                    ws = wb[hoja_detalle]
                    max_row = ws.max_row
                    if max_row > 1:
                        logger.info(f"   🔄 Intentando leer con pandas usando nrows={max_row}...")
                        df_check = pd.read_excel(
                            io.BytesIO(file_content),
                            sheet_name=hoja_detalle,
                            header=None,
                            keep_default_na=False,
                            engine='openpyxl',
                            nrows=max_row
                        )
                        if len(df_check) > len(df_detalle_raw):
                            df_detalle_raw = df_check
                wb.close()
            except (ImportError, Exception) as e2:
                logger.warning(f"   ⚠️ Error en verificación con openpyxl: {e2}")
        
        # Buscar la fila que contiene los headers
        header_row_idx: Optional[int] = None
        for idx, row in df_detalle_raw.iterrows():
            row_values = [str(v).upper().strip() if v != "" and pd.notna(v) else "" for v in row.values]
            row_str = " ".join(row_values)
            if "CODIGOPRODUCTO" in row_str or "CODIGO PRODUCTO" in row_str:
                header_row_idx = int(idx) if isinstance(idx, (int, float)) else 0
                logger.info(f"✅ Fila de header encontrada en índice: {header_row_idx}")
                break
        
        if header_row_idx is None:
            header_row_idx = 0
            logger.info(f"⚠️ No se encontró fila de header, usando fila 0 como header")
        
        # Leer con el header correcto
        try:
            df_detalle_direct = pd.read_excel(
                io.BytesIO(file_content), 
                sheet_name=hoja_detalle, 
                header=int(header_row_idx), 
                keep_default_na=False,
                engine='openpyxl'
            )
            df_detalle = pd.read_excel(
                excel_file, 
                sheet_name=hoja_detalle, 
                header=int(header_row_idx), 
                keep_default_na=False
            )
            
            if len(df_detalle_direct) > len(df_detalle):
                df_detalle = df_detalle_direct
        except Exception as e:
            logger.warning(f"⚠️ Error al leer con header={header_row_idx}: {e}. Intentando procesar manualmente...")
            df_detalle_manual = pd.read_excel(excel_file, sheet_name=hoja_detalle, header=None, keep_default_na=False)
            header_row_idx_int = int(header_row_idx) if header_row_idx is not None else 0
            
            if len(df_detalle_manual) > header_row_idx_int + 1:
                df_detalle = df_detalle_manual.iloc[header_row_idx_int + 1:].copy()
                df_detalle.columns = df_detalle_manual.iloc[header_row_idx_int].values
                df_detalle.columns = [str(col).strip() if pd.notna(col) and str(col).strip() != "" else f"col_{i}" 
                                     for i, col in enumerate(df_detalle.columns)]
            else:
                df_detalle = pd.DataFrame()
        
        resultado["resumen"]["filasLeidas"] = len(df_detalle)
        
        # Normalizar nombres de columnas
        df_detalle.columns = [str(col).strip() if pd.notna(col) else f"col_{i}" 
                             for i, col in enumerate(df_detalle.columns)]
        
        # Buscar columnas obligatorias
        col_producto, col_tienda, col_cantidad = self._buscar_columnas_obligatorias(df_detalle, hoja_detalle, resultado)
        
        if not col_producto or not col_tienda or not col_cantidad:
            return resultado
        
        # Eliminar filas vacías
        df_detalle = df_detalle.dropna(how='all')
        
        # Procesar cada fila
        duplicados_detectados = set()
        filas_procesadas = {}
        
        for idx, row in df_detalle.iterrows():
            idx_int = int(idx) if isinstance(idx, (int, float)) else 0
            row_num = idx_int + 2
            fila_valida = True
            errores_fila = []
            
            codigo_producto_raw = row.get(col_producto)
            id_tienda_raw = row.get(col_tienda)
            cantidad_raw = row.get(col_cantidad)
            
            # Normalizar valores
            codigo_producto = self._normalizar_codigo_producto(codigo_producto_raw)
            id_tienda = self._normalizar_id_tienda(id_tienda_raw)
            cantidad = self._validar_cantidad(cantidad_raw, row_num, errores_fila)
            
            # Validar campos obligatorios
            if not codigo_producto:
                fila_valida = False
                errores_fila.append({
                    "fila": row_num,
                    "campo": "CodigoProducto",
                    "tipo": "ERROR",
                    "mensaje": "CodigoProducto es obligatorio y no puede estar vacío"
                })
            
            if not id_tienda:
                fila_valida = False
                errores_fila.append({
                    "fila": row_num,
                    "campo": "IdTienda",
                    "tipo": "ERROR",
                    "mensaje": "IdTienda es obligatorio y no puede estar vacío"
                })
            
            if cantidad is None:
                fila_valida = False
            
            # Verificar duplicados
            if codigo_producto and id_tienda and cantidad:
                clave_duplicado = (codigo_producto.upper(), id_tienda.upper())
                
                if clave_duplicado in filas_procesadas:
                    fila_valida = False
                    fila_original = filas_procesadas[clave_duplicado]
                    errores_fila.append({
                        "fila": row_num,
                        "campo": "CodigoProducto, IdTienda",
                        "tipo": "ERROR",
                        "mensaje": f"Registro duplicado (SKU + Tienda). Ya existe en fila {fila_original}"
                    })
                    duplicados_detectados.add(clave_duplicado)
                else:
                    filas_procesadas[clave_duplicado] = row_num
            
            resultado["errores"].extend(errores_fila)
            
            if fila_valida and codigo_producto and id_tienda and cantidad:
                resultado["data"].append({
                    "codigoProducto": codigo_producto,
                    "idTienda": id_tienda,
                    "cantidad": cantidad,
                    "filaOrigen": row_num
                })
                resultado["resumen"]["filasValidas"] += 1
            else:
                resultado["resumen"]["filasInvalidas"] += 1
        
        return resultado
    
    def _buscar_columnas_obligatorias(self, df_detalle: pd.DataFrame, hoja_detalle: str, resultado: Dict[str, Any]) -> tuple:
        """Busca las columnas obligatorias en el detalle."""
        col_producto = None
        col_tienda = None
        col_cantidad = None
        
        posibles_producto = ['codigoproducto', 'codigo producto', 'producto', 'sku', 'codigo', 'codigo/sku', 'codigo_sku']
        posibles_tienda = ['idtienda', 'id tienda', 'tienda', 'tienda_id', 'codigo tienda', 'id_tienda']
        posibles_cantidad = ['cantidad', 'qty', 'cant', 'quantity', 'cantidad solicitada']
        
        for col in df_detalle.columns:
            col_lower = str(col).lower().strip()
            if col_lower in posibles_producto and not col_producto:
                col_producto = col
            elif col_lower in posibles_tienda and not col_tienda:
                col_tienda = col
            elif col_lower in posibles_cantidad and not col_cantidad:
                col_cantidad = col
        
        if not col_producto:
            columnas_lista = list(df_detalle.columns) if not isinstance(df_detalle.columns, list) else df_detalle.columns
            resultado["errores"].append({
                "fila": 0,
                "campo": "CodigoProducto",
                "tipo": "ERROR",
                "mensaje": f"No se encontró columna 'CodigoProducto' en hoja '{hoja_detalle}'. Columnas disponibles: {', '.join(columnas_lista)}"
            })
            resultado["resumen"]["filasInvalidas"] = resultado["resumen"]["filasLeidas"]
        
        if not col_tienda:
            columnas_lista = list(df_detalle.columns) if not isinstance(df_detalle.columns, list) else df_detalle.columns
            resultado["errores"].append({
                "fila": 0,
                "campo": "IdTienda",
                "tipo": "ERROR",
                "mensaje": f"No se encontró columna 'IdTienda' en hoja '{hoja_detalle}'. Columnas disponibles: {', '.join(columnas_lista)}"
            })
            resultado["resumen"]["filasInvalidas"] = resultado["resumen"]["filasLeidas"]
        
        if not col_cantidad:
            columnas_lista = list(df_detalle.columns) if not isinstance(df_detalle.columns, list) else df_detalle.columns
            resultado["errores"].append({
                "fila": 0,
                "campo": "Cantidad",
                "tipo": "ERROR",
                "mensaje": f"No se encontró columna 'Cantidad' en hoja '{hoja_detalle}'. Columnas disponibles: {', '.join(columnas_lista)}"
            })
            resultado["resumen"]["filasInvalidas"] = resultado["resumen"]["filasLeidas"]
        
        logger.info(f"✅ Columnas detectadas - Producto: {col_producto}, Tienda: {col_tienda}, Cantidad: {col_cantidad}")
        return col_producto, col_tienda, col_cantidad
    
    def _normalizar_codigo_producto(self, valor_raw: Any) -> Optional[str]:
        """Normaliza código de producto."""
        if valor_raw is not None and not pd.isna(valor_raw):
            codigo = str(valor_raw).strip()
            while "  " in codigo:
                codigo = codigo.replace("  ", " ")
            return codigo if codigo else None
        return None
    
    def _normalizar_id_tienda(self, valor_raw: Any) -> Optional[str]:
        """Normaliza ID de tienda."""
        if valor_raw is not None and not pd.isna(valor_raw):
            tienda = str(valor_raw).strip()
            while "  " in tienda:
                tienda = tienda.replace("  ", " ")
            return tienda if tienda else None
        return None
    
    def _validar_cantidad(self, cantidad_raw: Any, row_num: int, errores_fila: List[Dict]) -> Optional[int]:
        """Valida y normaliza cantidad."""
        if cantidad_raw is not None and not pd.isna(cantidad_raw):
            try:
                cantidad_str = str(cantidad_raw).strip().replace(",", ".")
                cantidad_float = float(cantidad_str)
                cantidad = int(cantidad_float)
                
                if cantidad_float != cantidad:
                    errores_fila.append({
                        "fila": row_num,
                        "campo": "Cantidad",
                        "tipo": "ERROR",
                        "mensaje": f"Cantidad debe ser un número entero. Valor recibido: {cantidad_raw}"
                    })
                    return None
                elif cantidad <= 0:
                    errores_fila.append({
                        "fila": row_num,
                        "campo": "Cantidad",
                        "tipo": "ERROR",
                        "mensaje": f"Cantidad debe ser mayor a 0. Valor recibido: {cantidad_raw}"
                    })
                    return None
                return cantidad
            except (ValueError, TypeError):
                errores_fila.append({
                    "fila": row_num,
                    "campo": "Cantidad",
                    "tipo": "ERROR",
                    "mensaje": f"Cantidad no es un entero válido. Valor recibido: {cantidad_raw}"
                })
                return None
        else:
            errores_fila.append({
                "fila": row_num,
                "campo": "Cantidad",
                "tipo": "ERROR",
                "mensaje": "Cantidad es obligatoria y no puede estar vacía"
            })
            return None
    
    def extraer_cabecera(self, df: pd.DataFrame, filename: str, usuario_id: Optional[str]) -> Dict[str, Any]:
        """
        Extrae los datos de cabecera del DataFrame (formato legacy).
        
        Ajustado según estructura real del Excel:
        - Los labels están en la columna E (índice 4)
        - Los valores pueden estar en la misma celda o en columnas adyacentes
        """
        cabecera = {
            "numero_pedido": None,
            "fecha_pedido": None,
            "fecha_entrega": None,
            "forma_pago": None,
            "odc": None,
            "proveedor_nombre": None,
            "comprador_nombre": None,
            "comprador_codigo": None,
            "origen_traslado": None,
            "serie": None,
            "archivo_nombre": filename,
            "creado_por": usuario_id,
        }
        
        label_to_field = {
            "PEDIDO ROLAND NO.": "numero_pedido",
            "FECHA DE PEDIDO": "fecha_pedido",
            "FECHA DE ENTREGA": "fecha_entrega",
            "FORMA DE PAGO": "forma_pago",
            "ODC": "odc",
            "NOMBRE PROVEEDOR": "proveedor_nombre",
            "COMPRADOR NOMBRE": "comprador_nombre",
            "COD COMPRADOR": "comprador_codigo",
            "ORIGEN TRASLADO": "origen_traslado",
            "SERIE": "serie",
        }
        
        max_filas_buscar = min(50, len(df))
        columna_labels = 4
        columna_valores = 5
        
        for row_idx in range(max_filas_buscar):
            label_cell = self.obtener_valor_celda(df, row_idx, columna_labels)
            
            if label_cell:
                label_upper = label_cell.upper().strip()
                
                for label_key, field_name in label_to_field.items():
                    if label_upper == label_key or label_upper.startswith(label_key):
                        valor = None
                        
                        if label_upper.startswith(label_key) and len(label_upper) > len(label_key):
                            valor_str = label_upper[len(label_key):].strip()
                            if valor_str:
                                valor = valor_str
                        
                        if not valor:
                            for col_offset in [columna_valores, 6, 3, 7, 2]:
                                if col_offset < len(df.columns):
                                    valor = self.obtener_valor_celda(df, row_idx, col_offset)
                                    if valor:
                                        break
                        
                        if field_name == "numero_pedido" and valor and label_key in valor.upper():
                            valor = valor.upper().replace(label_key, "").strip()
                        
                        cabecera[field_name] = valor if valor else None
                        break
        
        if not cabecera["numero_pedido"]:
            raise ValueError(
                "No se pudo encontrar el campo 'PEDIDO ROLAND NO.' en el archivo Excel. "
                "Verifica que el archivo tenga la estructura correcta."
            )
        
        # Convertir fecha_pedido a DATE si es posible
        if cabecera["fecha_pedido"]:
            try:
                if isinstance(cabecera["fecha_pedido"], datetime):
                    cabecera["fecha_pedido"] = cabecera["fecha_pedido"].date()
                elif isinstance(cabecera["fecha_pedido"], str):
                    cabecera["fecha_pedido"] = pd.to_datetime(cabecera["fecha_pedido"], dayfirst=True).date()
            except Exception as e:
                logger.warning(f"⚠️ Error al parsear fecha_pedido: {e}")
                cabecera["fecha_pedido"] = None
        
        return cabecera
    
    def obtener_valor_celda(self, df: pd.DataFrame, row: int, col: int) -> Optional[str]:
        """Obtiene el valor de una celda específica."""
        try:
            if row < len(df) and col < len(df.columns):
                valor = df.iloc[row, col]
                if pd.isna(valor) or valor == '' or (isinstance(valor, float) and pd.isna(valor)):
                    return None
                str_valor = str(valor).strip()
                return str_valor if str_valor else None
            return None
        except Exception as e:
            logger.debug(f"Error al obtener celda [{row}, {col}]: {e}")
            return None
    
    def extraer_detalle_con_tiendas(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Extrae detalles con distribuciones por tienda (formato complejo).
        
        Retorna lista de dicts con detalle y distribuciones.
        """
        detalles = []
        
        try:
            header_row: Optional[int] = None
            for idx, row in df.iterrows():
                row_values = [str(val).upper() if pd.notna(val) else "" for val in row.values]
                row_values_str = " ".join(row_values)
                if "CODIGO INTERNO" in row_values_str or "CODIGO PRODUCTO" in row_values_str or "CODIGOPRODUCTO" in row_values_str:
                    header_row = int(idx) if isinstance(idx, (int, float)) else 0
                    break
            
            if header_row is None:
                logger.warning("⚠️ No se encontró la fila de headers 'CODIGO INTERNO' o 'CODIGO PRODUCTO'")
                return []
            
            header_row_int = int(header_row) if header_row is not None else 0
            detalle_df = df.iloc[header_row_int + 1:].copy()
            
            if header_row_int < len(df):
                detalle_df.columns = df.iloc[header_row_int].values
                detalle_df.columns = [str(col).strip() if pd.notna(col) else f"col_{i}" 
                                     for i, col in enumerate(detalle_df.columns)]
            
            detalle_df = detalle_df.dropna(how='all')
            detalle_df.columns = [str(col).strip().lower() if pd.notna(col) else f"col_{i}" 
                                 for i, col in enumerate(detalle_df.columns)]
            
            for _, row in detalle_df.iterrows():
                codigo_interno = self.get_cell_value(row, "codigo interno")
                if not codigo_interno or pd.isna(codigo_interno):
                    codigo_interno = self.get_cell_value(row, "codigo producto")
                if not codigo_interno or pd.isna(codigo_interno):
                    codigo_interno = self.get_cell_value(row, "codigoproducto")
                if not codigo_interno or pd.isna(codigo_interno):
                    continue
                
                detalle = {
                    "codigo_interno": str(codigo_interno).strip(),
                    "descripcion_sap": self.get_cell_value(row, "descripcion sap"),
                    "marca": self.get_cell_value(row, "marca"),
                    "codigo_barras": self.get_cell_value(row, "codigo de barras"),
                    "pack": self.get_cell_value(row, "pack"),
                    "costo_doc_sin_iva": self.get_numeric_value(row, "costo doc sin iva"),
                    "descuento_1": self.get_numeric_value(row, "dscto 1") or self.get_numeric_value(row, "descuento 1"),
                    "pvp": self.get_numeric_value(row, "pvp"),
                    "subtotal": self.get_numeric_value(row, "subtotal"),
                    "total": self.get_numeric_value(row, "total"),
                }
                
                distribuciones = self.extraer_distribuciones_tienda(row, detalle_df.columns)
                
                detalles.append({
                    "detalle": detalle,
                    "distribuciones": distribuciones
                })
            
            logger.info(f"✅ _extraer_detalle_con_tiendas: {len(detalle_df)} filas procesadas, {len(detalles)} detalles creados")
            return detalles
            
        except Exception as e:
            logger.error(f"❌ Error al extraer detalle con tiendas: {e}", exc_info=True)
            return []
    
    def get_cell_value(self, row: pd.Series, column_name: str) -> Optional[str]:
        """Obtiene valor de celda como string."""
        try:
            if column_name in row.index:
                valor = row[column_name]
                if isinstance(valor, pd.Series):
                    if len(valor) == 0 or valor.isna().all():
                        return None
                    valor = valor.iloc[0] if len(valor) > 0 else None
                if valor is None or (isinstance(valor, (float, int)) and pd.isna(valor)):
                    return None
                return str(valor).strip() if valor else None
            return None
        except Exception:
            return None
    
    def get_numeric_value(self, row: pd.Series, column_name: str) -> Optional[float]:
        """Obtiene valor numérico de celda."""
        try:
            if column_name in row.index:
                valor = row[column_name]
                if isinstance(valor, pd.Series):
                    if len(valor) == 0 or valor.isna().all():
                        return None
                    valor = valor.iloc[0] if len(valor) > 0 else None
                if valor is None or (isinstance(valor, (float, int)) and pd.isna(valor)):
                    return None
                return float(valor)
            return None
        except (ValueError, TypeError):
            return None
    
    def extraer_distribuciones_tienda(self, row: pd.Series, columnas: List[str]) -> List[Dict[str, Any]]:
        """Extrae distribuciones por tienda desde las columnas del Excel."""
        distribuciones = []
        PREFIJO_TIENDA = "roland "
        
        for col_name in columnas:
            col_lower = str(col_name).lower().strip()
            
            if col_lower.startswith(PREFIJO_TIENDA):
                nombre_tienda = col_name[len(PREFIJO_TIENDA):].strip()
                cantidad = self.get_numeric_value(row, col_name)
                
                if cantidad and cantidad > 0:
                    cantidad_int = int(cantidad)
                    distribuciones.append({
                        "tienda_codigo": nombre_tienda.upper(),
                        "tienda_nombre": nombre_tienda.title(),
                        "cantidad": cantidad_int
                    })
        
        return distribuciones
    
    def extraer_detalle_formato_simple(self, file_content: bytes) -> List[Dict[str, Any]]:
        """
        Extrae detalles desde formato simple: CodigoProducto, IdTienda, Cantidad.
        
        Consolida productos: si hay múltiples filas con mismo CodigoProducto,
        se agrupan en un solo detalle con múltiples distribuciones.
        """
        detalles = []
        
        try:
            df_raw = pd.read_excel(io.BytesIO(file_content), sheet_name=0, header=0)
            df_raw.columns = [str(col).strip().lower() if pd.notna(col) else f"col_{i}" 
                             for i, col in enumerate(df_raw.columns)]
            
            col_producto = None
            col_tienda = None
            col_cantidad = None
            
            posibles_producto = ['codigoproducto', 'codigo producto', 'producto', 'sku', 'codigo']
            posibles_tienda = ['idtienda', 'id tienda', 'tienda', 'tienda_id', 'codigo tienda']
            posibles_cantidad = ['cantidad', 'qty', 'cant', 'quantity']
            
            for col in df_raw.columns:
                col_lower = str(col).lower().strip()
                if col_lower in posibles_producto and not col_producto:
                    col_producto = col
                elif col_lower in posibles_tienda and not col_tienda:
                    col_tienda = col
                elif col_lower in posibles_cantidad and not col_cantidad:
                    col_cantidad = col
            
            if not col_producto:
                raise ValueError("No se encontró columna 'CodigoProducto' (o variaciones)")
            if not col_tienda:
                raise ValueError("No se encontró columna 'IdTienda' (o variaciones)")
            if not col_cantidad:
                raise ValueError("No se encontró columna 'Cantidad' (o variaciones)")
            
            df_raw = df_raw.dropna(how='all')
            productos_agrupados = {}
            
            for idx, row in df_raw.iterrows():
                idx_int = int(idx) if isinstance(idx, (int, float)) else 0
                row_num = idx_int + 2
                
                codigo_producto = self.get_cell_value(row, col_producto)
                id_tienda = self.get_cell_value(row, col_tienda)
                cantidad_raw = row.get(col_cantidad)
                
                if not codigo_producto or pd.isna(codigo_producto):
                    continue
                
                codigo_producto = str(codigo_producto).strip()
                id_tienda = str(id_tienda).strip() if id_tienda and not pd.isna(id_tienda) else None
                
                cantidad = None
                if cantidad_raw is not None and not pd.isna(cantidad_raw):
                    try:
                        cantidad = int(float(cantidad_raw))
                        if cantidad <= 0:
                            logger.warning(f"⚠️ Fila {row_num}: Cantidad debe ser > 0, ignorando")
                            continue
                    except (ValueError, TypeError):
                        logger.warning(f"⚠️ Fila {row_num}: Cantidad inválida: {cantidad_raw}, ignorando")
                        continue
                
                if not cantidad or not id_tienda:
                    logger.warning(f"⚠️ Fila {row_num}: Faltan IdTienda o Cantidad válida, ignorando")
                    continue
                
                if codigo_producto not in productos_agrupados:
                    productos_agrupados[codigo_producto] = {
                        "detalle": {
                            "codigo_interno": codigo_producto,
                            "descripcion_sap": None,
                            "marca": None,
                            "codigo_barras": None,
                            "pack": None,
                            "costo_doc_sin_iva": None,
                            "descuento_1": None,
                            "pvp": None,
                            "subtotal": None,
                            "total": None,
                        },
                        "distribuciones": [],
                        "filas_origen": []
                    }
                
                tienda_ya_existe = False
                for dist in productos_agrupados[codigo_producto]["distribuciones"]:
                    if dist.get("tienda_codigo") == id_tienda.upper():
                        tienda_ya_existe = True
                        dist["cantidad"] += cantidad
                        break
                
                if not tienda_ya_existe:
                    productos_agrupados[codigo_producto]["distribuciones"].append({
                        "tienda_codigo": id_tienda.upper(),
                        "tienda_nombre": id_tienda,
                        "cantidad": cantidad
                    })
                
                productos_agrupados[codigo_producto]["filas_origen"].append(row_num)
            
            for codigo, data in productos_agrupados.items():
                detalles.append({
                    "detalle": data["detalle"],
                    "distribuciones": data["distribuciones"],
                    "filas_origen": data["filas_origen"]
                })
            
            logger.info(f"✅ Extraídos {len(detalles)} productos únicos desde {len(df_raw)} filas")
            return detalles
            
        except Exception as e:
            logger.error(f"❌ Error al extraer detalle formato simple: {e}", exc_info=True)
            raise

