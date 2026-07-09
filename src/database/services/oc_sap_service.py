"""
Servicio para enviar órdenes de compra a SAP Service Layer.

Este servicio orquesta la construcción del JSON y el envío de ODC a SAP.
"""

import json
import logging

from src.utils.timezone import ahora_naive
from typing import Optional, Dict, Any, List

from src.config import (
    PROJECT_ROOT,
    SAP_ITR_RETRY_MAX_ATTEMPTS,
    SAP_ITR_RETRY_BASE_DELAY_SECONDS,
    SAP_ITR_RETRY_MAX_JITTER_SECONDS,
    SAP_ODC_RETRY_MAX_ATTEMPTS,
    SAP_ODC_RETRY_BASE_DELAY_SECONDS,
    SAP_ODC_RETRY_MAX_JITTER_SECONDS,
)
from .retry_utils import retry_operation, sap_service_layer_result_should_retry
from ..repositories.orden_compra_repository import OrdenCompraRepository
from ..clients.sap_service_layer_client import SAPServiceLayerClient
from ..mappers.sap_oc_mapper import SAPOCMapper

logger = logging.getLogger(__name__)

_SIN_RESPUESTA_SAP = "Sin respuesta de SAP"


def _mensaje_sugiere_reintento_sap(mensaje: str) -> bool:
    """True si el texto describe un fallo típicamente transitorio hacia SAP SL (red, SL caído)."""
    if not mensaje:
        return False
    m = mensaje.lower()
    needles = (
        "conexión",
        "conexion",
        "connection",
        "timeout",
        "remote",
        "disconnected",
        "sin respuesta",
        "no se pudo establecer conexión",
        "no se pudo establecer conexion",
        # Regla operativa: permitir reenvío manual en errores de presupuesto de RL.
        "presupuesto excedido rl",
        "código sap: -1116",
        "codigo sap: -1116",
    )
    return any(n in m for n in needles)


