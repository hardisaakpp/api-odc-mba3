"""
Utilidades compartidas para parsers de pedido.

CHANGELOG:
- 2026-01-23: Extraído de pedido_parser.py
- 2026-01-27: Función normalize_column_name para evitar repetir str(x).strip().lower()
"""

import logging
import pandas as pd
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def normalize_column_name(value: Any) -> str:
    """
    Normaliza un nombre de columna/celda para comparación: string, sin espacios, minúsculas.
    None/NaN devuelve "".
    """
    if value is None or (hasattr(pd, "isna") and pd.isna(value)):
        return ""
    return str(value).strip().lower()


def normalize_codigo_columna(value: Any) -> str:
    """
    Normaliza código de columna (bodega/tienda) para evitar artefactos de lectura Excel.
    - Quita espacios.
    - Si las dos primeras letras son iguales (ej. OOUT-CD, TTRL-SNL), quita la primera.
    Así se corrigen columnas leídas con carácter duplicado (merged cells, encoding, etc.).
    """
    if value is None or (hasattr(pd, "isna") and pd.isna(value)):
        return ""
    s = str(value).strip()
    if not s:
        return s
    # Quitar primer carácter duplicado: OOUT-CD -> OUT-CD, TTRL-SNL -> TRL-SNL, RRG-CD -> RG-CD
    if len(s) >= 2 and s[0].upper() == s[1].upper():
        return s[1:].strip()
    return s


