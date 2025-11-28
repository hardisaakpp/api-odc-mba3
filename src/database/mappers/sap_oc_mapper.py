"""
Mapper para convertir datos de orden_compra_cabecera/detalle a formato JSON de SAP Service Layer.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SAPOCMapper:
    """Mapper para convertir ODC de tablas a formato JSON de SAP Service Layer."""
    
    @staticmethod
    def to_sap_purchase_order(
        oc_cabecera: Dict[str, Any],
        oc_detalles: List[Dict[str, Any]],
        warehouse_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Convierte una orden de compra de las tablas a formato JSON de SAP Service Layer.
        
        Args:
            oc_cabecera: Datos de orden_compra_cabecera
            oc_detalles: Lista de datos de orden_compra_detalle
            warehouse_code: Código de bodega (opcional, si no se proporciona se omite)
            
        Returns:
            Diccionario con estructura JSON para SAP Service Layer
            
        Ejemplo de salida:
        {
            "CardCode": "PROVEEDOR001",
            "DocDate": "2025-01-21",
            "DocDueDate": "2025-01-21",
            "TaxDate": "2025-01-21",
            "Comments": "Ref: 900125351",
            "DocumentLines": [
                {
                    "ItemCode": "5-0012.9",
                    "Quantity": 1824.0,
                    "UnitPrice": 1.1625,
                    "LineTotal": 2120.4,
                    "WarehouseCode": "01"
                }
            ]
        }
        """
        # Formatear fecha
        fecha = oc_cabecera.get("fecha_generacion")
        if isinstance(fecha, str):
            # Intentar parsear si viene en formato datetime string
            try:
                if 'T' in fecha or ' ' in fecha:
                    fecha_obj = datetime.fromisoformat(fecha.replace('Z', '+00:00'))
                    fecha = fecha_obj.strftime("%Y-%m-%d")
            except:
                # Si ya está en formato YYYY-MM-DD, usarlo directamente
                pass
        elif fecha is not None and hasattr(fecha, 'strftime'):
            fecha = fecha.strftime("%Y-%m-%d")
        elif fecha is None:
            fecha = datetime.now().strftime("%Y-%m-%d")
        
        # Construir líneas del documento
        document_lines = []
        for idx, detalle in enumerate(oc_detalles, start=1):
            line = {
                "LineNum": idx - 1,  # SAP usa índice base 0
                "ItemCode": detalle.get("sku_sap"),
                "Quantity": float(detalle.get("cantidad_sap", 0)),
                "UnitPrice": float(detalle.get("precio_unitario", 0)),
                "LineTotal": float(detalle.get("total_linea", 0)),
                "DiscountPercent": 0.0
            }
            
            # Agregar código de bodega si está disponible
            if warehouse_code:
                line["WarehouseCode"] = warehouse_code
            
            # Validar que los campos requeridos estén presentes
            if not line.get("ItemCode") or line.get("Quantity", 0) <= 0:
                logger.warning(
                    f"⚠️ Línea {idx} omitida: ItemCode={line.get('ItemCode')}, "
                    f"Quantity={line.get('Quantity')}"
                )
                continue
            
            document_lines.append(line)
        
        if not document_lines:
            raise ValueError("No hay líneas válidas para la orden de compra")
        
        # Obtener CardCode y agregar prefijo 'P' si no lo tiene (convención SAP: proveedores tienen prefijo 'P')
        proveedor = oc_cabecera.get("proveedor")
        if proveedor:
            proveedor = str(proveedor).strip()
            if not proveedor.startswith('P'):
                proveedor_original = proveedor
                proveedor = f"P{proveedor}"
                logger.info(f"🔄 CardCode convertido con prefijo 'P': {proveedor_original} → {proveedor}")
        
        # Construir JSON completo
        purchase_order = {
            "CardCode": proveedor,
            "DocDate": fecha,
            "DocDueDate": fecha,  # Por defecto igual a DocDate, se puede calcular según lógica
            "TaxDate": fecha,
            "Comments": f"Ref: {oc_cabecera.get('referencia_despacho', 'N/A')}",
            "U_ORIGEN": "C",  # Campo hardcodeado para identificar el sistema origen
            "DocumentLines": document_lines
        }
        
        # Validar campos requeridos
        if not purchase_order.get("CardCode"):
            raise ValueError("CardCode (proveedor) es requerido")
        
        logger.debug(f"✅ Purchase Order JSON construido: {len(document_lines)} líneas, CardCode: {proveedor}")
        return purchase_order

