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
        hoja_cabecera: str = "cabecera",
        hoja_detalle: str = "detalle",
        es_formato_nuevo_v1_0: bool = True
    ) -> Dict[str, Any]:
        """
        Parsea un archivo Excel de pedido en formato v1.0.
        
        Formato esperado (Template_Pedido_Inicial_v1.0.xlsx):
        - Hoja 1: "cabecera" (formato clave-valor: Campo | Valor | Ejemplo)
        - Hoja 2: "detalle" (formato tabular con columnas A-J producto, K-M bodegas, N+ tiendas)
        
        Solo parsing técnico: lee, normaliza y valida estructura.
        NO aplica reglas de negocio, NO consolida duplicados.
        NO calcula SUBTOTAL ni TOTAL - solo parsea los valores del Excel.
        
        Args:
            file_content: Contenido del archivo Excel en bytes
            hoja_cabecera: Nombre de la hoja de cabecera (default: "cabecera")
            hoja_detalle: Nombre de la hoja de detalle (default: "detalle")
            es_formato_nuevo_v1_0: Si True, usa el nuevo formato v1.0 (default: True)
            
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
            
            # PASO 1: Leer y parsear hoja "cabecera"
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
            
            # PASO 2: Leer y parsear hoja "detalle" (nuevo formato v1.0)
            # Parsea columnas A-J (producto), K-M (bodegas), N+ (tiendas hasta última columna con información)
            detalle_resultado = self._parsear_detalle_nuevo_formato_v1_0(excel_file, file_content, hoja_detalle)
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
            "FECHA DE PEDIDO": "fecha_pedido",
            "FECHA ENTREGA": "fecha_entrega",
            "FECHA DE ENTREGA": "fecha_entrega",
            "FORMA PAGO": "forma_pago",
            "FORMA DE PAGO": "forma_pago",
            "ODC": "odc",
            "NOMBRE PROVEEDOR": "proveedor_nombre",
            "NOMBRE DE PROVEEDOR": "proveedor_nombre",
            "COMPRADOR NOMBRE": "comprador_nombre",
            "COMPRADOR": "comprador_nombre",
            "COD COMPRADOR": "comprador_codigo",
            "CÓD COMPRADOR": "comprador_codigo",
            "CODIGO COMPRADOR": "comprador_codigo",
            "ORIGEN TRASLADO": "origen_traslado",
            "ORIGEN DE TRASLADO": "origen_traslado",
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
    
    def _es_codigo_valido(self, codigo: str) -> bool:
        """
        Valida si un código es válido para tienda/bodega.
        
        Filtra códigos que sean solo números simples (como "1", "2", "3")
        que probablemente son índices o números de fila, no códigos reales.
        
        Args:
            codigo: Código a validar
            
        Returns:
            True si el código es válido, False si es solo un número simple
        """
        import re
        codigo_clean = str(codigo).strip().upper()
        
        # Si es solo números (1-3 dígitos), probablemente no es un código válido
        if re.match(r'^\d{1,3}$', codigo_clean):
            return False
        
        # Códigos válidos deben tener al menos una letra o ser códigos conocidos
        # Formato esperado: "ROL01", "RL-CD", "OUT-CD", "REG-CD", etc.
        tiene_letras = bool(re.search(r'[A-Z]', codigo_clean))
        
        return tiene_letras
    
    def _parsear_detalle_nuevo_formato_v1_0(self, excel_file: pd.ExcelFile, file_content: bytes, hoja_detalle: str) -> Dict[str, Any]:
        """
        Parsea la hoja de detalle en el nuevo formato v1.0.
        
        Estructura esperada:
        - Fila 1 (header nombres): Nombres de columnas
          - Columnas A-J: Información del producto (CODIGO PRODUCTO, MARCA, CODIGO BARRAS, etc.)
          - Columnas K-M: Nombres de bodegas centrales
          - Columnas N+: Nombres de tiendas individuales
        - Fila 2 (header códigos): Códigos de columnas
          - Columnas A-J: (generalmente vacías o repetidas)
          - Columnas K-M: Códigos de bodegas (RL-CD, OUT-CD, REG-CD)
          - Columnas N+: Códigos de tiendas individuales
        - Fila 3+: Datos de productos
        
        Las bodegas centrales NO se incluyen en SUBTOTAL.
        Las tiendas individuales SÍ se incluyen en SUBTOTAL.
        TOTAL = SUBTOTAL + RL-CD + OUT-CD + REG-CD
        """
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
            # Leer Excel sin header primero para identificar estructura
            df_detalle_raw = pd.read_excel(
                excel_file, 
                sheet_name=hoja_detalle, 
                header=None, 
                keep_default_na=False,
                engine='openpyxl'
            )
            
            logger.info(f"📊 Excel nuevo formato v1.0: {len(df_detalle_raw)} filas, {len(df_detalle_raw.columns)} columnas")
            
            # Buscar la fila que contiene los headers (fila 1 = nombres)
            header_row_idx: Optional[int] = None
            for idx, row in df_detalle_raw.iterrows():
                row_values = [str(v).upper().strip() if v != "" and pd.notna(v) else "" for v in row.values]
                row_str = " ".join(row_values)
                # Buscar "CODIGO PRODUCTO" o "CODIGOPRODUCTO"
                if "CODIGOPRODUCTO" in row_str or "CODIGO PRODUCTO" in row_str:
                    header_row_idx = int(idx) if isinstance(idx, (int, float)) else 0
                    logger.info(f"✅ Fila de header (nombres) encontrada en índice: {header_row_idx}")
                    break
            
            if header_row_idx is None:
                header_row_idx = 0
                logger.warning(f"⚠️ No se encontró fila de header, usando fila 0 como header")
            
            # Verificar que existe una segunda fila de header (fila 2 = códigos)
            codigos_row_idx = header_row_idx + 1
            if codigos_row_idx >= len(df_detalle_raw):
                logger.warning(f"⚠️ No se encontró segunda fila de header (códigos), usando solo primera fila")
                codigos_row_idx = None
            
            # Leer con el header de nombres (fila 1) para identificar estructura
            df_detalle = pd.read_excel(
                io.BytesIO(file_content), 
                sheet_name=hoja_detalle, 
                header=int(header_row_idx), 
                keep_default_na=False,
                engine='openpyxl'
            )
            
            # Normalizar nombres de columnas (de la fila 1 = nombres)
            df_detalle.columns = [str(col).strip() if pd.notna(col) else f"col_{i}" 
                                 for i, col in enumerate(df_detalle.columns)]
            
            # Si existe segunda fila de header (códigos), leer los códigos
            codigos_columnas = {}
            if codigos_row_idx is not None and codigos_row_idx < len(df_detalle_raw):
                fila_codigos = df_detalle_raw.iloc[codigos_row_idx]
                logger.info(f"✅ Leyendo códigos de la fila {codigos_row_idx + 1} (segunda fila de header)")
                
                # Crear mapeo de índices de columna a códigos
                for col_idx in range(len(fila_codigos)):
                    codigo_val = fila_codigos.iloc[col_idx]
                    if codigo_val is not None and not pd.isna(codigo_val) and str(codigo_val).strip():
                        codigo_str = str(codigo_val).strip().upper()
                        codigos_columnas[col_idx] = codigo_str
                        logger.debug(f"   Columna {col_idx}: código '{codigo_str}'")
            
            logger.info(f"📋 Columnas detectadas en nuevo formato: {list(df_detalle.columns)[:15]}...")
            
            # Identificar índices de columnas por posición
            # Columna A = 0, B = 1, ..., K = 10, L = 11, M = 12, N = 13, etc.
            
            # Identificar columnas de información del producto (A-J = índices 0-9)
            # Según especificación: A=CODIGO PRODUCTO, B=MARCA, C=CODIGO BARRAS, D=DESCRIPCION SAP,
            # E=PACK, F=COSTO SIN IVA, G=DESCUENTO, H=PVP, I=TOTAL, J=SUBTOTAL
            columnas_producto = {}
            
            # Mapeo de nombres de columnas esperados (flexible)
            mapeo_columnas_producto = {
                'codigo producto': ('codigoproducto', 'codigo producto', 'producto', 'sku', 'codigo'),
                'marca': ('marca',),
                'codigo barras': ('codigo de barras', 'codigo_barras', 'código de barras', 'codigo barras', 'ean'),
                'descripcion sap': ('descripcion sap', 'descripción sap', 'descripcion', 'descripción'),
                'pack': ('pack', 'unidad', 'unidad de empaque'),
                'costo sin iva': ('costo sin iva', 'costo doc sin iva', 'costo', 'precio sin iva'),
                'descuento': ('descuento', 'dscto', 'dscto 1', 'descuento 1'),
                'pvp': ('pvp', 'precio venta publico', 'precio de venta'),
                'total': ('total',),
                'subtotal': ('subtotal',)
            }
            
            for col_idx, col_name in enumerate(df_detalle.columns):
                col_lower = str(col_name).lower().strip()
                
                # Buscar coincidencias con las columnas esperadas de producto
                for campo_bd, posibles_nombres in mapeo_columnas_producto.items():
                    if any(nombre in col_lower for nombre in posibles_nombres):
                        if campo_bd not in columnas_producto:
                            columnas_producto[campo_bd] = col_name
                            logger.debug(f"   Columna producto '{campo_bd}' encontrada: '{col_name}' (índice {col_idx})")
                            break
            
            # Verificar que CODIGO PRODUCTO existe (obligatorio)
            if 'codigo producto' not in columnas_producto:
                resultado["errores"].append({
                    "fila": 0,
                    "campo": "CODIGO PRODUCTO",
                    "tipo": "ERROR",
                    "mensaje": f"No se encontró columna 'CODIGO PRODUCTO' en hoja '{hoja_detalle}'"
                })
                return resultado
            
            col_producto = columnas_producto['codigo producto']
            logger.info(f"✅ Columnas de producto detectadas: {list(columnas_producto.keys())}")
            
            # Identificar columnas de bodegas (K, L, M = índices 10, 11, 12)
            # Usar códigos de la fila 2 si están disponibles, sino usar nombres de la fila 1
            columnas_bodegas = {}
            bodegas_esperadas = {
                'RL-CD': 'BODEGA ROLAND',
                'OUT-CD': 'BODEGA DESCUENTON', 
                'REG-CD': 'BODEGA REGIONS'
            }
            
            # Primero intentar identificar por códigos de la fila 2 (columnas K, L, M = índices 10, 11, 12)
            for col_idx in [10, 11, 12]:
                if col_idx < len(df_detalle.columns):
                    # Si tenemos códigos de la segunda fila, usarlos
                    if col_idx in codigos_columnas:
                        codigo_bodega = codigos_columnas[col_idx]
                        col_name = df_detalle.columns[col_idx]
                        # Verificar si el código coincide con alguna bodega esperada
                        if codigo_bodega in bodegas_esperadas:
                            columnas_bodegas[codigo_bodega] = col_name
                            logger.info(f"✅ Bodega encontrada por código: '{codigo_bodega}' (índice {col_idx}, nombre columna: '{col_name}')")
                        else:
                            # Si el código no coincide exactamente, buscar por coincidencia parcial
                            for codigo_esperado, nombre_esperado in bodegas_esperadas.items():
                                if codigo_esperado in codigo_bodega or codigo_bodega in codigo_esperado:
                                    columnas_bodegas[codigo_esperado] = col_name
                                    logger.info(f"✅ Bodega encontrada por código parcial: '{codigo_bodega}' → {codigo_esperado} (índice {col_idx})")
                                    break
                    else:
                        # Fallback: usar nombres de la fila 1
                        col_name = df_detalle.columns[col_idx]
                        col_upper = str(col_name).upper().strip()
                        if col_upper in bodegas_esperadas:
                            columnas_bodegas[col_upper] = col_name
                            logger.info(f"✅ Bodega encontrada por nombre: '{col_name}' (índice {col_idx})")
                        elif 'BODEGA' in col_upper:
                            # Buscar por nombre de bodega
                            for codigo, nombre in bodegas_esperadas.items():
                                if nombre.upper() in col_upper or codigo in col_upper:
                                    columnas_bodegas[codigo] = col_name
                                    logger.info(f"✅ Bodega encontrada por nombre: '{col_name}' → {codigo} (índice {col_idx})")
                                    break
            
            # Identificar columnas de tiendas (desde columna N = índice 13 en adelante)
            # Las tiendas son todas las columnas que NO son:
            # - Columnas A-J (producto): índices 0-9
            # - Columnas K-M (bodegas): índices 10-12
            columnas_tiendas = {}
            
            # Identificar índices de columnas de producto y bodegas para excluirlas
            indices_columnas_producto = set()
            for campo_bd, col_name in columnas_producto.items():
                if col_name in df_detalle.columns:
                    indices_columnas_producto.add(list(df_detalle.columns).index(col_name))
            
            indices_columnas_bodegas = set()
            for bodega_codigo, col_name in columnas_bodegas.items():
                if col_name in df_detalle.columns:
                    indices_columnas_bodegas.add(list(df_detalle.columns).index(col_name))
            
            # Las tiendas empiezan desde índice 13 (columna N)
            inicio_tiendas_idx = 13
            
            # Identificar última columna con información real (no vacía en todas las filas)
            ultima_columna_idx = len(df_detalle.columns) - 1
            # Verificar hacia atrás desde la última columna para encontrar la última con datos
            for col_idx in range(len(df_detalle.columns) - 1, inicio_tiendas_idx - 1, -1):
                col_name = df_detalle.columns[col_idx]
                # Verificar si la columna tiene al menos un valor no vacío en alguna fila
                if col_idx < len(df_detalle.columns):
                    col_has_data = False
                    for row_idx in range(min(10, len(df_detalle))):  # Revisar primeras 10 filas como muestra
                        val = df_detalle.iloc[row_idx, col_idx]
                        if val is not None and not pd.isna(val) and str(val).strip() != "":
                            col_has_data = True
                            break
                    if col_has_data:
                        ultima_columna_idx = col_idx
                        break
            
            logger.info(f"📊 Rango de columnas: Producto (0-9), Bodegas (10-12), Tiendas (13-{ultima_columna_idx})")
            
            # Procesar columnas desde N hasta la última con información
            # Usar códigos de la fila 2 si están disponibles, sino usar nombres de la fila 1
            for col_idx, col_name in enumerate(df_detalle.columns):
                # Si está en el rango de tiendas (desde índice 13) y no supera la última columna con datos
                if col_idx >= inicio_tiendas_idx and col_idx <= ultima_columna_idx:
                    # Verificar que no sea una columna de producto
                    if col_idx in indices_columnas_producto:
                        continue
                    
                    # Verificar que no sea una columna de bodega
                    if col_idx in indices_columnas_bodegas:
                        continue
                    
                    # Es una columna de tienda
                    # Usar código de la fila 2 si está disponible, sino usar nombre de la fila 1
                    if col_idx in codigos_columnas:
                        codigo_tienda = codigos_columnas[col_idx]
                        # ⭐ VALIDACIÓN: Filtrar códigos que sean solo números simples
                        if self._es_codigo_valido(codigo_tienda):
                            columnas_tiendas[codigo_tienda] = col_idx
                            logger.debug(f"   Tienda detectada por código: '{codigo_tienda}' (índice {col_idx}, nombre columna: '{col_name}')")
                        else:
                            # Código inválido (solo números), usar nombre de columna como fallback
                            logger.warning(f"⚠️ Código '{codigo_tienda}' en columna {col_idx} parece ser un número simple, usando nombre de columna '{col_name}' como fallback")
                            col_upper = str(col_name).upper().strip()
                            columnas_tiendas[col_upper] = col_idx
                            logger.debug(f"   Tienda detectada por nombre (fallback): '{col_name}' (índice {col_idx})")
                    else:
                        # Fallback: usar nombre de la columna como código
                        col_upper = str(col_name).upper().strip()
                        columnas_tiendas[col_upper] = col_idx
                        logger.debug(f"   Tienda detectada por nombre: '{col_name}' (índice {col_idx})")
            
            logger.info(f"📊 Columnas detectadas: {len(columnas_bodegas)} bodegas, {len(columnas_tiendas)} tiendas")
            
            # Eliminar filas vacías
            df_detalle = df_detalle.dropna(how='all')
            
            # Si hay dos filas de header, necesitamos eliminar la primera fila de datos que corresponde a la fila de códigos
            # (porque pandas la incluyó como datos cuando usamos header=header_row_idx)
            # Cuando usamos header=header_row_idx, pandas usa esa fila como header y los datos empiezan desde header_row_idx+1
            # Entonces si codigos_row_idx = header_row_idx + 1, esa fila será la primera fila de datos y debemos eliminarla
            if codigos_row_idx is not None and codigos_row_idx == header_row_idx + 1:
                # La primera fila del DataFrame corresponde a la fila de códigos, eliminarla
                if len(df_detalle) > 0:
                    # Verificar si la primera fila parece ser la fila de códigos (no tiene código de producto válido)
                    primera_fila = df_detalle.iloc[0]
                    primer_codigo = primera_fila.get(col_producto)
                    primer_codigo_str = str(primer_codigo).strip() if primer_codigo is not None and not pd.isna(primer_codigo) else ""
                    # Si la primera fila no tiene código de producto válido, probablemente es la fila de códigos
                    if not primer_codigo_str or len(primer_codigo_str) < 2:
                        df_detalle = df_detalle.iloc[1:].reset_index(drop=True)
                        logger.info(f"✅ Fila de códigos (fila {codigos_row_idx + 1}) eliminada del DataFrame de datos")
            
            resultado["resumen"]["filasLeidas"] = len(df_detalle)
            
            # Procesar cada fila
            for idx, row in df_detalle.iterrows():
                idx_int = int(idx) if isinstance(idx, (int, float)) else 0
                # Calcular número de fila en Excel: header_row_idx (fila 1) + 1 (fila 2 códigos) + idx_int (datos) + 1 (Excel es 1-indexed)
                if codigos_row_idx is not None:
                    row_num = header_row_idx + 2 + idx_int + 1  # +2 por las dos filas de header, +1 porque Excel es 1-indexed
                else:
                    row_num = header_row_idx + idx_int + 2  # +2 porque idx empieza en 0 y header_row_idx es relativo
                
                codigo_producto_raw = row.get(col_producto)
                codigo_producto = self._normalizar_codigo_producto(codigo_producto_raw)
                
                if not codigo_producto:
                    resultado["resumen"]["filasInvalidas"] += 1
                    resultado["errores"].append({
                        "fila": row_num,
                        "campo": "CODIGO PRODUCTO",
                        "tipo": "ERROR",
                        "mensaje": "CODIGO PRODUCTO es obligatorio y no puede estar vacío"
                    })
                    continue
                
                # Extraer información completa del producto (columnas A-J)
                from typing import Any
                info_producto: Dict[str, Any] = {
                    "codigo_interno": codigo_producto
                }
                
                # Extraer cada campo de producto si existe la columna
                if 'marca' in columnas_producto:
                    marca_val = row.get(columnas_producto['marca'])
                    info_producto["marca"] = str(marca_val).strip() if marca_val is not None and not pd.isna(marca_val) else None
                
                if 'codigo barras' in columnas_producto:
                    codigo_barras_val = row.get(columnas_producto['codigo barras'])
                    if codigo_barras_val is not None and not pd.isna(codigo_barras_val):
                        # Convertir a string sin decimales si es numérico
                        if isinstance(codigo_barras_val, float) and codigo_barras_val.is_integer():
                            info_producto["codigo_barras"] = str(int(codigo_barras_val))
                        else:
                            info_producto["codigo_barras"] = str(codigo_barras_val).strip()
                    else:
                        info_producto["codigo_barras"] = None
                
                if 'descripcion sap' in columnas_producto:
                    desc_sap_val = row.get(columnas_producto['descripcion sap'])
                    info_producto["descripcion_sap"] = str(desc_sap_val).strip() if desc_sap_val is not None and not pd.isna(desc_sap_val) else None
                
                if 'pack' in columnas_producto:
                    pack_val = row.get(columnas_producto['pack'])
                    info_producto["pack"] = str(pack_val).strip() if pack_val is not None and not pd.isna(pack_val) else None
                
                if 'costo sin iva' in columnas_producto:
                    costo_val = row.get(columnas_producto['costo sin iva'])
                    if costo_val is not None and not pd.isna(costo_val):
                        try:
                            info_producto["costo_doc_sin_iva"] = float(str(costo_val).replace(",", "."))
                        except (ValueError, TypeError):
                            info_producto["costo_doc_sin_iva"] = None
                    else:
                        info_producto["costo_doc_sin_iva"] = None
                
                if 'descuento' in columnas_producto:
                    descuento_val = row.get(columnas_producto['descuento'])
                    if descuento_val is not None and not pd.isna(descuento_val):
                        try:
                            info_producto["descuento_1"] = float(str(descuento_val).replace(",", "."))
                        except (ValueError, TypeError):
                            info_producto["descuento_1"] = None
                    else:
                        info_producto["descuento_1"] = None
                
                if 'pvp' in columnas_producto:
                    pvp_val = row.get(columnas_producto['pvp'])
                    if pvp_val is not None and not pd.isna(pvp_val):
                        try:
                            info_producto["pvp"] = float(str(pvp_val).replace(",", "."))
                        except (ValueError, TypeError):
                            info_producto["pvp"] = None
                    else:
                        info_producto["pvp"] = None
                
                if 'subtotal' in columnas_producto:
                    subtotal_val = row.get(columnas_producto['subtotal'])
                    if subtotal_val is not None and not pd.isna(subtotal_val):
                        try:
                            info_producto["subtotal"] = float(str(subtotal_val).replace(",", "."))
                        except (ValueError, TypeError):
                            info_producto["subtotal"] = None
                    else:
                        info_producto["subtotal"] = None
                
                if 'total' in columnas_producto:
                    total_val = row.get(columnas_producto['total'])
                    if total_val is not None and not pd.isna(total_val):
                        try:
                            info_producto["total"] = float(str(total_val).replace(",", "."))
                        except (ValueError, TypeError):
                            info_producto["total"] = None
                    else:
                        info_producto["total"] = None
                
                # Procesar bodegas
                # columnas_bodegas ahora mapea código_bodega -> nombre_columna
                for bodega_codigo, col_bodega_name in columnas_bodegas.items():
                    cantidad_raw = row.get(col_bodega_name)
                    if cantidad_raw is not None and not pd.isna(cantidad_raw):
                        try:
                            cantidad = int(float(str(cantidad_raw).strip().replace(",", ".")))
                            if cantidad > 0:
                                # Usar código de bodega (ya viene de la fila 2 o nombre de columna)
                                bodega_codigo_final = str(bodega_codigo).strip().upper()
                                
                                resultado["data"].append({
                                    "codigoProducto": codigo_producto,
                                    "idTienda": bodega_codigo_final,  # Usar código de bodega como ID
                                    "cantidad": cantidad,
                                    "filaOrigen": row_num,
                                    "es_bodega": True,
                                    "info_producto": info_producto  # Incluir información completa del producto
                                })
                                logger.debug(f"   Fila {row_num}: {codigo_producto} → {bodega_codigo_final} x{cantidad} (bodega)")
                        except (ValueError, TypeError):
                            logger.warning(f"⚠️ Fila {row_num}: Cantidad inválida en bodega {bodega_codigo}: {cantidad_raw}")
                
                # Procesar tiendas
                # columnas_tiendas ahora mapea código_tienda -> índice_columna
                for codigo_tienda, col_idx in columnas_tiendas.items():
                    # Obtener el nombre de la columna para acceder a los datos
                    if col_idx < len(df_detalle.columns):
                        col_name = df_detalle.columns[col_idx]
                        cantidad_raw = row.get(col_name)
                        if cantidad_raw is not None and not pd.isna(cantidad_raw):
                            try:
                                cantidad = int(float(str(cantidad_raw).strip().replace(",", ".")))
                                if cantidad > 0:
                                    # Usar el código de la tienda (ya viene de la fila 2 o nombre de columna)
                                    codigo_tienda_final = str(codigo_tienda).strip().upper()
                                    
                                    resultado["data"].append({
                                        "codigoProducto": codigo_producto,
                                        "idTienda": codigo_tienda_final,
                                        "cantidad": cantidad,
                                        "filaOrigen": row_num,
                                        "es_bodega": False,
                                        "info_producto": info_producto  # Incluir información completa del producto
                                    })
                                    logger.debug(f"   Fila {row_num}: {codigo_producto} → {codigo_tienda_final} x{cantidad} (tienda)")
                            except (ValueError, TypeError):
                                logger.warning(f"⚠️ Fila {row_num}: Cantidad inválida en tienda {codigo_tienda}: {cantidad_raw}")
                
                resultado["resumen"]["filasValidas"] += 1
            
            logger.info(
                f"✅ Parsing nuevo formato v1.0 completado: {resultado['resumen']['filasLeidas']} filas leídas, "
                f"{resultado['resumen']['filasValidas']} válidas, "
                f"{len(resultado['data'])} distribuciones creadas"
            )
            
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error al parsear detalle nuevo formato v1.0: {e}", exc_info=True)
            resultado["errores"].append({
                "fila": 0,
                "campo": "Archivo",
                "tipo": "ERROR",
                "mensaje": f"Error al leer el archivo Excel: {str(e)}"
            })
            resultado["resumen"]["filasInvalidas"] = resultado["resumen"]["filasLeidas"]
            return resultado
    
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
                
                # Validar campos obligatorios (alineación estricta: las 3 columnas deben tener datos)
                if not codigo_producto:
                    msg = f"Fila {fila_num}: 'CODIGO PRODUCTO' es obligatorio"
                    logger.warning(f"❌ {msg}")
                    resultado["errores"].append(msg)
                    continue
                
                if not tienda_str:
                    msg = f"Fila {fila_num}: 'TIENDAS' es obligatorio"
                    logger.warning(f"❌ {msg}")
                    resultado["errores"].append(msg)
                    continue
                
                if cantidad_raw is None or str(cantidad_raw).strip() == "":
                    msg = f"Fila {fila_num}: 'CANTIDAD' es obligatoria"
                    logger.warning(f"❌ {msg}")
                    resultado["errores"].append(msg)
                    continue
                
                # Convertir cantidad a entero
                try:
                    cantidad = int(float(str(cantidad_raw).replace(",", ".")))
                    if cantidad <= 0:
                        msg = f"Fila {fila_num}: 'CANTIDAD' debe ser un entero > 0 (recibido {cantidad})"
                        logger.warning(f"❌ {msg}")
                        resultado["errores"].append(msg)
                        continue
                except (ValueError, TypeError):
                    msg = f"Fila {fila_num}: 'CANTIDAD' no es un número entero válido (recibido '{cantidad_raw}')"
                    logger.warning(f"❌ {msg}")
                    resultado["errores"].append(msg)
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
    
    def leer_hoja_tiendas(self, file_content: bytes) -> Dict[str, Dict]:
        """
        Lee la hoja "Tiendas" y retorna catálogo NORMALIZADO.
        
        IMPORTANTE: Normaliza TODOS los datos para evitar falsos errores
        (espacios, mayúsculas, booleanos).
        
        Args:
            file_content: Contenido del archivo Excel en bytes
            
        Returns:
            {
                "TRL-QSN": {
                    "codigo": "TRL-QSN",
                    "nombre": "ROLAND QUICENTRO NORTE",
                    "activa": True,
                    "codigo_original": "TRL-qsn",
                    "fila_origen": 2
                },
                ...
            }
            
        Raises:
            ValueError: Si hay error al leer la hoja
        """
        import openpyxl
        import re  # ✅ AGREGAR IMPORT
        import unicodedata
        
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
            
            # ✅ Buscar hoja "Tiendas" (case-insensitive)
            sheet_name = None
            for name in workbook.sheetnames:
                if name.lower() == "tiendas":
                    sheet_name = name
                    break
            
            if not sheet_name:
                logger.warning("⚠️ Hoja 'Tiendas' no encontrada en Excel")
                return {}  # Retornar vacío si no existe (permisivo para formato simple)
            
            ws = workbook[sheet_name]
            catalogo = {}
            misaligned_rows_tiendas: List[int] = []
            
            # ✅ Leer headers de la primera fila con normalización robusta
            def _normalize_header(text: str) -> str:
                # Minúsculas, sin acentos, sin espacios ni signos
                t = str(text).lower().strip()
                # Remover acentos
                t = ''.join(
                    c for c in unicodedata.normalize('NFD', t)
                    if unicodedata.category(c) != 'Mn'
                )
                # Reemplazar espacios y guiones por nada para comparación flexible
                t = t.replace(' ', '')
                t = t.replace('-', '')
                return t

            headers = {}
            for col_idx, cell in enumerate(ws[1]):
                if cell.value:
                    header_normalized = _normalize_header(str(cell.value))
                    headers[col_idx] = header_normalized
            
            # Validar que existan columnas mínimas
            col_codigo = None
            col_nombre = None
            col_activa = None
            
            # Mapear columnas por candidatos exactos tras normalización
            codigo_candidates = {"idtienda", "codigo", "codigo_tienda", "codigotienda", "code"}
            nombre_candidates = {"nombretienda", "nombre", "tienda", "nombredetienda"}
            activa_candidates = {"activo", "activa", "active", "estado"}

            for col_idx, header in headers.items():
                if header in codigo_candidates or any(h in header for h in codigo_candidates):
                    col_codigo = col_idx
                elif header in nombre_candidates or any(h in header for h in nombre_candidates):
                    col_nombre = col_idx
                elif header in activa_candidates or any(h in header for h in activa_candidates):
                    col_activa = col_idx
            
            if col_codigo is None:
                raise ValueError(f"Hoja 'Tiendas' debe tener columna 'id_tienda' o 'Código'. Headers encontrados: {list(headers.values())}")
            if col_nombre is None:
                raise ValueError(f"Hoja 'Tiendas' debe tener columna 'Nombre Tienda'. Headers encontrados: {list(headers.values())}")
            if col_activa is None:
                raise ValueError(f"Hoja 'Tiendas' debe tener columna 'ACTIVO'. Headers encontrados: {list(headers.values())}")
            
            # ✅ Leer filas de datos (desde fila 2)
            detalles_alineacion = {}  # Para diagnóstico detallado
            
            logger.info(f"📊 Leyendo hoja 'Tiendas': {ws.max_row} filas totales (incluyendo header)")
            logger.info(f"   Columna ID TIENDA: índice {col_codigo}")
            logger.info(f"   Columna NOMBRE TIENDA: índice {col_nombre}")
            logger.info(f"   Columna ACTIVO: índice {col_activa}")
            
            for fila_idx in range(2, ws.max_row + 1):
                codigo_bruto = ws.cell(row=fila_idx, column=(col_codigo + 1)).value
                nombre_bruto = ws.cell(row=fila_idx, column=(col_nombre + 1)).value if col_nombre is not None else None
                activa_bruto = ws.cell(row=fila_idx, column=(col_activa + 1)).value if col_activa is not None else True
                
                # ✅ VALIDACIÓN ESTRICTA: ID TIENDA y NOMBRE TIENDA deben estar SINCRONIZADOS
                # Si hay información en una columna, DEBE haber información en la otra
                has_codigo = bool(codigo_bruto is not None and str(codigo_bruto).strip())
                has_nombre = bool(nombre_bruto is not None and str(nombre_bruto).strip())
                has_activa = bool(activa_bruto is not None and str(activa_bruto).strip())

                fila_tiene_datos = has_codigo or has_nombre or has_activa

                if fila_tiene_datos:
                    # Validar sincronización entre ID TIENDA y NOMBRE TIENDA
                    # REGLA: Si una está llena, la otra DEBE estar llena
                    sincronizacion_correcta = (has_codigo and has_nombre) or (not has_codigo and not has_nombre)
                
                    if not sincronizacion_correcta:
                        misaligned_rows_tiendas.append(fila_idx)
                        detalles_alineacion[fila_idx] = {
                            "ID TIENDA": codigo_bruto if has_codigo else "[VACÍO]",
                            "NOMBRE TIENDA": nombre_bruto if has_nombre else "[VACÍO]",
                            "ACTIVO": activa_bruto if has_activa else "[VACÍO]"
                        }
                        
                        # LOG DETALLADO para diagnóstico
                        logger.error(
                            f"\n❌ FILA {fila_idx} (Excel): INCOMPLETA - FALTA SINCRONIZACIÓN ENTRE ID TIENDA Y NOMBRE TIENDA\n"
                            f"   ID TIENDA      = {repr(codigo_bruto):30} → {'' if has_codigo else '❌ VACÍO'}\n"
                            f"   NOMBRE TIENDA  = {repr(nombre_bruto):30} → {'' if has_nombre else '❌ VACÍO'}\n"
                            f"   ACTIVO         = {repr(activa_bruto):30}\n"
                        )
                        
                        if not has_codigo and has_nombre:
                            logger.error(f"   ❌ PROBLEMA: NOMBRE TIENDA tiene valor pero ID TIENDA está vacío")
                        elif has_codigo and not has_nombre:
                            logger.error(f"   ❌ PROBLEMA: ID TIENDA tiene valor pero NOMBRE TIENDA está vacío")
                        continue

                if not fila_tiene_datos:
                    # Fila completamente vacía, ignorar sin error
                    continue
                
                # ✅ NORMALIZACIÓN CRÍTICA
                if not codigo_bruto:
                    logger.warning(f"⚠️ Fila {fila_idx}: Código de tienda vacío, omitiendo")
                    continue
                
                # Normalizar código (strip + upper)
                codigo_normalizado = str(codigo_bruto).strip().upper()
                
                # Validar código (caracteres permitidos: A-Z, 0-9, guión, punto)
                if not re.match(r'^[A-Z0-9\-\.]+$', codigo_normalizado):
                    logger.warning(
                        f"⚠️ Fila {fila_idx}: Código '{codigo_normalizado}' contiene caracteres inválidos"
                    )
                    continue
                
                # Normalizar nombre (strip + title case)
                nombre_normalizado = str(nombre_bruto).strip() if nombre_bruto else codigo_normalizado
                
                # ✅ CONVERTIR BOOLEANO (CRÍTICO)
                activa_normalizada = True
                if activa_bruto is not None:
                    activa_str = str(activa_bruto).lower().strip()
                    if activa_str in ("no", "false", "0", "f"):
                        activa_normalizada = False
                    elif activa_str in ("si", "yes", "true", "1", "v"):
                        activa_normalizada = True
                    else:
                        # Valor desconocido, por defecto activa
                        logger.warning(
                            f"⚠️ Fila {fila_idx}: Valor 'Activa' inválido '{activa_bruto}', asumiendo SI"
                        )
                        activa_normalizada = True
                
                # Detectar duplicados (mismo código)
                if codigo_normalizado in catalogo:
                    logger.warning(
                        f"⚠️ Código de tienda '{codigo_normalizado}' duplicado "
                        f"(filas {catalogo[codigo_normalizado]['fila_origen']} y {fila_idx}), "
                        f"usando última ocurrencia"
                    )
                
                # ✅ GUARDAR EN CATÁLOGO
                catalogo[codigo_normalizado] = {
                    "codigo": codigo_normalizado,  # Normalizado
                    "nombre": nombre_normalizado,
                    "activa": activa_normalizada,
                    "codigo_original": codigo_bruto,  # Guardar original para auditoría
                    "fila_origen": fila_idx
                }
                
                logger.debug(
                    f"✅ Tienda cargada: {codigo_normalizado} "
                    f"(Activa: {activa_normalizada}, Fila: {fila_idx})"
                )
            
            if misaligned_rows_tiendas:
                filas = ", ".join(str(n) for n in misaligned_rows_tiendas[:10])
                extra = f" y {len(misaligned_rows_tiendas) - 10} más" if len(misaligned_rows_tiendas) > 10 else ""
                
                # Mostrar detalles de filas problemáticas en el log
                logger.error(f"❌ FILAS CON FALTA DE SINCRONIZACIÓN (Total: {len(misaligned_rows_tiendas)}):")
                for num_fila, detalles in list(detalles_alineacion.items())[:5]:
                    logger.error(f"   Fila {num_fila}: {detalles}")
                if len(detalles_alineacion) > 5:
                    logger.error(f"   ... y {len(detalles_alineacion) - 5} filas más")
                
                raise ValueError(
                    f"❌ Validación fallida en hoja 'Tiendas': falta sincronización entre columnas ID TIENDA y NOMBRE TIENDA. "
                    f"Filas problemáticas: {filas}{extra}. "
                    f"REGLA: Si hay información en la columna ID TIENDA, DEBE haber información en NOMBRE TIENDA y viceversa. "
                    f"Las filas completamente vacías se ignoran automáticamente."
                )
            
            if not catalogo:
                logger.warning("⚠️ No se encontraron tiendas válidas en la hoja 'Tiendas'")
            
            logger.info(f"📊 Catálogo de tiendas cargado: {len(catalogo)} tiendas válidas")
            return catalogo
            
        except Exception as e:
            logger.error(f"❌ Error al leer hoja 'Tiendas': {e}", exc_info=True)
            raise ValueError(f"Error al leer catálogo de tiendas: {str(e)}")

