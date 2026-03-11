"""
Repositorio para persistir el snapshot de cada envío ODC a SAP (información que se envía por correo).
"""

import logging
from typing import Optional

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
