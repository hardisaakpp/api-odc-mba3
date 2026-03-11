"""
Servicio para crear Solicitudes de Transferencia (Inventory Transfer Requests) en SAP.
FASE 5: Generación de Solicitudes de Transferencia desde distribución confirmada por tienda.

⚠️ IMPORTANTE: Este servicio crea Inventory Transfer Requests (POST /InventoryTransferRequests),
NO Stock Transfer Orders. Las Inventory Transfer Requests son solicitudes que NO mueven stock,
solo crean una solicitud que debe ser procesada posteriormente.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from collections import defaultdict

from src.config import PROJECT_ROOT
from ..connection import get_db_connection_context
from ..repositories.pedido_repository import PedidoRepository
from ..repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
from ..repositories.orden_compra_repository import OrdenCompraRepository
from ..repositories.pedido_sap_procesamiento_repository import PedidoSAPProcesamientoRepository
from ..repositories.solicitud_transferencia_repository import SolicitudTransferenciaRepository
from ..clients.sap_service_layer_client import SAPServiceLayerClient
from ..mappers.sap_stock_transfer_mapper import SAPStockTransferMapper
from ..services.bodega_sap_service import BodegaSAPService
from src.exceptions import SAPDataMasterError

logger = logging.getLogger(__name__)


class StockTransferService:
    """Servicio para crear Solicitudes de Transferencia en SAP."""
    
    def __init__(self):
        """Inicializa el servicio."""
        self.sap_client = SAPServiceLayerClient()
    
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
            lines = itr.get("StockTransferLines", [])
            
            # Validar FromWarehouse != ToWarehouse
            if not from_wh or not to_wh:
                raise ValueError(
                    f"ITR {idx+1}: FromWarehouse y ToWarehouse son requeridos"
                )
            
            if from_wh.upper() == to_wh.upper():
                raise ValueError(
                    f"ITR {idx+1}: FromWarehouse ({from_wh}) no puede ser igual a ToWarehouse ({to_wh})"
                )
            
            # Validar que haya líneas y que todas tengan Quantity > 0
            if not lines:
                raise ValueError(
                    f"ITR {idx+1}: Debe tener al menos una línea en StockTransferLines"
                )
            
            for line_idx, line in enumerate(lines):
                item_code = line.get("ItemCode", "").strip()
                quantity = float(line.get("Quantity", 0))
                
                if not item_code:
                    raise ValueError(
                        f"ITR {idx+1}, línea {line_idx+1}: ItemCode es requerido"
                    )
                
                if quantity <= 0:
                    raise ValueError(
                        f"ITR {idx+1}, línea {line_idx+1}: Quantity debe ser mayor que 0 (actual: {quantity})"
                    )
        
        logger.info(
            f"✅ Validación mínima ITR: {len(stock_transfers_json)} documento(s) con formato correcto"
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
        # Recopilar todos los item_code_sap únicos
        items_unicos = set()
        for tienda_id, productos in distribucion_por_tienda.items():
            for producto in productos:
                item_code_sap = producto.get("item_code_sap")
                if item_code_sap:
                    items_unicos.add(item_code_sap)
        
        if not items_unicos:
            logger.warning("⚠️ No hay artículos para validar habilitación en bodega origen")
            return
        
        logger.info(
            f"🔍 Validando que {len(items_unicos)} artículo(s) estén habilitados en bodega origen {bodega_origen}..."
        )
        
        # Validar cada artículo
        articulos_no_habilitados = []
        
        for item_code in items_unicos:
            try:
                # Intentar obtener stock - si lanza SAPDataMasterError, el artículo no está habilitado
                stock_info = self.sap_client.get_stock_by_warehouse(item_code, bodega_origen)
                
                # Si stock_info es None, es un error de conexión (no debería pasar)
                if stock_info is None:
                    # ⚠️ WARNING funcional: problema de conexión, no bloqueante para validación preventiva
                    logger.warning(
                        f"⚠️ No se pudo verificar habilitación de {item_code} en {bodega_origen} "
                        f"(error de conexión). Se continuará con la validación."
                    )
                    continue
                
                # Si llegamos aquí, el artículo SÍ está habilitado (no lanzó excepción)
                logger.debug(f"✅ {item_code} habilitado en {bodega_origen}")
                
            except SAPDataMasterError as e:
                # El artículo NO está habilitado en la bodega origen
                articulos_no_habilitados.append({
                    "item_code": item_code,
                    "error_type": e.error_type,
                    "available_warehouses": e.available_warehouses
                })
                logger.warning(
                    f"⚠️ {item_code} NO habilitado en bodega origen {bodega_origen}"
                )
        
        # Si hay artículos no habilitados, lanzar error preventivo
        if articulos_no_habilitados:
            items_list = [a["item_code"] for a in articulos_no_habilitados]
            
            # Construir mensaje claro para el negocio
            if len(articulos_no_habilitados) == 1:
                primer_error = articulos_no_habilitados[0]
                warehouses_str = ", ".join(primer_error["available_warehouses"]) if primer_error["available_warehouses"] else "NINGUNA"
                mensaje = (
                    f"El artículo {items_list[0]} no está habilitado en la bodega origen {bodega_origen} en SAP. "
                    f"Bodegas donde SÍ está habilitado: {warehouses_str}. "
                    f"Contacte a logística o maestros de artículos para habilitar el artículo en la bodega {bodega_origen}."
                )
            else:
                mensaje = (
                    f"{len(articulos_no_habilitados)} artículos no están habilitados en la bodega origen {bodega_origen} en SAP. "
                    f"Artículos: {', '.join(items_list[:5])}"
                    f"{' y ' + str(len(items_list) - 5) + ' más' if len(items_list) > 5 else ''}. "
                    f"Contacte a logística o maestros de artículos para habilitar estos artículos en la bodega {bodega_origen}."
                )
            
            logger.error(
                f"❌ VALIDACIÓN PREVENTIVA: {len(articulos_no_habilitados)} artículo(s) no habilitados en bodega origen {bodega_origen}: "
                f"{', '.join(items_list)}"
            )
            
            # Lanzar excepción con el primer artículo
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
    def obtener_bodega_de_tienda(tienda_codigo: str) -> Optional[str]:
        """
        Determina a qué bodega pertenece una tienda basándose en el prefijo de su código.
        
        Reglas de mapeo:
        - TRL-* (excepto TRL-RG*) → RL-CD (ROLAND)
        - TOUT-* → OUT-CD (DESCUENTON)
        - RG-* o TRL-RG* → RG-CD (REGIONS)
        
        Args:
            tienda_codigo: Código de la tienda (ej: "TRL-QSN", "TOUT-BMB", "RG-INT")
        
        Returns:
            Código de bodega (OUT-CD, RG-CD, RL-CD) o None si no se puede determinar
        """
        if not tienda_codigo:
            return None
        
        codigo_upper = tienda_codigo.strip().upper()
        
        # REGIONS: RG-* o TRL-RG*
        if codigo_upper.startswith("RG-") or codigo_upper.startswith("TRL-RG"):
            return "RG-CD"
        
        # DESCUENTON: TOUT-*
        if codigo_upper.startswith("TOUT-"):
            return "OUT-CD"
        
        # ROLAND: TRL-* (resto)
        if codigo_upper.startswith("TRL-"):
            return "RL-CD"
        
        # Si no coincide con ningún patrón, retornar None
        return None
    
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
        # 1. Agrupar cantidades requeridas por ItemCode
        total_required = defaultdict(float)
        
        for st in stock_transfers_json:
            lines = st.get("StockTransferLines", [])
            for line in lines:
                item_code = line.get("ItemCode")
                quantity = float(line.get("Quantity", 0))
                if item_code and quantity > 0:
                    total_required[item_code] += quantity
        
        if not total_required:
            logger.warning("⚠️ No hay productos para validar stock")
            return
        
        logger.info(
            f"🔍 Validando stock total en {source_warehouse} para {len(total_required)} producto(s)..."
        )
        
        # 2. Consultar stock disponible en SAP para cada producto
        productos_insuficientes = []
        productos_error_datos_maestros = []  # Errores de configuración, NO stock insuficiente
        
        for item_code, required_qty in total_required.items():
            try:
                stock_info = self.sap_client.get_stock_by_warehouse(item_code, source_warehouse)
            except SAPDataMasterError as e:
                # ❌ CORTAR FLUJO: Error de datos maestros - NO continuar
                productos_error_datos_maestros.append({
                    "item_code": e.item_code,
                    "error_type": e.error_type,
                    "available_warehouses": e.available_warehouses,
                    "required_warehouse": e.warehouse_code
                })
                continue  # No agregar a productos_insuficientes, es otro tipo de error
            
            if stock_info is None:
                # Error al consultar - esto NO debería pasar si SAPDataMasterError se lanza correctamente
                # Si llegamos aquí, es un error de conexión o respuesta inesperada
                # ⚠️ WARNING funcional: problema de conexión, no de datos maestros
                logger.warning(
                    f"⚠️ No se pudo consultar stock de {item_code} en {source_warehouse}. "
                    f"Error de conexión o respuesta inesperada de SAP. "
                    f"NO se puede validar stock - ABORTANDO validación."
                )
                # ❌ HARD STOP: Sin información de stock, NO podemos crear STs
                # Mensaje claro para el negocio
                raise ValueError(
                    f"El artículo {item_code} no está asociado a la bodega {source_warehouse} en SAP, "
                    f"o hay un problema de conexión con SAP. "
                    f"Contacte a logística o maestros de artículos para verificar la configuración del artículo en SAP."
                )
            
            available = stock_info.get("InStock", 0.0)
            uom_code = stock_info.get("UomCode")
            
            # ⭐ VALIDACIÓN CRÍTICA: Si UomCode es NULL, SAP solo conoce unidad base
            # La conversión (ej: X12) existe solo en lógica externa, por lo que debemos
            # validar que el stock en unidades base alcance para la cantidad ya convertida
            if uom_code is None:
                logger.debug(
                    f"ℹ️ {item_code}: UomCode=NULL en SAP. "
                    f"Validando stock en unidades base (InStock={available}) vs cantidad convertida ({required_qty})"
                )
                # Si UomCode es NULL, el stock está en unidades base y debemos comparar
                # directamente con la cantidad requerida (que ya está convertida a unidades SAP)
                if available < required_qty:
                    productos_insuficientes.append({
                        "item_code": item_code,
                        "disponible": available,
                        "requerido": required_qty,
                        "faltante": required_qty - available,
                        "uom_code": None,
                        "nota": "UomCode=NULL: validación en unidades base"
                    })
                    logger.error(
                        f"❌ Stock insuficiente REAL: {item_code} en {source_warehouse}. "
                        f"Disponible (unidades base): {available}, Requerido (convertido): {required_qty}, "
                        f"Faltante: {required_qty - available}"
                    )
            else:
                # UomCode existe, validación normal
                if available < required_qty:
                    productos_insuficientes.append({
                        "item_code": item_code,
                        "disponible": available,
                        "requerido": required_qty,
                        "faltante": required_qty - available,
                        "uom_code": uom_code
                    })
                    logger.error(
                        f"❌ Stock insuficiente REAL: {item_code} en {source_warehouse}. "
                        f"Disponible: {available}, Requerido: {required_qty}, Faltante: {required_qty - available} "
                        f"(UomCode={uom_code})"
                    )
        
        # 3. Manejar errores: CORTAR FLUJO inmediatamente si hay errores de datos maestros
        if productos_error_datos_maestros:
            # ❌ CORTAR FLUJO: Errores de datos maestros - lanzar excepción de dominio
            items_list = [p['item_code'] for p in productos_error_datos_maestros]
            
            # ⚠️ WARNING funcional: ItemWarehouseInfoCollection vacío es esperado para algunos tipos de artículos
            # pero impide validar stock, por lo que abortamos la creación de ITRs
            logger.warning(
                f"⚠️ VALIDACIÓN DE STOCK ABORTADA: {len(productos_error_datos_maestros)} artículo(s) "
                f"sin información de bodega {source_warehouse} en SAP (ItemWarehouseInfoCollection vacío). "
                f"Artículos: {', '.join(items_list)}. "
                f"NO se pueden crear Inventory Transfer Requests sin validación de stock."
            )
            
            # Lanzar excepción con el primer artículo (todos tienen el mismo problema)
            primer_error = productos_error_datos_maestros[0]
            
            # Mensaje claro para el negocio
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
        
        # 4. Stock insuficiente real (solo si no hay errores de datos maestros)
        if productos_insuficientes:
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
        
        # ✅ Solo loguear éxito si REALMENTE se validó TODO correctamente
        # (no se lanzó ninguna excepción, no hay errores de datos maestros, y todos los productos tienen stock)
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

    def crear_solicitudes_transferencia_desde_pedido(
        self,
        pedido_id: str,
        oc_doc_num: Optional[int] = None,
        oc_id: Optional[str] = None,
        bodega_origen: Optional[str] = None,
        usuario_id: Optional[str] = None,
        serie: Optional[int] = None
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
        - Cada bodega tiene sus propias tiendas
        
        Proceso:
        1. Obtiene la distribución confirmada del pedido
        2. Obtiene los datos de procesamiento SAP (item_code_sap, unidad_conversion por producto)
        3. Valida que todas las tiendas destino existan en SAP (previene errores de "No matching records found")
        4. Filtra solo distribuciones de TIENDAS (es_bodega=False); las bodegas no se redistribuyen
        5. Convierte cantidades por tienda: cantidad_sap = cantidad_asignada × unidad_conversion (trazable, sin usar totales ni bodega)
        6. Excluye bodegas como destino (evita ST de bodega a bodega)
        7. Valida que destino no sea la misma bodega origen
        8. Valida que cada tienda pertenezca a la bodega origen (basado en prefijos: TRL-→RL-CD, TOUT-→OUT-CD, RG-→RG-CD)
        9. Agrupa por tienda y crea un Inventory Transfer Request por tienda en SAP (POST /InventoryTransferRequests)
        10. Registra los resultados
        
        Args:
            pedido_id: UUID del pedido
            oc_doc_num: Número de OC de SAP (DocNum) relacionada (opcional)
            bodega_origen: Código de bodega origen (si None, usa origen_traslado del pedido)
                          ⭐ Recomendado: pasar codigo_bodega de la OC para consistencia
            usuario_id: ID del usuario que genera las transferencias
        
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
            "resultados": []
        }
        
        try:
            with get_db_connection_context() as conn:
                pedido_repo = PedidoRepository(conn)
                dist_repo = DistribucionConfirmadaRepository(conn)
                sap_proc_repo = PedidoSAPProcesamientoRepository(conn)
                
                # 1. Obtener pedido completo
                pedido_data = pedido_repo.get_pedido_completo(pedido_id)
                if not pedido_data:
                    raise ValueError(f"No se encontró el pedido con ID: {pedido_id}")
                
                pedido_cabecera = pedido_data.get("cabecera", {})
                
                # ⭐ Obtener serie del pedido si no se proporcionó como parámetro
                if serie is None:
                    serie_raw = pedido_cabecera.get("serie")
                    if serie_raw is not None:
                        try:
                            serie = int(serie_raw)
                            logger.info(f"📍 Usando serie del pedido para ITR: {serie}")
                        except (TypeError, ValueError):
                            logger.warning(f"⚠️ Valor de serie no válido en pedido: {serie_raw}")
                else:
                    logger.info(f"📍 Usando serie proporcionada para ITR: {serie}")
                
                # 2. Obtener bodega origen (prioridad: parámetro > origen_traslado del pedido > default)
                # ⭐ IMPORTANTE: Si bodega_origen viene de la OC (codigo_bodega), tiene prioridad
                # sobre origen_traslado del pedido para asegurar consistencia
                if not bodega_origen:
                    bodega_origen = pedido_cabecera.get("origen_traslado") or "01"  # Default a "01" si no hay
                    logger.info(f"📍 Usando bodega origen del pedido (origen_traslado): {bodega_origen}")
                else:
                    logger.info(f"📍 Usando bodega origen proporcionada (de la OC): {bodega_origen}")
                
                # Asegurar que bodega_origen nunca sea None
                if bodega_origen is None:
                    bodega_origen = "01"
                
                # 3. Obtener distribución confirmada (última versión)
                version_actual = dist_repo.get_version_actual(pedido_id)
                if version_actual == 0:
                    raise ValueError(f"No hay distribución confirmada para el pedido {pedido_id}")
                
                distribucion_data = dist_repo.get_distribucion_completa(pedido_id, version_actual)
                productos_distribucion = distribucion_data.get("productos", [])
                
                if not productos_distribucion:
                    raise ValueError(f"No hay productos en la distribución confirmada del pedido {pedido_id}")
                
                # 4. Obtener procesamientos SAP (para códigos SAP y conversiones)
                procesamientos = sap_proc_repo.get_procesamientos_por_pedido(pedido_id)
                mapa_procesamientos = {p["pedido_detalle_id"]: p for p in procesamientos}
                
                # 5. Agrupar distribución por TIENDA (solo tiendas, NO bodegas)
                # ⭐ IMPORTANTE: Las Solicitudes de Transferencia se crean desde bodega origen hacia TIENDAS
                # - Origen: Bodega (OUT-CD, RG-CD, RL-CD) del campo origen_traslado
                # - Destino: TIENDAS (es_bodega=False), cada bodega tiene sus propias tiendas
                # - Se excluyen bodegas como destino para evitar ST de bodega a bodega
                # - Se valida que las tiendas existan en SAP antes de crear las STs
                distribucion_por_tienda: Dict[str, List[Dict[str, Any]]] = {}
                bodegas_codigos = {'OUT-CD', 'RG-CD', 'RL-CD'}  # Códigos de bodegas para EXCLUIR como destino
                distribuciones_omitidas = 0
                
                # ⭐ VALIDACIÓN PREVIA: Recopilar todos los códigos de tiendas únicos para validar en SAP
                codigos_tiendas_unicos = set()
                for producto_dist in productos_distribucion:
                    distribuciones = producto_dist.get("distribuciones", [])
                    distribuciones_tiendas = [d for d in distribuciones if not d.get("es_bodega", False)]
                    for dist in distribuciones_tiendas:
                        tienda_codigo = dist.get("tienda_codigo")
                        if tienda_codigo:
                            codigos_tiendas_unicos.add(tienda_codigo.strip().upper())
                
                # Validar que todas las tiendas existan en SAP
                # ⭐ IMPORTANTE: Guardar código exacto de SAP (WhsCode) y nombre para usar en las STs
                tiendas_validas_en_sap = set()  # Códigos normalizados para validación
                mapeo_codigo_exacto_sap = {}  # Mapeo: código_normalizado → código_exacto_SAP (WhsCode)
                mapeo_nombre_tienda = {}  # Mapeo: código_normalizado → nombre_tienda (WhsName)
                
                if codigos_tiendas_unicos:
                    logger.info(f"🔍 Validando {len(codigos_tiendas_unicos)} tienda(s) en SAP antes de crear STs...")
                    bodega_sap_service = BodegaSAPService()
                    resultado_validacion = bodega_sap_service.validate_codigos_bodegas_tiendas(
                        codigos=list(codigos_tiendas_unicos),
                        force_refresh=False
                    )
                    
                    # Procesar resultados de validación
                    for codigo, info in resultado_validacion.items():
                        if info.get("encontrado", False):
                            codigo_normalizado = codigo.upper()
                            codigo_exacto_sap = info.get("WhsCode", codigo_normalizado)  # Usar código exacto de SAP
                            nombre_tienda = info.get("WhsName", None)  # Obtener nombre de la tienda
                            
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
                
                for producto_dist in productos_distribucion:
                    pedido_detalle_id = producto_dist.get("pedido_detalle_id")
                    procesamiento = mapa_procesamientos.get(pedido_detalle_id)
                    
                    if not procesamiento:
                        logger.warning(
                            f"⚠️ No hay procesamiento SAP para pedido_detalle_id: {pedido_detalle_id}"
                        )
                        continue
                    
                    # Obtener item_code_sap y unidad_conversion desde procesamiento
                    item_code_sap = procesamiento.get("item_code_sap")
                    unidad_conversion = procesamiento.get("unidad_conversion")
                    
                    if not item_code_sap:
                        logger.warning(
                            f"⚠️ Procesamiento incompleto para pedido_detalle_id: {pedido_detalle_id}"
                        )
                        continue
                    
                    # ⭐ Conversión por tienda (trazable): cantidad_sap = cantidad_asignada × unidad_conversion.
                    # No se usa el total del producto ni bodegas; cada tienda se convierte de forma independiente.
                    factor_conversion = float(unidad_conversion) if unidad_conversion is not None and float(unidad_conversion) > 0 else 1.0
                    logger.debug(
                        f"   Conversión por tienda: {item_code_sap} | unidad_conversion={factor_conversion} "
                        f"(cada cantidad_asignada × {factor_conversion} → cantidad_sap)"
                    )
                    
                    # Procesar distribuciones por TIENDA de este producto (excluir bodegas)
                    distribuciones = producto_dist.get("distribuciones", [])
                    # ⭐ CORRECCIÓN: Filtrar solo distribuciones de TIENDAS (es_bodega=False)
                    distribuciones_tiendas = [d for d in distribuciones if not d.get("es_bodega", False)]
                    
                    if not distribuciones_tiendas:
                        continue
                    
                    cantidad_total_distribuida_tiendas = sum(d.get("cantidad_asignada", 0) for d in distribuciones_tiendas)
                    
                    if cantidad_total_distribuida_tiendas == 0:
                        continue
                    
                    for dist in distribuciones_tiendas:
                        tienda_id = dist.get("tienda_id")
                        tienda_codigo = dist.get("tienda_codigo")
                        cantidad_asignada = dist.get("cantidad_asignada", 0)
                        es_bodega = dist.get("es_bodega", False)
                        
                        if cantidad_asignada <= 0:
                            continue
                        
                        # ⭐ VALIDACIÓN 1: Excluir bodegas como destino (evitar ST de bodega a bodega)
                        tienda_codigo_upper = tienda_codigo.strip().upper() if tienda_codigo else ""
                        if tienda_codigo_upper in bodegas_codigos:
                            distribuciones_omitidas += 1
                            logger.warning(
                                f"⚠️ Omitiendo distribución: '{tienda_codigo}' es una bodega, no una tienda. "
                                f"Las Solicitudes de Transferencia solo se crean hacia tiendas, no hacia bodegas."
                            )
                            continue
                        
                        # ⭐ VALIDACIÓN 2: Validar que destino no sea la misma bodega origen
                        bodega_origen_upper = bodega_origen.strip().upper()
                        if tienda_codigo_upper == bodega_origen_upper:
                            distribuciones_omitidas += 1
                            logger.warning(
                                f"⚠️ Omitiendo distribución: '{tienda_codigo}' es la misma bodega origen ({bodega_origen}). "
                                f"No se puede crear transferencia de {bodega_origen} a {tienda_codigo}"
                            )
                            continue
                        
                        # ⭐ VALIDACIÓN 3: Validar que la tienda exista en SAP
                        if tienda_codigo_upper not in tiendas_validas_en_sap:
                            distribuciones_omitidas += 1
                            logger.warning(
                                f"⚠️ Omitiendo distribución: La tienda '{tienda_codigo}' no existe en SAP. "
                                f"No se puede crear Solicitud de Transferencia hacia una tienda inexistente."
                            )
                            continue
                        
                        # ⭐ VALIDACIÓN 4: Validar que la tienda pertenezca a la bodega origen
                        bodega_tienda = self.obtener_bodega_de_tienda(tienda_codigo)
                        if bodega_tienda is None:
                            distribuciones_omitidas += 1
                            logger.warning(
                                f"⚠️ Omitiendo distribución: No se pudo determinar la bodega de la tienda '{tienda_codigo}'. "
                                f"El código no coincide con ningún patrón conocido (TRL-*, TOUT-*, RG-*)."
                            )
                            continue
                        
                        if bodega_tienda != bodega_origen_upper:
                            distribuciones_omitidas += 1
                            logger.warning(
                                f"⚠️ Omitiendo distribución: La tienda '{tienda_codigo}' pertenece a la bodega '{bodega_tienda}', "
                                f"pero el pedido tiene origen '{bodega_origen}'. "
                                f"No se puede crear transferencia de {bodega_origen} a una tienda de {bodega_tienda}."
                            )
                            continue
                        
                        # Convertir por tienda: cantidad_sap = cantidad_asignada × unidad_conversion (trazable)
                        cantidad_sap_asignada = float(cantidad_asignada) * factor_conversion
                        logger.debug(
                            f"      {item_code_sap} → {tienda_codigo}: {cantidad_asignada} × {factor_conversion} = {cantidad_sap_asignada}"
                        )
                        
                        # ⭐ Obtener código exacto de SAP (WhsCode) para usar en la ST
                        codigo_exacto_sap = mapeo_codigo_exacto_sap.get(tienda_codigo_upper, tienda_codigo_upper)
                        
                        if tienda_id not in distribucion_por_tienda:
                            distribucion_por_tienda[tienda_id] = []
                        
                        distribucion_por_tienda[tienda_id].append({
                            "pedido_detalle_id": pedido_detalle_id,
                            "codigo_producto": producto_dist.get("codigo_producto"),
                            "item_code_sap": item_code_sap,
                            "cantidad_asignada": cantidad_asignada,
                            "cantidad_sap": cantidad_sap_asignada,
                            "tienda_id": tienda_id,
                            "tienda_codigo": tienda_codigo,
                            "warehouse_code": codigo_exacto_sap,  # ⭐ Usar código exacto de SAP (WhsCode)
                            "es_bodega": es_bodega
                        })
                        
                        # ⭐ LOGGING: Registrar el código exacto que se usará
                        if codigo_exacto_sap != tienda_codigo_upper:
                            logger.debug(
                                f"📝 Código normalizado '{tienda_codigo_upper}' → código exacto SAP '{codigo_exacto_sap}'"
                            )
                
                if distribuciones_omitidas > 0:
                    logger.info(
                        f"ℹ️ Se omitieron {distribuciones_omitidas} distribución(es) "
                        f"(bodegas o mismo origen que {bodega_origen})"
                    )
                
                if not distribucion_por_tienda:
                    raise ValueError(
                        "No hay distribución válida por tienda para crear transferencias. "
                        "Las Solicitudes de Transferencia se crean desde bodega origen hacia tiendas, no hacia bodegas."
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
                
                # ⭐ VALIDACIÓN MÍNIMA PARA ITR: Solo validar formato básico
                # SAP NO requiere validación de stock ni de artículos habilitados en bodega origen para ITR
                # Las ITR son solo solicitudes, no mueven stock, por lo que SAP permite crearlas
                # aunque el artículo no esté dado de alta en la bodega origen
                try:
                    self._validate_itr_minimal(stock_transfers_json)
                except ValueError as e:
                    # Error de formato básico - esto SÍ debe bloquear el flujo
                    error_msg = str(e)
                    logger.error(f"❌ {error_msg}")
                    result["error"] = error_msg
                    result["success"] = False
                    result["error_type"] = "validacion_formato"  # Flag para identificar tipo de error
                    # Persistir y generar JSON (auditoría de intento fallido)
                    self._persistir_y_guardar_json_solicitudes_transferencia(
                        conn=conn,
                        result=result,
                        payloads_sap=stock_transfers_json,
                        oc_id=oc_id,
                        pedido_id=pedido_id,
                        bodega_origen=bodega_origen,
                        oc_doc_num=oc_doc_num,
                    )
                    return result
                
                # 7. Crear cada Inventory Transfer Request en SAP (POST /InventoryTransferRequests)
                logger.info(
                    f"📤 Enviando {len(stock_transfers_json)} Inventory Transfer Request(s) a SAP..."
                )
                for idx, stock_transfer_json in enumerate(stock_transfers_json):
                    tienda_codigo = stock_transfer_json.get("ToWarehouse", "N/A")
                    tienda_id = list(distribucion_por_tienda.keys())[idx]
                    
                    logger.debug(
                        f"🔄 Enviando ITR {idx+1}/{len(stock_transfers_json)} a SAP: "
                        f"{bodega_origen} → {tienda_codigo}..."
                    )
                    sap_response = self.sap_client.create_stock_transfer(stock_transfer_json)
                    
                    # Obtener nombre de la tienda desde el mapeo
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
                    
                    if sap_response and sap_response.get("success") and sap_response.get("doc_entry"):
                        # ✅ SOLO AQUÍ se considera que el ITR fue creado realmente en SAP
                        resultado_tienda["success"] = True
                        resultado_tienda["doc_entry"] = sap_response.get("doc_entry")
                        resultado_tienda["doc_num"] = sap_response.get("doc_num")
                        result["transferencias_creadas"] += 1
                        logger.info(
                            f"✅ Inventory Transfer Request CREADO en SAP: {bodega_origen} → {tienda_codigo} "
                            f"(DocEntry={resultado_tienda['doc_entry']}, DocNum={resultado_tienda['doc_num']})"
                        )
                    else:
                        error_msg = sap_response.get("error", "Error desconocido") if sap_response else "No se recibió respuesta de SAP"
                        resultado_tienda["error"] = error_msg
                        result["transferencias_errores"] += 1
                        logger.warning(
                            f"⚠️ Inventory Transfer Request NO creado: {bodega_origen} → {tienda_codigo}: {error_msg}"
                        )
                    
                    result["resultados"].append(resultado_tienda)
                
                # 8. Determinar éxito general y loguear resultado REAL
                result["success"] = result["transferencias_creadas"] > 0
                
                # ⭐ IMPORTANTE: Construir mensajes de error/warning detallados para la UI
                # Extraer errores individuales de cada ITR fallido
                errores_detalle = []
                for r in result["resultados"]:
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
                    # ⭐ FIX: Establecer result["error"] con detalle real (antes quedaba sin definir → "Error desconocido")
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
                
                # Persistir en BD y generar JSON
                self._persistir_y_guardar_json_solicitudes_transferencia(
                    conn=conn,
                    result=result,
                    payloads_sap=stock_transfers_json,
                    oc_id=oc_id,
                    pedido_id=pedido_id,
                    bodega_origen=bodega_origen,
                    oc_doc_num=oc_doc_num,
                )
                return result
                
        except Exception as e:
            logger.error(f"❌ Error al crear Solicitudes de Transferencia: {e}", exc_info=True)
            result["error"] = str(e)
            return result
