"""
Repositorio para operaciones de procesamiento SAP de pedidos.
Almacena información SAP procesada cuando MT confirma la redistribución.
"""

import logging
import pyodbc
from typing import Dict, Any, List, Optional
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)


class PedidoSAPProcesamientoRepository:
    """Repositorio para operaciones de procesamiento SAP de pedidos."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def find_by_pedido_detalle_id(self, pedido_detalle_id: str) -> Optional[str]:
        """
        Busca si ya existe un procesamiento para un pedido_detalle_id.
        
        Args:
            pedido_detalle_id: UUID del pedido_detalle
            
        Returns:
            procesamiento_id si existe, None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT procesamiento_detalle_id
                FROM pedido_sap_procesamiento_detalle
                WHERE pedido_detalle_id = ?
            """, (pedido_detalle_id,))
            row = cursor.fetchone()
            return str(row[0]) if row and row[0] else None
        except Exception as e:
            logger.error(f"❌ Error al buscar procesamiento: {e}", exc_info=True)
            return None
        finally:
            cursor.close()
    
    def insert_procesamiento(self, datos: Dict[str, Any]) -> str:
        """
        Inserta un nuevo procesamiento SAP.
        
        Args:
            datos: Diccionario con datos del procesamiento (sin procesamiento_id)
            
        Returns:
            procesamiento_id (UUID) generado
        """
        cursor = self.conn.cursor()
        try:
            # ✅ CORRECCIÓN: Usar OUTPUT INSERTED para obtener el GUID generado
            # ✅ CORRECCIÓN: Nombre correcto de la tabla: pedido_sap_procesamiento_detalle
            cursor.execute("""
                INSERT INTO pedido_sap_procesamiento_detalle (
                    pedido_id,
                    pedido_detalle_id,
                    descripcion_producto,
                    item_code_sap,
                    pack_sap,
                    unidad_conversion,
                    unidad_sap,
                    cantidad_original,
                    cantidad_sap,
                    precio_unitario_original,
                    precio_unitario_sap,
                    total_linea_original,
                    total_linea_sap,
                    producto_homologado,
                    tipo_problema,
                    item_code_sap_encontrado,
                    mensaje_error,
                    procesado_por
                )
                OUTPUT INSERTED.procesamiento_detalle_id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datos.get("pedido_id"),
                datos.get("pedido_detalle_id"),
                datos.get("descripcion_producto"),
                datos.get("item_code_sap"),
                datos.get("pack_sap"),
                datos.get("unidad_conversion"),
                datos.get("unidad_sap"),
                datos.get("cantidad_original"),
                datos.get("cantidad_sap"),
                datos.get("precio_unitario_original"),
                datos.get("precio_unitario_sap"),
                datos.get("total_linea_original"),
                datos.get("total_linea_sap"),
                datos.get("producto_homologado", True),
                datos.get("tipo_problema"),
                datos.get("item_code_sap_encontrado"),
                datos.get("mensaje_error"),
                datos.get("procesado_por")
            ))
            
            # Obtener el ID generado desde OUTPUT INSERTED
            row = cursor.fetchone()
            procesamiento_detalle_id = str(row[0]) if row and row[0] else None
            
            if not procesamiento_detalle_id:
                raise ValueError("No se pudo obtener el ID del procesamiento insertado")
            
            self.conn.commit()
            logger.info(f"✅ Procesamiento SAP detalle insertado: {procesamiento_detalle_id}")
            return procesamiento_detalle_id
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar procesamiento SAP: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def update_procesamiento(self, procesamiento_detalle_id: str, datos: Dict[str, Any]) -> bool:
        """
        Actualiza un procesamiento SAP existente.
        
        Args:
            procesamiento_detalle_id: UUID del procesamiento detalle
            datos: Diccionario con datos a actualizar
            
        Returns:
            True si se actualizó correctamente
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                UPDATE pedido_sap_procesamiento_detalle
                SET
                    descripcion_producto = ?,
                    item_code_sap = ?,
                    pack_sap = ?,
                    unidad_conversion = ?,
                    unidad_sap = ?,
                    cantidad_original = ?,
                    cantidad_sap = ?,
                    precio_unitario_original = ?,
                    precio_unitario_sap = ?,
                    total_linea_original = ?,
                    total_linea_sap = ?,
                    producto_homologado = ?,
                    tipo_problema = ?,
                    item_code_sap_encontrado = ?,
                    mensaje_error = ?,
                    fecha_procesamiento = GETDATE(),
                    procesado_por = ?
                WHERE procesamiento_detalle_id = ?
            """, (
                datos.get("descripcion_producto"),
                datos.get("item_code_sap"),
                datos.get("pack_sap"),
                datos.get("unidad_conversion"),
                datos.get("unidad_sap"),
                datos.get("cantidad_original"),
                datos.get("cantidad_sap"),
                datos.get("precio_unitario_original"),
                datos.get("precio_unitario_sap"),
                datos.get("total_linea_original"),
                datos.get("total_linea_sap"),
                datos.get("producto_homologado", True),
                datos.get("tipo_problema"),
                datos.get("item_code_sap_encontrado"),
                datos.get("mensaje_error"),
                datos.get("procesado_por"),
                procesamiento_detalle_id
            ))
            
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.debug(f"✅ Procesamiento SAP detalle actualizado: {procesamiento_detalle_id}")
                return True
            else:
                logger.warning(f"⚠️ No se actualizó ningún registro: {procesamiento_detalle_id}")
                return False
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar procesamiento SAP: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def upsert_procesamiento(self, datos: Dict[str, Any]) -> str:
        """
        Inserta o actualiza un procesamiento SAP (UPSERT).
        
        Args:
            datos: Diccionario con datos del procesamiento
            
        Returns:
            procesamiento_id (UUID)
        """
        pedido_detalle_id = datos.get("pedido_detalle_id")
        if not pedido_detalle_id:
            raise ValueError("pedido_detalle_id es requerido")
        
        # Buscar si ya existe
        existing_id = self.find_by_pedido_detalle_id(pedido_detalle_id)
        
        if existing_id:
            # Actualizar
            self.update_procesamiento(existing_id, datos)
            return existing_id
        else:
            # Insertar
            return self.insert_procesamiento(datos)
    
    def get_procesamientos_por_pedido(self, pedido_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene todos los procesamientos SAP de un pedido.
        
        Args:
            pedido_id: UUID del pedido
            
        Returns:
            Lista de diccionarios con información de procesamiento
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT 
                    ps.procesamiento_detalle_id,
                    ps.pedido_id,
                    ps.pedido_detalle_id,
                    pd.codigo_interno,
                    ps.descripcion_producto,
                    ps.item_code_sap,
                    ps.pack_sap,
                    ps.unidad_conversion,
                    ps.unidad_sap,
                    ps.cantidad_original,
                    ps.cantidad_sap,
                    ps.precio_unitario_original,
                    ps.precio_unitario_sap,
                    ps.total_linea_original,
                    ps.total_linea_sap,
                    ps.producto_homologado,
                    ps.tipo_problema,
                    ps.item_code_sap_encontrado,
                    ps.mensaje_error,
                    ps.fecha_procesamiento,
                    ps.procesado_por
                FROM pedido_sap_procesamiento_detalle ps
                INNER JOIN pedido_detalle pd ON ps.pedido_detalle_id = pd.pedido_detalle_id
                WHERE ps.pedido_id = ?
                ORDER BY pd.codigo_interno
            """, (pedido_id,))
            
            resultados = []
            for row in cursor.fetchall():
                resultados.append({
                    "procesamiento_detalle_id": str(row[0]),
                    "pedido_id": str(row[1]),
                    "pedido_detalle_id": str(row[2]),
                    "codigo_interno": row[3],
                    "descripcion_producto": row[4],
                    "item_code_sap": row[5],
                    "pack_sap": row[6],
                    "unidad_conversion": float(row[7]) if row[7] else None,
                    "unidad_sap": row[8],
                    "cantidad_original": float(row[9]) if row[9] else None,
                    "cantidad_sap": float(row[10]) if row[10] else None,
                    "precio_unitario_original": float(row[11]) if row[11] else None,
                    "precio_unitario_sap": float(row[12]) if row[12] else None,
                    "total_linea_original": float(row[13]) if row[13] else None,
                    "total_linea_sap": float(row[14]) if row[14] else None,
                    "producto_homologado": bool(row[15]) if row[15] is not None else True,
                    "tipo_problema": row[16],
                    "item_code_sap_encontrado": row[17],
                    "mensaje_error": row[18],
                    "fecha_procesamiento": row[19],
                    "procesado_por": row[20]
                })
            
            return resultados
            
        except Exception as e:
            logger.error(f"❌ Error al obtener procesamientos: {e}", exc_info=True)
            return []
        finally:
            cursor.close()
    
    def get_productos_no_homologados_por_pedido(self, pedido_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene productos no homologados de un pedido.
        
        Args:
            pedido_id: UUID del pedido
            
        Returns:
            Lista de productos no homologados
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT 
                    ps.procesamiento_detalle_id,
                    ps.pedido_detalle_id,
                    pd.codigo_interno,
                    pd.descripcion_sap,
                    ps.tipo_problema,
                    ps.item_code_sap_encontrado,
                    ps.mensaje_error,
                    ps.fecha_procesamiento
                FROM pedido_sap_procesamiento_detalle ps
                INNER JOIN pedido_detalle pd ON ps.pedido_detalle_id = pd.pedido_detalle_id
                WHERE ps.pedido_id = ? 
                    AND ps.producto_homologado = 0
                ORDER BY pd.codigo_interno
            """, (pedido_id,))
            
            resultados = []
            for row in cursor.fetchall():
                resultados.append({
                    "procesamiento_detalle_id": str(row[0]),
                    "pedido_detalle_id": str(row[1]),
                    "codigo_interno": row[2],
                    "descripcion_sap": row[3],
                    "tipo_problema": row[4],
                    "item_code_sap_encontrado": row[5],
                    "mensaje_error": row[6],
                    "fecha_procesamiento": row[7]
                })
            
            return resultados
            
        except Exception as e:
            logger.error(f"❌ Error al obtener productos no homologados: {e}", exc_info=True)
            return []
        finally:
            cursor.close()
