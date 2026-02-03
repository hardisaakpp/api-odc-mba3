"""
Servicio para procesar confirmación del proveedor y ajustar pedidos (FASE 4).
Ajusta cantidades por tienda, recalcula costos y genera reportes de diferencias.

CORRECCIONES APLICADAS:
- ✅ Separación lógica de pasos (SRP)
- ✅ Redondeo seguro con Decimal
- ✅ Un solo commit transaccional
- ✅ Validación de idempotencia (rowcount)
- ✅ Cambio de estado al final
- ✅ Reload del pedido post-commit para reporte preciso
"""

import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal, ROUND_HALF_UP

from ..connection import get_db_connection_context
from ..pedido_estados import ESTADO_CONFIRMADO_PROVEEDOR
from ..repositories.pedido_repository import PedidoRepository
from ..repositories.pedido_respuesta_repository import PedidoRespuestaRepository

logger = logging.getLogger(__name__)


class PedidoAjusteService:
    """Servicio para ajustar pedidos después de confirmación del proveedor."""
    
    def procesar_confirmacion_proveedor(
        self,
        pedido_id: str,
        usuario_id: Optional[str] = None,
        forzar_redistribucion: bool = False
    ) -> Dict[str, Any]:
        """
        Procesa la confirmación del proveedor y ajusta el pedido.
        
        FLUJO TRANSACCIONAL (un solo commit):
        1. Validar estado de respuesta
        2. Aplicar ajustes (cantidades + costos)
        3. Cerrar respuesta y pedido
        4. Commit único
        5. Reload del pedido actualizado
        6. Generar reporte (con datos actualizados)
        
        Args:
            pedido_id: UUID del pedido
            usuario_id: User ID del usuario que procesa la confirmación
            forzar_redistribucion: Si True, redistribuye aunque haya distribución específica
            
        Returns:
            Dict con resultado del procesamiento y reporte de diferencias
        """
        with get_db_connection_context() as conn:
            respuesta_repo = PedidoRespuestaRepository(conn)
            pedido_repo = PedidoRepository(conn)
            
            # PASO 1: Validar estado
            respuesta, pedido = self._validar_estado_respuesta(
                conn=conn,
                pedido_id=pedido_id,
                respuesta_repo=respuesta_repo,
                pedido_repo=pedido_repo
            )
            
            # PASO 2: Aplicar ajustes (sin commit aún)
            ajustes_realizados = self._aplicar_ajustes(
                conn=conn,
                respuesta=respuesta,
                pedido=pedido,
                forzar_redistribucion=forzar_redistribucion
            )
            
            # PASO 3: Cerrar respuesta y pedido (sin commit aún)
            self._cerrar_respuesta_y_pedido(
                conn=conn,
                respuesta_id=respuesta["cabecera"]["respuesta_id"],
                pedido_id=pedido_id,
                usuario_id=usuario_id,
                pedido_repo=pedido_repo
            )
            
            # ✅ COMMIT ÚNICO: Todo o nada
            conn.commit()
            logger.info(f"✅ Confirmación procesada exitosamente para pedido {pedido_id}")
            
            # ✅ CORRECCIÓN PUNTO 1: Reload del pedido POST-COMMIT
            # Esto asegura que el reporte muestre las cantidades actualizadas por tienda
            pedido_actualizado = pedido_repo.get_pedido_completo(pedido_id)
            if not pedido_actualizado:
                logger.warning(f"⚠️ No se pudo recargar pedido {pedido_id} después del commit")
                pedido_actualizado = pedido  # Fallback al original
        
        # PASO 4: Generar reporte (fuera de transacción, con datos actualizados)
        reporte_diferencias = self._generar_reporte_diferencias_interno(
            respuesta=respuesta,
            pedido=pedido_actualizado  # ✅ Usar pedido actualizado
        )
        
        # Calcular resumen
        total_solicitado = sum(d["cantidad_solicitada"] for d in reporte_diferencias)
        total_confirmado = sum(d["cantidad_confirmada"] for d in reporte_diferencias)
        total_diferencia = total_confirmado - total_solicitado
        
        return {
            "status": "success",
            "message": "Confirmación del proveedor procesada exitosamente",
            "pedido_id": pedido_id,
            "respuesta_id": respuesta["cabecera"]["respuesta_id"],
            "ajustes_realizados": len(ajustes_realizados),
            "resumen": {
                "total_productos": len(ajustes_realizados),
                "total_solicitado": total_solicitado,
                "total_confirmado": total_confirmado,
                "total_diferencia": total_diferencia,
                "porcentaje_confirmacion": round(
                    (total_confirmado / total_solicitado * 100) if total_solicitado > 0 else 0, 
                    2
                )
            },
            "reporte_diferencias": reporte_diferencias,
            "ajustes_detalle": ajustes_realizados
        }
    
    def _validar_estado_respuesta(
        self,
        conn,
        pedido_id: str,
        respuesta_repo: PedidoRespuestaRepository,
        pedido_repo: PedidoRepository
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Valida que la respuesta esté en estado correcto para procesar.
        
        Returns:
            Tupla (respuesta, pedido)
        """
        respuesta = respuesta_repo.obtener_respuesta_activa(pedido_id)
        if not respuesta:
            raise ValueError(f"No existe respuesta del proveedor para el pedido {pedido_id}")
        
        if respuesta["cabecera"]["estado"] != "PENDIENTE_REVISION":
            raise ValueError(
                f"La respuesta debe estar en estado PENDIENTE_REVISION. "
                f"Estado actual: {respuesta['cabecera']['estado']}"
            )
        
        pedido = pedido_repo.get_pedido_completo(pedido_id)
        if not pedido:
            raise ValueError(f"Pedido no encontrado: {pedido_id}")
        
        return respuesta, pedido
    
    def _aplicar_ajustes(
        self,
        conn,
        respuesta: Dict[str, Any],
        pedido: Dict[str, Any],
        forzar_redistribucion: bool
    ) -> List[Dict[str, Any]]:
        """
        Aplica todos los ajustes necesarios (cantidades y costos).
        
        ⚠️ NO hace commit - debe ser parte de transacción mayor.
        
        Returns:
            Lista de ajustes realizados
        """
        ajustes_realizados = []
        
        for detalle_respuesta in respuesta["detalles"]:
            pedido_detalle_id = detalle_respuesta["pedido_detalle_id"]
            cantidad_confirmada = detalle_respuesta["cantidad_confirmada_total"]
            
            # Buscar detalle del pedido
            detalle_pedido = next(
                (d for d in pedido["detalles"] 
                 if d["pedido_detalle_id"] == pedido_detalle_id),
                None
            )
            if not detalle_pedido:
                logger.warning(f"Detalle {pedido_detalle_id} no encontrado en pedido")
                continue
            
            # Ajustar cantidades por tienda
            ajuste_tiendas = self._ajustar_cantidades_por_tienda(
                conn=conn,
                pedido_detalle_id=pedido_detalle_id,
                cantidad_confirmada_total=cantidad_confirmada,
                distribucion_original=detalle_pedido["tiendas"],
                respuesta_id=respuesta["cabecera"]["respuesta_id"],
                forzar_redistribucion=forzar_redistribucion
            )
            
            # Recalcular costos si hay cambios de precio
            costo_ajustado = None
            if detalle_respuesta.get("costo_doc_sin_iva_ajustado") is not None:
                costo_ajustado = self._actualizar_costos_producto(
                    conn=conn,
                    pedido_detalle_id=pedido_detalle_id,
                    costo_ajustado=detalle_respuesta["costo_doc_sin_iva_ajustado"],
                    descuento_ajustado=detalle_respuesta.get("descuento_1_ajustado"),
                    cantidad_confirmada=cantidad_confirmada
                )
            
            ajustes_realizados.append({
                "pedido_detalle_id": pedido_detalle_id,
                "codigo_producto": detalle_respuesta["codigo_producto"],
                "cantidad_solicitada": detalle_respuesta["cantidad_solicitada_total"],
                "cantidad_confirmada": cantidad_confirmada,
                "diferencia": cantidad_confirmada - detalle_respuesta["cantidad_solicitada_total"],
                "ajuste_tiendas": ajuste_tiendas,
                "costo_actualizado": costo_ajustado is not None
            })
        
        return ajustes_realizados
    
    def _ajustar_cantidades_por_tienda(
        self,
        conn,
        pedido_detalle_id: str,
        cantidad_confirmada_total: int,
        distribucion_original: List[Dict[str, Any]],
        respuesta_id: str,
        forzar_redistribucion: bool = False
    ) -> Dict[str, Any]:
        """
        Ajusta las cantidades por tienda para que coincidan con el total confirmado.
        
        ⚠️ NO hace commit - debe ser parte de transacción mayor.
        
        ESTRATEGIA:
        1. Si existe distribución específica en pedido_respuesta_proveedor_detalle_tienda, usarla
        2. Si no, redistribuir proporcionalmente según cantidades originales
        
        Returns:
            Dict con información del ajuste realizado
        """
        cursor = conn.cursor()
        
        try:
            # Verificar si existe distribución específica del proveedor
            cursor.execute("""
                SELECT 
                    rdt.pedido_detalle_tienda_id,
                    rdt.cantidad_confirmada
                FROM pedido_respuesta_proveedor_detalle_tienda rdt
                INNER JOIN pedido_respuesta_proveedor_detalle rd 
                    ON rdt.respuesta_detalle_id = rd.id
                WHERE rd.respuesta_id = ? 
                    AND rd.pedido_detalle_id = ?
            """, (respuesta_id, pedido_detalle_id))
            
            distribucion_especifica = {}
            for row in cursor.fetchall():
                distribucion_especifica[str(row[0])] = int(row[1])
            
            # Calcular total de distribución específica
            total_distribucion_especifica = sum(distribucion_especifica.values())
            
            usar_distribucion_especifica = (
                len(distribucion_especifica) > 0 
                and total_distribucion_especifica == cantidad_confirmada_total
                and not forzar_redistribucion
            )
            
            if usar_distribucion_especifica:
                # Usar distribución específica del proveedor
                ajustes = []
                for pedido_detalle_tienda_id, cantidad_confirmada in distribucion_especifica.items():
                    cursor.execute("""
                        UPDATE pedido_detalle_tienda
                        SET cantidad = ?
                        WHERE id = ?
                    """, (cantidad_confirmada, pedido_detalle_tienda_id))
                    ajustes.append({
                        "pedido_detalle_tienda_id": pedido_detalle_tienda_id,
                        "cantidad_anterior": None,
                        "cantidad_nueva": cantidad_confirmada,
                        "metodo": "distribucion_especifica"
                    })
                
                return {
                    "metodo": "distribucion_especifica",
                    "tiendas_ajustadas": len(ajustes),
                    "ajustes": ajustes
                }
            else:
                # Redistribuir proporcionalmente
                cantidad_total_original = sum(t["cantidad"] for t in distribucion_original)
                
                if cantidad_total_original == 0:
                    raise ValueError(
                        f"No hay cantidades originales para redistribuir en detalle {pedido_detalle_id}"
                    )
                
                # ✅ CORRECCIÓN: Redondeo seguro con Decimal
                ajustes = []
                cantidad_asignada = Decimal(0)
                cantidad_confirmada_decimal = Decimal(cantidad_confirmada_total)
                
                # Ordenar por cantidad (mayor a menor) para mejor distribución
                distribucion_ordenada = sorted(
                    distribucion_original,
                    key=lambda x: x["cantidad"],
                    reverse=True
                )
                
                for i, tienda in enumerate(distribucion_ordenada):
                    if i == len(distribucion_ordenada) - 1:
                        # Última tienda: asignar el resto para que sume exactamente
                        cantidad_nueva = int(cantidad_confirmada_decimal - cantidad_asignada)
                    else:
                        # Calcular proporción con Decimal
                        proporcion = Decimal(tienda["cantidad"]) / Decimal(cantidad_total_original)
                        cantidad_calculada = (cantidad_confirmada_decimal * proporcion).quantize(
                            Decimal('1'), 
                            rounding=ROUND_HALF_UP
                        )
                        cantidad_nueva = int(cantidad_calculada)
                        cantidad_asignada += Decimal(cantidad_nueva)
                    
                    # Actualizar cantidad en BD (sin commit)
                    cursor.execute("""
                        UPDATE pedido_detalle_tienda
                        SET cantidad = ?
                        WHERE pedido_detalle_id = ?
                            AND tienda_id = ?
                    """, (cantidad_nueva, pedido_detalle_id, tienda["tienda_id"]))
                    
                    ajustes.append({
                        "tienda_id": tienda["tienda_id"],
                        "tienda_codigo": tienda["codigo"],
                        "cantidad_anterior": tienda["cantidad"],
                        "cantidad_nueva": cantidad_nueva,
                        "diferencia": cantidad_nueva - tienda["cantidad"],
                        "metodo": "redistribucion_proporcional"
                    })
                
                return {
                    "metodo": "redistribucion_proporcional",
                    "tiendas_ajustadas": len(ajustes),
                    "ajustes": ajustes
                }
                
        except Exception as e:
            logger.error(f"❌ Error al ajustar cantidades por tienda: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def _actualizar_costos_producto(
        self,
        conn,
        pedido_detalle_id: str,
        costo_ajustado: float,
        descuento_ajustado: Optional[float],
        cantidad_confirmada: int
    ) -> Dict[str, Any]:
        """
        Actualiza los costos del producto en pedido_detalle y recalcula totales.
        
        ⚠️ NO hace commit - debe ser parte de transacción mayor.
        
        Returns:
            Dict con información del costo actualizado
        """
        cursor = conn.cursor()
        
        try:
            # Obtener costo y descuento original
            cursor.execute("""
                SELECT costo_doc_sin_iva, descuento_1
                FROM pedido_detalle
                WHERE pedido_detalle_id = ?
            """, (pedido_detalle_id,))
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Detalle no encontrado: {pedido_detalle_id}")
            
            costo_original = float(row[0]) if row[0] else None
            descuento_original = float(row[1]) if row[1] else None
            
            # Calcular nuevos totales con Decimal para precisión
            cantidad_decimal = Decimal(cantidad_confirmada)
            costo_decimal = Decimal(str(costo_ajustado))
            
            # Subtotal = cantidad * costo_unitario
            subtotal_nuevo = float(cantidad_decimal * costo_decimal)
            
            # Aplicar descuento si existe
            descuento_aplicar = descuento_ajustado if descuento_ajustado is not None else descuento_original
            if descuento_aplicar:
                total_nuevo = subtotal_nuevo * (1 - descuento_aplicar / 100)
            else:
                total_nuevo = subtotal_nuevo
            
            # Actualizar en BD (sin commit)
            update_fields = ["costo_doc_sin_iva = ?", "subtotal = ?", "total = ?"]
            values: List[Any] = [costo_ajustado, subtotal_nuevo, total_nuevo]
            
            if descuento_ajustado is not None:
                update_fields.append("descuento_1 = ?")
                values.append(descuento_ajustado)
            
            values.append(pedido_detalle_id)
            
            cursor.execute(f"""
                UPDATE pedido_detalle
                SET {', '.join(update_fields)}
                WHERE pedido_detalle_id = ?
            """, values)
            
            return {
                "costo_original": costo_original,
                "costo_ajustado": costo_ajustado,
                "descuento_original": descuento_original,
                "descuento_ajustado": descuento_ajustado,
                "subtotal_nuevo": subtotal_nuevo,
                "total_nuevo": total_nuevo,
                "cantidad_confirmada": cantidad_confirmada
            }
            
        except Exception as e:
            logger.error(f"❌ Error al actualizar costos: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def _cerrar_respuesta_y_pedido(
        self,
        conn,
        respuesta_id: str,
        pedido_id: str,
        usuario_id: Optional[str] = None,
        pedido_repo: Optional[PedidoRepository] = None
    ) -> None:
        """
        Cierra la respuesta (aprobación) y actualiza estado del pedido.
        
        ⚠️ NO hace commit - debe ser parte de transacción mayor.
        
        ORDEN CORRECTO:
        1. Aprobar respuesta (con validación de idempotencia)
        2. Cambiar estado del pedido (último paso)
        """
        cursor = conn.cursor()
        
        try:
            # ✅ CORRECCIÓN: Validación de idempotencia
            # Solo actualiza si está en estado correcto (evita race conditions)
            cursor.execute("""
                UPDATE pedido_respuesta_proveedor
                SET estado = 'APROBADA',
                    fecha_aprobacion = GETDATE(),
                    aprobado_por = ?,
                    updated_at = GETDATE()
                WHERE respuesta_id = ?
                    AND estado = 'PENDIENTE_REVISION'
            """, (usuario_id, respuesta_id))
            
            rows_affected = cursor.rowcount
            
            if rows_affected == 0:
                # Alguien ya procesó esta respuesta
                raise ValueError(
                    f"La respuesta {respuesta_id} ya fue procesada o no está en estado PENDIENTE_REVISION"
                )
            
            if rows_affected > 1:
                # Esto no debería pasar (respuesta_id es PK), pero por seguridad
                logger.warning(f"⚠️ Múltiples filas actualizadas para respuesta {respuesta_id}")
            
            logger.debug(f"✅ Respuesta {respuesta_id} aprobada")
            
            # ✅ CORRECCIÓN: Cambio de estado del pedido al final
            # Esto debe ser el último paso antes del commit
            if pedido_repo:
                pedido_repo.update_estado(pedido_id, ESTADO_CONFIRMADO_PROVEEDOR)
                logger.debug(f"✅ Estado del pedido {pedido_id} actualizado a CONFIRMADO_PROVEEDOR")
            
        except Exception as e:
            logger.error(f"❌ Error al cerrar respuesta y pedido: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def _generar_reporte_diferencias_interno(
        self,
        respuesta: Dict[str, Any],
        pedido: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Genera reporte de diferencias (solo lectura, fuera de transacción).
        
        Returns:
            Lista de diferencias por producto
        """
        reporte = []
        
        for detalle_respuesta in respuesta["detalles"]:
            cantidad_solicitada = detalle_respuesta["cantidad_solicitada_total"]
            cantidad_confirmada = detalle_respuesta["cantidad_confirmada_total"]
            diferencia = cantidad_confirmada - cantidad_solicitada
            porcentaje = (diferencia / cantidad_solicitada * 100) if cantidad_solicitada > 0 else 0
            
            # Obtener distribución por tienda del pedido actualizado
            detalle_pedido = next(
                (d for d in pedido["detalles"] 
                 if d["pedido_detalle_id"] == detalle_respuesta["pedido_detalle_id"]),
                None
            )
            
            distribucion_tiendas = []
            if detalle_pedido:
                distribucion_tiendas = [
                    {
                        "tienda_codigo": t["codigo"],
                        "tienda_nombre": t["nombre"],
                        "cantidad": t["cantidad"]
                    }
                    for t in detalle_pedido["tiendas"]
                ]
            
            reporte.append({
                "codigo_producto": detalle_respuesta["codigo_producto"],
                "descripcion": detalle_respuesta["descripcion"],
                "cantidad_solicitada": cantidad_solicitada,
                "cantidad_confirmada": cantidad_confirmada,
                "diferencia": diferencia,
                "porcentaje_diferencia": round(porcentaje, 2),
                "costo_original": detalle_respuesta.get("costo_doc_sin_iva_original"),
                "costo_ajustado": detalle_respuesta.get("costo_doc_sin_iva_ajustado"),
                "cambio_precio": detalle_respuesta.get("costo_doc_sin_iva_ajustado") is not None,
                "distribucion_tiendas": distribucion_tiendas,
                "observaciones": detalle_respuesta.get("observaciones")
            })
        
        return reporte
    
    def generar_reporte_diferencias(
        self,
        pedido_id: str,
        formato: str = "json"
    ) -> Dict[str, Any]:
        """
        Genera un reporte de diferencias entre solicitado y confirmado.
        
        Args:
            pedido_id: UUID del pedido
            formato: Formato del reporte ('json', 'excel', 'csv')
            
        Returns:
            Dict con reporte o bytes del archivo según formato
        """
        with get_db_connection_context() as conn:
            respuesta_repo = PedidoRespuestaRepository(conn)
            pedido_repo = PedidoRepository(conn)
            
            respuesta = respuesta_repo.obtener_respuesta_activa(pedido_id)
            pedido = pedido_repo.get_pedido_completo(pedido_id)
            
            if not respuesta or not pedido:
                raise ValueError(f"Pedido o respuesta no encontrados: {pedido_id}")
            
            reporte_detalle = self._generar_reporte_diferencias_interno(respuesta, pedido)
            
            # Calcular totales
            total_solicitado = sum(r["cantidad_solicitada"] for r in reporte_detalle)
            total_confirmado = sum(r["cantidad_confirmada"] for r in reporte_detalle)
            total_diferencia = total_confirmado - total_solicitado
            
            resultado = {
                "pedido_id": pedido_id,
                "numero_pedido": pedido["cabecera"]["numero_pedido"],
                "resumen": {
                    "total_productos": len(reporte_detalle),
                    "total_solicitado": total_solicitado,
                    "total_confirmado": total_confirmado,
                    "total_diferencia": total_diferencia,
                    "porcentaje_confirmacion": round(
                        (total_confirmado / total_solicitado * 100) if total_solicitado > 0 else 0, 
                        2
                    )
                },
                "detalle": reporte_detalle
            }
            
            if formato == "json":
                return resultado
            elif formato == "excel":
                raise NotImplementedError("Exportación a Excel pendiente de implementar")
            elif formato == "csv":
                raise NotImplementedError("Exportación a CSV pendiente de implementar")
            else:
                raise ValueError(f"Formato no soportado: {formato}")

