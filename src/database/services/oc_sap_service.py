"""
Servicio para enviar órdenes de compra a SAP Service Layer.

Este servicio orquesta la construcción del JSON y el envío de ODC a SAP.
"""

import logging
import json
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
                result["sap_response"] = sap_response_data  # Agregar respuesta completa de SAP
                result["error_source"] = None  # Sin error
                result["message"] = mensaje_sap  # Agregar mensaje para frontend
                
                logger.info(
                    f"✅ ODC {oc_id} enviada exitosamente: "
                    f"DocEntry={doc_entry}, DocNum={doc_num}"
                )
                
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
                        
                        stock_transfer_service = StockTransferService()
                        resultado_transferencias = stock_transfer_service.crear_solicitudes_transferencia_desde_pedido(
                            pedido_id=pedido_id,
                            oc_doc_num=doc_num,
                            bodega_origen=None,  # Usará origen_traslado del pedido
                            usuario_id=None
                        )
                        
                        if resultado_transferencias.get("success"):
                            logger.info(
                                f"✅ {resultado_transferencias['transferencias_creadas']}/{resultado_transferencias['total_tiendas']} "
                                f"Solicitud(es) de Transferencia creada(s) para pedido {pedido_id}"
                            )
                            result["solicitudes_transferencia"] = resultado_transferencias
                        else:
                            logger.warning(
                                f"⚠️ No se pudieron crear Solicitudes de Transferencia para pedido {pedido_id}: "
                                f"{resultado_transferencias.get('error', 'Error desconocido')}"
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
        
        # Validación 5: Advertencia si viene de despacho (legacy)
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


