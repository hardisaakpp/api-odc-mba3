"""
Servicio para enviar órdenes de compra a SAP Service Layer.

Este servicio orquesta la construcción del JSON y el envío de ODC a SAP.
"""

import logging
import json
from typing import Optional, Dict, Any

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
            
            # 3. Convertir a formato JSON de SAP
            try:
                purchase_order_json = SAPOCMapper.to_sap_purchase_order(
                    oc_cabecera,
                    oc_detalles,
                    warehouse_code
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
            
            # 4. Enviar a SAP Service Layer
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
            
            # 5. Actualizar estado y número de OC en la base de datos
            doc_entry = sap_response.get("doc_entry")
            doc_num = sap_response.get("doc_num")
            sap_response_data = sap_response.get("data")  # Respuesta completa de SAP
            
            try:
                # Preparar mensaje de respuesta SAP
                mensaje_sap = f"Orden creada exitosamente. DocNum: {doc_num}"
                if sap_response_data and isinstance(sap_response_data, dict):
                    # Si hay un mensaje en la respuesta, usarlo
                    mensaje_sap = sap_response_data.get("message", mensaje_sap)
                
                # Actualizar estado a ENVIADA y guardar respuesta de SAP
                oc_repo.update_estado(
                    oc_id,
                    "ENVIADA",
                    numero_oc_sap=str(doc_num) if doc_num else None,
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
                
                logger.info(f"✅ ODC {oc_id} enviada exitosamente: DocNum={doc_num}")
                
            except Exception as e:
                # Aunque falló la actualización, la OC se creó en SAP
                logger.warning(f"⚠️ ODC creada en SAP pero error al actualizar estado: {e}")
                result["success"] = True
                result["doc_entry"] = doc_entry
                result["doc_num"] = doc_num
                result["sap_response"] = sap_response_data  # Agregar respuesta completa de SAP
                result["error"] = f"Advertencia: Error al actualizar estado: {str(e)}"
                result["message"] = f"Orden creada exitosamente. DocNum: {doc_num}"
            
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


