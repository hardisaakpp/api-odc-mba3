"""
Mapper para convertir datos de distribución confirmada a formato JSON de Inventory Transfer Request de SAP Service Layer.

⚠️ IMPORTANTE: Este mapper genera Inventory Transfer Requests (Solicitudes de Traslado),
NO Stock Transfer Orders (Traslados). Las Inventory Transfer Requests NO mueven stock,
solo crean una solicitud que debe ser procesada posteriormente.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)


class SAPStockTransferMapper:
    """
    Mapper para convertir distribución por tienda a formato JSON de Inventory Transfer Request de SAP.
    
    ⚠️ IMPORTANTE: Genera Inventory Transfer Requests (POST /InventoryTransferRequests),
    NO Stock Transfer Orders. Las Inventory Transfer Requests son solicitudes que NO mueven stock.
    """
    
    @staticmethod
    def to_sap_stock_transfer(
        pedido_data: Dict[str, Any],
        distribucion_por_tienda: Dict[str, List[Dict[str, Any]]],
        bodega_origen: str,
        oc_doc_num: Optional[int] = None,
        usuario_id: Optional[str] = None,
        pedido_id: Optional[str] = None,
        serie: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Convierte la distribución por tienda en múltiples Inventory Transfer Requests (una por tienda).
        
        ⚠️ IMPORTANTE: Genera Inventory Transfer Requests (POST /InventoryTransferRequests),
        NO Stock Transfer Orders. Las Inventory Transfer Requests son solicitudes que NO mueven stock.
        
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
            serie: Numbering Series de SAP para InventoryTransferRequests (ej: 10131)
        
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
            fecha = ahora_naive().strftime("%Y-%m-%d")
        
        numero_pedido = pedido_data.get("numero_pedido", "N/A")
        comentario_base = f"Transferencia desde OC {oc_doc_num}" if oc_doc_num else "Transferencia desde pedido"
        comentario_base += f" - Pedido {numero_pedido}"
        
        stock_transfers = []
        bodega_origen_upper = bodega_origen.strip().upper()
        
        # Crear un Inventory Transfer Request por cada tienda
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
                f"📤 Preparando Inventory Transfer Request: FromWarehouse='{bodega_origen_upper}', "
                f"ToWarehouse='{tienda_destino}' (código exacto de SAP)"
            )
            
            # ⚠️ VALIDACIÓN: No crear transferencia si origen == destino
            if bodega_origen_upper == tienda_destino:
                logger.warning(
                    f"⚠️ Omitiendo Inventory Transfer Request: origen y destino son iguales ({bodega_origen}). "
                    f"No tiene sentido crear una transferencia de {bodega_origen} a {tienda_destino}"
                )
                continue
            
            logger.debug(f"📋 Preparando JSON de Inventory Transfer Request: {bodega_origen} → {tienda_destino} ({len(productos)} productos)")
            
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
                
                # ⚠️ IMPORTANTE: InventoryTransferRequests no requiere LineNum
                line = {
                    "ItemCode": item_code,
                    "Quantity": float(cantidad)
                }
                
                stock_transfer_lines.append(line)
            
            if not stock_transfer_lines:
                logger.warning(f"⚠️ Tienda {tienda_id} sin líneas válidas, omitiendo")
                continue
            
            # Construir JSON completo del Inventory Transfer Request
            # ⚠️ IMPORTANTE: Formato correcto para InventoryTransferRequests (POST /InventoryTransferRequests)
            # ⚠️ NOTA: InventoryTransferRequests usa DueDate (no DocDueDate), que es correcto para este endpoint
            stock_transfer = {
                "DocDate": fecha,
                "DueDate": fecha,  # ⚠️ Correcto para Inventory Transfer Requests (POST /InventoryTransferRequests)
                "FromWarehouse": bodega_origen_upper,
                "ToWarehouse": tienda_destino,
                "Comments": comentario_base,
                "StockTransferLines": stock_transfer_lines,
            }
            # Guardar número de OC SAP en campo específico (U_ODC) si está disponible
            if oc_doc_num is not None:
                stock_transfer["U_ODC"] = oc_doc_num
            # ⭐ Asignar Numbering Series de SAP si se proporcionó (ej: 10131)
            if serie is not None:
                stock_transfer["Series"] = serie
            
            stock_transfers.append(stock_transfer)
        
        if not stock_transfers:
            raise ValueError("No hay stock transfers válidos para crear")
        
        # ⚠️ IMPORTANTE: Esto solo prepara los JSONs, NO crea ITRs en SAP
        logger.info(f"📋 Preparados {len(stock_transfers)} JSON(s) de Inventory Transfer Request para {len(distribucion_por_tienda)} tienda(s) (aún no creados en SAP)")
        return stock_transfers

    @staticmethod
    def to_sap_inventory_transfer_requests_by_bodega(
        oc_detalles: List[Dict[str, Any]],
        from_warehouse: str,
        doc_date: Optional[str] = None,
        due_date: Optional[str] = None,
        oc_doc_num: Optional[int] = None,
        serie: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Agrupa detalles de OC por codigo_bodega y genera 1 Inventory Transfer Request por bodega destino.
        Contrato Postman: POST /InventoryTransferRequests con DocDate, DueDate, FromWarehouse, ToWarehouse,
        Comments, StockTransferLines: [{ItemCode, Quantity}].
        """
        from collections import defaultdict

        if not doc_date:
            doc_date = ahora_naive().strftime("%Y-%m-%d")
        if not due_date:
            due_date = doc_date

        por_bodega: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for d in oc_detalles:
            b = (d.get("codigo_bodega") or d.get("warehouse_code") or "").strip()
            if not b or (d.get("cantidad_sap") or 0) <= 0:
                continue
            por_bodega[b].append(d)

        if not por_bodega:
            raise ValueError(
                "No hay detalles con codigo_bodega y cantidad_sap > 0 para generar Inventory Transfer Requests"
            )

        from_wh = from_warehouse.strip()
        payloads = []

        for to_wh, detalles in por_bodega.items():
            if from_wh.upper() == to_wh.upper():
                logger.warning(f"⚠️ Omitiendo ITR: FromWarehouse y ToWarehouse iguales ({to_wh})")
                continue
            agg: Dict[str, float] = defaultdict(float)
            for d in detalles:
                sku = d.get("sku_sap")
                qty = float(d.get("cantidad_sap", 0))
                if sku and qty > 0:
                    agg[sku] += qty

            lines = [{"ItemCode": k, "Quantity": v} for k, v in agg.items()]
            payload = {
                "DocDate": doc_date,
                "DueDate": due_date,
                "FromWarehouse": from_wh,
                "ToWarehouse": to_wh,
                "StockTransferLines": lines,
            }
            if oc_doc_num is not None:
                payload["Comments"] = f"Solicitud de traslado desde OC {oc_doc_num}"
                payload["U_ODC"] = oc_doc_num
            # ⭐ Asignar Numbering Series de SAP si se proporcionó (ej: 10131)
            if serie is not None:
                payload["Series"] = serie
            payloads.append(payload)
            logger.debug(f"   ITR: {from_wh} → {to_wh}, {len(lines)} línea(s)")

        if not payloads:
            raise ValueError("No se generó ningún Inventory Transfer Request (ej. origen = destinos)")
        # ⚠️ IMPORTANTE: Esto solo prepara los JSONs, NO crea ITRs en SAP
        logger.info(f"📋 Preparados {len(payloads)} JSON(s) de Inventory Transfer Request para {len(por_bodega)} bodega(s) (aún no creados en SAP)")
        return payloads
