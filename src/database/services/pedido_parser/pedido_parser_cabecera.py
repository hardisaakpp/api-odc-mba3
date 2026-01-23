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

    def parsear(self, excel_file: pd.ExcelFile, hoja_cabecera: str) -> Dict[str, Any]:
        """
        Parsea la hoja de cabecera. Soporta formato vertical (campo|valor) y horizontal (campos en fila 1, valores en fila 2).
        
        Args:
            excel_file: Archivo Excel abierto
            hoja_cabecera: Nombre de la hoja de cabecera
            
        Returns:
            Dict con los campos de cabecera parseados
        """
        cabecera = {}
        df_cabecera = pd.read_excel(excel_file, sheet_name=hoja_cabecera, header=None)
        
        logger.info(f"📋 Iniciando parsing de cabecera. Filas: {len(df_cabecera)}, Columnas: {len(df_cabecera.columns)}")
        
        if len(df_cabecera) == 0:
            logger.warning("⚠️ Hoja de cabecera vacía")
            return cabecera
        
        logger.debug(f"📊 Primeras 3 filas de cabecera:")
        for idx in range(min(3, len(df_cabecera))):
            fila = df_cabecera.iloc[idx]
            valores = [str(v)[:30] if pd.notna(v) else "(vacío)" for v in fila.values[:10]]
            logger.debug(f"   Fila {idx}: {valores}")
        
        primera_fila_idx = None
        segunda_fila_idx = None
        
        for idx in range(min(5, len(df_cabecera))):
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
            
            primera_fila_str = [str(v).upper().strip() if pd.notna(v) else "" for v in primera_fila.values]
            segunda_fila_str = [str(v).strip() if pd.notna(v) else "" for v in segunda_fila.values]
            
            campos_conocidos_en_primera = sum(1 for campo in primera_fila_str if any(campo_mapeo in campo for campo_mapeo in self.utils.MAPEO_CAMPOS_CABECERA.keys()))
            valores_en_segunda = sum(1 for v in segunda_fila_str if v and not any(campo_mapeo in v.upper() for campo_mapeo in self.utils.MAPEO_CAMPOS_CABECERA.keys()))
            
            logger.debug(f"   Campos conocidos en primera fila: {campos_conocidos_en_primera}")
            logger.debug(f"   Valores en segunda fila: {valores_en_segunda}")
            
            if campos_conocidos_en_primera >= 2 and valores_en_segunda >= 2:
                es_formato_horizontal = True
                logger.info(f"📊 Detectado formato HORIZONTAL (campos en fila {primera_fila_idx + 1}, valores en fila {segunda_fila_idx + 1})")
            else:
                logger.info(f"📊 No se detectó formato horizontal. Campos conocidos: {campos_conocidos_en_primera}, Valores: {valores_en_segunda}")
        
        if es_formato_horizontal:
            logger.info("🔍 Procesando formato HORIZONTAL")
            for col_idx in range(len(df_cabecera.columns)):
                campo_raw = df_cabecera.iloc[int(primera_fila_idx) if primera_fila_idx is not None else 0, col_idx] if col_idx < len(df_cabecera.columns) else None
                valor_raw = df_cabecera.iloc[int(segunda_fila_idx) if segunda_fila_idx is not None else 0, col_idx] if col_idx < len(df_cabecera.columns) else None
                
                if campo_raw is not None and not pd.isna(campo_raw):
                    campo = str(campo_raw).strip()
                    valor = str(valor_raw).strip() if valor_raw is not None and not pd.isna(valor_raw) else None
                    
                    if campo and valor:
                        cabecera[campo] = valor
                        
                        campo_normalizado = self.mapear_campo(campo)
                        if campo_normalizado:
                            cabecera[campo_normalizado] = valor
                            logger.info(f"✓ Campo mapeado: '{campo}' → '{campo_normalizado}' = '{valor}'")
                        else:
                            campo_gen = campo.lower().replace(" ", "_")
                            cabecera[campo_gen] = valor
                            logger.debug(f"⚠️ Campo sin mapeo específico: '{campo}' → '{campo_gen}' = '{valor}'")
        else:
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
                            
                            campo_normalizado = self.mapear_campo(campo)
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
