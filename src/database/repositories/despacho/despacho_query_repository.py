"""
Repositorio especializado para consultas complejas de despachos.

CHANGELOG:
- 2026-01-08: Extraído de despacho_repository.py
"""

import logging
import pyodbc
from typing import Optional, List, Dict, Any

from ..common.serialization import serialize_date, serialize_decimal

logger = logging.getLogger(__name__)


class DespachoQueryRepository:
    """Repositorio para consultas complejas de despachos."""

    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.

        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn

    def get_despachos_sin_oc(self) -> List[str]:
        """
        Obtiene todos los despacho_id que no tienen una orden de compra asociada.

        Returns:
            Lista de despacho_id (UUIDs) que no tienen OC
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT dc.despacho_id
                FROM despacho_cabecera dc
                LEFT JOIN orden_compra_cabecera oc ON dc.despacho_id = oc.despacho_id
                WHERE oc.despacho_id IS NULL
                ORDER BY dc.created_at DESC
                """
            )
            results = cursor.fetchall()
            return [str(row[0]) for row in results]
        finally:
            cursor.close()

    def count_despachos_sin_oc(self) -> int:
        """
        Cuenta los despachos que no tienen una orden de compra asociada.

        Returns:
            Número de despachos disponibles para procesar
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT COUNT(dc.despacho_id)
                FROM despacho_cabecera dc
                LEFT JOIN orden_compra_cabecera oc ON dc.despacho_id = oc.despacho_id
                WHERE oc.despacho_id IS NULL
                """
            )
            result = cursor.fetchone()
            return result[0] if result else 0
        finally:
            cursor.close()

    def get_despachos_con_info_oc(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Obtiene información detallada de despachos junto con sus órdenes de compra asociadas.

        Args:
            limit: Número máximo de registros a retornar (opcional)

        Returns:
            Lista de diccionarios con información combinada de despachos, OCs y sus detalles
        """
        cursor = self.conn.cursor()
        try:
            sql = self._build_query_sql(limit)
            cursor.execute(sql)
            results = cursor.fetchall()

            return self._agrupar_resultados(results)
        finally:
            cursor.close()

    def _build_query_sql(self, limit: Optional[int]) -> str:
        """Construye la query SQL según si hay límite o no."""
        base_query = """
            SELECT 
                -- Campos de despacho_cabecera
                dc.despacho_id, dc.empresa, dc.codigo_cliente, dc.fecha_despacho,
                dc.codigo_factura, dc.anulada, dc.numero_pedido_sistema, dc.numero_orden,
                dc.numero_factura, dc.tipo_documento, dc.orden_compra, dc.orden_compra_cliente,
                dc.remision_facturada, dc.num_id_factura_relacionada, dc.fecha_factura,
                dc.codigo_despacho, dc.codigo_bodega, dc.confirmado,
                dc.created_at AS despacho_created_at, dc.updated_at AS despacho_updated_at,
                -- Campos de orden_compra_cabecera
                oc.oc_id, oc.proveedor, oc.fecha_generacion, oc.referencia_despacho,
                oc.estado AS oc_estado, oc.numero_oc_sap, oc.created_at AS oc_created_at,
                -- Campos de despacho_detalle
                dd.detalle_id, dd.sku, dd.cantidad_docena_mba3, dd.subtotal_sap,
                dd.cantidad_pack_sap, dd.unidad_sap, dd.precio_unitario_mba3,
                dd.descuento, dd.total_linea_mba3, dd.impuesto, dd.nombre_producto,
                dd.tipo_linea, dd.precio_unitario_sap
            FROM despacho_cabecera dc
            OUTER APPLY (
                SELECT TOP 1 
                    oc_inner.oc_id, oc_inner.proveedor, oc_inner.fecha_generacion,
                    oc_inner.referencia_despacho, oc_inner.estado, oc_inner.numero_oc_sap,
                    oc_inner.created_at
                FROM orden_compra_cabecera oc_inner
                WHERE (
                    oc_inner.despacho_id = dc.despacho_id 
                    OR oc_inner.referencia_despacho = dc.codigo_factura
                )
                ORDER BY 
                    CASE WHEN oc_inner.despacho_id = dc.despacho_id THEN 1 ELSE 2 END,
                    oc_inner.created_at DESC
            ) oc
            LEFT JOIN despacho_detalle dd ON dd.despacho_id = dc.despacho_id
            ORDER BY dc.created_at DESC, dd.detalle_id
        """

        if limit and isinstance(limit, int) and limit > 0:
            # Query con límite usando CTE
            return f"""
                WITH DespachosLimitados AS (
                    SELECT TOP {limit}
                        dc.despacho_id, dc.empresa, dc.codigo_cliente, dc.fecha_despacho,
                        dc.codigo_factura, dc.anulada, dc.numero_pedido_sistema, dc.numero_orden,
                        dc.numero_factura, dc.tipo_documento, dc.orden_compra, dc.orden_compra_cliente,
                        dc.remision_facturada, dc.num_id_factura_relacionada, dc.fecha_factura,
                        dc.codigo_despacho, dc.codigo_bodega, dc.confirmado,
                        dc.created_at AS despacho_created_at, dc.updated_at AS despacho_updated_at,
                        oc.oc_id, oc.proveedor, oc.fecha_generacion, oc.referencia_despacho,
                        oc.estado AS oc_estado, oc.numero_oc_sap, oc.created_at AS oc_created_at
                    FROM despacho_cabecera dc
                    OUTER APPLY (
                        SELECT TOP 1 
                            oc_inner.oc_id, oc_inner.proveedor, oc_inner.fecha_generacion,
                            oc_inner.referencia_despacho, oc_inner.estado, oc_inner.numero_oc_sap,
                            oc_inner.created_at
                        FROM orden_compra_cabecera oc_inner
                        WHERE (
                            oc_inner.despacho_id = dc.despacho_id 
                            OR oc_inner.referencia_despacho = dc.codigo_factura
                        )
                        ORDER BY 
                            CASE WHEN oc_inner.despacho_id = dc.despacho_id THEN 1 ELSE 2 END,
                            oc_inner.created_at DESC
                    ) oc
                    ORDER BY dc.created_at DESC
                )
                SELECT 
                    dl.*,
                    dd.detalle_id, dd.sku, dd.cantidad_docena_mba3, dd.subtotal_sap,
                    dd.cantidad_pack_sap, dd.unidad_sap, dd.precio_unitario_mba3,
                    dd.descuento, dd.total_linea_mba3, dd.impuesto, dd.nombre_producto,
                    dd.tipo_linea, dd.precio_unitario_sap
                FROM DespachosLimitados dl
                LEFT JOIN despacho_detalle dd ON dd.despacho_id = dl.despacho_id
                ORDER BY dl.despacho_created_at DESC, dd.detalle_id
            """

        return base_query

    def _agrupar_resultados(self, results: List) -> List[Dict[str, Any]]:
        """Agrupa los resultados de la query en estructura de despachos con detalles."""
        despachos_dict = {}

        for row in results:
            despacho_id = str(row[0])

            # Si es la primera vez que vemos este despacho, crear la entrada
            if despacho_id not in despachos_dict:
                oc_id = str(row[20]) if row[20] else None
                tiene_odc = oc_id is not None

                despachos_dict[despacho_id] = {
                    "despacho_id": despacho_id,
                    "empresa": row[1],
                    "codigo_cliente": row[2],
                    "fecha_despacho": serialize_date(row[3]),
                    "codigo_factura": row[4],
                    "anulada": bool(row[5]) if row[5] is not None else None,
                    "numero_pedido_sistema": row[6],
                    "numero_orden": row[7],
                    "numero_factura": row[8],
                    "tipo_documento": row[9],
                    "orden_compra": row[10],
                    "orden_compra_cliente": row[11],
                    "remision_facturada": bool(row[12]) if row[12] is not None else None,
                    "num_id_factura_relacionada": row[13],
                    "fecha_factura": serialize_date(row[14]),
                    "codigo_despacho": row[15],
                    "codigo_bodega": row[16],
                    "confirmado": bool(row[17]) if row[17] is not None else None,
                    "despacho_created_at": serialize_date(row[18]),
                    "despacho_updated_at": serialize_date(row[19]),
                    "tiene_odc": tiene_odc,
                    "oc_id": oc_id,
                    "despacho_detalles": [],
                    "orden_compra_info": {
                        "oc_id": oc_id,
                        "proveedor": row[21],
                        "fecha_generacion": serialize_date(row[22]),
                        "referencia_despacho": row[23],
                        "estado": row[24],
                        "numero_oc_sap": row[25],
                        "oc_created_at": serialize_date(row[26])
                    } if oc_id else None
                }

            # Agregar detalle si existe
            detalle_id = str(row[27]) if row[27] else None
            if detalle_id:
                detalle = {
                    "detalle_id": detalle_id,
                    "despacho_id": despacho_id,
                    "sku": row[28],
                    "cantidad_docena_mba3": serialize_decimal(row[29]),
                    "subtotal_sap": serialize_decimal(row[30]),
                    "cantidad_pack_sap": serialize_decimal(row[31]),
                    "unidad_sap": row[32],
                    "precio_unitario_mba3": serialize_decimal(row[33]),
                    "descuento": serialize_decimal(row[34]),
                    "total_linea_mba3": serialize_decimal(row[35]),
                    "impuesto": serialize_decimal(row[36]),
                    "nombre_producto": row[37],
                    "tipo_linea": row[38],
                    "precio_unitario_sap": serialize_decimal(row[39]),
                }
                despachos_dict[despacho_id]["despacho_detalles"].append(detalle)

        return list(despachos_dict.values())

