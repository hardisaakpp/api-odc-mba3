"""
Repositorio especializado para operaciones de despacho_detalle.

CHANGELOG:
- 2026-01-08: Extraído de despacho_repository.py
"""

import logging
import pyodbc
from typing import List, Dict, Any

from ..common.serialization import serialize_decimal

logger = logging.getLogger(__name__)


class DespachoDetalleRepository:
    """Repositorio para operaciones de despacho_detalle."""

    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.

        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn

    def insert_many(self, despacho_id: str, detalles: List[Dict[str, Any]]) -> int:
        """
        Inserta múltiples líneas de detalle en despacho_detalle.

        Args:
            despacho_id: UUID de la cabecera de despacho
            detalles: Lista de diccionarios con datos de detalle

        Returns:
            Número de líneas insertadas
        """
        if not detalles:
            return 0

        cursor = self.conn.cursor()
        inserted_count = 0

        try:
            sql = """
            INSERT INTO despacho_detalle (
                detalle_id, despacho_id, sku, cantidad_docena_mba3,
                subtotal_sap, cantidad_pack_sap, unidad_sap,
                precio_unitario_mba3, descuento, total_linea_mba3,
                impuesto, nombre_producto, tipo_linea, precio_unitario_sap
            ) VALUES (NEWID(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            for detalle in detalles:
                try:
                    values = (
                        despacho_id,
                        detalle.get("sku"),
                        detalle.get("cantidad"),
                        detalle.get("total_producto"),
                        detalle.get("cantidad_sap"),
                        detalle.get("unidad_sap"),
                        detalle.get("precio_unitario"),
                        detalle.get("descuento"),
                        detalle.get("total_linea"),
                        detalle.get("impuesto"),
                        detalle.get("nombre_producto"),
                        detalle.get("tipo_linea"),
                        detalle.get("precio_unitario_sap"),
                    )

                    cursor.execute(sql, values)
                    inserted_count += 1
                    logger.debug(f"   → Línea insertada: {detalle.get('sku')} ({detalle.get('tipo_linea')})")
                except Exception as e:
                    logger.warning(f"   ⚠️ Error al insertar línea de detalle: {e}")
                    logger.warning(f"      Tipo: {detalle.get('tipo_linea')}, SKU: {detalle.get('sku')}")
                    continue

            self.conn.commit()
            logger.debug(f"✅ {inserted_count} líneas de detalle insertadas")
            return inserted_count

        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar despacho_detalle: {e}")
            raise
        finally:
            cursor.close()

    def get_by_despacho_id(self, despacho_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene todos los detalles de un despacho.

        Args:
            despacho_id: UUID del despacho

        Returns:
            Lista de diccionarios con los datos de detalle
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT detalle_id, despacho_id, sku, cantidad_docena_mba3,
                       subtotal_sap, cantidad_pack_sap, unidad_sap,
                       precio_unitario_mba3, descuento, total_linea_mba3,
                       impuesto, nombre_producto, tipo_linea, precio_unitario_sap
                FROM despacho_detalle
                WHERE despacho_id = ?
                ORDER BY detalle_id
                """,
                (despacho_id,)
            )
            results = cursor.fetchall()

            detalles: List[Dict[str, Any]] = []
            for row in results:
                detalles.append({
                    "detalle_id": str(row[0]),
                    "despacho_id": str(row[1]),
                    "sku": row[2],
                    "cantidad_docena_mba3": serialize_decimal(row[3]),
                    "subtotal_sap": serialize_decimal(row[4]),
                    "cantidad_pack_sap": serialize_decimal(row[5]),
                    "unidad_sap": row[6],
                    "precio_unitario_mba3": serialize_decimal(row[7]),
                    "descuento": serialize_decimal(row[8]),
                    "total_linea_mba3": serialize_decimal(row[9]),
                    "impuesto": serialize_decimal(row[10]),
                    "nombre_producto": row[11],
                    "tipo_linea": row[12],
                    "precio_unitario_sap": serialize_decimal(row[13]),
                })

            return detalles
        finally:
            cursor.close()

    def delete_by_despacho_id(self, despacho_id: str) -> int:
        """
        Elimina todos los detalles de un despacho.

        Args:
            despacho_id: UUID del despacho

        Returns:
            Número de detalles eliminados
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM despacho_detalle WHERE despacho_id = ?",
                (despacho_id,)
            )
            rows_deleted = cursor.rowcount
            self.conn.commit()
            if rows_deleted > 0:
                logger.debug(f"✅ {rows_deleted} detalles eliminados para despacho: {despacho_id}")
            return rows_deleted
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al eliminar detalles: {e}")
            raise
        finally:
            cursor.close()

