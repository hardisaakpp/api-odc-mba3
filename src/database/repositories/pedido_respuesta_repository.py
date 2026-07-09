"""
Repositorio para operaciones de respuesta del proveedor (FASE 3).
Modelo: Respuesta por producto consolidado + detalle por tienda opcional.
"""

import logging
import pyodbc
from typing import Dict, Any, List, Optional

from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)


class PedidoRespuestaRepository:
    """Repositorio para operaciones de respuesta del proveedor."""
    
    def __init__(self, conn: pyodbc.Connection):
        self.conn = conn
    
    def crear_respuesta_proveedor(
        self,
        pedido_id: str,
        usuario_id: Optional[str] = None,
        observaciones_generales: Optional[str] = None
    ) -> str:
        """
        Crea una nueva respuesta del proveedor (cabecera).
        Determina automáticamente la versión.
        
        Args:
            pedido_id: UUID del pedido
            usuario_id: User ID del usuario que carga la respuesta
            observaciones_generales: Observaciones generales de la respuesta
            
        Returns:
            respuesta_id (UUID) generado
        """
        cursor = self.conn.cursor()
        
        try:
            # Obtener última versión
            cursor.execute("""
                SELECT MAX(version)
                FROM pedido_respuesta_proveedor
                WHERE pedido_id = ?
            """, (pedido_id,))
            
            row = cursor.fetchone()
            nueva_version = (row[0] if row and row[0] else 0) + 1
            
            # Crear respuesta
            cursor.execute("SELECT NEWID()")
            row = cursor.fetchone()
            if not row:
                raise ValueError("No se pudo generar el UUID para la respuesta")
            respuesta_id = str(row[0])
            
            _ahora = ahora_naive()
            cursor.execute("""
                INSERT INTO pedido_respuesta_proveedor (
                    respuesta_id, pedido_id, version, estado,
                    fecha_respuesta, creado_por, observaciones_generales,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'PENDIENTE_REVISION', ?, ?, ?, ?, ?)
            """, (respuesta_id, pedido_id, nueva_version, _ahora, usuario_id, observaciones_generales, _ahora, _ahora))
            
            self.conn.commit()
            logger.debug(f"✅ Respuesta del proveedor creada: {respuesta_id} (versión {nueva_version})")
            return respuesta_id
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al crear respuesta del proveedor: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def _construir_mapa_precios(
        self, respuestas_precios: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Indexa respuestas_precios por pedido_detalle_id para búsqueda O(1)."""
        precios_map: Dict[str, Dict[str, Any]] = {}
        for precio_resp in respuestas_precios:
            pedido_detalle_id = precio_resp.get("pedido_detalle_id")
            if pedido_detalle_id:
                precios_map[pedido_detalle_id] = precio_resp
        return precios_map

    def guardar_respuesta_detalles(
        self,
        respuesta_id: str,
        respuestas_cantidades: List[Dict[str, Any]],
        respuestas_precios: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Guarda los detalles de respuesta (cantidades y precios) por producto.

        Args:
            respuesta_id: UUID de la respuesta (cabecera)
            respuestas_cantidades: Lista de dicts con pedido_detalle_id, cantidad_solicitada_total, cantidad_confirmada_total, observaciones
            respuestas_precios: Lista de dicts con pedido_detalle_id, costo_ajustado, descuento_ajustado, observaciones_precio

        Returns:
            Dict con conteos: {"cantidades_guardadas": N, "precios_guardados": M}
        """
        cursor = self.conn.cursor()
        cantidades_guardadas = 0
        precios_guardados = 0

        try:
            precios_map = self._construir_mapa_precios(respuestas_precios)

            # Guardar cada respuesta de cantidad (que incluye precio si existe)
            for cant_resp in respuestas_cantidades:
                pedido_detalle_id = cant_resp.get("pedido_detalle_id")
                cantidad_solicitada_total = cant_resp.get("cantidad_solicitada_total")
                cantidad_confirmada_total = cant_resp.get("cantidad_confirmada_total")
                observaciones = cant_resp.get("observaciones")
                
                if not pedido_detalle_id or cantidad_solicitada_total is None or cantidad_confirmada_total is None:
                    continue

                # Persistir cantidades como float (decimales); la columna debe ser DECIMAL(18,4) ver alter_pedido_respuesta_detalle_cantidad_decimal.sql
                cantidad_solicitada_total = float(cantidad_solicitada_total)
                cantidad_confirmada_total = float(cantidad_confirmada_total)

                # Obtener precios originales desde pedido_detalle
                cursor.execute("""
                    SELECT costo_doc_sin_iva, descuento_1
                    FROM pedido_detalle
                    WHERE pedido_detalle_id = ?
                """, (pedido_detalle_id,))
                row = cursor.fetchone()
                
                if not row:
                    continue
                
                costo_original = float(row[0]) if row[0] else None
                descuento_original = float(row[1]) if row[1] else None
                
                # Obtener precios ajustados si existen
                precio_resp = precios_map.get(pedido_detalle_id, {})
                costo_ajustado = precio_resp.get("costo_doc_sin_iva_ajustado")
                descuento_ajustado = precio_resp.get("descuento_1_ajustado")
                observaciones_precio = precio_resp.get("observaciones_precio")
                
                # Insertar detalle de respuesta
                _ahora = ahora_naive()
                cursor.execute("""
                    INSERT INTO pedido_respuesta_proveedor_detalle (
                        id, respuesta_id, pedido_detalle_id,
                        cantidad_solicitada_total, cantidad_confirmada_total,
                        costo_doc_sin_iva_original, costo_doc_sin_iva_ajustado,
                        descuento_1_original, descuento_1_ajustado,
                        observaciones, created_at, updated_at
                    ) VALUES (NEWID(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    respuesta_id, pedido_detalle_id,
                    cantidad_solicitada_total, cantidad_confirmada_total,
                    costo_original, costo_ajustado,
                    descuento_original, descuento_ajustado,
                    observaciones or observaciones_precio,
                    _ahora,
                    _ahora,
                ))
                
                cantidades_guardadas += 1
                if costo_ajustado is not None:
                    precios_guardados += 1
            
            self.conn.commit()
            logger.debug(f"✅ {cantidades_guardadas} respuestas de productos guardadas ({precios_guardados} con precios ajustados)")
            
            return {
                "cantidades_guardadas": cantidades_guardadas,
                "precios_guardados": precios_guardados
            }
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al guardar detalles de respuesta: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def eliminar_detalles_por_respuesta_id(self, respuesta_id: str) -> int:
        """
        Elimina todos los detalles de una respuesta (para reemplazarlos con valores actuales).
        Usado cuando ya existía respuesta y el usuario confirma de nuevo: se actualizan
        cantidad_confirmada_total etc. con los totales actuales del pedido (incl. decimales).

        Returns:
            Número de filas eliminadas.
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM pedido_respuesta_proveedor_detalle WHERE respuesta_id = ?",
                (respuesta_id,),
            )
            count = cursor.rowcount
            self.conn.commit()
            if count > 0:
                logger.debug(f"✅ {count} detalles de respuesta eliminados para respuesta_id={respuesta_id}")
            return count
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al eliminar detalles de respuesta: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def _map_cabecera_respuesta(self, row: Any, respuesta_id: str) -> Dict[str, Any]:
        """Mapea una fila de pedido_respuesta_proveedor a dict de cabecera."""
        return {
            "respuesta_id": respuesta_id,
            "version": row[1],
            "estado": row[2],
            "fecha_respuesta": row[3].isoformat() if row[3] else None,
            "fecha_aprobacion": row[4].isoformat() if row[4] else None,
            "creado_por": row[5],
            "aprobado_por": row[6],
            "observaciones_generales": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "updated_at": row[9].isoformat() if row[9] else None,
        }

    def _map_detalle_respuesta(self, det_row: Any, tiene_campos_modificados: bool) -> Dict[str, Any]:
        """Mapea una fila de pedido_respuesta_proveedor_detalle a dict."""
        # Normalizar cantidades a float para preservar decimales (ej. 0.5)
        try:
            cant_sol = float(det_row[2]) if det_row[2] is not None else 0.0
        except (TypeError, ValueError):
            cant_sol = 0.0
        try:
            cant_conf = float(det_row[3]) if det_row[3] is not None else 0.0
        except (TypeError, ValueError):
            cant_conf = 0.0
        detalle_dict = {
            "id": str(det_row[0]),
            "pedido_detalle_id": str(det_row[1]),
            "codigo_producto": det_row[9],
            "descripcion": det_row[10],
            "cantidad_solicitada_total": cant_sol,
            "cantidad_confirmada_total": cant_conf,
            "costo_doc_sin_iva_original": float(det_row[4]) if det_row[4] else None,
            "costo_doc_sin_iva_ajustado": float(det_row[5]) if det_row[5] else None,
            "descuento_1_original": float(det_row[6]) if det_row[6] else None,
            "descuento_1_ajustado": float(det_row[7]) if det_row[7] else None,
            "observaciones": det_row[8],
        }
        if tiene_campos_modificados and len(det_row) > 11:
            detalle_dict["costo_modificado_manual"] = bool(det_row[11])
            detalle_dict["total_modificado_manual"] = bool(det_row[12])
        else:
            # Campos no presentes en BD antigua: devolver False por defecto
            detalle_dict["costo_modificado_manual"] = False
            detalle_dict["total_modificado_manual"] = False
        return detalle_dict

    def obtener_respuesta_activa(self, pedido_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene la respuesta más reciente (última versión) del proveedor para un pedido.

        Args:
            pedido_id: UUID del pedido

        Returns:
            Dict con respuesta completa incluyendo cabecera y detalles, o None si no existe
        """
        cursor = self.conn.cursor()

        try:
            # Obtener cabecera de respuesta más reciente
            cursor.execute("""
                SELECT TOP 1
                    respuesta_id, version, estado, fecha_respuesta,
                    fecha_aprobacion, creado_por, aprobado_por, observaciones_generales,
                    created_at, updated_at
                FROM pedido_respuesta_proveedor
                WHERE pedido_id = ?
                ORDER BY version DESC
            """, (pedido_id,))

            row = cursor.fetchone()
            if not row:
                return None

            respuesta_id = str(row[0])
            cabecera = self._map_cabecera_respuesta(row, respuesta_id)

            # Obtener detalles de respuesta con campos de modificación manual
            # Nota: Los campos costo_modificado_manual y total_modificado_manual pueden no existir en BD antigua
            try:
                cursor.execute("""
                    SELECT
                        r.id,
                        r.pedido_detalle_id,
                        r.cantidad_solicitada_total,
                        r.cantidad_confirmada_total,
                        r.costo_doc_sin_iva_original,
                        r.costo_doc_sin_iva_ajustado,
                        r.descuento_1_original,
                        r.descuento_1_ajustado,
                        r.observaciones,
                        pd.codigo_interno,
                        pd.descripcion_sap,
                        ISNULL(pd.costo_modificado_manual, 0) AS costo_modificado_manual,
                        ISNULL(pd.total_modificado_manual, 0) AS total_modificado_manual
                    FROM pedido_respuesta_proveedor_detalle r
                    INNER JOIN pedido_detalle pd ON r.pedido_detalle_id = pd.pedido_detalle_id
                    WHERE r.respuesta_id = ?
                """, (respuesta_id,))
                tiene_campos_modificados = True
            except Exception:
                # Si los campos no existen, usar consulta sin ellos
                cursor.execute("""
                    SELECT
                        r.id,
                        r.pedido_detalle_id,
                        r.cantidad_solicitada_total,
                        r.cantidad_confirmada_total,
                        r.costo_doc_sin_iva_original,
                        r.costo_doc_sin_iva_ajustado,
                        r.descuento_1_original,
                        r.descuento_1_ajustado,
                        r.observaciones,
                        pd.codigo_interno,
                        pd.descripcion_sap
                    FROM pedido_respuesta_proveedor_detalle r
                    INNER JOIN pedido_detalle pd ON r.pedido_detalle_id = pd.pedido_detalle_id
                    WHERE r.respuesta_id = ?
                """, (respuesta_id,))
                tiene_campos_modificados = False

            detalles = [
                self._map_detalle_respuesta(det_row, tiene_campos_modificados)
                for det_row in cursor.fetchall()
            ]

            return {
                "cabecera": cabecera,
                "detalles": detalles,
            }

        except Exception as e:
            logger.error(f"❌ Error al obtener respuesta activa: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

