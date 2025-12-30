"""
Servicio para evaluar y cerrar pedidos cuando todas sus ODC están enviadas.
"""

import logging
from typing import Optional, Dict, Any
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
        pedido_repo: PedidoRepository
    ) -> Dict[str, Any]:
        """
        Cierra un pedido si todas sus ODC están enviadas.
        
        Args:
            pedido_id: UUID del pedido
            oc_repo: Repositorio de órdenes de compra
            pedido_repo: Repositorio de pedidos
            
        Returns:
            {
                "cerrado": bool,
                "estado_anterior": Optional[str],
                "estado_nuevo": Optional[str],
                "evaluacion": Dict con detalles de la evaluación
            }
        """
        # Evaluar si puede cerrar
        evaluacion = self.evaluar_cierre_pedido(pedido_id, oc_repo, pedido_repo)
        
        if not evaluacion["puede_cerrar"]:
            logger.debug(
                f"Pedido {pedido_id} no puede cerrarse: {evaluacion['razon_no_cierre']}"
            )
            return {
                "cerrado": False,
                "estado_anterior": None,
                "estado_nuevo": None,
                "evaluacion": evaluacion
            }
        
        # Obtener estado actual del pedido
        pedido = pedido_repo.get_pedido_completo(pedido_id)
        estado_anterior = pedido.get("estado") if pedido else None
        
        # Actualizar estado a CONFIRMADO_ENVIADO
        actualizado = pedido_repo.update_estado(pedido_id, "CONFIRMADO_ENVIADO")
        
        if actualizado:
            logger.info(
                f"✅ Pedido {pedido_id} cerrado: {estado_anterior} → CONFIRMADO_ENVIADO "
                f"({evaluacion['odc_enviadas']}/{evaluacion['total_odc']} ODC enviadas)"
            )
            return {
                "cerrado": True,
                "estado_anterior": estado_anterior,
                "estado_nuevo": "CONFIRMADO_ENVIADO",
                "evaluacion": evaluacion
            }
        else:
            logger.warning(f"⚠️ No se pudo actualizar estado del pedido {pedido_id}")
            return {
                "cerrado": False,
                "estado_anterior": estado_anterior,
                "estado_nuevo": None,
                "evaluacion": evaluacion
            }

