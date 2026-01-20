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
        
        ⭐ IMPORTANTE: Este método recibe solo distribuciones de TIENDAS (es_bodega=False).
        Las bodegas ya fueron excluidas en el servicio que llama a este método.
        Las Solicitudes de Transferencia se crean desde bodega origen hacia tiendas.
        
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
                            "warehouse_code": "TRL-QSN",  # Código de tienda (destino)
                            "tienda_codigo": "TRL-QSN",
                            "es_bodega": False,
                            ...
                        }
                    ],
                    "tienda_id_2": [...]
                }
            bodega_origen: Código de bodega origen (ej: "OUT-CD", "RL-CD", "RG-CD")
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
        bodega_origen_upper = bodega_origen.strip().upper()
        
        # Crear un Stock Transfer Order por cada tienda
        for tienda_id, productos in distribucion_por_tienda.items():
            if not productos:
                logger.warning(f"⚠️ Tienda {tienda_id} sin productos, omitiendo")
                continue
            
            # Obtener código de tienda destino desde la primera línea (debería estar en todos los productos de la tienda)
            primera_linea = productos[0]
            # ⭐ IMPORTANTE: Usar warehouse_code que ya contiene el código exacto de SAP (WhsCode)
            tienda_destino = primera_linea.get("warehouse_code") or primera_linea.get("tienda_codigo")
            
            if not tienda_destino:
                logger.warning(f"⚠️ Tienda {tienda_id} sin código de tienda, omitiendo")
                continue
            
            # ⭐ Usar código exacto de SAP sin normalizar (ya viene normalizado desde el servicio)
            tienda_destino = tienda_destino.strip()
            
            # ⭐ LOGGING: Registrar el código exacto que se enviará a SAP
            logger.debug(
                f"📤 Preparando Stock Transfer: FromWarehouse='{bodega_origen_upper}', "
                f"ToWarehouse='{tienda_destino}' (código exacto de SAP)"
            )
            
            # ⚠️ VALIDACIÓN: No crear transferencia si origen == destino
            if bodega_origen_upper == tienda_destino:
                logger.warning(
                    f"⚠️ Omitiendo Stock Transfer: origen y destino son iguales ({bodega_origen}). "
                    f"No tiene sentido crear una transferencia de {bodega_origen} a {tienda_destino}"
                )
                continue
            
            logger.info(f"📦 Creando Stock Transfer: {bodega_origen} → {tienda_destino} ({len(productos)} productos)")
            
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
                "FromWarehouse": bodega_origen_upper,
                "ToWarehouse": tienda_destino,
                "Comments": comentario_base,
                "StockTransferLines": stock_transfer_lines
            }
            
            stock_transfers.append(stock_transfer)
        
        if not stock_transfers:
            raise ValueError("No hay stock transfers válidos para crear")
        
        logger.info(f"✅ Generados {len(stock_transfers)} Stock Transfer Order(s) para {len(distribucion_por_tienda)} tienda(s)")
        return stock_transfers
