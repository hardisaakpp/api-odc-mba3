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
    def to_despacho_detalle(
        linea: Dict[str, Any], 
        tipo_linea: str,
        sap_info: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Transforma una línea de factura MBA3 a formato de despacho_detalle.
        
        Si se proporciona información SAP, calcula las conversiones automáticamente SOLO para productos
        de los grupos "R-MEDIAS" y "RD-INDUM MEDIAS":
        - cantidad_pack_sap = cantidad_docena_mba3 (docenas) × unidad_conversion
        - precio_unitario_sap = precio_unitario_mba3 / unidad_conversion
        - subtotal_sap = cantidad_pack_sap × precio_unitario_sap
        
        Para productos de otros grupos, se mantienen las unidades originales (no se convierte).
        
        Mapeo de campos a columnas de la tabla:
        - cantidad → cantidad_docena_mba3 (docenas de El Rayo)
        - cantidad_sap → cantidad_pack_sap (packs convertidos para Mabel)
        - precio_unitario → precio_unitario_mba3 (precio por docena)
        - total_linea → total_linea_mba3 (total de la línea)
        - total_producto → subtotal_sap (subtotal para SAP, calculado)
        
        Args:
            linea: Diccionario con datos de línea de factura
            tipo_linea: Tipo de línea (GrabarLineasProd, CtrlEliminados1, etc.)
            sap_info: Información SAP del producto (opcional):
                {
                    "pack_sap": "X3",
                    "unidad_conversion": 4.0,
                    "pack_id": "X3",
                    "grupo_articulos": "R-MEDIAS"
                }
            
        Returns:
            Diccionario con datos para insertar en despacho_detalle, o None si no es válida
        """
        codigo = linea.get("Codigo")
        
        # Solo procesar si hay un código de producto válido
        if not codigo or not codigo.strip():
            return None
        
        total_linea = linea.get("TotalLinea") or 0
        cantidad = linea.get("Cantidad") or 0
        # precio_unitario_mba3: precio unitario de El Rayo (por docena)
        precio_unitario_mba3 = linea.get("PrecioUnitario") or 0
        
        # Calcular conversiones SAP si hay información disponible
        # IMPORTANTE: Solo se aplica conversión para grupos R-MEDIAS y RD-INDUM MEDIAS
        cantidad_sap = None
        precio_unitario_sap = None
        subtotal_sap = None
        unidad_sap = None
        
        # Grupos permitidos para conversión de unidades
        grupos_permitidos = ["R-MEDIAS", "RD-INDUM MEDIAS"]
        
        if sap_info and cantidad > 0:
            grupo_articulos = sap_info.get("grupo_articulos")
            unidad_conversion = sap_info.get("unidad_conversion")
            pack_sap = sap_info.get("pack_sap")
            
            # Verificar si el producto pertenece a un grupo permitido para conversión
            debe_convertir = grupo_articulos in grupos_permitidos
            
            if debe_convertir and unidad_conversion is not None and unidad_conversion > 0:
                # Calcular cantidad en packs: docenas × unidad_conversion = packs
                cantidad_sap = cantidad * unidad_conversion
                
                # Calcular precio unitario Mabel Trading: precio_unitario_mba3 / unidad_conversion
                if precio_unitario_mba3 > 0 and unidad_conversion > 0:
                    precio_unitario_sap = precio_unitario_mba3 / unidad_conversion
                    
                    # Calcular subtotal Mabel Trading: cantidad_pack × precio_unitario_sap
                    if cantidad_sap > 0:
                        subtotal_sap = cantidad_sap * precio_unitario_sap
                
                unidad_sap = pack_sap
                
                # Log de conversión para debugging
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(
                    f"   🔄 Conversión aplicada para {codigo} (Grupo: {grupo_articulos}): "
                    f"{cantidad} docenas × {unidad_conversion} = {cantidad_sap:.2f} packs, "
                    f"Precio unitario Mabel: {precio_unitario_mba3:.2f} / {unidad_conversion} = {precio_unitario_sap:.4f}, "
                    f"Subtotal: {cantidad_sap:.2f} × {precio_unitario_sap:.4f} = {subtotal_sap:.2f}"
                )
            elif grupo_articulos:
                # Producto de otro grupo - no se convierte
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(
                    f"   ⏭️ Sin conversión para {codigo} (Grupo: {grupo_articulos}): "
                    f"Mantiene unidades originales (docenas)"
                )
        
        return {
            # Campos que vienen de MBA3
            "sku": codigo,
            "cantidad": cantidad,  # Docenas de El Rayo -> cantidad_docena_mba3
            "precio_unitario": precio_unitario_mba3,  # precio_unitario_mba3 - Precio por docena (El Rayo)
            "total_linea": total_linea,  # total_linea_mba3
            "descuento": linea.get("Descuento") or 0,
            "tipo_linea": tipo_linea,
            "nombre_producto": linea.get("Nombre") or None,
            "impuesto": linea.get("Impuesto"),
            
            # Campos calculados o derivados
            # subtotal_sap solo debe tener valor si hay conversión SAP válida
            # (es decir, si cantidad_sap y precio_unitario_sap están disponibles)
            "total_producto": subtotal_sap,  # subtotal_sap - NULL si no hay conversión SAP
            
            # Campos de conversión SAP
            "cantidad_sap": cantidad_sap,  # cantidad_pack_sap - Packs convertidos para Mabel
            "unidad_sap": unidad_sap,  # unidad_sap - Pack usado (X1, X2, X3, etc.)
            "precio_unitario_sap": precio_unitario_sap,  # precio_unitario_sap - Precio por pack (Mabel Trading)
        }


