"""
Paquete de parsers especializados para pedidos.

CHANGELOG:
- 2026-01-23: Creado para organizar parsers de pedido
- 2026-01-23: Movida clase PedidoParser aquí para resolver conflicto de nombres
"""

import logging
import pandas as pd
import io
from typing import Dict, Any, Optional

from .pedido_parser_utils import PedidoParserUtils
from .pedido_parser_cabecera import PedidoParserCabecera
from .pedido_parser_detalle import PedidoParserDetalle
from .pedido_parser_tiendas import PedidoParserTiendas

logger = logging.getLogger(__name__)


class PedidoParser:
    """
    Parser para archivos Excel de pedidos.
    
    REFACTORIZADO: Facade que delega a parsers especializados.
    Mantiene la misma interfaz pública para compatibilidad hacia atrás.
    """
    
    # Constantes compartidas (delegadas a utils)
    MAPEO_CAMPOS_CABECERA = PedidoParserUtils.MAPEO_CAMPOS_CABECERA
    CAMPOS_CRITICOS_CABECERA = PedidoParserUtils.CAMPOS_CRITICOS_CABECERA
    MAPEO_COLUMNAS_PRODUCTO = PedidoParserUtils.MAPEO_COLUMNAS_PRODUCTO
    BODEGAS_ESPERADAS = PedidoParserUtils.BODEGAS_ESPERADAS
    VARIANTES_BODEGAS = PedidoParserUtils.VARIANTES_BODEGAS
    INDICE_INICIO_TIENDAS = PedidoParserUtils.INDICE_INICIO_TIENDAS
    INDICES_BODEGAS = PedidoParserUtils.INDICES_BODEGAS
    INDICES_PRODUCTO = PedidoParserUtils.INDICES_PRODUCTO
    PREFIJO_TIENDA_ANTIGUO = PedidoParserUtils.PREFIJO_TIENDA_ANTIGUO
    PATRON_CODIGO_TIENDA = PedidoParserUtils.PATRON_CODIGO_TIENDA
    PATRON_CODIGO_VALIDO = PedidoParserUtils.PATRON_CODIGO_VALIDO
    PATRON_NUMERO_SIMPLE = PedidoParserUtils.PATRON_NUMERO_SIMPLE

    def __init__(self):
        """Inicializa el parser con sus módulos especializados."""
        self.cabecera_parser = PedidoParserCabecera()
        self.detalle_parser = PedidoParserDetalle()
        self.tiendas_parser = PedidoParserTiendas()
        self.utils = PedidoParserUtils()

    def parsear_excel_pedido(
        self,
        file_content: bytes,
        hoja_cabecera: str = "cabecera",
        hoja_detalle: str = "detalle"
    ) -> Dict[str, Any]:
        """
        Parsea un archivo Excel de pedido en formato v1.0.
        
        DELEGADO a parsers especializados.
        """
        resultado = {
            "cabecera": {},
            "resumen": {
                "filasLeidas": 0,
                "filasValidas": 0,
                "filasInvalidas": 0
            },
            "errores": [],
            "data": []
        }
        
        try:
            excel_file = pd.ExcelFile(io.BytesIO(file_content))
            
            if hoja_cabecera not in excel_file.sheet_names:
                resultado["errores"].append({
                    "fila": 0,
                    "campo": "Hoja",
                    "tipo": "ERROR",
                    "mensaje": f"La hoja '{hoja_cabecera}' no existe en el archivo. Hojas disponibles: {', '.join(str(s) for s in excel_file.sheet_names)}"
                })
                resultado["resumen"]["filasInvalidas"] = 1
                return resultado
            
            if hoja_detalle not in excel_file.sheet_names:
                resultado["errores"].append({
                    "fila": 0,
                    "campo": "Hoja",
                    "tipo": "ERROR",
                    "mensaje": f"La hoja '{hoja_detalle}' no existe en el archivo. Hojas disponibles: {', '.join(str(s) for s in excel_file.sheet_names)}"
                })
                resultado["resumen"]["filasInvalidas"] = 1
                return resultado
            
            # PASO 1: Leer y parsear hoja "cabecera"
            resultado["cabecera"] = self.cabecera_parser.parsear(excel_file, hoja_cabecera)
            
            # Validar que campos críticos estén presentes
            tiene_codigo_pedido = any(campo in resultado["cabecera"] for campo in self.CAMPOS_CRITICOS_CABECERA)
            if not tiene_codigo_pedido:
                resultado["errores"].append({
                    "fila": 0,
                    "campo": "CODIGO PEDIDO",
                    "tipo": "WARNING",
                    "mensaje": "No se encontró el campo 'CODIGO PEDIDO' en la cabecera. Campos encontrados: " + ", ".join(list(resultado["cabecera"].keys())[:5])
                })
            
            # PASO 2: Leer y parsear hoja "detalle" (nuevo formato v1.0)
            detalle_resultado = self.detalle_parser.parsear_nuevo_formato_v1_0(excel_file, file_content, hoja_detalle)
            resultado["resumen"].update(detalle_resultado["resumen"])
            resultado["errores"].extend(detalle_resultado["errores"])
            resultado["data"] = detalle_resultado["data"]
            
            logger.info(
                f"✅ Parsing completado: {resultado['resumen']['filasLeidas']} filas leídas, "
                f"{resultado['resumen']['filasValidas']} válidas, "
                f"{resultado['resumen']['filasInvalidas']} inválidas"
            )
            
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error al parsear Excel: {e}", exc_info=True)
            resultado["errores"].append({
                "fila": 0,
                "campo": "Archivo",
                "tipo": "ERROR",
                "mensaje": f"Error al leer el archivo Excel: {str(e)}"
            })
            resultado["resumen"]["filasInvalidas"] = resultado["resumen"]["filasLeidas"]
            return resultado

    # ========== Métodos delegados a parsers especializados ==========

    def parsear_cabecera(self, excel_file: pd.ExcelFile, hoja_cabecera: str = "cabecera") -> Dict[str, Any]:
        """
        Parsea solo la hoja de cabecera.
        
        DELEGADO a PedidoParserCabecera.
        
        Args:
            excel_file: Archivo Excel abierto
            hoja_cabecera: Nombre de la hoja de cabecera
            
        Returns:
            Dict con los campos de cabecera parseados
        """
        return self.cabecera_parser.parsear(excel_file, hoja_cabecera)

    def leer_hoja_tiendas(self, file_content: bytes) -> Dict[str, Dict]:
        """
        Lee la hoja "Tiendas" y retorna catálogo NORMALIZADO.
        
        DELEGADO a PedidoParserTiendas.
        """
        return self.tiendas_parser.leer_hoja_tiendas(file_content)

    def leer_hoja_movimiento(
        self, 
        file_content: bytes, 
        catalogo_tiendas: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Lee la hoja 'Movimiento' del Excel y retorna distribuciones por producto y tienda.
        
        DELEGADO a PedidoParserTiendas.
        """
        return self.tiendas_parser.leer_hoja_movimiento(file_content, catalogo_tiendas)

    def extraer_distribuciones_tienda(
        self, 
        row: pd.Series, 
        columnas: list,
        catalogo_tiendas: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> list:
        """
        Extrae distribuciones por tienda desde las columnas del Excel.
        
        DELEGADO a PedidoParserTiendas.
        """
        return self.tiendas_parser.extraer_distribuciones_tienda(row, columnas, catalogo_tiendas)

    # ========== Métodos de utilidad (delegados a utils) ==========

    def get_cell_value(self, row: pd.Series, column_name: str, alternative_names: Optional[list] = None) -> Optional[str]:
        """
        Obtiene valor de celda como string, con búsqueda flexible de columnas.
        
        DELEGADO a PedidoParserUtils.
        """
        return self.utils.get_cell_value(row, column_name, alternative_names)

    def get_numeric_value(self, row: pd.Series, column_name: str, alternative_names: Optional[list] = None) -> Optional[float]:
        """
        Obtiene valor numérico de celda, manejando formatos de moneda y porcentaje.
        
        DELEGADO a PedidoParserUtils.
        """
        return self.utils.get_numeric_value(row, column_name, alternative_names)


__all__ = [
    'PedidoParser',
    'PedidoParserUtils',
    'PedidoParserCabecera',
    'PedidoParserDetalle',
    'PedidoParserTiendas',
]