class PedidoParserUtils:
    """Utilidades compartidas para parsers de pedido."""

    # Constantes: Mapeo de campos de cabecera
    MAPEO_CAMPOS_CABECERA = {
        "CODIGO PEDIDO": "numero_pedido",
        "CÓDIGO PEDIDO": "numero_pedido",
        "FECHA PEDIDO": "fecha_pedido",
        "FECHA DE PEDIDO": "fecha_pedido",
        "FECHA ENTREGA": "fecha_entrega",
        "FECHA DE ENTREGA": "fecha_entrega",
        "FORMA PAGO": "forma_pago",
        "FORMA DE PAGO": "forma_pago",
        "MENSAJE": "mensaje",
        "NOMBRE PROVEEDOR": "proveedor_nombre",
        "NOMBRE DE PROVEEDOR": "proveedor_nombre",
        "COMPRADOR NOMBRE": "comprador_nombre",
        "COMPRADOR": "comprador_nombre",
        "COD COMPRADOR": "comprador_codigo",
        "CÓD COMPRADOR": "comprador_codigo",
        "CODIGO COMPRADOR": "comprador_codigo",
        "ORIGEN TRASLADO": "origen_traslado",
        "ORIGEN DE TRASLADO": "origen_traslado",
        "SERIE": "serie"
    }
    
    # Constantes: Campos críticos de cabecera
    CAMPOS_CRITICOS_CABECERA = ["numero_pedido", "CODIGO PEDIDO", "CÓDIGO PEDIDO"]
    
    _CLAVE_CODIGO_BARRAS = 'codigo barras'

    # Constantes: Mapeo de columnas de producto
    # NOTA: La columna "marca" fue eliminada de la plantilla Excel (2026-02-05)
    MAPEO_COLUMNAS_PRODUCTO = {
        'codigo producto': ('codigoproducto', 'codigo producto', 'producto', 'sku', 'codigo'),
        _CLAVE_CODIGO_BARRAS: ('codigo de barras', 'codigo_barras', 'código de barras', _CLAVE_CODIGO_BARRAS, 'ean'),
        'descripcion sap': ('descripcion sap', 'descripción sap', 'descripcion', 'descripción'),
        'pack': ('pack', 'unidad', 'unidad de empaque'),
        'costo sin iva': ('costo sin iva', 'costo doc sin iva', 'costo', 'precio sin iva'),
        'descuento': ('descuento', 'dscto', 'dscto 1', 'descuento 1'),
        'pvp': ('pvp', 'precio venta publico', 'precio de venta'),
        'total': ('total',),
        'subtotal': ('subtotal',)
    }
    
    # Constantes: Configuración de bodegas
    BODEGAS_ESPERADAS = {
        'RL-CD': 'BODEGA ROLAND',
        'OUT-CD': 'BODEGA DESCUENTON', 
        'RG-CD': 'BODEGA REGIONS'
    }
    
    VARIANTES_BODEGAS = {
        'RG-CD': 'RG-CD',  # Código correcto en SAP - NO cambiar
        'REG-CD': 'RG-CD',  # Si Excel tiene REG-CD, convertir a RG-CD
        'RL-CD': 'RL-CD',
        'OUT-CD': 'OUT-CD'
    }
    
    # Constantes: Índices de columnas
    # NOTA: Ajustados tras eliminar columna "marca" de la plantilla (2026-02-05)
    INDICE_INICIO_TIENDAS = 12  # Columna M (antes N)
    INDICES_BODEGAS = [9, 10, 11]  # Columnas J, K, L (antes K, L, M)
    INDICES_PRODUCTO = list(range(9))  # Columnas A-I (0-8, antes A-J 0-9)
    
    # Constantes: Prefijos y patrones
    PREFIJO_TIENDA_ANTIGUO = "roland "
    PATRON_CODIGO_TIENDA = r'^[A-Z]{3}\d{2}$'
    PATRON_CODIGO_VALIDO = r'^[A-Z0-9\-\.]+$'
    PATRON_NUMERO_SIMPLE = r'^\d{1,3}$'

    def normalizar_codigo_producto(self, valor_raw: Any) -> Optional[str]:
        """Normaliza código de producto."""
        if valor_raw is not None and not pd.isna(valor_raw):
            codigo = str(valor_raw).strip()
            while "  " in codigo:
                codigo = codigo.replace("  ", " ")
            return codigo if codigo else None
        return None
    
    def normalizar_id_tienda(self, valor_raw: Any) -> Optional[str]:
        """Normaliza ID de tienda."""
        if valor_raw is not None and not pd.isna(valor_raw):
            tienda = str(valor_raw).strip()
            while "  " in tienda:
                tienda = tienda.replace("  ", " ")
            return tienda if tienda else None
        return None
    
    def validar_cantidad(self, cantidad_raw: Any, row_num: int, errores_fila: List[Dict]) -> Optional[float]:
        """Valida y normaliza cantidad (acepta decimales)."""
        if cantidad_raw is not None and not pd.isna(cantidad_raw):
            try:
                cantidad_str = str(cantidad_raw).strip().replace(",", ".")
                cantidad = float(cantidad_str)
                
                if cantidad < 0:
                    errores_fila.append({
                        "fila": row_num,
                        "campo": "Cantidad",
                        "tipo": "ERROR",
                        "mensaje": f"Cantidad no puede ser negativa. Valor recibido: {cantidad_raw}"
                    })
                    return None
                return cantidad
            except (ValueError, TypeError):
                errores_fila.append({
                    "fila": row_num,
                    "campo": "Cantidad",
                    "tipo": "ERROR",
                    "mensaje": f"Cantidad no es un número válido. Valor recibido: {cantidad_raw}"
                })
                return None
        else:
            errores_fila.append({
                "fila": row_num,
                "campo": "Cantidad",
                "tipo": "ERROR",
                "mensaje": "Cantidad es obligatoria y no puede estar vacía"
            })
            return None
    
    def find_column_flexible(self, row: pd.Series, column_names: List[str]) -> Optional[str]:
        """
        Busca una columna de manera flexible, probando múltiples variaciones del nombre.
        
        Args:
            row: Serie de pandas con los datos de la fila
            column_names: Lista de nombres de columnas a buscar (en orden de prioridad)
            
        Returns:
            Nombre de la columna encontrada, o None si no se encuentra ninguna
        """
        # Primero intentar coincidencia exacta (sin espacios extra)
        for col_name in column_names:
            col_normalized = ' '.join(col_name.lower().split())
            if col_normalized in row.index:
                return col_normalized
        
        # Si no hay coincidencia exacta, buscar coincidencia parcial
        for col_name in column_names:
            col_normalized = ' '.join(col_name.lower().split())
            keywords = [kw for kw in col_normalized.split() if len(kw) > 2]
            if not keywords:
                keywords = col_normalized.split()
            
            for idx_col in row.index:
                idx_col_lower = normalize_column_name(idx_col)
                if all(keyword in idx_col_lower for keyword in keywords):
                    return idx_col
        
        return None
    
    @staticmethod
    def _extraer_de_serie(valor: pd.Series) -> Optional[Any]:
        """Extrae el primer elemento de una Series; None si vacía o toda-NaN."""
        if len(valor) == 0 or valor.isna().all():
            return None
        return valor.iloc[0]

    @staticmethod
    def _formatear_codigo_barras(valor: Any) -> str:
        """Convierte valor de código de barras a string sin decimales innecesarios."""
        if isinstance(valor, int):
            return str(valor)
        if isinstance(valor, float):
            return str(int(valor)) if valor.is_integer() else str(valor).rstrip('0').rstrip('.')
        result = str(valor).strip()
        if result.endswith('.0'):
            try:
                num_val = float(result)
                if num_val.is_integer():
                    return str(int(num_val))
            except (ValueError, TypeError):
                pass
        return result

    @staticmethod
    def _normalizar_string_numerico(str_value: str) -> str:
        """Elimina símbolos monetarios y normaliza separador decimal."""
        str_value = str_value.replace('$', '').replace('€', '').replace('USD', '').replace('%', '').strip()
        str_value = ''.join(c for c in str_value if c.isdigit() or c in '.,-')
        if ',' in str_value and '.' in str_value:
            return str_value.replace('.', '').replace(',', '.')
        if ',' in str_value:
            return str_value.replace(',', '.')
        return str_value

    def get_cell_value(self, row: pd.Series, column_name: str, alternative_names: Optional[List[str]] = None) -> Optional[str]:
        """
        Obtiene valor de celda como string, con búsqueda flexible de columnas.

        Args:
            row: Serie de pandas con los datos de la fila
            column_name: Nombre principal de la columna a buscar
            alternative_names: Nombres alternativos para buscar (opcional)
        """
        try:
            names_to_try = [column_name]
            if alternative_names:
                names_to_try.extend(alternative_names)

            found_column = self.find_column_flexible(row, names_to_try)
            if not found_column:
                return None

            valor = row[found_column]
            if isinstance(valor, pd.Series):
                valor = self._extraer_de_serie(valor)
            if valor is None or (isinstance(valor, (float, int)) and pd.isna(valor)):
                return None

            aliases_barras = self.MAPEO_COLUMNAS_PRODUCTO[self._CLAVE_CODIGO_BARRAS]
            es_barras = any(n.lower() in aliases_barras for n in names_to_try)

            result = self._formatear_codigo_barras(valor) if es_barras else str(valor).strip()
            return result if result else None
        except Exception as e:
            logger.debug(f"⚠️ Error al obtener valor de celda '{column_name}': {e}")
            return None
    
    def get_numeric_value(self, row: pd.Series, column_name: str, alternative_names: Optional[List[str]] = None) -> Optional[float]:
        """
        Obtiene valor numérico de celda, manejando formatos de moneda y porcentaje.
        Usa búsqueda flexible de columnas.

        Args:
            row: Serie de pandas con los datos de la fila
            column_name: Nombre principal de la columna a buscar
            alternative_names: Nombres alternativos para buscar (opcional)
        """
        try:
            names_to_try = [column_name]
            if alternative_names:
                names_to_try.extend(alternative_names)

            found_column = self.find_column_flexible(row, names_to_try)
            if not found_column:
                return None

            valor = row[found_column]
            if isinstance(valor, pd.Series):
                valor = self._extraer_de_serie(valor)
            if valor is None or (isinstance(valor, (float, int)) and pd.isna(valor)):
                return None

            if isinstance(valor, (int, float)):
                return float(valor)

            str_value = self._normalizar_string_numerico(str(valor).strip())
            return float(str_value) if str_value else None
        except (ValueError, TypeError) as e:
            logger.debug(f"⚠️ Error al convertir valor numérico de columna '{column_name}': {e}")
            return None
    
    def es_codigo_valido(self, codigo: str) -> bool:
        """
        Valida si un código es válido para tienda/bodega.
        
        Filtra códigos que sean solo números simples (como "1", "2", "3")
        que probablemente son índices o números de fila, no códigos reales.
        
        Args:
            codigo: Código a validar
            
        Returns:
            True si el código es válido, False si es solo un número simple
        """
        codigo_clean = str(codigo).strip().upper()
        
        if re.match(self.PATRON_NUMERO_SIMPLE, codigo_clean):
            return False
        
        tiene_letras = bool(re.search(r'[A-Z]', codigo_clean))
        
        return tiene_letras
