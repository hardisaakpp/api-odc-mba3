"""
Procesador de formatos específicos de Excel para pedidos.
Maneja el procesamiento de formatos dos hojas y simple.
"""

import logging
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
import io

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
        # Extraer datos de cabecera
        cabecera_parseada = self.parser.parsear_cabecera(excel_file, str(hoja_cabecera_encontrada))
        cabecera = self.consolidator.normalizar_cabecera_para_bd(
            cabecera_parseada=cabecera_parseada,
            filename=filename,
            usuario_id=usuario_id
        )
        
        # Coerción de fechas
        try:
            valor_fecha_pedido = cabecera.get("fecha_pedido", cabecera.get("fecha_de_pedido"))
            if valor_fecha_pedido is not None:
                cabecera["fecha_pedido"] = self.type_converter.parsear_fecha_texto(valor_fecha_pedido)
            valor_fecha_entrega = cabecera.get("fecha_entrega", cabecera.get("fecha_de_entrega"))
            if valor_fecha_entrega is not None:
                cabecera["fecha_entrega"] = self.type_converter.parsear_fecha_texto(valor_fecha_entrega)
        except Exception:
            pass
        
        # Detectar formato del detalle
        df_detalle_detection = pd.read_excel(
            excel_file, 
            sheet_name=str(hoja_detalle_encontrada), 
            header=0, 
            nrows=1,
            keep_default_na=False
        )
        
        # Normalizar nombres de columnas
        if not isinstance(df_detalle_detection, pd.DataFrame):
            return cabecera, None
            
        df_detalle_detection.columns = [str(col).strip() if pd.notna(col) and str(col).strip() != "" else "" 
                                       for col in df_detalle_detection.columns]
        
        # Buscar columnas de tiendas
        columnas_tiendas = []
        import re
        for col in df_detalle_detection.columns:
            col_upper = str(col).upper().strip()
            es_codigo_tienda = bool(re.match(r'^[A-Z]{3}\d{2}$', col_upper))
            es_formato_antiguo = "ROLAND" in col_upper and col_upper != "ROLAND"
            if es_codigo_tienda or es_formato_antiguo:
                columnas_tiendas.append(col)
        
        # Detección de formato simple
        df_detalle_detection_lower = df_detalle_detection.copy()
        df_detalle_detection_lower.columns = [str(col).strip().lower() if pd.notna(col) else "" 
                                              for col in df_detalle_detection_lower.columns]
        has_producto = any('codigoproducto' in col or 'codigo producto' in col for col in df_detalle_detection_lower.columns)
        has_idtienda = any('idtienda' in col or 'id tienda' in col for col in df_detalle_detection_lower.columns)
        has_cantidad = any('cantidad' in col for col in df_detalle_detection_lower.columns)
        is_detalle_simple = (has_producto and has_idtienda and has_cantidad) and not columnas_tiendas
        
        if is_detalle_simple:
            logger.info("📋 Detalle en formato SIMPLE")
            resultado_parsing = self.parser.parsear_excel_pedido(
                file_content=file_content,
                hoja_cabecera=str(hoja_cabecera_encontrada),
                hoja_detalle=str(hoja_detalle_encontrada)
            )
            detalles: List[Dict[str, Any]] = self.consolidator.consolidar_detalles_simple(resultado_parsing.get("data", []))
        else:
            logger.info("📋 Detalle en formato COMPLEJO")
            catalogo_tiendas = self.parser.leer_hoja_tiendas(file_content)
            
            try:
                df_detalle: pd.DataFrame = pd.read_excel(
                    excel_file, 
                    sheet_name=str(hoja_detalle_encontrada), 
                    header=0,
                    keep_default_na=False
                )
                if not isinstance(df_detalle, pd.DataFrame):
                    return cabecera, None
            except Exception as e:
                try:
                    df_detalle_raw: pd.DataFrame = pd.read_excel(
                        excel_file, 
                        sheet_name=str(hoja_detalle_encontrada), 
                        header=None,
                        keep_default_na=False
                    )
                    if not isinstance(df_detalle_raw, pd.DataFrame):
                        return cabecera, None
                        
                    if len(df_detalle_raw) > 0:
                        df_detalle = df_detalle_raw.iloc[1:].copy()
                        df_detalle.columns = df_detalle_raw.iloc[0].values
                        df_detalle.columns = [str(col).strip() if pd.notna(col) and str(col).strip() != "" else f"col_{i}" 
                                             for i, col in enumerate(df_detalle.columns)]
                    else:
                        df_detalle = pd.DataFrame()
                except Exception:
                    df_detalle = pd.DataFrame()
            
            if len(df_detalle) == 0:
                detalles = []
            else:
                df_detalle_sin_header = df_detalle.copy()
                columnas_lista = list(df_detalle.columns)
                headers_row = pd.DataFrame([columnas_lista], columns=pd.Index(columnas_lista))
                df_detalle_sin_header = pd.concat([headers_row, df_detalle.reset_index(drop=True)], ignore_index=True)
                df_detalle_sin_header.columns = [str(i) for i in range(len(df_detalle_sin_header.columns))]
                detalles = self.parser.extraer_detalle_con_tiendas(
                    df_detalle_sin_header,
                    catalogo_tiendas=catalogo_tiendas
                )
        
        return cabecera, detalles
