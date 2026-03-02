"""
Mapper para convertir datos de orden_compra_cabecera/detalle a formato JSON de SAP Service Layer.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)


class SAPOCMapper:
    """Mapper para convertir ODC de tablas a formato JSON de SAP Service Layer."""
    
    @staticmethod
    def to_sap_purchase_order(
        oc_cabecera: Dict[str, Any],
        oc_detalles: List[Dict[str, Any]],
        warehouse_code: Optional[str] = None,
        usuario_id: Optional[str] = None,
        pedido_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Convierte una orden de compra a formato JSON para POST /PurchaseOrders (Postman-validado).
        
        Regla: WarehouseCode por línea SOLO desde detalle.codigo_bodega. NO usar bodega de cabecera.
        Si un detalle no tiene codigo_bodega → ValueError (error funcional).
        
        Args:
            oc_cabecera: Datos de orden_compra_cabecera
            oc_detalles: Lista de orden_compra_detalle (cada uno debe tener codigo_bodega)
            warehouse_code: No se usa para WarehouseCode; se mantiene por compatibilidad de firma
            usuario_id: Para U_USUARIO
            pedido_id: Para U_LOTE
            
        Returns:
            JSON para SAP (CardCode, DocDate, DocDueDate, TaxDate, Comments, DocumentLines con WarehouseCode).
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
            fecha = ahora_naive().strftime("%Y-%m-%d")
        
        # Construir DocumentLines. WarehouseCode SOLO desde detalle.codigo_bodega (contrato Postman).
        document_lines = []
        for idx, detalle in enumerate(oc_detalles, start=1):
            sku = detalle.get("sku_sap")
            qty = float(detalle.get("cantidad_sap", 0))
            if not sku or qty <= 0:
                logger.warning(f"⚠️ Línea {idx} omitida: ItemCode={sku}, Quantity={qty}")
                continue

            bodega = detalle.get("codigo_bodega") or detalle.get("warehouse_code")
            if not bodega or not str(bodega).strip():
                raise ValueError(
                    f"Línea {idx} (SKU={sku}) sin codigo_bodega. "
                    "Cada detalle debe tener codigo_bodega; no se usa bodega de cabecera."
                )
            bodega = str(bodega).strip()

            line = {
                "LineNum": idx - 1,
                "ItemCode": sku,
                "Quantity": qty,
                "UnitPrice": float(detalle.get("precio_unitario", 0)),
                "LineTotal": float(detalle.get("total_linea", 0)),
                "DiscountPercent": 0.0,
                "WarehouseCode": bodega,
            }
            document_lines.append(line)
            logger.debug(f"   Línea {idx}: ItemCode={sku}, WarehouseCode={bodega}")

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
        
        # Obtener información para UDFs
        # Usuario: de parámetro, de cabecera, o fallback
        usuario_final = usuario_id or oc_cabecera.get("creado_por") or "SYSTEM"
        
        # Pedido ID: de parámetro, de cabecera, o vacío
        pedido_final = pedido_id or oc_cabecera.get("pedido_id") or ""
        
        # Fecha actual para U_FECHA
        fecha_actual = ahora_naive().strftime("%Y-%m-%d")
        
        # Construir JSON completo con UDFs de trazabilidad
        # ⚠️ NOTA: Purchase Orders usa DocDueDate (no DueDate), que es correcto para este endpoint
        # PriceList: 2 = "Último precio determinado" (según configuración SAP)
        purchase_order = {
            "CardCode": proveedor,
            "DocDate": fecha,
            "DocDueDate": fecha,  # ⚠️ Correcto para Purchase Orders (POST /PurchaseOrders)
            "TaxDate": fecha,
            "Comments": f"Ref: {oc_cabecera.get('referencia_despacho', 'N/A')}",
            "PriceList": -2,
            
            # UDFs de trazabilidad
            "U_ORIGEN": "C",  # Sistema origen (C = consultas)
            "U_USUARIO": usuario_final,  # Usuario que genera la OC
            "U_FECHA": fecha_actual,  # Fecha de generación
            "U_LOTE": pedido_final,  # Lote/pedido relacionado (puede estar vacío si viene de despacho)
            
            "DocumentLines": document_lines
        }
        
        # Validar campos requeridos
        if not purchase_order.get("CardCode"):
            raise ValueError("CardCode (proveedor) es requerido")
        
        logger.debug(
            f"✅ Purchase Order JSON construido: {len(document_lines)} líneas, "
            f"CardCode: {proveedor}, "
            f"UDFs: U_ORIGEN={purchase_order['U_ORIGEN']}, "
            f"U_USUARIO={purchase_order['U_USUARIO']}, "
            f"U_FECHA={purchase_order['U_FECHA']}, "
            f"U_LOTE={purchase_order['U_LOTE'] or '(vacío)'}"
        )
        return purchase_order

