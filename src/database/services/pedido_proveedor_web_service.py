"""
Servicio para manejar interfaz web del proveedor (FASE 3).
Reutiliza validaciones y lógica de PedidoProveedorService.
Soporta borrador/confirmado y es idempotente.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..connection import get_db_connection_context
from ..pedido_estados import ESTADO_REDISTRIBUCION
from ..repositories.pedido_repository import PedidoRepository
from ..repositories.pedido_respuesta_repository import PedidoRespuestaRepository
from ..repositories.pedido_confirmacion_rayo_repository import PedidoConfirmacionRayoRepository
from .pedido_proveedor_service import PedidoProveedorService
from src.utils.audit_context import AuditContext, ORIGEN_WEB
from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)


class PedidoProveedorWebService:
    """Servicio para interfaz web del proveedor."""

    def __init__(self):
        self.proveedor_service = PedidoProveedorService()

    # ── helpers: obtener_formulario_proveedor ──────────────────────────────

    @staticmethod
    def _construir_mapa_respuestas(respuesta_existente: Optional[Dict]) -> Dict:
        if not respuesta_existente:
            return {}
        mapa: Dict = {}
        for dr in respuesta_existente.get("detalles", []):
            pdid = dr.get("pedido_detalle_id")
            if pdid:
                mapa[pdid] = dr
        return mapa

    @staticmethod
    def _mensaje_estado_formulario(
        puede_responder: bool,
        estado_pedido: str,
        respuesta_existente: Optional[Dict],
    ) -> Optional[str]:
        if not puede_responder:
            return f"El pedido está en estado '{estado_pedido}' y no puede ser modificado."
        if not respuesta_existente:
            return None
        estado_resp = respuesta_existente.get("estado", "PENDIENTE_REVISION")
        if estado_resp == "BORRADOR":
            return "Tiene una respuesta guardada como borrador. Puede continuar editando."
        if estado_resp == "PENDIENTE_REVISION":
            return "Ya envió una respuesta que está pendiente de revisión. Puede crear una nueva versión."
        if estado_resp == "APROBADA":
            return "Ya tiene una respuesta aprobada. Puede crear una nueva versión si necesita cambios."
        return None

    @staticmethod
    def _normalizar_fecha(fecha: Any) -> Optional[str]:
        if not fecha:
            return fecha
        if hasattr(fecha, "isoformat"):
            return fecha.isoformat()
        if not isinstance(fecha, str):
            return str(fecha)
        return fecha

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

            respuesta_repo = PedidoRespuestaRepository(conn)
            respuesta_existente = respuesta_repo.obtener_respuesta_activa(pedido_id)

            estado_pedido = cabecera.get("estado", "PENDIENTE_CONFIRMACION_PROVEEDOR")
            estados_bloqueados = [
                "CONFIRMADO_PROVEEDOR",
                "ORDEN_COMPRA_CREADA",
                "ENVIADA_SAP",
                "CERRADO",
                "CANCELADO",
            ]
            puede_responder = estado_pedido not in estados_bloqueados
            mapa_respuestas = self._construir_mapa_respuestas(respuesta_existente)

            productos_formulario = []
            for detalle in detalles:
                pedido_detalle_id = detalle["pedido_detalle_id"]
                respuesta_detalle = mapa_respuestas.get(pedido_detalle_id, {})
                cantidad_total = sum(t["cantidad"] for t in detalle["tiendas"])
                tiendas_formulario = [
                    {
                        "tienda_id": t["tienda_id"],
                        "codigo": t["codigo"],
                        "nombre": t.get("nombre"),
                        "cantidad_solicitada": t["cantidad"],
                    }
                    for t in detalle["tiendas"]
                ]
                productos_formulario.append({
                    "pedido_detalle_id": pedido_detalle_id,
                    "codigo_producto": detalle["codigo_interno"],
                    "descripcion": detalle.get("descripcion_sap"),
                    "marca": detalle.get("marca"),
                    "cantidad_total_solicitada": cantidad_total,
                    "costo_unitario_original": detalle.get("costo_doc_sin_iva"),
                    "descuento_original": detalle.get("descuento_1"),
                    "tiendas": tiendas_formulario,
                    "cantidad_confirmada_total": respuesta_detalle.get("cantidad_confirmada_total"),
                    "costo_unitario_ajustado": respuesta_detalle.get("costo_doc_sin_iva_ajustado"),
                    "descuento_ajustado": respuesta_detalle.get("descuento_1_ajustado"),
                    "observaciones": respuesta_detalle.get("observaciones"),
                })

            return {
                "pedido_id": pedido_id,
                "numero_pedido": cabecera.get("numero_pedido"),
                "fecha_pedido": self._normalizar_fecha(cabecera.get("fecha_pedido")),
                "fecha_entrega": cabecera.get("fecha_entrega"),
                "proveedor_nombre": cabecera.get("proveedor_nombre"),
                "estado_pedido": estado_pedido,
                "puede_responder": puede_responder,
                "tiene_respuesta": respuesta_existente is not None,
                "respuesta_id": respuesta_existente.get("respuesta_id") if respuesta_existente else None,
                "version_respuesta": respuesta_existente.get("version") if respuesta_existente else None,
                "estado_respuesta": respuesta_existente.get("estado") if respuesta_existente else None,
                "productos": productos_formulario,
                "mensaje_estado": self._mensaje_estado_formulario(
                    puede_responder, estado_pedido, respuesta_existente
                ),
            }

    # ── helpers: procesar_respuesta_proveedor_web ─────────────────────────

    @staticmethod
    def _convertir_productos_a_respuestas(
        productos: List[Dict[str, Any]],
        mapa_productos: Dict[str, Any],
    ) -> Tuple[List, List]:
        respuestas_cantidades: List[Dict] = []
        respuestas_precios: List[Dict] = []
        for producto_resp in productos:
            codigo_producto = producto_resp.get("codigo_producto")
            if codigo_producto not in mapa_productos:
                logger.warning(f"Producto {codigo_producto} no encontrado en pedido, omitiendo")
                continue
            pedido_detalle_id = producto_resp.get("pedido_detalle_id")
            producto_info = mapa_productos[codigo_producto]
            respuestas_cantidades.append({
                "pedido_detalle_id": pedido_detalle_id,
                "codigo_producto": codigo_producto,
                "cantidad_solicitada_total": producto_info["cantidad_solicitada_total"],
                "cantidad_confirmada_total": producto_resp.get("cantidad_confirmada_total", 0),
                "observaciones": producto_resp.get("observaciones"),
            })
            costo_ajustado = producto_resp.get("costo_unitario_ajustado")
            if costo_ajustado is not None:
                respuestas_precios.append({
                    "pedido_detalle_id": pedido_detalle_id,
                    "codigo_producto": codigo_producto,
                    "costo_doc_sin_iva_original": producto_info["costo_original"],
                    "costo_doc_sin_iva_ajustado": costo_ajustado,
                    "descuento_1_original": producto_info["descuento_original"],
                    "descuento_1_ajustado": producto_resp.get("descuento_ajustado"),
                    "observaciones_precio": None,
                })
        return respuestas_cantidades, respuestas_precios

    def procesar_respuesta_proveedor_web(
        self,
        pedido_id: str,
        productos: List[Dict[str, Any]],
        observaciones_generales: Optional[str] = None,
        estado: str = "borrador",
        usuario_id: Optional[str] = None,
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
            repo = PedidoRepository(conn)
            pedido = repo.get_pedido_completo(pedido_id)

            if not pedido:
                raise ValueError(f"Pedido no encontrado: {pedido_id}")

            estado_pedido = pedido["cabecera"].get("estado", "PENDIENTE_CONFIRMACION_PROVEEDOR")
            estados_bloqueados = [
                "CONFIRMADO_PROVEEDOR",
                "ORDEN_COMPRA_CREADA",
                "ENVIADA_SAP",
                "CERRADO",
                "CANCELADO",
            ]
            if estado_pedido in estados_bloqueados:
                raise ValueError(f"El pedido está en estado '{estado_pedido}' y no puede ser modificado")

            mapa_productos = {
                detalle["codigo_interno"]: {
                    "pedido_detalle_id": detalle["pedido_detalle_id"],
                    "cantidad_solicitada_total": sum(t["cantidad"] for t in detalle["tiendas"]),
                    "costo_original": detalle.get("costo_doc_sin_iva"),
                    "descuento_original": detalle.get("descuento_1"),
                }
                for detalle in pedido["detalles"]
            }

            respuestas_cantidades, respuestas_precios = self._convertir_productos_a_respuestas(
                productos, mapa_productos
            )

            validacion = self.proveedor_service.validar_respuesta_proveedor(
                pedido=pedido,
                respuestas_cantidades=respuestas_cantidades,
                respuestas_precios=respuestas_precios,
            )

            if estado == "confirmado" and not validacion["valido"]:
                return {
                    "status": "validation_error",
                    "message": "La respuesta contiene errores de validación y no puede ser confirmada",
                    "validacion": validacion,
                    "errores": validacion["errores"],
                    "warnings": validacion["warnings"],
                    "pedido_id": pedido_id,
                }

            respuesta_repo = PedidoRespuestaRepository(conn)
            respuesta_id = None
            if estado == "borrador":
                respuesta_existente = respuesta_repo.obtener_respuesta_activa(pedido_id)
                if respuesta_existente and respuesta_existente.get("estado") == "BORRADOR":
                    respuesta_id = respuesta_existente.get("respuesta_id")

            if not respuesta_id:
                respuesta_id = respuesta_repo.crear_respuesta_proveedor(
                    pedido_id=pedido_id,
                    usuario_id=usuario_id,
                    observaciones_generales=observaciones_generales,
                )

            estado_respuesta = "BORRADOR" if estado == "borrador" else "PENDIENTE_REVISION"

            if respuesta_id:
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        UPDATE pedido_respuesta_proveedor
                        SET estado = ?,
                            observaciones_generales = ?,
                            updated_at = ?
                        WHERE respuesta_id = ?
                    """, (estado_respuesta, observaciones_generales, ahora_naive(), respuesta_id))
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error al actualizar estado de respuesta: {e}")
                    raise
                finally:
                    cursor.close()

            resultado_guardado = respuesta_repo.guardar_respuesta_detalles(
                respuesta_id=respuesta_id,
                respuestas_cantidades=respuestas_cantidades,
                respuestas_precios=respuestas_precios,
            )

            if estado == "confirmado":
                audit = AuditContext(usuario=usuario_id, origen=ORIGEN_WEB)
                repo.update_estado(pedido_id, ESTADO_REDISTRIBUCION, audit_context=audit)

            return {
                "status": "success",
                "message": f"Respuesta del proveedor guardada como {estado}",
                "respuesta_id": respuesta_id,
                "validacion": validacion,
                "cantidades_guardadas": resultado_guardado["cantidades_guardadas"],
                "precios_guardados": resultado_guardado["precios_guardados"],
                "pedido_id": pedido_id,
                "estado_guardado": estado_respuesta,
            }

    # ── helpers: crear_respuesta_desde_pedido ─────────────────────────────

    @staticmethod
    def _validar_fecha_entrega(pedido: Dict, pedido_id: str) -> None:
        fecha_entrega = pedido.get("cabecera", {}).get("fecha_entrega", "")
        if fecha_entrega and str(fecha_entrega).strip().upper() == "INMEDIATO":
            logger.warning(
                f"Pedido {pedido_id} tiene fecha de entrega INMEDIATO, no se puede confirmar sin fecha real"
            )
            raise ValueError(
                "No se puede confirmar un pedido con fecha de entrega INMEDIATO. "
                "Por favor, seleccione una fecha de entrega antes de confirmar."
            )

    @staticmethod
    def _leer_total_desde_bd(
        conn: Any,
        pedido_detalle_id: str,
        detalle: Dict,
    ) -> Tuple[Optional[float], bool]:
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
                return (float(row[0]) if row[0] is not None else None), bool(row[1])
            logger.warning(
                f"No se pudo leer total desde BD para {pedido_detalle_id}, usando valor del detalle"
            )
            return detalle.get("total"), detalle.get("total_modificado_manual", False)
        except Exception as e:
            logger.warning(
                f"Error al leer total desde BD para {pedido_detalle_id}: {e}, usando valor del detalle"
            )
            return detalle.get("total"), detalle.get("total_modificado_manual", False)
        finally:
            cursor.close()

    @staticmethod
    def _calcular_cantidad_solicitada(
        tiendas: List,
        total_value: Optional[float],
        pedido_detalle_id: str,
    ) -> float:
        if tiendas:
            return sum(
                float(t.get("cantidad", 0)) if t.get("cantidad") is not None else 0
                for t in tiendas
            )
        if total_value is not None:
            try:
                cantidad: float = float(total_value)
            except (ValueError, TypeError):
                cantidad = 0.0
        else:
            cantidad = 0.0
        logger.debug(
            f"Detalle {pedido_detalle_id} sin tiendas, usando total del detalle como cantidad solicitada: {cantidad}"
        )
        return cantidad

    @staticmethod
    def _validar_total_modificado_manual(
        codigo_producto: str,
        pedido_detalle_id: str,
        cantidad_confirmada_total: float,
        cantidad_solicitada_total: float,
    ) -> None:
        if cantidad_confirmada_total < 0:
            error_msg = (
                f"El producto {codigo_producto} (ID: {pedido_detalle_id}) "
                f"fue modificado manualmente por EL RAYO pero el total es negativo ({cantidad_confirmada_total}). "
                f"El total debe ser mayor o igual a 0. Por favor, verifique el valor antes de confirmar."
            )
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
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

    @staticmethod
    def _log_cantidad_sin_modificar(
        codigo_producto: str,
        pedido_detalle_id: str,
        cantidad_confirmada_total: float,
        cantidad_solicitada_total: float,
    ) -> None:
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

    def _calcular_cantidad_confirmada(
        self,
        codigo_producto: str,
        pedido_detalle_id: str,
        total_value: Optional[float],
        total_modificado_manual: bool,
        cantidad_solicitada_total: float,
    ) -> float:
        if total_value is None:
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
            return cantidad_solicitada_total
        try:
            cantidad_confirmada_total = float(total_value)
            if total_modificado_manual:
                self._validar_total_modificado_manual(
                    codigo_producto, pedido_detalle_id,
                    cantidad_confirmada_total, cantidad_solicitada_total,
                )
            else:
                self._log_cantidad_sin_modificar(
                    codigo_producto, pedido_detalle_id,
                    cantidad_confirmada_total, cantidad_solicitada_total,
                )
            return cantidad_confirmada_total
        except (ValueError, TypeError) as e:
            logger.warning(
                f"⚠️ Error al convertir total a entero para {codigo_producto} (ID: {pedido_detalle_id}): {e}. "
                f"Usando cantidad solicitada como fallback: {cantidad_solicitada_total}"
            )
            return cantidad_solicitada_total

    def _convertir_detalles_a_respuestas(
        self,
        conn: Any,
        detalles: List[Dict],
    ) -> Tuple[List, List]:
        respuestas_cantidades: List[Dict] = []
        respuestas_precios: List[Dict] = []
        for detalle in detalles:
            pedido_detalle_id = detalle.get("pedido_detalle_id")
            codigo_producto = detalle.get("codigo_interno")
            if not pedido_detalle_id:
                logger.warning("Detalle sin pedido_detalle_id, omitiendo")
                continue
            if not codigo_producto:
                logger.warning(f"Detalle {pedido_detalle_id} sin codigo_interno, usando 'SIN_CODIGO'")
                codigo_producto = "SIN_CODIGO"
            total_value, total_modificado_manual = self._leer_total_desde_bd(conn, pedido_detalle_id, detalle)
            cantidad_solicitada_total = self._calcular_cantidad_solicitada(
                detalle.get("tiendas", []), total_value, pedido_detalle_id
            )
            cantidad_confirmada_total = self._calcular_cantidad_confirmada(
                codigo_producto, pedido_detalle_id,
                total_value, total_modificado_manual, cantidad_solicitada_total,
            )
            costo_original = detalle.get("costo_doc_sin_iva")
            costo_ajustado = costo_original
            descuento_original = detalle.get("descuento_1")
            descuento_ajustado = descuento_original
            respuestas_cantidades.append({
                "pedido_detalle_id": pedido_detalle_id,
                "codigo_producto": codigo_producto,
                "cantidad_solicitada_total": cantidad_solicitada_total,
                "cantidad_confirmada_total": cantidad_confirmada_total,
                "observaciones": None,
            })
            if costo_original is not None:
                respuestas_precios.append({
                    "pedido_detalle_id": pedido_detalle_id,
                    "codigo_producto": codigo_producto,
                    "costo_doc_sin_iva_original": costo_original,
                    "costo_doc_sin_iva_ajustado": costo_ajustado,
                    "descuento_1_original": descuento_original,
                    "descuento_1_ajustado": descuento_ajustado,
                    "observaciones_precio": None,
                })
        return respuestas_cantidades, respuestas_precios

    def _persistir_respuesta(
        self,
        conn: Any,
        respuesta_repo: PedidoRespuestaRepository,
        pedido_id: str,
        respuesta_id: Optional[str],
        ya_existia_respuesta: bool,
        usuario_id: Optional[str],
        observaciones_generales: Optional[str],
        respuestas_cantidades: List,
        respuestas_precios: List,
    ) -> Tuple[str, Dict]:
        if not respuesta_id:
            respuesta_id = respuesta_repo.crear_respuesta_proveedor(
                pedido_id=pedido_id,
                usuario_id=usuario_id,
                observaciones_generales=observaciones_generales,
            )
        else:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    UPDATE pedido_respuesta_proveedor
                    SET observaciones_generales = ?,
                        updated_at = ?
                    WHERE respuesta_id = ?
                """, (observaciones_generales, ahora_naive(), respuesta_id))
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Error al actualizar observaciones de respuesta: {e}")
                raise
            finally:
                cursor.close()

        if not ya_existia_respuesta:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    UPDATE pedido_respuesta_proveedor
                    SET estado = 'PENDIENTE_REVISION',
                        observaciones_generales = ?,
                        updated_at = ?
                    WHERE respuesta_id = ?
                """, (observaciones_generales, ahora_naive(), respuesta_id))
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Error al actualizar estado de respuesta: {e}")
                raise
            finally:
                cursor.close()

        if not ya_existia_respuesta:
            resultado_guardado = respuesta_repo.guardar_respuesta_detalles(
                respuesta_id=respuesta_id,
                respuestas_cantidades=respuestas_cantidades,
                respuestas_precios=respuestas_precios,
            )
        else:
            respuesta_repo.eliminar_detalles_por_respuesta_id(respuesta_id)
            resultado_guardado = respuesta_repo.guardar_respuesta_detalles(
                respuesta_id=respuesta_id,
                respuestas_cantidades=respuestas_cantidades,
                respuestas_precios=respuestas_precios,
            )
            logger.info(
                f"Respuesta ya existía; detalles reemplazados con valores actuales del pedido "
                f"({resultado_guardado.get('cantidades_guardadas', 0)} cantidades, incl. decimales)"
            )

        return respuesta_id, resultado_guardado

    @staticmethod
    def _detectar_cambio_numerico(anterior: Optional[float], actual: Optional[float]) -> bool:
        if anterior is None and actual is None:
            return False
        if anterior is None or actual is None:
            return True
        return abs(float(anterior) - float(actual)) > 0.01

    @staticmethod
    def _cargar_detalles_bd(conn: Any, pedido_id: str) -> Dict:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                pedido_detalle_id,
                codigo_interno,
                costo_doc_sin_iva,
                total,
                comentario,
                ISNULL(costo_modificado_manual, 0)     AS costo_modificado_manual,
                ISNULL(total_modificado_manual, 0)     AS total_modificado_manual,
                ISNULL(comentario_modificado_manual, 0) AS comentario_modificado_manual
            FROM pedido_detalle
            WHERE pedido_id = ?
        """, (pedido_id,))
        detalles_bd: Dict = {}
        for row in cursor.fetchall():
            detalles_bd[row[0]] = {
                "pedido_detalle_id": str(row[0]),
                "codigo_interno": row[1],
                "costo_doc_sin_iva": float(row[2]) if row[2] is not None else None,
                "total": float(row[3]) if row[3] is not None else None,
                "comentario": row[4],
                "costo_modificado_manual": bool(row[5]),
                "total_modificado_manual": bool(row[6]),
                "comentario_modificado_manual": bool(row[7]),
            }
        cursor.close()
        return detalles_bd

    @staticmethod
    def _cargar_valores_anteriores(
        confirmacion_repo: Any,
        pedido_id: str,
    ) -> Tuple[List, Dict]:
        confirmaciones_previas = confirmacion_repo.obtener_confirmaciones_por_pedido(pedido_id, limit=1)
        valores_anteriores: Dict = {}
        if confirmaciones_previas:
            ultima = confirmacion_repo.obtener_confirmacion(confirmaciones_previas[0]["confirmacion_id"])
            if ultima and ultima.get("detalles"):
                for dc in ultima["detalles"]:
                    pdid = dc["pedido_detalle_id"]
                    valores_anteriores[pdid] = {
                        "costo": dc.get("costo_nuevo"),
                        "total": dc.get("total_nuevo"),
                        "comentario": dc.get("comentario_nuevo"),
                    }
        return confirmaciones_previas, valores_anteriores

    def _detectar_cambios(
        self,
        detalles_bd: Dict,
        valores_anteriores: Dict,
    ) -> Tuple[Dict, bool]:
        detalles_con_cambios: Dict = {}
        hay_cambios = False
        for pedido_detalle_id, detalle_bd in detalles_bd.items():
            if not (
                detalle_bd["costo_modificado_manual"]
                or detalle_bd["total_modificado_manual"]
                or detalle_bd["comentario_modificado_manual"]
            ):
                continue
            valores_ant = valores_anteriores.get(pedido_detalle_id, {})
            cambio_costo = self._detectar_cambio_numerico(
                valores_ant.get("costo"), detalle_bd["costo_doc_sin_iva"]
            )
            cambio_total = self._detectar_cambio_numerico(
                valores_ant.get("total"), detalle_bd["total"]
            )
            cambio_comentario = (detalle_bd["comentario"] or "") != (valores_ant.get("comentario") or "")
            if cambio_costo or cambio_total or cambio_comentario:
                hay_cambios = True
                detalles_con_cambios[pedido_detalle_id] = {
                    "detalle_bd": detalle_bd,
                    "valores_anteriores": valores_ant,
                    "cambio_costo": cambio_costo,
                    "cambio_total": cambio_total,
                    "cambio_comentario": cambio_comentario,
                }
        return detalles_con_cambios, hay_cambios

    @staticmethod
    def _aplicar_valores_anteriores(
        valores_ant: Dict,
        detalle_bd: Dict,
    ) -> Tuple[Any, Any, Any]:
        costo = valores_ant.get("costo")
        if costo is None:
            costo = detalle_bd["costo_doc_sin_iva"]
        total = valores_ant.get("total")
        if total is None:
            total = detalle_bd["total"]
        comentario = valores_ant.get("comentario")
        if comentario is None:
            comentario = detalle_bd["comentario"]
        return costo, total, comentario

    @staticmethod
    def _actualizar_resumen_cambios(
        resumen_cambios: Dict,
        info_cambio: Dict,
        pedido_detalle_id: Any,
        codigo_interno: str,
    ) -> None:
        if info_cambio["cambio_costo"]:
            resumen_cambios["cambios_costo"] += 1
        if info_cambio["cambio_total"]:
            resumen_cambios["cambios_total"] += 1
        if info_cambio["cambio_comentario"]:
            resumen_cambios["cambios_comentario"] += 1
        resumen_cambios["detalles"].append({
            "pedido_detalle_id": pedido_detalle_id,
            "codigo_producto": codigo_interno,
            "cambio_costo": info_cambio["cambio_costo"],
            "cambio_total": info_cambio["cambio_total"],
            "cambio_comentario": info_cambio["cambio_comentario"],
        })

    @staticmethod
    def _registrar_detalles_confirmacion(
        confirmacion_repo: Any,
        confirmacion_id: str,
        detalles_con_cambios: Dict,
    ) -> Tuple[int, Dict]:
        resumen_cambios: Dict = {
            "cambios_costo": 0, "cambios_total": 0, "cambios_comentario": 0, "detalles": []
        }
        detalles_modificados_count = 0
        for pedido_detalle_id, info_cambio in detalles_con_cambios.items():
            detalle_bd = info_cambio["detalle_bd"]
            costo_anterior, total_anterior, comentario_anterior = (
                PedidoProveedorWebService._aplicar_valores_anteriores(
                    info_cambio["valores_anteriores"], detalle_bd
                )
            )
            detalles_modificados_count += 1
            confirmacion_repo.agregar_detalle_confirmacion(
                confirmacion_id=confirmacion_id,
                pedido_detalle_id=pedido_detalle_id,
                costo_anterior=costo_anterior,
                costo_nuevo=detalle_bd["costo_doc_sin_iva"],
                total_anterior=total_anterior,
                total_nuevo=detalle_bd["total"],
                comentario_anterior=comentario_anterior,
                comentario_nuevo=detalle_bd["comentario"],
                codigo_producto=detalle_bd["codigo_interno"],
            )
            PedidoProveedorWebService._actualizar_resumen_cambios(
                resumen_cambios, info_cambio, pedido_detalle_id, detalle_bd["codigo_interno"]
            )
        return detalles_modificados_count, resumen_cambios

    def _registrar_confirmacion_rayo(
        self,
        conn: Any,
        confirmacion_repo: Any,
        pedido_id: str,
        respuesta_id: str,
        usuario_id: Optional[str],
        observaciones_generales: Optional[str],
    ) -> Tuple[bool, List]:
        hay_cambios = False
        confirmaciones_previas: List = []
        try:
            detalles_bd = self._cargar_detalles_bd(conn, pedido_id)
            confirmaciones_previas, valores_anteriores = self._cargar_valores_anteriores(
                confirmacion_repo, pedido_id
            )
            detalles_con_cambios, hay_cambios = self._detectar_cambios(detalles_bd, valores_anteriores)

            if hay_cambios or not confirmaciones_previas:
                confirmacion_id = confirmacion_repo.crear_confirmacion(
                    pedido_id=pedido_id,
                    respuesta_id=respuesta_id,
                    usuario_id=usuario_id or "SISTEMA",
                    observaciones_generales=observaciones_generales,
                )
                detalles_modificados_count, resumen_cambios = self._registrar_detalles_confirmacion(
                    confirmacion_repo, confirmacion_id, detalles_con_cambios
                )
                confirmacion_repo.actualizar_resumen_confirmacion(
                    confirmacion_id=confirmacion_id,
                    total_detalles_modificados=detalles_modificados_count,
                    resumen_cambios=resumen_cambios,
                )
                logger.info(
                    f"✅ Confirmación de EL RAYO registrada: {confirmacion_id} "
                    f"({detalles_modificados_count} detalles modificados)"
                )
            else:
                logger.info("ℹ️ No se registró nueva confirmación: no hay cambios desde la última confirmación")
        except Exception as e:
            logger.error(f"⚠️ Error al registrar confirmación de EL RAYO (no crítico): {e}", exc_info=True)
            hay_cambios = False
        return hay_cambios, confirmaciones_previas

    def _generar_respuesta_automatica(
        self,
        conn: Any,
        pedido_id: str,
        usuario_id: Optional[str] = None,
        observaciones_generales: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], str, Dict[str, int], Dict[str, Any], bool]:
        """
        Genera (o regenera) la respuesta_proveedor de un pedido a partir de sus propios
        detalles (total y costo_doc_sin_iva), sin transicionar su estado_id ni registrar
        confirmación de EL RAYO -- eso lo decide el llamador (ver crear_respuesta_desde_pedido
        y generar_respuesta_proveedor_automatica).

        Returns:
            (pedido, respuesta_id, resultado_guardado, validacion, ya_existia_respuesta)
        """
        repo = PedidoRepository(conn)
        pedido = repo.get_pedido_completo(pedido_id)

        if not pedido:
            logger.error(f"Pedido {pedido_id} no encontrado")
            raise ValueError(f"Pedido no encontrado: {pedido_id}")

        logger.debug(f"Pedido {pedido_id} encontrado con {len(pedido.get('detalles', []))} detalles")
        self._validar_fecha_entrega(pedido, pedido_id)

        respuesta_repo = PedidoRespuestaRepository(conn)
        respuesta_existente = respuesta_repo.obtener_respuesta_activa(pedido_id)

        respuesta_id = None
        ya_existia_respuesta = False
        if respuesta_existente:
            respuesta_id = respuesta_existente["cabecera"]["respuesta_id"]
            ya_existia_respuesta = True
            logger.info(
                f"Ya existe respuesta {respuesta_id} para pedido {pedido_id}, "
                f"se usará para la confirmación"
            )

        detalles = pedido.get("detalles", [])
        if not detalles:
            logger.error(f"Pedido {pedido_id} no tiene detalles")
            raise ValueError(f"El pedido {pedido_id} no tiene detalles")

        logger.debug(f"Procesando {len(detalles)} detalles del pedido {pedido_id}")
        respuestas_cantidades, respuestas_precios = self._convertir_detalles_a_respuestas(
            conn, detalles
        )

        if not respuestas_cantidades:
            logger.error(
                f"No se pudo crear ninguna respuesta para pedido {pedido_id}: "
                f"el pedido no tiene detalles válidos"
            )
            raise ValueError("No se pudo crear ninguna respuesta: el pedido no tiene detalles válidos")

        logger.debug(
            f"Se crearon {len(respuestas_cantidades)} respuestas de cantidades "
            f"y {len(respuestas_precios)} respuestas de precios"
        )

        try:
            validacion = self.proveedor_service.validar_respuesta_proveedor(
                pedido=pedido,
                respuestas_cantidades=respuestas_cantidades,
                respuestas_precios=respuestas_precios,
            )
        except Exception as e:
            logger.error(f"Error en validación de respuesta: {e}", exc_info=True)
            raise ValueError(f"Error al validar respuesta: {str(e)}")

        respuesta_id, resultado_guardado = self._persistir_respuesta(
            conn, respuesta_repo, pedido_id, respuesta_id, ya_existia_respuesta,
            usuario_id, observaciones_generales, respuestas_cantidades, respuestas_precios,
        )

        return pedido, respuesta_id, resultado_guardado, validacion, ya_existia_respuesta

    def generar_respuesta_proveedor_automatica(
        self,
        pedido_id: str,
        usuario_id: Optional[str] = None,
    ) -> str:
        """
        Genera la respuesta_proveedor de un pedido sin transicionar su estado_id ni
        registrar confirmación de EL RAYO.

        Usada por el botón "Aceptar" sobre un pedido hijo en PRODUCCION_POSPUESTA (22):
        ese pedido pasa a LISTO_PARA_REDISTRIBUCION (25) directo, sin pasar por
        "Confirmado por El Rayo" (4) -- el único otro punto que genera respuesta_proveedor
        hasta ahora (ver crear_respuesta_desde_pedido). Sin ella, la vista de Redistribución
        se queda mostrando "Preparando datos para redistribución" indefinidamente (gate en
        RedistribucionTiendas.vue).

        Returns:
            respuesta_id generado
        """
        with get_db_connection_context() as conn:
            _, respuesta_id, _, _, _ = self._generar_respuesta_automatica(conn, pedido_id, usuario_id)
            return respuesta_id

    def crear_respuesta_desde_pedido(
        self,
        pedido_id: str,
        usuario_id: Optional[str] = None,
        observaciones_generales: Optional[str] = None,
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
            repo = PedidoRepository(conn)
            pedido, respuesta_id, resultado_guardado, validacion, ya_existia_respuesta = (
                self._generar_respuesta_automatica(
                    conn, pedido_id, usuario_id, observaciones_generales
                )
            )

            estado_id_actual = pedido["cabecera"].get("estado_id")
            try:
                estado_id_actual = int(estado_id_actual) if estado_id_actual is not None else None
            except (TypeError, ValueError):
                estado_id_actual = None
            if estado_id_actual != ESTADO_REDISTRIBUCION:
                audit = AuditContext(usuario=usuario_id, origen=ORIGEN_WEB)
                repo.update_estado(pedido_id, ESTADO_REDISTRIBUCION, audit_context=audit)

            confirmacion_repo = PedidoConfirmacionRayoRepository(conn)
            hay_cambios, confirmaciones_previas = self._registrar_confirmacion_rayo(
                conn, confirmacion_repo, pedido_id, respuesta_id, usuario_id, observaciones_generales
            )

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
                "estado_guardado": "CONFIRMADO",
                "ya_existia": ya_existia_respuesta,
                "confirmacion_registrada": hay_cambios or not confirmaciones_previas,
            }
