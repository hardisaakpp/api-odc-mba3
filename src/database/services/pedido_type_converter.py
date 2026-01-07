"""
Conversor de tipos de datos para pedidos.
Centraliza toda la lógica de conversión de valores textuales a tipos específicos.
"""

import logging
from typing import Optional, Any
from datetime import datetime, date
import re

logger = logging.getLogger(__name__)


class PedidoTypeConverter:
    """Convierte tipos de datos para procesamiento de pedidos."""
    
    @staticmethod
    def convertir_a_decimal(valor) -> Optional[float]:
        """
        Convierte un valor a decimal (float).
        Tolera formatos: "1.5", "1,5", "1", etc.
        """
        if valor is None or valor == "":
            return None
        
        try:
            if isinstance(valor, (int, float)):
                return float(valor)
            
            # Convertir a string y limpiar
            valor_str = str(valor).strip()
            if valor_str == "":
                return None
            
            # Reemplazar coma por punto (formato europeo)
            valor_str = valor_str.replace(",", ".")
            
            # Intentar conversión
            return float(valor_str)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def convertir_a_entero(valor) -> Optional[int]:
        """
        Convierte un valor a entero.
        Tolera formatos: "10", "10.5" (redondea), etc.
        """
        if valor is None or valor == "":
            return None
        
        try:
            if isinstance(valor, int):
                return valor
            
            # Primero convertir a float y luego a int (redondea)
            decimal = PedidoTypeConverter.convertir_a_decimal(valor)
            if decimal is not None:
                return int(round(decimal))
            
            return None
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def parsear_fecha_texto(valor) -> Any:
        """
        Parsea una fecha desde texto en múltiples formatos.
        Retorna date si es válido, o el valor original si no.
        """
        if valor is None or valor == "":
            return None
        
        # Si ya es date o datetime, retornar como date
        if isinstance(valor, date) and not isinstance(valor, datetime):
            return valor
        if isinstance(valor, datetime):
            return valor.date()
        
        # Convertir a string
        valor_str = str(valor).strip()
        
        # Formatos a intentar (en orden de preferencia)
        formatos = [
            "%d/%m/%Y",      # 01/01/2024
            "%Y-%m-%d",      # 2024-01-01
            "%d-%m-%Y",      # 01-01-2024
            "%d.%m.%Y",      # 01.01.2024
            "%Y/%m/%d",      # 2024/01/01
            "%d/%m/%y",      # 01/01/24
            "%d-%m-%y",      # 01-01-24
        ]
        
        for fmt in formatos:
            try:
                return datetime.strptime(valor_str, fmt).date()
            except ValueError:
                continue
        
        # Si no se puede parsear, retornar el valor original (puede ser "INMEDIATO", etc.)
        logger.warning(f"No se pudo parsear fecha: {valor_str}")
        return valor
    
    @staticmethod
    def normalizar_codigo_producto(codigo: Optional[str]) -> Optional[str]:
        """
        Normaliza un código de producto:
        - Convierte a mayúsculas
        - Elimina espacios en blanco
        - Elimina caracteres especiales
        """
        if not codigo:
            return None
        
        codigo_str = str(codigo).strip().upper()
        # Eliminar espacios
        codigo_str = codigo_str.replace(" ", "")
        
        if codigo_str == "":
            return None
        
        return codigo_str
    
    @staticmethod
    def normalizar_codigo_tienda(codigo: Optional[str]) -> Optional[str]:
        """
        Normaliza un código de tienda:
        - Convierte a mayúsculas
        - Elimina espacios
        - Valida formato (típicamente alfanumérico)
        """
        if not codigo:
            return None
        
        codigo_str = str(codigo).strip().upper()
        codigo_str = codigo_str.replace(" ", "")
        
        if codigo_str == "":
            return None
        
        return codigo_str
    
    @staticmethod
    def extraer_numero_de_ordenes(valor: Optional[str]) -> Optional[int]:
        """
        Extrae un número desde una cadena tipo "5 ORDENES" o "5".
        """
        if not valor:
            return None
        
        valor_str = str(valor).strip()
        
        # Buscar el primer número en la cadena
        match = re.search(r'(\d+)', valor_str)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                return None
        
        return None
    
    @staticmethod
    def booleano_desde_texto(valor: Optional[str]) -> Optional[bool]:
        """
        Convierte texto a booleano.
        Reconoce: "sí", "si", "yes", "1", "true", "activo" como True
        Reconoce: "no", "0", "false", "inactivo" como False
        """
        if valor is None:
            return None
        
        valor_str = str(valor).strip().lower()
        
        if valor_str in ["sí", "si", "yes", "1", "true", "activo", "v"]:
            return True
        if valor_str in ["no", "0", "false", "inactivo", "f"]:
            return False
        
        return None
