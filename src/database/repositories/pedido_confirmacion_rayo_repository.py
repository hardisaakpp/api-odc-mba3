"""
Repositorio para operaciones de confirmaciones de EL RAYO.
Almacena historial completo de cada confirmación realizada.
"""

import logging
import json
import pyodbc
from typing import Dict, Any, List, Optional

from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)


class PedidoConfirmacionRayoRepository:
    """Repositorio para operaciones de confirmaciones de EL RAYO."""
    
    def __init__(self, conn: pyodbc.Connection):
        self.conn = conn
    
    def crear_confirmacion(
        self,
        pedido_id: str,
        respuesta_id: str,
        usuario_id: str,
        observaciones_generales: Optional[str] = None
    ) -> str:
        """
        Crea un registro de confirmación de EL RAYO.
        
        Args:
            pedido_id: UUID del pedido
            respuesta_id: UUID de la respuesta del proveedor creada
            usuario_id: User ID de EL RAYO
            observaciones_generales: Observaciones generales (opcional)
            
        Returns:
            confirmacion_id (UUID) generado
        """
        cursor = self.conn.cursor()
        
        try:
            # Generar ID de confirmación
            cursor.execute("SELECT NEWID()")
            row = cursor.fetchone()
            if not row:
                raise ValueError("No se pudo generar el UUID para la confirmación")
            confirmacion_id = str(row[0])
            
            # Crear registro de confirmación
            cursor.execute("""
                INSERT INTO pedido_confirmacion_rayo (
                    confirmacion_id, pedido_id, respuesta_id,
                    confirmado_por, fecha_confirmacion,
                    total_detalles_modificados, observaciones_generales
                ) VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (confirmacion_id, pedido_id, respuesta_id, usuario_id, ahora_naive(), observaciones_generales))
            
            self.conn.commit()
            logger.debug(f"✅ Confirmación de EL RAYO creada: {confirmacion_id}")
            return confirmacion_id
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al crear confirmación de EL RAYO: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def agregar_detalle_confirmacion(
        self,
        confirmacion_id: str,
        pedido_detalle_id: str,
        costo_anterior: Optional[float],
        costo_nuevo: Optional[float],
        total_anterior: Optional[float],
        total_nuevo: Optional[float],
        comentario_anterior: Optional[str],
        comentario_nuevo: Optional[str],
        codigo_producto: Optional[str] = None
    ) -> str:
        """
        Agrega un detalle de cambio a la confirmación.
        
        Args:
            confirmacion_id: UUID de la confirmación
            pedido_detalle_id: UUID del detalle del pedido
            costo_anterior: Valor anterior del costo (opcional)
            costo_nuevo: Nuevo valor del costo (opcional)
            total_anterior: Valor anterior del total (opcional)
            total_nuevo: Nuevo valor del total (opcional)
            comentario_anterior: Valor anterior del comentario (opcional)
            comentario_nuevo: Nuevo valor del comentario (opcional)
            codigo_producto: Código del producto (opcional, para facilitar consultas)
            
        Returns:
            confirmacion_detalle_id (UUID) generado
        """
        cursor = self.conn.cursor()
        
        try:
            # Determinar qué campos cambiaron
            cambio_costo = (
                costo_anterior is not None and costo_nuevo is not None and 
                float(costo_anterior) != float(costo_nuevo)
            ) or (costo_anterior is None and costo_nuevo is not None) or \
                 (costo_anterior is not None and costo_nuevo is None)
            
            cambio_total = (
                total_anterior is not None and total_nuevo is not None and 
                float(total_anterior) != float(total_nuevo)
            ) or (total_anterior is None and total_nuevo is not None) or \
                 (total_anterior is not None and total_nuevo is None)
            
            cambio_comentario = (
                (comentario_anterior or '') != (comentario_nuevo or '')
            )
            
            # Generar ID de detalle
            cursor.execute("SELECT NEWID()")
            row = cursor.fetchone()
            if not row:
                raise ValueError("No se pudo generar el UUID para el detalle de confirmación")
            confirmacion_detalle_id = str(row[0])
            
            # Insertar detalle
            cursor.execute("""
                INSERT INTO pedido_confirmacion_rayo_detalle (
                    confirmacion_detalle_id, confirmacion_id, pedido_detalle_id,
                    costo_anterior, costo_nuevo,
                    total_anterior, total_nuevo,
                    comentario_anterior, comentario_nuevo,
                    cambio_costo, cambio_total, cambio_comentario,
                    codigo_producto
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                confirmacion_detalle_id, confirmacion_id, pedido_detalle_id,
                costo_anterior, costo_nuevo,
                total_anterior, total_nuevo,
                comentario_anterior, comentario_nuevo,
                1 if cambio_costo else 0,
                1 if cambio_total else 0,
                1 if cambio_comentario else 0,
                codigo_producto
            ))
            
            self.conn.commit()
            logger.debug(f"✅ Detalle de confirmación agregado: {confirmacion_detalle_id}")
            return confirmacion_detalle_id
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al agregar detalle de confirmación: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def actualizar_resumen_confirmacion(
        self,
        confirmacion_id: str,
        total_detalles_modificados: int,
        resumen_cambios: Optional[Dict[str, Any]] = None
    ):
        """
        Actualiza el resumen de la confirmación con el total de detalles modificados.
        
        Args:
            confirmacion_id: UUID de la confirmación
            total_detalles_modificados: Número total de detalles modificados
            resumen_cambios: Diccionario con resumen de cambios (se serializa a JSON)
        """
        cursor = self.conn.cursor()
        
        try:
            detalles_json = None
            if resumen_cambios:
                detalles_json = json.dumps(resumen_cambios, ensure_ascii=False)
            
            cursor.execute("""
                UPDATE pedido_confirmacion_rayo
                SET total_detalles_modificados = ?,
                    detalles_modificados = ?
                WHERE confirmacion_id = ?
            """, (total_detalles_modificados, detalles_json, confirmacion_id))
            
            self.conn.commit()
            logger.debug(f"✅ Resumen de confirmación actualizado: {confirmacion_id}")
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar resumen de confirmación: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def _map_detalle_confirmacion(self, detalle_row: Any) -> Dict[str, Any]:
        """Mapea una fila de pedido_confirmacion_rayo_detalle a dict."""
        return {
            "confirmacion_detalle_id": str(detalle_row[0]),
            "pedido_detalle_id": str(detalle_row[1]),
            "costo_anterior": float(detalle_row[2]) if detalle_row[2] is not None else None,
            "costo_nuevo": float(detalle_row[3]) if detalle_row[3] is not None else None,
            "total_anterior": float(detalle_row[4]) if detalle_row[4] is not None else None,
            "total_nuevo": float(detalle_row[5]) if detalle_row[5] is not None else None,
            "comentario_anterior": detalle_row[6],
            "comentario_nuevo": detalle_row[7],
            "cambio_costo": bool(detalle_row[8]),
            "cambio_total": bool(detalle_row[9]),
            "cambio_comentario": bool(detalle_row[10]),
            "codigo_producto": detalle_row[11],
        }

    def obtener_confirmacion(
        self,
        confirmacion_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene una confirmación completa con sus detalles.

        Args:
            confirmacion_id: UUID de la confirmación

        Returns:
            Dict con confirmación y detalles, o None si no existe
        """
        cursor = self.conn.cursor()

        try:
            # Obtener cabecera
            cursor.execute("""
                SELECT
                    confirmacion_id, pedido_id, respuesta_id,
                    confirmado_por, fecha_confirmacion,
                    total_detalles_modificados, detalles_modificados,
                    observaciones_generales
                FROM pedido_confirmacion_rayo
                WHERE confirmacion_id = ?
            """, (confirmacion_id,))

            row = cursor.fetchone()
            if not row:
                return None

            # Construir cabecera
            detalles_modificados_json = None
            if row[6]:
                try:
                    detalles_modificados_json = json.loads(row[6])
                except json.JSONDecodeError:
                    logger.warning(f"Error al parsear JSON de detalles_modificados: {row[6]}")

            confirmacion = {
                "confirmacion_id": str(row[0]),
                "pedido_id": str(row[1]),
                "respuesta_id": str(row[2]) if row[2] else None,
                "confirmado_por": row[3],
                "fecha_confirmacion": row[4].isoformat() if row[4] else None,
                "total_detalles_modificados": row[5],
                "detalles_modificados": detalles_modificados_json,
                "observaciones_generales": row[7]
            }

            # Obtener detalles
            cursor.execute("""
                SELECT
                    confirmacion_detalle_id, pedido_detalle_id,
                    costo_anterior, costo_nuevo,
                    total_anterior, total_nuevo,
                    comentario_anterior, comentario_nuevo,
                    cambio_costo, cambio_total, cambio_comentario,
                    codigo_producto
                FROM pedido_confirmacion_rayo_detalle
                WHERE confirmacion_id = ?
                ORDER BY codigo_producto
            """, (confirmacion_id,))

            confirmacion["detalles"] = [
                self._map_detalle_confirmacion(r) for r in cursor.fetchall()
            ]
            return confirmacion

        except Exception as e:
            logger.error(f"❌ Error al obtener confirmación: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def obtener_confirmaciones_por_pedido(
        self,
        pedido_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Obtiene todas las confirmaciones de un pedido, ordenadas por fecha descendente.
        
        Args:
            pedido_id: UUID del pedido
            limit: Número máximo de confirmaciones a retornar (opcional)
            
        Returns:
            Lista de dicts con confirmaciones (sin detalles, solo cabeceras)
        """
        cursor = self.conn.cursor()
        
        try:
            query = """
                SELECT 
                    confirmacion_id, pedido_id, respuesta_id,
                    confirmado_por, fecha_confirmacion,
                    total_detalles_modificados, detalles_modificados,
                    observaciones_generales
                FROM pedido_confirmacion_rayo
                WHERE pedido_id = ?
                ORDER BY fecha_confirmacion DESC
            """
            
            if limit:
                query += f" OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"
            
            cursor.execute(query, (pedido_id,))
            
            confirmaciones = []
            for row in cursor.fetchall():
                detalles_modificados_json = None
                if row[6]:
                    try:
                        detalles_modificados_json = json.loads(row[6])
                    except json.JSONDecodeError:
                        logger.warning(f"Error al parsear JSON de detalles_modificados: {row[6]}")
                
                confirmaciones.append({
                    "confirmacion_id": str(row[0]),
                    "pedido_id": str(row[1]),
                    "respuesta_id": str(row[2]) if row[2] else None,
                    "confirmado_por": row[3],
                    "fecha_confirmacion": row[4].isoformat() if row[4] else None,
                    "total_detalles_modificados": row[5],
                    "detalles_modificados": detalles_modificados_json,
                    "observaciones_generales": row[7]
                })
            
            return confirmaciones
            
        except Exception as e:
            logger.error(f"❌ Error al obtener confirmaciones por pedido: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
