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

from src.config import PROJECT_ROOT
from ..connection import get_db_connection_context
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
                fecha_pedido = datetime.now()
        elif fecha_pedido is None:
            fecha_pedido = datetime.now()
        
        return {
            "despacho_id": None,  # No viene de despacho
            "pedido_id": pedido_cabecera.get("pedido_id"),
            "proveedor": proveedor,
            "fecha_generacion": fecha_pedido,
            "referencia_despacho": pedido_cabecera.get("numero_pedido"),  # Similar a numero_factura
            "codigo_bodega": codigo_bodega,  # Bodega determinada
        }
    
    def _to_orden_compra_detalle_from_procesamiento(
        self,
        procesamiento_detalle: Dict[str, Any],
        oc_id: str,
        conn: Optional[pyodbc.Connection] = None,
        pedido_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transforma un detalle de pedido_sap_procesamiento_detalle a formato de orden_compra_detalle.
        
        Similar a OrdenCompraMapper.to_orden_compra_detalle() pero para pedidos procesados.
        
        Mapeo directo (sin conversiones, ya están procesados):
        - item_code_sap → sku_sap
        - cantidad_sap → cantidad_sap (ya convertida)
        - unidad_sap → unidad_sap (ya procesada)
        - precio_unitario_sap → precio_unitario (ya convertido)
        - total_linea_sap → total_linea (ya calculado)
        - cantidad_original → cantidad_origen (para auditoría)
        - pedido_detalle_id → referencia_detalle
        - codigo_bodega → obtenido desde distribuciones confirmadas (es_bodega=True, cantidad_asignada > 0)
        
        Args:
            procesamiento_detalle: Diccionario con datos de pedido_sap_procesamiento_detalle
            oc_id: UUID de la cabecera de orden de compra
            conn: Conexión a la base de datos (opcional, para obtener bodega desde distribuciones)
            pedido_id: UUID del pedido (opcional, para obtener bodega desde distribuciones)
            
        Returns:
            Diccionario con datos para insertar en orden_compra_detalle
        """
        import pyodbc
        
        codigo_bodega = None
        
        # Intentar obtener bodega desde distribuciones confirmadas
        if conn and pedido_id:
            pedido_detalle_id = procesamiento_detalle.get("pedido_detalle_id")
            if pedido_detalle_id:
                try:
                    from ..repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
                    dist_repo = DistribucionConfirmadaRepository(conn)
                    
                    # Obtener versión actual de distribución confirmada
                    version_actual = dist_repo.get_version_actual(pedido_id)
                    if version_actual > 0:
                        distribucion_data = dist_repo.get_distribucion_completa(pedido_id, version_actual)
                        productos_distribucion = distribucion_data.get("productos", [])
                        
                        # Buscar bodega para este pedido_detalle_id específico
                        for producto in productos_distribucion:
                            if producto.get("pedido_detalle_id") == pedido_detalle_id:
                                distribuciones = producto.get("distribuciones", [])
                                for dist in distribuciones:
                                    if dist.get("es_bodega", False):
                                        cantidad_asignada = dist.get("cantidad_asignada", 0)
                                        if cantidad_asignada and cantidad_asignada > 0:
                                            tienda_codigo = dist.get("tienda_codigo")
                                            if tienda_codigo:
                                                codigo_bodega = tienda_codigo.strip().upper()
                                                logger.debug(
                                                    f"📍 Bodega obtenida desde distribución para detalle {pedido_detalle_id}: {codigo_bodega}"
                                                )
                                                break
                                if codigo_bodega:
                                    break
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo obtener bodega desde distribuciones para detalle {pedido_detalle_id}: {e}")
        
        return {
            "sku_sap": procesamiento_detalle.get("item_code_sap"),
            "cantidad_sap": procesamiento_detalle.get("cantidad_sap"),
            "unidad_sap": procesamiento_detalle.get("unidad_sap"),
            "referencia_detalle": procesamiento_detalle.get("pedido_detalle_id"),
            "precio_unitario": procesamiento_detalle.get("precio_unitario_sap"),
            "total_linea": procesamiento_detalle.get("total_linea_sap"),
            "cantidad_origen": procesamiento_detalle.get("cantidad_original"),
            "codigo_bodega": codigo_bodega,  # ⭐ NUEVO: Bodega por línea desde distribuciones
        }
    
    def crear_oc_desde_pedido_confirmado(
        self,
        pedido_id: str,
        usuario_id: Optional[str] = None,
        upsert: bool = True
    ) -> Dict[str, Any]:
        """
        Crea una orden de compra desde un pedido confirmado.
        
        Similar a copy_despacho_to_orden_compra() pero para pedidos.
        Lee desde pedido_sap_procesamiento_detalle (datos ya procesados).
        
        Flujo:
        1. Valida que el pedido existe
        2. Verifica si ya existe OC para este pedido (upsert)
        3. Obtiene cabecera desde pedido
        4. Obtiene detalles desde pedido_sap_procesamiento_detalle (ya procesados)
        5. Valida productos homologados y cantidad > 0
        6. Mapea empresa → proveedor desde tabla cliente
        7. Crea/actualiza OC con pedido_id asociado
        8. Estado inicial: PENDIENTE
        
        Args:
            pedido_id: UUID del pedido
            usuario_id: User ID del usuario que crea la OC (opcional, para auditoría)
            upsert: Si True, actualiza si existe; si False, inserta siempre
            
        Returns:
            Dict con resultado de la creación:
            {
                "oc_id": "uuid",
                "pedido_id": "uuid",
                "proveedor": "CardCode",
                "estado": "PENDIENTE",
                "detalles_insertados": 10,
                "total_lineas": 10,
                "cabecera_insertada": True,
                "cabecera_actualizada": False,
                "warnings": []
            }
        """
        result = {
            "oc_id": None,
            "pedido_id": pedido_id,
            "proveedor": None,
            "estado": "PENDIENTE",
            "detalles_insertados": 0,
            "total_lineas": 0,
            "cabecera_insertada": False,
            "cabecera_actualizada": False,
            "warnings": []
        }
        
        with get_db_connection_context() as conn:
            pedido_repo = PedidoRepository(conn)
            sap_proc_repo = PedidoSAPProcesamientoRepository(conn)
            oc_repo = OrdenCompraRepository(conn)
            
            # 1. Validar que el pedido existe
            pedido = pedido_repo.get_pedido_completo(pedido_id)
            if not pedido:
                raise ValueError(f"Pedido no encontrado: {pedido_id}")
            
            pedido_cabecera = pedido.get("cabecera", {})
            if not pedido_cabecera:
                raise ValueError(f"No se encontró cabecera del pedido {pedido_id}")
            
            # 1.1. Validar estado del pedido (debe estar en un estado válido para generar ODC)
            estado_pedido = pedido_cabecera.get("estado")
            estados_validos = ["CONFIRMADO_PROVEEDOR", "PEDIDO_CONFIRMADO", "CONFIRMADO REDISTRIBUCION"]
            if estado_pedido not in estados_validos:
                raise ValueError(
                    f"El pedido {pedido_id} no está en un estado válido para generar ODC. "
                    f"Estado actual: {estado_pedido}. "
                    f"Estados válidos: {', '.join(estados_validos)}"
                )
            
            # 2. Verificar si ya existe una OC para este pedido (para upsert)
            existing_oc_id = None
            if upsert:
                existing_oc_id = oc_repo.find_by_pedido_id(pedido_id)
                if existing_oc_id:
                    logger.info(f"ℹ️ OC ya existe para pedido {pedido_id} (oc_id: {existing_oc_id}), se actualizará")
            
            # 3. Obtener detalles procesados desde pedido_sap_procesamiento_detalle
            procesamientos = sap_proc_repo.get_procesamientos_por_pedido(pedido_id)
            
            if not procesamientos:
                raise ValueError(
                    f"No hay productos procesados (pedido_sap_procesamiento_detalle) para el pedido {pedido_id}. "
                    f"Debe ejecutarse 'Confirmar Redistribución' primero."
                )
            
            # 4. Filtrar solo productos homologados y con cantidad > 0
            procesamientos_validos = []
            productos_no_homologados = []
            productos_sin_cantidad = []
            
            for proc in procesamientos:
                producto_homologado = proc.get("producto_homologado", True)
                cantidad_sap = proc.get("cantidad_sap")
                item_code_sap = proc.get("item_code_sap")
                
                if not producto_homologado:
                    productos_no_homologados.append({
                        "codigo_interno": proc.get("codigo_interno"),
                        "tipo_problema": proc.get("tipo_problema"),
                        "mensaje_error": proc.get("mensaje_error")
                    })
                    continue
                
                if not cantidad_sap or cantidad_sap <= 0:
                    productos_sin_cantidad.append({
                        "codigo_interno": proc.get("codigo_interno"),
                        "cantidad_sap": cantidad_sap
                    })
                    continue
                
                if not item_code_sap:
                    productos_no_homologados.append({
                        "codigo_interno": proc.get("codigo_interno"),
                        "tipo_problema": "sin_item_code",
                        "mensaje_error": "No tiene ItemCode SAP"
                    })
                    continue
                
                procesamientos_validos.append(proc)
            
            # Advertencias
            if productos_no_homologados:
                result["warnings"].append(
                    f"{len(productos_no_homologados)} producto(s) no homologado(s) omitido(s)"
                )
                logger.warning(f"⚠️ {len(productos_no_homologados)} productos no homologados omitidos")
            
            if productos_sin_cantidad:
                result["warnings"].append(
                    f"{len(productos_sin_cantidad)} producto(s) con cantidad 0 omitido(s)"
                )
                logger.warning(f"⚠️ {len(productos_sin_cantidad)} productos con cantidad 0 omitidos")
            
            if not procesamientos_validos:
                raise ValueError(
                    f"No hay productos válidos para crear la OC. "
                    f"Productos no homologados: {len(productos_no_homologados)}, "
                    f"Productos sin cantidad: {len(productos_sin_cantidad)}"
                )
            
            # 5. Mapear empresa → proveedor
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
            result["proveedor"] = proveedor
            
            # 6. Determinar bodega para la OC
            codigo_bodega = None
            try:
                # Intentar determinar desde distribuciones o origen_traslado
                from ..services.oc_sap_service import OCSAPService
                oc_sap_service = OCSAPService()
                
                # Crear una cabecera temporal para usar el método estático
                cabecera_temporal = {"pedido_id": pedido_id}
                codigo_bodega = oc_sap_service.determinar_bodega_desde_pedido(
                    cabecera_temporal,
                    oc_repo
                )
                if codigo_bodega:
                    logger.info(f"📍 Bodega determinada para OC: {codigo_bodega}")
                else:
                    logger.warning(f"⚠️ No se pudo determinar bodega para el pedido {pedido_id}")
            except Exception as e:
                logger.warning(f"⚠️ Error al determinar bodega: {e}")
            
            # 7. Transformar cabecera
            oc_cabecera_data = self._to_orden_compra_cabecera_from_pedido(
                pedido_cabecera,
                proveedor,
                codigo_bodega
            )
            oc_cabecera_data["estado"] = "PENDIENTE"
            
            if existing_oc_id:
                # ACTUALIZAR OC existente (UPSERT)
                logger.info(f"🔄 Actualizando OC existente: {existing_oc_id}")
                
                oc_repo.update_cabecera(existing_oc_id, oc_cabecera_data)
                result["oc_id"] = existing_oc_id
                result["cabecera_insertada"] = False
                result["cabecera_actualizada"] = True
                
                # Eliminar detalles antiguos
                detalles_eliminados = oc_repo.delete_detalles(existing_oc_id)
                logger.debug(f"   → {detalles_eliminados} detalles antiguos eliminados")
                
                oc_id = existing_oc_id
            else:
                # INSERTAR nueva OC
                oc_id = oc_repo.insert_cabecera(oc_cabecera_data)
                result["oc_id"] = oc_id
                result["cabecera_insertada"] = True
                result["cabecera_actualizada"] = False
                logger.info(f"✅ Orden de compra cabecera creada: {oc_id} para pedido {pedido_id}")
            
            # 8. Transformar y preparar detalles (mapeo directo, sin conversiones)
            oc_detalles = []
            for proc in procesamientos_validos:
                oc_detalle = self._to_orden_compra_detalle_from_procesamiento(
                    proc, 
                    oc_id,
                    conn=conn,  # ⭐ Pasar conexión para obtener bodega
                    pedido_id=pedido_id  # ⭐ Pasar pedido_id para obtener bodega
                )
                
                # Validar campos mínimos requeridos
                if oc_detalle.get("sku_sap") and oc_detalle.get("cantidad_sap") is not None:
                    oc_detalles.append(oc_detalle)
                else:
                    logger.warning(
                        f"⚠️ Detalle omitido por falta de datos: "
                        f"SKU={oc_detalle.get('sku_sap')}, "
                        f"Cantidad={oc_detalle.get('cantidad_sap')}"
                    )
            
            if not oc_detalles:
                raise ValueError("No se pudo crear ninguna línea de detalle válida para la OC")
            
            # 9. Insertar detalles (tanto para INSERT como UPDATE)
            detalles_insertados = oc_repo.insert_detalles(oc_id, oc_detalles)
            result["detalles_insertados"] = detalles_insertados
            result["total_lineas"] = len(oc_detalles)
            
            # 10. Generar JSON SAP (para envío posterior y para debugging -2028)
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
                    )
                    result["sap_request_json"] = sap_request_json
                    # DESACTIVADO: Descarga de ODC en JSON a output/ ya no es necesaria
                    # try:
                    #     output_dir = PROJECT_ROOT / "output"
                    #     output_dir.mkdir(parents=True, exist_ok=True)
                    #     out_file = output_dir / f"odc_{oc_id}.json"
                    #     with open(out_file, "w", encoding="utf-8") as f:
                    #         json.dump(sap_request_json, f, ensure_ascii=False, indent=2, default=str)
                    #     logger.info(f"📥 ODC guardada en {out_file}")
                    # except Exception as e:
                    #     logger.warning(f"⚠️ No se pudo guardar ODC en output/: {e}")
                    # Log resumido en INFO para ver CardCode, ítems y bodegas sin DEBUG
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
            
            accion = "actualizada" if result.get("cabecera_actualizada") else "creada"
            logger.info(
                f"✅ OC {accion}: {oc_id} para pedido {pedido_id} "
                f"(detalles: {detalles_insertados}/{len(procesamientos_validos)})"
            )
            return result
