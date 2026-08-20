"""
Servicio para crear Solicitudes de Transferencia (Inventory Transfer Requests) en SAP.
FASE 5: Generación de Solicitudes de Transferencia desde distribución confirmada por tienda.

⚠️ IMPORTANTE: Este servicio crea Inventory Transfer Requests (POST /InventoryTransferRequests),
NO Stock Transfer Orders. Las Inventory Transfer Requests son solicitudes que NO mueven stock,
solo crean una solicitud que debe ser procesada posteriormente.
"""

import contextlib
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

from src.config import PROJECT_ROOT
from src.config import (
    SAP_ITR_RETRY_MAX_ATTEMPTS,
    SAP_ITR_RETRY_BASE_DELAY_SECONDS,
    SAP_ITR_RETRY_MAX_JITTER_SECONDS,
)
from .retry_utils import retry_operation, sap_service_layer_result_should_retry
from .proceso_estado_service import get_redis_client
from ..connection import get_db_connection_context
from ..repositories.pedido_repository import PedidoRepository
from ..repositories.orden_compra_repository import OrdenCompraRepository
from ..repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
from ..repositories.pedido_sap_procesamiento_repository import PedidoSAPProcesamientoRepository
from ..repositories.solicitud_transferencia_repository import SolicitudTransferenciaRepository
from ..clients.sap_service_layer_client import SAPServiceLayerClient
from ..mappers.sap_stock_transfer_mapper import SAPStockTransferMapper
from ..services.bodega_sap_service import BodegaSAPService
from ..services.marca_tienda_service import MARCA_A_BODEGA
from src.exceptions import SAPDataMasterError, SolicitudTransferenciaNoAplicaError

logger = logging.getLogger(__name__)

_LOCK_REINTENTO_ST_TIMEOUT_SEGUNDOS = 120.0


@contextlib.contextmanager
def redis_lock_reintento_st(oc_id: str, blocking_timeout: float = 120.0):
    """
    Lock distribuido (Redis) para serializar reintentos de ST por oc_id.

    Necesario porque el endpoint manual (proceso FastAPI) y la reconciliación
    automática (proceso Celery) no comparten memoria; un lock en memoria
    (threading.Lock) solo protege dentro de un mismo proceso.

    Yields True si se obtuvo el lock, False si no (el caller debe omitir la ejecución).
    """
    client = get_redis_client()
    lock = client.lock(f"lock:reintento-st:{oc_id}", timeout=_LOCK_REINTENTO_ST_TIMEOUT_SEGUNDOS)
    acquired = False
    try:
        acquired = lock.acquire(blocking=True, blocking_timeout=blocking_timeout)
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except Exception:
                pass


