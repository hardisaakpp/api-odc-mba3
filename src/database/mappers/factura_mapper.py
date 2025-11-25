"""
Mapper para transformar datos de facturas MBA3 a formato SQL Server.
"""

from typing import Optional, Dict, Any
from datetime import datetime


class FacturaMapper:
    """Mapper para transformar facturas de MBA3 a SQL Server."""
    
    @staticmethod
    def parse_date(date_str: Optional[str]) -> Optional[str]:
        """
        Parsea una fecha en formato string a formato compatible con SQL Server.
        
        Args:
            date_str: String con fecha (formato: "YYYY-MM-DD" o similar)
            
        Returns:
            String con fecha en formato SQL Server, o None si no se puede parsear
        """
        if not date_str:
            return None
        
        try:
            if isinstance(date_str, str):
                # Formato esperado: "2025-11-20"
                if len(date_str) >= 10:
                    return date_str[:10]  # YYYY-MM-DD
        except Exception:
            pass
        
        return None
    
    @staticmethod
    def extract_empresa_from_codigo(codigo_factura: Optional[str]) -> Optional[str]:
        """
        Intenta extraer la empresa del código de factura.
        
        Formatos conocidos:
        - "FE-{numero}-{EMPRESA}" -> extrae EMPRESA
        - "REMSI-{numero}-{EMPRESA}" -> extrae EMPRESA
        
        Args:
            codigo_factura: Código de factura
            
        Returns:
            Nombre de la empresa si se puede extraer, None en caso contrario
        """
        if not codigo_factura:
            return None
        
        # Intentar extraer empresa del formato "*-*-EMPRESA"
        parts = codigo_factura.split("-")
        if len(parts) >= 3:
            # El último segmento después del último guión suele ser la empresa
            return parts[-1].strip()
        
        return None
    
    @staticmethod
    def to_despacho_cabecera(factura: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transforma una factura de MBA3 a formato de despacho_cabecera.
        
        Si el campo EMPRESA no está disponible, intenta extraerlo del código de factura.
        
        Args:
            factura: Diccionario con datos de factura de MBA3
            
        Returns:
            Diccionario con datos para insertar en despacho_cabecera
        """
        fecha_factura = FacturaMapper.parse_date(factura.get("FECHA_FACTURA"))
        
        # fecha_despacho es requerido (NOT NULL), usar fecha_factura o fecha actual como fallback
        fecha_despacho = fecha_factura
        if not fecha_despacho:
            # Si no hay fecha de factura, usar la fecha actual como valor por defecto
            fecha_despacho = datetime.now().strftime("%Y-%m-%d")
        
        # Obtener empresa: primero del campo EMPRESA, luego del código de factura
        empresa = factura.get("EMPRESA")
        if not empresa:
            codigo_factura = factura.get("CODIGO_FACTURA")
            empresa = FacturaMapper.extract_empresa_from_codigo(codigo_factura)
        
        # Si aún no hay empresa, usar valor por defecto
        if not empresa:
            empresa = "SIN_EMPRESA"  # Valor por defecto para campos requeridos
        
        # Obtener codigo_cliente con valor por defecto si no está disponible
        codigo_cliente = factura.get("CODIGO_CLIENTE")
        if not codigo_cliente:
            codigo_cliente = "SIN_CLIENTE"  # Valor por defecto para campos requeridos
        
        # Obtener tipo_documento con valor por defecto si no está disponible
        tipo_documento = factura.get("TIPO_DOCUMENTO")
        if not tipo_documento:
            tipo_documento = "SIN_TIPO"  # Valor por defecto para campos requeridos
        
        # Obtener numero_factura con valor por defecto si no está disponible
        numero_factura = factura.get("NUMERO_FACTURA")
        if numero_factura is None:
            # Intentar extraer del código de factura si es posible
            codigo_factura = factura.get("CODIGO_FACTURA", "")
            if codigo_factura:
                # Intentar extraer número del formato "FE-{numero}-{empresa}"
                parts = codigo_factura.split("-")
                if len(parts) >= 2:
                    try:
                        numero_factura = int(parts[1])
                    except (ValueError, IndexError):
                        numero_factura = 0  # Valor por defecto
                else:
                    numero_factura = 0
            else:
                numero_factura = 0  # Valor por defecto
        
        return {
            # Campos que vienen de MBA3
            "empresa": empresa,
            "codigo_cliente": codigo_cliente,
            "fecha_despacho": fecha_despacho,  # Usar fecha_factura o fecha actual si no está disponible
            "codigo_factura": factura.get("CODIGO_FACTURA"),
            "anulada": 1 if factura.get("ANULADA") else 0,
            "numero_pedido_sistema": factura.get("NUMERO_PEDIDO_SISTEMA"),
            "numero_orden": factura.get("NUMERO_ORDEN"),
            "numero_factura": numero_factura,
            "tipo_documento": tipo_documento,
            "orden_compra": factura.get("ORDEN_COMPRA") or None,
            "orden_compra_cliente": factura.get("ORDEN_COMPRA_CLIENTE") or None,
            "remision_facturada": 1 if factura.get("Remision_Facturada") else 0,
            "num_id_factura_relacionada": factura.get("NumIDFacturaRelacionada"),
            "codigo_despacho": factura.get("CODIGO_DESPACHO"),
            "codigo_bodega": factura.get("CODIGO_BODEGA"),
            "fecha_factura": fecha_factura,
            "confirmado": 1 if factura.get("CONFIRMADO") else 0,  # Mapea CONFIRMADO de MBA3
        }
    
    @staticmethod
    def to_despacho_detalle(linea: Dict[str, Any], tipo_linea: str) -> Optional[Dict[str, Any]]:
        """
        Transforma una línea de factura MBA3 a formato de despacho_detalle.
        
        Args:
            linea: Diccionario con datos de línea de factura
            tipo_linea: Tipo de línea (GrabarLineasProd, CtrlEliminados1, etc.)
            
        Returns:
            Diccionario con datos para insertar en despacho_detalle, o None si no es válida
        """
        codigo = linea.get("Codigo")
        
        # Solo procesar si hay un código de producto válido
        if not codigo or not codigo.strip():
            return None
        
        total_linea = linea.get("TotalLinea") or 0
        
        return {
            # Campos que vienen de MBA3
            "sku": codigo,
            "cantidad": linea.get("Cantidad") or 0,
            "precio_unitario": linea.get("PrecioUnitario") or 0,
            "total_linea": total_linea,
            "descuento": linea.get("Descuento") or 0,
            "tipo_linea": tipo_linea,
            "nombre_producto": linea.get("Nombre") or None,
            "impuesto": linea.get("Impuesto"),
            "reg_num": linea.get("RegNum"),
            
            # Campos calculados o derivados
            "producto_id": codigo,  # Por defecto igual a SKU (puede cambiarse después)
            "total_producto": total_linea,  # Por defecto igual a total_linea
            
            # Campos que NO vienen de MBA3 (se dejan como NULL)
            # Estos campos se pueden poblar después mediante transformaciones o mapeos
            "unid_detalle": None,  # Unidad de medida (no viene de MBA3)
            "cantidad_sap": None,  # Transformación para SAP
            "unidad_sap": None,  # Transformación para SAP
            "sku_sap": None,  # Transformación para SAP
        }


