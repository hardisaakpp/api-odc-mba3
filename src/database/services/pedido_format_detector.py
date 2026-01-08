"""
Detector de formatos Excel para pedidos.
Centraliza la lógica de detección de diferentes formatos de plantillas.
"""

import logging
import pandas as pd
from typing import Dict, Optional, Tuple
import io

logger = logging.getLogger(__name__)


class PedidoFormatDetector:
    """Detecta el formato de archivos Excel de pedidos."""
    
    @staticmethod
    def detectar_hojas(file_content: bytes) -> Dict[str, Optional[str]]:
        """
        Detecta las hojas disponibles en un archivo Excel.
        
        Returns:
            Dict con claves: 'cabecera', 'detalle', 'movimiento', 'tiendas'
        """
        try:
            excel_file = pd.ExcelFile(io.BytesIO(file_content))
            resultado: Dict[str, Optional[str]] = {
                'cabecera': None,
                'detalle': None,
                'movimiento': None,
                'tiendas': None
            }
            
            logger.info(f"📄 Hojas encontradas en el Excel: {excel_file.sheet_names}")
            
            for sheet_name in excel_file.sheet_names:
                sheet_name_upper = str(sheet_name).upper().strip()
                
                # Buscar variaciones de CABECERA_PEDIDO
                if not resultado['cabecera']:
                    if ("CABECERA" in sheet_name_upper and "PEDIDO" in sheet_name_upper) or \
                       sheet_name_upper == "CABECERA_PEDIDO" or \
                       sheet_name_upper == "CABECERA PEDIDO":
                        resultado['cabecera'] = str(sheet_name)
                        logger.info(f"✅ Hoja de cabecera detectada: '{sheet_name}'")
                
                # Buscar variaciones de DETALLE_ARTICULO
                if not resultado['detalle']:
                    if ("DETALLE" in sheet_name_upper and "ARTICULO" in sheet_name_upper) or \
                       ("DETALLE" in sheet_name_upper and "ARTÍCULO" in sheet_name_upper) or \
                       sheet_name_upper == "DETALLE_ARTICULO" or \
                       sheet_name_upper == "DETALLE ARTICULO":
                        resultado['detalle'] = str(sheet_name)
                        logger.info(f"✅ Hoja de detalle detectada: '{sheet_name}'")
                
                # Buscar variaciones de MOVIMIENTO (nuevo formato v1.0)
                if not resultado['movimiento']:
                    if sheet_name_upper == "MOVIMIENTO":
                        resultado['movimiento'] = str(sheet_name)
                        logger.info(f"✅ Hoja de movimiento detectada: '{sheet_name}'")
                
                # Buscar variaciones de TIENDAS (nuevo formato v1.0)
                if not resultado['tiendas']:
                    if sheet_name_upper == "TIENDAS":
                        resultado['tiendas'] = str(sheet_name)
                        logger.info(f"✅ Hoja de tiendas detectada: '{sheet_name}'")
            
            return resultado
        except Exception as e:
            logger.error(f"❌ Error detectando hojas Excel: {e}", exc_info=True)
            return {'cabecera': None, 'detalle': None, 'movimiento': None, 'tiendas': None}
    
    @staticmethod
    def detectar_formato(hojas: Dict[str, Optional[str]]) -> str:
        """
        Detecta el formato del Excel basado en las hojas disponibles.
        
        Returns:
            - 'cuatro_hojas_v1_0': Contiene Cabecera, Detalle, Movimiento, Tiendas
            - 'dos_hojas': Contiene Cabecera y Detalle
            - 'simple': Formato simple con columnas específicas
            - 'complejo': Formato legacy con cabecera y columnas de tiendas
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
            # Necesitamos más información para determinar si es simple o complejo
            return 'simple'  # Por defecto, se detectará más adelante
    
    @staticmethod
    def detectar_formato_detalle_simple(file_content: bytes) -> bool:
        """
        Detecta si el detalle es formato simple basado en las columnas.
        
        Returns:
            True si es formato simple (CodigoProducto, IdTienda, Cantidad)
        """
        try:
            df_detection = pd.read_excel(io.BytesIO(file_content), sheet_name=0, header=0, nrows=5)
            df_detection.columns = [str(col).strip().lower() if pd.notna(col) else "" 
                                   for col in df_detection.columns]
            
            has_producto = any('codigoproducto' in col or 'producto' in col for col in df_detection.columns)
            has_idtienda = any('idtienda' in col or 'id tienda' in col for col in df_detection.columns)
            has_cantidad = any('cantidad' in col for col in df_detection.columns)
            
            return has_producto and has_idtienda and has_cantidad
        except Exception as e:
            logger.warning(f"⚠️ Error detectando formato detalle simple: {e}")
            return False
