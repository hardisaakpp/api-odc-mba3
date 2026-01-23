"""
Utilidades compartidas para parsers de pedido.

CHANGELOG:
- 2026-01-23: Extraído de pedido_parser.py
"""

import logging
import pandas as pd
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


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
        "ODC": "odc",
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
    
    # Constantes: Mapeo de columnas de producto
    MAPEO_COLUMNAS_PRODUCTO = {
        'codigo producto': ('codigoproducto', 'codigo producto', 'producto', 'sku', 'codigo'),
        'marca': ('marca',),
        'codigo barras': ('codigo de barras', 'codigo_barras', 'código de barras', 'codigo barras', 'ean'),
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
    INDICE_INICIO_TIENDAS = 13  # Columna N
    INDICES_BODEGAS = [10, 11, 12]  # Columnas K, L, M
    INDICES_PRODUCTO = list(range(10))  # Columnas A-J (0-9)
    
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
    
    def validar_cantidad(self, cantidad_raw: Any, row_num: int, errores_fila: List[Dict]) -> Optional[int]:
        """Valida y normaliza cantidad."""
        if cantidad_raw is not None and not pd.isna(cantidad_raw):
            try:
                cantidad_str = str(cantidad_raw).strip().replace(",", ".")
                cantidad_float = float(cantidad_str)
                cantidad = int(cantidad_float)
                
                if cantidad_float != cantidad:
                    errores_fila.append({
                        "fila": row_num,
                        "campo": "Cantidad",
                        "tipo": "ERROR",
                        "mensaje": f"Cantidad debe ser un número entero. Valor recibido: {cantidad_raw}"
                    })
                    return None
                elif cantidad <= 0:
                    errores_fila.append({
                        "fila": row_num,
                        "campo": "Cantidad",
                        "tipo": "ERROR",
                        "mensaje": f"Cantidad debe ser mayor a 0. Valor recibido: {cantidad_raw}"
                    })
                    return None
                return cantidad
            except (ValueError, TypeError):
                errores_fila.append({
                    "fila": row_num,
                    "campo": "Cantidad",
                    "tipo": "ERROR",
                    "mensaje": f"Cantidad no es un entero válido. Valor recibido: {cantidad_raw}"
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
                idx_col_lower = str(idx_col).lower().strip()
                if all(keyword in idx_col_lower for keyword in keywords):
                    return idx_col
        
        return None
    
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
            
            if found_column:
                valor = row[found_column]
                if isinstance(valor, pd.Series):
                    if len(valor) == 0 or valor.isna().all():
                        return None
                    valor = valor.iloc[0] if len(valor) > 0 else None
                if valor is None or (isinstance(valor, (float, int)) and pd.isna(valor)):
                    return None
                
                is_codigo_barras = any(name.lower() in ['codigo de barras', 'codigo_barras', 'código de barras', 'codigo barras'] 
                                      for name in names_to_try)
                
                if is_codigo_barras and isinstance(valor, (int, float)):
                    try:
                        if isinstance(valor, int):
                            result = str(valor)
                        elif isinstance(valor, float):
                            if valor.is_integer():
                                result = str(int(valor))
                            else:
                                result = str(valor).rstrip('0').rstrip('.')
                        else:
                            result = str(valor).strip()
                    except (ValueError, TypeError, OverflowError):
                        result = str(valor).strip()
                else:
                    result = str(valor).strip()
                    
                    if is_codigo_barras and result.endswith('.0'):
                        try:
                            num_val = float(result)
                            if num_val.is_integer():
                                result = str(int(num_val))
                        except (ValueError, TypeError):
                            pass
                
                return result if result else None
            
            return None
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
            
            if found_column:
                valor = row[found_column]
                if isinstance(valor, pd.Series):
                    if len(valor) == 0 or valor.isna().all():
                        return None
                    valor = valor.iloc[0] if len(valor) > 0 else None
                if valor is None or (isinstance(valor, (float, int)) and pd.isna(valor)):
                    return None
                
                if isinstance(valor, (int, float)):
                    return float(valor)
                
                str_value = str(valor).strip()
                if not str_value:
                    return None
                
                es_porcentaje = '%' in str_value
                
                str_value = str_value.replace('$', '').replace('€', '').replace('USD', '').replace('%', '').strip()
                str_value = ''.join(c for c in str_value if c.isdigit() or c in '.,-')
                
                if ',' in str_value and '.' in str_value:
                    str_value = str_value.replace('.', '').replace(',', '.')
                elif ',' in str_value:
                    str_value = str_value.replace(',', '.')
                
                if not str_value:
                    return None
                
                valor_numerico = float(str_value)
                return valor_numerico
                
            return None
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
