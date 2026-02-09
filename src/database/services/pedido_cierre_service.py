"""
Servicio para evaluar y cerrar pedidos cuando todas sus ODC están enviadas.
"""

import logging
from typing import Optional, Dict, Any
from ..pedido_estados import (
    ESTADO_CONFIRMADO_ENVIADO,
    ESTADO_ERROR_DATOS_MAESTROS,
    ESTADO_PENDIENTE_LOGISTICA,
)
from ..repositories.orden_compra_repository import OrdenCompraRepository
from ..repositories.pedido_repository import PedidoRepository

logger = logging.getLogger(__name__)


class PedidoCierreService:
    """Servicio para evaluar y cerrar pedidos."""
    
    def evaluar_cierre_pedido(
        self,
        pedido_id: str,
        oc_repo: OrdenCompraRepository,
        pedido_repo: PedidoRepository
    ) -> Dict[str, Any]:
        """
        Evalúa si un pedido puede cerrarse (todas sus ODC están enviadas).
        
        Condiciones para cerrar:
        - Todas las ODC asociadas están en estado ENVIADA
        - Todas tienen DocEntry válido (no NULL)
        - No hay ODC en estado ERROR o PENDIENTE
        
        Args:
            pedido_id: UUID del pedido
            oc_repo: Repositorio de órdenes de compra
            pedido_repo: Repositorio de pedidos
            
        Returns:
            {
                "puede_cerrar": bool,
                "total_odc": int,
                "odc_enviadas": int,
                "odc_pendientes": int,
                "odc_con_error": int,
                "odc_sin_doc_entry": int,
                "razon_no_cierre": Optional[str]
            }
        """
        # Obtener todas las ODC del pedido
        ocs = oc_repo.get_by_pedido_id(pedido_id)
        
        if not ocs:
            return {
                "puede_cerrar": False,
                "total_odc": 0,
                "odc_enviadas": 0,
                "odc_pendientes": 0,
                "odc_con_error": 0,
                "odc_sin_doc_entry": 0,
                "razon_no_cierre": "No hay ODC asociadas al pedido"
            }
        
        total_odc = len(ocs)
        odc_enviadas = 0
        odc_pendientes = 0
        odc_con_error = 0
        odc_sin_doc_entry = 0
        
        for oc in ocs:
            estado = oc.get("estado")
            doc_entry = oc.get("doc_entry")
            
            if estado == "ENVIADA":
                odc_enviadas += 1
                # Validar que doc_entry sea válido (no None, no 0, no string vacío)
                if not doc_entry or doc_entry == 0 or (isinstance(doc_entry, str) and not doc_entry.strip()):
                    odc_sin_doc_entry += 1
            elif estado == "PENDIENTE":
                odc_pendientes += 1
            elif estado == "ERROR":
                odc_con_error += 1
        
        # Evaluar si puede cerrar
        puede_cerrar = (
            total_odc > 0 and
            odc_enviadas == total_odc and
            odc_pendientes == 0 and
            odc_con_error == 0 and
            odc_sin_doc_entry == 0
        )
        
        razon_no_cierre = None
        if not puede_cerrar:
            razones = []
            if odc_pendientes > 0:
                razones.append(f"{odc_pendientes} ODC pendientes")
            if odc_con_error > 0:
                razones.append(f"{odc_con_error} ODC con error")
            if odc_sin_doc_entry > 0:
                razones.append(f"{odc_sin_doc_entry} ODC sin DocEntry válido")
            if odc_enviadas < total_odc:
                razones.append(f"Solo {odc_enviadas}/{total_odc} ODC enviadas")
            
            razon_no_cierre = "; ".join(razones) if razones else "Condiciones no cumplidas"
        
        return {
            "puede_cerrar": puede_cerrar,
            "total_odc": total_odc,
            "odc_enviadas": odc_enviadas,
            "odc_pendientes": odc_pendientes,
            "odc_con_error": odc_con_error,
            "odc_sin_doc_entry": odc_sin_doc_entry,
            "razon_no_cierre": razon_no_cierre
        }
    
    def cerrar_pedido_si_corresponde(
        self,
        pedido_id: str,
        oc_repo: OrdenCompraRepository,
        pedido_repo: PedidoRepository,
        resultado_st: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evalúa y actualiza el estado del pedido según el resultado de OC y ST.
        
        ⭐ REGLA DE NEGOCIO:
        - OC OK + ST OK → CONFIRMADO_ENVIADO (pedido completo)
        - OC OK + ST ❌ → PENDIENTE_LOGISTICA (OC lista, pero ST falló)
        - OC ❌ → No cambia estado (OC debe estar OK primero)
        
        Args:
            pedido_id: UUID del pedido
            oc_repo: Repositorio de órdenes de compra
            pedido_repo: Repositorio de pedidos
            resultado_st: Resultado de creación de Solicitudes de Transferencia (opcional)
                {
                    "success": bool,
                    "transferencias_creadas": int,
                    "transferencias_errores": int,
                    "total_tiendas": int,
                    "error": Optional[str]
                }
            
        Returns:
            {
                "cerrado": bool,
                "estado_anterior": Optional[str],
                "estado_nuevo": Optional[str],
                "evaluacion": Dict con detalles de la evaluación
            }
        """
        # Evaluar si OC está OK
        evaluacion = self.evaluar_cierre_pedido(pedido_id, oc_repo, pedido_repo)
        
        # Obtener estado actual del pedido
        pedido = pedido_repo.get_pedido_completo(pedido_id)
        estado_anterior = pedido.get("estado") if pedido else None
        
        # Si OC no está OK, no cambiar estado
        if not evaluacion["puede_cerrar"]:
            logger.debug(
                f"Pedido {pedido_id} no puede cerrarse: {evaluacion['razon_no_cierre']}"
            )
            return {
                "cerrado": False,
                "estado_anterior": estado_anterior,
                "estado_nuevo": None,
                "evaluacion": evaluacion
            }
        
        # OC está OK, ahora verificar ST
        estado_nuevo = None
        razon_estado = None
        
        if resultado_st is None:
            # No se intentó crear ST (puede ser que no haya distribución o no se requiera)
            # En este caso, si OC está OK, podemos cerrar como CONFIRMADO_ENVIADO
            estado_nuevo_id = ESTADO_CONFIRMADO_ENVIADO
            estado_nuevo = "CONFIRMADO_ENVIADO"
            razon_estado = "OC enviada, no se requieren Solicitudes de Transferencia"
        elif resultado_st.get("success", False):
            # ST exitosas → CONFIRMADO_ENVIADO
            estado_nuevo_id = ESTADO_CONFIRMADO_ENVIADO
            estado_nuevo = "CONFIRMADO_ENVIADO"
            razon_estado = (
                f"OC y ST exitosas: {resultado_st.get('transferencias_creadas', 0)}/"
                f"{resultado_st.get('total_tiendas', 0)} transferencias creadas"
            )
        else:
            # ST fallaron - determinar estado según tipo de error
            error_type = resultado_st.get("error_type")
            error_st = resultado_st.get("error")
            transferencias_errores = resultado_st.get("transferencias_errores", 0)
            
            # ⭐ FIX: Si no hay error de nivel superior, extraer de resultados individuales
            if not error_st:
                resultados_st = resultado_st.get("resultados", [])
                errores_individuales = [
                    f"{r.get('tienda_codigo', 'N/A')}: {r.get('error', 'Sin detalle')}"
                    for r in resultados_st
                    if not r.get("success") and r.get("error")
                ]
                error_st = "; ".join(errores_individuales) if errores_individuales else "Error desconocido al crear Solicitudes de Transferencia"
            
            if error_type == "datos_maestros":
                # ❌ ERROR DE DATOS MAESTROS: No es problema de logística
                estado_nuevo_id = ESTADO_ERROR_DATOS_MAESTROS
                estado_nuevo = "ERROR_DATOS_MAESTROS"
                razon_estado = (
                    f"OC enviada pero ST fallaron por errores de datos maestros en SAP. "
                    f"Error: {error_st}"
                )
                logger.error(
                    f"❌ Pedido {pedido_id}: OC OK pero ST fallaron por datos maestros. "
                    f"Estado: {estado_anterior} → {estado_nuevo}"
                )
            else:
                # Stock insuficiente u otro error → PENDIENTE_LOGISTICA
                estado_nuevo_id = ESTADO_PENDIENTE_LOGISTICA
                estado_nuevo = "PENDIENTE_LOGISTICA"
                razon_estado = (
                    f"OC enviada pero ST fallaron: {transferencias_errores} error(es). "
                    f"Error: {error_st}"
                )
                logger.warning(
                    f"⚠️ Pedido {pedido_id}: OC OK pero ST fallaron. "
                    f"Estado: {estado_anterior} → {estado_nuevo}"
                )
        
        # Actualizar estado del pedido (por id)
        actualizado = pedido_repo.update_estado(pedido_id, estado_nuevo_id)
        
        if actualizado:
            if estado_nuevo == "CONFIRMADO_ENVIADO":
                logger.info(
                    f"✅ Pedido {pedido_id} cerrado: {estado_anterior} → {estado_nuevo} "
                    f"({evaluacion['odc_enviadas']}/{evaluacion['total_odc']} ODC enviadas). "
                    f"{razon_estado}"
                )
            else:
                logger.info(
                    f"📋 Pedido {pedido_id} actualizado: {estado_anterior} → {estado_nuevo}. "
                    f"{razon_estado}"
                )
            return {
                "cerrado": (estado_nuevo == "CONFIRMADO_ENVIADO"),
                "estado_anterior": estado_anterior,
                "estado_nuevo": estado_nuevo,
                "evaluacion": evaluacion,
                "razon_estado": razon_estado
            }
        else:
            logger.warning(f"⚠️ No se pudo actualizar estado del pedido {pedido_id}")
            return {
                "cerrado": False,
                "estado_anterior": estado_anterior,
                "estado_nuevo": None,
                "evaluacion": evaluacion
            }

