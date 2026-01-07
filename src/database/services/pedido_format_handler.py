"""
Manejador de formatos Excel para pedidos.
Detecta y procesa diferentes formatos de plantillas Excel.
"""

import logging
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
import io

logger = logging.getLogger(__name__)


class PedidoFormatHandler:
    """Detecta y maneja diferentes formatos de Excel para pedidos."""
    
    @staticmethod
    def detectar_hojas_excel(file_content: bytes) -> Dict[str, Optional[str]]:
        """
        Detecta las hojas disponibles en un archivo Excel.
        
        Retorna dict con claves:
        - 'cabecera': Nombre de hoja CABECERA_PEDIDO
        - 'detalle': Nombre de hoja DETALLE_ARTICULO
        - 'movimiento': Nombre de hoja MOVIMIENTO (v1.0)
        - 'tiendas': Nombre de hoja TIENDAS (v1.0)
        """
        try:
            excel_file = pd.ExcelFile(io.BytesIO(file_content))
            resultado: Dict[str, Optional[str]] = {
                'cabecera': None,
                'detalle': None,
                'movimiento': None,
                'tiendas': None
            }
            
            logger.info(f"Hojas encontradas: {excel_file.sheet_names}")
            
            for sheet_name in excel_file.sheet_names:
                sheet_upper = str(sheet_name).upper().strip()
                
                # Detectar cabecera
                if not resultado['cabecera']:
                    if ("CABECERA" in sheet_upper and "PEDIDO" in sheet_upper) or \
                       sheet_upper == "CABECERA_PEDIDO" or \
                       sheet_upper == "CABECERA PEDIDO":
                        resultado['cabecera'] = str(sheet_name)
                
                # Detectar detalle
                if not resultado['detalle']:
                    if ("DETALLE" in sheet_upper and ("ARTICULO" in sheet_upper or "ARTÍCULO" in sheet_upper)) or \
                       sheet_upper == "DETALLE_ARTICULO" or \
                       sheet_upper == "DETALLE ARTICULO":
                        resultado['detalle'] = str(sheet_name)
                
                # Detectar movimiento (v1.0)
                if not resultado['movimiento']:
                    if sheet_upper == "MOVIMIENTO":
                        resultado['movimiento'] = str(sheet_name)
                
                # Detectar tiendas (v1.0)
                if not resultado['tiendas']:
                    if sheet_upper == "TIENDAS":
                        resultado['tiendas'] = str(sheet_name)
            
            return resultado
        except Exception as e:
            logger.error(f"Error detectando hojas Excel: {e}")
            return {'cabecera': None, 'detalle': None, 'movimiento': None, 'tiendas': None}
    
    @staticmethod
    def detectar_formato_excel(hojas: Dict[str, Optional[str]]) -> str:
        """
        Detecta el formato del Excel basado en las hojas disponibles.
        
        Retorna:
        - 'cuatro_hojas_v1_0': Contiene Cabecera, Detalle, Movimiento, Tiendas
        - 'dos_hojas': Contiene Cabecera y Detalle
        - 'simple': Formato simple con columnas específicas
        - 'desconocido': No se reconoce el formato
        """
        tiene_cabecera = hojas['cabecera'] is not None
        tiene_detalle = hojas['detalle'] is not None
        tiene_movimiento = hojas['movimiento'] is not None
        tiene_tiendas = hojas['tiendas'] is not None
        
        if tiene_cabecera and tiene_detalle and tiene_movimiento and tiene_tiendas:
            return 'cuatro_hojas_v1_0'
        elif tiene_cabecera and tiene_detalle:
            return 'dos_hojas'
        else:
            return 'simple'
    
    @staticmethod
    def detectar_formato_detalle(
        excel_file: pd.ExcelFile,
        sheet_name: str
    ) -> Tuple[bool, List[str]]:
        """
        Detecta si el detalle es formato simple o complejo.
        
        Retorna:
        - (True, []) si es simple (columnas: CodigoProducto, IdTienda, Cantidad)
        - (False, [tienda_cols]) si es complejo (columnas de tiendas)
        """
        try:
            df = pd.read_excel(excel_file, sheet_name=sheet_name, header=0, nrows=1, keep_default_na=False)
            
            if not isinstance(df, pd.DataFrame):
                return False, []
            
            # Normalizar nombres de columnas
            df.columns = [str(col).strip().lower() if pd.notna(col) else "" 
                         for col in df.columns]
            
            # Buscar columnas de tienda (formato complejo)
            import re
            columnas_tiendas = []
            for col in df.columns:
                # Formato: ROL01, ROL02, etc.
                es_codigo = bool(re.match(r'^[a-z]{3}\d{2}$', col))
                # Formato antiguo: contiene "roland"
                es_roland = "roland" in col and col != "roland"
                
                if es_codigo or es_roland:
                    columnas_tiendas.append(col)
            
            # Detectar columnas simples
            has_producto = any('codigoproducto' in col or 'codigo producto' in col for col in df.columns)
            has_idtienda = any('idtienda' in col or 'id tienda' in col for col in df.columns)
            has_cantidad = any('cantidad' in col for col in df.columns)
            
            es_simple = has_producto and has_idtienda and has_cantidad and not columnas_tiendas
            
            return es_simple, columnas_tiendas
        except Exception as e:
            logger.warning(f"Error detectando formato detalle: {e}")
            return False, []
    
    @staticmethod
    def leer_hoja_segura(
        excel_file: pd.ExcelFile,
        sheet_name: str,
        header: Optional[int] = 0
    ) -> pd.DataFrame:
        """
        Lee una hoja de Excel de forma robusta.
        Intenta con header primero, luego sin header.
        """
        try:
            df = pd.read_excel(excel_file, sheet_name=sheet_name, header=header, keep_default_na=False)
            if isinstance(df, pd.DataFrame):
                return df
        except Exception as e:
            logger.warning(f"Error leyendo hoja con header={header}: {e}")
        
        # Intentar sin header
        try:
            df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None, keep_default_na=False)
            if isinstance(df, pd.DataFrame) and len(df) > 0:
                # Usar primera fila como headers
                df_out = df.iloc[1:].copy()
                df_out.columns = df.iloc[0].values
                df_out.columns = [str(col).strip() if pd.notna(col) and str(col).strip() != "" 
                                 else f"col_{i}" for i, col in enumerate(df_out.columns)]
                return df_out
        except Exception as e:
            logger.warning(f"Error leyendo hoja sin header: {e}")
        
        return pd.DataFrame()
