"""
Servicio para crear Solicitudes de Transferencia (Stock Transfer Orders) en SAP.
FASE 5: Generación de Solicitudes de Transferencia desde distribución confirmada por tienda.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..connection import get_db_connection_context
from ..repositories.pedido_repository import PedidoRepository
from ..repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
from ..repositories.orden_compra_repository import OrdenCompraRepository
from ..repositories.pedido_sap_procesamiento_repository import PedidoSAPProcesamientoRepository
from ..clients.sap_service_layer_client import SAPServiceLayerClient
from ..mappers.sap_stock_transfer_mapper import SAPStockTransferMapper

logger = logging.getLogger(__name__)


class StockTransferService:
    """Servicio para crear Solicitudes de Transferencia en SAP."""
    
    def __init__(self):
        """Inicializa el servicio."""
        self.sap_client = SAPServiceLayerClient()
    
    def crear_solicitudes_transferencia_desde_pedido(
        self,
        pedido_id: str,
        oc_doc_num: Optional[int] = None,
        bodega_origen: Optional[str] = None,
        usuario_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Crea Solicitudes de Transferencia (Stock Transfer Orders) en SAP desde la distribución confirmada de un pedido.
        
        Proceso:
        1. Obtiene la distribución confirmada del pedido (por tienda)
        2. Obtiene los datos de procesamiento SAP (conversiones y códigos SAP)
        3. Agrupa por tienda
        4. Crea un Stock Transfer Order por tienda en SAP
        5. Registra los resultados
        
        Args:
            pedido_id: UUID del pedido
            oc_doc_num: Número de OC de SAP (DocNum) relacionada (opcional)
            bodega_origen: Código de bodega origen (si None, usa origen_traslado del pedido)
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
                
                # 2. Obtener bodega origen (del pedido o parámetro)
                if not bodega_origen:
                    bodega_origen = pedido_cabecera.get("origen_traslado") or "01"  # Default a "01" si no hay
                    logger.info(f"📍 Usando bodega origen del pedido: {bodega_origen}")
                else:
                    logger.info(f"📍 Usando bodega origen proporcionada: {bodega_origen}")
                
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
                
                # 5. Agrupar distribución por tienda
                distribucion_por_tienda: Dict[str, List[Dict[str, Any]]] = {}
                
                for producto_dist in productos_distribucion:
                    pedido_detalle_id = producto_dist.get("pedido_detalle_id")
                    procesamiento = mapa_procesamientos.get(pedido_detalle_id)
                    
                    if not procesamiento:
                        logger.warning(
                            f"⚠️ No hay procesamiento SAP para pedido_detalle_id: {pedido_detalle_id}"
                        )
                        continue
                    
                    # Obtener item_code_sap y cantidad_sap desde procesamiento
                    item_code_sap = procesamiento.get("item_code_sap")
                    cantidad_sap = procesamiento.get("cantidad_sap")
                    
                    if not item_code_sap or cantidad_sap is None:
                        logger.warning(
                            f"⚠️ Procesamiento incompleto para pedido_detalle_id: {pedido_detalle_id}"
                        )
                        continue
                    
                    # Procesar distribuciones por tienda de este producto
                    distribuciones = producto_dist.get("distribuciones", [])
                    cantidad_total_distribuida = sum(d.get("cantidad_asignada", 0) for d in distribuciones)
                    
                    if cantidad_total_distribuida == 0:
                        continue
                    
                    # Calcular factor de conversión para distribuir cantidad_sap proporcionalmente
                    cantidad_original_total = producto_dist.get("cantidad_total_solicitada", cantidad_total_distribuida)
                    factor_conversion = cantidad_sap / cantidad_original_total if cantidad_original_total > 0 else 1
                    
                    for dist in distribuciones:
                        tienda_id = dist.get("tienda_id")
                        tienda_codigo = dist.get("tienda_codigo")
                        cantidad_asignada = dist.get("cantidad_asignada", 0)
                        
                        if cantidad_asignada <= 0:
                            continue
                        
                        # Convertir cantidad_asignada a unidades SAP proporcionalmente
                        cantidad_sap_asignada = cantidad_asignada * factor_conversion
                        
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
                            "warehouse_code": tienda_codigo  # Usar código de tienda como warehouse code
                        })
                
                if not distribucion_por_tienda:
                    raise ValueError("No hay distribución válida por tienda para crear transferencias")
                
                result["total_tiendas"] = len(distribucion_por_tienda)
                logger.info(f"📦 Creando {result['total_tiendas']} Solicitud(es) de Transferencia para {len(distribucion_por_tienda)} tienda(s)...")
                
                # 6. Convertir a formato SAP usando mapper
                stock_transfers_json = SAPStockTransferMapper.to_sap_stock_transfer(
                    pedido_data=pedido_cabecera,
                    distribucion_por_tienda=distribucion_por_tienda,
                    bodega_origen=bodega_origen,
                    oc_doc_num=oc_doc_num,
                    usuario_id=usuario_id,
                    pedido_id=pedido_id
                )
                
                # 7. Crear cada Stock Transfer Order en SAP
                for idx, stock_transfer_json in enumerate(stock_transfers_json):
                    tienda_codigo = stock_transfer_json.get("ToWarehouse", "N/A")
                    tienda_id = list(distribucion_por_tienda.keys())[idx]
                    
                    logger.info(f"🔄 Creando Solicitud de Transferencia {idx+1}/{len(stock_transfers_json)} para tienda {tienda_codigo}...")
                    
                    sap_response = self.sap_client.create_stock_transfer(stock_transfer_json)
                    
                    resultado_tienda = {
                        "tienda_id": tienda_id,
                        "tienda_codigo": tienda_codigo,
                        "success": False,
                        "doc_entry": None,
                        "doc_num": None,
                        "error": None
                    }
                    
                    if sap_response and sap_response.get("success"):
                        resultado_tienda["success"] = True
                        resultado_tienda["doc_entry"] = sap_response.get("doc_entry")
                        resultado_tienda["doc_num"] = sap_response.get("doc_num")
                        result["transferencias_creadas"] += 1
                        logger.info(
                            f"✅ Solicitud de Transferencia creada para tienda {tienda_codigo}: "
                            f"DocEntry={resultado_tienda['doc_entry']}, DocNum={resultado_tienda['doc_num']}"
                        )
                    else:
                        error_msg = sap_response.get("error", "Error desconocido") if sap_response else "No se recibió respuesta de SAP"
                        resultado_tienda["error"] = error_msg
                        result["transferencias_errores"] += 1
                        logger.error(f"❌ Error al crear Solicitud de Transferencia para tienda {tienda_codigo}: {error_msg}")
                    
                    result["resultados"].append(resultado_tienda)
                
                # 8. Determinar éxito general
                result["success"] = result["transferencias_creadas"] > 0
                
                if result["success"]:
                    logger.info(
                        f"✅ Proceso completado: {result['transferencias_creadas']}/{result['total_tiendas']} "
                        f"Solicitud(es) de Transferencia creada(s)"
                    )
                    if result["transferencias_errores"] > 0:
                        logger.warning(
                            f"⚠️ {result['transferencias_errores']} Solicitud(es) de Transferencia con errores"
                        )
                else:
                    logger.error(f"❌ No se pudo crear ninguna Solicitud de Transferencia")
                
                return result
                
        except Exception as e:
            logger.error(f"❌ Error al crear Solicitudes de Transferencia: {e}", exc_info=True)
            result["error"] = str(e)
            return result
