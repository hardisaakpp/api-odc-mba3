"""
Mapper para convertir datos de distribución confirmada a formato JSON de Stock Transfer Order de SAP Service Layer.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SAPStockTransferMapper:
    """Mapper para convertir distribución por tienda a formato JSON de Stock Transfer Order de SAP."""
    
    @staticmethod
    def to_sap_stock_transfer(
        pedido_data: Dict[str, Any],
        distribucion_por_tienda: Dict[str, List[Dict[str, Any]]],
        bodega_origen: str,
        oc_doc_num: Optional[int] = None,
        usuario_id: Optional[str] = None,
        pedido_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Convierte la distribución por tienda en múltiples Stock Transfer Orders (una por tienda).
        
        Args:
            pedido_data: Datos del pedido (cabecera)
            distribucion_por_tienda: Diccionario agrupado por tienda_id:
                {
                    "tienda_id_1": [
                        {
                            "pedido_detalle_id": "...",
                            "codigo_producto": "...",
                            "item_code_sap": "...",
                            "cantidad_asignada": 10,
                            "cantidad_sap": 120.0,  # Ya convertida a unidades SAP
                            ...
                        }
                    ],
                    "tienda_id_2": [...]
                }
            bodega_origen: Código de bodega origen (ej: "01", "RL-CD")
            oc_doc_num: Número de OC de SAP (DocNum) relacionada
            usuario_id: ID del usuario que genera la transferencia
            pedido_id: ID del pedido relacionado
        
        Returns:
            Lista de diccionarios con estructura JSON para SAP Service Layer (uno por tienda)
            
        Ejemplo de salida:
        [
            {
                "DocDate": "2025-01-21",
                "FromWarehouse": "01",
                "ToWarehouse": "02",
                "Comments": "Transferencia desde OC 12345 - Pedido P-12.48",
                "StockTransferLines": [
                    {
                        "LineNum": 0,
                        "ItemCode": "5-0012.9",
                        "Quantity": 120.0
                    }
                ]
            }
        ]
        """
        # Formatear fecha
        fecha = pedido_data.get("fecha_pedido") or pedido_data.get("creado_en")
        if isinstance(fecha, str):
            try:
                if 'T' in fecha or ' ' in fecha:
                    fecha_obj = datetime.fromisoformat(fecha.replace('Z', '+00:00'))
                    fecha = fecha_obj.strftime("%Y-%m-%d")
            except:
                pass
        elif fecha is not None and hasattr(fecha, 'strftime'):
            fecha = fecha.strftime("%Y-%m-%d")
        elif fecha is None:
            fecha = datetime.now().strftime("%Y-%m-%d")
        
        numero_pedido = pedido_data.get("numero_pedido", "N/A")
        comentario_base = f"Transferencia desde OC {oc_doc_num}" if oc_doc_num else "Transferencia desde pedido"
        comentario_base += f" - Pedido {numero_pedido}"
        
        stock_transfers = []
        
        # Crear un Stock Transfer Order por cada tienda
        for tienda_id, productos in distribucion_por_tienda.items():
            if not productos:
                logger.warning(f"⚠️ Tienda {tienda_id} sin productos, omitiendo")
                continue
            
            # Obtener código de bodega destino desde la primera línea (debería estar en todos los productos de la tienda)
            primera_linea = productos[0]
            bodega_destino = primera_linea.get("warehouse_code") or primera_linea.get("tienda_codigo")
            
            if not bodega_destino:
                logger.warning(f"⚠️ Tienda {tienda_id} sin código de bodega, omitiendo")
                continue
            
            logger.debug(f"📦 Creando Stock Transfer: {bodega_origen} → {bodega_destino} ({len(productos)} productos)")
            
            # Construir líneas del documento
            stock_transfer_lines = []
            for idx, producto in enumerate(productos):
                item_code = producto.get("item_code_sap") or producto.get("codigo_producto")
                cantidad = producto.get("cantidad_sap") or producto.get("cantidad_asignada", 0)
                
                if not item_code or cantidad <= 0:
                    logger.warning(
                        f"⚠️ Línea {idx+1} omitida: ItemCode={item_code}, "
                        f"Quantity={cantidad}"
                    )
                    continue
                
                line = {
                    "LineNum": idx,
                    "ItemCode": item_code,
                    "Quantity": float(cantidad)
                }
                
                stock_transfer_lines.append(line)
            
            if not stock_transfer_lines:
                logger.warning(f"⚠️ Tienda {tienda_id} sin líneas válidas, omitiendo")
                continue
            
            # Construir JSON completo del Stock Transfer Order
            stock_transfer = {
                "DocDate": fecha,
                "FromWarehouse": bodega_origen,
                "ToWarehouse": bodega_destino,
                "Comments": comentario_base,
                "StockTransferLines": stock_transfer_lines
            }
            
            stock_transfers.append(stock_transfer)
        
        if not stock_transfers:
            raise ValueError("No hay stock transfers válidos para crear")
        
        logger.info(f"✅ Generados {len(stock_transfers)} Stock Transfer Order(s) para {len(distribucion_por_tienda)} tienda(s)")
        return stock_transfers
