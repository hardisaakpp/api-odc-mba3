"""
Parser especializado para detalle de pedidos.

CHANGELOG:
- 2026-01-23: Extraído de pedido_parser.py
"""

import logging
import pandas as pd
import io
import re
from typing import Dict, Any, List, Optional

from .pedido_parser_utils import PedidoParserUtils, normalize_column_name, normalize_codigo_columna

logger = logging.getLogger(__name__)


class PedidoParserDetalle:
    """Parser para detalle de pedidos."""

    def __init__(self):
        """Inicializa el parser con utilidades compartidas."""
        self.utils = PedidoParserUtils()

    def parsear_nuevo_formato_v1_0(
        self, 
        excel_file: pd.ExcelFile, 
        file_content: bytes, 
        hoja_detalle: str
    ) -> Dict[str, Any]:
        """
        Parsea la hoja de detalle en el nuevo formato v1.0.
        
        Estructura esperada:
        - Fila 1 (header nombres): Nombres de columnas
        - Fila 2 (header códigos): Códigos de columnas
        - Fila 3+: Datos de productos
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
            df_detalle_raw = pd.read_excel(
                excel_file, 
                sheet_name=hoja_detalle, 
                header=None, 
                keep_default_na=False,
                engine='openpyxl'
            )
            
            logger.info(f"📊 Excel nuevo formato v1.0: {len(df_detalle_raw)} filas, {len(df_detalle_raw.columns)} columnas")
            
            header_row_idx: Optional[int] = None
            for idx, row in df_detalle_raw.iterrows():
                row_values = [str(v).upper().strip() if v != "" and pd.notna(v) else "" for v in row.values]
                row_str = " ".join(row_values)
                if "CODIGOPRODUCTO" in row_str or "CODIGO PRODUCTO" in row_str:
                    header_row_idx = int(idx) if isinstance(idx, (int, float)) else 0
                    logger.info(f"✅ Fila de header (nombres) encontrada en índice: {header_row_idx}")
                    break
            
            if header_row_idx is None:
                header_row_idx = 0
                logger.warning("⚠️ No se encontró fila de header, usando fila 0 como header")
            
            codigos_row_idx = header_row_idx + 1
            if codigos_row_idx >= len(df_detalle_raw):
                logger.warning("⚠️ No se encontró segunda fila de header (códigos), usando solo primera fila")
                codigos_row_idx = None
            
            df_detalle = pd.read_excel(
                io.BytesIO(file_content), 
                sheet_name=hoja_detalle, 
                header=int(header_row_idx), 
                keep_default_na=False,
                engine='openpyxl'
            )
            
            _raw_cols = [
                normalize_codigo_columna(str(col)) if pd.notna(col) and str(col).strip() else f"col_{i}"
                for i, col in enumerate(df_detalle.columns)
            ]
            # Asegurar unicidad: si la normalización duplicó nombres (ej. OOUT-CD y OUT-CD -> OUT-CD), renumerar
            seen: Dict[str, int] = {}
            new_cols = []
            for c in _raw_cols:
                base = c
                if base not in seen:
                    seen[base] = 1
                    new_cols.append(base)
                else:
                    new_cols.append(f"{base}.{seen[base]}")
                    seen[base] += 1
            df_detalle.columns = new_cols

            logger.info(f"📋 Nombres de columnas (fila 1) detectados: {list(df_detalle.columns)[:15]}...")
            
            codigos_columnas = {}
            nombres_columnas_fila1 = {}
            
            fila_nombres = df_detalle_raw.iloc[header_row_idx] if header_row_idx < len(df_detalle_raw) else None
            if fila_nombres is not None:
                logger.info(f"📋 Leyendo nombres de la fila {header_row_idx + 1}")
                for col_idx in range(len(fila_nombres)):
                    nombre_val = fila_nombres.iloc[col_idx] if col_idx < len(fila_nombres) else None
                    if nombre_val is not None and not pd.isna(nombre_val):
                        nombre_str = str(nombre_val).strip()
                        if nombre_str:
                            nombres_columnas_fila1[col_idx] = nombre_str
                logger.info(f"✅ Leídos {len(nombres_columnas_fila1)} nombres de la fila 1")
            
            if codigos_row_idx is not None and codigos_row_idx < len(df_detalle_raw):
                fila_codigos = df_detalle_raw.iloc[codigos_row_idx]
                logger.info(f"✅ Leyendo códigos de la fila {codigos_row_idx + 1}")
                for col_idx in range(len(fila_codigos)):
                    codigo_val = fila_codigos.iloc[col_idx]
                    if codigo_val is not None and not pd.isna(codigo_val) and str(codigo_val).strip():
                        codigo_str = normalize_codigo_columna(codigo_val).upper()
                        codigos_columnas[col_idx] = codigo_str
            
            columnas_producto = self.identificar_columnas_producto(df_detalle)
            
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
            
            columnas_bodegas = self.identificar_columnas_bodegas(
                df_detalle, codigos_columnas, self.utils.INDICES_BODEGAS
            )
            
            columnas_tiendas = self.identificar_columnas_tiendas(
                df_detalle, columnas_producto, columnas_bodegas, 
                codigos_columnas, nombres_columnas_fila1
            )
            
            logger.info(f"📊 Columnas detectadas: {len(columnas_bodegas)} bodegas, {len(columnas_tiendas)} tiendas")
            
            df_detalle = df_detalle.dropna(how='all')
            
            if codigos_row_idx is not None and codigos_row_idx == header_row_idx + 1:
                if len(df_detalle) > 0:
                    primera_fila = df_detalle.iloc[0]
                    primer_codigo = primera_fila.get(col_producto)
                    primer_codigo_str = str(primer_codigo).strip() if primer_codigo is not None and not pd.isna(primer_codigo) else ""
                    if not primer_codigo_str or len(primer_codigo_str) < 2:
                        df_detalle = df_detalle.iloc[1:].reset_index(drop=True)
                        logger.info("✅ Fila de códigos eliminada del DataFrame de datos")
            
            resultado["resumen"]["filasLeidas"] = len(df_detalle)
            
            self.procesar_filas_detalle(
                df_detalle, col_producto, columnas_producto, columnas_bodegas, 
                columnas_tiendas, nombres_columnas_fila1, header_row_idx, 
                codigos_row_idx, resultado
            )
            
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

    def identificar_columnas_producto(self, df_detalle: pd.DataFrame) -> Dict[str, str]:
        """Identifica las columnas de producto en el DataFrame."""
        columnas_producto = {}
        
        for col_idx, col_name in enumerate(df_detalle.columns):
            col_lower = normalize_column_name(col_name)
            
            for campo_bd, posibles_nombres in self.utils.MAPEO_COLUMNAS_PRODUCTO.items():
                if any(nombre in col_lower for nombre in posibles_nombres):
                    if campo_bd not in columnas_producto:
                        columnas_producto[campo_bd] = col_name
                        logger.debug(f"   Columna producto '{campo_bd}' encontrada: '{col_name}' (índice {col_idx})")
                        break
        
        return columnas_producto

    def identificar_columnas_bodegas(
        self, 
        df_detalle: pd.DataFrame, 
        codigos_columnas: Dict[int, str], 
        indices_bodegas: List[int]
    ) -> Dict[str, str]:
        """Identifica las columnas de bodegas en el DataFrame."""
        columnas_bodegas = {}
        
        for col_idx in indices_bodegas:
            if col_idx < len(df_detalle.columns):
                col_name = df_detalle.columns[col_idx]
                col_upper = str(col_name).upper().strip()
                bodega_detectada = False
                
                if col_idx in codigos_columnas:
                    codigo_bodega = codigos_columnas[col_idx]
                    codigo_bodega_upper = str(codigo_bodega).upper().strip()
                    codigo_normalizado = self.utils.VARIANTES_BODEGAS.get(codigo_bodega_upper, codigo_bodega_upper)
                    
                    if codigo_normalizado in self.utils.BODEGAS_ESPERADAS:
                        columnas_bodegas[codigo_normalizado] = col_name
                        logger.info(f"✅ Bodega encontrada por código: '{codigo_bodega}' → '{codigo_normalizado}' (índice {col_idx})")
                        bodega_detectada = True
                    elif codigo_bodega_upper in self.utils.BODEGAS_ESPERADAS:
                        columnas_bodegas[codigo_bodega_upper] = col_name
                        logger.info(f"✅ Bodega encontrada por código: '{codigo_bodega}' (índice {col_idx})")
                        bodega_detectada = True
                    else:
                        for codigo_esperado, nombre_esperado in self.utils.BODEGAS_ESPERADAS.items():
                            if codigo_esperado in codigo_bodega_upper or codigo_bodega_upper in codigo_esperado:
                                columnas_bodegas[codigo_esperado] = col_name
                                logger.info(f"✅ Bodega encontrada por código parcial: '{codigo_bodega}' → {codigo_esperado}")
                                bodega_detectada = True
                                break
                
                if not bodega_detectada:
                    if col_upper in self.utils.BODEGAS_ESPERADAS:
                        columnas_bodegas[col_upper] = col_name
                        logger.info(f"✅ Bodega encontrada por nombre: '{col_name}' (índice {col_idx})")
                        bodega_detectada = True
                    elif 'BODEGA' in col_upper or col_upper in ['RL-CD', 'OUT-CD', 'RG-CD', 'REG-CD']:
                        for codigo, nombre in self.utils.BODEGAS_ESPERADAS.items():
                            if nombre.upper() in col_upper or codigo in col_upper:
                                columnas_bodegas[codigo] = col_name
                                logger.info(f"✅ Bodega encontrada por nombre: '{col_name}' → {codigo}")
                                bodega_detectada = True
                                break
                        
                        if not bodega_detectada and col_upper in self.utils.VARIANTES_BODEGAS:
                            codigo_normalizado = self.utils.VARIANTES_BODEGAS[col_upper]
                            if codigo_normalizado in self.utils.BODEGAS_ESPERADAS:
                                columnas_bodegas[codigo_normalizado] = col_name
                                logger.info(f"✅ Bodega encontrada por variante: '{col_name}' → '{codigo_normalizado}'")
                                bodega_detectada = True
        
        return columnas_bodegas

    def extraer_info_producto(
        self, 
        row: pd.Series, 
        columnas_producto: Dict[str, str], 
        codigo_producto: str
    ) -> Dict[str, Any]:
        """Extrae información completa del producto desde una fila."""
        info_producto: Dict[str, Any] = {
            "codigo_interno": codigo_producto
        }
        
        # NOTA: La columna "marca" fue eliminada de la plantilla Excel (2026-02-05)
        # El campo se mantiene en BD para datos históricos, pero ya no se lee del Excel
        
        if 'codigo barras' in columnas_producto:
            codigo_barras_val = row.get(columnas_producto['codigo barras'])
            if codigo_barras_val is not None and not pd.isna(codigo_barras_val):
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
        
        mapeo_campos = {
            'costo sin iva': 'costo_doc_sin_iva',
            'descuento': 'descuento_1',
            'pvp': 'pvp',
            'subtotal': 'subtotal',
            'total': 'total'
        }
        
        for campo_bd, campo_salida in mapeo_campos.items():
            if campo_bd in columnas_producto:
                valor = row.get(columnas_producto[campo_bd])
                if valor is not None and not pd.isna(valor):
                    try:
                        info_producto[campo_salida] = float(str(valor).replace(",", "."))
                    except (ValueError, TypeError):
                        info_producto[campo_salida] = None
                else:
                    info_producto[campo_salida] = None
        
        return info_producto

    def identificar_columnas_tiendas(
        self,
        df_detalle: pd.DataFrame,
        columnas_producto: Dict[str, str],
        columnas_bodegas: Dict[str, str],
        codigos_columnas: Dict[int, str],
        nombres_columnas_fila1: Dict[int, str]
    ) -> Dict[str, Dict[str, Any]]:
        """Identifica las columnas de tiendas en el DataFrame."""
        columnas_tiendas = {}
        
        indices_columnas_producto = set()
        for campo_bd, col_name in columnas_producto.items():
            if col_name in df_detalle.columns:
                indices_columnas_producto.add(list(df_detalle.columns).index(col_name))
        
        indices_columnas_bodegas = set()
        for bodega_codigo, col_name in columnas_bodegas.items():
            if col_name in df_detalle.columns:
                indices_columnas_bodegas.add(list(df_detalle.columns).index(col_name))
        
        inicio_tiendas_idx = self.utils.INDICE_INICIO_TIENDAS
        
        columnas_con_codigo_tienda = []
        for col_idx in range(inicio_tiendas_idx, len(df_detalle.columns)):
            if col_idx in indices_columnas_producto or col_idx in indices_columnas_bodegas:
                continue

            codigo_columna = codigos_columnas.get(col_idx)
            nombre_columna = nombres_columnas_fila1.get(col_idx, df_detalle.columns[col_idx])
            if self._es_codigo_columna_tienda(codigo_columna) or self._es_codigo_columna_tienda(nombre_columna):
                columnas_con_codigo_tienda.append(col_idx)

        if columnas_con_codigo_tienda:
            ultima_columna_idx = max(columnas_con_codigo_tienda)
        else:
            # Fallback para plantillas antiguas sin fila de códigos: usar datos, como antes.
            ultima_columna_idx = len(df_detalle.columns) - 1
            for col_idx in range(len(df_detalle.columns) - 1, inicio_tiendas_idx - 1, -1):
                if col_idx < len(df_detalle.columns):
                    col_has_data = False
                    for row_idx in range(min(10, len(df_detalle))):
                        val = df_detalle.iloc[row_idx, col_idx]
                        if val is not None and not pd.isna(val) and str(val).strip() != "":
                            col_has_data = True
                            break
                    if col_has_data:
                        ultima_columna_idx = col_idx
                        break

        logger.info(f"📊 Rango de columnas: Producto (0-8), Bodegas (9-11), Tiendas ({inicio_tiendas_idx}-{ultima_columna_idx})")
        
        for col_idx, col_name in enumerate(df_detalle.columns):
            if col_idx >= inicio_tiendas_idx and col_idx <= ultima_columna_idx:
                if col_idx in indices_columnas_producto or col_idx in indices_columnas_bodegas:
                    continue
                
                if col_idx in nombres_columnas_fila1:
                    nombre_tienda_fila1 = nombres_columnas_fila1[col_idx]
                    if nombre_tienda_fila1 and nombre_tienda_fila1.strip():
                        nombre_columna = nombre_tienda_fila1
                    else:
                        nombre_columna = str(col_name).strip()
                else:
                    nombre_columna = str(col_name).strip()
                
                codigo_tienda = codigos_columnas.get(col_idx)
                if self._es_codigo_columna_tienda(codigo_tienda):
                    codigo_final = normalize_codigo_columna(codigo_tienda).upper().strip()
                    columnas_tiendas[codigo_final] = {
                        "col_idx": col_idx,
                        "col_name": nombre_columna
                    }
                elif self._es_codigo_columna_tienda(nombre_columna):
                    col_upper = normalize_codigo_columna(nombre_columna).upper().strip()
                    columnas_tiendas[col_upper] = {
                        "col_idx": col_idx,
                        "col_name": nombre_columna
                    }
                else:
                    logger.debug(
                        "Omitiendo columna %s como tienda: código='%s', nombre='%s'",
                        col_idx,
                        codigo_tienda,
                        nombre_columna,
                    )
        
        if columnas_tiendas:
            codigos_detectados = list(columnas_tiendas.keys())
            logger.info(
                "✅ Tiendas detectadas por encabezado/código: %s%s",
                codigos_detectados[:20],
                "..." if len(codigos_detectados) > 20 else "",
            )
        
        return columnas_tiendas

    def _es_codigo_columna_tienda(self, valor: Any) -> bool:
        """Determina si un valor de encabezado parece un código de tienda procesable."""
        if valor is None or pd.isna(valor):
            return False

        codigo = normalize_codigo_columna(valor).upper().strip()
        if not codigo:
            return False

        if codigo in self.utils.BODEGAS_ESPERADAS or codigo in self.utils.VARIANTES_BODEGAS:
            return False

        encabezados_no_tienda = ("COL", "UNNAMED", "TOTAL", "SUBTOTAL", "DIFERENCIA", "OBSERVACION")
        if codigo.startswith(encabezados_no_tienda):
            return False

        return (
            codigo.startswith(("TRL-", "TOUT-", "RG-"))
            or codigo.lower().startswith(self.utils.PREFIJO_TIENDA_ANTIGUO)
            or bool(re.match(self.utils.PATRON_CODIGO_TIENDA, codigo))
        )

    def procesar_filas_detalle(
        self,
        df_detalle: pd.DataFrame,
        col_producto: str,
        columnas_producto: Dict[str, str],
        columnas_bodegas: Dict[str, str],
        columnas_tiendas: Dict[str, Dict[str, Any]],
        nombres_columnas_fila1: Dict[int, str],
        header_row_idx: int,
        codigos_row_idx: Optional[int],
        resultado: Dict[str, Any]
    ) -> None:
        """Procesa cada fila del detalle y extrae distribuciones."""
        for idx, row in df_detalle.iterrows():
            idx_int = int(idx) if isinstance(idx, (int, float)) else 0
            if codigos_row_idx is not None:
                row_num = header_row_idx + 2 + idx_int + 1
            else:
                row_num = header_row_idx + idx_int + 2
            
            codigo_producto_raw = row.get(col_producto)
            codigo_producto = self.utils.normalizar_codigo_producto(codigo_producto_raw)
            
            if not codigo_producto:
                resultado["resumen"]["filasInvalidas"] += 1
                resultado["errores"].append({
                    "fila": row_num,
                    "campo": "CODIGO PRODUCTO",
                    "tipo": "ERROR",
                    "mensaje": "CODIGO PRODUCTO es obligatorio y no puede estar vacío"
                })
                continue
            
            info_producto = self.extraer_info_producto(row, columnas_producto, codigo_producto)
            total_esperado = info_producto.get("total")
            total_distribuido = 0.0
            
            for bodega_codigo, col_bodega_name in columnas_bodegas.items():
                cantidad_raw = row.get(col_bodega_name)
                if cantidad_raw is not None and not pd.isna(cantidad_raw):
                    raw_str = str(cantidad_raw).strip().replace(",", ".")
                    if raw_str.upper() in ("", "-", "N/A", "NA"):
                        continue
                    try:
                        cantidad = float(raw_str)
                        if cantidad >= 0:
                            bodega_codigo_final = str(bodega_codigo).strip().upper()
                            resultado["data"].append({
                                "codigoProducto": codigo_producto,
                                "idTienda": bodega_codigo_final,
                                "cantidad": cantidad,
                                "filaOrigen": row_num,
                                "es_bodega": True,
                                "info_producto": info_producto
                            })
                            total_distribuido += cantidad
                            logger.debug(f"   Fila {row_num}: {codigo_producto} → {bodega_codigo_final} x{cantidad} (bodega)")
                    except (ValueError, TypeError):
                        logger.warning(f"⚠️ Fila {row_num}: Cantidad inválida en bodega {bodega_codigo}: {cantidad_raw}")
            
            for codigo_tienda, tienda_info in columnas_tiendas.items():
                col_idx = tienda_info["col_idx"]
                
                if col_idx in nombres_columnas_fila1:
                    nombre_tienda = nombres_columnas_fila1[col_idx]
                else:
                    nombre_tienda = tienda_info["col_name"]
                
                if col_idx < len(df_detalle.columns):
                    col_name = df_detalle.columns[col_idx]
                    cantidad_raw = row.get(col_name)
                    if cantidad_raw is not None and not pd.isna(cantidad_raw):
                        raw_str = str(cantidad_raw).strip().replace(",", ".")
                        if raw_str.upper() in ("", "-", "N/A", "NA"):
                            pass  # omitir sin warning
                        else:
                            try:
                                cantidad = float(raw_str)
                                if cantidad >= 0:
                                    codigo_tienda_final = str(codigo_tienda).strip().upper()
                                    resultado["data"].append({
                                        "codigoProducto": codigo_producto,
                                        "idTienda": codigo_tienda_final,
                                        "nombreTienda": nombre_tienda,
                                        "cantidad": cantidad,
                                        "filaOrigen": row_num,
                                        "es_bodega": False,
                                        "info_producto": info_producto
                                    })
                                    total_distribuido += cantidad
                                    logger.debug(f"   Fila {row_num}: {codigo_producto} → {codigo_tienda_final} ({nombre_tienda}) x{cantidad} (tienda)")
                            except (ValueError, TypeError):
                                logger.warning(f"⚠️ Fila {row_num}: Cantidad inválida en tienda {codigo_tienda}: {cantidad_raw}")
            
            if total_esperado is not None and abs(float(total_esperado) - total_distribuido) > 0.0001:
                mensaje = (
                    f"Total del producto ({float(total_esperado):.4f}) no coincide con la suma "
                    f"de bodegas/tiendas parseadas ({total_distribuido:.4f}). "
                    "Puede existir una columna de tienda omitida o una cantidad inválida."
                )
                logger.warning(f"⚠️ Fila {row_num}: {codigo_producto} - {mensaje}")
                resultado["errores"].append({
                    "fila": row_num,
                    "campo": "TOTAL",
                    "tipo": "WARNING",
                    "mensaje": mensaje
                })
            
            resultado["resumen"]["filasValidas"] += 1
