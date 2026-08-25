"""
Servicio para enviar órdenes de compra a SAP Service Layer.

Este servicio orquesta la construcción del JSON y el envío de ODC a SAP.
"""

import contextlib
import json
import logging
import re

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
    SAP_PREVALIDACION_RETRY_MAX_ATTEMPTS,
    SAP_PREVALIDACION_RETRY_BASE_DELAY_SECONDS,
    SAP_PREVALIDACION_RETRY_MAX_JITTER_SECONDS,
    USE_BATCH_VALIDATION,
)
from .retry_utils import retry_operation, sap_service_layer_result_should_retry, mensaje_sugiere_reintento_transitorio
from .proceso_estado_service import get_redis_client
from ..repositories.orden_compra_repository import OrdenCompraRepository
from ..clients.sap_service_layer_client import SAPServiceLayerClient
from ..mappers.sap_oc_mapper import SAPOCMapper
from src.exceptions import SolicitudTransferenciaNoAplicaError

logger = logging.getLogger(__name__)

_SIN_RESPUESTA_SAP = "Sin respuesta de SAP"
_ERROR_DESCONOCIDO = "Error desconocido"

# Empareja errores de prevalidación por línea, ej. "Línea 1 (SKU): motivo" o
# "Línea 1: motivo", para poder agruparlos por motivo (ver _resumir_errores_prevalidacion).
_LINEA_ERROR_RE = re.compile(r'^Línea \d+(?:\s*\([^)]*\))?:\s*(.+)$')

# Cubre el caso real observado: prevalidación reintentando varios minutos por SAP
# saturado antes de fallar o tener éxito (ver redis_lock_envio_odc).
_LOCK_ENVIO_ODC_TIMEOUT_SEGUNDOS = 600.0


@contextlib.contextmanager
def redis_lock_envio_odc(oc_id: str, blocking_timeout: float = 0.1):
    """
    Lock distribuido (Redis) para serializar el ENVÍO a SAP de una misma ODC.

    Bug real que corrige: 2 clics de "Reintentar" (o un clic doble por lentitud
    de la UI) para la MISMA oc_id podían correr en paralelo -- sin este lock, no
    hay nada que lo impida, porque ambos requests leen la ODC en estado PENDIENTE
    antes de que el primero termine. Si el primero llega a SAP con éxito
    (DocEntry asignado) pero el segundo, corriendo en paralelo y sin saber del
    primero, falla su propia prevalidación después, su manejador de error pisaba
    el estado de la OC de vuelta a ERROR aunque ya estuviera ENVIADA con DocEntry
    real -- dejando la ODC en un loop: cada reintento posterior se resetea a
    PENDIENTE pero la validación de idempotencia (ya tiene DocEntry) lo rechaza
    de inmediato y la vuelve a marcar ERROR, sin salida posible desde la UI.

    No bloqueante por defecto (blocking_timeout=0.1): si otro envío de la misma
    ODC ya está en curso, se debe rechazar de inmediato -- no tiene sentido
    esperar, puede tardar varios minutos por reintentos ante SAP saturado.

    Yields True si se obtuvo el lock, False si no (el caller debe omitir el envío
    sin tocar el estado de la ODC, ya que el envío en curso es quien debe
    determinarlo).
    """
    client = get_redis_client()
    lock = client.lock(f"lock:envio-odc:{oc_id}", timeout=_LOCK_ENVIO_ODC_TIMEOUT_SEGUNDOS)
    acquired = False
    try:
        acquired = lock.acquire(blocking=True, blocking_timeout=blocking_timeout)
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except Exception:
                pass


