"""
Cliente para hablar con SAP Business One: middleware .NET o conexión directa.

SAPServiceLayerClient() es una factory (no una clase) que, según SAP_USE_MIDDLEWARE
(.env), devuelve una de dos implementaciones con la misma interfaz pública:

- _MiddlewareSAPServiceLayerClient (default, SAP_USE_MIDDLEWARE=true): habla con el
  middleware .NET, que gestiona sesiones SAP, throttling, reintentos y circuit
  breaker internamente.
- DirectSAPServiceLayerClient (SAP_USE_MIDDLEWARE=false, en sap_service_layer_client_direct.py):
  conexión directa a SAP Service Layer, como funcionaba antes de integrar el
  middleware. Pensado para desarrollo, para poder seguir probando la app mientras se
  resuelve algún problema puntual del middleware.

Todos los callers existentes siguen haciendo simplemente `SAPServiceLayerClient()`
sin cambios.
"""

import json
import logging
import urllib.parse
import requests
from typing import Dict, Any, Optional, List

from src.config import (
    SAP_MIDDLEWARE_URL,
    ENABLE_SAP_SERVICE_LAYER,
    SAP_SERVICE_LAYER_TIMEOUT,
    SAP_USE_MIDDLEWARE,
)
from src.exceptions import SAPDataMasterError
from .sap_service_layer_client_direct import DirectSAPServiceLayerClient

logger = logging.getLogger(__name__)


