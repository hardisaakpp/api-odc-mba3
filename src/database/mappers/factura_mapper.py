"""
Mapper para transformar datos de facturas MBA3 a formato SQL Server.
"""

from typing import Optional, Dict, Any


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
    def to_despacho_cabecera(factura: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transforma una factura de MBA3 a formato de despacho_cabecera.
        
        Args:
            factura: Diccionario con datos de factura de MBA3
            
        Returns:
            Diccionario con datos para insertar en despacho_cabecera
        """
        fecha_factura = FacturaMapper.parse_date(factura.get("FECHA_FACTURA"))
        
        return {
            "empresa": factura.get("EMPRESA"),
            "codigo_cliente": factura.get("CODIGO_CLIENTE"),
            "fecha_despacho": fecha_factura,  # Usar fecha_factura como fecha_despacho
            "codigo_factura": factura.get("CODIGO_FACTURA"),
            "anulada": 1 if factura.get("ANULADA") else 0,
            "numero_pedido_sistema": factura.get("NUMERO_PEDIDO_SISTEMA"),
            "numero_orden": factura.get("NUMERO_ORDEN"),
            "numero_factura": factura.get("NUMERO_FACTURA"),
            "tipo_documento": factura.get("TIPO_DOCUMENTO"),
            "orden_compra": factura.get("ORDEN_COMPRA") or None,
            "orden_compra_cliente": factura.get("ORDEN_COMPRA_CLIENTE") or None,
            "remision_facturada": 1 if factura.get("Remision_Facturada") else 0,
            "num_id_factura_relacionada": factura.get("NumIDFacturaRelacionada"),
            "codigo_despacho": factura.get("CODIGO_DESPACHO"),
            "fecha_factura": fecha_factura,
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
        
        return {
            "sku": codigo,
            "cantidad": linea.get("Cantidad") or 0,
            "precio_unitario": linea.get("PrecioUnitario") or 0,
            "total_linea": linea.get("TotalLinea") or 0,
            "descuento": linea.get("Descuento") or 0,
            "tipo_linea": tipo_linea,
            "nombre_producto": linea.get("Nombre") or None,
            "impuesto": linea.get("Impuesto"),
            "reg_num": linea.get("RegNum"),
        }

