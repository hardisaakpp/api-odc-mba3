"""
Servicio para crear órdenes de compra desde pedidos confirmados.
FASE 5: Generación de ODC desde pedido_sap_procesamiento_detalle (datos ya procesados).
Similar a copy_despacho_to_orden_compra() pero para pedidos.
"""

import json
import logging
import pyodbc
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.utils.timezone import ahora_naive

from ..connection import get_db_connection_context
from ..pedido_estados import ESTADOS_VALIDOS_PARA_ODC, estado_id_desde_legacy
from ..repositories.pedido_repository import PedidoRepository
from ..repositories.pedido_sap_procesamiento_repository import PedidoSAPProcesamientoRepository
from ..repositories.orden_compra_repository import OrdenCompraRepository
from ..mappers.sap_oc_mapper import SAPOCMapper

logger = logging.getLogger(__name__)


class PedidoOCService:
    """Servicio para crear órdenes de compra desde pedidos confirmados."""
    
    def __init__(self):
        """Inicializa el servicio."""
        pass
    
    def _to_orden_compra_cabecera_from_pedido(
        self,
        pedido_cabecera: Dict[str, Any],
        proveedor: str,
        codigo_bodega: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transforma una cabecera de pedido a formato de orden_compra_cabecera.
        
        Similar a OrdenCompraMapper.to_orden_compra_cabecera() pero para pedidos.
        
        Mapeo:
        - pedido_id → pedido_id (asociación directa)
        - numero_pedido → referencia_despacho (similar a numero_factura en despachos)
        - fecha_pedido → fecha_generacion
        - proveedor_nombre → proveedor (mapeado desde tabla cliente)
        - codigo_bodega → codigo_bodega (determinado desde distribuciones o origen_traslado)
        
        Args:
            pedido_cabecera: Diccionario con datos de pedido (cabecera)
            proveedor: CardCode SAP (proveedor) obtenido desde tabla cliente
            codigo_bodega: Código de bodega determinada (opcional)
            
        Returns:
            Diccionario con datos para insertar en orden_compra_cabecera
        """
        # Convertir fecha_pedido si viene como string ISO
        fecha_pedido = pedido_cabecera.get("fecha_pedido")
        if isinstance(fecha_pedido, str):
            try:
                fecha_pedido = datetime.fromisoformat(fecha_pedido.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                # Si falla, usar fecha actual
                fecha_pedido = ahora_naive()
        elif fecha_pedido is None:
            fecha_pedido = ahora_naive()
        
        return {
            "despacho_id": None,  # No viene de despacho
            "pedido_id": pedido_cabecera.get("pedido_id"),
            "proveedor": proveedor,
            "fecha_generacion": fecha_pedido,
            "referencia_despacho": pedido_cabecera.get("numero_pedido"),  # Similar a numero_factura
            "codigo_bodega": codigo_bodega,  # Bodega determinada
        }
    
    @staticmethod
    def _buscar_bodega_en_producto(
        producto: Dict[str, Any],
        pedido_detalle_id: str,
        bodega_objetivo: Optional[str] = None,
    ) -> Optional[str]:
        if producto.get("pedido_detalle_id") != pedido_detalle_id:
            return None
        bodega_objetivo_norm = bodega_objetivo.strip().upper() if bodega_objetivo else None
        for dist in producto.get("distribuciones", []):
            cantidad_asignada = dist.get("cantidad_asignada", 0)
            tienda_codigo = dist.get("tienda_codigo")
            if dist.get("es_bodega", False) and cantidad_asignada and cantidad_asignada > 0 and tienda_codigo:
                codigo = tienda_codigo.strip().upper()
                # En pedido mixto, una línea es_bodega=True de OTRA bodega no debe
                # "contaminar" la ODC que se está construyendo ahora (ver bug PYTD002:
                # ambas ODC de un pedido mixto terminaban con WarehouseCode de una sola
                # bodega porque esta búsqueda no distinguía para cuál ODC se llamaba).
                if bodega_objetivo_norm and codigo != bodega_objetivo_norm:
                    continue
                return codigo
        return None

    @staticmethod
    def _buscar_bodega_desde_distribuciones(
        conn: pyodbc.Connection,
        pedido_id: str,
        pedido_detalle_id: str,
        bodega_objetivo: Optional[str] = None,
    ) -> Optional[str]:
        try:
            from ..repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
            dist_repo = DistribucionConfirmadaRepository(conn)
            version_actual = dist_repo.get_version_actual(pedido_id)
            if version_actual <= 0:
                return None
            distribucion_data = dist_repo.get_distribucion_completa(pedido_id, version_actual)
            for producto in distribucion_data.get("productos", []):
                codigo = PedidoOCService._buscar_bodega_en_producto(producto, pedido_detalle_id, bodega_objetivo)
                if codigo:
                    logger.debug(f"📍 Bodega obtenida desde distribución para detalle {pedido_detalle_id}: {codigo}")
                    return codigo
        except Exception as e:
            logger.warning(f"⚠️ No se pudo obtener bodega desde distribuciones para detalle {pedido_detalle_id}: {e}")
        return None

    def _to_orden_compra_detalle_from_procesamiento(
        self,
        procesamiento_detalle: Dict[str, Any],
        conn: Optional[pyodbc.Connection] = None,
        pedido_id: Optional[str] = None,
        codigo_bodega_cabecera: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transforma un detalle de pedido_sap_procesamiento_detalle a formato de orden_compra_detalle.

        Mapeo directo (sin conversiones, ya están procesados):
        - item_code_sap → sku_sap
        - cantidad_sap → cantidad_sap (ya convertida)
        - unidad_sap → unidad_sap (ya procesada)
        - precio_unitario_sap → precio_unitario (ya convertido)
        - total_linea_sap → total_linea (ya calculado)
        - cantidad_original → cantidad_origen (para auditoría)
        - pedido_detalle_id → referencia_detalle
        - codigo_bodega → obtenido desde distribuciones confirmadas (es_bodega=True),
                           con fallback a codigo_bodega_cabecera (origen_traslado)

        Args:
            procesamiento_detalle: Diccionario con datos de pedido_sap_procesamiento_detalle
            conn: Conexión a la base de datos (opcional, para obtener bodega desde distribuciones)
            pedido_id: UUID del pedido (opcional, para obtener bodega desde distribuciones)
            codigo_bodega_cabecera: Bodega de la cabecera como fallback (ej: RL-CD de origen_traslado)

        Returns:
            Diccionario con datos para insertar en orden_compra_detalle
        """
        codigo_bodega = None

        if conn and pedido_id:
            pedido_detalle_id = procesamiento_detalle.get("pedido_detalle_id")
            if pedido_detalle_id:
                codigo_bodega = PedidoOCService._buscar_bodega_desde_distribuciones(
                    conn, pedido_id, pedido_detalle_id, bodega_objetivo=codigo_bodega_cabecera
                )

        if not codigo_bodega and codigo_bodega_cabecera:
            codigo_bodega = codigo_bodega_cabecera
            sku = procesamiento_detalle.get("item_code_sap", "?")
            logger.debug(f"📍 Bodega de cabecera usada como fallback para {sku}: {codigo_bodega}")

        return {
            "sku_sap": procesamiento_detalle.get("item_code_sap"),
            "cantidad_sap": procesamiento_detalle.get("cantidad_sap"),
            "unidad_sap": procesamiento_detalle.get("unidad_sap"),
            "referencia_detalle": procesamiento_detalle.get("pedido_detalle_id"),
            "precio_unitario": procesamiento_detalle.get("precio_unitario_sap"),
            "total_linea": procesamiento_detalle.get("total_linea_sap"),
            "cantidad_origen": procesamiento_detalle.get("cantidad_original"),
            "codigo_bodega": codigo_bodega,
        }
    
    @staticmethod
    def _validar_estado_pedido(pedido_cabecera: Dict[str, Any], pedido_id: str) -> None:
        raw_eid = pedido_cabecera.get("estado_id")
        try:
            estado_id_pedido = int(raw_eid) if raw_eid is not None else None
        except (TypeError, ValueError):
            estado_id_pedido = None
        if estado_id_pedido is None and pedido_cabecera.get("estado"):
            estado_id_pedido = estado_id_desde_legacy(str(pedido_cabecera.get("estado")))
        if estado_id_pedido is None or estado_id_pedido not in ESTADOS_VALIDOS_PARA_ODC:
            estado_nom = pedido_cabecera.get("estado")
            raise ValueError(
                f"El pedido {pedido_id} no está en un estado válido para generar ODC. "
                f"estado_id={estado_id_pedido}, estado={estado_nom}. "
                f"Ids válidos: {sorted(ESTADOS_VALIDOS_PARA_ODC)}"
            )

    @staticmethod
    def _filtrar_procesamientos(
        procesamientos: List[Dict[str, Any]]
    ) -> tuple:
        validos: List[Dict[str, Any]] = []
        no_homologados: List[Dict[str, Any]] = []
        sin_cantidad: List[Dict[str, Any]] = []
        for proc in procesamientos:
            if not proc.get("producto_homologado", True):
                no_homologados.append({
                    "codigo_interno": proc.get("codigo_interno"),
                    "tipo_problema": proc.get("tipo_problema"),
                    "mensaje_error": proc.get("mensaje_error")
                })
                continue
            cantidad_sap = proc.get("cantidad_sap")
            if not cantidad_sap or cantidad_sap <= 0:
                sin_cantidad.append({
                    "codigo_interno": proc.get("codigo_interno"),
                    "cantidad_sap": cantidad_sap
                })
                continue
            if not proc.get("item_code_sap"):
                no_homologados.append({
                    "codigo_interno": proc.get("codigo_interno"),
                    "tipo_problema": "sin_item_code",
                    "mensaje_error": "No tiene ItemCode SAP"
                })
                continue
            validos.append(proc)
        return validos, no_homologados, sin_cantidad

    @staticmethod
    def _determinar_bodega_oc(pedido_id: str, oc_repo: Any) -> Optional[str]:
        try:
            from ..services.oc_sap_service import OCSAPService
            oc_sap_service = OCSAPService()
            cabecera_temporal = {"pedido_id": pedido_id}
            codigo_bodega = oc_sap_service.determinar_bodega_desde_pedido(cabecera_temporal, oc_repo)
            if codigo_bodega:
                logger.info(f"📍 Bodega determinada para OC: {codigo_bodega}")
            else:
                logger.warning(f"⚠️ No se pudo determinar bodega para el pedido {pedido_id}")
            return codigo_bodega
        except Exception as e:
            logger.warning(f"⚠️ Error al determinar bodega: {e}")
            return None

    @staticmethod
    def _upsert_oc_cabecera(
        oc_repo: Any,
        oc_cabecera_data: Dict[str, Any],
        existing_oc_id: Optional[str],
        pedido_id: str,
        result: Dict[str, Any]
    ) -> str:
        if existing_oc_id:
            logger.info(f"🔄 Actualizando OC existente: {existing_oc_id}")
            oc_repo.update_cabecera(existing_oc_id, oc_cabecera_data)
            result["oc_id"] = existing_oc_id
            result["cabecera_insertada"] = False
            result["cabecera_actualizada"] = True
            detalles_eliminados = oc_repo.delete_detalles(existing_oc_id)
            logger.debug(f"   → {detalles_eliminados} detalles antiguos eliminados")
            return existing_oc_id
        else:
            oc_id = oc_repo.insert_cabecera(oc_cabecera_data)
            result["oc_id"] = oc_id
            result["cabecera_insertada"] = True
            result["cabecera_actualizada"] = False
            logger.info(f"✅ Orden de compra cabecera creada: {oc_id} para pedido {pedido_id}")
            return oc_id

    def _construir_detalles_oc(
        self,
        procesamientos_validos: List[Dict[str, Any]],
        conn: pyodbc.Connection,
        pedido_id: str,
        codigo_bodega: Optional[str]
    ) -> List[Dict[str, Any]]:
        oc_detalles = []
        for proc in procesamientos_validos:
            oc_detalle = self._to_orden_compra_detalle_from_procesamiento(
                proc, conn=conn, pedido_id=pedido_id, codigo_bodega_cabecera=codigo_bodega
            )
            if oc_detalle.get("sku_sap") and oc_detalle.get("cantidad_sap") is not None:
                oc_detalles.append(oc_detalle)
            else:
                logger.warning(
                    f"⚠️ Detalle omitido por falta de datos: "
                    f"SKU={oc_detalle.get('sku_sap')}, "
                    f"Cantidad={oc_detalle.get('cantidad_sap')}"
                )
        return oc_detalles

    @staticmethod
    def _generar_json_sap_oc(
        oc_repo: Any,
        oc_id: str,
        codigo_bodega: Optional[str],
        pedido_id: str,
        pedido_cabecera: Dict[str, Any],
        result: Dict[str, Any]
    ) -> None:
        try:
            oc_cabecera_db = oc_repo.get_existing_cabecera(oc_id)
            oc_detalles_db = oc_repo.get_detalles(oc_id)
            if oc_cabecera_db and oc_detalles_db:
                warehouse_code = oc_cabecera_db.get("codigo_bodega") or codigo_bodega
                sap_request_json = SAPOCMapper.to_sap_purchase_order(
                    oc_cabecera_db,
                    oc_detalles_db,
                    warehouse_code,
                    usuario_id=oc_cabecera_db.get("creado_por"),
                    pedido_id=oc_cabecera_db.get("pedido_id") or pedido_id,
                    fecha_entrega=pedido_cabecera.get("fecha_entrega"),
                )
                result["sap_request_json"] = sap_request_json
                # DESACTIVADO: Descarga de ODC en JSON a output/
                # try:
                #     output_dir = PROJECT_ROOT / "output"
                #     output_dir.mkdir(parents=True, exist_ok=True)
                #     out_file = output_dir / f"odc_{oc_id}.json"
                #     with open(out_file, "w", encoding="utf-8") as f:
                #         json.dump(sap_request_json, f, ensure_ascii=False, indent=2, default=str)
                #     logger.info(f"📥 ODC guardada en {out_file}")
                # except Exception as e:
                #     logger.warning(f"⚠️ No se pudo guardar ODC en output/: {e}")
                card = sap_request_json.get("CardCode", "")
                lineas = sap_request_json.get("DocumentLines", [])
                items = [ln.get("ItemCode") for ln in lineas]
                bodegas = list({ln.get("WarehouseCode") for ln in lineas if ln.get("WarehouseCode")})
                logger.info(
                    f"📄 JSON SAP generado para ODC {oc_id}: CardCode={card}, "
                    f"ItemCodes={items[:5]}{'...' if len(items) > 5 else ''}, "
                    f"WarehouseCodes={bodegas}"
                )
                logger.debug(
                    f"   Request SAP completo: {json.dumps(sap_request_json, ensure_ascii=False, default=str)[:2500]}"
                )
        except ValueError as e:
            logger.warning(f"⚠️ No se pudo generar JSON SAP al crear ODC (validación): {e}")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo generar JSON SAP al crear ODC: {e}", exc_info=False)

    @staticmethod
    def _sumar_cantidad_por_bodega(distribuciones: List[Dict[str, Any]]) -> Dict[str, float]:
        """Suma cantidad_asignada por bodega (tienda→marca→bodega, ver Fase 1 de PYTD002:
        StockTransferService.obtener_bodega_de_tienda), ignorando filas es_bodega=True."""
        from .stock_transfer_service import StockTransferService
        sumas: Dict[str, float] = {}
        for dist in distribuciones:
            if dist.get("es_bodega", False):
                continue
            cantidad = dist.get("cantidad_asignada", 0) or 0
            if cantidad <= 0:
                continue
            tienda_codigo = dist.get("tienda_codigo")
            if not tienda_codigo:
                continue
            bodega = StockTransferService.obtener_bodega_de_tienda(tienda_codigo)
            if not bodega:
                continue
            sumas[bodega] = sumas.get(bodega, 0) + float(cantidad)
        return sumas

    @staticmethod
    def _registrar_tienda_por_bodega(
        dist: Dict[str, Any],
        grupos: Dict[str, List[str]],
        vistos: set,
    ) -> None:
        """Procesa una distribución individual de `_tiendas_por_bodega`: si es una
        tienda válida (no bodega, con cantidad, no vista aún) cuya bodega resuelta
        está en `grupos`, la agrega ahí (mutando `grupos`/`vistos` in-place)."""
        from .stock_transfer_service import StockTransferService

        if dist.get("es_bodega", False):
            return
        cantidad = dist.get("cantidad_asignada", 0) or 0
        if cantidad <= 0:
            return
        tienda_codigo = dist.get("tienda_codigo")
        if not tienda_codigo:
            return
        codigo_upper = tienda_codigo.strip().upper()
        if codigo_upper in vistos:
            return
        bodega = StockTransferService.obtener_bodega_de_tienda(codigo_upper)
        if bodega not in grupos:
            return
        vistos.add(codigo_upper)
        grupos[bodega].append(codigo_upper)

    @staticmethod
    def _tiendas_por_bodega(
        conn: pyodbc.Connection,
        pedido_id: str,
        bodegas: List[str],
    ) -> Dict[str, List[str]]:
        """Códigos de tienda (destino real de ST, es_bodega=False) de la distribución
        confirmada del pedido, agrupados por bodega resuelta (Fase 1). Se usa para
        acotar tiendas_destino_filtro al enviar cada ODC de un pedido mixto a SAP, para
        que cada una solo procese sus propias tiendas (la validación de bodega en
        StockTransferService ya rechaza cruces, esto solo evita ruido de líneas omitidas)."""
        from ..repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository

        grupos: Dict[str, List[str]] = {b: [] for b in bodegas}
        vistos: set = set()
        try:
            dist_repo = DistribucionConfirmadaRepository(conn)
            version_actual = dist_repo.get_version_actual(pedido_id)
            if version_actual <= 0:
                return grupos
            distribucion_data = dist_repo.get_distribucion_completa(pedido_id, version_actual)
            for producto in distribucion_data.get("productos", []):
                for dist in producto.get("distribuciones", []):
                    PedidoOCService._registrar_tienda_por_bodega(dist, grupos, vistos)
        except Exception as e:
            logger.warning(f"⚠️ No se pudo agrupar tiendas por bodega para pedido {pedido_id}: {e}")
        return grupos

    @staticmethod
    def _productos_por_detalle_id(conn: pyodbc.Connection, pedido_id: str) -> Dict[str, Dict[str, Any]]:
        """Distribución confirmada vigente del pedido, indexada por
        pedido_detalle_id. Usado por `_dividir_procesamientos_por_bodega` para
        conocer, por producto, cuánta cantidad fue asignada a cada tienda/bodega."""
        from ..repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository

        productos_por_detalle: Dict[str, Dict[str, Any]] = {}
        try:
            dist_repo = DistribucionConfirmadaRepository(conn)
            version_actual = dist_repo.get_version_actual(pedido_id)
            if version_actual <= 0:
                return productos_por_detalle
            distribucion_data = dist_repo.get_distribucion_completa(pedido_id, version_actual)
            for producto in distribucion_data.get("productos", []):
                pdi = producto.get("pedido_detalle_id")
                if pdi:
                    productos_por_detalle[pdi] = producto
        except Exception as e:
            logger.warning(f"⚠️ No se pudo obtener distribución confirmada para dividir por bodega: {e}")
        return productos_por_detalle

    @staticmethod
    def _repartir_proc_por_bodega(
        proc: Dict[str, Any],
        bodegas: List[str],
        productos_por_detalle: Dict[str, Dict[str, Any]],
        resultado: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        """Reparte un procesamiento individual entre las bodegas con cantidad
        asignada (mutando `resultado` in-place); ver `_dividir_procesamientos_por_bodega`."""
        pedido_detalle_id = proc.get("pedido_detalle_id")
        producto = productos_por_detalle.get(pedido_detalle_id) or {}
        sumas_por_bodega = PedidoOCService._sumar_cantidad_por_bodega(producto.get("distribuciones", []))
        bodegas_con_cantidad = [b for b in bodegas if sumas_por_bodega.get(b, 0) > 0]

        if len(bodegas_con_cantidad) <= 1:
            bodega_unica = bodegas_con_cantidad[0] if bodegas_con_cantidad else bodegas[0]
            if not bodegas_con_cantidad:
                logger.warning(
                    f"⚠️ No se pudo determinar bodega por tienda para {proc.get('item_code_sap')} "
                    f"(pedido_detalle_id={pedido_detalle_id}); se asigna a {bodega_unica} por defecto"
                )
            resultado.setdefault(bodega_unica, []).append(proc)
            return

        cantidad_total_tiendas = sum(sumas_por_bodega[b] for b in bodegas_con_cantidad)
        cantidad_sap_total = proc.get("cantidad_sap") or 0
        total_linea_sap_total = proc.get("total_linea_sap") or 0
        for bodega in bodegas_con_cantidad:
            proporcion = sumas_por_bodega[bodega] / cantidad_total_tiendas
            proc_bodega = dict(proc)
            proc_bodega["cantidad_original"] = sumas_por_bodega[bodega]
            proc_bodega["cantidad_sap"] = cantidad_sap_total * proporcion
            proc_bodega["total_linea_sap"] = total_linea_sap_total * proporcion
            resultado.setdefault(bodega, []).append(proc_bodega)

    @staticmethod
    def _dividir_procesamientos_por_bodega(
        procesamientos_validos: List[Dict[str, Any]],
        pedido_id: str,
        conn: pyodbc.Connection,
        bodegas: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Reparte procesamientos_validos entre las bodegas detectadas del pedido (pedido
        que mezcla tiendas de más de una marca, ver origen_traslado_detectado).

        pedido_sap_procesamiento_detalle guarda una cantidad_sap total por producto, ya
        sumada entre todas sus tiendas destino. Un producto cuyas tiendas pertenecen
        todas a una sola bodega pasa sin cambios a esa bodega. Un producto con tiendas
        de ambas bodegas se divide en 2 copias con cantidad_sap/total_linea_sap
        escalados según la proporción de cantidad asignada a cada bodega (mismo
        unidad_conversion ya calculado; no se vuelve a consultar SAP).
        """
        resultado: Dict[str, List[Dict[str, Any]]] = {b: [] for b in bodegas}
        productos_por_detalle = PedidoOCService._productos_por_detalle_id(conn, pedido_id)

        for proc in procesamientos_validos:
            PedidoOCService._repartir_proc_por_bodega(proc, bodegas, productos_por_detalle, resultado)

        return resultado

    def _crear_una_oc(
        self,
        oc_repo: 'OrdenCompraRepository',
        pedido_id: str,
        pedido_cabecera: Dict[str, Any],
        proveedor: str,
        codigo_bodega: Optional[str],
        oc_detalles: List[Dict[str, Any]],
        existing_oc_id: Optional[str],
    ) -> Dict[str, Any]:
        """Crea/actualiza una única orden_compra_cabecera + sus detalles. Usada tanto
        para el caso normal (1 ODC) como para cada bodega de un pedido mixto (2 ODC)."""
        result = {
            "oc_id": None,
            "pedido_id": pedido_id,
            "proveedor": proveedor,
            "codigo_bodega": codigo_bodega,
            "estado": "PENDIENTE",
            "detalles_insertados": 0,
            "total_lineas": 0,
            "cabecera_insertada": False,
            "cabecera_actualizada": False,
            "warnings": []
        }

        if not oc_detalles:
            raise ValueError(f"No se pudo crear ninguna línea de detalle válida para la OC (bodega {codigo_bodega})")

        oc_cabecera_data = self._to_orden_compra_cabecera_from_pedido(pedido_cabecera, proveedor, codigo_bodega)
        oc_cabecera_data["estado"] = "PENDIENTE"

        oc_id = self._upsert_oc_cabecera(oc_repo, oc_cabecera_data, existing_oc_id, pedido_id, result)

        detalles_insertados = oc_repo.insert_detalles(oc_id, oc_detalles)
        result["detalles_insertados"] = detalles_insertados
        result["total_lineas"] = len(oc_detalles)

        self._generar_json_sap_oc(oc_repo, oc_id, codigo_bodega, pedido_id, pedido_cabecera, result)

        accion = "actualizada" if result.get("cabecera_actualizada") else "creada"
        logger.info(
            f"✅ OC {accion}: {oc_id} para pedido {pedido_id} (bodega: {codigo_bodega}) "
            f"(detalles: {detalles_insertados}/{len(oc_detalles)})"
        )
        return result

    def _obtener_pedido_cabecera_validada(self, pedido_repo: 'PedidoRepository', pedido_id: str) -> Dict[str, Any]:
        """Carga la cabecera del pedido y valida existencia + estado. Usado por
        `crear_ocs_desde_pedido_confirmado`."""
        pedido = pedido_repo.get_pedido_completo(pedido_id)
        if not pedido:
            raise ValueError(f"Pedido no encontrado: {pedido_id}")

        pedido_cabecera = pedido.get("cabecera", {})
        if not pedido_cabecera:
            raise ValueError(f"No se encontró cabecera del pedido {pedido_id}")

        self._validar_estado_pedido(pedido_cabecera, pedido_id)
        return pedido_cabecera

    def _obtener_procesamientos_validos_y_warnings(
        self, sap_proc_repo: 'PedidoSAPProcesamientoRepository', pedido_id: str
    ) -> tuple:
        """Obtiene y filtra los procesamientos SAP del pedido, devolviendo
        (procesamientos_validos, warnings). Usado por `crear_ocs_desde_pedido_confirmado`."""
        procesamientos = sap_proc_repo.get_procesamientos_por_pedido(pedido_id)
        if not procesamientos:
            raise ValueError(
                f"No hay productos procesados (pedido_sap_procesamiento_detalle) para el pedido {pedido_id}. "
                f"Debe ejecutarse 'Confirmar Redistribución' primero."
            )

        procesamientos_validos, productos_no_homologados, productos_sin_cantidad = (
            self._filtrar_procesamientos(procesamientos)
        )

        warnings: List[str] = []
        if productos_no_homologados:
            warnings.append(f"{len(productos_no_homologados)} producto(s) no homologado(s) omitido(s)")
            logger.warning(f"⚠️ {len(productos_no_homologados)} productos no homologados omitidos")

        if productos_sin_cantidad:
            warnings.append(f"{len(productos_sin_cantidad)} producto(s) con cantidad 0 omitido(s)")
            logger.warning(f"⚠️ {len(productos_sin_cantidad)} productos con cantidad 0 omitidos")

        if not procesamientos_validos:
            raise ValueError(
                f"No hay productos válidos para crear la OC. "
                f"Productos no homologados: {len(productos_no_homologados)}, "
                f"Productos sin cantidad: {len(productos_sin_cantidad)}"
            )

        return procesamientos_validos, warnings

    @staticmethod
    def _resolver_proveedor(oc_repo: 'OrdenCompraRepository', pedido_cabecera: Dict[str, Any], pedido_id: str) -> str:
        """Resuelve el CardCode (proveedor) del pedido a partir de proveedor_nombre.
        Usado por `crear_ocs_desde_pedido_confirmado`."""
        proveedor_nombre = pedido_cabecera.get("proveedor_nombre")
        if not proveedor_nombre:
            raise ValueError(f"No se encontró 'proveedor_nombre' en la cabecera del pedido {pedido_id}")

        proveedor = oc_repo.get_proveedor_from_cliente(proveedor_nombre)
        if not proveedor:
            logger.warning(f"⚠️ No se pudo obtener proveedor para: {proveedor_nombre}. Usando proveedor_nombre como proveedor.")
            proveedor = proveedor_nombre
        if not proveedor:
            raise ValueError(f"No se pudo determinar el proveedor (CardCode) para: {proveedor_nombre}")

        logger.debug(f"🔄 Mapeo proveedor: {proveedor_nombre} → {proveedor}")
        return proveedor

    def _crear_oc_bodega_unica(
        self,
        oc_repo: 'OrdenCompraRepository',
        conn: pyodbc.Connection,
        pedido_id: str,
        pedido_cabecera: Dict[str, Any],
        proveedor: str,
        procesamientos_validos: List[Dict[str, Any]],
        warnings: List[str],
        upsert: bool,
    ) -> Dict[str, Any]:
        """Crea la única ODC de un pedido que no mezcla bodegas (caso normal,
        comportamiento idéntico al histórico). Usado por
        `crear_ocs_desde_pedido_confirmado`."""
        codigo_bodega = self._determinar_bodega_oc(pedido_id, oc_repo)
        existing_oc_id = oc_repo.find_by_pedido_id(pedido_id) if upsert else None
        if existing_oc_id:
            logger.info(f"ℹ️ OC ya existe para pedido {pedido_id} (oc_id: {existing_oc_id}), se actualizará")
        oc_detalles = self._construir_detalles_oc(procesamientos_validos, conn, pedido_id, codigo_bodega)
        resultado = self._crear_una_oc(
            oc_repo, pedido_id, pedido_cabecera, proveedor,
            codigo_bodega, oc_detalles, existing_oc_id
        )
        resultado["warnings"] = warnings + resultado.get("warnings", [])
        return resultado

    def _crear_oc_para_bodega(
        self,
        oc_repo: 'OrdenCompraRepository',
        conn: pyodbc.Connection,
        pedido_id: str,
        pedido_cabecera: Dict[str, Any],
        proveedor: str,
        codigo_bodega: str,
        procs_bodega: List[Dict[str, Any]],
        tiendas_por_bodega: Dict[str, List[str]],
        warnings: List[str],
        upsert: bool,
    ) -> Optional[Dict[str, Any]]:
        """Crea la ODC de una bodega de un pedido mixto, o None si esa bodega no
        tiene productos (se omite esa ODC). Usado por
        `crear_ocs_desde_pedido_confirmado`."""
        if not procs_bodega:
            logger.warning(f"⚠️ Sin productos para bodega {codigo_bodega} en pedido {pedido_id}, se omite esa ODC")
            return None
        existing_oc_id = oc_repo.find_by_pedido_id_y_bodega(pedido_id, codigo_bodega) if upsert else None
        if existing_oc_id:
            logger.info(f"ℹ️ OC ya existe para pedido {pedido_id}/{codigo_bodega} (oc_id: {existing_oc_id}), se actualizará")
        oc_detalles = self._construir_detalles_oc(procs_bodega, conn, pedido_id, codigo_bodega)
        resultado = self._crear_una_oc(
            oc_repo, pedido_id, pedido_cabecera, proveedor,
            codigo_bodega, oc_detalles, existing_oc_id
        )
        resultado["warnings"] = warnings + resultado.get("warnings", [])
        # Tiendas propias de esta bodega: se usa para acotar tiendas_destino_filtro
        # al enviar la ODC a SAP (ver enviar_oc_a_sap), así cada ODC solo procesa
        # sus propias tiendas sin ruido de líneas de la otra bodega omitidas.
        resultado["tiendas_bodega"] = tiendas_por_bodega.get(codigo_bodega, [])
        return resultado

    def crear_ocs_desde_pedido_confirmado(
        self,
        pedido_id: str,
        upsert: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Crea una o más órdenes de compra desde un pedido confirmado.

        Similar a copy_despacho_to_orden_compra() pero para pedidos.
        Lee desde pedido_sap_procesamiento_detalle (datos ya procesados).

        La mayoría de los pedidos generan 1 ODC (lista de 1 elemento). Si el
        pedido mezcla tiendas de más de una marca (origen_traslado_detectado con
        2+ códigos — ver Fase 1 de PYTD002), genera una ODC por bodega, cada una
        con solo sus líneas/tiendas correspondientes: mismo resultado que hoy se
        logra subiendo 2 pedidos separados, uno por marca.

        Args:
            pedido_id: UUID del pedido
            upsert: Si True, actualiza si existe; si False, inserta siempre

        Returns:
            Lista de dicts con resultado de la creación (uno por ODC)
        """
        with get_db_connection_context() as conn:
            pedido_repo = PedidoRepository(conn)
            sap_proc_repo = PedidoSAPProcesamientoRepository(conn)
            oc_repo = OrdenCompraRepository(conn)

            pedido_cabecera = self._obtener_pedido_cabecera_validada(pedido_repo, pedido_id)
            procesamientos_validos, warnings = self._obtener_procesamientos_validos_y_warnings(
                sap_proc_repo, pedido_id
            )
            proveedor = self._resolver_proveedor(oc_repo, pedido_cabecera, pedido_id)

            bodegas_detectadas = pedido_cabecera.get("origen_traslado_detectado") or []

            if len(bodegas_detectadas) <= 1:
                # Caso normal (una sola marca): comportamiento idéntico al histórico.
                resultado = self._crear_oc_bodega_unica(
                    oc_repo, conn, pedido_id, pedido_cabecera, proveedor,
                    procesamientos_validos, warnings, upsert,
                )
                return [resultado]

            # Pedido mixto: una ODC por bodega detectada.
            logger.info(f"📦 Pedido {pedido_id} mezcla {len(bodegas_detectadas)} bodegas: {bodegas_detectadas}")
            procesamientos_por_bodega = self._dividir_procesamientos_por_bodega(
                procesamientos_validos, pedido_id, conn, bodegas_detectadas
            )
            tiendas_por_bodega = self._tiendas_por_bodega(conn, pedido_id, bodegas_detectadas)

            resultados: List[Dict[str, Any]] = []
            for codigo_bodega in bodegas_detectadas:
                resultado = self._crear_oc_para_bodega(
                    oc_repo, conn, pedido_id, pedido_cabecera, proveedor, codigo_bodega,
                    procesamientos_por_bodega.get(codigo_bodega, []), tiendas_por_bodega,
                    warnings, upsert,
                )
                if resultado is not None:
                    resultados.append(resultado)

            if not resultados:
                raise ValueError(f"No se pudo crear ninguna ODC para el pedido mixto {pedido_id}")
            return resultados