class OCSAPService:
    """Servicio para enviar órdenes de compra a SAP Service Layer."""
    
    ODC_RETRY_MAX_ATTEMPTS = SAP_ODC_RETRY_MAX_ATTEMPTS
    ODC_RETRY_BASE_DELAY_SECONDS = SAP_ODC_RETRY_BASE_DELAY_SECONDS
    ODC_RETRY_MAX_JITTER_SECONDS = SAP_ODC_RETRY_MAX_JITTER_SECONDS
    
    ITR_RETRY_MAX_ATTEMPTS = SAP_ITR_RETRY_MAX_ATTEMPTS
    ITR_RETRY_BASE_DELAY_SECONDS = SAP_ITR_RETRY_BASE_DELAY_SECONDS
    ITR_RETRY_MAX_JITTER_SECONDS = SAP_ITR_RETRY_MAX_JITTER_SECONDS
    
    def __init__(self):
        """Inicializa el servicio."""
        self.sap_client = SAPServiceLayerClient()
    
    def _enviar_oc_con_reintento(self, purchase_order_json: Dict[str, Any]) -> Dict[str, Any]:
        """Envía la ODC a SAP con reintento y backoff exponencial."""
        return retry_operation(
            execute=lambda: self.sap_client.create_purchase_order(purchase_order_json),
            is_success=lambda response: bool(
                response and response.get("success") and response.get("doc_entry")
            ),
            extract_error=lambda response: (
                response.get("error", "Error desconocido")
                if response else "No se recibió respuesta de SAP Service Layer"
            ),
            max_attempts=self.ODC_RETRY_MAX_ATTEMPTS,
            should_retry=sap_service_layer_result_should_retry,
            base_delay_seconds=self.ODC_RETRY_BASE_DELAY_SECONDS,
            max_jitter_seconds=self.ODC_RETRY_MAX_JITTER_SECONDS,
            logger=logger,
            operation_label="ODC",
        )
    
    def _enviar_itr_con_reintento(
        self,
        payload: Dict[str, Any],
        from_wh: str,
        to_wh: str,
    ) -> Dict[str, Any]:
        """Envía ITR (flujo por bodega destino) con reintento automático."""
        return retry_operation(
            execute=lambda: self.sap_client.create_stock_transfer(payload),
            is_success=lambda response: bool(
                response and response.get("success") and response.get("doc_entry")
            ),
            extract_error=lambda response: (
                response.get("error", _SIN_RESPUESTA_SAP)
                if response else _SIN_RESPUESTA_SAP
            ),
            max_attempts=self.ITR_RETRY_MAX_ATTEMPTS,
            should_retry=sap_service_layer_result_should_retry,
            base_delay_seconds=self.ITR_RETRY_BASE_DELAY_SECONDS,
            max_jitter_seconds=self.ITR_RETRY_MAX_JITTER_SECONDS,
            logger=logger,
            operation_label=f"ITR ({from_wh} → {to_wh})",
        )
    
    @staticmethod
    def _extraer_bodegas_desde_distribucion(productos_distribucion: list) -> set:
        """Retorna códigos de bodega (es_bodega=True, cantidad > 0) desde la distribución."""
        bodegas = set()
        for producto in productos_distribucion:
            for dist in producto.get("distribuciones", []):
                if dist.get("es_bodega", False):
                    cantidad = dist.get("cantidad_asignada", 0)
                    tienda_codigo = dist.get("tienda_codigo")
                    if cantidad and cantidad > 0 and tienda_codigo:
                        bodegas.add(tienda_codigo.strip().upper())
        return bodegas

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
                    
                    bodegas_encontradas = OCSAPService._extraer_bodegas_desde_distribucion(productos_distribucion)

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

    @staticmethod
    def obtener_fecha_entrega_pedido(conn, pedido_id: Optional[str]) -> Optional[Any]:
        """
        Lee fecha_entrega desde pedido para mapear DocDueDate en SAP.
        Retorna None si no hay pedido_id o falla la consulta.
        """
        if not pedido_id:
            return None
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT fecha_entrega FROM pedido WHERE pedido_id = ?",
                (pedido_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.warning(
                "⚠️ No se pudo leer fecha_entrega del pedido %s: %s",
                pedido_id,
                e,
            )
            return None

    @staticmethod
    def _cargar_y_validar_cabecera(
        oc_repo: 'OrdenCompraRepository',
        oc_id: str,
        result: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Carga la cabecera de la ODC y valida que exista y esté en estado PENDIENTE."""
        oc_cabecera = oc_repo.get_existing_cabecera(oc_id)
        if not oc_cabecera:
            error_msg = f"No se encontró orden de compra con ID: {oc_id}"
            result["error"] = error_msg
            result["error_message"] = error_msg
            result["error_source"] = "BACKEND"
            result["retry_recommended"] = True
            logger.error(f"❌ {error_msg}")
            return None
        estado_actual = oc_cabecera.get("estado")
        if estado_actual != "PENDIENTE":
            error_msg = f"La ODC no está en estado PENDIENTE (estado actual: {estado_actual})"
            result["error"] = error_msg
            result["error_message"] = error_msg
            result["error_source"] = "BACKEND"
            result["retry_recommended"] = True
            logger.warning(f"⚠️ {error_msg}")
            return None
        return oc_cabecera

    @staticmethod
    def _cargar_y_validar_detalles(
        oc_repo: 'OrdenCompraRepository',
        oc_id: str,
        result: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """Carga los detalles de la ODC y valida que no estén vacíos."""
        oc_detalles = oc_repo.get_detalles(oc_id)
        if not oc_detalles:
            error_msg = f"No se encontraron detalles para la ODC: {oc_id}"
            result["error"] = error_msg
            result["error_message"] = error_msg
            result["error_source"] = "BACKEND"
            result["retry_recommended"] = True
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
            return None
        logger.info(f"📦 Preparando envío de ODC {oc_id} a SAP ({len(oc_detalles)} líneas)")
        return oc_detalles

    def _resolver_warehouse_code(
        self,
        oc_cabecera: Dict[str, Any],
        oc_repo: 'OrdenCompraRepository',
        oc_id: str,
        warehouse_code: Optional[str]
    ) -> Optional[str]:
        """Resuelve el código de bodega: parámetro > cabecera > distribuciones del pedido."""
        if warehouse_code:
            return warehouse_code
        warehouse_code = oc_cabecera.get("codigo_bodega")
        if warehouse_code:
            logger.info(f"📍 Bodega obtenida de la cabecera: {warehouse_code}")
            return warehouse_code
        warehouse_code = self.determinar_bodega_desde_pedido(oc_cabecera, oc_repo)
        if warehouse_code:
            logger.info(f"📍 Bodega determinada automáticamente: {warehouse_code}")
            try:
                oc_repo.update_cabecera(oc_id, {"codigo_bodega": warehouse_code})
                logger.info(f"✅ Bodega persistida en orden_compra_cabecera: {warehouse_code}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo persistir bodega en la cabecera: {e}")
        else:
            logger.warning(f"⚠️ No se pudo determinar bodega para ODC {oc_id}. La ODC se enviará sin WarehouseCode.")
        return warehouse_code

    def _ejecutar_validaciones_oc(
        self,
        oc_cabecera: Dict[str, Any],
        oc_detalles: List[Dict[str, Any]],
        oc_id: str,
        oc_repo: 'OrdenCompraRepository',
        result: Dict[str, Any]
    ) -> bool:
        """Ejecuta validación interna y prevalidación contra SAP. Retorna False si alguna falla."""
        validacion = self._validar_antes_de_crear_oc(oc_cabecera, oc_detalles)
        if not validacion["valid"]:
            error_msg = f"Validación falló: {'; '.join(validacion['errors'])}"
            result["error"] = error_msg
            result["error_message"] = error_msg
            result["error_source"] = "BACKEND"
            result["retry_recommended"] = True
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
            return False
        for warning in validacion.get("warnings", []):
            logger.warning(warning)

        logger.info("🔍 Paso 3.5: Prevalidación contra SAP Service Layer...")
        prevalidacion = self._precheck_against_service_layer(oc_cabecera, oc_detalles)
        if not prevalidacion["valid"]:
            errores_prevalidacion = prevalidacion.get("errors", [])
            error_msg = f"Prevalidación SAP falló: {'; '.join(errores_prevalidacion)}"
            proveedor_oc = (oc_cabecera.get("proveedor") or "").strip()
            pedido_id_oc = oc_cabecera.get("pedido_id")
            result["error"] = error_msg
            result["error_message"] = error_msg
            result["error_source"] = "SAP_VALIDATION"
            result["prevalidacion_detalle"] = prevalidacion.get("detalle_validacion")
            result["prevalidacion_resumen"] = prevalidacion.get("resumen")
            result["retry_recommended"] = True
            logger.error(
                "❌ %s | oc_id=%s pedido_id=%s proveedor=%s errores=%s",
                error_msg, oc_id, pedido_id_oc, proveedor_oc, errores_prevalidacion,
            )
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
            return False
        for warning in prevalidacion.get("warnings", []):
            logger.warning(f"⚠️ Prevalidación: {warning}")
        return True

    def _construir_json_sap(
        self,
        oc_cabecera: Dict[str, Any],
        oc_detalles: List[Dict[str, Any]],
        warehouse_code: Optional[str],
        oc_repo: 'OrdenCompraRepository',
        oc_id: str,
        result: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Convierte la ODC a JSON de SAP y lo persiste en output/. Retorna None si falla."""
        try:
            pid = oc_cabecera.get("pedido_id")
            fecha_entrega_raw = (
                self.obtener_fecha_entrega_pedido(oc_repo.conn, pid) if pid else None
            )
            purchase_order_json = SAPOCMapper.to_sap_purchase_order(
                oc_cabecera,
                oc_detalles,
                warehouse_code,
                usuario_id=oc_cabecera.get("creado_por"),
                pedido_id=pid,
                fecha_entrega=fecha_entrega_raw,
            )
            result["sap_request_json"] = purchase_order_json
            try:
                output_dir = PROJECT_ROOT / "output"
                output_dir.mkdir(parents=True, exist_ok=True)
                out_file = output_dir / f"odc_{oc_id}.json"
                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump(purchase_order_json, f, ensure_ascii=False, indent=2, default=str)
                logger.info(f"📥 ODC (request SAP) guardada en {out_file}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo guardar ODC en output/: {e}")
            return purchase_order_json
        except ValueError as e:
            error_msg = f"Error al construir JSON de SAP: {str(e)}"
            result["error"] = error_msg
            result["error_message"] = error_msg
            result["error_source"] = "BACKEND"
            result["retry_recommended"] = True
            logger.error(f"❌ Error al construir JSON: {error_msg}")
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
            return None
        except Exception as e:
            error_msg = f"Error inesperado al construir JSON: {str(e)}"
            result["error"] = error_msg
            result["error_message"] = error_msg
            result["error_source"] = "BACKEND"
            result["retry_recommended"] = True
            logger.error(f"❌ Error inesperado: {error_msg}", exc_info=True)
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
            return None

    @staticmethod
    def _manejar_fallo_envio_sap(
        oc_id: str,
        sap_response: Optional[Dict[str, Any]],
        envio_oc_result: Dict[str, Any],
        oc_repo: 'OrdenCompraRepository',
        result: Dict[str, Any]
    ) -> None:
        """Maneja la respuesta fallida de SAP: sin respuesta o error de SAP."""
        if not sap_response:
            error_msg = "No se recibió respuesta de SAP Service Layer"
            result["error"] = error_msg
            result["error_message"] = error_msg
            result["error_source"] = "SAP_CONNECTION"
            result["retry_recommended"] = True
            logger.error(f"❌ {error_msg}")
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
            return
        error_msg = sap_response.get("error", "Error desconocido")
        error_code = sap_response.get("error_code")
        sap_error_details = sap_response.get("sap_error_details")
        if error_code:
            error_final = f"{error_msg} (Código SAP: {error_code})"
        else:
            error_final = f"Error al crear Purchase Order en SAP: {error_msg}"
        result["error"] = error_final
        result["error_message"] = error_final
        result["error_code"] = error_code
        result["sap_error_details"] = sap_error_details
        result["error_source"] = "SAP"
        result["attempts"] = envio_oc_result.get("attempts")
        result["retry_recommended"] = True
        logger.error(f"❌ {error_final}")
        try:
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

    @staticmethod
    def _obtener_serie_itr(
        oc_cabecera: Dict[str, Any],
        oc_repo: 'OrdenCompraRepository'
    ) -> Optional[int]:
        """Obtiene el número de serie del pedido para asignar Numbering Series a las ITRs."""
        pedido_id = oc_cabecera.get("pedido_id")
        if not pedido_id:
            return None
        try:
            from ..repositories.pedido_repository import PedidoRepository as _PedidoRepoSerie
            _repo_serie = _PedidoRepoSerie(oc_repo.conn)
            _pedido_serie = _repo_serie.get_pedido_completo(pedido_id)
            if _pedido_serie:
                _serie_raw = (_pedido_serie.get("cabecera") or {}).get("serie")
                if _serie_raw is not None:
                    try:
                        serie_itr = int(_serie_raw)
                        logger.info(f"📍 Serie del pedido para ITR: {serie_itr}")
                        return serie_itr
                    except (TypeError, ValueError):
                        logger.warning(f"⚠️ Valor de serie no válido: {_serie_raw}")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo obtener serie del pedido (no crítico): {e}")
        return None

    @staticmethod
    def _resolver_from_warehouse(oc_cabecera: Dict[str, Any]) -> str:
        """Resuelve el FromWarehouse para ITRs: codigo_bodega de OC > SAP_ST_FROM_WAREHOUSE."""
        try:
            from src.config import SAP_ST_FROM_WAREHOUSE
            from_wh = (oc_cabecera.get("codigo_bodega") or "").strip()
            if not from_wh:
                from_wh = (SAP_ST_FROM_WAREHOUSE or "").strip()
                if from_wh:
                    logger.info(f"📍 Usando SAP_ST_FROM_WAREHOUSE como fallback: {from_wh}")
            return from_wh
        except Exception:
            return (oc_cabecera.get("codigo_bodega") or "").strip()

    def _enviar_itrs_por_bodega(
        self,
        oc_detalles: List[Dict[str, Any]],
        from_wh: str,
        doc_num: Any,
        doc_date_itr: str,
        serie_itr: Optional[int],
        result: Dict[str, Any]
    ) -> None:
        """Crea y envía Inventory Transfer Requests a SAP (1 por bodega destino)."""
        try:
            from ..mappers.sap_stock_transfer_mapper import SAPStockTransferMapper
            itr_payloads = SAPStockTransferMapper.to_sap_inventory_transfer_requests_by_bodega(
                oc_detalles=oc_detalles,
                from_warehouse=from_wh,
                doc_date=doc_date_itr,
                due_date=doc_date_itr,
                oc_doc_num=doc_num,
                serie=serie_itr,
            )
            itr_created = 0
            itr_errors = 0
            itr_results = []
            logger.info(f"📤 Enviando {len(itr_payloads)} Inventory Transfer Request(s) por bodega a SAP...")
            for idx, pl in enumerate(itr_payloads):
                to_warehouse = pl.get("ToWarehouse", "UNKNOWN")
                logger.debug(f"🔄 Enviando ITR {idx+1}/{len(itr_payloads)} a SAP: {from_wh} → {to_warehouse}...")
                envio_itr_result = self._enviar_itr_con_reintento(
                    payload=pl,
                    from_wh=from_wh,
                    to_wh=to_warehouse,
                )
                resp = envio_itr_result.get("response")
                if resp and resp.get("success") and resp.get("doc_entry"):
                    itr_created += 1
                    itr_results.append({
                        "ToWarehouse": to_warehouse,
                        "doc_entry": resp.get("doc_entry"),
                        "doc_num": resp.get("doc_num"),
                        "attempts": envio_itr_result.get("attempts"),
                        "success": True,
                    })
                    logger.info(
                        f"✅ Inventory Transfer Request CREADO en SAP: {from_wh} → {to_warehouse} "
                        f"(DocEntry={resp.get('doc_entry')}, DocNum={resp.get('doc_num')})"
                    )
                else:
                    itr_errors += 1
                    error_msg = envio_itr_result.get("error") or _SIN_RESPUESTA_SAP
                    itr_results.append({
                        "ToWarehouse": to_warehouse,
                        "success": False,
                        "attempts": envio_itr_result.get("attempts"),
                        "error": error_msg,
                    })
                    logger.warning(
                        f"⚠️ Inventory Transfer Request NO creado tras "
                        f"{envio_itr_result.get('attempts', self.ITR_RETRY_MAX_ATTEMPTS)} intento(s): "
                        f"{from_wh} → {to_warehouse}: {error_msg}"
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
                logger.warning(f"⚠️ {itr_errors} Inventory Transfer Request(s) NO se pudieron crear en SAP")
            if itr_created == 0:
                logger.warning(
                    f"⚠️ No se creó ningún Inventory Transfer Request en SAP "
                    f"(0/{len(itr_payloads)} exitosos)"
                )
        except Exception as e:
            logger.warning(f"⚠️ No se pudieron crear Inventory Transfer Requests (no crítico): {e}")
            result["inventory_transfer_requests_error"] = str(e)

    @staticmethod
    def _log_fallo_itr(pedido_id: str, resultado_transferencias: Dict[str, Any]) -> None:
        """Registra en log el detalle del fallo de Inventory Transfer Requests."""
        error_type = resultado_transferencias.get("error_type", "desconocido")
        error_msg = resultado_transferencias.get("error")
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

    @staticmethod
    def _crear_solicitudes_transferencia_oc(
        oc_id: str,
        oc_cabecera: Dict[str, Any],
        doc_num: Any,
        serie_itr: Optional[int],
        oc_repo: 'OrdenCompraRepository',
        pedido_id: str,
        result: Dict[str, Any]
    ) -> None:
        """Crea Solicitudes de Transferencia para el pedido asociado a la ODC."""
        try:
            from .stock_transfer_service import StockTransferService
            bodega_oc = oc_cabecera.get("codigo_bodega")
            if bodega_oc:
                logger.info(f"📍 Usando bodega de la OC para ST: {bodega_oc}")
            else:
                logger.warning("⚠️ OC sin codigo_bodega, se usará origen_traslado del pedido")
            stock_transfer_service = StockTransferService()
            resultado_transferencias = stock_transfer_service.crear_solicitudes_transferencia_desde_pedido(
                pedido_id=pedido_id,
                oc_doc_num=doc_num,
                oc_id=oc_id,
                bodega_origen=bodega_oc,
                usuario_id=None,
                serie=serie_itr
            )
            if resultado_transferencias.get("success"):
                logger.info(
                    f"✅ Inventory Transfer Requests creados en SAP: "
                    f"{resultado_transferencias['transferencias_creadas']}/{resultado_transferencias['total_tiendas']} "
                    f"para pedido {pedido_id} (DocEntry confirmado para cada uno)"
                )
                if resultado_transferencias.get("warnings"):
                    logger.warning(
                        f"⚠️ Advertencias en ITR de pedido {pedido_id}: "
                        f"{'; '.join(resultado_transferencias['warnings'])}"
                    )
            else:
                OCSAPService._log_fallo_itr(pedido_id, resultado_transferencias)
            result["solicitudes_transferencia"] = resultado_transferencias
        except Exception as e:
            logger.warning(f"⚠️ Error al crear Solicitudes de Transferencia (no crítico): {e}")
            result["solicitudes_transferencia_error"] = str(e)

    @staticmethod
    def _obtener_numero_pedido_para_notif(pedido_id: str, conn: Any) -> Optional[str]:
        """Obtiene el número de pedido para notificaciones; retorna None si falla."""
        try:
            from ..repositories.pedido_repository import PedidoRepository
            pedido_repo_temp = PedidoRepository(conn)
            pedido_data = pedido_repo_temp.get_pedido_completo(pedido_id)
            if pedido_data and pedido_data.get("cabecera"):
                return pedido_data["cabecera"].get("numero_pedido")
        except Exception:
            pass
        return None

    @staticmethod
    def _detectar_error_en_st(result: Dict[str, Any]) -> bool:
        """Retorna True si el resultado del ST contiene un error."""
        if result.get("solicitudes_transferencia_error"):
            return True
        resultado_st = result.get("solicitudes_transferencia")
        if isinstance(resultado_st, dict):
            transferencias_errores = int(resultado_st.get("transferencias_errores", 0) or 0)
            return transferencias_errores > 0 or not bool(resultado_st.get("success"))
        return False

    @staticmethod
    def _notificar_resultado_oc_st(
        oc_id: str,
        oc_cabecera: Dict[str, Any],
        doc_num: Any,
        doc_entry: Any,
        pedido_id: str,
        oc_repo: 'OrdenCompraRepository',
        result: Dict[str, Any]
    ) -> None:
        """Notifica errores de ODC/ST a técnicos y persiste snapshot del envío."""
        try:
            from src.utils.email_notifier import send_oc_st_error_notification_tecnicos
            from ..repositories.envio_odc_sap_repository import EnvioODCSAPRepository

            pedido_numero = OCSAPService._obtener_numero_pedido_para_notif(pedido_id, oc_repo.conn)
            resultado_transferencias_notif = result.get("solicitudes_transferencia")
            hay_error_st = OCSAPService._detectar_error_en_st(result)

            if hay_error_st:
                email_enviado = send_oc_st_error_notification_tecnicos(
                    oc_cabecera=oc_cabecera,
                    doc_num=doc_num,
                    doc_entry=doc_entry,
                    solicitudes_transferencia=resultado_transferencias_notif,
                    pedido_numero=pedido_numero,
                )
                if email_enviado:
                    logger.info(f"📧 Notificación de error ODC/ST enviada a técnicos (OC #{doc_num})")
                else:
                    logger.warning("⚠️ No se pudo enviar notificación de error ODC/ST a técnicos (no crítico)")
            else:
                logger.info(f"ℹ️ ODC/ST sin errores; no se envía notificación a técnicos (OC #{doc_num})")

            try:
                envio_repo = EnvioODCSAPRepository(oc_repo.conn)
                total_st = (resultado_transferencias_notif or {}).get("total_tiendas", 0)
                creadas_st = (resultado_transferencias_notif or {}).get("transferencias_creadas", 0)
                st_id = (resultado_transferencias_notif or {}).get("solicitud_transferencia_id")
                envio_repo.insert(
                    oc_id=oc_id,
                    pedido_id=pedido_id,
                    numero_oc_sap=str(doc_num) if doc_num else None,
                    doc_entry=doc_entry,
                    proveedor=oc_cabecera.get("proveedor"),
                    referencia=oc_cabecera.get("referencia_despacho"),
                    numero_pedido=pedido_numero,
                    solicitud_transferencia_id=st_id,
                    total_transferencias=total_st,
                    transferencias_creadas=creadas_st,
                )
                logger.info("📥 Snapshot de envío ODC/SAP persistido en envio_odc_sap")
            except Exception as e_persist:
                logger.warning(f"⚠️ No se pudo persistir envio_odc_sap (no crítico): {e_persist}")
        except Exception as e:
            logger.warning(f"⚠️ Error al enviar notificación de error ODC/ST a técnicos (no crítico): {e}")

    @staticmethod
    def _cerrar_pedido_desde_resultado_oc(
        pedido_id: str,
        oc_repo: 'OrdenCompraRepository',
        result: Dict[str, Any]
    ) -> None:
        """Evalúa y actualiza el estado del pedido según resultado de OC y ST."""
        try:
            from ..repositories.pedido_repository import PedidoRepository
            from .pedido_cierre_service import PedidoCierreService
            pedido_repo = PedidoRepository(oc_repo.conn)
            cierre_service = PedidoCierreService()
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
            logger.warning(f"⚠️ Error al evaluar cierre de pedido (no crítico): {e}")

    def _procesar_oc_exitosa(
        self,
        oc_id: str,
        oc_cabecera: Dict[str, Any],
        oc_detalles: List[Dict[str, Any]],
        sap_response: Dict[str, Any],
        envio_oc_result: Dict[str, Any],
        oc_repo: 'OrdenCompraRepository',
        result: Dict[str, Any]
    ) -> None:
        """Procesa el resultado exitoso de envío a SAP: actualiza estado, crea ITRs, STs, notifica y cierra pedido."""
        doc_entry = sap_response.get("doc_entry")
        doc_num = sap_response.get("doc_num")
        sap_response_data = sap_response.get("data")

        try:
            mensaje_sap = f"Orden creada exitosamente. DocNum: {doc_num}"
            if sap_response_data and isinstance(sap_response_data, dict):
                mensaje_sap = sap_response_data.get("message", mensaje_sap)

            oc_repo.update_estado(
                oc_id,
                "ENVIADA",
                numero_oc_sap=str(doc_num) if doc_num else None,
                doc_entry=doc_entry,
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
            result["attempts"] = envio_oc_result.get("attempts")

            doc_date_str = f", DocDate={result['doc_date']}" if result.get("doc_date") else ""
            logger.info(
                f"✅ ODC {oc_id} enviada exitosamente: "
                f"DocEntry={doc_entry}, DocNum={doc_num}{doc_date_str}"
            )

            serie_itr = self._obtener_serie_itr(oc_cabecera, oc_repo)

            doc_date_val = sap_response.get("doc_date")
            doc_date_itr = doc_date_val[:10] if isinstance(doc_date_val, str) and len(doc_date_val) >= 10 else None
            if not doc_date_itr:
                doc_date_itr = ahora_naive().strftime("%Y-%m-%d")

            from_wh = self._resolver_from_warehouse(oc_cabecera)

            if from_wh and oc_detalles:
                self._enviar_itrs_por_bodega(oc_detalles, from_wh, doc_num, doc_date_itr, serie_itr, result)

            logger.info("ℹ️ Envío de correo de ODC al proveedor omitido por configuración funcional")

            pedido_id = oc_cabecera.get("pedido_id")
            if pedido_id:
                self._crear_solicitudes_transferencia_oc(oc_id, oc_cabecera, doc_num, serie_itr, oc_repo, pedido_id, result)
                self._notificar_resultado_oc_st(oc_id, oc_cabecera, doc_num, doc_entry, pedido_id, oc_repo, result)
                self._cerrar_pedido_desde_resultado_oc(pedido_id, oc_repo, result)

        except Exception as e:
            logger.warning(
                f"⚠️ ODC creada en SAP pero error al actualizar estado: {e}. "
                f"DocEntry={doc_entry}, DocNum={doc_num}"
            )
            result["success"] = True
            result["doc_entry"] = doc_entry
            result["doc_num"] = doc_num
            result["sap_response"] = sap_response_data
            result["error"] = f"Advertencia: Error al actualizar estado: {str(e)}"
            result["message"] = f"Orden creada exitosamente. DocNum: {doc_num}"
            try:
                oc_repo.update_sap_refs(oc_id, doc_entry=doc_entry, doc_num=str(doc_num) if doc_num else None)
            except Exception:
                pass

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
            oc_cabecera = self._cargar_y_validar_cabecera(oc_repo, oc_id, result)
            if oc_cabecera is None:
                return result

            oc_detalles = self._cargar_y_validar_detalles(oc_repo, oc_id, result)
            if oc_detalles is None:
                return result

            warehouse_code = self._resolver_warehouse_code(oc_cabecera, oc_repo, oc_id, warehouse_code)

            if not self._ejecutar_validaciones_oc(oc_cabecera, oc_detalles, oc_id, oc_repo, result):
                return result

            purchase_order_json = self._construir_json_sap(
                oc_cabecera, oc_detalles, warehouse_code, oc_repo, oc_id, result
            )
            if purchase_order_json is None:
                return result

            logger.info(f"🔄 Enviando ODC {oc_id} a SAP Service Layer...")
            envio_oc_result = self._enviar_oc_con_reintento(purchase_order_json)
            sap_response = envio_oc_result.get("response")

            if not sap_response or not sap_response.get("success"):
                self._manejar_fallo_envio_sap(oc_id, sap_response, envio_oc_result, oc_repo, result)
                return result

            self._procesar_oc_exitosa(
                oc_id, oc_cabecera, oc_detalles, sap_response, envio_oc_result, oc_repo, result
            )

        except Exception as e:
            error_msg = f"Error inesperado: {str(e)}"
            result["error"] = error_msg
            result["error_message"] = error_msg  # Alias para compatibilidad con frontend
            result["error_source"] = "BACKEND"
            result["retry_recommended"] = True
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
    
    @staticmethod
    def _validar_proveedor_sap(sap_client, oc_cabecera, errors, detalle) -> None:
        proveedor = oc_cabecera.get("proveedor", "").strip()
        if not proveedor:
            return
        card_code = proveedor if proveedor.startswith('P') else f"P{proveedor}"
        logger.debug(f"🔍 Validando proveedor: {card_code}")
        bp_info = sap_client.get_business_partner(card_code)
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

    @staticmethod
    def _validar_linea_detalle_sap(
        idx, detalle_linea, sap_client, errors, warnings, detalle
    ) -> tuple:
        sku = detalle_linea.get("sku_sap", "").strip()
        cantidad = float(detalle_linea.get("cantidad_sap", 0))
        bodega = (detalle_linea.get("codigo_bodega") or detalle_linea.get("warehouse_code") or "").strip()
        if cantidad <= 0:
            return 0, 0
        if not sku:
            errors.append(f"Línea {idx}: SKU vacío")
            return 0, 1
        logger.debug(f"🔍 Validando línea {idx}: {sku} en bodega {bodega}")
        validacion_item = sap_client.validate_item_in_warehouse(sku, bodega)
        detalle["articulos"][sku] = {
            "linea": idx,
            "bodega": bodega,
            "cantidad": cantidad,
            "validacion": validacion_item,
        }
        if not validacion_item["valid"]:
            for error in validacion_item["errors"]:
                errors.append(f"Línea {idx} ({sku}): {error}")
            return 0, 1
        stock = validacion_item.get("stock", 0)
        if stock is not None and stock < cantidad:
            warnings.append(
                f"Línea {idx} ({sku}): Stock disponible ({stock}) es menor que la cantidad solicitada ({cantidad})"
            )
        return 1, 0

    @staticmethod
    def _validar_articulos_sap(sap_client, oc_detalles, errors, warnings, detalle) -> tuple:
        articulos_validados = 0
        articulos_con_error = 0
        for idx, detalle_linea in enumerate(oc_detalles, start=1):
            validated, with_error = OCSAPService._validar_linea_detalle_sap(
                idx, detalle_linea, sap_client, errors, warnings, detalle
            )
            articulos_validados += validated
            articulos_con_error += with_error
        return articulos_validados, articulos_con_error

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

        self._validar_proveedor_sap(self.sap_client, oc_cabecera, errors, detalle)
        articulos_validados, articulos_con_error = self._validar_articulos_sap(
            self.sap_client, oc_detalles, errors, warnings, detalle
        )

        total_lineas = articulos_validados + articulos_con_error

        if errors:
            logger.error(
                "❌ Prevalidación Service Layer: %s error(es). "
                "Artículos válidos=%s/%s. Detalle=%s",
                len(errors),
                articulos_validados,
                total_lineas,
                errors,
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
                    logger.warning("⚠️ ODC sin oc_id, omitiendo")
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

    # ──────────────────────────────────────────────────────────────────────
    # Métodos auxiliares para generación de PDF
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _obtener_cabecera_pedido_para_pdf(cursor, pedido_id: str) -> Dict[str, Any]:
        try:
            cursor.execute(
                """
                SELECT proveedor_nombre, forma_pago, fecha_entrega
                FROM pedido
                WHERE pedido_id = ?
                """,
                (pedido_id,),
            )
            row = cursor.fetchone()
            if row:
                fecha = row[2].isoformat() if row[2] and hasattr(row[2], "isoformat") else (row[2] or None)
                info = {
                    "proveedor_nombre": row[0] or None,
                    "forma_pago": row[1] or None,
                    "fecha_entrega": fecha,
                }
                logger.debug(
                    f"📋 Pedido info para PDF: proveedor={info.get('proveedor_nombre')}, "
                    f"forma_pago={info.get('forma_pago')}, "
                    f"fecha_entrega={info.get('fecha_entrega')}"
                )
                return info
        except Exception as e:
            logger.warning(f"⚠️ No se pudo obtener cabecera del pedido {pedido_id}: {e}")
        return {}

    @staticmethod
    def _enriquecer_detalles_desde_pedido(cursor, oc_detalles: List[Dict[str, Any]]) -> None:
        referencia_ids = [
            d.get("referencia_detalle")
            for d in oc_detalles
            if d.get("referencia_detalle")
        ]
        if not referencia_ids:
            return
        try:
            placeholders = ",".join("?" for _ in referencia_ids)
            cursor.execute(
                f"""
                SELECT pedido_detalle_id, codigo_barras, descripcion_sap
                FROM pedido_detalle
                WHERE pedido_detalle_id IN ({placeholders})
                """,
                referencia_ids,
            )
            detalle_map: Dict[str, Dict[str, Any]] = {}
            for r in cursor.fetchall():
                detalle_map[str(r[0])] = {
                    "codigo_barras": r[1] or "",
                    "descripcion": r[2] or "",
                }
            enriched = 0
            for detalle in oc_detalles:
                ref_id = detalle.get("referencia_detalle")
                if ref_id and ref_id in detalle_map:
                    extra = detalle_map[ref_id]
                    detalle["codigo_barras"] = extra.get("codigo_barras", "")
                    detalle["descripcion"] = extra.get("descripcion", "")
                    enriched += 1
            logger.debug(
                f"📋 Detalles enriquecidos para PDF: {enriched}/{len(oc_detalles)} "
                f"(de {len(detalle_map)} registros encontrados en pedido_detalle)"
            )
        except Exception as e:
            logger.warning(f"⚠️ No se pudieron obtener detalles del pedido para PDF: {e}")

    @staticmethod
    def _obtener_pedido_info_para_pdf(
        conn,
        pedido_id: str,
        oc_detalles: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene información adicional del pedido para enriquecer el PDF de la ODC.

        Enriquece cada elemento de ``oc_detalles`` *in-place* con los campos
        ``codigo_barras`` y ``descripcion`` obtenidos de ``pedido_detalle``
        (usando ``referencia_detalle`` como enlace a ``pedido_detalle_id``).

        Además retorna un dict con la información de cabecera del pedido
        (proveedor_nombre, forma_pago, fecha_entrega).

        Args:
            conn: Conexión activa a la base de datos.
            pedido_id: UUID del pedido relacionado.
            oc_detalles: Lista de detalles de la ODC (se modifica in-place).

        Returns:
            Dict con: proveedor_nombre, forma_pago, fecha_entrega.
            None si no se puede obtener la información.
        """
        cursor = conn.cursor()
        try:
            pedido_info = OCSAPService._obtener_cabecera_pedido_para_pdf(cursor, pedido_id)
            OCSAPService._enriquecer_detalles_desde_pedido(cursor, oc_detalles)
            return pedido_info if pedido_info else None
        except Exception as e:
            logger.warning(f"⚠️ Error general al obtener pedido info para PDF: {e}")
            return None
        finally:
            cursor.close()

