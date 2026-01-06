"""
Servicio para manejar interfaz web del proveedor (FASE 3).
Reutiliza validaciones y lógica de PedidoProveedorService.
Soporta borrador/confirmado y es idempotente.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..connection import get_db_connection_context
from ..repositories.pedido_repository import PedidoRepository
from ..repositories.pedido_respuesta_repository import PedidoRespuestaRepository
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
                repo.update_estado(pedido_id, "RESPUESTA_PROVEEDOR_CARGADA")
            
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
