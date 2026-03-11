"""
Repositorio para persistir el snapshot de cada envío ODC a SAP (información que se envía por correo).
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class EnvioODCSAPRepository:
    """Repositorio para la tabla envio_odc_sap (auditoría de lo enviado por correo)."""

    def __init__(self, conn):
        self.conn = conn

    def insert(
        self,
        oc_id: str,
        pedido_id: str,
        numero_oc_sap: Optional[str] = None,
        doc_entry: Optional[int] = None,
        proveedor: Optional[str] = None,
        referencia: Optional[str] = None,
        numero_pedido: Optional[str] = None,
        solicitud_transferencia_id: Optional[str] = None,
        total_transferencias: int = 0,
        transferencias_creadas: int = 0,
    ) -> Optional[str]:
        """
        Inserta un registro con el snapshot del envío (OC + solicitudes de transferencia) notificado por correo.

        Args:
            oc_id: UUID de la orden de compra
            pedido_id: UUID del pedido
            numero_oc_sap: DocNum de SAP (ej: 22523)
            doc_entry: DocEntry de SAP (ej: 43366)
            proveedor: CardCode del proveedor
            referencia: Referencia/Pedido (ej: PREG-02.03.2026)
            numero_pedido: Número legible del pedido
            solicitud_transferencia_id: UUID del batch en solicitud_transferencia (opcional)
            total_transferencias: Total de tiendas/solicitudes
            transferencias_creadas: Cantidad creadas exitosamente en SAP

        Returns:
            envio_odc_sap_id si se insertó correctamente, None si falló
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO envio_odc_sap (
                    oc_id, pedido_id, numero_oc_sap, doc_entry, proveedor, referencia,
                    numero_pedido, solicitud_transferencia_id, total_transferencias, transferencias_creadas
                )
                OUTPUT INSERTED.envio_odc_sap_id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(oc_id),
                    str(pedido_id),
                    numero_oc_sap,
                    doc_entry,
                    (proveedor or "")[:50] if proveedor else None,
                    (referencia or "")[:100] if referencia else None,
                    (numero_pedido or "")[:100] if numero_pedido else None,
                    str(solicitud_transferencia_id) if solicitud_transferencia_id else None,
                    total_transferencias,
                    transferencias_creadas,
                ),
            )
            row = cursor.fetchone()
            self.conn.commit()
            envio_id = str(row[0]) if row and row[0] else None
            cursor.close()
            return envio_id
        except Exception as e:
            logger.warning(f"No se pudo insertar envio_odc_sap (tabla puede no existir): {e}")
            try:
                self.conn.rollback()
            except Exception:
                pass
            return None

    def get_by_oc_id(self, oc_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el registro de envio_odc_sap para una OC (el más reciente si hay varios).

        Args:
            oc_id: UUID de la orden de compra.

        Returns:
            Dict con oc_id, pedido_id, numero_oc_sap, doc_entry, proveedor, solicitud_transferencia_id,
            total_transferencias, transferencias_creadas, etc. None si no existe.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT TOP 1 envio_odc_sap_id, oc_id, pedido_id, numero_oc_sap, doc_entry,
                       proveedor, referencia, numero_pedido, solicitud_transferencia_id,
                       total_transferencias, transferencias_creadas
                FROM envio_odc_sap
                WHERE oc_id = ?
                ORDER BY envio_odc_sap_id DESC
                """,
                (str(oc_id),),
            )
            row = cursor.fetchone()
            cursor.close()
            if not row:
                return None
            return {
                "envio_odc_sap_id": str(row[0]) if row[0] else None,
                "oc_id": str(row[1]) if row[1] else None,
                "pedido_id": str(row[2]) if row[2] else None,
                "numero_oc_sap": str(row[3]) if row[3] is not None else None,
                "doc_entry": row[4],
                "proveedor": row[5],
                "referencia": row[6],
                "numero_pedido": row[7],
                "solicitud_transferencia_id": str(row[8]) if row[8] else None,
                "total_transferencias": row[9] or 0,
                "transferencias_creadas": row[10] or 0,
            }
        except Exception as e:
            logger.warning(f"No se pudo obtener envio_odc_sap por oc_id: {e}")
            return None
