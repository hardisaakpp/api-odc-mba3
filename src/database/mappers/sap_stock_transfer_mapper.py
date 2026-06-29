"""
Mapper para convertir datos de distribución confirmada a formato JSON de Inventory Transfer Request de SAP Service Layer.

⚠️ IMPORTANTE: Este mapper genera Inventory Transfer Requests (Solicitudes de Traslado),
NO Stock Transfer Orders (Traslados). Las Inventory Transfer Requests NO mueven stock,
solo crean una solicitud que debe ser procesada posteriormente.
"""

import logging
from collections import defaultdict
from typing import Dict, Any, List, Optional

from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)


class SAPStockTransferMapper:
    """
    Mapper para convertir distribución por tienda a formato JSON de Inventory Transfer Request de SAP.

    ⚠️ IMPORTANTE: Genera Inventory Transfer Requests (POST /InventoryTransferRequests),
    NO Stock Transfer Orders. Las Inventory Transfer Requests son solicitudes que NO mueven stock.
    """

    @staticmethod
    def _build_transfer_lines(productos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Construye las líneas de un Inventory Transfer Request filtrando entradas inválidas."""
        lines = []
        for idx, producto in enumerate(productos):
            item_code = producto.get("item_code_sap") or producto.get("codigo_producto")
            cantidad = producto.get("cantidad_sap") or producto.get("cantidad_asignada", 0)
            if not item_code or cantidad <= 0:
                logger.warning(
                    f"⚠️ Línea {idx + 1} omitida: ItemCode={item_code}, Quantity={cantidad}"
                )
                continue
            # ⚠️ IMPORTANTE: InventoryTransferRequests no requiere LineNum
            lines.append({"ItemCode": item_code, "Quantity": float(cantidad)})
        return lines

    @staticmethod
    def _group_detalles_by_bodega(
        oc_detalles: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Agrupa detalles con cantidad_sap > 0 por codigo_bodega."""
        por_bodega: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for d in oc_detalles:
            b = (d.get("codigo_bodega") or d.get("warehouse_code") or "").strip()
            if b and (d.get("cantidad_sap") or 0) > 0:
                por_bodega[b].append(d)
        return por_bodega

    @staticmethod
    def _aggregate_by_sku(detalles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Agrega cantidades por SKU y retorna lista de {ItemCode, Quantity}."""
        agg: Dict[str, float] = defaultdict(float)
        for d in detalles:
            sku = d.get("sku_sap")
            qty = float(d.get("cantidad_sap", 0))
            if sku and qty > 0:
                agg[sku] += qty
        return [{"ItemCode": k, "Quantity": v} for k, v in agg.items()]

    @staticmethod
    def _build_comentario_transferencia(oc_doc_num: Optional[int], numero_pedido: str) -> str:
        """Construye el comentario base para un Inventory Transfer Request."""
        base = f"Transferencia desde OC {oc_doc_num}" if oc_doc_num else "Transferencia desde pedido"
        return f"{base} - Pedido {numero_pedido}"

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
        # Para Inventory Transfer Requests usar siempre la fecha actual de ejecución.
        fecha = ahora_naive().strftime("%Y-%m-%d")

        numero_pedido = pedido_data.get("numero_pedido", "N/A")
        comentario_base = SAPStockTransferMapper._build_comentario_transferencia(oc_doc_num, numero_pedido)

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

            stock_transfer_lines = SAPStockTransferMapper._build_transfer_lines(productos)

            if not stock_transfer_lines:
                logger.warning(f"⚠️ Tienda {tienda_id} sin líneas válidas, omitiendo")
                continue

            # Construir JSON completo del Inventory Transfer Request
            # ⚠️ IMPORTANTE: Formato correcto para InventoryTransferRequests (POST /InventoryTransferRequests)
            stock_transfer = {
                "DocDate": fecha,
                "FromWarehouse": bodega_origen_upper,
                "ToWarehouse": tienda_destino,
                "Comments": comentario_base,
                "PriceList": -2,
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
        Contrato Postman: POST /InventoryTransferRequests con DocDate, FromWarehouse, ToWarehouse,
        Comments, StockTransferLines: [{ItemCode, Quantity}].
        """
        # Para Inventory Transfer Requests usar siempre fecha actual de ejecución.
        effective_date = ahora_naive().strftime("%Y-%m-%d")

        por_bodega = SAPStockTransferMapper._group_detalles_by_bodega(oc_detalles)

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
            lines = SAPStockTransferMapper._aggregate_by_sku(detalles)
            payload = {
                "DocDate": effective_date,
                "FromWarehouse": from_wh,
                "ToWarehouse": to_wh,
                "PriceList": -2,
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
