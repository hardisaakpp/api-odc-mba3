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
from ..services.bodega_sap_service import BodegaSAPService

logger = logging.getLogger(__name__)


class StockTransferService:
    """Servicio para crear Solicitudes de Transferencia en SAP."""
    
    def __init__(self):
        """Inicializa el servicio."""
        self.sap_client = SAPServiceLayerClient()
    
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
    
    def crear_solicitudes_transferencia_desde_pedido(
        self,
        pedido_id: str,
        oc_doc_num: Optional[int] = None,
        bodega_origen: Optional[str] = None,
        usuario_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Crea Solicitudes de Transferencia (Stock Transfer Orders) en SAP desde la distribución confirmada de un pedido.
        
        ⭐ IMPORTANTE: Las Solicitudes de Transferencia se crean desde bodega origen hacia TIENDAS.
        - Origen: Bodega (del campo origen_traslado del pedido, ej: OUT-CD, RG-CD, RL-CD)
        - Destino: TIENDAS (es_bodega=False), NO bodegas
        - Las bodegas (OUT-CD, RG-CD, RL-CD) se excluyen como destino para evitar transferencias de bodega a bodega
        - Cada bodega tiene sus propias tiendas
        
        Proceso:
        1. Obtiene la distribución confirmada del pedido
        2. Obtiene los datos de procesamiento SAP (conversiones y códigos SAP)
        3. Valida que todas las tiendas destino existan en SAP (previene errores de "No matching records found")
        4. Filtra solo distribuciones de TIENDAS (es_bodega=False)
        5. Excluye bodegas como destino (evita ST de bodega a bodega)
        6. Valida que destino no sea la misma bodega origen
        7. Valida que cada tienda pertenezca a la bodega origen (basado en prefijos: TRL-→RL-CD, TOUT-→OUT-CD, RG-→RG-CD)
        8. Agrupa por tienda
        9. Crea un Stock Transfer Order por tienda en SAP
        10. Registra los resultados
        
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
                # ⭐ IMPORTANTE: Guardar código exacto de SAP (WhsCode) para usar en las STs
                tiendas_validas_en_sap = set()  # Códigos normalizados para validación
                mapeo_codigo_exacto_sap = {}  # Mapeo: código_normalizado → código_exacto_SAP (WhsCode)
                
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
                            
                            tiendas_validas_en_sap.add(codigo_normalizado)
                            mapeo_codigo_exacto_sap[codigo_normalizado] = codigo_exacto_sap
                            
                            logger.info(
                                f"✅ Tienda validada en SAP: '{codigo}' → WhsCode='{codigo_exacto_sap}', "
                                f"Nombre='{info.get('WhsName', 'N/A')}'"
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
                    
                    # Obtener item_code_sap y cantidad_sap desde procesamiento
                    item_code_sap = procesamiento.get("item_code_sap")
                    cantidad_sap = procesamiento.get("cantidad_sap")
                    
                    if not item_code_sap or cantidad_sap is None:
                        logger.warning(
                            f"⚠️ Procesamiento incompleto para pedido_detalle_id: {pedido_detalle_id}"
                        )
                        continue
                    
                    # Procesar distribuciones por TIENDA de este producto
                    distribuciones = producto_dist.get("distribuciones", [])
                    # ⭐ CORRECCIÓN: Filtrar solo distribuciones de TIENDAS (es_bodega=False)
                    distribuciones_tiendas = [d for d in distribuciones if not d.get("es_bodega", False)]
                    
                    if not distribuciones_tiendas:
                        continue
                    
                    cantidad_total_distribuida_tiendas = sum(d.get("cantidad_asignada", 0) for d in distribuciones_tiendas)
                    
                    if cantidad_total_distribuida_tiendas == 0:
                        continue
                    
                    # Calcular factor de conversión para distribuir cantidad_sap proporcionalmente
                    cantidad_original_total = producto_dist.get("cantidad_total_solicitada", cantidad_total_distribuida_tiendas)
                    factor_conversion = cantidad_sap / cantidad_original_total if cantidad_original_total > 0 else 1
                    
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
                        
                        # Convertir cantidad_asignada a unidades SAP proporcionalmente
                        cantidad_sap_asignada = cantidad_asignada * factor_conversion
                        
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
                    pedido_id=pedido_id
                )
                
                # 7. Crear cada Stock Transfer Order en SAP
                for idx, stock_transfer_json in enumerate(stock_transfers_json):
                    tienda_codigo = stock_transfer_json.get("ToWarehouse", "N/A")
                    tienda_id = list(distribucion_por_tienda.keys())[idx]
                    
                    logger.info(
                        f"🔄 Creando Solicitud de Transferencia {idx+1}/{len(stock_transfers_json)}: "
                        f"{bodega_origen} → {tienda_codigo}..."
                    )
                    
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
                            f"✅ Solicitud de Transferencia creada: {bodega_origen} → {tienda_codigo} "
                            f"(DocEntry={resultado_tienda['doc_entry']}, DocNum={resultado_tienda['doc_num']})"
                        )
                    else:
                        error_msg = sap_response.get("error", "Error desconocido") if sap_response else "No se recibió respuesta de SAP"
                        resultado_tienda["error"] = error_msg
                        result["transferencias_errores"] += 1
                        logger.error(
                            f"❌ Error al crear Solicitud de Transferencia: {bodega_origen} → {tienda_codigo}: {error_msg}"
                        )
                    
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
