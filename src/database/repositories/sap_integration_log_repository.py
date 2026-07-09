"""
Repositorio para guardar logs de integración con SAP Service Layer.
"""

import logging
import json
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)


@dataclass
class SAPLogEntry:
    """Datos de un log de integración SAP."""
    nivel_log: str
    mensaje: str
    proceso_id: Optional[str] = None
    usuario: Optional[str] = None
    fuente: Optional[str] = None
    oc_id: Optional[str] = None
    referencia_despacho: Optional[str] = None
    proveedor: Optional[str] = None
    doc_entry: Optional[int] = None
    doc_num: Optional[int] = None
    error_code: Optional[str] = None
    error_source: Optional[str] = None
    success: Optional[bool] = None
    detalles_adicionales: Optional[Dict[str, Any]] = None


class SAPIntegrationLogRepository:
    """Repositorio para guardar logs de integración con SAP."""
    
    def __init__(self, connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            connection: Conexión a SQL Server (pyodbc.Connection)
        """
        self.conn = connection
    
    def guardar_log(self, entry: SAPLogEntry) -> None:
        """
        Guarda un log de integración SAP en la base de datos.

        Solo guarda logs que tengan información relevante de OC (oc_id, referencia_despacho o proveedor).
        Los logs sin información de OC (inicio/fin del proceso) no se guardan.

        Args:
            entry: Datos del log a guardar
        """
        if not entry.oc_id and not entry.referencia_despacho and not entry.proveedor:
            logger.debug(f"Log omitido (sin información de OC): {entry.mensaje[:50]}...")
            return

        try:
            cursor = self.conn.cursor()

            detalles_json = None
            if entry.detalles_adicionales:
                try:
                    detalles_json = json.dumps(entry.detalles_adicionales, ensure_ascii=False, default=str)
                except Exception as e:
                    logger.warning(f"No se pudo serializar detalles_adicionales: {e}")

            proceso_id_str = str(entry.proceso_id) if entry.proceso_id else None
            oc_id_str = str(entry.oc_id) if entry.oc_id else None

            query = """
                INSERT INTO sap_integration_logs (
                    proceso_id, timestamp_log, nivel_log, mensaje,
                    usuario, fuente, oc_id, referencia_despacho, proveedor,
                    doc_entry, doc_num, error_code, error_source, success,
                    detalles_adicionales
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            cursor.execute(query, (
                proceso_id_str,
                ahora_naive(),
                entry.nivel_log,
                entry.mensaje,
                entry.usuario,
                entry.fuente,
                oc_id_str,
                entry.referencia_despacho,
                entry.proveedor,
                entry.doc_entry,
                entry.doc_num,
                entry.error_code,
                entry.error_source,
                entry.success,
                detalles_json
            ))

            self.conn.commit()
            cursor.close()

        except Exception as e:
            logger.error(f"Error al guardar log de integración SAP: {e}", exc_info=True)
            try:
                self.conn.rollback()
            except Exception:
                pass
    
    @staticmethod
    def _build_where_clause(
        oc_id: Optional[str],
        referencia_despacho: Optional[str],
        proveedor: Optional[str],
        fecha_desde: Optional[datetime],
        fecha_hasta: Optional[datetime],
        nivel_log: Optional[str],
        success: Optional[bool],
    ):
        conditions = []
        params = []
        if oc_id:
            conditions.append("oc_id = ?")
            params.append(str(oc_id))
        if referencia_despacho:
            conditions.append("referencia_despacho = ?")
            params.append(referencia_despacho)
        if proveedor:
            conditions.append("proveedor = ?")
            params.append(proveedor)
        if fecha_desde:
            conditions.append("timestamp_log >= ?")
            params.append(fecha_desde)
        if fecha_hasta:
            conditions.append("timestamp_log <= ?")
            params.append(fecha_hasta)
        if nivel_log:
            conditions.append("nivel_log = ?")
            params.append(nivel_log)
        if success is not None:
            conditions.append("success = ?")
            params.append(1 if success else 0)
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        return where_clause, params

    @staticmethod
    def _map_log_row(log_dict: Dict[str, Any]) -> Dict[str, Any]:
        if log_dict.get("detalles_adicionales"):
            try:
                log_dict["detalles_adicionales"] = json.loads(log_dict["detalles_adicionales"])
            except Exception:
                pass
        if log_dict.get("timestamp_log") and isinstance(log_dict["timestamp_log"], datetime):
            log_dict["timestamp_log"] = log_dict["timestamp_log"].isoformat()
        return log_dict

    def get_historial_ordenes(
        self,
        oc_id: Optional[str] = None,
        referencia_despacho: Optional[str] = None,
        proveedor: Optional[str] = None,
        fecha_desde: Optional[datetime] = None,
        fecha_hasta: Optional[datetime] = None,
        nivel_log: Optional[str] = None,
        success: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Obtiene el historial de órdenes desde los logs de integración SAP.

        Args:
            oc_id: Filtrar por UUID de orden de compra
            referencia_despacho: Filtrar por referencia de despacho
            proveedor: Filtrar por código de proveedor
            fecha_desde: Filtrar desde esta fecha
            fecha_hasta: Filtrar hasta esta fecha
            nivel_log: Filtrar por nivel (INFO, ERROR, WARNING)
            success: Filtrar por éxito (True) o error (False)
            limit: Límite de registros
            offset: Offset para paginación

        Returns:
            Diccionario con 'data' (lista de logs) y 'total' (conteo total)
        """
        try:
            cursor = self.conn.cursor()

            where_clause, params = self._build_where_clause(
                oc_id, referencia_despacho, proveedor,
                fecha_desde, fecha_hasta, nivel_log, success
            )

            count_query = f"SELECT COUNT(*) FROM sap_integration_logs WHERE {where_clause}"
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]

            data_query = f"""
                SELECT
                    log_id,
                    proceso_id,
                    timestamp_log,
                    nivel_log,
                    mensaje,
                    usuario,
                    fuente,
                    oc_id,
                    referencia_despacho,
                    proveedor,
                    doc_entry,
                    doc_num,
                    error_code,
                    error_source,
                    success,
                    detalles_adicionales
                FROM sap_integration_logs
                WHERE {where_clause}
                ORDER BY timestamp_log DESC
            """

            if limit:
                data_query += " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
                params.extend([offset or 0, limit])

            cursor.execute(data_query, params)

            columns = [col[0] for col in cursor.description]
            logs = [self._map_log_row(dict(zip(columns, row))) for row in cursor.fetchall()]

            cursor.close()

            return {"data": logs, "total": total}

        except Exception as e:
            logger.error(f"Error al obtener historial de órdenes: {e}", exc_info=True)
            raise

