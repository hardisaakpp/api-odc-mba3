import logging
from typing import Dict, Any, List, Optional

from ..connection import get_db_connection_context
from ..repositories.pedido_repository import PedidoRepository

logger = logging.getLogger(__name__)


def guardar_pedido_v1_0(
    resultado: Dict[str, Any],
    pedido_id: Optional[str],
    detalles_finales: List[Dict],
    cabecera: Dict,
) -> bool:
    """Guarda pedido en BD. Retorna True si éxito, False si error."""
    logger.info("📋 PASO 7: Guardando en base de datos")

    try:
        with get_db_connection_context() as conn:
            repository = PedidoRepository(conn)

            try:
                cabecera["estado"] = "PENDIENTE_CONFIRMACION_PROVEEDOR"
            except Exception:
                pass

            pedido_id = repository.insert_cabecera(cabecera)
            resultado["pedido_id"] = pedido_id
            logger.info(f"✅ Cabecera guardada: {pedido_id}")

            for detalle_data in detalles_finales:
                try:
                    # ✅ Calcular subtotal sumando cantidades de distribuciones
                    distribuciones_data = detalle_data.get("distribuciones", [])
                    subtotal_calculado = sum(
                        dist.get("cantidad", 0)
                        for dist in distribuciones_data
                        if isinstance(dist.get("cantidad"), (int, float)) and dist.get("cantidad", 0) > 0
                    )
                    
                    # ✅ Obtener bodega del detalle (manejar NULL)
                    bodega = detalle_data["detalle"].get("bodega")
                    bodega_valor = 0  # Default a 0 si es None
                    if bodega is not None:
                        try:
                            bodega_valor = int(bodega) if isinstance(bodega, (int, float)) else 0
                        except (ValueError, TypeError):
                            bodega_valor = 0
                    
                    # ✅ Calcular TOTAL = SUBTOTAL + BODEGA
                    total_calculado = subtotal_calculado + bodega_valor
                    
                    # Actualizar detalle con subtotal y total calculados
                    detalle_actualizado = detalle_data["detalle"].copy()
                    detalle_actualizado["subtotal"] = subtotal_calculado
                    detalle_actualizado["total"] = total_calculado  # Total = Subtotal + Bodega
                    
                    pedido_detalle_id = repository.insert_detalle(
                        pedido_id=pedido_id, datos_detalle=detalle_actualizado
                    )
                    resultado["articulos_cargados"] += 1

                    if distribuciones_data:
                        distribuciones = []
                        for dist in distribuciones_data:
                            tienda_codigo = dist.get("tienda_codigo")
                            cantidad = dist.get("cantidad")
                            if tienda_codigo and cantidad and cantidad > 0:
                                tienda_id = repository.get_or_create_tienda(
                                    codigo=tienda_codigo, nombre=dist.get("tienda_nombre")
                                )
                                distribuciones.append(
                                    {
                                        "tienda_id": tienda_id,
                                        "cantidad": cantidad,
                                        "fila_origen": dist.get("fila_origen"),
                                    }
                                )

                        if distribuciones:
                            distribuciones_insertadas = repository.insert_detalle_tiendas(
                                pedido_detalle_id=pedido_detalle_id, distribuciones=distribuciones
                            )
                            resultado["distribuciones_cargadas"] += distribuciones_insertadas
                except Exception as e:
                    error_msg = f"Error procesando artículo: {str(e)}"
                    logger.warning(f"⚠️ {error_msg}")
                    resultado["warnings"].append(error_msg)
                    continue

        logger.info(f"✅ Plantilla v1.0 guardada: {resultado['pedido_id']}")
        return True
    except Exception as e:
        logger.error(f"❌ Error guardando: {e}")
        resultado["status"] = "error"
        resultado["errores"].append(str(e))
        return False
