"""
Servicio para enviar órdenes de compra a SAP Service Layer.

Este servicio orquesta la construcción del JSON y el envío de ODC a SAP.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from ..repositories.orden_compra_repository import OrdenCompraRepository
from ..clients.sap_service_layer_client import SAPServiceLayerClient
from ..mappers.sap_oc_mapper import SAPOCMapper

logger = logging.getLogger(__name__)


class OCSAPService:
    """Servicio para enviar órdenes de compra a SAP Service Layer."""
    
    def __init__(self):
        """Inicializa el servicio."""
        self.sap_client = SAPServiceLayerClient()
    
    @staticmethod
    def determinar_bodega_desde_pedido(
        oc_cabecera: Dict[str, Any],
        oc_repo: 'OrdenCompraRepository'
    ) -> Optional[str]:
        """
        Determina el código de bodega (WhsCode) a usar en la ODC.
        
        Prioridad:
        1. Si hay distribuciones con es_bodega=True y cantidad > 0, usar la primera bodega encontrada
        2. Si no hay bodegas en distribuciones, usar origen_traslado del pedido
        3. Si no hay origen_traslado, retornar None
        
        Args:
            oc_cabecera: Diccionario con datos de orden_compra_cabecera
            oc_repo: Repositorio de órdenes de compra (para acceder a la conexión)
            
        Returns:
            Código de bodega (ej: "RL-CD", "OUT-CD", "REG-CD") o None si no se puede determinar
        """
        pedido_id = oc_cabecera.get("pedido_id")
        if not pedido_id:
            # Si no hay pedido_id, intentar usar origen_traslado si existe en la cabecera
            # (para compatibilidad con ODCs legacy que vienen de despachos)
            logger.debug("⚠️ OC sin pedido_id, no se puede determinar bodega desde distribuciones")
            return None
        
        try:
            # Usar la conexión del repositorio existente
            conn = oc_repo.conn
            from ..repositories.pedido_repository import PedidoRepository
            from ..repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
            
            pedido_repo = PedidoRepository(conn)
            dist_repo = DistribucionConfirmadaRepository(conn)
            
            # 1. Obtener pedido completo para acceder a origen_traslado
            pedido_data = pedido_repo.get_pedido_completo(pedido_id)
            if not pedido_data:
                logger.warning(f"⚠️ No se encontró pedido {pedido_id} para determinar bodega")
                return None
            
            pedido_cabecera = pedido_data.get("cabecera", {})
            origen_traslado = pedido_cabecera.get("origen_traslado")
            
            # 2. Intentar obtener distribución confirmada para buscar bodegas con cantidad > 0
            try:
                version_actual = dist_repo.get_version_actual(pedido_id)
                if version_actual > 0:
                    distribucion_data = dist_repo.get_distribucion_completa(pedido_id, version_actual)
                    productos_distribucion = distribucion_data.get("productos", [])
                    
                    # Buscar la primera bodega (es_bodega=True) con cantidad_asignada > 0
                    bodegas_encontradas = set()
                    for producto in productos_distribucion:
                        distribuciones = producto.get("distribuciones", [])
                        for dist in distribuciones:
                            if dist.get("es_bodega", False):
                                cantidad_asignada = dist.get("cantidad_asignada", 0)
                                if cantidad_asignada and cantidad_asignada > 0:
                                    tienda_codigo = dist.get("tienda_codigo")
                                    if tienda_codigo:
                                        bodegas_encontradas.add(tienda_codigo.strip().upper())
                    
                    # Si encontramos bodegas con cantidad > 0, usar la primera
                    if bodegas_encontradas:
                        bodega_seleccionada = list(bodegas_encontradas)[0]
                        logger.info(
                            f"📍 Bodega determinada desde distribuciones: {bodega_seleccionada} "
                            f"(encontradas: {', '.join(bodegas_encontradas)})"
                        )
                        return bodega_seleccionada
            except Exception as e:
                logger.warning(f"⚠️ No se pudo obtener distribución confirmada: {e}")
            
            # 3. Fallback: usar origen_traslado del pedido
            if origen_traslado and origen_traslado.strip():
                bodega_fallback = origen_traslado.strip().upper()
                logger.info(f"📍 Bodega determinada desde origen_traslado: {bodega_fallback}")
                return bodega_fallback
            
            logger.warning(f"⚠️ No se pudo determinar bodega para pedido {pedido_id}")
            return None
                
        except Exception as e:
            logger.error(f"❌ Error al determinar bodega desde pedido: {e}", exc_info=True)
            return None
    
    def enviar_oc_a_sap(
        self,
        oc_repo: OrdenCompraRepository,
        oc_id: str,
        warehouse_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Envía una orden de compra a SAP Service Layer.
        
        Proceso:
        1. Obtiene la cabecera y detalles de la ODC desde la base de datos
        2. Convierte los datos a formato JSON de SAP
        3. Envía la ODC a SAP Service Layer
        4. Actualiza el estado y número de OC en la base de datos
        
        Args:
            oc_repo: Repositorio de órdenes de compra
            oc_id: UUID de la orden de compra a enviar
            warehouse_code: Código de bodega (opcional)
            
        Returns:
            Diccionario con el resultado:
            {
                "success": True/False,
                "oc_id": "uuid",
                "doc_entry": 123,  # DocEntry de SAP
                "doc_num": 456,    # DocNum de SAP
                "error": "mensaje de error"  # Solo si success=False
            }
        """
        result = {
            "success": False,
            "oc_id": oc_id,
            "doc_entry": None,
            "doc_num": None,
            "error": None
        }
        
        try:
            # 1. Obtener cabecera de la ODC
            oc_cabecera = oc_repo.get_existing_cabecera(oc_id)
            if not oc_cabecera:
                error_msg = f"No se encontró orden de compra con ID: {oc_id}"
                result["error"] = error_msg
                result["error_message"] = error_msg  # Alias para compatibilidad con frontend
                result["error_source"] = "BACKEND"
                logger.error(f"❌ {result['error']}")
                return result
            
            # Verificar que esté en estado PENDIENTE
            estado_actual = oc_cabecera.get("estado")
            if estado_actual != "PENDIENTE":
                error_msg = f"La ODC no está en estado PENDIENTE (estado actual: {estado_actual})"
                result["error"] = error_msg
                result["error_message"] = error_msg  # Alias para compatibilidad con frontend
                result["error_source"] = "BACKEND"
                logger.warning(f"⚠️ {result['error']}")
                return result
            
            # 2. Obtener detalles de la ODC
            oc_detalles = oc_repo.get_detalles(oc_id)
            if not oc_detalles:
                error_msg = f"No se encontraron detalles para la ODC: {oc_id}"
                result["error"] = error_msg
                result["error_message"] = error_msg  # Alias para compatibilidad con frontend
                result["error_source"] = "BACKEND"  # Indicar que el error viene del backend
                logger.error(f"❌ {result['error']}")
                try:
                    oc_repo.update_estado(
                        oc_id, 
                        "ERROR",
                        respuesta_sap=error_msg,
                        error_message=error_msg,
                        error_source="BACKEND"
                    )
                except Exception:
                    pass
                return result
            
            logger.info(f"📦 Preparando envío de ODC {oc_id} a SAP ({len(oc_detalles)} líneas)")
            
            # 2.5. Determinar bodega si no se proporcionó
            if not warehouse_code:
                # Intentar obtener de la cabecera si ya está persistida
                warehouse_code = oc_cabecera.get("codigo_bodega")
                if warehouse_code:
                    logger.info(f"📍 Bodega obtenida de la cabecera: {warehouse_code}")
                else:
                    # Determinar desde el pedido
                    warehouse_code = self.determinar_bodega_desde_pedido(oc_cabecera, oc_repo)
                    if warehouse_code:
                        logger.info(f"📍 Bodega determinada automáticamente: {warehouse_code}")
                        # Persistir la bodega determinada en la cabecera
                        try:
                            oc_repo.update_cabecera(oc_id, {"codigo_bodega": warehouse_code})
                            logger.info(f"✅ Bodega persistida en orden_compra_cabecera: {warehouse_code}")
                        except Exception as e:
                            logger.warning(f"⚠️ No se pudo persistir bodega en la cabecera: {e}")
                    else:
                        logger.warning(f"⚠️ No se pudo determinar bodega para ODC {oc_id}. La ODC se enviará sin WarehouseCode.")
            
            # 3. Validar antes de crear OC
            validacion = self._validar_antes_de_crear_oc(oc_cabecera, oc_detalles)
            
            if not validacion["valid"]:
                error_msg = f"Validación falló: {'; '.join(validacion['errors'])}"
                result["error"] = error_msg
                result["error_message"] = error_msg
                result["error_source"] = "BACKEND"
                logger.error(f"❌ {error_msg}")
                try:
                    oc_repo.update_estado(
                        oc_id, 
                        "ERROR",
                        respuesta_sap=error_msg,
                        error_message=error_msg,
                        error_source="BACKEND"
                    )
                except Exception:
                    pass
                return result
            
            # Log warnings si existen
            if validacion["warnings"]:
                for warning in validacion["warnings"]:
                    logger.warning(warning)
            
            # 3.5. Prevalidación contra SAP Service Layer (datos maestros)
            # Valida que proveedor, artículos y bodegas existan en SAP antes de crear la OC
            logger.info("🔍 Paso 3.5: Prevalidación contra SAP Service Layer...")
            prevalidacion = self._precheck_against_service_layer(oc_cabecera, oc_detalles)
            
            if not prevalidacion["valid"]:
                # Construir mensaje de error detallado
                errores_prevalidacion = prevalidacion.get("errors", [])
                error_msg = f"Prevalidación SAP falló: {'; '.join(errores_prevalidacion)}"
                
                result["error"] = error_msg
                result["error_message"] = error_msg
                result["error_source"] = "SAP_VALIDATION"
                result["prevalidacion_detalle"] = prevalidacion.get("detalle_validacion")
                result["prevalidacion_resumen"] = prevalidacion.get("resumen")
                
                logger.error(f"❌ {error_msg}")
                try:
                    oc_repo.update_estado(
                        oc_id,
                        "ERROR",
                        respuesta_sap=error_msg,
                        error_message=error_msg,
                        error_source="SAP_VALIDATION"
                    )
                except Exception:
                    pass
                return result
            
            # Log warnings de prevalidación si existen
            if prevalidacion.get("warnings"):
                for warning in prevalidacion["warnings"]:
                    logger.warning(f"⚠️ Prevalidación: {warning}")
            
            # 4. Convertir a formato JSON de SAP
            try:
                purchase_order_json = SAPOCMapper.to_sap_purchase_order(
                    oc_cabecera,
                    oc_detalles,
                    warehouse_code,
                    usuario_id=oc_cabecera.get("creado_por"),  # Usuario de la cabecera
                    pedido_id=oc_cabecera.get("pedido_id")     # Pedido relacionado
                )
            except ValueError as e:
                error_msg = f"Error al construir JSON de SAP: {str(e)}"
                result["error"] = error_msg
                result["error_message"] = error_msg  # Alias para compatibilidad con frontend
                result["error_source"] = "BACKEND"
                logger.error(f"❌ Error al construir JSON: {result['error']}")
                try:
                    oc_repo.update_estado(
                        oc_id, 
                        "ERROR",
                        respuesta_sap=error_msg,
                        error_message=error_msg,
                        error_source="BACKEND"
                    )
                except Exception:
                    pass
                return result
            except Exception as e:
                error_msg = f"Error inesperado al construir JSON: {str(e)}"
                result["error"] = error_msg
                result["error_message"] = error_msg  # Alias para compatibilidad con frontend
                result["error_source"] = "BACKEND"
                logger.error(f"❌ Error inesperado: {result['error']}", exc_info=True)
                try:
                    oc_repo.update_estado(
                        oc_id, 
                        "ERROR",
                        respuesta_sap=error_msg,
                        error_message=error_msg,
                        error_source="BACKEND"
                    )
                except Exception:
                    pass
                return result
            
            # 5. Enviar a SAP Service Layer
            logger.info(f"🔄 Enviando ODC {oc_id} a SAP Service Layer...")
            sap_response = self.sap_client.create_purchase_order(purchase_order_json)
            
            if not sap_response:
                error_msg = "No se recibió respuesta de SAP Service Layer"
                result["error"] = error_msg
                result["error_message"] = error_msg  # Alias para compatibilidad con frontend
                result["error_source"] = "SAP_CONNECTION"
                logger.error(f"❌ {result['error']}")
                try:
                    oc_repo.update_estado(
                        oc_id, 
                        "ERROR",
                        respuesta_sap=error_msg,
                        error_message=error_msg,
                        error_source="SAP_CONNECTION"
                    )
                except Exception:
                    pass
                return result
            
            if not sap_response.get("success"):
                # Extraer información detallada del error de SAP
                error_msg = sap_response.get("error", "Error desconocido")
                error_code = sap_response.get("error_code")  # Código de error de SAP (ej: -4013)
                sap_error_details = sap_response.get("sap_error_details")  # Respuesta completa de SAP
                
                # Construir mensaje de error con código si está disponible
                if error_code:
                    error_final = f"{error_msg} (Código SAP: {error_code})"
                else:
                    error_final = f"Error al crear Purchase Order en SAP: {error_msg}"
                
                result["error"] = error_final
                result["error_message"] = error_final  # Alias para compatibilidad con frontend
                result["error_code"] = error_code
                result["sap_error_details"] = sap_error_details
                result["error_source"] = "SAP"  # Indicar que el error viene de SAP
                
                logger.error(f"❌ {result['error']}")
                try:
                    # Actualizar estado a ERROR y persistir información del error
                    oc_repo.update_estado(
                        oc_id, 
                        "ERROR",
                        respuesta_sap=error_final,
                        error_message=error_final,
                        error_code=str(error_code) if error_code else None,
                        error_source="SAP"
                    )
                except Exception:
                    pass
                return result
            
            # 6. Actualizar estado y referencias de SAP en la base de datos
            doc_entry = sap_response.get("doc_entry")
            doc_num = sap_response.get("doc_num")
            sap_response_data = sap_response.get("data")  # Respuesta completa de SAP
            
            try:
                # Preparar mensaje de respuesta SAP
                mensaje_sap = f"Orden creada exitosamente. DocNum: {doc_num}"
                if sap_response_data and isinstance(sap_response_data, dict):
                    # Si hay un mensaje en la respuesta, usarlo
                    mensaje_sap = sap_response_data.get("message", mensaje_sap)
                
                # Actualizar estado a ENVIADA y guardar respuesta de SAP (incluyendo DocEntry)
                oc_repo.update_estado(
                    oc_id,
                    "ENVIADA",
                    numero_oc_sap=str(doc_num) if doc_num else None,
                    doc_entry=doc_entry,  # ⭐ Persistir DocEntry
                    respuesta_sap=mensaje_sap,
                    error_message=None,
                    error_code=None,
                    error_source=None
                )
                
                result["success"] = True
                result["doc_entry"] = doc_entry
                result["doc_num"] = doc_num
                result["doc_date"] = sap_response.get("doc_date")
                result["sap_response"] = sap_response_data
                result["error_source"] = None
                result["message"] = mensaje_sap

                doc_date_str = f", DocDate={result['doc_date']}" if result.get("doc_date") else ""
                logger.info(
                    f"✅ ODC {oc_id} enviada exitosamente: "
                    f"DocEntry={doc_entry}, DocNum={doc_num}{doc_date_str}"
                )

                # 6.1. Inventory Transfer Requests (1 por bodega destino) — POST /InventoryTransferRequests
                doc_date_val = sap_response.get("doc_date")
                doc_date_itr = None
                if isinstance(doc_date_val, str) and len(doc_date_val) >= 10:
                    doc_date_itr = doc_date_val[:10]
                if not doc_date_itr:
                    doc_date_itr = datetime.utcnow().strftime("%Y-%m-%d")
                
                # ⭐ REGLA CLARA: FromWarehouse prioridad
                # 1. codigo_bodega de la OC (viene de Excel) → prioridad
                # 2. SAP_ST_FROM_WAREHOUSE (config) → fallback solo si no hay bodega en OC
                # 3. Si ninguno → error (no crear ITR)
                from_wh = None
                try:
                    from src.config import SAP_ST_FROM_WAREHOUSE
                    # Prioridad 1: bodega de la OC (viene de Excel)
                    from_wh = (oc_cabecera.get("codigo_bodega") or "").strip()
                    # Prioridad 2: SAP_ST_FROM_WAREHOUSE solo como fallback
                    if not from_wh:
                        from_wh = (SAP_ST_FROM_WAREHOUSE or "").strip()
                        if from_wh:
                            logger.info(f"📍 Usando SAP_ST_FROM_WAREHOUSE como fallback: {from_wh}")
                except Exception:
                    from_wh = (oc_cabecera.get("codigo_bodega") or "").strip()
                
                if from_wh and oc_detalles:
                    try:
                        from ..mappers.sap_stock_transfer_mapper import SAPStockTransferMapper
                        itr_payloads = SAPStockTransferMapper.to_sap_inventory_transfer_requests_by_bodega(
                            oc_detalles=oc_detalles,
                            from_warehouse=from_wh,
                            doc_date=doc_date_itr,
                            due_date=doc_date_itr,
                            oc_doc_num=doc_num,
                        )
                        itr_created = 0
                        itr_errors = 0
                        itr_results = []
                        logger.info(f"📤 Enviando {len(itr_payloads)} Inventory Transfer Request(s) por bodega a SAP...")
                        for idx, pl in enumerate(itr_payloads):
                            to_warehouse = pl.get("ToWarehouse", "UNKNOWN")
                            logger.debug(f"🔄 Enviando ITR {idx+1}/{len(itr_payloads)} a SAP: {from_wh} → {to_warehouse}...")
                            resp = self.sap_client.create_stock_transfer(pl)
                            
                            # ✅ SOLO considerar creado si hay DocEntry confirmado
                            if resp and resp.get("success") and resp.get("doc_entry"):
                                itr_created += 1
                                itr_results.append({
                                    "ToWarehouse": to_warehouse,
                                    "doc_entry": resp.get("doc_entry"),
                                    "doc_num": resp.get("doc_num"),
                                    "success": True,
                                })
                                logger.info(
                                    f"✅ Inventory Transfer Request CREADO en SAP: {from_wh} → {to_warehouse} "
                                    f"(DocEntry={resp.get('doc_entry')}, DocNum={resp.get('doc_num')})"
                                )
                            else:
                                itr_errors += 1
                                error_msg = resp.get("error") if resp else "Sin respuesta de SAP"
                                itr_results.append({
                                    "ToWarehouse": to_warehouse,
                                    "success": False,
                                    "error": error_msg,
                                })
                                logger.warning(
                                    f"⚠️ Inventory Transfer Request NO creado: {from_wh} → {to_warehouse}: {error_msg}"
                                )
                        result["inventory_transfer_requests"] = {
                            "created": itr_created,
                            "errors": itr_errors,
                            "total": len(itr_payloads),
                            "resultados": itr_results,
                        }
                        if itr_created:
                            logger.info(
                                f"✅ Inventory Transfer Requests creados en SAP: {itr_created}/{len(itr_payloads)} "
                                f"(DocEntry confirmado para cada uno)"
                            )
                        if itr_errors:
                            logger.warning(
                                f"⚠️ {itr_errors} Inventory Transfer Request(s) NO se pudieron crear en SAP"
                            )
                        if itr_created == 0:
                            logger.warning(
                                f"⚠️ No se creó ningún Inventory Transfer Request en SAP "
                                f"(0/{len(itr_payloads)} exitosos)"
                            )
                    except Exception as e:
                        logger.warning(f"⚠️ No se pudieron crear Inventory Transfer Requests (no crítico): {e}")
                        result["inventory_transfer_requests_error"] = str(e)

                # ============================================================
                # FASE 6: Notificación y cierre
                # ============================================================
                
                # 7. Enviar correo al proveedor (no bloquea si falla)
                try:
                    from src.utils.email_notifier import send_oc_to_supplier
                    from src.config import EMAIL_PROVEEDOR_PRUEBAS
                    
                    # Durante fase de pruebas, usar email configurado
                    # TODO: En producción, obtener desde tabla cliente usando CardCode
                    proveedor_email = EMAIL_PROVEEDOR_PRUEBAS
                    
                    email_enviado = send_oc_to_supplier(
                        oc_cabecera=oc_cabecera,
                        oc_detalles=oc_detalles,
                        doc_num=doc_num,
                        doc_entry=doc_entry,
                        proveedor_email=proveedor_email
                    )
                    if email_enviado:
                        logger.info(f"📧 Email de ODC enviado al proveedor {oc_cabecera.get('proveedor')}")
                    else:
                        logger.warning(f"⚠️ No se pudo enviar email de ODC al proveedor (no crítico)")
                except Exception as e:
                    # NO fallar el proceso si el email falla
                    logger.warning(f"⚠️ Error al enviar email de ODC (no crítico): {e}")
                
                # 8. Crear Solicitudes de Transferencia (HU-04: Requerimiento de alta prioridad)
                pedido_id = oc_cabecera.get("pedido_id")
                if pedido_id:
                    try:
                        from .stock_transfer_service import StockTransferService
                        
                        # ⭐ Usar la bodega de la OC (codigo_bodega) en lugar de origen_traslado del pedido
                        # Esto asegura consistencia: la misma bodega usada para la OC se usa para las ST
                        bodega_oc = oc_cabecera.get("codigo_bodega")
                        if bodega_oc:
                            logger.info(f"📍 Usando bodega de la OC para ST: {bodega_oc}")
                        else:
                            logger.warning(f"⚠️ OC sin codigo_bodega, se usará origen_traslado del pedido")
                        
                        stock_transfer_service = StockTransferService()
                        resultado_transferencias = stock_transfer_service.crear_solicitudes_transferencia_desde_pedido(
                            pedido_id=pedido_id,
                            oc_doc_num=doc_num,
                            bodega_origen=bodega_oc,  # Usa codigo_bodega de la OC (prioridad sobre origen_traslado)
                            usuario_id=None
                        )
                        
                        if resultado_transferencias.get("success"):
                            logger.info(
                                f"✅ Inventory Transfer Requests creados en SAP: "
                                f"{resultado_transferencias['transferencias_creadas']}/{resultado_transferencias['total_tiendas']} "
                                f"para pedido {pedido_id} (DocEntry confirmado para cada uno)"
                            )
                            # Incluir warnings de éxito parcial (si algunos ITR fallaron)
                            if resultado_transferencias.get("warnings"):
                                logger.warning(
                                    f"⚠️ Advertencias en ITR de pedido {pedido_id}: "
                                    f"{'; '.join(resultado_transferencias['warnings'])}"
                                )
                            result["solicitudes_transferencia"] = resultado_transferencias
                        else:
                            error_type = resultado_transferencias.get("error_type", "desconocido")
                            error_msg = resultado_transferencias.get("error")
                            
                            # ⭐ FIX: Si no hay error de nivel superior, extraer de resultados individuales
                            if not error_msg:
                                resultados_st = resultado_transferencias.get("resultados", [])
                                errores_individuales = [
                                    f"{r.get('tienda_codigo', 'N/A')}: {r.get('error', 'Sin detalle')}"
                                    for r in resultados_st
                                    if not r.get("success") and r.get("error")
                                ]
                                error_msg = "; ".join(errores_individuales) if errores_individuales else "Error desconocido al crear Solicitudes de Transferencia"
                            
                            if error_type == "datos_maestros":
                                logger.warning(
                                    f"⚠️ Inventory Transfer Requests NO creados para pedido {pedido_id}: "
                                    f"validación de datos maestros fallida - {error_msg}"
                                )
                            elif error_type == "stock_insuficiente":
                                logger.warning(
                                    f"⚠️ Inventory Transfer Requests NO creados para pedido {pedido_id}: "
                                    f"validación de stock fallida - {error_msg}"
                                )
                            else:
                                logger.warning(
                                    f"⚠️ Inventory Transfer Requests NO creados para pedido {pedido_id}: {error_msg}"
                                )
                            result["solicitudes_transferencia"] = resultado_transferencias
                    except Exception as e:
                        # NO fallar el proceso si las solicitudes de transferencia fallan
                        logger.warning(f"⚠️ Error al crear Solicitudes de Transferencia (no crítico): {e}")
                        result["solicitudes_transferencia_error"] = str(e)
                
                # 8.1. Notificar a El Rayo para proceder con despacho y facturación (HU-04)
                try:
                    from src.utils.email_notifier import send_oc_ready_for_dispatch_notification
                    from ..repositories.pedido_repository import PedidoRepository
                    
                    # Obtener número de pedido si está disponible
                    pedido_numero = None
                    if pedido_id:
                        try:
                            pedido_repo_temp = PedidoRepository(oc_repo.conn)
                            pedido_data = pedido_repo_temp.get_pedido_completo(pedido_id)
                            if pedido_data and pedido_data.get("cabecera"):
                                pedido_numero = pedido_data["cabecera"].get("numero_pedido")
                        except Exception:
                            pass  # No crítico si falla
                    
                    # Obtener resultado de transferencias para incluir en la notificación
                    resultado_transferencias_notif = result.get("solicitudes_transferencia")
                    
                    email_enviado = send_oc_ready_for_dispatch_notification(
                        oc_cabecera=oc_cabecera,
                        doc_num=doc_num,
                        doc_entry=doc_entry,
                        solicitudes_transferencia=resultado_transferencias_notif,
                        pedido_numero=pedido_numero
                    )
                    if email_enviado:
                        logger.info(f"📧 Notificación de OC lista para despacho enviada a El Rayo (OC #{doc_num})")
                    else:
                        logger.warning(f"⚠️ No se pudo enviar notificación a El Rayo (no crítico)")
                except Exception as e:
                    # NO fallar el proceso si la notificación falla
                    logger.warning(f"⚠️ Error al enviar notificación a El Rayo (no crítico): {e}")
                
                # 9. Evaluar y actualizar estado del pedido según resultado de OC y ST
                if pedido_id:
                    try:
                        from ..repositories.pedido_repository import PedidoRepository
                        from .pedido_cierre_service import PedidoCierreService
                        
                        pedido_repo = PedidoRepository(oc_repo.conn)
                        cierre_service = PedidoCierreService()
                        
                        # Obtener resultado de ST (puede ser None si no se intentó crear)
                        resultado_st = result.get("solicitudes_transferencia")
                        
                        resultado_cierre = cierre_service.cerrar_pedido_si_corresponde(
                            pedido_id=pedido_id,
                            oc_repo=oc_repo,
                            pedido_repo=pedido_repo,
                            resultado_st=resultado_st
                        )
                        
                        if resultado_cierre.get("cerrado"):
                            logger.info(
                                f"✅ Pedido {pedido_id} cerrado automáticamente: "
                                f"{resultado_cierre['estado_anterior']} → {resultado_cierre['estado_nuevo']}"
                            )
                        elif resultado_cierre.get("estado_nuevo"):
                            logger.info(
                                f"📋 Pedido {pedido_id} actualizado: "
                                f"{resultado_cierre['estado_anterior']} → {resultado_cierre['estado_nuevo']}"
                            )
                    except Exception as e:
                        # NO fallar el proceso si el cierre falla
                        logger.warning(f"⚠️ Error al evaluar cierre de pedido (no crítico): {e}")
                
            except Exception as e:
                # Aunque falló la actualización, la OC se creó en SAP
                logger.warning(
                    f"⚠️ ODC creada en SAP pero error al actualizar estado: {e}. "
                    f"DocEntry={doc_entry}, DocNum={doc_num}"
                )
                result["success"] = True
                result["doc_entry"] = doc_entry
                result["doc_num"] = doc_num
                result["sap_response"] = sap_response_data  # Agregar respuesta completa de SAP
                result["error"] = f"Advertencia: Error al actualizar estado: {str(e)}"
                result["message"] = f"Orden creada exitosamente. DocNum: {doc_num}"
                # Intentar actualizar referencias SAP aunque haya fallado update_estado
                try:
                    oc_repo.update_sap_refs(oc_id, doc_entry=doc_entry, doc_num=str(doc_num) if doc_num else None)
                except Exception:
                    pass
            
            return result
            
        except Exception as e:
            error_msg = f"Error inesperado: {str(e)}"
            result["error"] = error_msg
            result["error_message"] = error_msg  # Alias para compatibilidad con frontend
            result["error_source"] = "BACKEND"
            logger.error(f"❌ Error al enviar ODC a SAP: {e}", exc_info=True)
            try:
                oc_repo.update_estado(
                    oc_id, 
                    "ERROR",
                    respuesta_sap=error_msg,
                    error_message=error_msg,
                    error_source="BACKEND"
                )
            except Exception:
                pass
            return result
    
    def _validar_antes_de_crear_oc(
        self,
        oc_cabecera: Dict[str, Any],
        oc_detalles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Valida que la OC esté lista para enviarse a SAP.
        
        Args:
            oc_cabecera: Datos de cabecera de la OC
            oc_detalles: Lista de detalles de la OC
            
        Returns:
            {
                "valid": bool,
                "errors": List[str],
                "warnings": List[str]
            }
        """
        errors = []
        warnings = []
        
        # Validación 1: No debe tener DocEntry (idempotencia)
        if oc_cabecera.get("doc_entry"):
            errors.append(
                f"La OC ya tiene DocEntry={oc_cabecera['doc_entry']}. "
                "No se puede recrear. (Idempotencia)"
            )
        
        # Validación 2: Debe tener detalles
        if not oc_detalles:
            errors.append("La OC no tiene líneas de detalle")
        
        # Validación 3: Todas las líneas deben tener cantidad > 0
        lineas_con_cantidad_cero = [
            d.get("sku_sap", "SKU desconocido")
            for d in oc_detalles 
            if d.get("cantidad_sap", 0) <= 0
        ]
        if lineas_con_cantidad_cero:
            errors.append(
                f"Líneas con cantidad <= 0: {', '.join(lineas_con_cantidad_cero)}"
            )
        
        # Validación 4: Debe tener proveedor (CardCode)
        if not oc_cabecera.get("proveedor"):
            errors.append("La OC no tiene proveedor (CardCode)")

        # Validación 5: codigo_bodega obligatorio por línea (solo detalle). No usar cabecera.
        lineas_sin_bodega = []
        for d in oc_detalles:
            if d.get("cantidad_sap", 0) <= 0:
                continue
            b = d.get("codigo_bodega") or d.get("warehouse_code")
            if not b or not str(b).strip():
                lineas_sin_bodega.append(d.get("sku_sap", "SKU desconocido"))
        if lineas_sin_bodega:
            errors.append(
                f"Líneas sin codigo_bodega en detalle: {', '.join(lineas_sin_bodega)}. "
                "Cada línea debe tener codigo_bodega; no se usa bodega de cabecera."
            )
        
        # Validación 6: Advertencia si viene de despacho (legacy)
        if oc_cabecera.get("despacho_id") and not oc_cabecera.get("pedido_id"):
            warnings.append(
                "⚠️ OC basada en despacho (legacy). "
                "Considerar migrar a flujo de pedido confirmado."
            )
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def _precheck_against_service_layer(
        self,
        oc_cabecera: Dict[str, Any],
        oc_detalles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Valida datos maestros contra SAP Service Layer ANTES de crear la OC.
        
        Esta validación consulta directamente Service Layer para detectar problemas
        que causarían errores genéricos (-2028) al intentar crear la Purchase Order.
        
        Validaciones:
        1. Proveedor (CardCode) existe en BusinessPartners
        2. Cada artículo (ItemCode) existe en Items
        3. Cada artículo es de compra (PurchaseItem = "tYES")
        4. Cada artículo está configurado en su bodega destino
        
        Args:
            oc_cabecera: Datos de cabecera de la OC
            oc_detalles: Lista de detalles de la OC
            
        Returns:
            {
                "valid": bool,
                "errors": List[str],  # Errores que bloquean la creación
                "warnings": List[str],  # Advertencias (no bloquean)
                "detalle_validacion": {
                    "proveedor": {...},
                    "articulos": {...}
                }
            }
        """
        errors = []
        warnings = []
        detalle = {
            "proveedor": {},
            "articulos": {}
        }
        
        logger.info("🔍 Iniciando prevalidación contra SAP Service Layer...")
        
        # ============================================================
        # 1. Validar Proveedor (Business Partner)
        # ============================================================
        proveedor = oc_cabecera.get("proveedor", "").strip()
        if proveedor:
            # Agregar prefijo 'P' si no lo tiene (convención SAP para proveedores)
            card_code = proveedor if proveedor.startswith('P') else f"P{proveedor}"
            
            logger.debug(f"🔍 Validando proveedor: {card_code}")
            bp_info = self.sap_client.get_business_partner(card_code)
            
            if bp_info is None:
                errors.append(f"Error de conexión al validar proveedor '{card_code}'")
                detalle["proveedor"] = {"error": "conexion", "card_code": card_code}
            elif bp_info.get("_error"):
                if bp_info.get("_error_type") == "no_existe":
                    errors.append(f"Proveedor '{card_code}' no existe en SAP BusinessPartners")
                else:
                    errors.append(bp_info.get("_error_message", f"Error al validar proveedor {card_code}"))
                detalle["proveedor"] = {"error": bp_info.get("_error_type"), "card_code": card_code}
            else:
                # Validar que no esté congelado
                if bp_info.get("Frozen") == "tYES":
                    errors.append(f"Proveedor '{card_code}' está CONGELADO en SAP (Frozen=tYES)")
                    detalle["proveedor"] = {"error": "congelado", "card_code": card_code}
                elif bp_info.get("Valid") == "tNO":
                    errors.append(f"Proveedor '{card_code}' no está activo en SAP (Valid=tNO)")
                    detalle["proveedor"] = {"error": "inactivo", "card_code": card_code}
                else:
                    detalle["proveedor"] = {
                        "valid": True,
                        "card_code": card_code,
                        "card_name": bp_info.get("CardName"),
                        "card_type": bp_info.get("CardType")
                    }
                    logger.info(f"✅ Proveedor validado: {card_code} - {bp_info.get('CardName')}")
        
        # ============================================================
        # 2. Validar Artículos (Items) y Bodegas
        # ============================================================
        articulos_validados = 0
        articulos_con_error = 0
        
        for idx, detalle_linea in enumerate(oc_detalles, start=1):
            sku = detalle_linea.get("sku_sap", "").strip()
            cantidad = float(detalle_linea.get("cantidad_sap", 0))
            bodega = (detalle_linea.get("codigo_bodega") or detalle_linea.get("warehouse_code") or "").strip()
            
            # Omitir líneas sin cantidad
            if cantidad <= 0:
                continue
            
            if not sku:
                errors.append(f"Línea {idx}: SKU vacío")
                articulos_con_error += 1
                continue
            
            logger.debug(f"🔍 Validando línea {idx}: {sku} en bodega {bodega}")
            
            # Validar artículo + bodega usando el método combinado
            validacion_item = self.sap_client.validate_item_in_warehouse(sku, bodega)
            
            detalle["articulos"][sku] = {
                "linea": idx,
                "bodega": bodega,
                "cantidad": cantidad,
                "validacion": validacion_item
            }
            
            if not validacion_item["valid"]:
                articulos_con_error += 1
                for error in validacion_item["errors"]:
                    errors.append(f"Línea {idx} ({sku}): {error}")
            else:
                articulos_validados += 1
                # Advertir si hay stock bajo (menos del solicitado)
                stock = validacion_item.get("stock", 0)
                if stock is not None and stock < cantidad:
                    warnings.append(
                        f"Línea {idx} ({sku}): Stock disponible ({stock}) es menor que la cantidad solicitada ({cantidad})"
                    )
        
        # ============================================================
        # Resumen de validación
        # ============================================================
        total_lineas = articulos_validados + articulos_con_error
        
        if errors:
            logger.warning(
                f"⚠️ Prevalidación Service Layer: {len(errors)} error(es) encontrado(s). "
                f"Artículos: {articulos_validados}/{total_lineas} válidos"
            )
        else:
            logger.info(
                f"✅ Prevalidación Service Layer exitosa: "
                f"Proveedor OK, {articulos_validados}/{total_lineas} artículos validados"
            )
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "detalle_validacion": detalle,
            "resumen": {
                "proveedor_validado": detalle["proveedor"].get("valid", False),
                "articulos_validados": articulos_validados,
                "articulos_con_error": articulos_con_error,
                "total_lineas": total_lineas
            }
        }
    
    def enviar_ocs_pendientes(
        self,
        oc_repo: OrdenCompraRepository,
        warehouse_code: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Envía todas las órdenes de compra pendientes a SAP.
        
        Args:
            oc_repo: Repositorio de órdenes de compra
            warehouse_code: Código de bodega (opcional)
            limit: Límite de ODC a procesar (None = todas)
            
        Returns:
            Diccionario con resumen del proceso:
            {
                "total_pendientes": 10,
                "enviadas": 8,
                "errores": 2,
                "detalles": [...]
            }
        """
        try:
            # Obtener ODC pendientes
            ocs_pendientes = oc_repo.get_by_estado("PENDIENTE")
            
            if limit:
                ocs_pendientes = ocs_pendientes[:limit]
            
            if not ocs_pendientes:
                logger.info("ℹ️ No hay órdenes de compra pendientes")
                return {
                    "total_pendientes": 0,
                    "enviadas": 0,
                    "errores": 0,
                    "detalles": []
                }
            
            logger.info(f"📦 Procesando {len(ocs_pendientes)} ODC pendientes")
            
            resultados = []
            enviadas = 0
            errores = 0
            
            for oc_info in ocs_pendientes:
                oc_id = oc_info.get("oc_id")
                if oc_id is None:
                    logger.warning(f"⚠️ ODC sin oc_id, omitiendo")
                    errores += 1
                    resultados.append({
                        "oc_id": None,
                        "proveedor": oc_info.get("proveedor"),
                        "success": False,
                        "doc_entry": None,
                        "doc_num": None,
                        "error": "oc_id es None"
                    })
                    continue
                
                resultado = self.enviar_oc_a_sap(oc_repo, oc_id, warehouse_code)
                resultados.append({
                    "oc_id": oc_id,
                    "proveedor": oc_info.get("proveedor"),
                    "success": resultado.get("success"),
                    "doc_entry": resultado.get("doc_entry"),
                    "doc_num": resultado.get("doc_num"),
                    "error": resultado.get("error")
                })
                
                if resultado.get("success"):
                    enviadas += 1
                else:
                    errores += 1
            
            logger.info(f"✅ Proceso completado: {enviadas} enviadas, {errores} errores de {len(ocs_pendientes)} ODC")
            
            return {
                "total_pendientes": len(ocs_pendientes),
                "enviadas": enviadas,
                "errores": errores,
                "detalles": resultados
            }
            
        except Exception as e:
            logger.error(f"❌ Error al enviar ODC pendientes: {e}", exc_info=True)
            return {
                "total_pendientes": 0,
                "enviadas": 0,
                "errores": 0,
                "error": str(e),
                "detalles": []
            }


