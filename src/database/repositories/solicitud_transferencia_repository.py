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
            solicitud_transferencia_id (UUID string) si se insertó correctamente, None si falló
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
                )
                OUTPUT INSERTED.solicitud_transferencia_id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            row = cursor.fetchone()
            self.conn.commit()
            solicitud_id = str(row[0]) if row and row[0] else None
            cursor.close()
            return solicitud_id

        except Exception as e:
            logger.error(f"Error al insertar solicitud_transferencia: {e}", exc_info=True)
            try:
                self.conn.rollback()
            except Exception:
                pass
            return None

    def insert_detalle(
        self,
        solicitud_transferencia_id: str,
        resultados: List[Dict[str, Any]],
    ) -> int:
        """
        Inserta una fila en solicitud_transferencia_detalle por cada tienda (resultado).
        Persiste la misma información que se envía por correo: Tienda, Nombre, Estado, DocNum.

        Args:
            solicitud_transferencia_id: UUID del registro en solicitud_transferencia
            resultados: Lista de dicts con tienda_codigo, tienda_nombre, success, doc_num, doc_entry, error

        Returns:
            Número de filas insertadas (0 si la tabla no existe o error)
        """
        if not resultados:
            return 0
        try:
            cursor = self.conn.cursor()
            insertados = 0
            for r in resultados:
                tienda_codigo = (r.get("tienda_codigo") or "N/A")[:20]
                tienda_nombre = (r.get("tienda_nombre") or "")[:255] if r.get("tienda_nombre") else None
                success = bool(r.get("success", False))
                estado = "Creada" if success else "Error"
                doc_num = r.get("doc_num")
                doc_entry = r.get("doc_entry")
                error_mensaje = (r.get("error") or "")[:500] if r.get("error") else None

                try:
                    cursor.execute(
                        """
                        INSERT INTO solicitud_transferencia_detalle (
                            solicitud_transferencia_id, tienda_codigo, tienda_nombre,
                            estado, doc_num, doc_entry, error_mensaje
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(solicitud_transferencia_id),
                            tienda_codigo,
                            tienda_nombre,
                            estado,
                            doc_num,
                            doc_entry,
                            error_mensaje,
                        ),
                    )
                    insertados += 1
                except Exception as e:
                    logger.warning(f"No se pudo insertar detalle para {tienda_codigo}: {e}")
            self.conn.commit()
            cursor.close()
            if insertados:
                logger.info(f"Persistidos {insertados} registros en solicitud_transferencia_detalle")
            return insertados
        except Exception as e:
            logger.warning(f"No se pudo insertar solicitud_transferencia_detalle (tabla puede no existir): {e}")
            try:
                self.conn.rollback()
            except Exception:
                pass
            return 0

    def get_doc_num_itr_por_oc_ids(self, oc_ids: List[str]) -> Dict[str, Any]:
        """
        Para cada oc_id devuelve el doc_num de la primera Solicitud de Transferencia (ITR)
        guardada en solicitud_transferencia_detalle. Es el número que debe mostrarse en la UI (ej. 70214643).

        Args:
            oc_ids: Lista de UUIDs de órdenes de compra.

        Returns:
            Dict oc_id -> doc_num (int o None). Solo incluye oc_ids que tengan al menos un ITR con doc_num.
        """
        if not oc_ids:
            return {}
        out = {}
        try:
            cursor = self.conn.cursor()
            placeholders = ",".join("?" * len(oc_ids))
            query = f"""
                SELECT st.oc_id, MIN(std.doc_num) AS doc_num
                FROM solicitud_transferencia st
                INNER JOIN solicitud_transferencia_detalle std
                    ON std.solicitud_transferencia_id = st.solicitud_transferencia_id
                WHERE st.oc_id IN ({placeholders}) AND std.doc_num IS NOT NULL
                GROUP BY st.oc_id
            """
            cursor.execute(query, [str(oid) for oid in oc_ids])
            for row in cursor.fetchall():
                out[str(row[0])] = row[1]
            cursor.close()
        except Exception as e:
            logger.warning(f"No se pudo obtener doc_num ITR por oc_id (tabla puede no existir): {e}")
        return out

    def get_detalle_by_solicitud_id(
        self, solicitud_transferencia_id: str
    ) -> List[Dict[str, Any]]:
        """
        Obtiene las filas de solicitud_transferencia_detalle para un batch de ST.
        Sirve para reconstruir resultados e itrs_por_tienda del modal de integración SAP.

        Args:
            solicitud_transferencia_id: UUID del registro en solicitud_transferencia.

        Returns:
            Lista de dicts con tienda_codigo, tienda_nombre, doc_num, doc_entry, success, error.
        """
        if not solicitud_transferencia_id:
            return []
        out = []
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT tienda_codigo, tienda_nombre, estado, doc_num, doc_entry, error_mensaje
                FROM solicitud_transferencia_detalle
                WHERE solicitud_transferencia_id = ?
                ORDER BY solicitud_transferencia_detalle_id
                """,
                (str(solicitud_transferencia_id),),
            )
            for row in cursor.fetchall():
                estado = (row[2] or "").strip()
                success = estado == "Creada"
                out.append({
                    "tienda_codigo": row[0] or "",
                    "tienda_nombre": row[1],
                    "estado": estado,
                    "doc_num": row[3],
                    "doc_entry": row[4],
                    "success": success,
                    "error": row[5] if not success else None,
                })
            cursor.close()
        except Exception as e:
            logger.warning(f"No se pudo obtener detalle ST por solicitud_id: {e}")
        return out

    def get_latest_resumen_by_oc_ids(self, oc_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Obtiene el resumen del último batch de ST por cada oc_id.

        Returns:
            Dict oc_id -> {
                "solicitud_transferencia_id": str,
                "total_tiendas": int,
                "transferencias_creadas": int,
                "transferencias_errores": int,
                "success": bool,
            }
        """
        if not oc_ids:
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        try:
            cursor = self.conn.cursor()
            placeholders = ",".join("?" * len(oc_ids))
            query = f"""
                WITH latest AS (
                    SELECT
                        solicitud_transferencia_id,
                        oc_id,
                        total_tiendas,
                        transferencias_creadas,
                        transferencias_errores,
                        success,
                        ROW_NUMBER() OVER (
                            PARTITION BY oc_id
                            ORDER BY creado_fecha DESC, solicitud_transferencia_id DESC
                        ) AS rn
                    FROM solicitud_transferencia
                    WHERE oc_id IN ({placeholders})
                )
                SELECT
                    solicitud_transferencia_id,
                    oc_id,
                    total_tiendas,
                    transferencias_creadas,
                    transferencias_errores,
                    success
                FROM latest
                WHERE rn = 1
            """
            cursor.execute(query, [str(oid) for oid in oc_ids])
            for row in cursor.fetchall():
                oc_id = str(row[1]) if row[1] else None
                if not oc_id:
                    continue
                out[oc_id] = {
                    "solicitud_transferencia_id": str(row[0]) if row[0] else None,
                    "total_tiendas": int(row[2] or 0),
                    "transferencias_creadas": int(row[3] or 0),
                    "transferencias_errores": int(row[4] or 0),
                    "success": bool(row[5]),
                }
            cursor.close()
        except Exception as e:
            logger.warning(f"No se pudo obtener resumen ST por oc_ids: {e}")
        return out

    def get_latest_failed_tienda_codigos_by_oc_id(self, oc_id: str) -> List[str]:
        """
        Obtiene códigos de tienda fallidos (estado Error) del último batch ST para un oc_id.
        """
        if not oc_id:
            return []
        out: List[str] = []
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT TOP 1 solicitud_transferencia_id
                FROM solicitud_transferencia
                WHERE oc_id = ?
                ORDER BY creado_fecha DESC, solicitud_transferencia_id DESC
                """,
                (str(oc_id),),
            )
            row = cursor.fetchone()
            solicitud_id = str(row[0]) if row and row[0] else None
            if not solicitud_id:
                cursor.close()
                return []
            cursor.execute(
                """
                SELECT DISTINCT tienda_codigo
                FROM solicitud_transferencia_detalle
                WHERE solicitud_transferencia_id = ?
                  AND estado = 'Error'
                  AND tienda_codigo IS NOT NULL
                """,
                (solicitud_id,),
            )
            for r in cursor.fetchall():
                codigo = (r[0] or "").strip()
                if codigo:
                    out.append(codigo)
            cursor.close()
        except Exception as e:
            logger.warning(f"No se pudo obtener tiendas fallidas ST por oc_id: {e}")
        return out
