"""
Repositorio para persistir el resultado de Solicitudes de Transferencia (ITR) en SAP.
"""

import json
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class SolicitudTransferenciaRepository:
    """Repositorio para operaciones de solicitud_transferencia."""

    def __init__(self, conn):
        """
        Inicializa el repositorio con una conexión a SQL Server.

        Args:
            conn: Conexión a SQL Server (pyodbc.Connection)
        """
        self.conn = conn

    def insert(
        self,
        pedido_id: str,
        resultado: Dict[str, Any],
        payloads_sap: Optional[List[Dict[str, Any]]] = None,
        oc_id: Optional[str] = None,
        oc_doc_num: Optional[int] = None,
        bodega_origen: Optional[str] = None,
    ) -> Optional[str]:
        """
        Inserta un registro con el resultado de la generación de Solicitudes de Transferencia.

        Args:
            pedido_id: UUID del pedido
            resultado: Diccionario con el resultado (success, total_tiendas, transferencias_creadas,
                       transferencias_errores, resultados, etc.)
            payloads_sap: Lista de payloads JSON enviados a SAP (opcional)
            oc_id: UUID de la orden de compra relacionada (opcional)
            oc_doc_num: DocNum de SAP de la OC (opcional)
            bodega_origen: Código de bodega origen (opcional)

        Returns:
            solicitud_transferencia_id si se insertó correctamente, None si falló (no crítico)
        """
        try:
            cursor = self.conn.cursor()

            total_tiendas = resultado.get("total_tiendas", 0)
            transferencias_creadas = resultado.get("transferencias_creadas", 0)
            transferencias_errores = resultado.get("transferencias_errores", 0)
            success = bool(resultado.get("success", False))

            resultado_json = None
            if resultado:
                try:
                    resultado_json = json.dumps(resultado, ensure_ascii=False, default=str)
                except Exception as e:
                    logger.warning(f"No se pudo serializar resultado a JSON: {e}")

            payloads_sap_json = None
            if payloads_sap:
                try:
                    payloads_sap_json = json.dumps(payloads_sap, ensure_ascii=False, default=str)
                except Exception as e:
                    logger.warning(f"No se pudo serializar payloads_sap a JSON: {e}")

            query = """
                INSERT INTO solicitud_transferencia (
                    pedido_id, oc_id, oc_doc_num, bodega_origen,
                    total_tiendas, transferencias_creadas, transferencias_errores,
                    success, resultado_json, payloads_sap_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            cursor.execute(
                query,
                (
                    str(pedido_id),
                    str(oc_id) if oc_id else None,
                    oc_doc_num,
                    bodega_origen,
                    total_tiendas,
                    transferencias_creadas,
                    transferencias_errores,
                    1 if success else 0,
                    resultado_json,
                    payloads_sap_json,
                ),
            )
            self.conn.commit()
            cursor.close()
            return "ok"

        except Exception as e:
            logger.error(f"Error al insertar solicitud_transferencia: {e}", exc_info=True)
            try:
                self.conn.rollback()
            except Exception:
                pass
            return None
