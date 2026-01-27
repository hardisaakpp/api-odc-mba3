"""
Detector de formatos Excel para pedidos.
Centraliza la lógica de detección de diferentes formatos de plantillas.
"""

import logging
import pandas as pd
from typing import Dict, Optional, Tuple
import io

from .pedido_parser.pedido_parser_utils import normalize_column_name

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
                sheet_name_lower = str(sheet_name).lower().strip()
                sheet_name_upper = str(sheet_name).upper().strip()
                
                # Solo se soporta el nuevo formato v1.0 con hojas "cabecera" y "detalle" (minúsculas)
                if not resultado['cabecera'] and sheet_name_lower == "cabecera":
                    resultado['cabecera'] = str(sheet_name)
                    logger.info(f"✅ Hoja de cabecera detectada (formato v1.0): '{sheet_name}'")
                
                if not resultado['detalle'] and sheet_name_lower == "detalle":
                    resultado['detalle'] = str(sheet_name)
                    logger.info(f"✅ Hoja de detalle detectada (formato v1.0): '{sheet_name}'")
                
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
            - 'dos_hojas_nuevo_v1_0': Contiene "cabecera" y "detalle" (formato v1.0 con bodegas) - ÚNICO FORMATO SOPORTADO
            - 'desconocido': No se reconoce el formato
        """
        tiene_cabecera = hojas['cabecera'] is not None
        tiene_detalle = hojas['detalle'] is not None
        
        # Formato de 2 hojas v1.0: hojas "cabecera" y "detalle" en minúsculas (ÚNICO FORMATO SOPORTADO)
        if tiene_cabecera and tiene_detalle:
            cabecera_name = normalize_column_name(hojas['cabecera'])
            detalle_name = normalize_column_name(hojas['detalle'])
            if cabecera_name == "cabecera" and detalle_name == "detalle":
                return 'dos_hojas_nuevo_v1_0'
        
        # Formato no reconocido
        return 'desconocido'
    
