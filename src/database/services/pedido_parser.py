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
                    "mensaje": f"La hoja '{hoja_cabecera}' no existe en el archivo. Hojas disponibles: {', '.join(str(s) for s in excel_file.sheet_names)}"
                })
                resultado["resumen"]["filasInvalidas"] = 1
                return resultado
            
            if hoja_detalle not in excel_file.sheet_names:
                resultado["errores"].append({
                    "fila": 0,
                    "campo": "Hoja",
                    "tipo": "ERROR",
                    "mensaje": f"La hoja '{hoja_detalle}' no existe en el archivo. Hojas disponibles: {', '.join(str(s) for s in excel_file.sheet_names)}"
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
        """Parsea la hoja de cabecera. Soporta formato vertical (campo|valor) y horizontal (campos en fila 1, valores en fila 2)."""
        cabecera = {}
        df_cabecera = pd.read_excel(excel_file, sheet_name=hoja_cabecera, header=None)
        
        logger.info(f"📋 Iniciando parsing de cabecera. Filas: {len(df_cabecera)}, Columnas: {len(df_cabecera.columns)}")
        
        if len(df_cabecera) == 0:
            logger.warning("⚠️ Hoja de cabecera vacía")
            return cabecera
        
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
        
        # Log de primeras filas para debug
        logger.debug(f"📊 Primeras 3 filas de cabecera:")
        for idx in range(min(3, len(df_cabecera))):
            fila = df_cabecera.iloc[idx]
            valores = [str(v)[:30] if pd.notna(v) else "(vacío)" for v in fila.values[:10]]
            logger.debug(f"   Fila {idx}: {valores}")
        
        # Detectar formato: horizontal o vertical
        # Buscar la primera fila no vacía
        primera_fila_idx = None
        segunda_fila_idx = None
        
        for idx in range(min(5, len(df_cabecera))):  # Buscar en las primeras 5 filas
            fila = df_cabecera.iloc[idx]
            valores_no_vacios = sum(1 for v in fila.values if pd.notna(v) and str(v).strip())
            if valores_no_vacios > 0:
                if primera_fila_idx is None:
                    primera_fila_idx = idx
                elif segunda_fila_idx is None:
                    segunda_fila_idx = idx
                    break
        
        logger.info(f"📊 Primera fila con datos: {primera_fila_idx}, Segunda fila con datos: {segunda_fila_idx}")
        
        es_formato_horizontal = False
        
        if primera_fila_idx is not None and segunda_fila_idx is not None:
            primera_fila = df_cabecera.iloc[primera_fila_idx]
            segunda_fila = df_cabecera.iloc[segunda_fila_idx]
            
            # Verificar si la primera fila contiene campos conocidos (formato horizontal)
            primera_fila_str = [str(v).upper().strip() if pd.notna(v) else "" for v in primera_fila.values]
            segunda_fila_str = [str(v).strip() if pd.notna(v) else "" for v in segunda_fila.values]
            
            # Si la primera fila contiene campos conocidos y la segunda tiene valores, es formato horizontal
            campos_conocidos_en_primera = sum(1 for campo in primera_fila_str if any(campo_mapeo in campo for campo_mapeo in mapeo_campos_cabecera.keys()))
            
            # También verificar que la segunda fila tenga valores (no solo campos)
            valores_en_segunda = sum(1 for v in segunda_fila_str if v and not any(campo_mapeo in v.upper() for campo_mapeo in mapeo_campos_cabecera.keys()))
            
            logger.debug(f"   Campos conocidos en primera fila: {campos_conocidos_en_primera}")
            logger.debug(f"   Valores en segunda fila: {valores_en_segunda}")
            
            if campos_conocidos_en_primera >= 2 and valores_en_segunda >= 2:  # Al menos 2 campos conocidos y 2 valores
                es_formato_horizontal = True
                logger.info(f"📊 Detectado formato HORIZONTAL (campos en fila {primera_fila_idx + 1}, valores en fila {segunda_fila_idx + 1})")
            else:
                logger.info(f"📊 No se detectó formato horizontal. Campos conocidos: {campos_conocidos_en_primera}, Valores: {valores_en_segunda}")
        
        if es_formato_horizontal:
            # Formato HORIZONTAL: campos en primera_fila_idx, valores en segunda_fila_idx
            logger.info("🔍 Procesando formato HORIZONTAL")
            for col_idx in range(len(df_cabecera.columns)):
                campo_raw = df_cabecera.iloc[int(primera_fila_idx) if primera_fila_idx is not None else 0, col_idx] if col_idx < len(df_cabecera.columns) else None
                valor_raw = df_cabecera.iloc[int(segunda_fila_idx) if segunda_fila_idx is not None else 0, col_idx] if col_idx < len(df_cabecera.columns) else None
                
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
                            logger.info(f"✓ Campo mapeado: '{campo}' → '{campo_normalizado}' = '{valor}'")
                        else:
                            campo_gen = campo.lower().replace(" ", "_")
                            cabecera[campo_gen] = valor
                            logger.debug(f"⚠️ Campo sin mapeo específico: '{campo}' → '{campo_gen}' = '{valor}'")
        else:
            # Formato VERTICAL: campo en columna 0, valor en columna 1
            logger.info("🔍 Procesando formato VERTICAL (campo|valor)")
            
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
                
                logger.info(f"   Usando columnas: Campo={col_campo_idx}, Valor={col_valor_idx}, Start row={start_row}")
                
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
                                logger.info(f"✓ Campo mapeado: '{campo}' → '{campo_normalizado}' = '{valor}'")
                            else:
                                campo_gen = campo.lower().replace(" ", "_")
                                cabecera[campo_gen] = valor
                                logger.debug(f"⚠️ Campo sin mapeo específico: '{campo}' → '{campo_gen}' = '{valor}'")
        
        logger.info(f"✅ Cabecera parseada: {len(cabecera)} campos encontrados")
        logger.info(f"   Campos: {list(cabecera.keys())}")
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
    
    def extraer_detalle_con_tiendas(
        self, 
        df: pd.DataFrame,
        catalogo_tiendas: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extrae detalles con distribuciones por tienda (formato complejo).
        
        Args:
            df: DataFrame con los datos del detalle
            catalogo_tiendas: Diccionario opcional con tiendas válidas del Excel
            
        Returns:
            Lista de dicts con detalle y distribuciones.
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
                    "descripcion_sap": self.get_cell_value(row, "descripcion sap", ["descripción sap", "descripcion"]),
                    "marca": self.get_cell_value(row, "marca"),
                    "codigo_barras": self.get_cell_value(row, "codigo de barras", ["codigo_barras", "código de barras", "codigo barras"]),
                    "pack": self.get_cell_value(row, "pack"),
                    "costo_doc_sin_iva": self.get_numeric_value(row, "costo doc sin iva", ["costo doc sin iva", "costo sin iva", "costo documento sin iva"]),
                    "descuento_1": (
                        self.get_numeric_value(row, "dscto 1", ["descuento 1"]) or 
                        self.get_numeric_value(row, "descuento 1", ["dscto 1"]) or 
                        self.get_numeric_value(row, "descuento", ["dscto"])
                    ),
                    "pvp": self.get_numeric_value(row, "pvp"),
                    "subtotal": self.get_numeric_value(row, "subtotal"),
                    "total": self.get_numeric_value(row, "total"),
                }
                
                # Pasar catálogo de tiendas a la función de extracción
                distribuciones = self.extraer_distribuciones_tienda(row, list(detalle_df.columns), catalogo_tiendas)
                
                detalles.append({
                    "detalle": detalle,
                    "distribuciones": distribuciones
                })
            
            logger.info(f"✅ _extraer_detalle_con_tiendas: {len(detalle_df)} filas procesadas, {len(detalles)} detalles creados")
            return detalles
            
        except Exception as e:
            logger.error(f"❌ Error al extraer detalle con tiendas: {e}", exc_info=True)
            return []
    
    def _find_column_flexible(self, row: pd.Series, column_names: List[str]) -> Optional[str]:
        """
        Busca una columna de manera flexible, probando múltiples variaciones del nombre.
        
        Args:
            row: Serie de pandas con los datos de la fila
            column_names: Lista de nombres de columnas a buscar (en orden de prioridad)
            
        Returns:
            Nombre de la columna encontrada, o None si no se encuentra ninguna
        """
        # Primero intentar coincidencia exacta (sin espacios extra)
        for col_name in column_names:
            # Normalizar: remover espacios extras, convertir a minúsculas
            col_normalized = ' '.join(col_name.lower().split())
            if col_normalized in row.index:
                return col_normalized
        
        # Si no hay coincidencia exacta, buscar coincidencia parcial (que contenga las palabras clave)
        for col_name in column_names:
            col_normalized = ' '.join(col_name.lower().split())
            # Buscar columnas que contengan todas las palabras clave
            keywords = [kw for kw in col_normalized.split() if len(kw) > 2]  # Filtrar palabras muy cortas
            if not keywords:
                keywords = col_normalized.split()  # Si no hay palabras largas, usar todas
            
            for idx_col in row.index:
                idx_col_lower = str(idx_col).lower().strip()
                # Verificar si todas las palabras clave están en el nombre de la columna
                if all(keyword in idx_col_lower for keyword in keywords):
                    return idx_col
        
        return None
    
    def get_cell_value(self, row: pd.Series, column_name: str, alternative_names: Optional[List[str]] = None) -> Optional[str]:
        """
        Obtiene valor de celda como string, con búsqueda flexible de columnas.
        
        Args:
            row: Serie de pandas con los datos de la fila
            column_name: Nombre principal de la columna a buscar
            alternative_names: Nombres alternativos para buscar (opcional)
        """
        try:
            # Construir lista de nombres a buscar
            names_to_try = [column_name]
            if alternative_names:
                names_to_try.extend(alternative_names)
            
            # Buscar columna de manera flexible
            found_column = self._find_column_flexible(row, names_to_try)
            
            if found_column:
                valor = row[found_column]
                if isinstance(valor, pd.Series):
                    if len(valor) == 0 or valor.isna().all():
                        return None
                    valor = valor.iloc[0] if len(valor) > 0 else None
                if valor is None or (isinstance(valor, (float, int)) and pd.isna(valor)):
                    return None
                
                # Manejo especial para código de barras: si es un número, convertirlo a string sin decimales
                is_codigo_barras = any(name.lower() in ['codigo de barras', 'codigo_barras', 'código de barras', 'codigo barras'] 
                                      for name in names_to_try)
                
                if is_codigo_barras and isinstance(valor, (int, float)):
                    # Si es un número entero (aunque esté como float), convertir a string sin decimales
                    try:
                        if isinstance(valor, int):
                            result = str(valor)
                        elif isinstance(valor, float):
                            if valor.is_integer():
                                result = str(int(valor))
                            else:
                                # Si no es entero, convertir a string normalmente
                                result = str(valor).rstrip('0').rstrip('.')
                        else:
                            result = str(valor).strip()
                    except (ValueError, TypeError, OverflowError):
                        result = str(valor).strip()
                else:
                    # Convertir a string y limpiar
                    result = str(valor).strip()
                    
                    # Si es código de barras y el string termina en .0, intentar convertir
                    if is_codigo_barras and result.endswith('.0'):
                        try:
                            num_val = float(result)
                            if num_val.is_integer():
                                result = str(int(num_val))
                        except (ValueError, TypeError):
                            pass
                
                return result if result else None
            
            return None
        except Exception as e:
            logger.debug(f"⚠️ Error al obtener valor de celda '{column_name}': {e}")
            return None
    
    def get_numeric_value(self, row: pd.Series, column_name: str, alternative_names: Optional[List[str]] = None) -> Optional[float]:
        """
        Obtiene valor numérico de celda, manejando formatos de moneda y porcentaje.
        Usa búsqueda flexible de columnas.
        
        Args:
            row: Serie de pandas con los datos de la fila
            column_name: Nombre principal de la columna a buscar
            alternative_names: Nombres alternativos para buscar (opcional)
        """
        try:
            # Construir lista de nombres a buscar
            names_to_try = [column_name]
            if alternative_names:
                names_to_try.extend(alternative_names)
            
            # Buscar columna de manera flexible
            found_column = self._find_column_flexible(row, names_to_try)
            
            if found_column:
                valor = row[found_column]
                if isinstance(valor, pd.Series):
                    if len(valor) == 0 or valor.isna().all():
                        return None
                    valor = valor.iloc[0] if len(valor) > 0 else None
                if valor is None or (isinstance(valor, (float, int)) and pd.isna(valor)):
                    return None
                
                # Si ya es numérico, retornarlo directamente
                if isinstance(valor, (int, float)):
                    return float(valor)
                
                # Convertir a string y limpiar
                str_value = str(valor).strip()
                if not str_value:
                    return None
                
                # Detectar si es porcentaje (contiene %)
                es_porcentaje = '%' in str_value
                
                # Remover símbolos de moneda comunes
                str_value = str_value.replace('$', '').replace('€', '').replace('USD', '').replace('%', '').strip()
                
                # Remover espacios y otros caracteres no numéricos (excepto punto y coma)
                str_value = ''.join(c for c in str_value if c.isdigit() or c in '.,-')
                
                # Manejar formato decimal (punto o coma)
                if ',' in str_value and '.' in str_value:
                    # Tiene ambos: asumir punto=miles, coma=decimal
                    str_value = str_value.replace('.', '').replace(',', '.')
                elif ',' in str_value:
                    # Solo coma: reemplazar por punto
                    str_value = str_value.replace(',', '.')
                
                if not str_value:
                    return None
                
                # Convertir a float
                valor_numerico = float(str_value)
                
                # Si era porcentaje, ya está en formato decimal (20% = 20.0, no 0.20)
                # Mantener el valor tal cual (20% se guarda como 20.0, no como 0.20)
                return valor_numerico
                
            return None
        except (ValueError, TypeError) as e:
            logger.debug(f"⚠️ Error al convertir valor numérico de columna '{column_name}': {e}")
            return None
    
    def leer_hoja_tiendas(self, file_content: bytes) -> Dict[str, Dict[str, Any]]:
        """
        Lee la hoja 'Tiendas' del Excel y retorna un diccionario de tiendas válidas.
        
        Estructura esperada:
        - ID TIENDA: Código único corto (ej: TRL-QSN, TRL-SMA, TOUT-BOMB, RG-INT)
        - NOMBRE_TIENDA: Nombre descriptivo completo
        - ACTIVO: Estado de la tienda (SI/NO)
        - ID_TIENDA_ACTIVA: Validación de tienda (puede repetir ID o nombre)
        
        Args:
            file_content: Contenido del archivo Excel en bytes
            
        Returns:
            Dict con código_tienda -> {nombre, activa, id_tienda_activa}
            Ejemplo: {
                "TRL-QSN": {
                    "nombre": "ROLAND QUICENTRO NORTE", 
                    "activa": True,
                    "id_tienda_activa": "TRL-QSN"
                }
            }
        """
        tiendas = {}
        
        try:
            excel_file = pd.ExcelFile(io.BytesIO(file_content))
            
            # Buscar hoja "Tiendas" (case-insensitive)
            hoja_tiendas = None
            for sheet_name in excel_file.sheet_names:
                if str(sheet_name).upper().strip() == "TIENDAS":
                    hoja_tiendas = sheet_name
                    break
            
            if not hoja_tiendas:
                logger.warning("⚠️ No se encontró hoja 'Tiendas' en el Excel")
                return tiendas
            
            # Leer hoja con header en primera fila
            df_tiendas = pd.read_excel(
                excel_file, 
                sheet_name=hoja_tiendas, 
                header=0,
                keep_default_na=False
            )
            
            # Normalizar nombres de columnas (mantener espacios para búsqueda flexible)
            columnas_originales = [str(col).strip() for col in df_tiendas.columns]
            df_tiendas.columns = columnas_originales
            
            logger.info(f"📋 Hoja 'Tiendas' encontrada con {len(df_tiendas)} filas")
            logger.info(f"🔍 Columnas en hoja Tiendas: {columnas_originales}")
            
            # Buscar columnas necesarias (flexible)
            col_codigo = None
            col_nombre = None
            col_activa = None
            col_id_activa = None
            
            for col in columnas_originales:
                col_upper = str(col).upper().strip()
                
                if col_codigo is None and "ID" in col_upper and "TIENDA" in col_upper:
                    # Preferir "ID TIENDA" antes que variaciones
                    if "ID_TIENDA_ACTIVA" not in col_upper:
                        col_codigo = col
                
                if col_nombre is None and "NOMBRE" in col_upper and "TIENDA" in col_upper:
                    col_nombre = col
                
                if col_activa is None and "ACTIVA" in col_upper:
                    # Preferir "ACTIVO" sin "_TIENDA"
                    if "ID_TIENDA" not in col_upper:
                        col_activa = col
                
                if col_id_activa is None and "ID_TIENDA_ACTIVA" in col_upper:
                    col_id_activa = col
            
            if not col_codigo:
                logger.warning("⚠️ No se encontró columna 'ID TIENDA' en hoja Tiendas")
                return tiendas
            
            logger.info(f"   Usando columnas: ID TIENDA='{col_codigo}', NOMBRE='{col_nombre}', ACTIVO='{col_activa}'")
            
            # Procesar cada fila
            for idx, row in df_tiendas.iterrows():
                codigo = str(row.get(col_codigo, "")).strip()
                if not codigo:
                    continue
                
                # Normalizar código (mayúsculas, pero mantener guiones)
                codigo = codigo.upper()
                
                nombre = str(row.get(col_nombre, "")).strip() if col_nombre else codigo
                activa_str = str(row.get(col_activa, "SI")).strip().upper() if col_activa else "SI"
                activa = activa_str in ["SI", "SÍ", "YES", "TRUE", "1", "ACTIVA"]
                
                id_tienda_activa = str(row.get(col_id_activa, codigo)).strip() if col_id_activa else codigo
                
                tiendas[codigo] = {
                    "nombre": nombre,
                    "activa": activa,
                    "id_tienda_activa": id_tienda_activa
                }
                
                logger.debug(f"   Tienda: {codigo} → {nombre} (Activa: {activa}, ID Activa: {id_tienda_activa})")
            
            logger.info(f"✅ Se cargaron {len(tiendas)} tiendas desde la hoja Tiendas")
            logger.info(f"   Tiendas cargadas: {', '.join(tiendas.keys())}")
            
        except Exception as e:
            logger.error(f"❌ Error al leer hoja 'Tiendas': {e}", exc_info=True)
        
        return tiendas
    
    def leer_hoja_movimiento(self, file_content: bytes, catalogo_tiendas: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Lee la hoja 'Movimiento' del Excel y retorna distribuciones por producto y tienda.
        
        Estructura esperada:
        - CODIGO PRODUCTO: El SKU del producto
        - TIENDAS: Nombre o código de la tienda
        - CANTIDAD: Cantidad a enviar a esa tienda
        
        Args:
            file_content: Contenido del archivo Excel en bytes
            catalogo_tiendas: Diccionario opcional con tiendas válidas {código -> {nombre, activa}}
            
        Returns:
            Dict con estructura:
            {
                "resumen": {
                    "filas_leidas": N,
                    "filas_validas": M,
                    "productos_unicos": P,
                    "distribuciones_totales": D
                },
                "datos": [
                    {
                        "codigo_producto": "MTF123.9",
                        "tienda_codigo": "ROL01",
                        "tienda_nombre": "ROLAND QUICENTRO NORTE",
                        "cantidad": 10,
                        "fila_origen": 3,
                        "validacion": {"valida": True, "errores": [...], "warnings": [...]}
                    },
                    ...
                ],
                "errores": [...]
            }
        """
        resultado = {
            "resumen": {
                "filas_leidas": 0,
                "filas_validas": 0,
                "productos_unicos": 0,
                "distribuciones_totales": 0
            },
            "datos": [],
            "errores": []
        }
        
        try:
            excel_file = pd.ExcelFile(io.BytesIO(file_content))
            
            # Buscar hoja "Movimiento" (case-insensitive)
            hoja_movimiento = None
            for sheet_name in excel_file.sheet_names:
                if str(sheet_name).upper().strip() == "MOVIMIENTO":
                    hoja_movimiento = sheet_name
                    break
            
            if not hoja_movimiento:
                logger.warning("⚠️ No se encontró hoja 'Movimiento' en el Excel")
                return resultado
            
            # Leer hoja con header en primera fila
            df_movimiento = pd.read_excel(
                excel_file,
                sheet_name=hoja_movimiento,
                header=0,
                keep_default_na=False
            )
            
            # Normalizar nombres de columnas
            df_movimiento.columns = [str(col).strip() for col in df_movimiento.columns]
            
            logger.info(f"📋 Hoja 'Movimiento' encontrada con {len(df_movimiento)} filas")
            logger.info(f"🔍 Columnas en hoja Movimiento: {list(df_movimiento.columns)}")
            
            # Buscar columnas necesarias (flexible)
            col_codigo = None
            col_tienda = None
            col_cantidad = None
            
            for col in df_movimiento.columns:
                col_upper = str(col).upper().strip()
                if col_codigo is None:
                    if "CODIGO" in col_upper and "PRODUCTO" in col_upper:
                        col_codigo = col
                    elif col_upper in ["PRODUCTO", "SKU", "CODIGO"]:
                        col_codigo = col
                
                if col_tienda is None:
                    if "TIENDA" in col_upper:
                        col_tienda = col
                
                if col_cantidad is None:
                    if "CANTIDAD" in col_upper or col_upper in ["CANT", "QTY"]:
                        col_cantidad = col
            
            # Validar que se encontraron las columnas obligatorias
            if not col_codigo:
                resultado["errores"].append("❌ No se encontró columna 'CODIGO PRODUCTO' en hoja Movimiento")
                logger.error("❌ Columna CODIGO PRODUCTO no encontrada")
                return resultado
            
            if not col_tienda:
                resultado["errores"].append("❌ No se encontró columna 'TIENDAS' en hoja Movimiento")
                logger.error("❌ Columna TIENDAS no encontrada")
                return resultado
            
            if not col_cantidad:
                resultado["errores"].append("❌ No se encontró columna 'CANTIDAD' en hoja Movimiento")
                logger.error("❌ Columna CANTIDAD no encontrada")
                return resultado
            
            logger.info(f"   Usando columnas: CODIGO PRODUCTO='{col_codigo}', TIENDAS='{col_tienda}', CANTIDAD='{col_cantidad}'")
            
            # Procesar cada fila
            productos_vistos = set()
            
            for idx, row in df_movimiento.iterrows():
                fila_num = (int(idx) if isinstance(idx, (int, float)) else 0) + 2  # +1 porque idx empieza en 0, +1 más para header
                resultado["resumen"]["filas_leidas"] += 1
                
                codigo_producto = str(row.get(col_codigo, "")).strip()
                tienda_str = str(row.get(col_tienda, "")).strip()
                cantidad_raw = row.get(col_cantidad)
                
                # Validar campos obligatorios
                if not codigo_producto:
                    logger.debug(f"⚠️ Fila {fila_num}: CODIGO PRODUCTO vacío, ignorando")
                    continue
                
                if not tienda_str:
                    logger.debug(f"⚠️ Fila {fila_num}: TIENDA vacía, ignorando")
                    continue
                
                if cantidad_raw is None or str(cantidad_raw).strip() == "":
                    logger.debug(f"⚠️ Fila {fila_num}: CANTIDAD vacía, ignorando")
                    continue
                
                # Convertir cantidad a entero
                try:
                    cantidad = int(float(str(cantidad_raw).replace(",", ".")))
                    if cantidad <= 0:
                        logger.debug(f"⚠️ Fila {fila_num}: Cantidad debe ser > 0 ({cantidad}), ignorando")
                        continue
                except (ValueError, TypeError):
                    logger.debug(f"⚠️ Fila {fila_num}: Cantidad no es número válido: '{cantidad_raw}', ignorando")
                    continue
                
                # Normalizar códigos
                codigo_producto = codigo_producto.upper()
                
                # Normalizar código de tienda (puede ser nombre o código)
                tienda_codigo = tienda_str.upper().replace(" ", "")
                tienda_nombre = tienda_str
                validacion_tienda = {"valida": True, "errores": [], "warnings": []}
                
                # Validar contra catálogo si está disponible
                if catalogo_tiendas:
                    # Buscar el código en el catálogo
                    tienda_encontrada = False
                    for cod_cat, info_cat in catalogo_tiendas.items():
                        # Buscar por código exacto
                        if tienda_codigo == cod_cat:
                            tienda_codigo = cod_cat
                            tienda_nombre = info_cat.get("nombre", tienda_str)
                            tienda_encontrada = True
                            
                            # Validar que esté activa
                            if not info_cat.get("activa", False):
                                validacion_tienda["valida"] = False
                                validacion_tienda["errores"].append(
                                    f"Tienda '{tienda_codigo}' ({tienda_nombre}) está INACTIVA"
                                )
                            break
                        # Buscar por nombre (case-insensitive, sin espacios)
                        elif tienda_codigo == str(info_cat.get("nombre", "")).upper().replace(" ", ""):
                            tienda_codigo = cod_cat
                            tienda_nombre = info_cat.get("nombre", tienda_str)
                            tienda_encontrada = True
                            
                            if not info_cat.get("activa", False):
                                validacion_tienda["valida"] = False
                                validacion_tienda["errores"].append(
                                    f"Tienda '{tienda_codigo}' ({tienda_nombre}) está INACTIVA"
                                )
                            break
                    
                    if not tienda_encontrada:
                        validacion_tienda["valida"] = False
                        validacion_tienda["errores"].append(
                            f"Tienda '{tienda_str}' no existe en el catálogo de tiendas"
                        )
                        logger.warning(f"⚠️ Fila {fila_num}: Tienda '{tienda_str}' no encontrada en catálogo")
                else:
                    validacion_tienda["warnings"].append(
                        "No se encontró hoja 'Tiendas' para validar tiendas"
                    )
                
                # Agregar distribución
                distribucion = {
                    "codigo_producto": codigo_producto,
                    "tienda_codigo": tienda_codigo,
                    "tienda_nombre": tienda_nombre,
                    "cantidad": cantidad,
                    "fila_origen": fila_num,
                    "validacion": validacion_tienda
                }
                
                resultado["datos"].append(distribucion)
                resultado["resumen"]["filas_validas"] += 1
                resultado["resumen"]["distribuciones_totales"] += 1
                
                # Contar productos únicos
                if codigo_producto not in productos_vistos:
                    productos_vistos.add(codigo_producto)
                    resultado["resumen"]["productos_unicos"] += 1
                
                logger.debug(f"   ✓ Fila {fila_num}: {codigo_producto} → {tienda_nombre} x{cantidad}")
            
            logger.info(
                f"✅ Hoja 'Movimiento' procesada: {resultado['resumen']['filas_validas']} filas válidas, "
                f"{resultado['resumen']['productos_unicos']} productos únicos, "
                f"{resultado['resumen']['distribuciones_totales']} distribuciones"
            )
            
        except Exception as e:
            logger.error(f"❌ Error al leer hoja 'Movimiento': {e}", exc_info=True)
            resultado["errores"].append(f"Error al leer hoja 'Movimiento': {str(e)}")
        
        return resultado
    
    def extraer_distribuciones_tienda(
        self, 
        row: pd.Series, 
        columnas: List[str],
        catalogo_tiendas: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extrae distribuciones por tienda desde las columnas del Excel.
        
        Soporta dos formatos:
        1. Formato antiguo: "ROLAND QUICENTRO NORTE", "ROLAND CC EL BOSQUE"
        2. Formato nuevo: "ROL01", "ROL02", "ROL03" (códigos de tienda)
        
        Args:
            row: Fila de datos con las cantidades
            columnas: Lista de nombres de columnas
            catalogo_tiendas: Diccionario opcional con tiendas válidas del Excel
            
        Returns:
            Lista de distribuciones: [{"tienda_codigo": "ROL01", "tienda_nombre": "...", "cantidad": 10, "validacion": {...}}]
        """
        distribuciones = []
        
        # Formato antiguo: columnas que empiezan con "roland "
        PREFIJO_TIENDA_ANTIGUO = "roland "
        
        for col_name in columnas:
            col_lower = str(col_name).lower().strip()
            col_upper = str(col_name).upper().strip()
            
            # Formato nuevo: columnas tipo ROL01, ROL02, etc.
            # Detectar si es código de tienda: empieza con letras y termina con números
            import re
            es_codigo_tienda = bool(re.match(r'^[A-Z]{3}\d{2}$', col_upper))
            
            # Formato antiguo: empieza con "roland "
            es_formato_antiguo = col_lower.startswith(PREFIJO_TIENDA_ANTIGUO)
            
            if es_codigo_tienda or es_formato_antiguo:
                cantidad = self.get_numeric_value(row, col_name)
                
                if cantidad and cantidad > 0:
                    cantidad_int = int(cantidad)
                    
                    if es_codigo_tienda:
                        # Formato nuevo: usar código directamente
                        tienda_codigo = col_upper
                        validacion_tienda = {"valida": True, "errores": [], "warnings": []}
                        
                        # Validar contra catálogo si está disponible
                        if catalogo_tiendas:
                            if tienda_codigo not in catalogo_tiendas:
                                validacion_tienda["valida"] = False
                                validacion_tienda["errores"].append(
                                    f"Código de tienda '{tienda_codigo}' no existe en hoja 'Tiendas'"
                                )
                                tienda_nombre = tienda_codigo
                                logger.warning(f"⚠️ Tienda {tienda_codigo} no encontrada en catálogo")
                            else:
                                tienda_info = catalogo_tiendas[tienda_codigo]
                                tienda_nombre = tienda_info.get("nombre", tienda_codigo)
                                
                                # Validar que esté activa
                                if not tienda_info.get("activa", False):
                                    validacion_tienda["valida"] = False
                                    validacion_tienda["errores"].append(
                                        f"Tienda '{tienda_codigo}' ({tienda_nombre}) está INACTIVA"
                                    )
                                    logger.warning(f"⚠️ Tienda {tienda_codigo} está inactiva")
                        else:
                            # No hay catálogo, usar código como nombre
                            tienda_nombre = tienda_codigo
                            validacion_tienda["warnings"].append(
                                "No se encontró hoja 'Tiendas' para validar el código"
                            )
                        
                        distribuciones.append({
                            "tienda_codigo": tienda_codigo,
                            "tienda_nombre": tienda_nombre,
                            "cantidad": cantidad_int,
                            "validacion": validacion_tienda
                        })
                    else:
                        # Formato antiguo: extraer nombre después de "roland "
                        nombre_tienda = col_name[len(PREFIJO_TIENDA_ANTIGUO):].strip()
                        distribuciones.append({
                            "tienda_codigo": nombre_tienda.upper(),
                            "tienda_nombre": nombre_tienda.title(),
                            "cantidad": cantidad_int,
                            "validacion": {"valida": True, "errores": [], "warnings": []}
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

