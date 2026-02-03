"""
Servicio para manejar interfaz web del proveedor (FASE 3).
Reutiliza validaciones y lógica de PedidoProveedorService.
Soporta borrador/confirmado y es idempotente.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..connection import get_db_connection_context
from ..pedido_estados import ESTADO_RESPUESTA_PROVEEDOR_CARGADA
from ..repositories.pedido_repository import PedidoRepository
from ..repositories.pedido_respuesta_repository import PedidoRespuestaRepository
from ..repositories.pedido_confirmacion_rayo_repository import PedidoConfirmacionRayoRepository
from .pedido_proveedor_service import PedidoProveedorService

logger = logging.getLogger(__name__)


class PedidoProveedorWebService:
    """Servicio para interfaz web del proveedor."""
    
    def __init__(self):
        self.proveedor_service = PedidoProveedorService()
    
    def obtener_formulario_proveedor(self, pedido_id: str) -> Dict[str, Any]:
        """
        Obtiene los datos del pedido formateados para el formulario web.
        
        Características:
        - Idempotente: muestra respuesta existente si ya respondió
        - Indica si puede responder (no está cerrado/bloqueado)
        - Incluye datos de respuesta previa si existe
        
        Args:
            pedido_id: UUID del pedido
            
        Returns:
            Dict con datos formateados para formulario
        """
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = repo.get_pedido_completo(pedido_id)
            
            if not pedido:
                raise ValueError(f"Pedido no encontrado: {pedido_id}")
            
            cabecera = pedido["cabecera"]
            detalles = pedido["detalles"]
            
            # Obtener respuesta existente si existe
            respuesta_repo = PedidoRespuestaRepository(conn)
            respuesta_existente = respuesta_repo.obtener_respuesta_activa(pedido_id)
            
            # Determinar si puede responder
            estado_pedido = cabecera.get("estado", "PENDIENTE_CONFIRMACION_PROVEEDOR")
            estados_bloqueados = [
                "CONFIRMADO_PROVEEDOR",
                "ORDEN_COMPRA_CREADA",
                "ENVIADA_SAP",
                "CERRADO",
                "CANCELADO"
            ]
            puede_responder = estado_pedido not in estados_bloqueados
            
            # Formatear productos para formulario
            productos_formulario = []
            
            # Crear mapa de respuestas existentes por pedido_detalle_id
            mapa_respuestas = {}
            if respuesta_existente:
                for detalle_respuesta in respuesta_existente.get("detalles", []):
                    pedido_detalle_id = detalle_respuesta.get("pedido_detalle_id")
                    if pedido_detalle_id:
                        mapa_respuestas[pedido_detalle_id] = detalle_respuesta
            
            for detalle in detalles:
                pedido_detalle_id = detalle["pedido_detalle_id"]
                respuesta_detalle = mapa_respuestas.get(pedido_detalle_id, {})
                
                # Calcular total solicitado
                cantidad_total = sum(t["cantidad"] for t in detalle["tiendas"])
                
                # Formatear tiendas
                tiendas_formulario = []
                for tienda in detalle["tiendas"]:
                    tiendas_formulario.append({
                        "tienda_id": tienda["tienda_id"],
                        "codigo": tienda["codigo"],
                        "nombre": tienda.get("nombre"),
                        "cantidad_solicitada": tienda["cantidad"]
                    })
                
                producto = {
                    "pedido_detalle_id": pedido_detalle_id,
                    "codigo_producto": detalle["codigo_interno"],
                    "descripcion": detalle.get("descripcion_sap"),
                    "marca": detalle.get("marca"),
                    "cantidad_total_solicitada": cantidad_total,
                    "costo_unitario_original": detalle.get("costo_doc_sin_iva"),
                    "descuento_original": detalle.get("descuento_1"),
                    "tiendas": tiendas_formulario,
                    # Datos de respuesta existente (si hay)
                    "cantidad_confirmada_total": respuesta_detalle.get("cantidad_confirmada_total"),
                    "costo_unitario_ajustado": respuesta_detalle.get("costo_doc_sin_iva_ajustado"),
                    "descuento_ajustado": respuesta_detalle.get("descuento_1_ajustado"),
                    "observaciones": respuesta_detalle.get("observaciones")
                }
                
                productos_formulario.append(producto)
            
            # Mensaje de estado
            mensaje_estado = None
            if not puede_responder:
                mensaje_estado = f"El pedido está en estado '{estado_pedido}' y no puede ser modificado."
            elif respuesta_existente:
                estado_resp = respuesta_existente.get("estado", "PENDIENTE_REVISION")
                if estado_resp == "BORRADOR":
                    mensaje_estado = "Tiene una respuesta guardada como borrador. Puede continuar editando."
                elif estado_resp == "PENDIENTE_REVISION":
                    mensaje_estado = "Ya envió una respuesta que está pendiente de revisión. Puede crear una nueva versión."
                elif estado_resp == "APROBADA":
                    mensaje_estado = "Ya tiene una respuesta aprobada. Puede crear una nueva versión si necesita cambios."
            
            # Manejar fecha_pedido (puede venir como string ISO o como date)
            fecha_pedido = cabecera.get("fecha_pedido")
            if fecha_pedido:
                if hasattr(fecha_pedido, 'isoformat'):
                    fecha_pedido = fecha_pedido.isoformat()
                elif not isinstance(fecha_pedido, str):
                    fecha_pedido = str(fecha_pedido)
            
            return {
                "pedido_id": pedido_id,
                "numero_pedido": cabecera.get("numero_pedido"),
                "fecha_pedido": fecha_pedido,
                "fecha_entrega": cabecera.get("fecha_entrega"),
                "proveedor_nombre": cabecera.get("proveedor_nombre"),
                "estado_pedido": estado_pedido,
                "puede_responder": puede_responder,
                "tiene_respuesta": respuesta_existente is not None,
                "respuesta_id": respuesta_existente.get("respuesta_id") if respuesta_existente else None,
                "version_respuesta": respuesta_existente.get("version") if respuesta_existente else None,
                "estado_respuesta": respuesta_existente.get("estado") if respuesta_existente else None,
                "productos": productos_formulario,
                "mensaje_estado": mensaje_estado
            }
    
    def procesar_respuesta_proveedor_web(
        self,
        pedido_id: str,
        productos: List[Dict[str, Any]],
        observaciones_generales: Optional[str] = None,
        estado: str = "borrador",
        usuario_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Procesa la respuesta del proveedor desde el formulario web.
        
        Reutiliza validaciones de PedidoProveedorService.
        Soporta guardar como borrador o confirmado.
        
        Args:
            pedido_id: UUID del pedido
            productos: Lista de productos con respuestas
            observaciones_generales: Observaciones generales
            estado: 'borrador' o 'confirmado'
            usuario_id: User ID del usuario (opcional, para auditoría)
            
        Returns:
            Dict con resultado del procesamiento
        """
        with get_db_connection_context() as conn:
            # Obtener pedido completo para validación
            repo = PedidoRepository(conn)
            pedido = repo.get_pedido_completo(pedido_id)
            
            if not pedido:
                raise ValueError(f"Pedido no encontrado: {pedido_id}")
            
            # Verificar que puede responder
            estado_pedido = pedido["cabecera"].get("estado", "PENDIENTE_CONFIRMACION_PROVEEDOR")
            estados_bloqueados = [
                "CONFIRMADO_PROVEEDOR",
                "ORDEN_COMPRA_CREADA",
                "ENVIADA_SAP",
                "CERRADO",
                "CANCELADO"
            ]
            if estado_pedido in estados_bloqueados:
                raise ValueError(f"El pedido está en estado '{estado_pedido}' y no puede ser modificado")
            
            # Convertir productos a formato de validación
            respuestas_cantidades = []
            respuestas_precios = []
            
            # Crear mapa de productos del pedido
            mapa_productos = {}
            for detalle in pedido["detalles"]:
                codigo = detalle["codigo_interno"]
                mapa_productos[codigo] = {
                    "pedido_detalle_id": detalle["pedido_detalle_id"],
                    "cantidad_solicitada_total": sum(t["cantidad"] for t in detalle["tiendas"]),
                    "costo_original": detalle.get("costo_doc_sin_iva"),
                    "descuento_original": detalle.get("descuento_1")
                }
            
            for producto_resp in productos:
                pedido_detalle_id = producto_resp.get("pedido_detalle_id")
                codigo_producto = producto_resp.get("codigo_producto")
                cantidad_confirmada = producto_resp.get("cantidad_confirmada_total", 0)
                
                # Validar que el producto existe en el pedido
                if codigo_producto not in mapa_productos:
                    logger.warning(f"Producto {codigo_producto} no encontrado en pedido, omitiendo")
                    continue
                
                producto_info = mapa_productos[codigo_producto]
                
                # Agregar a respuestas de cantidades
                respuestas_cantidades.append({
                    "pedido_detalle_id": pedido_detalle_id,
                    "codigo_producto": codigo_producto,
                    "cantidad_solicitada_total": producto_info["cantidad_solicitada_total"],
                    "cantidad_confirmada_total": cantidad_confirmada,
                    "observaciones": producto_resp.get("observaciones")
                })
                
                # Agregar a respuestas de precios si hay ajustes
                costo_ajustado = producto_resp.get("costo_unitario_ajustado")
                descuento_ajustado = producto_resp.get("descuento_ajustado")
                
                if costo_ajustado is not None:
                    respuestas_precios.append({
                        "pedido_detalle_id": pedido_detalle_id,
                        "codigo_producto": codigo_producto,
                        "costo_doc_sin_iva_original": producto_info["costo_original"],
                        "costo_doc_sin_iva_ajustado": costo_ajustado,
                        "descuento_1_original": producto_info["descuento_original"],
                        "descuento_1_ajustado": descuento_ajustado,
                        "observaciones_precio": None
                    })
            
            # ✅ Validar usando el servicio existente
            validacion = self.proveedor_service.validar_respuesta_proveedor(
                pedido=pedido,
                respuestas_cantidades=respuestas_cantidades,
                respuestas_precios=respuestas_precios
            )
            
            # Si es confirmado, debe pasar validación estricta
            if estado == "confirmado" and not validacion["valido"]:
                return {
                    "status": "validation_error",
                    "message": "La respuesta contiene errores de validación y no puede ser confirmada",
                    "validacion": validacion,
                    "errores": validacion["errores"],
                    "warnings": validacion["warnings"],
                    "pedido_id": pedido_id
                }
            
            # Guardar respuesta
            respuesta_repo = PedidoRespuestaRepository(conn)
            
            # Si es borrador, buscar si existe uno previo para actualizar
            respuesta_id = None
            if estado == "borrador":
                respuesta_existente = respuesta_repo.obtener_respuesta_activa(pedido_id)
                if respuesta_existente and respuesta_existente.get("estado") == "BORRADOR":
                    respuesta_id = respuesta_existente.get("respuesta_id")
                    # Actualizar respuesta existente (eliminar detalles anteriores y crear nuevos)
                    # Por simplicidad, creamos nueva versión siempre
                    # TODO: Implementar actualización de borrador si es necesario
            
            # Crear nueva respuesta (o nueva versión)
            if not respuesta_id:
                respuesta_id = respuesta_repo.crear_respuesta_proveedor(
                    pedido_id=pedido_id,
                    usuario_id=usuario_id,
                    observaciones_generales=observaciones_generales
                )
            
            # Determinar estado de la respuesta
            estado_respuesta = "BORRADOR" if estado == "borrador" else "PENDIENTE_REVISION"
            
            # Actualizar estado de la respuesta si es necesario
            if respuesta_id:
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        UPDATE pedido_respuesta_proveedor
                        SET estado = ?,
                            observaciones_generales = ?,
                            updated_at = GETDATE()
                        WHERE respuesta_id = ?
                    """, (estado_respuesta, observaciones_generales, respuesta_id))
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error al actualizar estado de respuesta: {e}")
                    raise
                finally:
                    cursor.close()
            
            # Guardar detalles
            resultado_guardado = respuesta_repo.guardar_respuesta_detalles(
                respuesta_id=respuesta_id,
                respuestas_cantidades=respuestas_cantidades,
                respuestas_precios=respuestas_precios
            )
            
            # Si es confirmado, actualizar estado del pedido
            if estado == "confirmado":
                repo.update_estado(pedido_id, ESTADO_RESPUESTA_PROVEEDOR_CARGADA)
            
            return {
                "status": "success",
                "message": f"Respuesta del proveedor guardada como {estado}",
                "respuesta_id": respuesta_id,
                "validacion": validacion,
                "cantidades_guardadas": resultado_guardado["cantidades_guardadas"],
                "precios_guardados": resultado_guardado["precios_guardados"],
                "pedido_id": pedido_id,
                "estado_guardado": estado_respuesta
            }
    
    def crear_respuesta_desde_pedido(
        self,
        pedido_id: str,
        usuario_id: Optional[str] = None,
        observaciones_generales: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Crea automáticamente una respuesta del proveedor desde los detalles del pedido.
        
        Este método se usa cuando EL RAYO ha editado directamente los campos del pedido
        (total y costo_doc_sin_iva) y necesita generar la respuesta automáticamente.
        
        Args:
            pedido_id: UUID del pedido
            usuario_id: User ID del usuario (opcional, para auditoría)
            observaciones_generales: Observaciones generales (opcional)
            
        Returns:
            Dict con resultado del procesamiento incluyendo respuesta_id
        """
        with get_db_connection_context() as conn:
            # Obtener pedido completo
            repo = PedidoRepository(conn)
            pedido = repo.get_pedido_completo(pedido_id)
            
            if not pedido:
                logger.error(f"Pedido {pedido_id} no encontrado")
                raise ValueError(f"Pedido no encontrado: {pedido_id}")
            
            logger.debug(f"Pedido {pedido_id} encontrado con {len(pedido.get('detalles', []))} detalles")
            
            # Verificar si ya existe una respuesta activa
            respuesta_repo = PedidoRespuestaRepository(conn)
            respuesta_existente = respuesta_repo.obtener_respuesta_activa(pedido_id)
            
            respuesta_id = None
            ya_existia_respuesta = False
            
            if respuesta_existente:
                # Si ya existe una respuesta, usar la existente
                respuesta_id = respuesta_existente["cabecera"]["respuesta_id"]
                ya_existia_respuesta = True
                logger.info(f"Ya existe respuesta {respuesta_id} para pedido {pedido_id}, se usará para la confirmación")
            
            # Validar que el pedido tenga detalles
            detalles = pedido.get("detalles", [])
            if not detalles or len(detalles) == 0:
                logger.error(f"Pedido {pedido_id} no tiene detalles")
                raise ValueError(f"El pedido {pedido_id} no tiene detalles")
            
            logger.debug(f"Procesando {len(detalles)} detalles del pedido {pedido_id}")
            
            # Convertir detalles del pedido a formato de respuesta
            respuestas_cantidades = []
            respuestas_precios = []
            
            for detalle in pedido["detalles"]:
                pedido_detalle_id = detalle.get("pedido_detalle_id")
                codigo_producto = detalle.get("codigo_interno")
                
                # Validar campos requeridos
                if not pedido_detalle_id:
                    logger.warning(f"Detalle sin pedido_detalle_id, omitiendo")
                    continue
                
                if not codigo_producto:
                    logger.warning(f"Detalle {pedido_detalle_id} sin codigo_interno, usando 'SIN_CODIGO'")
                    codigo_producto = "SIN_CODIGO"
                
                # Validar que tenga tiendas
                tiendas = detalle.get("tiendas", [])
                if not tiendas:
                    logger.warning(f"Detalle {pedido_detalle_id} sin tiendas, omitiendo")
                    continue
                
                # Obtener cantidad solicitada total (suma de todas las tiendas)
                cantidad_solicitada_total = sum(t.get("cantidad", 0) for t in tiendas)
                
                # ⭐ MEJORADO: Leer total directamente desde BD para asegurar valor más reciente
                # y verificar si fue modificado manualmente por EL RAYO
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        SELECT 
                            total,
                            ISNULL(total_modificado_manual, 0) AS total_modificado_manual
                        FROM pedido_detalle
                        WHERE pedido_detalle_id = ?
                    """, (pedido_detalle_id,))
                    row = cursor.fetchone()
                    
                    if row:
                        total_value = float(row[0]) if row[0] is not None else None
                        total_modificado_manual = bool(row[1])
                    else:
                        total_value = detalle.get("total")
                        total_modificado_manual = detalle.get("total_modificado_manual", False)
                        logger.warning(f"No se pudo leer total desde BD para {pedido_detalle_id}, usando valor del detalle")
                except Exception as e:
                    logger.warning(f"Error al leer total desde BD para {pedido_detalle_id}: {e}, usando valor del detalle")
                    total_value = detalle.get("total")
                    total_modificado_manual = detalle.get("total_modificado_manual", False)
                finally:
                    cursor.close()
                
                # ⭐ MEJORADO: Obtener cantidad confirmada desde el campo "total" del detalle
                # NOTA: En el frontend, cuando EL RAYO edita, el campo "total" se usa para la cantidad confirmada
                # El valor 0 es válido para la lógica del negocio
                if total_value is not None:
                    # Convertir a entero (puede venir como float desde la BD)
                    try:
                        cantidad_confirmada_total = int(float(total_value))
                        
                        # ⭐ VALIDACIÓN: Si EL RAYO modificó manualmente el total, validar explícitamente
                        if total_modificado_manual:
                            if cantidad_confirmada_total < 0:
                                error_msg = (
                                    f"El producto {codigo_producto} (ID: {pedido_detalle_id}) "
                                    f"fue modificado manualmente por EL RAYO pero el total es negativo ({cantidad_confirmada_total}). "
                                    f"El total debe ser mayor o igual a 0. Por favor, verifique el valor antes de confirmar."
                                )
                                logger.error(f"❌ {error_msg}")
                                raise ValueError(error_msg)
                            
                            # ⭐ VALIDACIÓN ESPECÍFICA: Si total_modificado_manual es True y el valor es 0, registrar explícitamente
                            if cantidad_confirmada_total == 0:
                                logger.info(
                                    f"✅ Producto {codigo_producto} (ID: {pedido_detalle_id}): "
                                    f"EL RAYO modificó manualmente el total a 0. "
                                    f"Esto es válido para la lógica del negocio. "
                                    f"Se procesará con cantidad_confirmada_total = 0."
                                )
                            else:
                                logger.info(
                                    f"✅ Producto {codigo_producto} (ID: {pedido_detalle_id}): "
                                    f"Usando total modificado por EL RAYO: {cantidad_confirmada_total} "
                                    f"(cantidad solicitada original: {cantidad_solicitada_total})"
                                )
                        else:
                            # Si no fue modificado manualmente, usar el valor tal cual
                            if cantidad_confirmada_total != cantidad_solicitada_total:
                                logger.info(
                                    f"ℹ️ Producto {codigo_producto} (ID: {pedido_detalle_id}): "
                                    f"Total ({cantidad_confirmada_total}) difiere de cantidad solicitada ({cantidad_solicitada_total}), "
                                    f"pero no fue marcado como modificado manualmente."
                                )
                            else:
                                logger.debug(
                                    f"Producto {codigo_producto} (ID: {pedido_detalle_id}): "
                                    f"Total coincide con cantidad solicitada: {cantidad_confirmada_total}"
                                )
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            f"⚠️ Error al convertir total a entero para {codigo_producto} (ID: {pedido_detalle_id}): {e}. "
                            f"Usando cantidad solicitada como fallback: {cantidad_solicitada_total}"
                        )
                        cantidad_confirmada_total = cantidad_solicitada_total
                else:
                    # Si total es None, usar cantidad solicitada
                    if total_modificado_manual:
                        error_msg = (
                            f"El producto {codigo_producto} (ID: {pedido_detalle_id}) "
                            f"fue marcado como modificado manualmente por EL RAYO pero el total es None. "
                            f"Por favor, verifique que el total tenga un valor antes de confirmar."
                        )
                        logger.error(f"❌ {error_msg}")
                        raise ValueError(error_msg)
                    
                    logger.warning(
                        f"⚠️ Producto {codigo_producto} (ID: {pedido_detalle_id}): "
                        f"Total no disponible (None), usando cantidad solicitada como fallback: {cantidad_solicitada_total}"
                    )
                    cantidad_confirmada_total = cantidad_solicitada_total
                
                # Obtener costos originales y ajustados
                costo_original = detalle.get("costo_doc_sin_iva")
                costo_ajustado = detalle.get("costo_doc_sin_iva")  # El costo ajustado es el mismo que el original si no se modificó
                
                descuento_original = detalle.get("descuento_1")
                descuento_ajustado = detalle.get("descuento_1")
                
                # Agregar a respuestas de cantidades
                respuestas_cantidades.append({
                    "pedido_detalle_id": pedido_detalle_id,
                    "codigo_producto": codigo_producto,
                    "cantidad_solicitada_total": cantidad_solicitada_total,
                    "cantidad_confirmada_total": cantidad_confirmada_total,
                    "observaciones": None
                })
                
                # Agregar a respuestas de precios si hay costos
                if costo_original is not None:
                    respuestas_precios.append({
                        "pedido_detalle_id": pedido_detalle_id,
                        "codigo_producto": codigo_producto,
                        "costo_doc_sin_iva_original": costo_original,
                        "costo_doc_sin_iva_ajustado": costo_ajustado,
                        "descuento_1_original": descuento_original,
                        "descuento_1_ajustado": descuento_ajustado,
                        "observaciones_precio": None
                    })
            
            # Validar que haya al menos una respuesta
            if not respuestas_cantidades:
                logger.error(f"No se pudo crear ninguna respuesta para pedido {pedido_id}: el pedido no tiene detalles válidos")
                raise ValueError(f"No se pudo crear ninguna respuesta: el pedido no tiene detalles válidos")
            
            logger.debug(f"Se crearon {len(respuestas_cantidades)} respuestas de cantidades y {len(respuestas_precios)} respuestas de precios")
            
            # Validar usando el servicio existente
            try:
                validacion = self.proveedor_service.validar_respuesta_proveedor(
                    pedido=pedido,
                    respuestas_cantidades=respuestas_cantidades,
                    respuestas_precios=respuestas_precios
                )
            except Exception as e:
                logger.error(f"Error en validación de respuesta: {e}", exc_info=True)
                raise ValueError(f"Error al validar respuesta: {str(e)}")
            
            # Crear respuesta solo si no existe
            if not respuesta_id:
                respuesta_id = respuesta_repo.crear_respuesta_proveedor(
                    pedido_id=pedido_id,
                    usuario_id=usuario_id,
                    observaciones_generales=observaciones_generales
                )
            else:
                # Actualizar observaciones si cambió
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        UPDATE pedido_respuesta_proveedor
                        SET observaciones_generales = ?,
                            updated_at = GETDATE()
                        WHERE respuesta_id = ?
                    """, (observaciones_generales, respuesta_id))
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error al actualizar observaciones de respuesta: {e}")
                    raise
                finally:
                    cursor.close()
            
            # Actualizar estado a PENDIENTE_REVISION (listo para procesar) solo si no existía
            if not ya_existia_respuesta:
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        UPDATE pedido_respuesta_proveedor
                        SET estado = 'PENDIENTE_REVISION',
                            observaciones_generales = ?,
                            updated_at = GETDATE()
                        WHERE respuesta_id = ?
                    """, (observaciones_generales, respuesta_id))
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error al actualizar estado de respuesta: {e}")
                    raise
                finally:
                    cursor.close()
            
            # Guardar detalles (solo si no existía respuesta, o si se quiere actualizar)
            # Por ahora, solo actualizamos si no existía
            if not ya_existia_respuesta:
                resultado_guardado = respuesta_repo.guardar_respuesta_detalles(
                    respuesta_id=respuesta_id,
                    respuestas_cantidades=respuestas_cantidades,
                    respuestas_precios=respuestas_precios
                )
            else:
                # Si ya existía respuesta, no actualizamos los detalles
                resultado_guardado = {
                    "cantidades_guardadas": 0,
                    "precios_guardados": 0
                }
                logger.info(f"Respuesta ya existía, no se actualizan detalles de respuesta (solo se registrará confirmación si hay cambios)")
            
            # Actualizar estado del pedido solo si no estaba ya en ese estado
            estado_actual = pedido["cabecera"].get("estado")
            if estado_actual != "RESPUESTA_PROVEEDOR_CARGADA":
                repo.update_estado(pedido_id, ESTADO_RESPUESTA_PROVEEDOR_CARGADA)
            
            # ✅ REGISTRAR CONFIRMACIÓN DE EL RAYO
            # Obtener valores actuales desde la BD para registrar el historial completo
            confirmacion_repo = PedidoConfirmacionRayoRepository(conn)
            
            hay_cambios = False
            confirmaciones_previas = []
            
            try:
                # Obtener valores actuales directamente desde la BD
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        pedido_detalle_id,
                        codigo_interno,
                        costo_doc_sin_iva,
                        total,
                        comentario,
                        ISNULL(costo_modificado_manual, 0) AS costo_modificado_manual,
                        ISNULL(total_modificado_manual, 0) AS total_modificado_manual,
                        ISNULL(comentario_modificado_manual, 0) AS comentario_modificado_manual
                    FROM pedido_detalle
                    WHERE pedido_id = ?
                """, (pedido_id,))
                
                detalles_bd = {}
                for row in cursor.fetchall():
                    detalles_bd[row[0]] = {
                        "pedido_detalle_id": str(row[0]),
                        "codigo_interno": row[1],
                        "costo_doc_sin_iva": float(row[2]) if row[2] is not None else None,
                        "total": float(row[3]) if row[3] is not None else None,
                        "comentario": row[4],
                        "costo_modificado_manual": bool(row[5]),
                        "total_modificado_manual": bool(row[6]),
                        "comentario_modificado_manual": bool(row[7])
                    }
                
                cursor.close()
                
                # Buscar confirmación previa para obtener valores anteriores y validar si hay cambios
                confirmaciones_previas = confirmacion_repo.obtener_confirmaciones_por_pedido(pedido_id, limit=1)
                
                # Crear mapa de valores anteriores desde la última confirmación
                valores_anteriores = {}
                if confirmaciones_previas:
                    ultima_confirmacion = confirmacion_repo.obtener_confirmacion(confirmaciones_previas[0]["confirmacion_id"])
                    if ultima_confirmacion and ultima_confirmacion.get("detalles"):
                        for detalle_conf in ultima_confirmacion["detalles"]:
                            pedido_detalle_id = detalle_conf["pedido_detalle_id"]
                            valores_anteriores[pedido_detalle_id] = {
                                "costo": detalle_conf.get("costo_nuevo"),  # El valor anterior confirmado
                                "total": detalle_conf.get("total_nuevo"),
                                "comentario": detalle_conf.get("comentario_nuevo")
                            }
                
                # Verificar si hay cambios comparando valores actuales con la última confirmación
                detalles_con_cambios = {}
                for pedido_detalle_id, detalle_bd in detalles_bd.items():
                    # Solo verificar si hay algún campo modificado manualmente
                    if not (detalle_bd["costo_modificado_manual"] or 
                           detalle_bd["total_modificado_manual"] or 
                           detalle_bd["comentario_modificado_manual"]):
                        continue
                    
                    valores_ant = valores_anteriores.get(pedido_detalle_id, {})
                    
                    # Comparar valores actuales con los de la última confirmación
                    costo_actual = detalle_bd["costo_doc_sin_iva"]
                    total_actual = detalle_bd["total"]
                    comentario_actual = detalle_bd["comentario"] or ""
                    
                    costo_anterior_conf = valores_ant.get("costo")
                    total_anterior_conf = valores_ant.get("total")
                    comentario_anterior_conf = valores_ant.get("comentario") or ""
                    
                    # Verificar si hay cambios
                    # Para costo y total: comparar valores numéricos con tolerancia
                    if costo_anterior_conf is None and costo_actual is None:
                        cambio_costo = False
                    elif costo_anterior_conf is None or costo_actual is None:
                        cambio_costo = True
                    else:
                        cambio_costo = abs(float(costo_anterior_conf) - float(costo_actual)) > 0.01
                    
                    if total_anterior_conf is None and total_actual is None:
                        cambio_total = False
                    elif total_anterior_conf is None or total_actual is None:
                        cambio_total = True
                    else:
                        cambio_total = abs(float(total_anterior_conf) - float(total_actual)) > 0.01
                    
                    cambio_comentario = comentario_actual != comentario_anterior_conf
                    
                    if cambio_costo or cambio_total or cambio_comentario:
                        hay_cambios = True
                        detalles_con_cambios[pedido_detalle_id] = {
                            "detalle_bd": detalle_bd,
                            "valores_anteriores": valores_ant,
                            "cambio_costo": cambio_costo,
                            "cambio_total": cambio_total,
                            "cambio_comentario": cambio_comentario
                        }
                
                # Solo crear confirmación si hay cambios o si no existe confirmación previa
                if hay_cambios or not confirmaciones_previas:
                    # Crear registro de confirmación
                    confirmacion_id = confirmacion_repo.crear_confirmacion(
                        pedido_id=pedido_id,
                        respuesta_id=respuesta_id,
                        usuario_id=usuario_id or "SISTEMA",
                        observaciones_generales=observaciones_generales
                    )
                    
                    # Contar detalles modificados
                    detalles_modificados_count = 0
                    resumen_cambios = {
                        "cambios_costo": 0,
                        "cambios_total": 0,
                        "cambios_comentario": 0,
                        "detalles": []
                    }
                    
                    # Agregar detalles de confirmación
                    for pedido_detalle_id, info_cambio in detalles_con_cambios.items():
                        detalle_bd = info_cambio["detalle_bd"]
                        valores_ant = info_cambio["valores_anteriores"]
                        
                        detalles_modificados_count += 1
                        
                        # Obtener valores anteriores
                        costo_anterior = valores_ant.get("costo")
                        total_anterior = valores_ant.get("total")
                        comentario_anterior = valores_ant.get("comentario")
                        
                        # Si no hay valores anteriores de confirmación previa, usar valores actuales
                        # (indica que esta es la primera confirmación)
                        if costo_anterior is None:
                            costo_anterior = detalle_bd["costo_doc_sin_iva"]
                        if total_anterior is None:
                            total_anterior = detalle_bd["total"]
                        if comentario_anterior is None:
                            comentario_anterior = detalle_bd["comentario"]
                        
                        # Agregar detalle de confirmación
                        confirmacion_repo.agregar_detalle_confirmacion(
                            confirmacion_id=confirmacion_id,
                            pedido_detalle_id=pedido_detalle_id,
                            costo_anterior=costo_anterior,
                            costo_nuevo=detalle_bd["costo_doc_sin_iva"],
                            total_anterior=total_anterior,
                            total_nuevo=detalle_bd["total"],
                            comentario_anterior=comentario_anterior,
                            comentario_nuevo=detalle_bd["comentario"],
                            codigo_producto=detalle_bd["codigo_interno"]
                        )
                        
                        # Actualizar resumen
                        if info_cambio["cambio_costo"]:
                            resumen_cambios["cambios_costo"] += 1
                        if info_cambio["cambio_total"]:
                            resumen_cambios["cambios_total"] += 1
                        if info_cambio["cambio_comentario"]:
                            resumen_cambios["cambios_comentario"] += 1
                        
                        resumen_cambios["detalles"].append({
                            "pedido_detalle_id": pedido_detalle_id,
                            "codigo_producto": detalle_bd["codigo_interno"],
                            "cambio_costo": info_cambio["cambio_costo"],
                            "cambio_total": info_cambio["cambio_total"],
                            "cambio_comentario": info_cambio["cambio_comentario"]
                        })
                    
                    # Actualizar resumen de confirmación
                    confirmacion_repo.actualizar_resumen_confirmacion(
                        confirmacion_id=confirmacion_id,
                        total_detalles_modificados=detalles_modificados_count,
                        resumen_cambios=resumen_cambios
                    )
                    
                    logger.info(f"✅ Confirmación de EL RAYO registrada: {confirmacion_id} ({detalles_modificados_count} detalles modificados)")
                else:
                    logger.info(f"ℹ️ No se registró nueva confirmación: no hay cambios desde la última confirmación")
                
            except Exception as e:
                # No fallar si no se puede registrar la confirmación, solo loggear
                logger.error(f"⚠️ Error al registrar confirmación de EL RAYO (no crítico): {e}", exc_info=True)
                hay_cambios = False  # En caso de error, asumir que no hay cambios
            
            # Determinar mensaje según si existía respuesta y si se registró confirmación
            if ya_existia_respuesta:
                if hay_cambios or not confirmaciones_previas:
                    message = "Confirmación registrada exitosamente (respuesta ya existía)"
                else:
                    message = "No se registró nueva confirmación: no hay cambios desde la última confirmación"
            else:
                message = "Respuesta del proveedor creada automáticamente desde el pedido"
            
            return {
                "status": "success",
                "message": message,
                "respuesta_id": respuesta_id,
                "validacion": validacion,
                "cantidades_guardadas": resultado_guardado["cantidades_guardadas"],
                "precios_guardados": resultado_guardado["precios_guardados"],
                "pedido_id": pedido_id,
                "estado_guardado": "PENDIENTE_REVISION",
                "ya_existia": ya_existia_respuesta,
                "confirmacion_registrada": hay_cambios or not confirmaciones_previas
            }