class OCSAPService:
    """Servicio para enviar órdenes de compra a SAP Service Layer."""
    
    ODC_RETRY_MAX_ATTEMPTS = SAP_ODC_RETRY_MAX_ATTEMPTS
    ODC_RETRY_BASE_DELAY_SECONDS = SAP_ODC_RETRY_BASE_DELAY_SECONDS
    ODC_RETRY_MAX_JITTER_SECONDS = SAP_ODC_RETRY_MAX_JITTER_SECONDS
    
    ITR_RETRY_MAX_ATTEMPTS = SAP_ITR_RETRY_MAX_ATTEMPTS
    ITR_RETRY_BASE_DELAY_SECONDS = SAP_ITR_RETRY_BASE_DELAY_SECONDS
    ITR_RETRY_MAX_JITTER_SECONDS = SAP_ITR_RETRY_MAX_JITTER_SECONDS

    PREVALIDACION_RETRY_MAX_ATTEMPTS = SAP_PREVALIDACION_RETRY_MAX_ATTEMPTS
    PREVALIDACION_RETRY_BASE_DELAY_SECONDS = SAP_PREVALIDACION_RETRY_BASE_DELAY_SECONDS
    PREVALIDACION_RETRY_MAX_JITTER_SECONDS = SAP_PREVALIDACION_RETRY_MAX_JITTER_SECONDS

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
                response.get("error", _ERROR_DESCONOCIDO)
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
            Código de bodega (ej: "RL-CD", "OUT-CD", "RG-CD") o None si no se puede determinar
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

    def _prevalidar_con_reintento(
        self,
        oc_cabecera: Dict[str, Any],
        oc_detalles: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Prevalida contra SAP Service Layer con reintento y backoff ante saturación
        transitoria (HTTP 202 encolado por el middleware). Errores de validación
        reales (item/proveedor inexistente, etc.) no se reintentan.
        """
        resultado = retry_operation(
            execute=lambda: self._precheck_against_service_layer(oc_cabecera, oc_detalles),
            is_success=lambda response: bool(response and response.get("valid")),
            extract_error=lambda response: (
                '; '.join(response.get("errors", [])) if response else _ERROR_DESCONOCIDO
            ),
            max_attempts=self.PREVALIDACION_RETRY_MAX_ATTEMPTS,
            should_retry=lambda response: mensaje_sugiere_reintento_transitorio(
                '; '.join(response.get("errors", [])) if response else None
            ),
            base_delay_seconds=self.PREVALIDACION_RETRY_BASE_DELAY_SECONDS,
            max_jitter_seconds=self.PREVALIDACION_RETRY_MAX_JITTER_SECONDS,
            logger=logger,
            operation_label="Prevalidación SAP",
        )
        return resultado["response"]

    @staticmethod
    def _resumir_errores_prevalidacion(errores: List[str], total_lineas_oc: int) -> str:
        """
        Colapsa errores de prevalidación repetidos (ej. "SAP saturado" en las 12
        líneas de la ODC) a una sola oración con el conteo, en vez de listar la
        misma razón línea por línea. Si las líneas fallan por motivos distintos
        entre sí, mantiene el detalle completo porque ahí sí importa saber qué
        línea falló y por qué.
        """
        lineas_por_razon: Dict[str, int] = {}
        otros_errores: List[str] = []
        for error in errores:
            match = _LINEA_ERROR_RE.match(error)
            if match:
                razon = match.group(1)
                lineas_por_razon[razon] = lineas_por_razon.get(razon, 0) + 1
            else:
                otros_errores.append(error)

        total_lineas_con_error = sum(lineas_por_razon.values())
        if len(lineas_por_razon) == 1 and total_lineas_con_error > 1:
            (razon, count), = lineas_por_razon.items()
            resumen = f"{razon} ({count} de {total_lineas_oc} líneas)"
            return '; '.join(otros_errores + [resumen])
        return '; '.join(errores)

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
        prevalidacion = self._prevalidar_con_reintento(oc_cabecera, oc_detalles)
        if not prevalidacion["valid"]:
            errores_prevalidacion = prevalidacion.get("errors", [])
            errores_resumidos = self._resumir_errores_prevalidacion(errores_prevalidacion, len(oc_detalles))
            error_msg = f"Prevalidación SAP falló: {errores_resumidos}"
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
        error_msg = sap_response.get("error", _ERROR_DESCONOCIDO)
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
        result: Dict[str, Any],
        tiendas_destino_filtro: Optional[List[str]] = None
    ) -> None:
        """Crea Solicitudes de Transferencia para el pedido asociado a la ODC.

        tiendas_destino_filtro acota las tiendas procesadas -- útil cuando el pedido
        tiene más de una ODC (una por bodega/marca), para que cada ODC genere ST solo
        hacia SUS tiendas sin procesar (y omitir con warning) las de la otra bodega
        (ver enviar_oc_a_sap)."""
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
                serie=serie_itr,
                tiendas_destino_filtro=tiendas_destino_filtro
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
        except SolicitudTransferenciaNoAplicaError as e:
            # No es una falla de SAP/Service Layer: la distribución del pedido no tiene
            # destino a tienda (ej. todo va a bodega), así que no corresponde generar ITR.
            # Se guarda con la misma forma que un resultado "sin ST" normal (ver
            # docs/FRONTEND_MODAL_INTEGRACION_SAP.md, Caso 1) para que ni el modal ni el
            # correo a técnicos lo traten como un error.
            logger.info(f"ℹ️ Solicitudes de Transferencia no aplican para pedido {pedido_id}: {e}")
            result["solicitudes_transferencia"] = {
                "success": False,
                "transferencias_creadas": 0,
                "transferencias_errores": 0,
                "total_tiendas": 0,
                "error": str(e),
                "no_aplica": True,
            }
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
            if resultado_st.get("no_aplica"):
                # Distribución sin destino a tienda: resultado esperado, no un error de SAP.
                return False
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
        result: Dict[str, Any],
        tiendas_destino_filtro: Optional[List[str]] = None
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
                self._crear_solicitudes_transferencia_oc(
                    oc_id, oc_cabecera, doc_num, serie_itr, oc_repo, pedido_id, result,
                    tiendas_destino_filtro=tiendas_destino_filtro
                )
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

    @staticmethod
    def resolver_tiendas_destino_filtro(oc_repo: 'OrdenCompraRepository', oc_id: str) -> Optional[List[str]]:
        """
        Si esta ODC pertenece a un pedido con más de una ODC (pedido mixto, una por
        bodega/marca -- ver PedidoOCService.crear_ocs_desde_pedido_confirmado),
        devuelve las tiendas propias de la bodega de ESTA ODC, para pasarlas como
        tiendas_destino_filtro a enviar_oc_a_sap y evitar ST duplicadas (ver su
        docstring). Devuelve None si el pedido tiene una sola ODC (caso normal,
        sin cambios) o si no se pudo determinar -- fail-open, igual que hoy.

        Usar antes de cualquier reenvío/reintento manual o por lote de una ODC
        puntual (no aplica al envío inicial de un pedido mixto, que ya arma este
        filtro directamente en endpoints_proceso.py::_paso2_generar_odc).
        """
        try:
            oc_cabecera = oc_repo.get_existing_cabecera(oc_id)
            if not oc_cabecera:
                return None
            pedido_id = oc_cabecera.get("pedido_id")
            codigo_bodega = oc_cabecera.get("codigo_bodega")
            if not pedido_id or not codigo_bodega:
                return None
            ocs_del_pedido = oc_repo.get_by_pedido_id(pedido_id)
            if len(ocs_del_pedido) <= 1:
                return None
            from .pedido_oc_service import PedidoOCService
            tiendas_por_bodega = PedidoOCService._tiendas_por_bodega(oc_repo.conn, pedido_id, [codigo_bodega])
            return tiendas_por_bodega.get(codigo_bodega) or None
        except Exception as e:
            logger.warning(f"⚠️ No se pudo resolver tiendas_destino_filtro para OC {oc_id}: {e}")
            return None

    def enviar_oc_a_sap(
        self,
        oc_repo: OrdenCompraRepository,
        oc_id: str,
        warehouse_code: Optional[str] = None,
        tiendas_destino_filtro: Optional[List[str]] = None
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
            tiendas_destino_filtro: Lista opcional de códigos de tienda a los que
                acotar las Solicitudes de Transferencia generadas tras el envío
                (ver StockTransferService.crear_solicitudes_transferencia_desde_pedido).
                Útil cuando el pedido tiene más de una ODC (una por bodega/marca): sin
                este filtro, cada ODC igual solo generaría ST hacia sus propias tiendas
                (la validación de bodega ya rechaza cruces), pero recorrería también las
                tiendas de la otra bodega solo para omitirlas con warning.

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

        with redis_lock_envio_odc(oc_id) as adquirido:
            if not adquirido:
                error_msg = "Ya hay un envío a SAP en curso para esta ODC. Espera a que termine antes de reintentar."
                result["error"] = error_msg
                result["error_message"] = error_msg
                result["error_source"] = "BACKEND"
                result["retry_recommended"] = True
                logger.warning(f"⚠️ {error_msg} (oc_id={oc_id})")
                return result

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
                    oc_id, oc_cabecera, oc_detalles, sap_response, envio_oc_result, oc_repo, result,
                    tiendas_destino_filtro=tiendas_destino_filtro
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
    def _extraer_linea(detalle_linea: Dict[str, Any]) -> tuple:
        """Extrae (sku, cantidad, bodega) normalizados de una línea de detalle."""
        sku = detalle_linea.get("sku_sap", "").strip()
        cantidad = float(detalle_linea.get("cantidad_sap", 0))
        bodega = (detalle_linea.get("codigo_bodega") or detalle_linea.get("warehouse_code") or "").strip()
        return sku, cantidad, bodega

    @staticmethod
    def _registrar_validacion_linea(
        idx, sku, bodega, cantidad, validacion_item, errors, warnings, detalle
    ) -> tuple:
        """Registra el resultado de validación de una línea. Retorna (validados, con_error)."""
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
    def _validar_linea_detalle_sap(
        idx, detalle_linea, sap_client, errors, warnings, detalle
    ) -> tuple:
        sku, cantidad, bodega = OCSAPService._extraer_linea(detalle_linea)
        if cantidad <= 0:
            return 0, 0
        if not sku:
            errors.append(f"Línea {idx}: SKU vacío")
            return 0, 1
        logger.debug(f"🔍 Validando línea {idx}: {sku} en bodega {bodega}")
        validacion_item = sap_client.validate_item_in_warehouse(sku, bodega)
        return OCSAPService._registrar_validacion_linea(
            idx, sku, bodega, cantidad, validacion_item, errors, warnings, detalle
        )

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

    @staticmethod
    def _validar_proveedor_batch(bp_result, card_code, errors, detalle) -> None:
        """Registra la validación del proveedor a partir de la respuesta batch del middleware."""
        if not card_code:
            return
        if bp_result is None or bp_result.get("errorType") == "connection_error":
            errors.append(f"Error de conexión al validar proveedor '{card_code}'")
            detalle["proveedor"] = {"error": "conexion", "card_code": card_code}
            return
        error_type = bp_result.get("errorType")
        if error_type == "not_found" or not bp_result.get("exists"):
            errors.append(f"Proveedor '{card_code}' no existe en SAP BusinessPartners")
            detalle["proveedor"] = {"error": "no_existe", "card_code": card_code}
        elif error_type:
            errors.append(bp_result.get("errorMessage") or f"Error al validar proveedor {card_code}")
            detalle["proveedor"] = {"error": error_type, "card_code": card_code}
        elif bp_result.get("frozen"):
            errors.append(f"Proveedor '{card_code}' está CONGELADO en SAP (Frozen=tYES)")
            detalle["proveedor"] = {"error": "congelado", "card_code": card_code}
        elif bp_result.get("valid") is False:
            errors.append(f"Proveedor '{card_code}' no está activo en SAP (Valid=tNO)")
            detalle["proveedor"] = {"error": "inactivo", "card_code": card_code}
        else:
            detalle["proveedor"] = {
                "valid": True,
                "card_code": card_code,
                "card_name": bp_result.get("cardName"),
                "card_type": bp_result.get("cardType"),
            }
            logger.info(f"✅ Proveedor validado (batch): {card_code} - {bp_result.get('cardName')}")

    @staticmethod
    def _validacion_desde_batch_item(item_result, sku, bodega) -> Dict[str, Any]:
        """
        Traduce un elemento de la respuesta batch al mismo formato que
        SAPServiceLayerClient.validate_item_in_warehouse, para reutilizar
        el registro de líneas sin lógica nueva.
        """
        result = {
            "valid": False,
            "item_exists": False,
            "is_purchase_item": False,
            "warehouse_configured": False,
            "stock": None,
            "errors": [],
        }
        if item_result is None or item_result.get("errorType") == "connection_error":
            result["errors"].append(f"Error de conexión al validar artículo {sku}")
            return result

        error_type = item_result.get("errorType")
        if error_type == "item_not_found":
            result["errors"].append(f"Artículo '{sku}' no existe en SAP")
            return result
        if error_type and error_type != "warehouse_not_found":
            result["errors"].append(item_result.get("errorMessage") or f"Error al validar {sku}")
            return result

        result["item_exists"] = True
        if not item_result.get("purchaseItem"):
            result["errors"].append(
                f"Artículo '{sku}' no está habilitado para compra (PurchaseItem=tNO)"
            )
            return result

        result["is_purchase_item"] = True
        if error_type == "warehouse_not_found":
            result["errors"].append(
                f"Artículo '{sku}' no está configurado en bodega '{bodega}'. "
                f"Contacte a logística para dar de alta el artículo en la bodega '{bodega}'."
            )
            return result

        result["warehouse_configured"] = True
        in_stock = float(item_result.get("inStock") or 0)
        committed = float(item_result.get("isCommitted") or 0)
        result["stock"] = in_stock - committed
        result["valid"] = True
        return result

    @staticmethod
    def _validar_articulos_batch(
        oc_detalles, items_lookup, errors, warnings, detalle
    ) -> tuple:
        """Valida todas las líneas usando el lookup de la respuesta batch."""
        articulos_validados = 0
        articulos_con_error = 0
        for idx, detalle_linea in enumerate(oc_detalles, start=1):
            sku, cantidad, bodega = OCSAPService._extraer_linea(detalle_linea)
            if cantidad <= 0:
                continue
            if not sku:
                errors.append(f"Línea {idx}: SKU vacío")
                articulos_con_error += 1
                continue
            validacion_item = OCSAPService._validacion_desde_batch_item(
                items_lookup.get((sku, bodega)), sku, bodega
            )
            validated, with_error = OCSAPService._registrar_validacion_linea(
                idx, sku, bodega, cantidad, validacion_item, errors, warnings, detalle
            )
            articulos_validados += validated
            articulos_con_error += with_error
        return articulos_validados, articulos_con_error

    def _precheck_batch(
        self, oc_cabecera, oc_detalles, errors, warnings, detalle
    ) -> Optional[tuple]:
        """
        Prevalidación con una sola llamada batch al middleware.

        Retorna (articulos_validados, articulos_con_error), o None si el batch
        no está disponible (el caller hace fallback a la validación por línea).
        """
        proveedor = (oc_cabecera.get("proveedor") or "").strip()
        card_code = None
        if proveedor:
            card_code = proveedor if proveedor.startswith('P') else f"P{proveedor}"

        pares_unicos = {}
        for detalle_linea in oc_detalles:
            sku, cantidad, bodega = self._extraer_linea(detalle_linea)
            if cantidad > 0 and sku:
                pares_unicos[(sku, bodega)] = {"itemCode": sku, "warehouseCode": bodega}

        # Límite del contrato batch del middleware; con más pares se usa la vía por línea
        if len(pares_unicos) > 500:
            logger.warning(
                f"⚠️ Batch omitido: {len(pares_unicos)} pares únicos supera el límite de 500"
            )
            return None

        batch = self.sap_client.validate_purchase_order_batch(
            card_code, list(pares_unicos.values())
        )
        if batch is None:
            return None

        self._validar_proveedor_batch(batch.get("businessPartner"), card_code, errors, detalle)
        items_lookup = {
            (item.get("itemCode"), item.get("warehouseCode")): item
            for item in (batch.get("items") or [])
        }
        return self._validar_articulos_batch(oc_detalles, items_lookup, errors, warnings, detalle)

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

        resultado_batch = None
        if USE_BATCH_VALIDATION:
            resultado_batch = self._precheck_batch(
                oc_cabecera, oc_detalles, errors, warnings, detalle
            )
            if resultado_batch is None:
                logger.warning(
                    "⚠️ Validación batch no disponible; fallback a validación línea por línea"
                )
                errors.clear()
                warnings.clear()
                detalle["proveedor"] = {}
                detalle["articulos"] = {}

        if resultado_batch is not None:
            articulos_validados, articulos_con_error = resultado_batch
        else:
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
                
                tiendas_destino_filtro = self.resolver_tiendas_destino_filtro(oc_repo, oc_id)
                resultado = self.enviar_oc_a_sap(oc_repo, oc_id, warehouse_code, tiendas_destino_filtro)
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

