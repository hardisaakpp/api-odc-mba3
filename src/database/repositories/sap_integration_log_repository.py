"""
Repositorio para guardar logs de integración con SAP Service Layer.
"""

import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class SAPIntegrationLogRepository:
    """Repositorio para guardar logs de integración con SAP."""
    
    def __init__(self, connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            connection: Conexión a SQL Server (pyodbc.Connection)
        """
        self.conn = connection
    
    def guardar_log(
        self,
        proceso_id: Optional[str],
        nivel_log: str,
        mensaje: str,
        usuario: Optional[str] = None,
        fuente: Optional[str] = None,
        oc_id: Optional[str] = None,
        referencia_despacho: Optional[str] = None,
        proveedor: Optional[str] = None,
        doc_entry: Optional[int] = None,
        doc_num: Optional[int] = None,
        error_code: Optional[str] = None,
        error_source: Optional[str] = None,
        success: Optional[bool] = None,
        detalles_adicionales: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Guarda un log de integración SAP en la base de datos.
        
        Solo guarda logs que tengan información relevante de OC (oc_id, referencia_despacho o proveedor).
        Los logs sin información de OC (inicio/fin del proceso) no se guardan.
        
        Args:
            proceso_id: ID único del proceso (mismo para todas las OCs del mismo request)
            nivel_log: INFO, WARNING, ERROR, DEBUG
            mensaje: Mensaje del log
            usuario: Usuario que ejecutó el proceso
            fuente: Fuente del request (API, WEB, etc.)
            oc_id: UUID de la orden de compra
            referencia_despacho: Referencia del despacho
            proveedor: Código del proveedor
            doc_entry: DocEntry de SAP (si éxito)
            doc_num: DocNum de SAP (si éxito)
            error_code: Código de error de SAP
            error_source: Origen del error (SAP, BACKEND, SAP_CONNECTION)
            success: True si éxito, False si error, None si no aplica
            detalles_adicionales: Diccionario con información adicional (se guarda como JSON)
        """
        # Filtrar logs que no tienen información relevante de OC
        # Solo guardar si al menos uno de estos campos tiene valor
        if not oc_id and not referencia_despacho and not proveedor:
            # Log sin información de OC, no guardar
            logger.debug(f"Log omitido (sin información de OC): {mensaje[:50]}...")
            return
        
        try:
            cursor = self.conn.cursor()
            
            # Convertir detalles_adicionales a JSON string
            detalles_json = None
            if detalles_adicionales:
                try:
                    detalles_json = json.dumps(detalles_adicionales, ensure_ascii=False, default=str)
                except Exception as e:
                    logger.warning(f"No se pudo serializar detalles_adicionales: {e}")
            
            # Convertir UUIDs a string si son UUID objects
            proceso_id_str = None
            if proceso_id:
                if isinstance(proceso_id, uuid.UUID):
                    proceso_id_str = str(proceso_id)
                else:
                    proceso_id_str = str(proceso_id)
            
            oc_id_str = None
            if oc_id:
                if isinstance(oc_id, uuid.UUID):
                    oc_id_str = str(oc_id)
                else:
                    oc_id_str = str(oc_id)
            
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
                datetime.now(),
                nivel_log,
                mensaje,
                usuario,
                fuente,
                oc_id_str,
                referencia_despacho,
                proveedor,
                doc_entry,
                doc_num,
                error_code,
                error_source,
                success,
                detalles_json
            ))
            
            self.conn.commit()
            cursor.close()
            
        except Exception as e:
            # No fallar el proceso principal si falla el guardado del log
            logger.error(f"Error al guardar log de integración SAP: {e}", exc_info=True)
            try:
                self.conn.rollback()
            except Exception:
                pass
    
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
            
            # Construir query base
            where_conditions = []
            params = []
            
            if oc_id:
                where_conditions.append("oc_id = ?")
                params.append(str(oc_id))
            
            if referencia_despacho:
                where_conditions.append("referencia_despacho = ?")
                params.append(referencia_despacho)
            
            if proveedor:
                where_conditions.append("proveedor = ?")
                params.append(proveedor)
            
            if fecha_desde:
                where_conditions.append("timestamp_log >= ?")
                params.append(fecha_desde)
            
            if fecha_hasta:
                where_conditions.append("timestamp_log <= ?")
                params.append(fecha_hasta)
            
            if nivel_log:
                where_conditions.append("nivel_log = ?")
                params.append(nivel_log)
            
            if success is not None:
                where_conditions.append("success = ?")
                params.append(1 if success else 0)
            
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            
            # Query para obtener total
            count_query = f"SELECT COUNT(*) FROM sap_integration_logs WHERE {where_clause}"
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]
            
            # Query para obtener datos
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
                if offset:
                    params.append(offset)
                else:
                    params.append(0)
                params.append(limit)
            
            cursor.execute(data_query, params)
            
            # Obtener columnas
            columns = [column[0] for column in cursor.description]
            
            # Convertir resultados a diccionarios
            logs = []
            for row in cursor.fetchall():
                log_dict = dict(zip(columns, row))
                
                # Parsear detalles_adicionales si es JSON string
                if log_dict.get("detalles_adicionales"):
                    try:
                        log_dict["detalles_adicionales"] = json.loads(log_dict["detalles_adicionales"])
                    except:
                        pass
                
                # Convertir datetime a string ISO
                if log_dict.get("timestamp_log"):
                    if isinstance(log_dict["timestamp_log"], datetime):
                        log_dict["timestamp_log"] = log_dict["timestamp_log"].isoformat()
                
                logs.append(log_dict)
            
            cursor.close()
            
            return {
                "data": logs,
                "total": total
            }
            
        except Exception as e:
            logger.error(f"Error al obtener historial de órdenes: {e}", exc_info=True)
            raise

