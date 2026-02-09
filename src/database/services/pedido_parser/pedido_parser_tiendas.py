"""
Parser especializado para tiendas y distribuciones de pedidos.

CHANGELOG:
- 2026-01-23: Extraído de pedido_parser.py
"""

import logging
import pandas as pd
import io
import re
import unicodedata
from typing import Dict, Any, List, Optional

from .pedido_parser_utils import PedidoParserUtils, normalize_column_name

logger = logging.getLogger(__name__)


class PedidoParserTiendas:
    """Parser para tiendas y distribuciones de pedidos."""

    def __init__(self):
        """Inicializa el parser con utilidades compartidas."""
        self.utils = PedidoParserUtils()

    def leer_hoja_movimiento(
        self, 
        file_content: bytes, 
        catalogo_tiendas: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Lee la hoja 'Movimiento' del Excel y retorna distribuciones por producto y tienda.
        
        Args:
            file_content: Contenido del archivo Excel en bytes
            catalogo_tiendas: Diccionario opcional con tiendas válidas
            
        Returns:
            Dict con distribuciones y resumen
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
            
            hoja_movimiento = None
            for sheet_name in excel_file.sheet_names:
                if str(sheet_name).upper().strip() == "MOVIMIENTO":
                    hoja_movimiento = sheet_name
                    break
            
            if not hoja_movimiento:
                logger.warning("⚠️ No se encontró hoja 'Movimiento' en el Excel")
                return resultado
            
            df_movimiento = pd.read_excel(
                excel_file,
                sheet_name=hoja_movimiento,
                header=0,
                keep_default_na=False
            )
            
            df_movimiento.columns = [str(col).strip() for col in df_movimiento.columns]
            
            logger.info(f"📋 Hoja 'Movimiento' encontrada con {len(df_movimiento)} filas")
            
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
            
            if not col_codigo:
                resultado["errores"].append("❌ No se encontró columna 'CODIGO PRODUCTO' en hoja Movimiento")
                return resultado
            
            if not col_tienda:
                resultado["errores"].append("❌ No se encontró columna 'TIENDAS' en hoja Movimiento")
                return resultado
            
            if not col_cantidad:
                resultado["errores"].append("❌ No se encontró columna 'CANTIDAD' en hoja Movimiento")
                return resultado
            
            productos_vistos = set()
            
            for idx, row in df_movimiento.iterrows():
                fila_num = (int(idx) if isinstance(idx, (int, float)) else 0) + 2
                resultado["resumen"]["filas_leidas"] += 1
                
                codigo_producto = str(row.get(col_codigo, "")).strip()
                tienda_str = str(row.get(col_tienda, "")).strip()
                cantidad_raw = row.get(col_cantidad)
                
                if not codigo_producto:
                    resultado["errores"].append(f"Fila {fila_num}: 'CODIGO PRODUCTO' es obligatorio")
                    continue
                
                if not tienda_str:
                    resultado["errores"].append(f"Fila {fila_num}: 'TIENDAS' es obligatorio")
                    continue
                
                if cantidad_raw is None or str(cantidad_raw).strip() == "":
                    resultado["errores"].append(f"Fila {fila_num}: 'CANTIDAD' es obligatoria")
                    continue
                
                try:
                    cantidad = int(float(str(cantidad_raw).replace(",", ".")))
                    if cantidad <= 0:
                        resultado["errores"].append(f"Fila {fila_num}: 'CANTIDAD' debe ser > 0")
                        continue
                except (ValueError, TypeError):
                    resultado["errores"].append(f"Fila {fila_num}: 'CANTIDAD' no es un número válido")
                    continue
                
                codigo_producto = codigo_producto.upper()
                tienda_codigo = tienda_str.upper().replace(" ", "")
                tienda_nombre = tienda_str
                validacion_tienda = {"valida": True, "errores": [], "warnings": []}
                
                if catalogo_tiendas:
                    tienda_encontrada = False
                    for cod_cat, info_cat in catalogo_tiendas.items():
                        if tienda_codigo == cod_cat:
                            tienda_codigo = cod_cat
                            tienda_nombre = info_cat.get("nombre", tienda_str)
                            tienda_encontrada = True
                            
                            if not info_cat.get("activa", False):
                                validacion_tienda["valida"] = False
                                validacion_tienda["errores"].append(
                                    f"Tienda '{tienda_codigo}' ({tienda_nombre}) está INACTIVA"
                                )
                            break
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
                else:
                    validacion_tienda["warnings"].append(
                        "No se encontró hoja 'Tiendas' para validar tiendas"
                    )
                
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
                
                if codigo_producto not in productos_vistos:
                    productos_vistos.add(codigo_producto)
                    resultado["resumen"]["productos_unicos"] += 1
            
            logger.info(
                f"✅ Hoja 'Movimiento' procesada: {resultado['resumen']['filas_validas']} filas válidas, "
                f"{resultado['resumen']['productos_unicos']} productos únicos"
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
        
        Args:
            row: Fila de datos con las cantidades
            columnas: Lista de nombres de columnas
            catalogo_tiendas: Diccionario opcional con tiendas válidas
            
        Returns:
            Lista de distribuciones
        """
        distribuciones = []
        
        for col_name in columnas:
            col_lower = normalize_column_name(col_name)
            col_upper = str(col_name).upper().strip()
            
            es_codigo_tienda = bool(re.match(self.utils.PATRON_CODIGO_TIENDA, col_upper))
            es_formato_antiguo = col_lower.startswith(self.utils.PREFIJO_TIENDA_ANTIGUO)
            
            if es_codigo_tienda or es_formato_antiguo:
                cantidad = self.utils.get_numeric_value(row, col_name)
                
                if cantidad and cantidad > 0:
                    cantidad_int = int(cantidad)
                    
                    if es_codigo_tienda:
                        tienda_codigo = col_upper
                        validacion_tienda = {"valida": True, "errores": [], "warnings": []}
                        
                        if catalogo_tiendas:
                            if tienda_codigo not in catalogo_tiendas:
                                validacion_tienda["valida"] = False
                                validacion_tienda["errores"].append(
                                    f"Código de tienda '{tienda_codigo}' no existe en hoja 'Tiendas'"
                                )
                                tienda_nombre = tienda_codigo
                            else:
                                tienda_info = catalogo_tiendas[tienda_codigo]
                                tienda_nombre = tienda_info.get("nombre", tienda_codigo)
                                
                                if not tienda_info.get("activa", False):
                                    validacion_tienda["valida"] = False
                                    validacion_tienda["errores"].append(
                                        f"Tienda '{tienda_codigo}' ({tienda_nombre}) está INACTIVA"
                                    )
                        else:
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
                        nombre_tienda = col_name[len(self.utils.PREFIJO_TIENDA_ANTIGUO):].strip()
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
        
        Args:
            file_content: Contenido del archivo Excel en bytes
            
        Returns:
            Dict con catálogo de tiendas normalizado
        """
        import openpyxl
        
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
            
            sheet_name = None
            for name in workbook.sheetnames:
                if name.lower() == "tiendas":
                    sheet_name = name
                    break
            
            if not sheet_name:
                logger.warning("⚠️ Hoja 'Tiendas' no encontrada en Excel")
                return {}
            
            ws = workbook[sheet_name]
            catalogo = {}
            
            def _normalize_header(text: str) -> str:
                t = normalize_column_name(text)
                t = ''.join(
                    c for c in unicodedata.normalize('NFD', t)
                    if unicodedata.category(c) != 'Mn'
                )
                t = t.replace(' ', '').replace('-', '')
                return t

            headers = {}
            for col_idx, cell in enumerate(ws[1]):
                if cell.value:
                    header_normalized = _normalize_header(str(cell.value))
                    headers[col_idx] = header_normalized
            
            col_codigo = None
            col_nombre = None
            col_activa = None
            
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
            
            if col_codigo is None or col_nombre is None or col_activa is None:
                logger.warning("⚠️ Columnas requeridas no encontradas en hoja 'Tiendas'")
                return {}
            
            # Validación de sincronización: ID TIENDA ↔ NOMBRE TIENDA
            filas_desincronizadas = []
            for fila_idx in range(2, ws.max_row + 1):
                codigo_bruto = ws.cell(row=fila_idx, column=(col_codigo + 1)).value
                nombre_bruto = ws.cell(row=fila_idx, column=(col_nombre + 1)).value if col_nombre is not None else None
                
                has_codigo = bool(codigo_bruto is not None and str(codigo_bruto).strip())
                has_nombre = bool(nombre_bruto is not None and str(nombre_bruto).strip())
                
                # Si tiene uno pero no el otro, es error de sincronización
                if has_codigo != has_nombre:
                    filas_desincronizadas.append(fila_idx)
            
            if filas_desincronizadas:
                filas_str = ", ".join(str(f) for f in filas_desincronizadas)
                raise ValueError(
                    f"Error de sincronización entre ID TIENDA y NOMBRE TIENDA. "
                    f"Filas problemáticas: {filas_str}. "
                    f"Si hay información en la columna ID TIENDA debe haber en NOMBRE TIENDA y viceversa."
                )
            
            for fila_idx in range(2, ws.max_row + 1):
                codigo_bruto = ws.cell(row=fila_idx, column=(col_codigo + 1)).value
                nombre_bruto = ws.cell(row=fila_idx, column=(col_nombre + 1)).value if col_nombre is not None else None
                activa_bruto = ws.cell(row=fila_idx, column=(col_activa + 1)).value if col_activa is not None else True
                
                has_codigo = bool(codigo_bruto is not None and str(codigo_bruto).strip())
                has_nombre = bool(nombre_bruto is not None and str(nombre_bruto).strip())
                
                if not has_codigo or not has_nombre:
                    continue
                
                codigo_normalizado = str(codigo_bruto).strip().upper()
                
                if not re.match(self.utils.PATRON_CODIGO_VALIDO, codigo_normalizado):
                    logger.warning(f"⚠️ Fila {fila_idx}: Código '{codigo_normalizado}' contiene caracteres inválidos")
                    continue
                
                nombre_normalizado = str(nombre_bruto).strip() if nombre_bruto else codigo_normalizado
                
                activa_normalizada = True
                if activa_bruto is not None:
                    activa_str = normalize_column_name(activa_bruto)
                    if activa_str in ("no", "false", "0", "f"):
                        activa_normalizada = False
                    elif activa_str in ("si", "yes", "true", "1", "v"):
                        activa_normalizada = True
                
                catalogo[codigo_normalizado] = {
                    "codigo": codigo_normalizado,
                    "nombre": nombre_normalizado,
                    "activa": activa_normalizada,
                    "codigo_original": codigo_bruto,
                    "fila_origen": fila_idx
                }
            
            logger.info(f"✅ Catálogo de tiendas cargado: {len(catalogo)} tiendas")
            return catalogo
            
        except ValueError:
            # Re-raise ValueError (validaciones de negocio como sincronización ID/NOMBRE)
            raise
        except Exception as e:
            logger.error(f"❌ Error al leer hoja 'Tiendas': {e}", exc_info=True)
            return {}
