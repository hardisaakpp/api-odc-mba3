"""
Parser especializado para detalle de pedidos.

CHANGELOG:
- 2026-01-23: Extraído de pedido_parser.py
"""

import logging
import pandas as pd
import io
import re
from typing import Dict, Any, Optional

from .pedido_parser_utils import PedidoParserUtils, normalize_column_name, normalize_codigo_columna

logger = logging.getLogger(__name__)


class PedidoParserDetalle:
    """Parser para detalle de pedidos."""

    _CAMPO_CODIGO_PRODUCTO = "CODIGO PRODUCTO"

    def __init__(self):
        """Inicializa el parser con utilidades compartidas."""
        self.utils = PedidoParserUtils()

    # ========== Helpers privados ==========

    def _buscar_fila_header(self, df_raw: pd.DataFrame) -> int:
        for idx, row in df_raw.iterrows():
            row_str = " ".join(
                str(v).upper().strip() if v != "" and pd.notna(v) else ""
                for v in row.values
            )
            if "CODIGOPRODUCTO" in row_str or self._CAMPO_CODIGO_PRODUCTO in row_str:
                header_idx = int(idx) if isinstance(idx, (int, float)) else 0
                logger.info(f"✅ Fila de header (nombres) encontrada en índice: {header_idx}")
                return header_idx
        logger.warning("⚠️ No se encontró fila de header, usando fila 0 como header")
        return 0

    @staticmethod
    def _normalizar_columnas_con_unicidad(df: pd.DataFrame) -> list:
        # Asegurar unicidad: si la normalización duplicó nombres (ej. OOUT-CD y OUT-CD -> OUT-CD), renumerar
        raw_cols = [
            normalize_codigo_columna(str(col)) if pd.notna(col) and str(col).strip() else f"col_{i}"
            for i, col in enumerate(df.columns)
        ]
        seen: Dict[str, int] = {}
        new_cols = []
        for c in raw_cols:
            if c not in seen:
                seen[c] = 1
                new_cols.append(c)
            else:
                new_cols.append(f"{c}.{seen[c]}")
                seen[c] += 1
        return new_cols

    @staticmethod
    def _leer_nombres_fila_header(df_raw: pd.DataFrame, header_row_idx: int) -> Dict[int, str]:
        nombres: Dict[int, str] = {}
        if header_row_idx >= len(df_raw):
            return nombres
        fila = df_raw.iloc[header_row_idx]
        logger.info(f"📋 Leyendo nombres de la fila {header_row_idx + 1}")
        for col_idx in range(len(fila)):
            val = fila.iloc[col_idx] if col_idx < len(fila) else None
            if val is not None and not pd.isna(val):
                nombre_str = str(val).strip()
                if nombre_str:
                    nombres[col_idx] = nombre_str
        logger.info(f"✅ Leídos {len(nombres)} nombres de la fila 1")
        return nombres

    @staticmethod
    def _leer_codigos_fila(df_raw: pd.DataFrame, codigos_row_idx: Optional[int]) -> Dict[int, str]:
        codigos: Dict[int, str] = {}
        if codigos_row_idx is None or codigos_row_idx >= len(df_raw):
            return codigos
        fila = df_raw.iloc[codigos_row_idx]
        logger.info(f"✅ Leyendo códigos de la fila {codigos_row_idx + 1}")
        for col_idx in range(len(fila)):
            val = fila.iloc[col_idx]
            if val is not None and not pd.isna(val) and str(val).strip():
                codigos[col_idx] = normalize_codigo_columna(val).upper()
        return codigos

    @staticmethod
    def _eliminar_fila_codigos_si_necesario(
        df: pd.DataFrame, col_producto: str, codigos_row_idx: Optional[int], header_row_idx: int
    ) -> pd.DataFrame:
        if codigos_row_idx is None or codigos_row_idx != header_row_idx + 1 or len(df) == 0:
            return df
        primer_codigo_raw = df.iloc[0].get(col_producto)
        primer_codigo_str = (
            str(primer_codigo_raw).strip()
            if primer_codigo_raw is not None and not pd.isna(primer_codigo_raw)
            else ""
        )
        if not primer_codigo_str or len(primer_codigo_str) < 2:
            logger.info("✅ Fila de códigos eliminada del DataFrame de datos")
            return df.iloc[1:].reset_index(drop=True)
        return df

    # ========== Interfaz pública ==========

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
            "resumen": {"filasLeidas": 0, "filasValidas": 0, "filasInvalidas": 0},
            "errores": [],
            "data": []
        }

        try:
            df_detalle_raw = pd.read_excel(
                excel_file, sheet_name=hoja_detalle, header=None,
                keep_default_na=False, engine='openpyxl'
            )
            logger.info(
                f"📊 Excel nuevo formato v1.0: {len(df_detalle_raw)} filas, "
                f"{len(df_detalle_raw.columns)} columnas"
            )

            header_row_idx = self._buscar_fila_header(df_detalle_raw)
            codigos_row_idx_candidate = header_row_idx + 1
            if codigos_row_idx_candidate >= len(df_detalle_raw):
                logger.warning("⚠️ No se encontró segunda fila de header (códigos), usando solo primera fila")
                codigos_row_idx: Optional[int] = None
            else:
                codigos_row_idx = codigos_row_idx_candidate

            df_detalle = pd.read_excel(
                io.BytesIO(file_content), sheet_name=hoja_detalle,
                header=int(header_row_idx), keep_default_na=False, engine='openpyxl'
            )
            df_detalle.columns = self._normalizar_columnas_con_unicidad(df_detalle)
            logger.info(f"📋 Nombres de columnas (fila 1) detectados: {list(df_detalle.columns)[:15]}...")

            nombres_columnas_fila1 = self._leer_nombres_fila_header(df_detalle_raw, header_row_idx)
            codigos_columnas = self._leer_codigos_fila(df_detalle_raw, codigos_row_idx)

            columnas_producto = self.identificar_columnas_producto(df_detalle)
            if 'codigo producto' not in columnas_producto:
                resultado["errores"].append({
                    "fila": 0,
                    "campo": self._CAMPO_CODIGO_PRODUCTO,
                    "tipo": "ERROR",
                    "mensaje": f"No se encontró columna '{self._CAMPO_CODIGO_PRODUCTO}' en hoja '{hoja_detalle}'"
                })
                return resultado

            col_producto = columnas_producto['codigo producto']
            logger.info(f"✅ Columnas de producto detectadas: {list(columnas_producto.keys())}")

            columnas_bodegas = self.identificar_columnas_bodegas(
                df_detalle, codigos_columnas, columnas_producto
            )
            columnas_tiendas = self.identificar_columnas_tiendas(
                df_detalle, columnas_producto, columnas_bodegas,
                codigos_columnas, nombres_columnas_fila1
            )
            logger.info(
                f"📊 Columnas detectadas: {len(columnas_bodegas)} bodegas, {len(columnas_tiendas)} tiendas"
            )

            df_detalle = df_detalle.dropna(how='all')
            df_detalle = self._eliminar_fila_codigos_si_necesario(
                df_detalle, col_producto, codigos_row_idx, header_row_idx
            )
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

    def _buscar_bodega_por_codigo(
        self, col_idx: int, codigos_columnas: Dict[int, str]
    ) -> Optional[str]:
        if col_idx not in codigos_columnas:
            return None
        codigo_bodega = codigos_columnas[col_idx]
        codigo_bodega_upper = str(codigo_bodega).upper().strip()
        codigo_normalizado = self.utils.VARIANTES_BODEGAS.get(codigo_bodega_upper, codigo_bodega_upper)
        if codigo_normalizado in self.utils.BODEGAS_ESPERADAS:
            logger.info(f"✅ Bodega encontrada por código: '{codigo_bodega}' → '{codigo_normalizado}' (índice {col_idx})")
            return codigo_normalizado
        if codigo_bodega_upper in self.utils.BODEGAS_ESPERADAS:
            logger.info(f"✅ Bodega encontrada por código: '{codigo_bodega}' (índice {col_idx})")
            return codigo_bodega_upper
        for codigo_esperado in self.utils.BODEGAS_ESPERADAS:
            if codigo_esperado in codigo_bodega_upper or codigo_bodega_upper in codigo_esperado:
                logger.info(f"✅ Bodega encontrada por código parcial: '{codigo_bodega}' → {codigo_esperado}")
                return codigo_esperado
        return None

    def _buscar_bodega_por_nombre(self, col_name: str, col_upper: str, col_idx: int) -> Optional[str]:
        if col_upper in self.utils.BODEGAS_ESPERADAS:
            logger.info(f"✅ Bodega encontrada por nombre: '{col_name}' (índice {col_idx})")
            return col_upper
        if 'BODEGA' in col_upper or col_upper in ('RL-CD', 'OUT-CD', 'RG-CD', 'REG-CD'):
            for codigo, nombre in self.utils.BODEGAS_ESPERADAS.items():
                if nombre.upper() in col_upper or codigo in col_upper:
                    logger.info(f"✅ Bodega encontrada por nombre: '{col_name}' → {codigo}")
                    return codigo
            codigo_variante = self.utils.VARIANTES_BODEGAS.get(col_upper)
            if codigo_variante and codigo_variante in self.utils.BODEGAS_ESPERADAS:
                logger.info(f"✅ Bodega encontrada por variante: '{col_name}' → '{codigo_variante}'")
                return codigo_variante
        return None

    def identificar_columnas_bodegas(
        self,
        df_detalle: pd.DataFrame,
        codigos_columnas: Dict[int, str],
        columnas_producto: Dict[str, str]
    ) -> Dict[str, str]:
        """
        Identifica las columnas de bodegas en el DataFrame por nombre/código
        (RL-CD/OUT-CD/RG-CD y variantes), en cualquier columna que no haya sido ya
        reclamada como campo de producto. No depende de una posición fija: insertar
        o quitar una columna de producto (ej. "Costo") no desalinea esta búsqueda.
        """
        columnas_bodegas: Dict[str, str] = {}
        indices_producto = self._calcular_indices_excluidos(df_detalle, columnas_producto, {})
        for col_idx, col_name in enumerate(df_detalle.columns):
            if col_idx in indices_producto:
                continue
            col_upper = str(col_name).upper().strip()
            clave = self._buscar_bodega_por_codigo(col_idx, codigos_columnas)
            if clave is None:
                clave = self._buscar_bodega_por_nombre(col_name, col_upper, col_idx)
            if clave is not None:
                columnas_bodegas[clave] = col_name
        return columnas_bodegas

    @staticmethod
    def _extraer_codigo_barras(row: pd.Series, col_name: str) -> Optional[str]:
        val = row.get(col_name)
        if val is None or pd.isna(val):
            return None
        if isinstance(val, float) and val.is_integer():
            return str(int(val))
        return str(val).strip()

    @staticmethod
    def _extraer_campo_str_opcional(row: pd.Series, col_name: str) -> Optional[str]:
        val = row.get(col_name)
        return str(val).strip() if val is not None and not pd.isna(val) else None

    def _extraer_campos_numericos(
        self, row: pd.Series, columnas_producto: Dict[str, str], info_producto: Dict[str, Any]
    ) -> None:
        mapeo_campos = {
            'costo sin iva': 'costo_doc_sin_iva',
            'costo margen': 'costo_margen',
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
            info_producto["codigo_barras"] = self._extraer_codigo_barras(row, columnas_producto['codigo barras'])

        if 'descripcion sap' in columnas_producto:
            info_producto["descripcion_sap"] = self._extraer_campo_str_opcional(row, columnas_producto['descripcion sap'])

        if 'pack' in columnas_producto:
            info_producto["pack"] = self._extraer_campo_str_opcional(row, columnas_producto['pack'])

        self._extraer_campos_numericos(row, columnas_producto, info_producto)
        return info_producto

    @staticmethod
    def _calcular_indices_excluidos(
        df_detalle: pd.DataFrame,
        columnas_producto: Dict[str, str],
        columnas_bodegas: Dict[str, str]
    ) -> set:
        col_list = list(df_detalle.columns)
        indices_producto = {col_list.index(col) for col in columnas_producto.values() if col in col_list}
        indices_bodegas = {col_list.index(col) for col in columnas_bodegas.values() if col in col_list}
        return indices_producto | indices_bodegas

    @staticmethod
    def _buscar_ultima_columna_con_datos(
        df_detalle: pd.DataFrame, inicio_tiendas_idx: int, indices_excluidos: set
    ) -> int:
        for col_idx in range(len(df_detalle.columns) - 1, inicio_tiendas_idx - 1, -1):
            if col_idx in indices_excluidos:
                continue
            for row_idx in range(min(10, len(df_detalle))):
                val = df_detalle.iloc[row_idx, col_idx]
                if val is not None and not pd.isna(val) and str(val).strip() != "":
                    return col_idx
        return len(df_detalle.columns) - 1

    def _detectar_ultima_columna_tiendas(
        self,
        df_detalle: pd.DataFrame,
        inicio_tiendas_idx: int,
        indices_excluidos: set,
        codigos_columnas: Dict[int, str],
        nombres_columnas_fila1: Dict[int, str]
    ) -> int:
        columnas_con_codigo_tienda = []
        for col_idx in range(inicio_tiendas_idx, len(df_detalle.columns)):
            if col_idx in indices_excluidos:
                continue
            codigo_columna = codigos_columnas.get(col_idx)
            nombre_columna = nombres_columnas_fila1.get(col_idx, df_detalle.columns[col_idx])
            if self._es_codigo_columna_tienda(codigo_columna) or self._es_codigo_columna_tienda(nombre_columna):
                columnas_con_codigo_tienda.append(col_idx)
        if columnas_con_codigo_tienda:
            return max(columnas_con_codigo_tienda)
        # Fallback para plantillas antiguas sin fila de códigos
        return self._buscar_ultima_columna_con_datos(df_detalle, inicio_tiendas_idx, indices_excluidos)

    @staticmethod
    def _resolver_nombre_columna_tienda(
        col_idx: int, col_name: Any, nombres_columnas_fila1: Dict[int, str]
    ) -> str:
        if col_idx in nombres_columnas_fila1:
            nombre = nombres_columnas_fila1[col_idx]
            if nombre and nombre.strip():
                return nombre
        return str(col_name).strip()

    def _clasificar_y_registrar_columna_tienda(
        self,
        col_idx: int,
        nombre_columna: str,
        codigos_columnas: Dict[int, str],
        columnas_tiendas: Dict[str, Dict[str, Any]]
    ) -> None:
        codigo_tienda = codigos_columnas.get(col_idx)
        if self._es_codigo_columna_tienda(codigo_tienda):
            codigo_final = normalize_codigo_columna(codigo_tienda).upper().strip()
            columnas_tiendas[codigo_final] = {"col_idx": col_idx, "col_name": nombre_columna}
        elif self._es_codigo_columna_tienda(nombre_columna):
            col_upper = normalize_codigo_columna(nombre_columna).upper().strip()
            columnas_tiendas[col_upper] = {"col_idx": col_idx, "col_name": nombre_columna}
        else:
            logger.debug(
                "Omitiendo columna %s como tienda: código='%s', nombre='%s'",
                col_idx,
                codigo_tienda,
                nombre_columna,
            )

    def identificar_columnas_tiendas(
        self,
        df_detalle: pd.DataFrame,
        columnas_producto: Dict[str, str],
        columnas_bodegas: Dict[str, str],
        codigos_columnas: Dict[int, str],
        nombres_columnas_fila1: Dict[int, str]
    ) -> Dict[str, Dict[str, Any]]:
        """Identifica las columnas de tiendas en el DataFrame."""
        indices_excluidos = self._calcular_indices_excluidos(df_detalle, columnas_producto, columnas_bodegas)
        # Sin posición fija de arranque: se excluyen las columnas ya reclamadas como
        # producto/bodega y el resto se evalúa por patrón (_es_codigo_columna_tienda),
        # así una columna de producto insertada en cualquier posición no desalinea esto.
        inicio_tiendas_idx = 0
        ultima_columna_idx = self._detectar_ultima_columna_tiendas(
            df_detalle, inicio_tiendas_idx, indices_excluidos, codigos_columnas, nombres_columnas_fila1
        )
        col_list = list(df_detalle.columns)
        indices_producto_dbg = {col_list.index(c) for c in columnas_producto.values() if c in col_list}
        indices_bodegas_dbg = {col_list.index(c) for c in columnas_bodegas.values() if c in col_list}
        logger.info(
            "📊 Columnas producto: %s, bodegas: %s, tiendas hasta índice %s",
            sorted(indices_producto_dbg), sorted(indices_bodegas_dbg), ultima_columna_idx,
        )
        columnas_tiendas: Dict[str, Dict[str, Any]] = {}
        for col_idx, col_name in enumerate(df_detalle.columns):
            if inicio_tiendas_idx <= col_idx <= ultima_columna_idx and col_idx not in indices_excluidos:
                nombre_columna = self._resolver_nombre_columna_tienda(col_idx, col_name, nombres_columnas_fila1)
                self._clasificar_y_registrar_columna_tienda(col_idx, nombre_columna, codigos_columnas, columnas_tiendas)
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

    def _parsear_cantidad_raw(self, cantidad_raw: Any, etiqueta: str, row_num: int) -> Optional[float]:
        if cantidad_raw is None or pd.isna(cantidad_raw):
            return None
        raw_str = str(cantidad_raw).strip().replace(",", ".")
        if raw_str.upper() in ("", "-", "N/A", "NA"):
            return None
        try:
            cantidad = float(raw_str)
            return cantidad if cantidad >= 0 else None
        except (ValueError, TypeError):
            logger.warning(f"⚠️ Fila {row_num}: Cantidad inválida en {etiqueta}: {cantidad_raw}")
            return None

    def _procesar_bodegas_fila(
        self,
        row: pd.Series,
        columnas_bodegas: Dict[str, str],
        data_list: list,
        codigo_producto: str,
        info_producto: Dict[str, Any],
        row_num: int,
    ) -> float:
        total = 0.0
        for bodega_codigo, col_bodega_name in columnas_bodegas.items():
            cantidad = self._parsear_cantidad_raw(row.get(col_bodega_name), f"bodega {bodega_codigo}", row_num)
            if cantidad is not None:
                bodega_codigo_final = str(bodega_codigo).strip().upper()
                data_list.append({
                    "codigoProducto": codigo_producto,
                    "idTienda": bodega_codigo_final,
                    "cantidad": cantidad,
                    "filaOrigen": row_num,
                    "es_bodega": True,
                    "info_producto": info_producto
                })
                total += cantidad
                logger.debug(f"   Fila {row_num}: {codigo_producto} → {bodega_codigo_final} x{cantidad} (bodega)")
        return total

    def _procesar_tiendas_fila(
        self,
        row: pd.Series,
        columnas_tiendas: Dict[str, Dict[str, Any]],
        df_detalle: pd.DataFrame,
        nombres_columnas_fila1: Dict[int, str],
        data_list: list,
        codigo_producto: str,
        info_producto: Dict[str, Any],
        row_num: int,
    ) -> float:
        total = 0.0
        for codigo_tienda, tienda_info in columnas_tiendas.items():
            col_idx = tienda_info["col_idx"]
            nombre_tienda = nombres_columnas_fila1.get(col_idx, tienda_info["col_name"])
            if col_idx >= len(df_detalle.columns):
                continue
            col_name = df_detalle.columns[col_idx]
            cantidad = self._parsear_cantidad_raw(row.get(col_name), f"tienda {codigo_tienda}", row_num)
            if cantidad is not None:
                codigo_tienda_final = str(codigo_tienda).strip().upper()
                data_list.append({
                    "codigoProducto": codigo_producto,
                    "idTienda": codigo_tienda_final,
                    "nombreTienda": nombre_tienda,
                    "cantidad": cantidad,
                    "filaOrigen": row_num,
                    "es_bodega": False,
                    "info_producto": info_producto
                })
                total += cantidad
                logger.debug(f"   Fila {row_num}: {codigo_producto} → {codigo_tienda_final} ({nombre_tienda}) x{cantidad} (tienda)")
        return total

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

            codigo_producto = self.utils.normalizar_codigo_producto(row.get(col_producto))
            if not codigo_producto:
                resultado["resumen"]["filasInvalidas"] += 1
                resultado["errores"].append({
                    "fila": row_num,
                    "campo": self._CAMPO_CODIGO_PRODUCTO,
                    "tipo": "ERROR",
                    "mensaje": f"{self._CAMPO_CODIGO_PRODUCTO} es obligatorio y no puede estar vacío"
                })
                continue

            info_producto = self.extraer_info_producto(row, columnas_producto, codigo_producto)
            total_esperado = info_producto.get("total")
            total_distribuido = (
                self._procesar_bodegas_fila(row, columnas_bodegas, resultado["data"], codigo_producto, info_producto, row_num)
                + self._procesar_tiendas_fila(row, columnas_tiendas, df_detalle, nombres_columnas_fila1, resultado["data"], codigo_producto, info_producto, row_num)
            )

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
