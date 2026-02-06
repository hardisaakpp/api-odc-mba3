"""
Repositorio para operaciones de distribución confirmada (FASE 4).
Maneja la redistribución realizada por MABEL TRADING después de la confirmación del proveedor.

CHANGELOG:
- 2026-02-06: Agregado soporte para AuditContext (Buenas Prácticas - Sección 3)
"""

import logging
import pyodbc
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from datetime import datetime
from decimal import Decimal

if TYPE_CHECKING:
    from src.utils.audit_context import AuditContext

logger = logging.getLogger(__name__)


class DistribucionConfirmadaRepository:
    """Repositorio para operaciones de distribución confirmada."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def get_version_actual(self, pedido_id: str) -> int:
        """
        Obtiene la versión actual de la redistribución para un pedido.
        
        Args:
            pedido_id: UUID del pedido
            
        Returns:
            Versión actual (1 si no existe ninguna)
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT MAX(version) 
                FROM distribucion_confirmada 
                WHERE pedido_id = ?
            """, (pedido_id,))
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else 0
        except Exception as e:
            logger.error(f"❌ Error al obtener versión actual: {e}", exc_info=True)
            return 0
    
    def get_distribucion_completa(
        self, 
        pedido_id: str, 
        version: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Obtiene la distribución completa de un pedido.
        
        Args:
            pedido_id: UUID del pedido
            version: Versión específica (si None, obtiene la última)
            
        Returns:
            Diccionario con la estructura completa de distribución
        """
        cursor = self.conn.cursor()
        
        try:
            # Si no se especifica versión, obtener la última
            if version is None:
                version = self.get_version_actual(pedido_id)
                if version == 0:
                    return {
                        "pedido_id": pedido_id,
                        "version_actual": 0,
                        "productos": []
                    }
            
            # Verificar si existe columna es_bodega en pedido_detalle_tienda para obtener info de bodegas
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido_detalle_tienda' 
                AND COLUMN_NAME = 'es_bodega'
            """)
            row_check = cursor.fetchone()
            tiene_es_bodega = (row_check[0] if row_check else 0) > 0
            
            # Obtener todas las distribuciones confirmadas (con información de bodegas si existe)
            if tiene_es_bodega:
                cursor.execute("""
                    SELECT 
                        dc.id,
                        dc.pedido_detalle_id,
                        dc.tienda_id,
                        t.codigo AS tienda_codigo,
                        t.nombre AS tienda_nombre,
                        dc.cantidad_solicitada,
                        dc.cantidad_confirmada,
                        dc.cantidad_asignada,
                        dc.costo_unitario_original,
                        dc.costo_unitario_ajustado,
                        dc.subtotal_original,
                        dc.subtotal_ajustado,
                        dc.version,
                        dc.estado,
                        dc.fecha_creacion,
                        dc.fecha_modificacion,
                        ISNULL(pdt.es_bodega, 0) AS es_bodega
                    FROM distribucion_confirmada dc
                    INNER JOIN tienda t ON dc.tienda_id = t.tienda_id
                    LEFT JOIN pedido_detalle_tienda pdt 
                        ON dc.pedido_detalle_id = pdt.pedido_detalle_id 
                        AND dc.tienda_id = pdt.tienda_id
                    WHERE dc.pedido_id = ? AND dc.version = ?
                    ORDER BY dc.pedido_detalle_id, t.codigo
                """, (pedido_id, version))
            else:
                cursor.execute("""
                    SELECT 
                        dc.id,
                        dc.pedido_detalle_id,
                        dc.tienda_id,
                        t.codigo AS tienda_codigo,
                        t.nombre AS tienda_nombre,
                        dc.cantidad_solicitada,
                        dc.cantidad_confirmada,
                        dc.cantidad_asignada,
                        dc.costo_unitario_original,
                        dc.costo_unitario_ajustado,
                        dc.subtotal_original,
                        dc.subtotal_ajustado,
                        dc.version,
                        dc.estado,
                        dc.fecha_creacion,
                        dc.fecha_modificacion,
                        0 AS es_bodega
                    FROM distribucion_confirmada dc
                    INNER JOIN tienda t ON dc.tienda_id = t.tienda_id
                    WHERE dc.pedido_id = ? AND dc.version = ?
                    ORDER BY dc.pedido_detalle_id, t.codigo
                """, (pedido_id, version))
            
            rows = cursor.fetchall()
            
            # Agrupar por producto
            productos_dict = {}
            for row in rows:
                pedido_detalle_id = str(row[1])
                
                if pedido_detalle_id not in productos_dict:
                    productos_dict[pedido_detalle_id] = {
                        "pedido_detalle_id": pedido_detalle_id,
                        "distribuciones": []
                    }
                
                # Convertir Decimal a float para JSON
                costo_unitario_original = float(row[9]) if row[9] is not None else None
                costo_unitario_ajustado = float(row[10]) if row[10] is not None else None
                subtotal_original = float(row[11]) if row[11] is not None else None
                subtotal_ajustado = float(row[12]) if row[12] is not None else None
                # Convertir SQL Server bit (0 o 1) a Python bool
                es_bodega = bool(row[16]) if tiene_es_bodega else False
                
                productos_dict[pedido_detalle_id]["distribuciones"].append({
                    "id": str(row[0]),
                    "pedido_detalle_id": pedido_detalle_id,
                    "tienda_id": str(row[2]),
                    "tienda_codigo": row[3],
                    "tienda_nombre": row[4],
                    "cantidad_solicitada": row[5],
                    "cantidad_confirmada": row[6],
                    "cantidad_asignada": row[7],
                    "costo_unitario_original": costo_unitario_original,
                    "costo_unitario_ajustado": costo_unitario_ajustado,
                    "subtotal_original": subtotal_original,
                    "subtotal_ajustado": subtotal_ajustado,
                    "version": row[12],
                    "estado": row[13],
                    "fecha_creacion": row[14].isoformat() if row[14] else None,
                    "fecha_modificacion": row[15].isoformat() if row[15] else None,
                    "es_bodega": es_bodega  # ⭐ NUEVO: Incluir flag de bodega
                })
            
            # Obtener totales de fuente de verdad (respuesta proveedor) para que
            # cantidad_solicitada_total y cantidad_confirmada_total no cambien por redondeo
            cursor.execute("""
                SELECT
                    rpd.pedido_detalle_id,
                    rpd.cantidad_solicitada_total,
                    rpd.cantidad_confirmada_total
                FROM pedido_respuesta_proveedor_detalle rpd
                INNER JOIN pedido_respuesta_proveedor rp ON rpd.respuesta_id = rp.respuesta_id
                WHERE rp.pedido_id = ?
                AND rp.respuesta_id = (
                    SELECT TOP 1 respuesta_id
                    FROM pedido_respuesta_proveedor
                    WHERE pedido_id = ?
                    ORDER BY version DESC, fecha_respuesta DESC
                )
            """, (pedido_id, pedido_id))
            respuestas_proveedor = {}
            for row in cursor.fetchall():
                respuestas_proveedor[str(row[0])] = {
                    "cantidad_solicitada_total": int(row[1]) if row[1] is not None else 0,
                    "cantidad_confirmada_total": int(row[2]) if row[2] is not None else 0,
                }
            
            # Calcular totales por producto (usar fuente de verdad para solicitada/confirmada)
            productos = []
            for pedido_detalle_id, producto_data in productos_dict.items():
                distribuciones = producto_data["distribuciones"]
                respuesta = respuestas_proveedor.get(pedido_detalle_id, {})
                cantidad_solicitada_total = respuesta.get("cantidad_solicitada_total")
                cantidad_confirmada_total = respuesta.get("cantidad_confirmada_total")
                if cantidad_solicitada_total is None:
                    cantidad_solicitada_total = sum(d["cantidad_solicitada"] for d in distribuciones)
                if cantidad_confirmada_total is None:
                    cantidad_confirmada_total = sum(d["cantidad_confirmada"] for d in distribuciones)
                cantidad_asignada_total = sum(d["cantidad_asignada"] for d in distribuciones)
                
                productos.append({
                    "pedido_detalle_id": pedido_detalle_id,
                    "cantidad_solicitada_total": cantidad_solicitada_total,
                    "cantidad_confirmada_total": cantidad_confirmada_total,
                    "cantidad_asignada_total": cantidad_asignada_total,
                    "distribuciones": distribuciones
                })
            
            return {
                "pedido_id": pedido_id,
                "version_actual": version,
                "productos": productos
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener distribución completa: {e}", exc_info=True)
            raise
    
    def crear_redistribucion(
        self,
        pedido_id: str,
        productos_redistribucion: List[Dict[str, Any]],
        usuario: Optional[str] = None,
        audit_context: Optional["AuditContext"] = None
    ) -> Dict[str, Any]:
        """
        Crea una nueva versión de redistribución.
        
        Args:
            pedido_id: UUID del pedido
            productos_redistribucion: Lista de productos con sus redistribuciones
                Formato: [{
                    "pedido_detalle_id": "...",
                    "distribuciones": [{"tienda_id": "...", "cantidad_asignada": 10}, ...]
                }, ...]
            usuario: Usuario que realiza la redistribución (deprecated, usar audit_context)
            audit_context: Contexto de auditoría opcional (Buenas Prácticas - Sección 3)
            
        Returns:
            Diccionario con el resultado de la operación
        """
        # Priorizar audit_context sobre usuario para campos de auditoría
        creado_por = usuario
        origen = None
        ip_origen = None
        if audit_context:
            creado_por = audit_context.get_creado_por()
            origen = audit_context.origen
            ip_origen = audit_context.ip_origen
        cursor = self.conn.cursor()
        
        try:
            # Obtener versión actual y crear nueva
            version_actual = self.get_version_actual(pedido_id)
            nueva_version = version_actual + 1
            
            # Obtener datos originales del pedido (cantidades solicitadas y confirmadas)
            # Primero, obtener la respuesta del proveedor más reciente
            cursor.execute("""
                SELECT TOP 1 rpd.pedido_detalle_id, rpd.cantidad_solicitada_total, rpd.cantidad_confirmada_total
                FROM pedido_respuesta_proveedor_detalle rpd
                INNER JOIN pedido_respuesta_proveedor rp ON rpd.respuesta_id = rp.respuesta_id
                WHERE rp.pedido_id = ?
                ORDER BY rp.version DESC, rp.fecha_respuesta DESC
            """, (pedido_id,))
            
            respuestas_proveedor = {}
            for row in cursor.fetchall():
                respuestas_proveedor[str(row[0])] = {
                    "cantidad_solicitada_total": row[1],
                    "cantidad_confirmada_total": row[2]
                }
            
            # Obtener distribuciones originales por producto y tienda (incluyendo es_bodega)
            # Verificar si existe columna es_bodega
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido_detalle_tienda' 
                AND COLUMN_NAME = 'es_bodega'
            """)
            row_check = cursor.fetchone()
            tiene_es_bodega = (row_check[0] if row_check else 0) > 0
            
            if tiene_es_bodega:
                cursor.execute("""
                    SELECT 
                        pdt.pedido_detalle_id,
                        pdt.tienda_id,
                        pdt.cantidad AS cantidad_solicitada,
                        pd.costo_doc_sin_iva,
                        pdt.es_bodega
                    FROM pedido_detalle_tienda pdt
                    INNER JOIN pedido_detalle pd ON pdt.pedido_detalle_id = pd.pedido_detalle_id
                    WHERE pd.pedido_id = ?
                """, (pedido_id,))
            else:
                cursor.execute("""
                    SELECT 
                        pdt.pedido_detalle_id,
                        pdt.tienda_id,
                        pdt.cantidad AS cantidad_solicitada,
                        pd.costo_doc_sin_iva,
                        0 AS es_bodega
                    FROM pedido_detalle_tienda pdt
                    INNER JOIN pedido_detalle pd ON pdt.pedido_detalle_id = pd.pedido_detalle_id
                    WHERE pd.pedido_id = ?
                """, (pedido_id,))
            
            distribuciones_originales = {}
            for row in cursor.fetchall():
                pedido_detalle_id = str(row[0])
                tienda_id = str(row[1])
                if pedido_detalle_id not in distribuciones_originales:
                    distribuciones_originales[pedido_detalle_id] = {}
                # Convertir SQL Server bit (0 o 1) a Python bool
                es_bodega = bool(row[4]) if tiene_es_bodega else False
                distribuciones_originales[pedido_detalle_id][tienda_id] = {
                    "cantidad_solicitada": row[2],
                    "costo_unitario": float(row[3]) if row[3] is not None else None,
                    "es_bodega": es_bodega  # ⭐ NUEVO: Incluir flag de bodega
                }
            
            # Insertar nuevas distribuciones confirmadas
            distribuciones_insertadas = 0
            fecha_creacion = datetime.now()
            
            for producto in productos_redistribucion:
                pedido_detalle_id = producto["pedido_detalle_id"]
                
                # Obtener cantidades confirmadas del proveedor
                respuesta = respuestas_proveedor.get(pedido_detalle_id, {})
                cantidad_confirmada_total = respuesta.get("cantidad_confirmada_total", 0)
                
                # Obtener distribuciones originales de este producto
                distribuciones_orig = distribuciones_originales.get(pedido_detalle_id, {})
                
                # Calcular proporción de confirmación (si hay confirmación parcial)
                cantidad_solicitada_total = respuesta.get("cantidad_solicitada_total", 0)
                factor_proporcion = (
                    cantidad_confirmada_total / cantidad_solicitada_total 
                    if cantidad_solicitada_total > 0 else 1.0
                )
                
                for distribucion in producto["distribuciones"]:
                    tienda_id = distribucion["tienda_id"]
                    cantidad_asignada = distribucion["cantidad_asignada"]
                    
                    # Obtener datos originales de esta tienda
                    distrib_orig = distribuciones_orig.get(tienda_id, {})
                    cantidad_solicitada = distrib_orig.get("cantidad_solicitada", 0)
                    costo_unitario_original = distrib_orig.get("costo_unitario")
                    
                    # Calcular cantidad confirmada proporcional
                    cantidad_confirmada = int(cantidad_solicitada * factor_proporcion) if cantidad_solicitada > 0 else 0
                    
                    # Calcular costos
                    costo_unitario_ajustado = costo_unitario_original
                    subtotal_original = (
                        float(costo_unitario_original * cantidad_solicitada) 
                        if costo_unitario_original is not None else None
                    )
                    subtotal_ajustado = (
                        float(costo_unitario_ajustado * cantidad_asignada) 
                        if costo_unitario_ajustado is not None else None
                    )
                    
                    # Insertar distribución confirmada
                    cursor.execute("""
                        INSERT INTO distribucion_confirmada (
                            pedido_id,
                            pedido_detalle_id,
                            tienda_id,
                            cantidad_solicitada,
                            cantidad_confirmada,
                            cantidad_asignada,
                            costo_unitario_original,
                            costo_unitario_ajustado,
                            subtotal_original,
                            subtotal_ajustado,
                            version,
                            estado,
                            creado_por,
                            origen,
                            ip_origen,
                            fecha_creacion
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE', ?, ?, ?, ?)
                    """, (
                        pedido_id,
                        pedido_detalle_id,
                        tienda_id,
                        cantidad_solicitada,
                        cantidad_confirmada,
                        cantidad_asignada,
                        costo_unitario_original,
                        costo_unitario_ajustado,
                        subtotal_original,
                        subtotal_ajustado,
                        nueva_version,
                        creado_por,
                        origen,
                        ip_origen,
                        fecha_creacion
                    ))
                    
                    distribuciones_insertadas += 1
            
            self.conn.commit()
            
            logger.info(f"✅ Redistribución creada: pedido_id={pedido_id}, version={nueva_version}, distribuciones={distribuciones_insertadas}")
            
            return {
                "success": True,
                "pedido_id": pedido_id,
                "version": nueva_version,
                "distribuciones_insertadas": distribuciones_insertadas,
                "mensaje": f"Redistribución creada exitosamente (versión {nueva_version})"
            }
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al crear redistribución: {e}", exc_info=True)
            raise
    
    def confirmar_redistribucion(
        self,
        pedido_id: str,
        version: Optional[int] = None,
        usuario: Optional[str] = None,
        audit_context: Optional["AuditContext"] = None
    ) -> Dict[str, Any]:
        """
        Confirma una redistribución, cambiando su estado a 'CONFIRMADO'.
        
        Args:
            pedido_id: UUID del pedido
            version: Versión a confirmar (si None, confirma la última)
            usuario: Usuario que confirma (deprecated, usar audit_context)
            audit_context: Contexto de auditoría opcional (Buenas Prácticas - Sección 3)
            
        Returns:
            Diccionario con el resultado de la operación
        """
        cursor = self.conn.cursor()
        
        # Priorizar audit_context sobre usuario
        modificado_por = usuario
        if audit_context:
            modificado_por = audit_context.get_modificado_por()
        
        try:
            if version is None:
                version = self.get_version_actual(pedido_id)
            
            if version == 0:
                raise ValueError("No existe ninguna redistribución para confirmar")
            
            # Actualizar estado de todas las distribuciones de esta versión
            fecha_modificacion = datetime.now()
            cursor.execute("""
                UPDATE distribucion_confirmada
                SET estado = 'CONFIRMADO',
                    modificado_por = ?,
                    fecha_modificacion = ?
                WHERE pedido_id = ? AND version = ?
            """, (modificado_por, fecha_modificacion, pedido_id, version))
            
            rows_affected = cursor.rowcount
            
            # Nota: El estado del pedido se actualiza externamente según el contexto
            # - Si se llama desde el endpoint interno: 'REDISTRIBUIDO'
            # - Si se llama desde el frontend (MABEL TRADING): 'CONFIRMADO REDISTRIBUCION'
            # Por eso no actualizamos el estado aquí, se hace en el endpoint
            
            self.conn.commit()
            
            logger.info(f"✅ Redistribución confirmada: pedido_id={pedido_id}, version={version}")
            
            return {
                "success": True,
                "pedido_id": pedido_id,
                "version_confirmada": version,
                "distribuciones_actualizadas": rows_affected,
                "mensaje": f"Redistribución versión {version} confirmada exitosamente"
            }
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al confirmar redistribución: {e}", exc_info=True)
            raise
    
    def calcular_diferencias(
        self,
        pedido_id: str,
        version: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Calcula las diferencias entre cantidades solicitadas, confirmadas y asignadas.
        
        Args:
            pedido_id: UUID del pedido
            version: Versión a analizar (si None, analiza la última)
            
        Returns:
            Diccionario con diferencias por producto, tienda y totales
        """
        cursor = self.conn.cursor()
        
        try:
            if version is None:
                version = self.get_version_actual(pedido_id)
            
            if version == 0:
                return {
                    "pedido_id": pedido_id,
                    "version": 0,
                    "total_productos": 0,
                    "diferencias_productos": [],
                    "diferencias_tiendas": [],
                    "totales": {}
                }
            
            # Obtener diferencias por producto
            cursor.execute("""
                SELECT 
                    dc.pedido_detalle_id,
                    pd.codigo_interno,
                    pd.descripcion_sap,
                    SUM(dc.cantidad_solicitada) AS total_solicitada,
                    SUM(dc.cantidad_confirmada) AS total_confirmada,
                    SUM(dc.cantidad_asignada) AS total_asignada,
                    MAX(dc.costo_unitario_original) AS costo_unitario_original,
                    MAX(dc.costo_unitario_ajustado) AS costo_unitario_ajustado,
                    SUM(dc.subtotal_original) AS subtotal_original,
                    SUM(dc.subtotal_ajustado) AS subtotal_ajustado
                FROM distribucion_confirmada dc
                INNER JOIN pedido_detalle pd ON dc.pedido_detalle_id = pd.pedido_detalle_id
                WHERE dc.pedido_id = ? AND dc.version = ?
                GROUP BY dc.pedido_detalle_id, pd.codigo_interno, pd.descripcion_sap
                ORDER BY pd.codigo_interno
            """, (pedido_id, version))
            
            diferencias_productos = []
            for row in cursor.fetchall():
                cantidad_solicitada = row[3]
                cantidad_confirmada = row[4]
                cantidad_asignada = row[5]
                diferencia_cantidad = cantidad_asignada - cantidad_confirmada
                
                # Índices según el SELECT:
                # 6: costo_unitario_original
                # 7: costo_unitario_ajustado
                # 8: subtotal_original
                # 9: subtotal_ajustado
                subtotal_original = float(row[8]) if row[8] is not None else None
                subtotal_ajustado = float(row[9]) if row[9] is not None else None
                diferencia_costo = (
                    subtotal_ajustado - subtotal_original 
                    if subtotal_ajustado is not None and subtotal_original is not None 
                    else None
                )
                
                diferencias_productos.append({
                    "pedido_detalle_id": str(row[0]),
                    "codigo_interno": row[1],
                    "descripcion_sap": row[2],
                    "cantidad_solicitada": cantidad_solicitada,
                    "cantidad_confirmada": cantidad_confirmada,
                    "cantidad_asignada": cantidad_asignada,
                    "diferencia_cantidad": diferencia_cantidad,
                    "costo_unitario_original": float(row[6]) if row[6] is not None else None,
                    "costo_unitario_ajustado": float(row[7]) if row[7] is not None else None,
                    "subtotal_original": subtotal_original,
                    "subtotal_ajustado": subtotal_ajustado,
                    "diferencia_costo": diferencia_costo
                })
            
            # Obtener diferencias por tienda
            cursor.execute("""
                SELECT 
                    dc.tienda_id,
                    t.codigo AS tienda_codigo,
                    t.nombre AS tienda_nombre,
                    SUM(dc.cantidad_solicitada) AS total_solicitada,
                    SUM(dc.cantidad_confirmada) AS total_confirmada,
                    SUM(dc.cantidad_asignada) AS total_asignada
                FROM distribucion_confirmada dc
                INNER JOIN tienda t ON dc.tienda_id = t.tienda_id
                WHERE dc.pedido_id = ? AND dc.version = ?
                GROUP BY dc.tienda_id, t.codigo, t.nombre
                ORDER BY t.codigo
            """, (pedido_id, version))
            
            diferencias_tiendas = []
            for row in cursor.fetchall():
                cantidad_solicitada = row[3]
                cantidad_confirmada = row[4]
                cantidad_asignada = row[5]
                diferencia_cantidad = cantidad_asignada - cantidad_confirmada
                
                diferencias_tiendas.append({
                    "tienda_id": str(row[0]),
                    "tienda_codigo": row[1],
                    "tienda_nombre": row[2],
                    "cantidad_solicitada": cantidad_solicitada,
                    "cantidad_confirmada": cantidad_confirmada,
                    "cantidad_asignada": cantidad_asignada,
                    "diferencia_cantidad": diferencia_cantidad
                })
            
            # Calcular totales
            total_cantidad_solicitada = sum(p["cantidad_solicitada"] for p in diferencias_productos)
            total_cantidad_confirmada = sum(p["cantidad_confirmada"] for p in diferencias_productos)
            total_cantidad_asignada = sum(p["cantidad_asignada"] for p in diferencias_productos)
            total_diferencia_cantidad = total_cantidad_asignada - total_cantidad_confirmada
            
            total_costo_original = sum(
                p["subtotal_original"] for p in diferencias_productos 
                if p["subtotal_original"] is not None
            ) or None
            
            total_costo_ajustado = sum(
                p["subtotal_ajustado"] for p in diferencias_productos 
                if p["subtotal_ajustado"] is not None
            ) or None
            
            total_diferencia_costo = (
                total_costo_ajustado - total_costo_original 
                if total_costo_ajustado is not None and total_costo_original is not None 
                else None
            )
            
            return {
                "pedido_id": pedido_id,
                "version": version,
                "total_productos": len(diferencias_productos),
                "total_cantidad_solicitada": total_cantidad_solicitada,
                "total_cantidad_confirmada": total_cantidad_confirmada,
                "total_cantidad_asignada": total_cantidad_asignada,
                "total_diferencia_cantidad": total_diferencia_cantidad,
                "total_costo_original": total_costo_original,
                "total_costo_ajustado": total_costo_ajustado,
                "total_diferencia_costo": total_diferencia_costo,
                "diferencias_productos": diferencias_productos,
                "diferencias_tiendas": diferencias_tiendas
            }
            
        except Exception as e:
            logger.error(f"❌ Error al calcular diferencias: {e}", exc_info=True)
            raise
