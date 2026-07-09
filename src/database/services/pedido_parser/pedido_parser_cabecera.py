"""
Parser especializado para cabecera de pedidos.

CHANGELOG:
- 2026-01-23: Extraído de pedido_parser.py
"""

import logging
import pandas as pd
from typing import Dict, Any, Optional

from .pedido_parser_utils import PedidoParserUtils

logger = logging.getLogger(__name__)


class PedidoParserCabecera:
    """Parser para cabecera de pedidos."""

    def __init__(self):
        """Inicializa el parser con utilidades compartidas."""
        self.utils = PedidoParserUtils()

    # ========== Helpers privados ==========

    @staticmethod
    def _log_primeras_filas(df: pd.DataFrame) -> None:
        logger.debug("📊 Primeras 3 filas de cabecera:")
        for idx in range(min(3, len(df))):
            valores = [str(v)[:30] if pd.notna(v) else "(vacío)" for v in df.iloc[idx].values[:10]]
            logger.debug(f"   Fila {idx}: {valores}")

    @staticmethod
    def _encontrar_filas_con_datos(df: pd.DataFrame):
        primera_fila_idx = None
        segunda_fila_idx = None
        for idx in range(min(5, len(df))):
            if any(pd.notna(v) and str(v).strip() for v in df.iloc[idx].values):
                if primera_fila_idx is None:
                    primera_fila_idx = idx
                else:
                    segunda_fila_idx = idx
                    break
        return primera_fila_idx, segunda_fila_idx

    def _detectar_formato_horizontal(
        self, df: pd.DataFrame, primera_fila_idx, segunda_fila_idx
    ) -> bool:
        if primera_fila_idx is None or segunda_fila_idx is None:
            return False
        primera_fila_str = [
            str(v).upper().strip() if pd.notna(v) else "" for v in df.iloc[primera_fila_idx].values
        ]
        segunda_fila_str = [
            str(v).strip() if pd.notna(v) else "" for v in df.iloc[segunda_fila_idx].values
        ]
        campos_conocidos = sum(
            1 for campo in primera_fila_str
            if any(k in campo for k in self.utils.MAPEO_CAMPOS_CABECERA.keys())
        )
        valores = sum(
            1 for v in segunda_fila_str
            if v and not any(k in v.upper() for k in self.utils.MAPEO_CAMPOS_CABECERA.keys())
        )
        logger.debug(f"   Campos conocidos en primera fila: {campos_conocidos}")
        logger.debug(f"   Valores en segunda fila: {valores}")
        if campos_conocidos >= 2 and valores >= 2:
            logger.info(
                f"📊 Detectado formato HORIZONTAL "
                f"(campos en fila {primera_fila_idx + 1}, valores en fila {segunda_fila_idx + 1})"
            )
            return True
        logger.info(
            f"📊 No se detectó formato horizontal. "
            f"Campos conocidos: {campos_conocidos}, Valores: {valores}"
        )
        return False

    def _registrar_campo(self, cabecera: dict, campo: str, valor: str) -> None:
        cabecera[campo] = valor
        campo_normalizado = self.mapear_campo(campo)
        if campo_normalizado:
            cabecera[campo_normalizado] = valor
            logger.info(f"✓ Campo mapeado: '{campo}' → '{campo_normalizado}' = '{valor}'")
        else:
            campo_gen = campo.lower().replace(" ", "_")
            cabecera[campo_gen] = valor
            logger.debug(f"⚠️ Campo sin mapeo específico: '{campo}' → '{campo_gen}' = '{valor}'")

    def _procesar_formato_horizontal(
        self, df: pd.DataFrame, primera_fila_idx: int, segunda_fila_idx: int
    ) -> Dict[str, Any]:
        cabecera: Dict[str, Any] = {}
        logger.info("🔍 Procesando formato HORIZONTAL")
        for col_idx in range(len(df.columns)):
            campo_raw = df.iloc[primera_fila_idx, col_idx]
            valor_raw = df.iloc[segunda_fila_idx, col_idx]
            if campo_raw is not None and not pd.isna(campo_raw):
                campo = str(campo_raw).strip()
                valor = str(valor_raw).strip() if valor_raw is not None and not pd.isna(valor_raw) else None
                if campo and valor:
                    self._registrar_campo(cabecera, campo, valor)
        return cabecera

    @staticmethod
    def _detectar_columnas_verticales(df: pd.DataFrame):
        if len(df) == 0:
            return 0, 1, 0
        primera_fila_str = [
            str(v).upper().strip() if pd.notna(v) else "" for v in df.iloc[0].values
        ]
        tiene_campo = any("CAMPO" in v for v in primera_fila_str)
        tiene_valor = any("VALOR" in v for v in primera_fila_str)
        if tiene_campo or tiene_valor:
            col_campo_idx = next((i for i, v in enumerate(primera_fila_str) if "CAMPO" in v), 0)
            col_valor_idx = next((i for i, v in enumerate(primera_fila_str) if "VALOR" in v), 1)
            return col_campo_idx, col_valor_idx, 1
        return 0, 1, 0

    def _procesar_fila_vertical(
        self,
        df: "pd.DataFrame",
        idx: int,
        col_campo_idx: int,
        col_valor_idx: int,
        cabecera: Dict[str, Any],
    ) -> None:
        """Procesa una fila del formato vertical y registra el campo si es válido."""
        campo_raw = df.iloc[idx, col_campo_idx] if col_campo_idx < len(df.columns) else None
        valor_raw = df.iloc[idx, col_valor_idx] if col_valor_idx < len(df.columns) else None
        if campo_raw is not None and not pd.isna(campo_raw):
            campo = str(campo_raw).strip()
            valor = str(valor_raw).strip() if valor_raw is not None and not pd.isna(valor_raw) else None
            if campo and valor:
                self._registrar_campo(cabecera, campo, valor)

    def _procesar_formato_vertical(self, df: pd.DataFrame) -> Dict[str, Any]:
        cabecera: Dict[str, Any] = {}
        logger.info("🔍 Procesando formato VERTICAL (campo|valor)")
        if len(df.columns) < 2:
            return cabecera
        col_campo_idx, col_valor_idx, start_row = self._detectar_columnas_verticales(df)
        logger.info(f"   Usando columnas: Campo={col_campo_idx}, Valor={col_valor_idx}, Start row={start_row}")
        for idx in range(start_row, len(df)):
            self._procesar_fila_vertical(df, idx, col_campo_idx, col_valor_idx, cabecera)
        return cabecera

    # ========== Interfaz pública ==========

    def parsear(self, excel_file: pd.ExcelFile, hoja_cabecera: str) -> Dict[str, Any]:
        """
        Parsea la hoja de cabecera. Soporta formato vertical (campo|valor) y horizontal (campos en fila 1, valores en fila 2).

        Args:
            excel_file: Archivo Excel abierto
            hoja_cabecera: Nombre de la hoja de cabecera

        Returns:
            Dict con los campos de cabecera parseados
        """
        df_cabecera = pd.read_excel(excel_file, sheet_name=hoja_cabecera, header=None)
        logger.info(
            f"📋 Iniciando parsing de cabecera. Filas: {len(df_cabecera)}, Columnas: {len(df_cabecera.columns)}"
        )
        if len(df_cabecera) == 0:
            logger.warning("⚠️ Hoja de cabecera vacía")
            return {}

        self._log_primeras_filas(df_cabecera)
        primera_fila_idx, segunda_fila_idx = self._encontrar_filas_con_datos(df_cabecera)
        logger.info(
            f"📊 Primera fila con datos: {primera_fila_idx}, Segunda fila con datos: {segunda_fila_idx}"
        )

        if (
            primera_fila_idx is not None
            and segunda_fila_idx is not None
            and self._detectar_formato_horizontal(df_cabecera, primera_fila_idx, segunda_fila_idx)
        ):
            cabecera = self._procesar_formato_horizontal(df_cabecera, primera_fila_idx, segunda_fila_idx)
        else:
            cabecera = self._procesar_formato_vertical(df_cabecera)

        logger.info(f"✅ Cabecera parseada: {len(cabecera)} campos encontrados")
        logger.info(f"   Campos: {list(cabecera.keys())}")
        return cabecera

    def mapear_campo(self, campo: str) -> Optional[str]:
        """
        Mapea un campo de cabecera a su nombre normalizado.

        Args:
            campo: Nombre del campo en el Excel

        Returns:
            Nombre normalizado del campo o None si no hay mapeo
        """
        campo_upper = campo.upper().strip()

        if campo_upper in self.utils.MAPEO_CAMPOS_CABECERA:
            return self.utils.MAPEO_CAMPOS_CABECERA[campo_upper]

        for campo_excel, campo_bd in self.utils.MAPEO_CAMPOS_CABECERA.items():
            if campo_upper == campo_excel.upper() or campo_upper.startswith(campo_excel.upper()):
                return campo_bd

        return None
