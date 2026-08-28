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

    @staticmethod
    def _insert_one_detalle(cursor, solicitud_transferencia_id: str, r: Dict[str, Any]) -> bool:
        tienda_codigo = (r.get("tienda_codigo") or "N/A")[:20]
        tienda_nombre = (r.get("tienda_nombre") or "")[:255] if r.get("tienda_nombre") else None
        success = bool(r.get("success", False))
        estado_resultado = r.get("estado")
        if estado_resultado == "confirmada":
            estado = "Creada"
        elif estado_resultado == "error_confirmado":
            estado = "Error"
        elif estado_resultado == "pendiente_confirmacion":
            # Sin confirmar todavía (timeout con reintentos agotados, o job SAP
            # en curso) -- se persiste como 'Encolada' para que el próximo
            # reintento la vuelva a mirar (get_tiendas_pendientes_reintento_st
            # ya trata 'Encolada' como pendiente), aunque no venga de un HTTP
            # 202 real con job_id.
            estado = "Encolada"
        elif r.get("queued"):
            # Compatibilidad: resultados sin el campo 'estado' (llamadores que
            # aún no pasan por la clasificación de 3 estados de _enviar_itrs_a_sap).
            estado = "Encolada"
        else:
            estado = "Creada" if success else "Error"
        doc_num = r.get("doc_num")
        doc_entry = r.get("doc_entry")
        job_id = (r.get("job_id") or None)
        error_mensaje = (r.get("error") or "")[:500] if r.get("error") else None
        try:
            cursor.execute(
                """
                INSERT INTO solicitud_transferencia_detalle (
                    solicitud_transferencia_id, tienda_codigo, tienda_nombre,
                    estado, doc_num, doc_entry, error_mensaje, job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(solicitud_transferencia_id),
                    tienda_codigo,
                    tienda_nombre,
                    estado,
                    doc_num,
                    doc_entry,
                    error_mensaje,
                    job_id,
                ),
            )
            return True
        except Exception as e:
            logger.warning(f"No se pudo insertar detalle para {tienda_codigo}: {e}")
            return False

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
                if self._insert_one_detalle(cursor, solicitud_transferencia_id, r):
                    insertados += 1
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

    def insert_detalle_individual(self, solicitud_transferencia_id: str, r: Dict[str, Any]) -> bool:
        """
        Inserta el detalle de UNA tienda de inmediato (su propio cursor + commit),
        en vez de esperar a que el lote de hasta 23 tiendas termine para persistir
        todo junto. Si el proceso se interrumpe (deploy, worker reiniciado, un bug)
        a mitad del envío a SAP, las tiendas ya resueltas hasta ese punto quedan
        registradas igual -- el batch-al-final original podía perder de golpe todas
        las confirmaciones reales de SAP si la interrupción ocurría después del
        último POST pero antes de ese guardado (ver conversación 2026-08-28).
        """
        try:
            cursor = self.conn.cursor()
            insertado = self._insert_one_detalle(cursor, solicitud_transferencia_id, r)
            self.conn.commit()
            cursor.close()
            return insertado
        except Exception as e:
            logger.warning(
                f"⚠️ No se pudo persistir de inmediato el detalle de "
                f"{r.get('tienda_codigo', 'N/A')}: {e}"
            )
            try:
                self.conn.rollback()
            except Exception:
                pass
            return False

    def update_detalle_individual(self, solicitud_transferencia_id: str, r: Dict[str, Any]) -> bool:
        """
        Actualiza el detalle ya persistido de UNA tienda (match por
        solicitud_transferencia_id + tienda_codigo) -- para cuando una tienda que
        se guardó como 'Encolada' (pendiente_confirmacion) se confirma más tarde,
        dentro del mismo request, vía la reconciliación de solo lectura al cierre
        (StockTransferService._reconciliar_pendientes_confirmacion). Evita dejar en
        la BD un estado ya superado en memoria.
        """
        tienda_codigo = (r.get("tienda_codigo") or "N/A")[:20]
        estado_resultado = r.get("estado")
        estado = "Creada" if estado_resultado == "confirmada" else (
            "Error" if estado_resultado == "error_confirmado" else "Encolada"
        )
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE solicitud_transferencia_detalle
                SET estado = ?, doc_num = ?, doc_entry = ?, error_mensaje = ?
                WHERE solicitud_transferencia_id = ? AND tienda_codigo = ?
                """,
                (
                    estado,
                    r.get("doc_num"),
                    r.get("doc_entry"),
                    (r.get("error") or "")[:500] if r.get("error") else None,
                    str(solicitud_transferencia_id),
                    tienda_codigo,
                ),
            )
            actualizado = cursor.rowcount > 0
            self.conn.commit()
            cursor.close()
            return actualizado
        except Exception as e:
            logger.warning(
                f"⚠️ No se pudo actualizar el detalle confirmado tardíamente de "
                f"{tienda_codigo}: {e}"
            )
            try:
                self.conn.rollback()
            except Exception:
                pass
            return False

    def update_resumen(self, solicitud_transferencia_id: str, resultado: Dict[str, Any]) -> bool:
        """
        Actualiza los contadores finales del encabezado (creado antes del envío a
        SAP con insert(), en 0/False) una vez que el lote completo terminó. El
        detalle por tienda ya se persistió aparte, tienda por tienda, vía
        insert_detalle_individual/update_detalle_individual -- esto solo cierra el
        resumen del encabezado (no vuelve a tocar solicitud_transferencia_detalle).
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
                UPDATE solicitud_transferencia
                SET transferencias_creadas = ?, transferencias_errores = ?,
                    success = ?, resultado_json = ?
                WHERE solicitud_transferencia_id = ?
                """,
                (
                    resultado.get("transferencias_creadas", 0),
                    resultado.get("transferencias_errores", 0),
                    1 if resultado.get("success") else 0,
                    resultado_json,
                    str(solicitud_transferencia_id),
                ),
            )
            actualizado = cursor.rowcount > 0
            self.conn.commit()
            cursor.close()
            return actualizado
        except Exception as e:
            logger.warning(f"No se pudo actualizar el resumen de solicitud_transferencia: {e}")
            try:
                self.conn.rollback()
            except Exception:
                pass
            return False

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

    def get_resumen_agregado_por_oc_id(self, oc_id: str) -> Dict[str, Any]:
        """
        Agrega el resultado de TODAS las Solicitudes de Transferencia (ITR) de una OC,
        uniendo todos los batches (envío original + reintentos posteriores). Por cada
        tienda destino se queda con la fila 'Creada' si tuvo éxito en cualquier intento;
        si nunca tuvo éxito, con la fila más reciente (el error vigente).

        A diferencia de get_detalle_by_solicitud_id (que solo mira un batch puntual),
        este método evita mostrar un resumen congelado del primer intento cuando un
        reintento posterior ya completó las tiendas que habían fallado.

        Returns:
            {
                "total_tiendas": int,
                "transferencias_creadas": int,
                "transferencias_errores": int,
                "resultados": [{tienda_codigo, tienda_nombre, doc_num, doc_entry, success, error}],
                "itrs_por_tienda": [{doc_num, tienda_codigo}],
            }
        """
        vacio: Dict[str, Any] = {
            "total_tiendas": 0,
            "transferencias_creadas": 0,
            "transferencias_errores": 0,
            "resultados": [],
            "itrs_por_tienda": [],
        }
        if not oc_id:
            return vacio
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                WITH agg AS (
                    SELECT
                        d.tienda_codigo,
                        d.tienda_nombre,
                        d.doc_num,
                        d.doc_entry,
                        d.estado,
                        d.error_mensaje,
                        ROW_NUMBER() OVER (
                            PARTITION BY UPPER(LTRIM(RTRIM(d.tienda_codigo)))
                            ORDER BY
                                CASE WHEN d.estado = 'Creada' AND d.doc_entry IS NOT NULL THEN 0 ELSE 1 END,
                                st.creado_fecha DESC,
                                d.solicitud_transferencia_detalle_id DESC
                        ) AS rn
                    FROM solicitud_transferencia_detalle d
                    INNER JOIN solicitud_transferencia st
                        ON st.solicitud_transferencia_id = d.solicitud_transferencia_id
                    WHERE st.oc_id = ?
                      AND d.tienda_codigo IS NOT NULL
                      AND LTRIM(RTRIM(d.tienda_codigo)) <> ''
                )
                SELECT tienda_codigo, tienda_nombre, doc_num, doc_entry, estado, error_mensaje
                FROM agg
                WHERE rn = 1
                ORDER BY tienda_codigo
                """,
                (str(oc_id),),
            )
            rows = cursor.fetchall()
            cursor.close()
        except Exception as e:
            logger.warning(f"No se pudo obtener resumen agregado ST por oc_id: {e}")
            return vacio

        resultados = []
        itrs_por_tienda = []
        creadas = 0
        for row in rows:
            estado = (row[4] or "").strip()
            success = estado == "Creada" and row[3] is not None
            if success:
                creadas += 1
            resultados.append({
                "tienda_codigo": row[0] or "",
                "tienda_nombre": row[1],
                "doc_num": row[2],
                "doc_entry": row[3],
                "success": success,
                "error": row[5] if not success else None,
            })
            if success and row[2] is not None:
                itrs_por_tienda.append({"doc_num": row[2], "tienda_codigo": row[0] or ""})

        return {
            "total_tiendas": len(rows),
            "transferencias_creadas": creadas,
            "transferencias_errores": len(rows) - creadas,
            "resultados": resultados,
            "itrs_por_tienda": itrs_por_tienda,
        }

    def get_resumen_agregado_por_oc_ids(self, oc_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Como get_resumen_agregado_por_oc_id, pero para varias OC en una sola consulta
        (para el listado paginado de /ordenes-compra).

        Bug que corrige: el listado usaba get_latest_resumen_by_oc_ids (totales del
        ÚLTIMO batch de ST) para el badge "Reintentar ST" de la tabla, mientras que el
        modal "Integración con SAP Completada" usa este agregado por tienda (todos los
        batches). Si un reintento posterior solo reprocesó las tiendas que habían
        fallado (ej. 2 de 34), el badge mostraba "2/2" (el batch chico) en vez de un
        total consistente con las 34 tiendas reales del pedido que muestra el modal.

        Returns:
            Dict oc_id -> {"total_tiendas": int, "transferencias_creadas": int, "transferencias_errores": int}
        """
        out: Dict[str, Dict[str, Any]] = {}
        if not oc_ids:
            return out
        try:
            cursor = self.conn.cursor()
            placeholders = ",".join("?" * len(oc_ids))
            cursor.execute(
                f"""
                WITH agg AS (
                    SELECT
                        st.oc_id,
                        d.tienda_codigo,
                        d.doc_entry,
                        d.estado,
                        ROW_NUMBER() OVER (
                            PARTITION BY st.oc_id, UPPER(LTRIM(RTRIM(d.tienda_codigo)))
                            ORDER BY
                                CASE WHEN d.estado = 'Creada' AND d.doc_entry IS NOT NULL THEN 0 ELSE 1 END,
                                st.creado_fecha DESC,
                                d.solicitud_transferencia_detalle_id DESC
                        ) AS rn
                    FROM solicitud_transferencia_detalle d
                    INNER JOIN solicitud_transferencia st
                        ON st.solicitud_transferencia_id = d.solicitud_transferencia_id
                    WHERE st.oc_id IN ({placeholders})
                      AND d.tienda_codigo IS NOT NULL
                      AND LTRIM(RTRIM(d.tienda_codigo)) <> ''
                )
                SELECT oc_id, estado, doc_entry
                FROM agg
                WHERE rn = 1
                """,
                [str(oid) for oid in oc_ids],
            )
            rows = cursor.fetchall()
            cursor.close()
            for oc_id, estado, doc_entry in rows:
                key = str(oc_id)
                bucket = out.setdefault(key, {"total_tiendas": 0, "transferencias_creadas": 0, "transferencias_errores": 0})
                bucket["total_tiendas"] += 1
                if (estado or "").strip() == "Creada" and doc_entry is not None:
                    bucket["transferencias_creadas"] += 1
                else:
                    bucket["transferencias_errores"] += 1
        except Exception as e:
            logger.warning(f"No se pudo obtener resumen agregado ST por oc_ids: {e}")
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

    @staticmethod
    def _norm_tienda(codigo: Optional[str]) -> str:
        return (codigo or "").strip().upper()

    def _get_latest_solicitud_transferencia_id(self, oc_id: str) -> Optional[str]:
        if not oc_id:
            return None
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
            cursor.close()
            return str(row[0]) if row and row[0] else None
        except Exception as e:
            logger.warning(f"No se pudo obtener último solicitud_transferencia por oc_id: {e}")
            return None

    def get_tiendas_itr_ok_norms_por_oc_id(self, oc_id: str) -> set:
        """
        Tiendas (normalizadas) que ya tienen ITR creado en SAP para esta OC,
        en cualquier batch (Creada + doc_entry).
        """
        if not oc_id:
            return set()
        norms: set = set()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT d.tienda_codigo
                FROM solicitud_transferencia_detalle d
                INNER JOIN solicitud_transferencia st
                    ON st.solicitud_transferencia_id = d.solicitud_transferencia_id
                WHERE st.oc_id = ?
                  AND d.estado = 'Creada'
                  AND d.doc_entry IS NOT NULL
                  AND d.tienda_codigo IS NOT NULL
                  AND LTRIM(RTRIM(d.tienda_codigo)) <> ''
                """,
                (str(oc_id),),
            )
            for row in cursor.fetchall():
                n = self._norm_tienda(row[0])
                if n:
                    norms.add(n)
            cursor.close()
        except Exception as e:
            logger.warning(f"No se pudo listar ITR OK por oc_id: {e}")
        return norms

    def get_tiendas_faltantes_por_oc_id(self, oc_id: str) -> List[str]:
        """
        Tiendas (es_bodega=False) que la distribución confirmada del pedido espera
        con cantidad_asignada > 0, pero que NO tienen ningún registro (ni Creada,
        ni Error, ni Encolada) en solicitud_transferencia_detalle en ningún batch
        de esta OC -- a diferencia de get_tiendas_pendientes_reintento_st, que solo
        detecta tiendas que SÍ se intentaron y quedaron en Error/Encolada.

        Cubre el hueco donde una tienda nunca llegó a intentarse (bug silencioso
        en la generación de payloads, no un fallo de SAP) -- ver conversación
        2026-08-28 (F4.5).

        Usa la ÚLTIMA versión de distribucion_confirmada del pedido (redistribución
        más reciente); excluye bodegas (RL-CD/RG-CD/OUT-CD) porque esas se envían
        por un flujo aparte (OCSAPService._enviar_itrs_por_bodega, ver
        solicitud_transferencia_bodega_repository.py) que este método no cubre.
        """
        if not oc_id:
            return []
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                WITH pedido AS (
                    SELECT TOP 1 pedido_id
                    FROM solicitud_transferencia
                    WHERE oc_id = ? AND pedido_id IS NOT NULL
                    ORDER BY creado_fecha DESC
                ),
                ultima_version AS (
                    SELECT MAX(dc.version) AS version
                    FROM distribucion_confirmada dc
                    INNER JOIN pedido p ON p.pedido_id = dc.pedido_id
                ),
                esperadas AS (
                    SELECT DISTINCT t.codigo AS tienda_codigo
                    FROM distribucion_confirmada dc
                    INNER JOIN pedido p ON p.pedido_id = dc.pedido_id
                    INNER JOIN ultima_version uv ON uv.version = dc.version
                    INNER JOIN tienda t ON t.tienda_id = dc.tienda_id
                    LEFT JOIN pedido_detalle_tienda pdt
                        ON pdt.pedido_detalle_id = dc.pedido_detalle_id
                        AND pdt.tienda_id = dc.tienda_id
                    WHERE ISNULL(pdt.es_bodega, 0) = 0
                      AND dc.cantidad_asignada > 0
                ),
                intentadas AS (
                    SELECT DISTINCT d.tienda_codigo
                    FROM solicitud_transferencia_detalle d
                    INNER JOIN solicitud_transferencia st
                        ON st.solicitud_transferencia_id = d.solicitud_transferencia_id
                    WHERE st.oc_id = ?
                )
                SELECT e.tienda_codigo
                FROM esperadas e
                LEFT JOIN intentadas i
                    ON UPPER(LTRIM(RTRIM(i.tienda_codigo))) = UPPER(LTRIM(RTRIM(e.tienda_codigo)))
                WHERE i.tienda_codigo IS NULL
                """,
                (str(oc_id), str(oc_id)),
            )
            faltantes = [row[0] for row in cursor.fetchall() if row[0]]
            cursor.close()
            return faltantes
        except Exception as e:
            logger.warning(f"No se pudo calcular tiendas faltantes por oc_id: {e}")
            return []

    def get_tiendas_pendientes_reintento_st(self, oc_id: str) -> List[str]:
        """
        Tiendas del último batch aún en Error o Encolada, excluyendo las que ya
        tienen ITR OK en cualquier intento previo (idempotencia / anti-duplicado).

        'Encolada' (job SAP en curso, ver get_tiendas_encoladas_con_job_id) también
        cuenta como pendiente: el caller (StockTransferService) decide si crea una
        ITR nueva (Error) o solo consulta el estado del job (Encolada) antes de
        reenviar, para no duplicar una ITR cuyo job original sigue en curso.
        """
        if not oc_id:
            return []
        solicitud_id = self._get_latest_solicitud_transferencia_id(oc_id)
        if not solicitud_id:
            return []
        ok_norms = self.get_tiendas_itr_ok_norms_por_oc_id(oc_id)
        candidatas: List[str] = []
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT tienda_codigo
                FROM solicitud_transferencia_detalle
                WHERE solicitud_transferencia_id = ?
                  AND estado IN ('Error', 'Encolada')
                  AND tienda_codigo IS NOT NULL
                  AND LTRIM(RTRIM(tienda_codigo)) <> ''
                """,
                (solicitud_id,),
            )
            for row in cursor.fetchall():
                raw = (row[0] or "").strip()
                if not raw:
                    continue
                if self._norm_tienda(raw) in ok_norms:
                    continue
                candidatas.append(raw)
            cursor.close()
        except Exception as e:
            logger.warning(f"No se pudo calcular tiendas pendientes ST: {e}")
            return []
        return candidatas

    def get_tiendas_encoladas_con_job_id(
        self, oc_id: str, tiendas_codigos: List[str]
    ) -> Dict[str, str]:
        """
        De las tiendas indicadas, cuáles quedaron 'Encolada' (HTTP 202) en el
        último batch ST de la OC, con su job_id.

        El caller debe consultar GET /api/v1/jobs/{job_id} para cada una antes de
        decidir si reintenta (evita crear una ITR duplicada si el job original
        todavía puede completarse en segundo plano).

        Returns:
            {tienda_codigo_normalizado: job_id}
        """
        if not oc_id or not tiendas_codigos:
            return {}
        solicitud_id = self._get_latest_solicitud_transferencia_id(oc_id)
        if not solicitud_id:
            return {}
        objetivo_norms = {self._norm_tienda(c) for c in tiendas_codigos if self._norm_tienda(c)}
        if not objetivo_norms:
            return {}
        resultado: Dict[str, str] = {}
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT tienda_codigo, job_id
                FROM solicitud_transferencia_detalle
                WHERE solicitud_transferencia_id = ?
                  AND estado = 'Encolada'
                  AND job_id IS NOT NULL
                """,
                (solicitud_id,),
            )
            for row in cursor.fetchall():
                tienda_norm = self._norm_tienda(row[0])
                if tienda_norm in objetivo_norms and row[1]:
                    resultado[tienda_norm] = str(row[1])
            cursor.close()
        except Exception as e:
            logger.warning(f"No se pudo obtener tiendas encoladas con job_id: {e}")
            return {}
        return resultado

    @staticmethod
    def _filtrar_tiendas_fallidas(resultados: List[Any], ok_norms: set) -> List[str]:
        out: List[str] = []
        for r in resultados:
            if not isinstance(r, dict):
                continue
            if r.get("success"):
                continue
            cod = (r.get("tienda_codigo") or "").strip()
            if not cod:
                continue
            if cod.upper() in ok_norms:
                continue
            out.append(cod)
        return out

    def get_tiendas_fallidas_desde_resultado_json_fallback(self, oc_id: str) -> List[str]:
        """
        Si no hay filas en solicitud_transferencia_detalle,
        intenta extraer tiendas con error desde resultado_json del último batch.
        """
        if not oc_id:
            return []
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT TOP 1 resultado_json
                FROM solicitud_transferencia
                WHERE oc_id = ?
                ORDER BY creado_fecha DESC, solicitud_transferencia_id DESC
                """,
                (str(oc_id),),
            )
            row = cursor.fetchone()
            cursor.close()
            if not row or not row[0]:
                return []
            data = json.loads(row[0])
            if not isinstance(data, dict):
                return []
            resultados = data.get("resultados") or []
            ok_norms = self.get_tiendas_itr_ok_norms_por_oc_id(oc_id)
            return list(dict.fromkeys(self._filtrar_tiendas_fallidas(resultados, ok_norms)))
        except Exception as e:
            logger.warning(f"Fallback resultado_json ST no disponible: {e}")
            return []

    def get_st_pendiente_reintento_count(self, oc_id: str) -> int:
        """Cuenta tiendas que aún requieren reintento ITR (detalle o fallback JSON)."""
        pend = self.get_tiendas_pendientes_reintento_st(oc_id)
        if pend:
            return len(pend)
        return len(self.get_tiendas_fallidas_desde_resultado_json_fallback(oc_id))

    def count_st_pendientes_reintento_por_oc_ids(self, oc_ids: List[str]) -> Dict[str, int]:
        """
        Para la tabla proceso: cuenta por oc_id cuántas tiendas siguen pendientes de reintento ITR.
        """
        if not oc_ids:
            return {}
        return {str(oid): self.get_st_pendiente_reintento_count(str(oid)) for oid in oc_ids}

    def get_oc_ids_con_tiendas_pendientes(self, dias_ventana: int) -> List[str]:
        """
        OCs en estado ENVIADA, con su primer intento de ST dentro de los últimos
        `dias_ventana` días, cuyo último batch ST tiene al menos una tienda en Error
        sin ITR ya creado en ningún intento previo (misma idempotencia que
        get_tiendas_pendientes_reintento_st, pero calculada para todas las OCs a la vez).

        `dias_ventana` es obligatorio a propósito (sin default): la reconciliación
        automática NO debe alcanzar OCs viejas sin que quien la llama lo decida
        explícitamente -- ver conversación 2026-08-28 (barrido diario corto vs.
        semanal más amplio en celery_reconciliar_transferencias.py).

        Candidatas a reconciliación automática (tarea Celery periódica).
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                WITH primer_envio AS (
                    SELECT oc_id, MIN(creado_fecha) AS fecha
                    FROM solicitud_transferencia
                    WHERE oc_id IS NOT NULL
                    GROUP BY oc_id
                ),
                latest AS (
                    SELECT
                        st.solicitud_transferencia_id,
                        st.oc_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY st.oc_id
                            ORDER BY st.creado_fecha DESC, st.solicitud_transferencia_id DESC
                        ) AS rn
                    FROM solicitud_transferencia st
                    INNER JOIN orden_compra_cabecera oc ON oc.oc_id = st.oc_id
                    INNER JOIN primer_envio pe ON pe.oc_id = st.oc_id
                    WHERE oc.estado = 'ENVIADA' AND pe.fecha >= DATEADD(day, -?, GETDATE())
                ),
                latest_error_tiendas AS (
                    SELECT DISTINCT l.oc_id, d.tienda_codigo
                    FROM latest l
                    INNER JOIN solicitud_transferencia_detalle d
                        ON d.solicitud_transferencia_id = l.solicitud_transferencia_id
                    WHERE l.rn = 1 AND d.estado = 'Error'
                ),
                ok_tiendas AS (
                    SELECT DISTINCT st.oc_id, d.tienda_codigo
                    FROM solicitud_transferencia st
                    INNER JOIN solicitud_transferencia_detalle d
                        ON d.solicitud_transferencia_id = st.solicitud_transferencia_id
                    WHERE d.estado = 'Creada' AND d.doc_entry IS NOT NULL
                )
                SELECT DISTINCT e.oc_id
                FROM latest_error_tiendas e
                LEFT JOIN ok_tiendas o
                    ON o.oc_id = e.oc_id
                    AND UPPER(LTRIM(RTRIM(o.tienda_codigo))) = UPPER(LTRIM(RTRIM(e.tienda_codigo)))
                WHERE o.tienda_codigo IS NULL
                """,
                (dias_ventana,),
            )
            oc_ids = [str(row[0]) for row in cursor.fetchall() if row[0]]
            cursor.close()
            return oc_ids
        except Exception as e:
            logger.warning(f"No se pudo obtener OCs con ST pendientes: {e}")
            return []

    def get_oc_ids_con_tiendas_faltantes(self, dias_ventana: int) -> List[str]:
        """
        OCs en estado ENVIADA, con su primer intento de ST dentro de los últimos
        `dias_ventana` días, donde la distribución confirmada del pedido espera al
        menos una tienda (es_bodega=False, cantidad_asignada > 0) que NUNCA se
        intentó -- ningún registro en solicitud_transferencia_detalle, en ningún
        batch. Complementa get_oc_ids_con_tiendas_pendientes, que solo detecta
        tiendas que SÍ se intentaron y quedaron en Error/Encolada (F4.5).

        `dias_ventana` es obligatorio a propósito, mismo criterio que
        get_oc_ids_con_tiendas_pendientes.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                WITH primer_envio AS (
                    SELECT oc_id, MIN(creado_fecha) AS fecha
                    FROM solicitud_transferencia
                    WHERE oc_id IS NOT NULL
                    GROUP BY oc_id
                ),
                oc_candidatas AS (
                    SELECT DISTINCT st.oc_id, st.pedido_id
                    FROM solicitud_transferencia st
                    INNER JOIN orden_compra_cabecera oc ON oc.oc_id = st.oc_id
                    INNER JOIN primer_envio pe ON pe.oc_id = st.oc_id
                    WHERE oc.estado = 'ENVIADA'
                      AND pe.fecha >= DATEADD(day, -?, GETDATE())
                      AND st.pedido_id IS NOT NULL
                ),
                ultima_version AS (
                    SELECT dc.pedido_id, MAX(dc.version) AS version
                    FROM distribucion_confirmada dc
                    INNER JOIN oc_candidatas c ON c.pedido_id = dc.pedido_id
                    GROUP BY dc.pedido_id
                ),
                esperadas AS (
                    SELECT DISTINCT c.oc_id, t.codigo AS tienda_codigo
                    FROM oc_candidatas c
                    INNER JOIN ultima_version uv ON uv.pedido_id = c.pedido_id
                    INNER JOIN distribucion_confirmada dc
                        ON dc.pedido_id = c.pedido_id AND dc.version = uv.version
                    INNER JOIN tienda t ON t.tienda_id = dc.tienda_id
                    LEFT JOIN pedido_detalle_tienda pdt
                        ON pdt.pedido_detalle_id = dc.pedido_detalle_id
                        AND pdt.tienda_id = dc.tienda_id
                    WHERE ISNULL(pdt.es_bodega, 0) = 0
                      AND dc.cantidad_asignada > 0
                ),
                intentadas AS (
                    SELECT DISTINCT st.oc_id, d.tienda_codigo
                    FROM solicitud_transferencia st
                    INNER JOIN solicitud_transferencia_detalle d
                        ON d.solicitud_transferencia_id = st.solicitud_transferencia_id
                    WHERE st.oc_id IN (SELECT oc_id FROM oc_candidatas)
                )
                SELECT DISTINCT e.oc_id
                FROM esperadas e
                LEFT JOIN intentadas i
                    ON i.oc_id = e.oc_id
                    AND UPPER(LTRIM(RTRIM(i.tienda_codigo))) = UPPER(LTRIM(RTRIM(e.tienda_codigo)))
                WHERE i.tienda_codigo IS NULL
                """,
                (dias_ventana,),
            )
            oc_ids = [str(row[0]) for row in cursor.fetchall() if row[0]]
            cursor.close()
            return oc_ids
        except Exception as e:
            logger.warning(f"No se pudo obtener OCs con tiendas faltantes: {e}")
            return []

    def get_doc_num_itr_por_pedido_id(self, pedido_id: str) -> Dict[str, int]:
        """
        Mapa tienda_codigo NORMALIZADO (UPPER+TRIM) -> doc_num de la ITR más reciente.

        Escala por solicitud_transferencia.pedido_id para cubrir TODOS los batches del
        pedido (reintentos incluidos) y el caso oc_id NULL. Desempata con ROW_NUMBER por
        creado_fecha DESC, de modo que un reintento posterior gana: a diferencia de
        get_doc_num_itr_por_oc_ids, no usa MIN(doc_num).

        Limitación conocida: las BODEGAS destino (RL-CD, RG-CD, OUT-CD) nunca aparecen
        aquí porque su flujo de ITR (OCSAPService._enviar_itrs_por_bodega) no persiste
        el doc_num en base de datos, solo lo devuelve en la respuesta HTTP.

        Args:
            pedido_id: UUID del pedido.

        Returns:
            Dict tienda_codigo normalizado -> doc_num (int). Vacío si no hay ITR creadas.
        """
        if not pedido_id:
            return {}
        out: Dict[str, int] = {}
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                WITH itr AS (
                    SELECT
                        UPPER(LTRIM(RTRIM(d.tienda_codigo))) AS tienda_norm,
                        d.doc_num,
                        ROW_NUMBER() OVER (
                            PARTITION BY UPPER(LTRIM(RTRIM(d.tienda_codigo)))
                            ORDER BY st.creado_fecha DESC, d.creado_fecha DESC
                        ) AS rn
                    FROM solicitud_transferencia st
                    INNER JOIN solicitud_transferencia_detalle d
                        ON d.solicitud_transferencia_id = st.solicitud_transferencia_id
                    WHERE st.pedido_id = ?
                      AND d.estado = 'Creada'
                      AND d.doc_num IS NOT NULL
                      AND d.tienda_codigo IS NOT NULL
                      AND LTRIM(RTRIM(d.tienda_codigo)) <> ''
                )
                SELECT tienda_norm, doc_num FROM itr WHERE rn = 1
                """,
                (str(pedido_id),),
            )
            for row in cursor.fetchall():
                if row[0] and row[1] is not None:
                    out[self._norm_tienda(row[0])] = int(row[1])
            cursor.close()
        except Exception as e:
            logger.warning(f"No se pudo obtener doc_num ITR por pedido_id: {e}")
        return out
