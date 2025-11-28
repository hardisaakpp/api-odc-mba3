"""
Servicio para enviar órdenes de compra a SAP Service Layer.

Este servicio orquesta la construcción del JSON y el envío de ODC a SAP.
"""

import logging
import json
import os
from typing import Optional, Dict, Any
from datetime import datetime

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
                result["error"] = f"No se encontró orden de compra con ID: {oc_id}"
                logger.error(f"❌ {result['error']}")
                return result
            
            # Verificar que esté en estado PENDIENTE
            estado_actual = oc_cabecera.get("estado")
            if estado_actual != "PENDIENTE":
                result["error"] = f"La ODC no está en estado PENDIENTE (estado actual: {estado_actual})"
                logger.warning(f"⚠️ {result['error']}")
                return result
            
            # 2. Obtener detalles de la ODC
            oc_detalles = oc_repo.get_detalles(oc_id)
            if not oc_detalles:
                result["error"] = f"No se encontraron detalles para la ODC: {oc_id}"
                logger.error(f"❌ {result['error']}")
                
                # Actualizar estado a ERROR
                try:
                    oc_repo.update_estado(oc_id, "ERROR")
                    logger.info(f"✅ Estado actualizado a ERROR para ODC: {oc_id}")
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo actualizar estado a ERROR: {e}")
                
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
                result["error"] = f"Error al construir JSON de SAP: {str(e)}"
                logger.error(f"❌ {result['error']}")
                
                # Actualizar estado a ERROR
                try:
                    oc_repo.update_estado(oc_id, "ERROR")
                    logger.info(f"✅ Estado actualizado a ERROR para ODC: {oc_id}")
                except Exception as update_error:
                    logger.warning(f"⚠️ No se pudo actualizar estado a ERROR: {update_error}")
                
                return result
            except Exception as e:
                result["error"] = f"Error inesperado al construir JSON: {str(e)}"
                logger.error(f"❌ {result['error']}", exc_info=True)
                
                # Actualizar estado a ERROR
                try:
                    oc_repo.update_estado(oc_id, "ERROR")
                    logger.info(f"✅ Estado actualizado a ERROR para ODC: {oc_id}")
                except Exception as update_error:
                    logger.warning(f"⚠️ No se pudo actualizar estado a ERROR: {update_error}")
                
                return result
            
            # 3.5. Guardar JSON en archivo para debugging (fase de pruebas)
            try:
                debug_dir = "debug/odc_json"
                os.makedirs(debug_dir, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                proveedor_clean = oc_cabecera.get("proveedor", "UNKNOWN").replace("/", "_").replace("\\", "_")
                filename = f"oc_{oc_id[:8]}_{proveedor_clean}_{timestamp}.json"
                filepath = os.path.join(debug_dir, filename)
                
                # Guardar JSON con formato legible
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(purchase_order_json, f, indent=2, ensure_ascii=False)
                
                logger.info(f"💾 JSON guardado para debugging: {filepath}")
                result["debug_file"] = filepath
            except Exception as e:
                # No fallar si no se puede guardar el archivo de debug
                logger.warning(f"⚠️ No se pudo guardar archivo de debugging: {e}")
            
            # 4. Enviar a SAP Service Layer
            sap_response = self.sap_client.create_purchase_order(purchase_order_json)
            
            if not sap_response:
                result["error"] = "No se recibió respuesta de SAP Service Layer"
                logger.error(f"❌ {result['error']}")
                
                # Actualizar estado a ERROR
                try:
                    oc_repo.update_estado(oc_id, "ERROR")
                    logger.info(f"✅ Estado actualizado a ERROR para ODC: {oc_id}")
                except Exception as update_error:
                    logger.warning(f"⚠️ No se pudo actualizar estado a ERROR: {update_error}")
                
                return result
            
            if not sap_response.get("success"):
                error_msg = sap_response.get("error", "Error desconocido")
                result["error"] = f"Error al crear Purchase Order en SAP: {error_msg}"
                logger.error(f"❌ {result['error']}")
                
                # Actualizar estado a ERROR
                try:
                    oc_repo.update_estado(oc_id, "ERROR")
                    logger.info(f"✅ Estado actualizado a ERROR para ODC: {oc_id}")
                except Exception as update_error:
                    logger.warning(f"⚠️ No se pudo actualizar estado a ERROR: {update_error}")
                
                return result
            
            # 5. Actualizar estado y número de OC en la base de datos
            doc_entry = sap_response.get("doc_entry")
            doc_num = sap_response.get("doc_num")
            
            try:
                # Actualizar estado a ENVIADA y guardar número de OC de SAP
                oc_repo.update_estado(
                    oc_id,
                    "ENVIADA",
                    numero_oc_sap=str(doc_num) if doc_num else None
                )
                
                result["success"] = True
                result["doc_entry"] = doc_entry
                result["doc_num"] = doc_num
                
                logger.info(
                    f"✅ ODC {oc_id} enviada exitosamente a SAP: "
                    f"DocEntry={doc_entry}, DocNum={doc_num}"
                )
                
            except Exception as e:
                # Aunque falló la actualización, la OC se creó en SAP
                logger.warning(f"⚠️ ODC creada en SAP pero error al actualizar estado: {e}")
                result["success"] = True
                result["doc_entry"] = doc_entry
                result["doc_num"] = doc_num
                result["error"] = f"Advertencia: Error al actualizar estado: {str(e)}"
            
            return result
            
        except Exception as e:
            result["error"] = f"Error inesperado: {str(e)}"
            logger.error(f"❌ Error al enviar ODC a SAP: {e}", exc_info=True)
            
            # Intentar actualizar estado a ERROR
            try:
                oc_repo.update_estado(oc_id, "ERROR")
                logger.info(f"✅ Estado actualizado a ERROR para ODC: {oc_id}")
            except Exception as update_error:
                logger.warning(f"⚠️ No se pudo actualizar estado a ERROR: {update_error}")
            
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
            
            logger.info(f"📦 Encontradas {len(ocs_pendientes)} ODC pendientes")
            
            resultados = []
            enviadas = 0
            errores = 0
            
            for oc_info in ocs_pendientes:
                oc_id = oc_info.get("oc_id")
                if oc_id is None:
                    logger.warning(f"⚠️ ODC sin oc_id, omitiendo: {oc_info}")
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
                
                logger.info(f"🔄 Procesando ODC: {oc_id}")
                
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
            
            logger.info(
                f"✅ Proceso completado: {enviadas} enviadas, {errores} errores "
                f"de {len(ocs_pendientes)} ODC pendientes"
            )
            
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


