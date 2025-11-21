"""
Repositorio para operaciones CRUD de despachos en SQL Server.
"""

import logging
import pyodbc
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class DespachoRepository:
    """Repositorio para operaciones de despacho_cabecera y despacho_detalle."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def find_by_codigo_factura(self, codigo_factura: str) -> Optional[str]:
        """
        Busca un despacho por código de factura.
        
        Args:
            codigo_factura: Código de factura a buscar
            
        Returns:
            despacho_id si existe, None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT despacho_id FROM despacho_cabecera WHERE codigo_factura = ?",
                (codigo_factura,)
            )
            result = cursor.fetchone()
            return str(result[0]) if result else None
        finally:
            cursor.close()
    
    def insert_cabecera(self, datos_cabecera: Dict[str, Any]) -> str:
        """
        Inserta un registro en despacho_cabecera.
        
        Args:
            datos_cabecera: Diccionario con datos de cabecera (sin despacho_id)
            
        Returns:
            despacho_id (UUID) generado
            
        Raises:
            Exception: Si falla la inserción
        """
        cursor = self.conn.cursor()
        
        try:
            # Generar UUID para despacho_id
            despacho_id = str(cursor.execute("SELECT NEWID()").fetchone()[0])
            
            # SQL para insertar
            sql = """
            INSERT INTO despacho_cabecera (
                despacho_id,
                empresa,
                codigo_cliente,
                fecha_despacho,
                codigo_factura,
                anulada,
                numero_pedido_sistema,
                numero_orden,
                numero_factura,
                tipo_documento,
                orden_compra,
                orden_compra_cliente,
                remision_facturada,
                num_id_factura_relacionada,
                codigo_despacho,
                fecha_factura,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
            """
            
            values = (
                despacho_id,
                datos_cabecera["empresa"],
                datos_cabecera["codigo_cliente"],
                datos_cabecera["fecha_despacho"],
                datos_cabecera["codigo_factura"],
                datos_cabecera["anulada"],
                datos_cabecera["numero_pedido_sistema"],
                datos_cabecera["numero_orden"],
                datos_cabecera["numero_factura"],
                datos_cabecera["tipo_documento"],
                datos_cabecera["orden_compra"],
                datos_cabecera["orden_compra_cliente"],
                datos_cabecera["remision_facturada"],
                datos_cabecera["num_id_factura_relacionada"],
                datos_cabecera["codigo_despacho"],
                datos_cabecera["fecha_factura"],
            )
            
            cursor.execute(sql, values)
            self.conn.commit()
            
            logger.debug(f"✅ Despacho cabecera insertado: {despacho_id} - {datos_cabecera['codigo_factura']}")
            return despacho_id
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar despacho_cabecera: {e}")
            logger.error(f"   Factura: {datos_cabecera.get('codigo_factura')}")
            raise
        finally:
            cursor.close()
    
    def insert_detalles(self, despacho_id: str, detalles: List[Dict[str, Any]]) -> int:
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
                detalle_id,
                despacho_id,
                sku,
                cantidad,
                precio_unitario,
                total_linea,
                descuento,
                tipo_linea,
                nombre_producto,
                impuesto,
                reg_num
            ) VALUES (NEWID(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            for detalle in detalles:
                try:
                    values = (
                        despacho_id,
                        detalle["sku"],
                        detalle["cantidad"],
                        detalle["precio_unitario"],
                        detalle["total_linea"],
                        detalle["descuento"],
                        detalle["tipo_linea"],
                        detalle["nombre_producto"],
                        detalle["impuesto"],
                        detalle["reg_num"],
                    )
                    
                    cursor.execute(sql, values)
                    inserted_count += 1
                    logger.debug(f"   → Línea insertada: {detalle['sku']} ({detalle['tipo_linea']})")
                    
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

