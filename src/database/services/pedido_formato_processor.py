"""
Procesador de formatos específicos de Excel para pedidos.
Maneja el procesamiento de formatos dos hojas y simple.
"""

import logging
import re
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

from .pedido_parser.pedido_parser_utils import normalize_column_name

logger = logging.getLogger(__name__)


class PedidoFormatoProcessor:
    """Procesa formatos específicos de Excel para pedidos."""

    def __init__(self, parser, consolidator, type_converter):
        """
        Inicializa el procesador.

        Args:
            parser: Instancia de PedidoParser
            consolidator: Instancia de PedidoConsolidator
            type_converter: Instancia de PedidoTypeConverter
        """
        self.parser = parser
        self.consolidator = consolidator
        self.type_converter = type_converter

    def _coercionar_fechas(self, cabecera: Dict[str, Any]) -> Dict[str, Any]:
        try:
            valor_fecha_pedido = cabecera.get("fecha_pedido", cabecera.get("fecha_de_pedido"))
            if valor_fecha_pedido is not None:
                cabecera["fecha_pedido"] = self.type_converter.parsear_fecha_texto(valor_fecha_pedido)
            valor_fecha_entrega = cabecera.get("fecha_entrega", cabecera.get("fecha_de_entrega"))
            if valor_fecha_entrega is not None:
                cabecera["fecha_entrega"] = self.type_converter.parsear_fecha_texto(valor_fecha_entrega)
        except Exception:
            pass
        return cabecera

    @staticmethod
    def _es_detalle_simple(df: pd.DataFrame) -> bool:
        cols_stripped = [
            str(col).strip() if pd.notna(col) and str(col).strip() != "" else ""
            for col in df.columns
        ]

        columnas_tiendas = []
        for col in cols_stripped:
            col_upper = col.upper()
            es_codigo_tienda = bool(re.match(r'^[A-Z]{3}\d{2}$', col_upper))
            es_formato_antiguo = "ROLAND" in col_upper and col_upper != "ROLAND"
            if es_codigo_tienda or es_formato_antiguo:
                columnas_tiendas.append(col)

        cols_normalized = [normalize_column_name(col) for col in cols_stripped]
        has_producto = any('codigoproducto' in col or 'codigo producto' in col for col in cols_normalized)
        has_idtienda = any('idtienda' in col or 'id tienda' in col for col in cols_normalized)
        has_cantidad = any('cantidad' in col for col in cols_normalized)

        return has_producto and has_idtienda and has_cantidad and not columnas_tiendas

    def _leer_df_detalle(
        self,
        excel_file: pd.ExcelFile,
        sheet_name: str
    ) -> Optional[pd.DataFrame]:
        try:
            df = pd.read_excel(excel_file, sheet_name=sheet_name, header=0, keep_default_na=False)
            if not isinstance(df, pd.DataFrame):
                return None
            return df
        except Exception:
            pass

        try:
            df_raw: pd.DataFrame = pd.read_excel(
                excel_file, sheet_name=sheet_name, header=None, keep_default_na=False
            )
            if not isinstance(df_raw, pd.DataFrame):
                return None
            if len(df_raw) > 0:
                df = df_raw.iloc[1:].copy()
                df.columns = df_raw.iloc[0].values
                df.columns = [
                    str(col).strip() if pd.notna(col) and str(col).strip() != "" else f"col_{i}"
                    for i, col in enumerate(df.columns)
                ]
                return df
            return pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    def _procesar_detalle_complejo(
        self,
        file_content: bytes,
        excel_file: pd.ExcelFile,
        hoja_detalle: Optional[str]
    ) -> Optional[List[Dict[str, Any]]]:
        catalogo_tiendas = self.parser.leer_hoja_tiendas(file_content)
        df_detalle = self._leer_df_detalle(excel_file, str(hoja_detalle))

        if df_detalle is None:
            return None

        if len(df_detalle) == 0:
            return []

        columnas_lista = list(df_detalle.columns)
        headers_row = pd.DataFrame([columnas_lista], columns=pd.Index(columnas_lista))
        df_sin_header = pd.concat([headers_row, df_detalle.reset_index(drop=True)], ignore_index=True)
        df_sin_header.columns = [str(i) for i in range(len(df_sin_header.columns))]
        return self.parser.extraer_detalle_con_tiendas(df_sin_header, catalogo_tiendas=catalogo_tiendas)

    def procesar_formato_dos_hojas_o_simple(
        self,
        file_content: bytes,
        filename: str,
        usuario_id: Optional[str],
        excel_file: pd.ExcelFile,
        hoja_cabecera_encontrada: Optional[str],
        hoja_detalle_encontrada: Optional[str]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
        """
        Procesa formato de dos hojas (CABECERA_PEDIDO + DETALLE_ARTICULO) o simple.

        Returns:
            (cabecera_dict, detalles_list) o (None, None) si error
        """
        cabecera_parseada = self.parser.parsear_cabecera(excel_file, str(hoja_cabecera_encontrada))
        cabecera = self.consolidator.normalizar_cabecera_para_bd(
            cabecera_parseada=cabecera_parseada,
            filename=filename,
            usuario_id=usuario_id
        )
        cabecera = self._coercionar_fechas(cabecera)

        df_detalle_detection = pd.read_excel(
            excel_file,
            sheet_name=str(hoja_detalle_encontrada),
            header=0,
            nrows=1,
            keep_default_na=False
        )

        if not isinstance(df_detalle_detection, pd.DataFrame):
            return cabecera, None

        if self._es_detalle_simple(df_detalle_detection):
            logger.info("📋 Detalle en formato SIMPLE")
            resultado_parsing = self.parser.parsear_excel_pedido(
                file_content=file_content,
                hoja_cabecera=str(hoja_cabecera_encontrada),
                hoja_detalle=str(hoja_detalle_encontrada)
            )
            detalles = self.consolidator.consolidar_detalles_simple(
                resultado_parsing.get("data", [])
            )
        else:
            logger.info("📋 Detalle en formato COMPLEJO")
            detalles = self._procesar_detalle_complejo(file_content, excel_file, hoja_detalle_encontrada)
            if detalles is None:
                return cabecera, None

        return cabecera, detalles