class StockTransferService:
    """Servicio para crear Solicitudes de Transferencia en SAP."""

    # Reintentos automáticos por ITR individual cuando falla Service Layer
    RETRY_MAX_ATTEMPTS = SAP_ITR_RETRY_MAX_ATTEMPTS
    RETRY_BASE_DELAY_SECONDS = SAP_ITR_RETRY_BASE_DELAY_SECONDS
    RETRY_MAX_JITTER_SECONDS = SAP_ITR_RETRY_MAX_JITTER_SECONDS

    # Req. 1.6: pares (bodega_origen, bodega_tienda) donde se permite el traslado
    # cruzado entre CEDIs distintos, además del caso normal bodega_origen == bodega_tienda.
    BODEGAS_TRASLADO_CRUZADO_PERMITIDO = frozenset({
        ("RL-CD", "RG-CD"),
        ("RG-CD", "RL-CD"),
    })

    def __init__(self):
        """Inicializa el servicio."""
        self.sap_client = SAPServiceLayerClient()

    def _enviar_itr_con_reintento(
        self,
        payload: Dict[str, Any],
        bodega_origen: str,
        tienda_codigo: str,
    ) -> Dict[str, Any]:
        """
        Envía una ITR a SAP con reintento automático y backoff exponencial.

        Reintenta solo la ITR actual (no todo el batch) para soportar éxito parcial.
        """
        return retry_operation(
            execute=lambda: self.sap_client.create_stock_transfer(payload),
            is_success=lambda response: bool(
                response and response.get("success") and response.get("doc_entry")
            ),
            extract_error=lambda response: (
                response.get("error", "Sin respuesta de SAP")
                if response else "Sin respuesta de SAP"
            ),
            max_attempts=self.RETRY_MAX_ATTEMPTS,
            should_retry=sap_service_layer_result_should_retry,
            base_delay_seconds=self.RETRY_BASE_DELAY_SECONDS,
            max_jitter_seconds=self.RETRY_MAX_JITTER_SECONDS,
            logger=logger,
            operation_label=f"ITR ({bodega_origen} → {tienda_codigo})",
        )

    def _validate_itr_lines(self, itr_idx: int, lines: List[Dict[str, Any]]) -> None:
        """Valida que un ITR tenga al menos una línea con ItemCode y Quantity > 0."""
        if not lines:
            raise ValueError(
                f"ITR {itr_idx+1}: Debe tener al menos una línea en StockTransferLines"
            )
        for line_idx, line in enumerate(lines):
            item_code = line.get("ItemCode", "").strip()
            quantity = float(line.get("Quantity", 0))
            if not item_code:
                raise ValueError(
                    f"ITR {itr_idx+1}, línea {line_idx+1}: ItemCode es requerido"
                )
            if quantity <= 0:
                raise ValueError(
                    f"ITR {itr_idx+1}, línea {line_idx+1}: Quantity debe ser mayor que 0 (actual: {quantity})"
                )

    def _validate_itr_minimal(
        self,
        stock_transfers_json: List[Dict[str, Any]]
    ) -> None:
        """
        Valida mínimamente los Inventory Transfer Requests antes de enviarlos a SAP.

        ⚠️ IMPORTANTE: Para ITR, SAP NO requiere:
        - Artículo asociado a bodega origen (ItemWarehouseInfoCollection puede estar vacío)
        - Stock disponible
        - Artículo habilitado en bodega origen

        SAP solo valida:
        - ItemCode existe
        - FromWarehouse != ToWarehouse
        - Quantity > 0
        - Formato JSON correcto

        Esta validación solo verifica lo esencial antes de enviar a SAP.

        Args:
            stock_transfers_json: Lista de ITRs a crear (formato SAP Service Layer)

        Raises:
            ValueError: Si hay errores de formato básico (FromWarehouse == ToWarehouse, Quantity <= 0)
        """
        for idx, itr in enumerate(stock_transfers_json):
            from_wh = itr.get("FromWarehouse", "").strip()
            to_wh = itr.get("ToWarehouse", "").strip()
            if not from_wh or not to_wh:
                raise ValueError(
                    f"ITR {idx+1}: FromWarehouse y ToWarehouse son requeridos"
                )
            if from_wh.upper() == to_wh.upper():
                raise ValueError(
                    f"ITR {idx+1}: FromWarehouse ({from_wh}) no puede ser igual a ToWarehouse ({to_wh})"
                )
            self._validate_itr_lines(idx, itr.get("StockTransferLines", []))

        logger.info(
            f"✅ Validación mínima ITR: {len(stock_transfers_json)} documento(s) con formato correcto"
        )

    @staticmethod
    def _recopilar_items_unicos_distribucion(
        distribucion_por_tienda: Dict[str, List[Dict[str, Any]]]
    ) -> set:
        """Extrae el conjunto de item_code_sap únicos de la distribución agrupada por tienda."""
        items_unicos: set = set()
        for productos in distribucion_por_tienda.values():
            for producto in productos:
                item_code_sap = producto.get("item_code_sap")
                if item_code_sap:
                    items_unicos.add(item_code_sap)
        return items_unicos

    @staticmethod
    def _construir_mensaje_no_habilitados(
        articulos_no_habilitados: List[Dict[str, Any]],
        bodega_origen: str
    ) -> str:
        """Construye el mensaje de error para artículos no habilitados en la bodega origen."""
        items_list = [a["item_code"] for a in articulos_no_habilitados]
        if len(articulos_no_habilitados) == 1:
            primer_error = articulos_no_habilitados[0]
            warehouses_str = (
                ", ".join(primer_error["available_warehouses"])
                if primer_error["available_warehouses"] else "NINGUNA"
            )
            return (
                f"El artículo {items_list[0]} no está habilitado en la bodega origen {bodega_origen} en SAP. "
                f"Bodegas donde SÍ está habilitado: {warehouses_str}. "
                f"Contacte a logística o maestros de artículos para habilitar el artículo en la bodega {bodega_origen}."
            )
        return (
            f"{len(articulos_no_habilitados)} artículos no están habilitados en la bodega origen {bodega_origen} en SAP. "
            f"Artículos: {', '.join(items_list[:5])}"
            f"{' y ' + str(len(items_list) - 5) + ' más' if len(items_list) > 5 else ''}. "
            f"Contacte a logística o maestros de artículos para habilitar estos artículos en la bodega {bodega_origen}."
        )

    def _validate_articulos_habilitados_en_bodega_origen(
        self,
        distribucion_por_tienda: Dict[str, List[Dict[str, Any]]],
        bodega_origen: str
    ) -> None:
        """
        ⚠️ DEPRECADO PARA ITR: Esta validación es demasiado estricta para Inventory Transfer Requests.

        SAP NO requiere que los artículos estén habilitados en la bodega origen para crear ITR.
        Esta validación solo debería usarse para Inventory Transfer real (movimientos de stock).

        Para ITR, usar `_validate_itr_minimal()` únicamente.

        Valida PREVENTIVAMENTE que todos los artículos estén habilitados en la bodega origen.

        Esta validación se hace ANTES de crear las ST para detectar problemas de datos maestros
        de forma temprana y dar un mensaje claro al usuario.

        Args:
            distribucion_por_tienda: Distribución agrupada por tienda
            bodega_origen: Código de bodega origen (ej: "RL-CD", "OUT-CD", "RG-CD")

        Raises:
            SAPDataMasterError: Si algún artículo no está habilitado en la bodega origen
        """
        items_unicos = self._recopilar_items_unicos_distribucion(distribucion_por_tienda)
        if not items_unicos:
            logger.warning("⚠️ No hay artículos para validar habilitación en bodega origen")
            return

        logger.info(
            f"🔍 Validando que {len(items_unicos)} artículo(s) estén habilitados en bodega origen {bodega_origen}..."
        )

        articulos_no_habilitados = []
        for item_code in items_unicos:
            try:
                stock_info = self.sap_client.get_stock_by_warehouse(item_code, bodega_origen)
                if stock_info is None:
                    # ⚠️ WARNING funcional: problema de conexión, no bloqueante para validación preventiva
                    logger.warning(
                        f"⚠️ No se pudo verificar habilitación de {item_code} en {bodega_origen} "
                        f"(error de conexión). Se continuará con la validación."
                    )
                    continue
                logger.debug(f"✅ {item_code} habilitado en {bodega_origen}")
            except SAPDataMasterError as e:
                articulos_no_habilitados.append({
                    "item_code": item_code,
                    "error_type": e.error_type,
                    "available_warehouses": e.available_warehouses
                })
                logger.warning(f"⚠️ {item_code} NO habilitado en bodega origen {bodega_origen}")

        if articulos_no_habilitados:
            items_list = [a["item_code"] for a in articulos_no_habilitados]
            mensaje = self._construir_mensaje_no_habilitados(articulos_no_habilitados, bodega_origen)
            logger.error(
                f"❌ VALIDACIÓN PREVENTIVA: {len(articulos_no_habilitados)} artículo(s) no habilitados en bodega origen {bodega_origen}: "
                f"{', '.join(items_list)}"
            )
            primer_error = articulos_no_habilitados[0]
            raise SAPDataMasterError(
                item_code=primer_error["item_code"],
                warehouse_code=bodega_origen,
                error_type=primer_error["error_type"],
                message=mensaje,
                available_warehouses=primer_error.get("available_warehouses", [])
            )

        logger.info(
            f"✅ Validación preventiva: todos los {len(items_unicos)} artículo(s) están habilitados en bodega origen {bodega_origen}"
        )

    @staticmethod
    def _obtener_bodega_por_prefijo(codigo_upper: str) -> Optional[str]:
        """
        Determina a qué bodega pertenece una tienda basándose en el prefijo de su código.

        Reglas de mapeo:
        - TRL-* (excepto TRL-RG*) → RL-CD (ROLAND)
        - TOUT-* → OUT-CD (DESCUENTON)
        - RG-* o TRL-RG* → RG-CD (REGIONS)
        """
        # REGIONS: RG-* o TRL-RG*
        if codigo_upper.startswith("RG-") or codigo_upper.startswith("TRL-RG"):
            return "RG-CD"

        # DESCUENTON: TOUT-*
        if codigo_upper.startswith("TOUT-"):
            return "OUT-CD"

        # ROLAND: TRL-* (resto)
        if codigo_upper.startswith("TRL-"):
            return "RL-CD"

        return None

    @staticmethod
    def _obtener_marca_local(codigo_upper: str) -> Optional[str]:
        """Lee tienda.marca (local, ya sincronizada desde sc_maestros) para un código. No bloqueante."""
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT marca FROM tienda WHERE codigo = ?", (codigo_upper,))
                row = cursor.fetchone()
                cursor.close()
                return row[0].strip().upper() if row and row[0] else None
        except Exception as e:
            logger.warning(f"⚠️ No se pudo leer marca local de tienda {codigo_upper}: {e}")
            return None

    @staticmethod
    def obtener_bodega_de_tienda(tienda_codigo: str) -> Optional[str]:
        """
        Determina a qué bodega pertenece una tienda.

        Prioridad:
        1. tienda.marca (sincronizada desde sc_maestros.almacenes_local) → MARCA_A_BODEGA
        2. Heurístico de prefijo del código (fallback si la tienda no existe localmente
           o su marca aún no fue sincronizada)

        Args:
            tienda_codigo: Código de la tienda (ej: "TRL-QSN", "TOUT-BMB", "RG-INT")

        Returns:
            Código de bodega (OUT-CD, RG-CD, RL-CD) o None si no se puede determinar
        """
        if not tienda_codigo:
            return None

        codigo_upper = tienda_codigo.strip().upper()

        marca = StockTransferService._obtener_marca_local(codigo_upper)
        if marca and marca in MARCA_A_BODEGA:
            return MARCA_A_BODEGA[marca]

        return StockTransferService._obtener_bodega_por_prefijo(codigo_upper)

    @staticmethod
    def detectar_origenes_traslado(detalles: List[Dict[str, Any]]) -> List[str]:
        """
        Detecta la(s) bodega(s)/CD de un pedido a partir de las tiendas (no bodegas)
        presentes en sus detalles — no persiste nada, es un valor calculado para
        mostrar en pantalla (campo "Origen Traslado"). No reemplaza al campo
        legado `pedido.origen_traslado` (valor único, escrito a mano en el Excel,
        usado sin cambios por el resto del sistema).

        Args:
            detalles: Lista de detalles del pedido, cada uno con "tiendas": [{"codigo", "es_bodega", ...}]
                      (formato de PedidoUtilsRepository.obtener_detalles_pedido).

        Returns:
            Códigos de bodega distintos, ordenados (ej. ["RG-CD", "RL-CD"]; un solo
            elemento en el caso normal de una sola marca).
        """
        codigos_tiendas: set = set()
        for detalle in detalles:
            for tienda in detalle.get("tiendas", []):
                if tienda.get("es_bodega", False):
                    continue
                codigo = tienda.get("codigo")
                if codigo:
                    codigos_tiendas.add(codigo.strip().upper())

        bodegas: set = set()
        for codigo in codigos_tiendas:
            bodega = StockTransferService.obtener_bodega_de_tienda(codigo)
            if bodega:
                bodegas.add(bodega)
        return sorted(bodegas)

    @staticmethod
    def _agrupar_cantidades_requeridas(
        stock_transfers_json: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Agrupa las cantidades requeridas por ItemCode sumando todas las líneas de todos los STs."""
        total_required: Dict[str, float] = defaultdict(float)
        for st in stock_transfers_json:
            for line in st.get("StockTransferLines", []):
                item_code = line.get("ItemCode")
                quantity = float(line.get("Quantity", 0))
                if item_code and quantity > 0:
                    total_required[item_code] += quantity
        return total_required

    def _verificar_stock_item(
        self,
        item_code: str,
        required_qty: float,
        source_warehouse: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Consulta stock de un item y determina si hay insuficiencia o error de datos maestros.

        Returns:
            (insuficiente_dict_or_None, error_datos_maestros_dict_or_None)
        Raises:
            ValueError: Si SAP no retorna información de stock (error de conexión).
        """
        try:
            stock_info = self.sap_client.get_stock_by_warehouse(item_code, source_warehouse)
        except SAPDataMasterError as e:
            return None, {
                "item_code": e.item_code,
                "error_type": e.error_type,
                "available_warehouses": e.available_warehouses,
                "required_warehouse": e.warehouse_code
            }

        if stock_info is None:
            # ⚠️ WARNING funcional: problema de conexión, no de datos maestros
            logger.warning(
                f"⚠️ No se pudo consultar stock de {item_code} en {source_warehouse}. "
                f"Error de conexión o respuesta inesperada de SAP. "
                f"NO se puede validar stock - ABORTANDO validación."
            )
            raise ValueError(
                f"El artículo {item_code} no está asociado a la bodega {source_warehouse} en SAP, "
                f"o hay un problema de conexión con SAP. "
                f"Contacte a logística o maestros de artículos para verificar la configuración del artículo en SAP."
            )

        available = stock_info.get("InStock", 0.0)
        uom_code = stock_info.get("UomCode")

        # ⭐ VALIDACIÓN CRÍTICA: Si UomCode es NULL, SAP solo conoce unidad base.
        # La conversión (ej: X12) existe solo en lógica externa, por lo que debemos
        # validar que el stock en unidades base alcance para la cantidad ya convertida.
        if uom_code is None:
            logger.debug(
                f"ℹ️ {item_code}: UomCode=NULL en SAP. "
                f"Validando stock en unidades base (InStock={available}) vs cantidad convertida ({required_qty})"
            )
            if available < required_qty:
                logger.error(
                    f"❌ Stock insuficiente REAL: {item_code} en {source_warehouse}. "
                    f"Disponible (unidades base): {available}, Requerido (convertido): {required_qty}, "
                    f"Faltante: {required_qty - available}"
                )
                return {
                    "item_code": item_code,
                    "disponible": available,
                    "requerido": required_qty,
                    "faltante": required_qty - available,
                    "uom_code": None,
                    "nota": "UomCode=NULL: validación en unidades base"
                }, None
        else:
            if available < required_qty:
                logger.error(
                    f"❌ Stock insuficiente REAL: {item_code} en {source_warehouse}. "
                    f"Disponible: {available}, Requerido: {required_qty}, Faltante: {required_qty - available} "
                    f"(UomCode={uom_code})"
                )
                return {
                    "item_code": item_code,
                    "disponible": available,
                    "requerido": required_qty,
                    "faltante": required_qty - available,
                    "uom_code": uom_code
                }, None

        return None, None

    @staticmethod
    def _lanzar_error_datos_maestros(
        productos_error_datos_maestros: List[Dict[str, Any]],
        source_warehouse: str
    ) -> None:
        """Construye y lanza SAPDataMasterError cuando hay artículos sin info de bodega en SAP."""
        items_list = [p['item_code'] for p in productos_error_datos_maestros]
        # ⚠️ WARNING funcional: ItemWarehouseInfoCollection vacío es esperado para algunos tipos de artículos
        # pero impide validar stock, por lo que abortamos la creación de ITRs
        logger.warning(
            f"⚠️ VALIDACIÓN DE STOCK ABORTADA: {len(productos_error_datos_maestros)} artículo(s) "
            f"sin información de bodega {source_warehouse} en SAP (ItemWarehouseInfoCollection vacío). "
            f"Artículos: {', '.join(items_list)}. "
            f"NO se pueden crear Inventory Transfer Requests sin validación de stock."
        )
        primer_error = productos_error_datos_maestros[0]
        if len(productos_error_datos_maestros) == 1:
            mensaje_negocio = (
                f"El artículo {items_list[0]} no está asociado a la bodega {source_warehouse} en SAP. "
                f"Contacte a logística o maestros de artículos para verificar la configuración del artículo."
            )
        else:
            mensaje_negocio = (
                f"{len(productos_error_datos_maestros)} artículos no están asociados a la bodega {source_warehouse} en SAP. "
                f"Artículos: {', '.join(items_list[:5])}"
                f"{' y ' + str(len(items_list) - 5) + ' más' if len(items_list) > 5 else ''}. "
                f"Contacte a logística o maestros de artículos para verificar la configuración de estos artículos."
            )
        raise SAPDataMasterError(
            item_code=primer_error['item_code'],
            warehouse_code=source_warehouse,
            error_type=primer_error['error_type'],
            message=mensaje_negocio,
            available_warehouses=primer_error.get('available_warehouses', [])
        )

    @staticmethod
    def _lanzar_error_stock_insuficiente(
        productos_insuficientes: List[Dict[str, Any]],
        source_warehouse: str
    ) -> None:
        """Construye y lanza ValueError cuando hay productos con stock insuficiente."""
        error_msg = f"Stock insuficiente en {source_warehouse} para crear Solicitudes de Transferencia:\n"
        for prod in productos_insuficientes:
            uom_note = ""
            if prod.get("uom_code") is None:
                uom_note = " (UomCode=NULL: validación en unidades base)"
            elif prod.get("uom_code"):
                uom_note = f" (UomCode={prod['uom_code']})"
            error_msg += (
                f"  - {prod['item_code']}: Disponible={prod['disponible']}, "
                f"Requerido={prod['requerido']}, Faltante={prod['faltante']}{uom_note}\n"
            )
        raise ValueError(error_msg.strip())

    def _validate_stock_before_st(
        self,
        stock_transfers_json: List[Dict[str, Any]],
        source_warehouse: str
    ) -> None:
        """
        ⚠️ DEPRECADO PARA ITR: Esta validación es demasiado estricta para Inventory Transfer Requests.

        SAP NO requiere validación de stock para crear ITR (solo para Inventory Transfer real).
        Esta validación solo debería usarse para Inventory Transfer real (movimientos de stock).

        Para ITR, usar `_validate_itr_minimal()` y `_log_articulos_info_optional()`.

        Valida que haya stock suficiente en la bodega origen antes de crear las STs.

        ⭐ IMPORTANTE: Esta validación previene el error "Quantity falls into negative inventory"
        que ocurre cuando SAP evalúa el stock disponible considerando las transacciones previas
        en el mismo proceso. Al validar ANTES de crear cualquier ST, evitamos crear STs parciales
        y estados inconsistentes.

        Args:
            stock_transfers_json: Lista de STs a crear (formato SAP Service Layer)
            source_warehouse: Código de bodega origen (ej: "RL-CD", "OUT-CD", "RG-CD")

        Raises:
            ValueError: Si no hay stock suficiente para algún producto.
                El mensaje incluye detalles de qué productos faltan y cuánto stock falta.
        """
        total_required = self._agrupar_cantidades_requeridas(stock_transfers_json)
        if not total_required:
            logger.warning("⚠️ No hay productos para validar stock")
            return

        logger.info(
            f"🔍 Validando stock total en {source_warehouse} para {len(total_required)} producto(s)..."
        )

        productos_insuficientes: List[Dict[str, Any]] = []
        productos_error_datos_maestros: List[Dict[str, Any]] = []

        for item_code, required_qty in total_required.items():
            insuf, err = self._verificar_stock_item(item_code, required_qty, source_warehouse)
            if err:
                productos_error_datos_maestros.append(err)
            elif insuf:
                productos_insuficientes.append(insuf)

        # ❌ CORTAR FLUJO inmediatamente si hay errores de datos maestros
        if productos_error_datos_maestros:
            self._lanzar_error_datos_maestros(productos_error_datos_maestros, source_warehouse)

        if productos_insuficientes:
            self._lanzar_error_stock_insuficiente(productos_insuficientes, source_warehouse)

        # ✅ Solo loguear éxito si REALMENTE se validó TODO correctamente
        if not productos_error_datos_maestros and not productos_insuficientes:
            logger.info(
                f"✅ Stock suficiente validado: todos los {len(total_required)} producto(s) tienen disponibilidad en {source_warehouse}"
            )

    def _persistir_y_guardar_json_solicitudes_transferencia(
        self,
        conn,
        result: Dict[str, Any],
        payloads_sap: Optional[List[Dict[str, Any]]],
        oc_id: Optional[str],
        pedido_id: str,
        bodega_origen: Optional[str],
        oc_doc_num: Optional[int] = None,
    ) -> None:
        """
        Persiste el resultado de solicitudes de transferencia en BD y genera JSON en output/.
        No falla el proceso principal si hay error.
        """
        try:
            st_repo = SolicitudTransferenciaRepository(conn)
            solicitud_id = st_repo.insert(
                pedido_id=pedido_id,
                resultado=result,
                payloads_sap=payloads_sap,
                oc_id=oc_id,
                oc_doc_num=oc_doc_num,
                bodega_origen=bodega_origen,
            )
            if solicitud_id and result.get("resultados"):
                st_repo.insert_detalle(
                    solicitud_transferencia_id=solicitud_id,
                    resultados=result["resultados"],
                )
            if solicitud_id:
                result["solicitud_transferencia_id"] = solicitud_id
            logger.info(f"📥 Solicitudes de Transferencia persistidas en BD para pedido {pedido_id}")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo persistir Solicitudes de Transferencia en BD: {e}")

        try:
            output_dir = PROJECT_ROOT / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            out_file = output_dir / f"str_{pedido_id}.json"
            json_data = {
                "pedido_id": pedido_id,
                "oc_id": oc_id,
                "oc_doc_num": oc_doc_num,
                "bodega_origen": bodega_origen,
                "resultado": result,
                "payloads_sap": payloads_sap or [],
            }
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)
            logger.info(f"📥 Solicitudes de Transferencia guardadas en {out_file}")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo guardar JSON de Solicitudes de Transferencia: {e}")

    # ── helpers for crear_solicitudes_transferencia_desde_pedido ────────────

    def _obtener_datos_pedido(
        self,
        pedido_repo: PedidoRepository,
        dist_repo: DistribucionConfirmadaRepository,
        sap_proc_repo: PedidoSAPProcesamientoRepository,
        pedido_id: str,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
        """Obtiene y valida pedido, distribución confirmada y procesamientos SAP. Raises ValueError si falta algo."""
        pedido_data = pedido_repo.get_pedido_completo(pedido_id)
        if not pedido_data:
            raise ValueError(f"No se encontró el pedido con ID: {pedido_id}")
        pedido_cabecera = pedido_data.get("cabecera", {})

        version_actual = dist_repo.get_version_actual(pedido_id)
        if version_actual == 0:
            raise ValueError(f"No hay distribución confirmada para el pedido {pedido_id}")

        distribucion_data = dist_repo.get_distribucion_completa(pedido_id, version_actual)
        productos_distribucion = distribucion_data.get("productos", [])
        if not productos_distribucion:
            raise ValueError(f"No hay productos en la distribución confirmada del pedido {pedido_id}")

        procesamientos = sap_proc_repo.get_procesamientos_por_pedido(pedido_id)
        mapa_procesamientos = {p["pedido_detalle_id"]: p for p in procesamientos}
        return pedido_cabecera, productos_distribucion, mapa_procesamientos

    def _resolver_serie(
        self,
        pedido_cabecera: Dict[str, Any],
        serie: Optional[int]
    ) -> Optional[int]:
        """Determina la serie a usar: parámetro > valor del pedido > None."""
        if serie is not None:
            logger.info(f"📍 Usando serie proporcionada para ITR: {serie}")
            return serie
        serie_raw = pedido_cabecera.get("serie")
        if serie_raw is not None:
            try:
                result = int(serie_raw)
                logger.info(f"📍 Usando serie del pedido para ITR: {result}")
                return result
            except (TypeError, ValueError):
                logger.warning(f"⚠️ Valor de serie no válido en pedido: {serie_raw}")
        return None

    @staticmethod
    def _resolver_bodega_origen(
        bodega_origen: Optional[str],
        pedido_cabecera: Dict[str, Any]
    ) -> str:
        """
        Determina la bodega origen a usar.
        Prioridad: parámetro > origen_traslado del pedido > "01" como default.
        """
        if not bodega_origen:
            # ⭐ IMPORTANTE: Si bodega_origen viene de la OC (codigo_bodega), tiene prioridad
            # sobre origen_traslado del pedido para asegurar consistencia
            bodega_origen = pedido_cabecera.get("origen_traslado") or "01"
            logger.info(f"📍 Usando bodega origen del pedido (origen_traslado): {bodega_origen}")
        else:
            logger.info(f"📍 Usando bodega origen proporcionada (de la OC): {bodega_origen}")
        return bodega_origen or "01"

    @staticmethod
    def _recopilar_codigos_tiendas(
        productos_distribucion: List[Dict[str, Any]]
    ) -> set:
        """Recopila todos los códigos de tiendas únicos (normalizados a upper) de la distribución."""
        codigos: set = set()
        for producto_dist in productos_distribucion:
            for dist in producto_dist.get("distribuciones", []):
                if dist.get("es_bodega", False):
                    continue
                tienda_codigo = dist.get("tienda_codigo")
                if tienda_codigo:
                    codigos.add(tienda_codigo.strip().upper())
        return codigos

    def _validar_tiendas_en_sap(
        self,
        codigos_tiendas_unicos: set
    ) -> Tuple[set, Dict[str, str], Dict[str, str]]:
        """
        Valida que los códigos de tienda existan en SAP y construye los mapeos de código y nombre.

        Returns:
            (tiendas_validas_en_sap, mapeo_codigo_exacto_sap, mapeo_nombre_tienda)
        """
        tiendas_validas_en_sap: set = set()
        mapeo_codigo_exacto_sap: Dict[str, str] = {}
        mapeo_nombre_tienda: Dict[str, str] = {}

        if not codigos_tiendas_unicos:
            return tiendas_validas_en_sap, mapeo_codigo_exacto_sap, mapeo_nombre_tienda

        logger.info(f"🔍 Validando {len(codigos_tiendas_unicos)} tienda(s) en SAP antes de crear STs...")
        bodega_sap_service = BodegaSAPService()
        resultado_validacion = bodega_sap_service.validate_codigos_bodegas_tiendas(
            codigos=list(codigos_tiendas_unicos),
            force_refresh=False
        )

        for codigo, info in resultado_validacion.items():
            if info.get("encontrado", False):
                codigo_normalizado = codigo.upper()
                # ⭐ IMPORTANTE: Guardar código exacto de SAP (WhsCode) y nombre para usar en las STs
                codigo_exacto_sap = info.get("WhsCode", codigo_normalizado)
                nombre_tienda = info.get("WhsName", None)
                tiendas_validas_en_sap.add(codigo_normalizado)
                mapeo_codigo_exacto_sap[codigo_normalizado] = codigo_exacto_sap
                if nombre_tienda:
                    mapeo_nombre_tienda[codigo_normalizado] = nombre_tienda
                logger.info(
                    f"✅ Tienda validada en SAP: '{codigo}' → WhsCode='{codigo_exacto_sap}', "
                    f"Nombre='{nombre_tienda or 'N/A'}'"
                )
            else:
                logger.warning(
                    f"⚠️ Tienda NO encontrada en SAP: '{codigo}'. "
                    f"Se omitirá al crear Solicitudes de Transferencia."
                )

        tiendas_no_encontradas = codigos_tiendas_unicos - tiendas_validas_en_sap
        if tiendas_no_encontradas:
            logger.warning(
                f"⚠️ {len(tiendas_no_encontradas)} tienda(s) no encontrada(s) en SAP y serán omitidas: "
                f"{', '.join(sorted(tiendas_no_encontradas))}"
            )
        else:
            logger.info(f"✅ Todas las {len(tiendas_validas_en_sap)} tienda(s) validadas en SAP")

        return tiendas_validas_en_sap, mapeo_codigo_exacto_sap, mapeo_nombre_tienda

    def _procesar_dist_tienda(
        self,
        dist: Dict[str, Any],
        pedido_detalle_id: str,
        item_code_sap: str,
        factor_conversion: float,
        codigo_producto: Optional[str],
        bodega_origen_upper: str,
        bodegas_codigos: set,
        tiendas_validas_en_sap: set,
        mapeo_codigo_exacto_sap: Dict[str, str],
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Procesa una distribución individual de tienda.

        Returns:
            (entry_dict, omitida) — entry_dict es None si se omitió o si cantidad <= 0.
        """
        tienda_id = dist.get("tienda_id")
        tienda_codigo = dist.get("tienda_codigo")
        cantidad_asignada = dist.get("cantidad_asignada", 0)
        es_bodega = dist.get("es_bodega", False)

        if cantidad_asignada <= 0:
            return None, False

        tienda_codigo_upper = tienda_codigo.strip().upper() if tienda_codigo else ""

        # ⭐ VALIDACIÓN 1: Excluir bodegas como destino (evitar ST de bodega a bodega)
        if tienda_codigo_upper in bodegas_codigos:
            logger.warning(
                f"⚠️ Omitiendo distribución: '{tienda_codigo}' es una bodega, no una tienda. "
                f"Las Solicitudes de Transferencia solo se crean hacia tiendas, no hacia bodegas."
            )
            return None, True

        # ⭐ VALIDACIÓN 2: Validar que destino no sea la misma bodega origen
        if tienda_codigo_upper == bodega_origen_upper:
            logger.warning(
                f"⚠️ Omitiendo distribución: '{tienda_codigo}' es la misma bodega origen ({bodega_origen_upper}). "
                f"No se puede crear transferencia de {bodega_origen_upper} a {tienda_codigo}"
            )
            return None, True

        # ⭐ VALIDACIÓN 3: Validar que la tienda exista en SAP
        if tienda_codigo_upper not in tiendas_validas_en_sap:
            logger.warning(
                f"⚠️ Omitiendo distribución: La tienda '{tienda_codigo}' no existe en SAP. "
                f"No se puede crear Solicitud de Transferencia hacia una tienda inexistente."
            )
            return None, True

        # ⭐ VALIDACIÓN 4: Validar que la tienda pertenezca a la bodega origen
        bodega_tienda = self.obtener_bodega_de_tienda(tienda_codigo_upper)
        if bodega_tienda is None:
            logger.warning(
                f"⚠️ Omitiendo distribución: No se pudo determinar la bodega de la tienda '{tienda_codigo}'. "
                f"El código no coincide con ningún patrón conocido (TRL-*, TOUT-*, RG-*)."
            )
            return None, True

        if bodega_tienda != bodega_origen_upper:
            if (bodega_origen_upper, bodega_tienda) not in self.BODEGAS_TRASLADO_CRUZADO_PERMITIDO:
                logger.warning(
                    f"⚠️ Omitiendo distribución: La tienda '{tienda_codigo}' pertenece a la bodega '{bodega_tienda}', "
                    f"pero el pedido tiene origen '{bodega_origen_upper}'. "
                    f"No se puede crear transferencia de {bodega_origen_upper} a una tienda de {bodega_tienda}."
                )
                return None, True
            logger.info(
                f"↔️ Traslado cruzado entre CEDIs permitido (req. 1.6): {bodega_origen_upper} → "
                f"tienda '{tienda_codigo}' (bodega {bodega_tienda})"
            )

        # Convertir por tienda: cantidad_sap = cantidad_asignada × unidad_conversion (trazable)
        cantidad_sap_asignada = float(cantidad_asignada) * factor_conversion
        logger.debug(
            f"      {item_code_sap} → {tienda_codigo}: {cantidad_asignada} × {factor_conversion} = {cantidad_sap_asignada}"
        )

        # ⭐ Obtener código exacto de SAP (WhsCode) para usar en la ST
        codigo_exacto_sap = mapeo_codigo_exacto_sap.get(tienda_codigo_upper, tienda_codigo_upper)
        if codigo_exacto_sap != tienda_codigo_upper:
            logger.debug(
                f"📝 Código normalizado '{tienda_codigo_upper}' → código exacto SAP '{codigo_exacto_sap}'"
            )

        return {
            "pedido_detalle_id": pedido_detalle_id,
            "codigo_producto": codigo_producto,
            "item_code_sap": item_code_sap,
            "cantidad_asignada": cantidad_asignada,
            "cantidad_sap": cantidad_sap_asignada,
            "tienda_id": tienda_id,
            "tienda_codigo": tienda_codigo,
            "warehouse_code": codigo_exacto_sap,  # ⭐ Usar código exacto de SAP (WhsCode)
            "es_bodega": es_bodega
        }, False

    def _procesar_producto_distribucion(
        self,
        producto_dist: Dict[str, Any],
        mapa_procesamientos: Dict[str, Any],
        bodega_origen_upper: str,
        bodegas_codigos: set,
        tiendas_validas_en_sap: set,
        mapeo_codigo_exacto_sap: Dict[str, str],
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Procesa todas las distribuciones de tienda de un producto.

        Returns:
            (lista_de_entries, cantidad_omitidas)
        """
        pedido_detalle_id = producto_dist.get("pedido_detalle_id")
        if pedido_detalle_id is None:
            logger.warning(f"⚠️ producto_dist sin pedido_detalle_id: {producto_dist.get('codigo_producto')}")
            return [], 0

        procesamiento = mapa_procesamientos.get(pedido_detalle_id)

        if not procesamiento:
            logger.warning(f"⚠️ No hay procesamiento SAP para pedido_detalle_id: {pedido_detalle_id}")
            return [], 0

        item_code_sap = procesamiento.get("item_code_sap")
        unidad_conversion = procesamiento.get("unidad_conversion")

        if not item_code_sap:
            logger.warning(f"⚠️ Procesamiento incompleto para pedido_detalle_id: {pedido_detalle_id}")
            return [], 0

        # ⭐ Conversión por tienda (trazable): cantidad_sap = cantidad_asignada × unidad_conversion.
        # No se usa el total del producto ni bodegas; cada tienda se convierte de forma independiente.
        factor_conversion = float(unidad_conversion) if unidad_conversion is not None and float(unidad_conversion) > 0 else 1.0
        logger.debug(
            f"   Conversión por tienda: {item_code_sap} | unidad_conversion={factor_conversion} "
            f"(cada cantidad_asignada × {factor_conversion} → cantidad_sap)"
        )

        # ⭐ CORRECCIÓN: Filtrar solo distribuciones de TIENDAS (es_bodega=False)
        distribuciones_tiendas = [d for d in producto_dist.get("distribuciones", []) if not d.get("es_bodega", False)]
        if not distribuciones_tiendas:
            return [], 0

        if sum(d.get("cantidad_asignada", 0) for d in distribuciones_tiendas) == 0:
            return [], 0

        entries: List[Dict[str, Any]] = []
        omitidas = 0
        codigo_producto = producto_dist.get("codigo_producto")

        for dist in distribuciones_tiendas:
            entry, omitida = self._procesar_dist_tienda(
                dist, pedido_detalle_id, item_code_sap, factor_conversion,
                codigo_producto, bodega_origen_upper, bodegas_codigos,
                tiendas_validas_en_sap, mapeo_codigo_exacto_sap
            )
            if omitida:
                omitidas += 1
            elif entry:
                entries.append(entry)

        return entries, omitidas

    def _construir_distribucion_por_tienda(
        self,
        productos_distribucion: List[Dict[str, Any]],
        mapa_procesamientos: Dict[str, Any],
        bodega_origen: str,
        tiendas_validas_en_sap: set,
        mapeo_codigo_exacto_sap: Dict[str, str],
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], int]:
        """
        Construye el mapa {tienda_id: [productos]} filtrando bodegas y validando cada distribución.

        Returns:
            (distribucion_por_tienda, total_distribuciones_omitidas)
        """
        # ⭐ IMPORTANTE: Las Solicitudes de Transferencia se crean desde bodega origen hacia TIENDAS.
        # Se excluyen bodegas como destino para evitar ST de bodega a bodega.
        bodegas_codigos = {'OUT-CD', 'RG-CD', 'RL-CD'}
        bodega_origen_upper = bodega_origen.strip().upper()
        distribucion_por_tienda: Dict[str, List[Dict[str, Any]]] = {}
        distribuciones_omitidas = 0

        for producto_dist in productos_distribucion:
            entries, omitidas = self._procesar_producto_distribucion(
                producto_dist, mapa_procesamientos, bodega_origen_upper,
                bodegas_codigos, tiendas_validas_en_sap, mapeo_codigo_exacto_sap
            )
            distribuciones_omitidas += omitidas
            for entry in entries:
                distribucion_por_tienda.setdefault(entry["tienda_id"], []).append(entry)

        return distribucion_por_tienda, distribuciones_omitidas

    @staticmethod
    def _aplicar_filtro_tiendas_destino(
        distribucion_por_tienda: Dict[str, List[Dict[str, Any]]],
        tiendas_destino_filtro: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Filtra la distribución para incluir solo las tiendas en tiendas_destino_filtro.
        Útil para reintento parcial de ITRs fallidos.
        """
        codigos_objetivo = {str(c).strip().upper() for c in tiendas_destino_filtro if str(c).strip()}
        distribucion_filtrada: Dict[str, List[Dict[str, Any]]] = {}
        for tienda_id, productos in distribucion_por_tienda.items():
            tienda_codigo_raw = str(productos[0].get("tienda_codigo") or "") if productos else ""
            tienda_codigo_norm = tienda_codigo_raw.strip().upper()
            if tienda_codigo_norm in codigos_objetivo:
                distribucion_filtrada[tienda_id] = productos
        if not distribucion_filtrada:
            raise ValueError(
                "No se encontraron tiendas objetivo para reintento ST en la distribución confirmada actual."
            )
        return distribucion_filtrada

    def _resolver_jobs_encolados_pendientes(
        self, conn, oc_id: str, tiendas_destino_filtro: List[str]
    ) -> Tuple[Dict[str, Dict[str, Any]], set]:
        """
        Antes de reintentar, resuelve tiendas cuyo último intento quedó 'Encolada'
        (HTTP 202 del middleware): consulta GET /api/v1/jobs/{job_id} en vez de
        reenviar la creación a ciegas — el job original todavía puede completarse
        en segundo plano, y reenviar crearía una ITR duplicada en SAP.

        Returns:
            (itrs_adoptadas, tiendas_en_cola)
            itrs_adoptadas: {tienda_norm: {"doc_num", "doc_entry"}} — jobs
                COMPLETADO, se adoptan (mismo shape que _buscar_itrs_existentes_en_sap).
            tiendas_en_cola: tiendas (normalizadas) cuyo job sigue ENCOLADO/PROCESANDO;
                no se reintentan este ciclo.
            Tiendas cuyo job resultó ERROR (o ya no se pudo consultar) no aparecen en
            ninguno de los dos: quedan libres para un intento de creación normal.
        """
        st_repo = SolicitudTransferenciaRepository(conn)
        pendientes = st_repo.get_tiendas_encoladas_con_job_id(oc_id, tiendas_destino_filtro)
        adoptadas: Dict[str, Dict[str, Any]] = {}
        en_cola: set = set()
        for tienda_norm, job_id in pendientes.items():
            job = self.sap_client.get_job_status(job_id)
            if not job:
                continue
            status = str(job.get("status") or "").upper()
            if status == "COMPLETADO":
                resultado_job = job.get("result") or {}
                doc_entry = resultado_job.get("docEntry")
                doc_num = resultado_job.get("docNum")
                if doc_entry:
                    adoptadas[tienda_norm] = {"doc_num": doc_num, "doc_entry": doc_entry}
                    logger.info(
                        f"♻️ Job SAP encolado COMPLETADO para {tienda_norm}: "
                        f"ITR adoptada (DocEntry={doc_entry}, DocNum={doc_num})"
                    )
            elif status in ("ENCOLADO", "PROCESANDO"):
                en_cola.add(tienda_norm)
                logger.info(f"⏳ Job SAP aún {status} para {tienda_norm}: se omite este ciclo")
            # status == "ERROR" (o desconocido/no consultable): no hacer nada especial,
            # la tienda queda libre para un intento de creación normal.
        return adoptadas, en_cola

    def _buscar_itrs_existentes_en_sap(
        self, comentario_exacto: str, bodega_origen: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        Verificación preventiva de duplicados: consulta a SAP qué ITRs ya existen
        para este pedido/OC antes de reintentar crearlas.

        Cubre el caso en que SAP creó el ITR pero la confirmación se perdió
        (timeout, caída) y nuestra BD quedó en Error: sin esto, el reintento
        crearía un duplicado.

        Matching estricto (los tres a la vez) para evitar falsos positivos por
        substring (ej. "Pedido P-12.4" vs "Pedido P-12.48"):
        - Comments igual EXACTO al comentario que nosotros mismos construimos
        - FromWarehouse igual a la bodega origen
        - ToWarehouse se usa como clave del mapa retornado

        Returns:
            {to_warehouse_normalizado: {"doc_num": ..., "doc_entry": ...}}.
            Vacío si no hay coincidencias o si la consulta falla (no bloqueante:
            el caller sigue con la creación normal, que es el comportamiento actual).
        """
        try:
            itrs = self.sap_client.get_inventory_transfer_requests_by_comment(comentario_exacto)
        except Exception as e:
            logger.warning(f"⚠️ No se pudo verificar ITRs existentes en SAP (no bloqueante): {e}")
            return {}

        bodega_norm = bodega_origen.strip().upper()
        comentario_norm = comentario_exacto.strip()
        existentes: Dict[str, Dict[str, Any]] = {}
        for itr in itrs or []:
            if str(itr.get("comments") or "").strip() != comentario_norm:
                continue
            if str(itr.get("from_warehouse") or "").strip().upper() != bodega_norm:
                continue
            to_wh = str(itr.get("to_warehouse") or "").strip().upper()
            if to_wh and itr.get("doc_entry"):
                existentes[to_wh] = {
                    "doc_num": itr.get("doc_num"),
                    "doc_entry": itr.get("doc_entry"),
                }
        if existentes:
            logger.info(
                f"♻️ ITRs ya existentes en SAP detectadas (no se duplicarán): "
                f"{sorted(existentes.keys())}"
            )
        return existentes

    @staticmethod
    def _resultado_desde_itr_existente(
        tienda_id: str,
        tienda_codigo: str,
        tienda_nombre: Optional[str],
        itr_existente: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Resultado por tienda cuando el ITR ya existía en SAP (mismo shape que uno creado)."""
        return {
            "tienda_id": tienda_id,
            "tienda_codigo": tienda_codigo,
            "tienda_nombre": tienda_nombre,
            "success": True,
            "doc_entry": itr_existente.get("doc_entry"),
            "doc_num": itr_existente.get("doc_num"),
            "error": None,
            "recuperada": True,
        }

    def _enviar_itrs_a_sap(
        self,
        stock_transfers_json: List[Dict[str, Any]],
        distribucion_por_tienda: Dict[str, List[Dict[str, Any]]],
        bodega_origen: str,
        mapeo_nombre_tienda: Dict[str, str],
        result: Dict[str, Any],
        itrs_existentes: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        """Envía cada ITR a SAP con reintento y actualiza result con los resultados por tienda."""
        tiendas_list = list(distribucion_por_tienda.keys())
        itrs_existentes = itrs_existentes or {}
        for idx, stock_transfer_json in enumerate(stock_transfers_json):
            tienda_codigo = stock_transfer_json.get("ToWarehouse", "N/A")
            tienda_id = tiendas_list[idx]

            itr_existente = itrs_existentes.get(tienda_codigo.strip().upper())
            if itr_existente:
                tienda_nombre_rec = mapeo_nombre_tienda.get(tienda_codigo.strip().upper())
                result["resultados"].append(
                    self._resultado_desde_itr_existente(
                        tienda_id, tienda_codigo, tienda_nombre_rec, itr_existente
                    )
                )
                result["transferencias_creadas"] += 1
                logger.info(
                    f"♻️ ITR ya existía en SAP, no se duplicó: {bodega_origen} → {tienda_codigo} "
                    f"(DocEntry={itr_existente.get('doc_entry')}, DocNum={itr_existente.get('doc_num')})"
                )
                continue

            logger.debug(
                f"🔄 Enviando ITR {idx+1}/{len(stock_transfers_json)} a SAP: "
                f"{bodega_origen} → {tienda_codigo}..."
            )
            envio_result = self._enviar_itr_con_reintento(
                payload=stock_transfer_json,
                bodega_origen=bodega_origen,
                tienda_codigo=tienda_codigo,
            )
            sap_response = envio_result.get("response")
            tienda_codigo_upper = tienda_codigo.strip().upper() if tienda_codigo else ""
            tienda_nombre = mapeo_nombre_tienda.get(tienda_codigo_upper, None)
            resultado_tienda = {
                "tienda_id": tienda_id,
                "tienda_codigo": tienda_codigo,
                "tienda_nombre": tienda_nombre,  # ⭐ Incluir nombre de la tienda
                "success": False,
                "doc_entry": None,
                "doc_num": None,
                "error": None
            }
            if envio_result.get("success") and isinstance(sap_response, dict):
                # ✅ SOLO AQUÍ se considera que el ITR fue creado realmente en SAP
                resultado_tienda["success"] = True
                resultado_tienda["doc_entry"] = sap_response.get("doc_entry")
                resultado_tienda["doc_num"] = sap_response.get("doc_num")
                resultado_tienda["attempts"] = envio_result.get("attempts")
                result["transferencias_creadas"] += 1
                logger.info(
                    f"✅ Inventory Transfer Request CREADO en SAP: {bodega_origen} → {tienda_codigo} "
                    f"(DocEntry={resultado_tienda['doc_entry']}, DocNum={resultado_tienda['doc_num']})"
                )
            elif isinstance(sap_response, dict) and sap_response.get("queued"):
                # ⏳ SAP saturado: el middleware encoló la petición (HTTP 202). No es un
                # error definitivo — se guarda el job_id para consultar su estado real
                # antes de reintentar (evita crear una ITR duplicada).
                resultado_tienda["queued"] = True
                resultado_tienda["job_id"] = sap_response.get("job_id")
                resultado_tienda["error"] = envio_result.get("error") or sap_response.get("error")
                resultado_tienda["attempts"] = envio_result.get("attempts")
                result["transferencias_encoladas"] += 1
                logger.info(
                    f"⏳ Inventory Transfer Request ENCOLADA en SAP (no es error definitivo): "
                    f"{bodega_origen} → {tienda_codigo} (jobId={resultado_tienda['job_id']})"
                )
            else:
                error_msg = envio_result.get("error") or "No se recibió respuesta de SAP"
                resultado_tienda["error"] = error_msg
                resultado_tienda["attempts"] = envio_result.get("attempts")
                result["transferencias_errores"] += 1
                logger.warning(
                    f"⚠️ Inventory Transfer Request NO creado tras "
                    f"{envio_result.get('attempts', self.RETRY_MAX_ATTEMPTS)} intento(s): "
                    f"{bodega_origen} → {tienda_codigo}: {error_msg}"
                )
            result["resultados"].append(resultado_tienda)

    @staticmethod
    def _construir_errores_detalle(
        resultados: List[Dict[str, Any]],
        bodega_origen: str
    ) -> List[Dict[str, Any]]:
        """Extrae los errores detallados de los resultados de ITRs fallidos."""
        errores_detalle = []
        for r in resultados:
            if not r["success"] and r.get("error"):
                tienda_cod = r.get("tienda_codigo", "N/A")
                tienda_nom = r.get("tienda_nombre")
                destino = f"{tienda_cod} ({tienda_nom})" if tienda_nom else tienda_cod
                errores_detalle.append({
                    "tienda_codigo": tienda_cod,
                    "tienda_nombre": tienda_nom,
                    "error": r["error"],
                    "mensaje": f"{bodega_origen} → {destino}: {r['error']}"
                })
        return errores_detalle

    @staticmethod
    def _registrar_resultado_final(
        result: Dict[str, Any],
        errores_detalle: List[Dict[str, Any]]
    ) -> None:
        """Determina el éxito global y registra el resultado en result con mensajes para la UI."""
        result["success"] = result["transferencias_creadas"] > 0
        if result["success"]:
            logger.info(
                f"✅ Inventory Transfer Requests creados en SAP: {result['transferencias_creadas']}/{result['total_tiendas']} "
                f"(DocEntry confirmado para cada uno)"
            )
            if result["transferencias_errores"] > 0:
                logger.warning(
                    f"⚠️ {result['transferencias_errores']} Inventory Transfer Request(s) NO se pudieron crear en SAP"
                )
                # Éxito parcial: incluir warnings para la UI
                result["warnings"] = [e["mensaje"] for e in errores_detalle]
        else:
            logger.warning(
                f"⚠️ No se creó ningún Inventory Transfer Request en SAP "
                f"(0/{result['total_tiendas']} exitosos)"
            )
            # ⭐ FIX: Establecer result["error"] con detalle real
            if errores_detalle:
                result["error"] = (
                    f"Solicitudes de Transferencia fallidas "
                    f"({result['transferencias_errores']}/{result['total_tiendas']}): "
                    + "; ".join(e["mensaje"] for e in errores_detalle)
                )
                result["errores_detalle"] = errores_detalle
            else:
                result["error"] = (
                    f"No se creó ninguna Solicitud de Transferencia en SAP "
                    f"(0/{result['total_tiendas']} exitosos)"
                )

    def crear_solicitudes_transferencia_desde_pedido(
        self,
        pedido_id: str,
        oc_doc_num: Optional[int] = None,
        oc_id: Optional[str] = None,
        bodega_origen: Optional[str] = None,
        usuario_id: Optional[str] = None,
        serie: Optional[int] = None,
        tiendas_destino_filtro: Optional[List[str]] = None,
        verificar_ya_existente_en_sap: bool = False,
    ) -> Dict[str, Any]:
        """
        Crea Solicitudes de Transferencia (Inventory Transfer Requests) en SAP desde la distribución confirmada de un pedido.

        ⚠️ IMPORTANTE: Este método crea Inventory Transfer Requests (POST /InventoryTransferRequests),
        NO Stock Transfer Orders. Las Inventory Transfer Requests son solicitudes que NO mueven stock,
        solo crean una solicitud que debe ser procesada posteriormente.

        ⭐ IMPORTANTE: Las Solicitudes de Transferencia se crean desde bodega origen hacia TIENDAS.
        - Origen: Bodega (prioridad: bodega_origen proporcionada > origen_traslado del pedido > "01")
          - Si se proporciona bodega_origen (ej: desde codigo_bodega de la OC), se usa esa
          - Si no, se usa origen_traslado del pedido
          - Si ninguno está disponible, se usa "01" como default
        - Destino: TIENDAS (es_bodega=False), NO bodegas
        - Las bodegas (OUT-CD, RG-CD, RL-CD) se excluyen como destino para evitar transferencias de bodega a bodega
        - Cada bodega tiene sus propias tiendas, EXCEPTO el traslado cruzado permitido por
          el req. 1.6 entre RL-CD (CEDI Roland) y RG-CD (Regions) en ambos sentidos
          (ver BODEGAS_TRASLADO_CRUZADO_PERMITIDO)

        Proceso:
        1. Obtiene la distribución confirmada del pedido
        2. Obtiene los datos de procesamiento SAP (item_code_sap, unidad_conversion por producto)
        3. Valida que todas las tiendas destino existan en SAP (previene errores de "No matching records found")
        4. Filtra solo distribuciones de TIENDAS (es_bodega=False); las bodegas no se redistribuyen
        5. Convierte cantidades por tienda: cantidad_sap = cantidad_asignada × unidad_conversion (trazable, sin usar totales ni bodega)
        6. Excluye bodegas como destino (evita ST de bodega a bodega)
        7. Valida que destino no sea la misma bodega origen
        8. Valida que cada tienda pertenezca a la bodega origen (basado en prefijos: TRL-→RL-CD, TOUT-→OUT-CD, RG-→RG-CD),
           salvo el traslado cruzado RL-CD↔RG-CD permitido por el req. 1.6
        9. Agrupa por tienda y crea un Inventory Transfer Request por tienda en SAP (POST /InventoryTransferRequests)
        10. Registra los resultados

        Args:
            pedido_id: UUID del pedido
            oc_doc_num: Número de OC de SAP (DocNum) relacionada (opcional)
            bodega_origen: Código de bodega origen (si None, usa origen_traslado del pedido)
                          ⭐ Recomendado: pasar codigo_bodega de la OC para consistencia
            usuario_id: ID del usuario que genera las transferencias
            tiendas_destino_filtro: Lista opcional de códigos de tienda destino a procesar.
                                  Si se envía, solo se intentan esas tiendas (útil para reintento parcial).
            verificar_ya_existente_en_sap: Si True, antes de crear consulta a SAP qué ITRs ya
                                  existen para este pedido/OC (verificación preventiva de duplicados);
                                  las encontradas se adoptan (doc_num/doc_entry) en vez de recrearse.
                                  Pensado para reintentos; el envío original no lo necesita.

        Returns:
            Diccionario con el resultado:
            {
                "success": True/False,
                "pedido_id": "...",
                "total_tiendas": 3,
                "transferencias_creadas": 3,
                "transferencias_errores": 0,
                "resultados": [
                    {
                        "tienda_id": "...",
                        "tienda_codigo": "TRL-QSN",
                        "success": True,
                        "doc_entry": 123,
                        "doc_num": 456,
                        "error": None
                    }
                ]
            }
        """
        result = {
            "success": False,
            "pedido_id": pedido_id,
            "total_tiendas": 0,
            "transferencias_creadas": 0,
            "transferencias_errores": 0,
            "transferencias_encoladas": 0,
            "resultados": []
        }

        try:
            with get_db_connection_context() as conn:
                pedido_repo = PedidoRepository(conn)
                dist_repo = DistribucionConfirmadaRepository(conn)
                sap_proc_repo = PedidoSAPProcesamientoRepository(conn)

                pedido_cabecera, productos_distribucion, mapa_procesamientos = self._obtener_datos_pedido(
                    pedido_repo, dist_repo, sap_proc_repo, pedido_id
                )
                serie = self._resolver_serie(pedido_cabecera, serie)
                bodega_origen = self._resolver_bodega_origen(bodega_origen, pedido_cabecera)

                codigos_tiendas_unicos = self._recopilar_codigos_tiendas(productos_distribucion)
                tiendas_validas_en_sap, mapeo_codigo_exacto_sap, mapeo_nombre_tienda = \
                    self._validar_tiendas_en_sap(codigos_tiendas_unicos)

                distribucion_por_tienda, distribuciones_omitidas = self._construir_distribucion_por_tienda(
                    productos_distribucion, mapa_procesamientos, bodega_origen,
                    tiendas_validas_en_sap, mapeo_codigo_exacto_sap
                )

                if distribuciones_omitidas > 0:
                    logger.info(
                        f"ℹ️ Se omitieron {distribuciones_omitidas} distribución(es) "
                        f"(bodegas o mismo origen que {bodega_origen})"
                    )

                if not distribucion_por_tienda:
                    raise SolicitudTransferenciaNoAplicaError(
                        "No hay distribución válida por tienda para crear transferencias. "
                        "Las Solicitudes de Transferencia se crean desde bodega origen hacia tiendas, no hacia bodegas."
                    )

                # Antes de reintentar, resolver tiendas cuyo último intento quedó
                # 'Encolada' (HTTP 202): consultar el job real en vez de reenviar a
                # ciegas (evita ITR duplicada si el job original sigue en curso).
                itrs_adoptadas_por_job: Dict[str, Dict[str, Any]] = {}
                if verificar_ya_existente_en_sap and oc_id and tiendas_destino_filtro:
                    itrs_adoptadas_por_job, tiendas_en_cola = self._resolver_jobs_encolados_pendientes(
                        conn, oc_id, tiendas_destino_filtro
                    )
                    if tiendas_en_cola:
                        tiendas_destino_filtro = [
                            t for t in tiendas_destino_filtro
                            if t.strip().upper() not in tiendas_en_cola
                        ]
                        logger.info(
                            f"⏳ {len(tiendas_en_cola)} tienda(s) con job SAP aún en cola, "
                            f"se omiten este ciclo (no se reenvían): {sorted(tiendas_en_cola)}"
                        )
                        if not tiendas_destino_filtro:
                            result["success"] = True
                            result["total_tiendas"] = 0
                            result["tiendas_en_cola"] = sorted(tiendas_en_cola)
                            logger.info(
                                "⏳ Todas las tiendas objetivo del reintento siguen con job SAP "
                                "en cola; nada que hacer este ciclo."
                            )
                            return result

                # Reintento parcial opcional: procesar solo tiendas destino indicadas.
                if tiendas_destino_filtro:
                    distribucion_por_tienda = self._aplicar_filtro_tiendas_destino(
                        distribucion_por_tienda, tiendas_destino_filtro
                    )
                    logger.info(
                        f"🔁 Reintento parcial ST activado: {len(distribucion_por_tienda)} tienda(s) objetivo"
                    )

                result["total_tiendas"] = len(distribucion_por_tienda)
                logger.info(
                    f"📦 Creando {result['total_tiendas']} Solicitud(es) de Transferencia para "
                    f"{len(distribucion_por_tienda)} tienda(s) desde bodega {bodega_origen}..."
                )

                # 6. Convertir a formato SAP usando mapper
                stock_transfers_json = SAPStockTransferMapper.to_sap_stock_transfer(
                    pedido_data=pedido_cabecera,
                    distribucion_por_tienda=distribucion_por_tienda,
                    bodega_origen=bodega_origen,
                    oc_doc_num=oc_doc_num,
                    usuario_id=usuario_id,
                    pedido_id=pedido_id,
                    serie=serie
                )

                # ⭐ VALIDACIÓN MÍNIMA PARA ITR: Solo validar formato básico.
                # SAP NO requiere validación de stock ni de artículos habilitados en bodega origen para ITR.
                # Las ITR son solo solicitudes, no mueven stock.
                try:
                    self._validate_itr_minimal(stock_transfers_json)
                except ValueError as e:
                    # Error de formato básico - esto SÍ debe bloquear el flujo
                    error_msg = str(e)
                    logger.error(f"❌ {error_msg}")
                    result["error"] = error_msg
                    result["success"] = False
                    result["error_type"] = "validacion_formato"
                    self._persistir_y_guardar_json_solicitudes_transferencia(
                        conn=conn, result=result, payloads_sap=stock_transfers_json,
                        oc_id=oc_id, pedido_id=pedido_id, bodega_origen=bodega_origen,
                        oc_doc_num=oc_doc_num,
                    )
                    return result

                # Verificación preventiva de duplicados (solo reintentos): si SAP creó
                # el ITR pero la confirmación se perdió, adoptarlo en vez de recrearlo.
                itrs_existentes = None
                if verificar_ya_existente_en_sap:
                    comentario_esperado = SAPStockTransferMapper.build_comentario_transferencia(
                        oc_doc_num, pedido_cabecera.get("numero_pedido", "N/A")
                    )
                    itrs_existentes = self._buscar_itrs_existentes_en_sap(
                        comentario_esperado, bodega_origen
                    )
                    if itrs_adoptadas_por_job:
                        itrs_existentes.update(itrs_adoptadas_por_job)

                # 7. Crear cada Inventory Transfer Request en SAP (POST /InventoryTransferRequests)
                logger.info(
                    f"📤 Enviando {len(stock_transfers_json)} Inventory Transfer Request(s) a SAP..."
                )
                self._enviar_itrs_a_sap(
                    stock_transfers_json, distribucion_por_tienda, bodega_origen,
                    mapeo_nombre_tienda, result, itrs_existentes=itrs_existentes
                )

                # 8. Determinar éxito general y loguear resultado REAL
                errores_detalle = self._construir_errores_detalle(result["resultados"], bodega_origen)
                self._registrar_resultado_final(result, errores_detalle)

                self._persistir_y_guardar_json_solicitudes_transferencia(
                    conn=conn, result=result, payloads_sap=stock_transfers_json,
                    oc_id=oc_id, pedido_id=pedido_id, bodega_origen=bodega_origen,
                    oc_doc_num=oc_doc_num,
                )
                return result

        except Exception as e:
            logger.error(f"❌ Error al crear Solicitudes de Transferencia: {e}", exc_info=True)
            result["error"] = str(e)
            return result

    @staticmethod
    def _resolver_tiendas_objetivo(
        st_repo: SolicitudTransferenciaRepository, oc_id: str
    ) -> Tuple[List[str], str]:
        """Tiendas pendientes de reintento (idempotente) y de dónde salió la lista."""
        tiendas_objetivo = st_repo.get_tiendas_pendientes_reintento_st(oc_id)
        if tiendas_objetivo:
            return tiendas_objetivo, "detalle"
        tiendas_fallback = st_repo.get_tiendas_fallidas_desde_resultado_json_fallback(oc_id)
        return tiendas_fallback, ("resultado_json" if tiendas_fallback else "ninguno")

    @staticmethod
    def _parse_oc_doc_num(numero_oc_sap_raw: Any) -> Optional[int]:
        if numero_oc_sap_raw is None:
            return None
        try:
            return int(numero_oc_sap_raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _obtener_numero_pedido(pedido_id: str, conn: Any) -> Optional[str]:
        """Número de pedido legible para notificaciones; None si falla (no bloqueante)."""
        try:
            pedido_data = PedidoRepository(conn).get_pedido_completo(pedido_id)
            if pedido_data and pedido_data.get("cabecera"):
                return pedido_data["cabecera"].get("numero_pedido")
        except Exception:
            pass
        return None

    @staticmethod
    def _notificar_st_creadas_en_reintento(
        oc_id: str,
        oc_cabecera: Dict[str, Any],
        resultado_st: Dict[str, Any],
        pedido_numero: Optional[str],
        origen: str,
    ) -> None:
        """
        Notifica a El Rayo (+ MABEL TRADING) los códigos de ST recién creados en un reintento.

        Mismo correo que el envío original (send_oc_ready_for_dispatch_notification):
        el flujo inicial solo lo dispara una vez al crear la ODC, así que sin esto,
        las ITR que se crean recién en un reintento (manual o automático) nunca
        llegaban a El Rayo con sus códigos.
        """
        from src.utils.email_notifier import send_oc_ready_for_dispatch_notification

        try:
            enviado = send_oc_ready_for_dispatch_notification(
                oc_cabecera=oc_cabecera,
                doc_num=oc_cabecera.get("numero_oc_sap"),
                doc_entry=oc_cabecera.get("doc_entry"),
                solicitudes_transferencia=resultado_st,
                pedido_numero=pedido_numero,
            )
            if enviado:
                logger.info(
                    f"📧 Notificación a El Rayo enviada tras reintento ST ({origen}) para OC {oc_id[:8]}..."
                )
            else:
                logger.warning(
                    f"⚠️ No se pudo notificar a El Rayo tras reintento ST ({origen}) para OC {oc_id[:8]}..."
                )
        except Exception as e:
            logger.warning(f"⚠️ Error al notificar a El Rayo tras reintento ST ({origen}): {e}")

    def reintentar_pendientes(
        self,
        oc_id: str,
        usuario_id: str,
        origen: str = "manual",
    ) -> Dict[str, Any]:
        """
        Reintenta únicamente las Solicitudes de Transferencia (ITR) pendientes de una OC ya ENVIADA.

        Compartido por el endpoint manual (POST /ordenes-compra/{oc_id}/reintentar-st) y por
        la reconciliación automática (Celery). Idempotente: solo reintenta tiendas sin ITR ya
        creado en algún intento previo (ver SolicitudTransferenciaRepository.get_tiendas_pendientes_reintento_st).

        Args:
            oc_id: UUID de la orden de compra.
            usuario_id: Identificador de quién dispara el reintento (usuario o "celery-beat").
            origen: Solo para logging ("manual" | "automatico").

        Returns:
            {"status": ..., "message": ..., "oc_id": ..., ...} — ver cada rama para el detalle.
            status: "no_encontrada" | "estado_invalido" | "sin_pedido" | "no_pendientes" | "success" | "partial" | "en_cola"
            ("en_cola": todas las tiendas objetivo siguen con un job SAP en curso — HTTP 202 —,
            no se reenvió nada este ciclo para evitar ITR duplicadas.)
        """
        with get_db_connection_context() as conn:
            oc_repo = OrdenCompraRepository(conn)
            st_repo = SolicitudTransferenciaRepository(conn)

            oc_cabecera = oc_repo.get_existing_cabecera(oc_id)
            if not oc_cabecera:
                return {"status": "no_encontrada", "message": "Orden de compra no encontrada", "oc_id": oc_id}

            estado = str(oc_cabecera.get("estado") or "").strip().upper()
            if estado != "ENVIADA":
                return {
                    "status": "estado_invalido",
                    "message": f"Solo se puede reintentar ST cuando la ODC está ENVIADA (estado actual: {estado or 'N/A'})",
                    "oc_id": oc_id,
                }

            tiendas_objetivo, origen_lista = self._resolver_tiendas_objetivo(st_repo, oc_id)
            if not tiendas_objetivo:
                return {
                    "status": "no_pendientes",
                    "message": "No hay Solicitudes de Transferencia pendientes para reintentar "
                               "(todas las tiendas ya tienen ITR o no hay registro de fallas).",
                    "oc_id": oc_id,
                    "reintentadas": 0,
                    "origen_lista_tiendas": origen_lista,
                }

            pedido_id = oc_cabecera.get("pedido_id")
            if not pedido_id:
                return {
                    "status": "sin_pedido",
                    "message": "La ODC no tiene pedido_id asociado para reconstruir ST.",
                    "oc_id": oc_id,
                }

            pedido_numero = self._obtener_numero_pedido(pedido_id, conn)

        logger.info(
            f"🔁 Reintento ST ({origen}) para OC {oc_id[:8]}...: "
            f"{len(tiendas_objetivo)} tienda(s) objetivo"
        )
        resultado_st = self.crear_solicitudes_transferencia_desde_pedido(
            pedido_id=str(pedido_id),
            oc_doc_num=self._parse_oc_doc_num(oc_cabecera.get("numero_oc_sap")),
            oc_id=oc_id,
            bodega_origen=oc_cabecera.get("codigo_bodega"),
            usuario_id=usuario_id,
            tiendas_destino_filtro=tiendas_objetivo,
            verificar_ya_existente_en_sap=True,
        )

        if resultado_st.get("transferencias_creadas", 0) > 0:
            self._notificar_st_creadas_en_reintento(oc_id, oc_cabecera, resultado_st, pedido_numero, origen)

        if resultado_st.get("tiendas_en_cola"):
            status = "en_cola"
            message = (
                "Las tiendas objetivo siguen con una Solicitud de Transferencia en "
                "cola en SAP (saturación temporal); no se reenvió nada para evitar "
                "duplicados. Intenta de nuevo en unos minutos."
            )
        else:
            status = "success" if resultado_st.get("success") else "partial"
            message = "Reintento ST ejecutado."

        return {
            "status": status,
            "message": message,
            "oc_id": oc_id,
            "origen_lista_tiendas": origen_lista,
            "tiendas_objetivo": tiendas_objetivo,
            "tiendas_count": len(tiendas_objetivo),
            "resultado_st": resultado_st,
        }
