"""
Repositorio para operaciones sobre pedido_original y pedido_detalle_original.

Estas tablas almacenan una copia inmutable de los datos del pedido tal como
fueron enviados originalmente (botón "Enviar" en cargar-plantilla).
Se usan para generar el Excel "Descargar Pedido Original".

CHANGELOG:
- 2026-02-12: Creado
"""

import logging
import pyodbc
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class PedidoOriginalRepository:
    """Repositorio para tablas pedido_original y pedido_detalle_original."""

    def __init__(self, conn: pyodbc.Connection):
        self.conn = conn

    # ========================================================================
    # ESCRITURA: copiar snapshot del pedido original
    # ========================================================================

    def copiar_pedido_original(
        self,
        pedido_id: str,
        cabecera: Dict[str, Any],
        detalles: List[Dict[str, Any]],
        copiado_por: Optional[str] = None,
    ) -> str:
        """
        Copia la cabecera y los detalles del pedido a las tablas _original.

        Si ya existe un snapshot para este pedido_id, no hace nada y devuelve
        el pedido_original_id existente (idempotente).

        Args:
            pedido_id: UUID del pedido vivo.
            cabecera: dict con los campos de la cabecera.
            detalles: lista de dicts con los campos de cada detalle.
            copiado_por: usuario que dispara la acción (JWT username).

        Returns:
            pedido_original_id (str UUID).
        """
        cursor = self.conn.cursor()
        try:
            # Verificar si ya existe un snapshot (idempotencia)
            cursor.execute(
                "SELECT pedido_original_id FROM pedido_original WHERE pedido_id = ?",
                (pedido_id,),
            )
            row = cursor.fetchone()
            if row:
                logger.info(f"ℹ️ Snapshot original ya existe para pedido {pedido_id}")
                return str(row[0])

            # --- Insertar cabecera original ---
            cursor.execute(
                """
                INSERT INTO pedido_original (
                    pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                    forma_pago, mensaje, proveedor_nombre, comprador_nombre,
                    comprador_codigo, origen_traslado, serie, archivo_nombre,
                    copiado_por
                )
                OUTPUT INSERTED.pedido_original_id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pedido_id,
                    cabecera.get("numero_pedido"),
                    cabecera.get("fecha_pedido"),
                    cabecera.get("fecha_entrega"),
                    cabecera.get("forma_pago"),
                    cabecera.get("mensaje"),
                    cabecera.get("proveedor_nombre"),
                    cabecera.get("comprador_nombre"),
                    cabecera.get("comprador_codigo"),
                    cabecera.get("origen_traslado"),
                    cabecera.get("serie"),
                    cabecera.get("archivo_nombre"),
                    copiado_por,
                ),
            )
            pedido_original_id = str(cursor.fetchone()[0])

            # --- Insertar detalles originales ---
            for detalle in detalles:
                cursor.execute(
                    """
                    INSERT INTO pedido_detalle_original (
                        pedido_original_id, pedido_detalle_id,
                        codigo_interno, descripcion_sap, marca, codigo_barras,
                        pack, costo_doc_sin_iva, descuento_1, pvp,
                        subtotal, total, comentario
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pedido_original_id,
                        detalle.get("pedido_detalle_id"),
                        detalle.get("codigo_interno"),
                        detalle.get("descripcion_sap"),
                        detalle.get("marca"),
                        detalle.get("codigo_barras"),
                        detalle.get("pack"),
                        detalle.get("costo_doc_sin_iva"),
                        detalle.get("descuento_1"),
                        detalle.get("pvp"),
                        detalle.get("subtotal"),
                        detalle.get("total"),
                        detalle.get("comentario"),
                    ),
                )

            self.conn.commit()
            logger.info(
                f"✅ Snapshot original creado para pedido {pedido_id}: "
                f"{len(detalles)} detalles copiados"
            )
            return pedido_original_id

        except Exception as e:
            self.conn.rollback()
            logger.error(
                f"❌ Error al copiar pedido original {pedido_id}: {e}",
                exc_info=True,
            )
            raise
        finally:
            cursor.close()

    # ========================================================================
    # LECTURA: obtener snapshot original
    # ========================================================================

    def get_pedido_original(self, pedido_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el snapshot original de un pedido (cabecera + detalles).

        Args:
            pedido_id: UUID del pedido vivo.

        Returns:
            Dict con "cabecera" y "detalles", o None si no existe snapshot.
        """
        cursor = self.conn.cursor()
        try:
            # Obtener cabecera original
            cursor.execute(
                """
                SELECT
                    pedido_original_id, pedido_id, numero_pedido,
                    fecha_pedido, fecha_entrega, forma_pago, mensaje,
                    proveedor_nombre, comprador_nombre, comprador_codigo,
                    origen_traslado, serie, archivo_nombre,
                    copiado_por, copiado_en
                FROM pedido_original
                WHERE pedido_id = ?
                """,
                (pedido_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            cabecera = {
                "pedido_original_id": str(row[0]),
                "pedido_id": str(row[1]),
                "numero_pedido": row[2],
                "fecha_pedido": str(row[3]) if row[3] else None,
                "fecha_entrega": row[4],
                "forma_pago": row[5],
                "mensaje": row[6],
                "proveedor_nombre": row[7],
                "comprador_nombre": row[8],
                "comprador_codigo": row[9],
                "origen_traslado": row[10],
                "serie": row[11],
                "archivo_nombre": row[12],
                "copiado_por": row[13],
                "copiado_en": str(row[14]) if row[14] else None,
            }

            pedido_original_id = cabecera["pedido_original_id"]

            # Obtener detalles originales
            cursor.execute(
                """
                SELECT
                    pedido_detalle_original_id, pedido_detalle_id,
                    codigo_interno, descripcion_sap, marca, codigo_barras,
                    pack, costo_doc_sin_iva, descuento_1, pvp,
                    subtotal, total, comentario
                FROM pedido_detalle_original
                WHERE pedido_original_id = ?
                ORDER BY codigo_interno
                """,
                (pedido_original_id,),
            )

            detalles = []
            for det_row in cursor.fetchall():
                detalles.append({
                    "pedido_detalle_original_id": str(det_row[0]),
                    "pedido_detalle_id": str(det_row[1]),
                    "codigo_interno": det_row[2],
                    "descripcion_sap": det_row[3],
                    "marca": det_row[4],
                    "codigo_barras": det_row[5],
                    "pack": det_row[6],
                    "costo_doc_sin_iva": det_row[7],
                    "descuento_1": det_row[8],
                    "pvp": det_row[9],
                    "subtotal": det_row[10],
                    "total": det_row[11],
                    "comentario": det_row[12],
                })

            return {"cabecera": cabecera, "detalles": detalles}

        finally:
            cursor.close()

    def existe_snapshot(self, pedido_id: str) -> bool:
        """Verifica si ya existe un snapshot original para un pedido."""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT 1 FROM pedido_original WHERE pedido_id = ?",
                (pedido_id,),
            )
            return cursor.fetchone() is not None
        finally:
            cursor.close()
