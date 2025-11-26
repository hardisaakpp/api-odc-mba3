"""
Mapper para transformar datos de despacho a orden de compra.
"""

from typing import Optional, Dict, Any, List


class OrdenCompraMapper:
    """Mapper para transformar despacho_cabecera/detalle a orden_compra_cabecera/detalle."""
    
    @staticmethod
    def to_orden_compra_cabecera(
        despacho_cabecera: Dict[str, Any],
        proveedor: str
    ) -> Dict[str, Any]:
        """
        Transforma una cabecera de despacho a formato de orden_compra_cabecera.
        
        Mapeo:
        - despacho_id → despacho_id (asociación 1:1)
        - empresa → proveedor (mapeado desde tabla cliente si es necesario)
        - fecha_despacho o fecha_factura → fecha_generacion
        - numero_factura → referencia_despacho
        - codigo_bodega → codigo_bodega (opcional)
        
        Args:
            despacho_cabecera: Diccionario con datos de despacho_cabecera
            proveedor: CardCode SAP (proveedor) obtenido desde tabla cliente
            
        Returns:
            Diccionario con datos para insertar en orden_compra_cabecera
        """
        # Usar fecha_factura si existe, sino fecha_despacho
        fecha_generacion = despacho_cabecera.get("fecha_factura") or despacho_cabecera.get("fecha_despacho")
        
        return {
            "despacho_id": despacho_cabecera.get("despacho_id"),
            "proveedor": proveedor,
            "fecha_generacion": fecha_generacion,
            "referencia_despacho": despacho_cabecera.get("numero_factura"),
            # Nota: codigo_bodega no existe en la tabla real, se omite
        }
    
    @staticmethod
    def to_orden_compra_detalle(
        despacho_detalle: Dict[str, Any],
        oc_id: str
    ) -> Dict[str, Any]:
        """
        Transforma un detalle de despacho a formato de orden_compra_detalle.
        
        Mapeo:
        - detalle_id → referencia_detalle
        - despacho_id → oc_id (FK indirecta a través de cabecera)
        - sku → sku_sap (ItemCode de SAP)
        - cantidad_pack_sap → cantidad_sap
        - unidad_sap → unidad_sap
        - precio_unitario_sap → precio_unitario
        - total_linea_mba3 o subtotal_sap → total_linea
        - cantidad_docena_mba3 → cantidad_origen
        - descuento → descuento
        
        Args:
            despacho_detalle: Diccionario con datos de despacho_detalle
            oc_id: UUID de la cabecera de orden de compra
            
        Returns:
            Diccionario con datos para insertar en orden_compra_detalle
        """
        # Usar total_linea_mba3 si existe, sino subtotal_sap
        total_linea = despacho_detalle.get("total_linea_mba3") or despacho_detalle.get("subtotal_sap")
        
        # Usar precio_unitario_sap si existe, sino calcular desde total_linea y cantidad_sap
        precio_unitario = despacho_detalle.get("precio_unitario_sap")
        if precio_unitario is None:
            cantidad_sap = despacho_detalle.get("cantidad_pack_sap")
            if cantidad_sap and cantidad_sap > 0 and total_linea:
                precio_unitario = total_linea / cantidad_sap
        
        return {
            "sku_sap": despacho_detalle.get("sku"),  # sku en despacho_detalle es el ItemCode SAP
            "cantidad_sap": despacho_detalle.get("cantidad_pack_sap"),
            "unidad_sap": despacho_detalle.get("unidad_sap"),
            "referencia_detalle": despacho_detalle.get("detalle_id"),
            "precio_unitario": precio_unitario,
            "total_linea": total_linea,
            "cantidad_origen": despacho_detalle.get("cantidad_docena_mba3"),
            # Nota: descuento no existe en la tabla real, se omite
            # Nota: sku_mbas no se mapea desde despacho_detalle (campo opcional en ODC)
        }