class _MiddlewareSAPServiceLayerClient:
    """Cliente para el SAP Middleware API."""

    def __init__(self):
        self.base_url = SAP_MIDDLEWARE_URL.rstrip("/")
        self.enabled = ENABLE_SAP_SERVICE_LAYER
        self.timeout = SAP_SERVICE_LAYER_TIMEOUT

        if not self.enabled:
            logger.warning("⚠️ SAP Service Layer deshabilitado (ENABLE_SAP_SERVICE_LAYER=False)")

    # ─── HTTP helpers ──────────────────────────────────────────────────────────

    def _get(self, path: str) -> Optional[requests.Response]:
        try:
            return requests.get(f"{self.base_url}{path}", timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ GET {path}: error de conexión: {e}")
            return None

    def _post(self, path: str, json_data: Dict) -> Optional[requests.Response]:
        try:
            return requests.post(
                f"{self.base_url}{path}",
                json=json_data,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ POST {path}: error de conexión: {e}")
            return None

    @staticmethod
    def _problem_detail(response: requests.Response) -> str:
        """Extrae el mensaje de una respuesta ProblemDetails (RFC 7807)."""
        try:
            body = response.json()
            return body.get("detail") or body.get("title") or f"HTTP {response.status_code}"
        except Exception:
            return f"HTTP {response.status_code}: {response.text[:200]}"

    @staticmethod
    def _extraer_error_sap_embebido(response: requests.Response) -> Dict[str, Any]:
        """
        Extrae el código y detalle de error nativo de SAP B1 cuando el middleware
        lo reenvía embebido como texto dentro de `detail`, ej.:
        "SAP Service Layer returned HTTP 404: {\"error\": {\"code\": -2028, ...}}".

        Sin esto, retry_utils.sap_service_layer_result_should_retry no puede aplicar
        su política por código B1 (forzar/evitar reintento) y cae siempre a la
        heurística genérica por status HTTP.

        Retorna {"error_code": ..., "sap_error_details": ...}; ambos None si el
        body no es JSON o no sigue el formato esperado (no bloqueante).
        """
        try:
            problem_body = response.json()
        except ValueError:
            return {"error_code": None, "sap_error_details": None}

        detail = problem_body.get("detail") or ""
        inicio_json = detail.find("{")
        if inicio_json == -1:
            return {"error_code": None, "sap_error_details": None}

        try:
            sap_error_body = json.loads(detail[inicio_json:])
        except ValueError:
            return {"error_code": None, "sap_error_details": None}

        error_detail = sap_error_body.get("error") or {}
        return {
            "error_code": error_detail.get("code"),
            "sap_error_details": sap_error_body,
        }

    @staticmethod
    def _bool_to_tyes(value: Any) -> str:
        """Convierte bool del middleware al formato SAP tYES/tNO que esperan los callers."""
        if isinstance(value, bool):
            return "tYES" if value else "tNO"
        return value  # ya viene como string (ej: "tYES")

    # ─── Purchase Orders ───────────────────────────────────────────────────────

    def create_purchase_order(self, purchase_order_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Crea una OC en SAP via middleware.

        Traduce el formato PascalCase/OData que produce SAPOCMapper
        al camelCase que espera el middleware (POST /api/v1/purchase-orders).
        """
        if not self.enabled:
            logger.debug("⏭️ Creación de Purchase Order deshabilitada")
            return None

        lines = [
            {
                "itemCode": line.get("ItemCode"),
                "quantity": line.get("Quantity"),
                "unitPrice": line.get("UnitPrice"),
                "warehouseCode": line.get("WarehouseCode"),
            }
            for line in purchase_order_data.get("DocumentLines", [])
        ]

        payload = {
            "cardCode": purchase_order_data.get("CardCode"),
            "docDate": purchase_order_data.get("DocDate"),
            "docDueDate": purchase_order_data.get("DocDueDate"),
            "taxDate": purchase_order_data.get("TaxDate"),
            "comments": purchase_order_data.get("Comments"),
            "u_ORIGEN": purchase_order_data.get("U_ORIGEN"),
            "u_USUARIO": purchase_order_data.get("U_USUARIO"),
            "u_FECHA": purchase_order_data.get("U_FECHA"),
            "u_FE_ETG": purchase_order_data.get("U_FE_ETG"),
            "u_LOTE": purchase_order_data.get("U_LOTE"),
            "lines": lines,
        }

        logger.info(f"📤 POST /api/v1/purchase-orders (CardCode={payload['cardCode']}, {len(lines)} líneas)")
        logger.debug(f"   Payload: {payload}")

        response = self._post("/api/v1/purchase-orders", payload)
        if response is None:
            return {"success": False, "error": "No se pudo conectar con el middleware SAP"}

        if response.status_code in (200, 201):
            result = response.json()
            doc_entry = result.get("docEntry")
            doc_num = result.get("docNum")
            logger.info(f"✅ Purchase Order creada: DocEntry={doc_entry}, DocNum={doc_num}")
            return {"success": True, "doc_entry": doc_entry, "doc_num": doc_num, "data": result}

        error_msg = self._problem_detail(response)
        sap_error = self._extraer_error_sap_embebido(response)
        logger.error(f"❌ Error al crear Purchase Order: {error_msg} (Código SAP: {sap_error['error_code']})")
        return {
            "success": False,
            "error": error_msg,
            "error_code": sap_error["error_code"],
            "status_code": response.status_code,
            "sap_error_details": sap_error["sap_error_details"],
        }

    # ─── Stock Transfers ────────────────────────────────────────────────────────

    def create_stock_transfer(self, stock_transfer_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Crea una Inventory Transfer Request en SAP via middleware.

        Traduce el formato PascalCase/OData que produce SAPStockTransferMapper
        al camelCase que espera el middleware (POST /api/v1/stock-transfers/requests).
        """
        if not self.enabled:
            logger.debug("⏭️ Creación de Inventory Transfer Request deshabilitada")
            return None

        lines = [
            {
                "itemCode": line.get("ItemCode"),
                "quantity": line.get("Quantity"),
                "projectCode": None,
            }
            for line in stock_transfer_data.get("StockTransferLines", [])
        ]

        payload = {
            "fromWarehouse": stock_transfer_data.get("FromWarehouse"),
            "toWarehouse": stock_transfer_data.get("ToWarehouse"),
            "docDate": stock_transfer_data.get("DocDate"),
            "comments": stock_transfer_data.get("Comments"),
            # Series (serie de numeración) y U_ODC (nº de OC origen, UDF) son requeridos por
            # la TN custom de SAP para InventoryTransferRequests: sin ellos la validación
            # SBO_SP_TRANSACTIONNOTIFICATION falla con "1299 no data found". El flujo directo
            # (DirectSAPServiceLayerClient) los envía verbatim y por eso funciona; aquí hay que
            # reenviarlos explícitamente al middleware (que los mapea a Series/U_ODC en el
            # payload a SAP y los omite si llegan nulos). El middleware acepta camelCase.
            "series": stock_transfer_data.get("Series"),
            "uOdc": stock_transfer_data.get("U_ODC"),
            "lines": lines,
        }

        from_wh = payload["fromWarehouse"]
        to_wh = payload["toWarehouse"]
        logger.info(f"📤 POST /api/v1/stock-transfers/requests ({from_wh} → {to_wh}, {len(lines)} líneas)")

        response = self._post("/api/v1/stock-transfers/requests", payload)
        if response is None:
            return {"success": False, "error": "No se pudo conectar con el middleware SAP"}

        if response.status_code in (200, 201):
            result = response.json()
            doc_entry = result.get("docEntry")
            doc_num = result.get("docNum")
            logger.info(f"✅ Inventory Transfer Request creada: DocEntry={doc_entry}, DocNum={doc_num}")
            return {"success": True, "doc_entry": doc_entry, "doc_num": doc_num, "data": result}

        error_msg = self._problem_detail(response)
        sap_error = self._extraer_error_sap_embebido(response)
        logger.error(
            f"❌ Error al crear Inventory Transfer Request: {error_msg} "
            f"(Código SAP: {sap_error['error_code']})"
        )
        return {
            "success": False,
            "error": error_msg,
            "error_code": sap_error["error_code"],
            "status_code": response.status_code,
            "sap_error_details": sap_error["sap_error_details"],
        }

    # ─── Inventory Transfer Requests (query) ──────────────────────────────────

    def get_inventory_transfer_requests_by_comment(self, comment_filter: str) -> List[Dict[str, Any]]:
        """Consulta ITRs filtrando por texto en Comments via middleware."""
        if not self.enabled:
            logger.debug("⏭️ Consulta de ITR deshabilitada")
            return []

        encoded = urllib.parse.quote(comment_filter)
        path = f"/api/v1/inventory-transfer-requests?commentsContain={encoded}"

        logger.info(f"🔍 GET /api/v1/inventory-transfer-requests?commentsContain='{comment_filter}'")
        response = self._get(path)
        if response is None:
            return []

        if response.status_code == 200:
            data = response.json()
            items = data if isinstance(data, list) else data.get("value", [])
            logger.info(f"✅ ITR encontrados: {len(items)}")
            return [
                {
                    "doc_num": item.get("docNum"),
                    "doc_entry": item.get("docEntry"),
                    "to_warehouse": item.get("toWarehouse"),
                    "from_warehouse": item.get("fromWarehouse"),
                    "comments": item.get("comments"),
                }
                for item in items
            ]

        logger.warning(f"⚠️ Error al consultar ITR: {self._problem_detail(response)}")
        return []

    # ─── Items ─────────────────────────────────────────────────────────────────

    @classmethod
    def _map_item_data(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Traduce la respuesta de ítem del middleware (GET /items/{code} o /items/batch) al shape SAP clásico."""
        return {
            "ItemCode": data.get("itemCode"),
            "ItemName": data.get("itemName"),
            "PurchaseItem": cls._bool_to_tyes(data.get("purchaseItem")),
            "SalesItem": cls._bool_to_tyes(data.get("salesItem")),
            "InventoryItem": cls._bool_to_tyes(data.get("inventoryItem")),
            "Valid": cls._bool_to_tyes(data.get("valid")),
            "Frozen": cls._bool_to_tyes(data.get("frozen")),
            "ItemType": data.get("itemType"),
            "U_IXX_PACK": data.get("packCode"),
            "ItmsGrpCod": data.get("groupCode"),
            "ItmsGrpNam": data.get("groupName"),
            "CardCode": data.get("preferredVendorCode") or None,
        }

    @staticmethod
    def _item_no_existe(item_code: str) -> Dict[str, Any]:
        return {
            "_error": True,
            "_error_type": "no_existe",
            "_error_message": f"Item '{item_code}' no existe en SAP",
        }

    def get_item(self, item_code: str) -> Optional[Dict[str, Any]]:
        """Consulta un artículo en SAP via middleware."""
        if not self.enabled:
            logger.debug(f"⏭️ Consulta de Item deshabilitada: {item_code}")
            return None

        path = f"/api/v1/items/{urllib.parse.quote(item_code, safe='')}"
        logger.debug(f"🔍 GET {path}")
        response = self._get(path)
        if response is None:
            return None

        if response.status_code == 200:
            data = response.json()
            logger.info(
                f"✅ Item encontrado: {item_code} - "
                f"Comprable={data.get('purchaseItem')}, Valid={data.get('valid')}, Frozen={data.get('frozen')}"
            )
            return self._map_item_data(data)

        if response.status_code == 404:
            logger.warning(f"⚠️ Item no encontrado: {item_code}")
            return self._item_no_existe(item_code)

        error_msg = self._problem_detail(response)
        logger.error(f"❌ Error al consultar Item {item_code}: {error_msg}")
        return {"_error": True, "_error_type": "error", "_error_message": error_msg}

    _ITEMS_BATCH_CHUNK_SIZE = 100

    def _get_items_batch_chunk(self, codes: List[str]) -> Optional[Dict[str, Any]]:
        response = self._post("/api/v1/items/batch", {"itemCodes": codes})
        if response is None:
            return None
        if response.status_code == 200:
            return response.json()
        # Incluye 202 (el middleware encoló el trabajo porque SAP está lento/saturado):
        # un solo intento, sin poll — igual que validate_warehouses_batch y
        # validate_purchase_order_batch, cualquier cosa que no sea 200 inmediato se
        # trata como "no disponible ahora" y el caller resuelve estos códigos por su
        # camino habitual (uno por uno, o fallback a OPENQUERY).
        logger.warning(
            f"⏭️ Batch de items no disponible ahora (HTTP {response.status_code}): "
            f"{self._problem_detail(response)}. {len(codes)} código(s) de este chunk "
            f"se resolverán por el camino habitual."
        )
        return None

    def get_items_batch(self, item_codes: List[str]) -> Optional[Dict[str, Dict[str, Any]]]:
        """
        Consulta múltiples ítems en una sola llamada al middleware (en chunks de 100,
        límite del endpoint) en vez de una llamada GET /items/{code} por código.

        Un solo intento por chunk, sin polling — misma filosofía que
        validate_warehouses_batch/validate_purchase_order_batch: si el middleware
        encola el trabajo (202) o falla, esos códigos simplemente no aparecen en el
        resultado y el caller debe resolverlos por su camino habitual.

        Returns:
            Dict item_code -> mismo shape que get_item() (incluye entradas "no existe"
            para los códigos que el middleware reportó en `notFound`). Los códigos cuyo
            chunk falló están simplemente ausentes del dict — tratarlos como si
            get_item(codigo) hubiera devuelto None. None solo si NINGÚN chunk pudo
            resolverse (mismo contrato que validate_warehouses_batch cuando
            chunks_ok == 0).
        """
        if not self.enabled:
            logger.debug("⏭️ Batch de items deshabilitado")
            return None
        if not item_codes:
            return {}

        chunks = [
            item_codes[i:i + self._ITEMS_BATCH_CHUNK_SIZE]
            for i in range(0, len(item_codes), self._ITEMS_BATCH_CHUNK_SIZE)
        ]
        resultado: Dict[str, Dict[str, Any]] = {}
        chunks_ok = 0
        for chunk in chunks:
            data = self._get_items_batch_chunk(chunk)
            if data is None:
                continue
            chunks_ok += 1
            for item in data.get("items", []):
                item_code = item.get("itemCode")
                if item_code:
                    resultado[item_code] = self._map_item_data(item)
            for codigo in data.get("notFound", []):
                resultado[codigo] = self._item_no_existe(codigo)

        if chunks_ok == 0:
            return None
        logger.info(
            f"✅ Batch de items: {len(resultado)}/{len(item_codes)} código(s) resueltos vía middleware"
        )
        return resultado

    def get_stock_by_warehouse(self, item_code: str, warehouse_code: str) -> Optional[Dict[str, Any]]:
        """
        Consulta el stock disponible de un artículo en una bodega via middleware.

        Lanza SAPDataMasterError si el artículo no está configurado en esa bodega (404).
        """
        if not self.enabled:
            logger.debug("⏭️ Consulta de stock deshabilitada")
            return None

        path = (
            f"/api/v1/items/{urllib.parse.quote(item_code, safe='')}"
            f"/stock/{urllib.parse.quote(warehouse_code, safe='')}"
        )
        logger.debug(f"🔍 GET {path}")
        response = self._get(path)
        if response is None:
            return None

        if response.status_code == 200:
            data = response.json()
            in_stock_raw = float(data.get("inStock") or 0)
            is_committed = float(data.get("isCommitted") or 0)
            in_stock = in_stock_raw - is_committed
            uom_code = data.get("uomCode")
            locked = data.get("locked")
            locked_str = self._bool_to_tyes(locked)

            if uom_code is None:
                logger.warning(f"⚠️ {item_code}: UomCode=NULL - validación en unidades base")
            if locked_str == "tYES":
                logger.warning(f"⚠️ {item_code} en {warehouse_code} está BLOQUEADO")

            logger.info(
                f"✅ Stock disponible: {item_code} en {warehouse_code} = {in_stock} "
                f"(InStock={in_stock_raw}, Comprometido={is_committed})"
            )
            return {
                "InStock": in_stock,
                "UomCode": uom_code,
                "WarehouseCode": warehouse_code,
                "Locked": locked_str,
                "IsCommited": is_committed,
            }

        if response.status_code == 404:
            logger.warning(f"⚠️ {item_code} no configurado en bodega {warehouse_code}")
            raise SAPDataMasterError(
                item_code=item_code,
                warehouse_code=warehouse_code,
                error_type="warehouse_not_found",
                available_warehouses=[],
            )

        logger.error(f"❌ Error al consultar stock de {item_code}: {self._problem_detail(response)}")
        return None

    def get_business_partner(self, card_code: str) -> Optional[Dict[str, Any]]:
        """Consulta un Business Partner en SAP via middleware."""
        if not self.enabled:
            logger.debug(f"⏭️ Consulta de Business Partner deshabilitada: {card_code}")
            return None

        path = f"/api/v1/business-partners/{urllib.parse.quote(card_code, safe='')}"
        logger.debug(f"🔍 GET {path}")
        response = self._get(path)
        if response is None:
            return None

        if response.status_code == 200:
            data = response.json()
            logger.info(
                f"✅ Business Partner encontrado: {card_code} - "
                f"{data.get('cardName')} ({data.get('cardType')})"
            )
            return {
                "CardCode": data.get("cardCode"),
                "CardName": data.get("cardName"),
                "CardType": data.get("cardType"),
                "Valid": self._bool_to_tyes(data.get("valid")),
                "Frozen": self._bool_to_tyes(data.get("frozen")),
            }

        if response.status_code == 404:
            logger.warning(f"⚠️ Business Partner no encontrado: {card_code}")
            return {
                "_error": True,
                "_error_type": "no_existe",
                "_error_message": f"Business Partner '{card_code}' no existe en SAP",
            }

        error_msg = self._problem_detail(response)
        logger.error(f"❌ Error al consultar Business Partner {card_code}: {error_msg}")
        return {"_error": True, "_error_type": "error", "_error_message": error_msg}

    def validate_item_in_warehouse(self, item_code: str, warehouse_code: str) -> Dict[str, Any]:
        """Valida que un artículo exista y esté configurado en una bodega."""
        result = {
            "valid": False,
            "item_exists": False,
            "is_purchase_item": False,
            "warehouse_configured": False,
            "stock": None,
            "errors": [],
        }

        item = self.get_item(item_code)
        if item is None:
            result["errors"].append(f"Error de conexión al validar artículo {item_code}")
            return result

        if item.get("_error"):
            if item.get("_error_type") == "no_existe":
                result["errors"].append(f"Artículo '{item_code}' no existe en SAP")
            else:
                result["errors"].append(item.get("_error_message", f"Error al validar {item_code}"))
            return result

        result["item_exists"] = True

        if item.get("PurchaseItem") != "tYES":
            result["errors"].append(
                f"Artículo '{item_code}' no está habilitado para compra "
                f"(PurchaseItem={item.get('PurchaseItem')})"
            )
            return result

        result["is_purchase_item"] = True

        try:
            stock_info = self.get_stock_by_warehouse(item_code, warehouse_code)
            if stock_info is None:
                result["errors"].append(f"Error de conexión al validar bodega {warehouse_code}")
                return result
            result["warehouse_configured"] = True
            result["stock"] = stock_info.get("InStock", 0)
            result["valid"] = True
        except SAPDataMasterError as e:
            if e.available_warehouses:
                result["errors"].append(
                    f"Artículo '{item_code}' no está configurado en bodega '{warehouse_code}'. "
                    f"Bodegas disponibles: {', '.join(e.available_warehouses)}"
                )
            else:
                result["errors"].append(
                    f"Artículo '{item_code}' no tiene bodegas configuradas en SAP. "
                    f"Contacte a logística para dar de alta el artículo en la bodega '{warehouse_code}'."
                )
        except Exception as e:
            result["errors"].append(f"Error inesperado al validar artículo en bodega: {str(e)}")

        return result

    _WAREHOUSE_VALIDATE_CHUNK_SIZE = 200

    def get_all_warehouses(self) -> Optional[List[Dict[str, Any]]]:
        """Consulta el catálogo completo de bodegas via middleware."""
        if not self.enabled:
            logger.debug("⏭️ Consulta de bodegas deshabilitada")
            return None

        response = self._get("/api/v1/warehouses")
        if response is None:
            return None

        if response.status_code == 200:
            warehouses = response.json().get("warehouses", [])
            logger.info(f"✅ {len(warehouses)} bodega(s) obtenidas del middleware")
            return [
                {"WhsCode": w.get("whsCode"), "WhsName": w.get("whsName")}
                for w in warehouses
            ]

        logger.error(f"❌ Error al consultar bodegas: {self._problem_detail(response)}")
        return None

    def _validate_warehouses_chunk(self, codes: List[str]) -> Optional[List[Dict[str, Any]]]:
        response = self._post("/api/v1/warehouses/validate", {"warehouseCodes": codes})
        if response is None:
            return None
        if response.status_code == 200:
            return response.json().get("warehouses", [])
        logger.error(
            f"❌ Validación batch de bodegas no disponible (HTTP {response.status_code}): "
            f"{self._problem_detail(response)}"
        )
        return None

    def validate_warehouses_batch(self, warehouse_codes: List[str]) -> Optional[Dict[str, Any]]:
        """
        Valida una lista de códigos de bodega contra SAP, en chunks de 200 (límite del middleware).

        Returns:
            {"warehouses": [...]} combinando todos los chunks, o None si NINGÚN chunk
            pudo consultarse (el caller debe hacer fallback a OPENQUERY). Si solo
            algunos chunks fallan, sus códigos se marcan con errorType="connection_error".
        """
        if not self.enabled:
            logger.debug("⏭️ Validación batch de bodegas deshabilitada")
            return None
        if not warehouse_codes:
            return {"warehouses": []}

        chunks = [
            warehouse_codes[i:i + self._WAREHOUSE_VALIDATE_CHUNK_SIZE]
            for i in range(0, len(warehouse_codes), self._WAREHOUSE_VALIDATE_CHUNK_SIZE)
        ]
        warehouses: List[Dict[str, Any]] = []
        chunks_ok = 0
        for chunk in chunks:
            resultado_chunk = self._validate_warehouses_chunk(chunk)
            if resultado_chunk is None:
                warehouses.extend(
                    {"whsCode": code, "exists": False, "whsName": None, "errorType": "connection_error"}
                    for code in chunk
                )
                continue
            chunks_ok += 1
            warehouses.extend(resultado_chunk)

        if chunks_ok == 0:
            return None
        return {"warehouses": warehouses}

    def validate_purchase_order_batch(
        self,
        card_code: Optional[str],
        lines: List[Dict[str, str]],
    ) -> Optional[Dict[str, Any]]:
        """
        Prevalida proveedor + líneas de una ODC en una sola llamada batch al middleware.

        Args:
            card_code: CardCode del proveedor a validar (None para omitir)
            lines: Lista de {"itemCode": ..., "warehouseCode": ...}

        Returns:
            Respuesta del middleware ({"businessPartner": ..., "items": [...]}),
            o None si el batch no está disponible (deshabilitado, error de conexión,
            middleware sin el endpoint, o SL totalmente caído) — el caller debe
            hacer fallback a la validación línea por línea.
        """
        if not self.enabled:
            logger.debug("⏭️ Validación batch deshabilitada (ENABLE_SAP_SERVICE_LAYER=False)")
            return None

        payload: Dict[str, Any] = {"lines": lines}
        if card_code:
            payload["cardCode"] = card_code

        logger.info(
            f"📤 POST /api/v1/validations/purchase-order "
            f"(cardCode={card_code}, {len(lines)} líneas)"
        )
        response = self._post("/api/v1/validations/purchase-order", payload)
        if response is None:
            return None

        if response.status_code == 200:
            return response.json()

        logger.error(
            f"❌ Validación batch no disponible (HTTP {response.status_code}): "
            f"{self._problem_detail(response)}"
        )
        return None

    def logout(self) -> bool:
        """No-op: el middleware gestiona las sesiones SAP internamente."""
        return True


def SAPServiceLayerClient():
    """
    Factory: elige la implementación según SAP_USE_MIDDLEWARE (.env).

    - true (default): _MiddlewareSAPServiceLayerClient — habla con el middleware .NET.
    - false: DirectSAPServiceLayerClient — conexión directa a SAP Service Layer, como
      funcionaba antes de integrar el middleware. Útil en desarrollo para aislar si un
      problema es del middleware o de SAP mismo, sin dejar de tener el middleware
      disponible para cuando se reactive.
    """
    if SAP_USE_MIDDLEWARE:
        return _MiddlewareSAPServiceLayerClient()
    return DirectSAPServiceLayerClient()
