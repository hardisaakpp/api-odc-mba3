"""
Repositorio para persistir el resultado de Inventory Transfer Requests entre
bodegas (OCSAPService._enviar_itrs_por_bodega) en SAP.

Tablas propias (solicitud_transferencia_bodega / _detalle), separadas de
solicitud_transferencia / solicitud_transferencia_detalle: el reintento
automático de tiendas asume que el último registro de solicitud_transferencia
para una oc_id es siempre un envío a tiendas (ver
SolicitudTransferenciaRepository.get_tiendas_pendientes_reintento_st). Compartir
tabla arriesgaría que una ITR de bodega se convierta en "la última" y rompa esa
lectura -- ver scripts/migrations/create_solicitud_transferencia_bodega.sql.
"""

import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SolicitudTransferenciaBodegaRepository:
    """Repositorio para operaciones de solicitud_transferencia_bodega."""

    def __init__(self, conn):
        """
        Inicializa el repositorio con una conexión a SQL Server.

        Args:
            conn: Conexión a SQL Server (pyodbc.Connection)
        """
        self.conn = conn

    def insert(
        self,
        oc_id: Optional[str],
        pedido_id: Optional[str],
        oc_doc_num: Any = None,
        bodega_origen: Optional[str] = None,
    ) -> Optional[str]:
        """
        Crea el encabezado ANTES de enviar las ITR a SAP (contadores en 0/False),
        para que quede un registro aunque el proceso se interrumpa a mitad del
        envío -- mismo criterio que SolicitudTransferenciaRepository.insert.

        Returns:
            solicitud_transferencia_bodega_id (UUID string) si se insertó, None si falló.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO solicitud_transferencia_bodega (
                    pedido_id, oc_id, oc_doc_num, bodega_origen
                )
                OUTPUT INSERTED.solicitud_transferencia_bodega_id
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(pedido_id) if pedido_id else None,
                    str(oc_id) if oc_id else None,
                    oc_doc_num,
                    bodega_origen,
                ),
            )
            row = cursor.fetchone()
            self.conn.commit()
            cursor.close()
            return str(row[0]) if row else None
        except Exception as e:
            logger.warning(f"⚠️ No se pudo crear encabezado solicitud_transferencia_bodega: {e}")
            try:
                self.conn.rollback()
            except Exception:
                pass
            return None

    def insert_detalle_individual(
        self, solicitud_transferencia_bodega_id: str, r: Dict[str, Any]
    ) -> bool:
        """
        Inserta el detalle de UNA bodega destino de inmediato (su propio cursor +
        commit), igual que SolicitudTransferenciaRepository.insert_detalle_individual
        para tiendas: si el proceso se interrumpe a mitad del envío, las bodegas ya
        resueltas hasta ese punto quedan registradas igual.

        r: {"bodega_codigo": str, "success": bool, "doc_num": ..., "doc_entry": ...,
            "error": str opcional}
        """
        bodega_codigo = (r.get("bodega_codigo") or "N\\A")[:20]
        success = bool(r.get("success", False))
        estado = "Creada" if success else "Error"
        error_mensaje = (r.get("error") or "")[:500] if r.get("error") else None
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO solicitud_transferencia_bodega_detalle (
                    solicitud_transferencia_bodega_id, bodega_codigo, estado,
                    doc_num, doc_entry, error_mensaje
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(solicitud_transferencia_bodega_id),
                    bodega_codigo,
                    estado,
                    r.get("doc_num"),
                    r.get("doc_entry"),
                    error_mensaje,
                ),
            )
            self.conn.commit()
            cursor.close()
            return True
        except Exception as e:
            logger.warning(
                f"⚠️ No se pudo persistir de inmediato el detalle de bodega {bodega_codigo}: {e}"
            )
            try:
                self.conn.rollback()
            except Exception:
                pass
            return False

    def update_resumen(self, solicitud_transferencia_bodega_id: str, resultado: Dict[str, Any]) -> bool:
        """
        Actualiza los contadores finales del encabezado una vez que el lote
        completo de ITR de bodega terminó. El detalle por bodega ya se persistió
        aparte, vía insert_detalle_individual.
        """
        try:
            resultado_json = None
            try:
                resultado_json = json.dumps(resultado, ensure_ascii=False, default=str)
            except Exception as e:
                logger.warning(f"No se pudo serializar resultado a JSON: {e}")

            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE solicitud_transferencia_bodega
                SET total_bodegas = ?, transferencias_creadas = ?, transferencias_errores = ?,
                    success = ?, resultado_json = ?
                WHERE solicitud_transferencia_bodega_id = ?
                """,
                (
                    resultado.get("total", 0),
                    resultado.get("created", 0),
                    resultado.get("errors", 0),
                    1 if resultado.get("errors", 0) == 0 and resultado.get("created", 0) > 0 else 0,
                    resultado_json,
                    str(solicitud_transferencia_bodega_id),
                ),
            )
            actualizado = cursor.rowcount > 0
            self.conn.commit()
            cursor.close()
            return actualizado
        except Exception as e:
            logger.warning(f"No se pudo actualizar el resumen de solicitud_transferencia_bodega: {e}")
            try:
                self.conn.rollback()
            except Exception:
                pass
            return False
