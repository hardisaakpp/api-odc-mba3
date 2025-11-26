"""
Repositorio para operaciones CRUD de órdenes de compra en SQL Server.
"""

import logging
import pyodbc
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class OrdenCompraRepository:
    """Repositorio para operaciones de orden_compra_cabecera y orden_compra_detalle."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def get_proveedor_from_cliente(self, empresa: str) -> Optional[str]:
        """
        Obtiene el CardCode (proveedor) desde la tabla cliente basado en empresa.
        
        Si empresa ≠ CardCode SAP, busca en la tabla cliente el mapeo.
        La tabla cliente puede tener diferentes estructuras, así que intenta varias opciones.
        
        Args:
            empresa: Nombre de la empresa
            
        Returns:
            CardCode (proveedor) si se encuentra, empresa si no existe mapeo
        """
        if not empresa:
            return None
        
        cursor = self.conn.cursor()
        try:
            # Intentar diferentes estructuras de tabla cliente
            # Opción 1: Tabla con campo 'empresa' y 'CardCode'
            try:
                cursor.execute(
                    """
                    SELECT TOP 1 CardCode
                    FROM cliente
                    WHERE empresa = ? OR CardCode = ?
                    """,
                    (empresa, empresa)
                )
                result = cursor.fetchone()
                if result and result[0]:
                    logger.debug(f"✅ Mapeo encontrado en cliente: {empresa} → {result[0]}")
                    return result[0]
            except Exception:
                pass
            
            # Opción 2: Tabla con campo 'nombre' o 'razon_social' y 'CardCode'
            try:
                cursor.execute(
                    """
                    SELECT TOP 1 CardCode
                    FROM cliente
                    WHERE (nombre = ? OR razon_social = ? OR CardName = ?) OR CardCode = ?
                    """,
                    (empresa, empresa, empresa, empresa)
                )
                result = cursor.fetchone()
                if result and result[0]:
                    logger.debug(f"✅ Mapeo encontrado en cliente (nombre): {empresa} → {result[0]}")
                    return result[0]
            except Exception:
                pass
            
            # Si no se encuentra mapeo, retornar la empresa misma
            # (puede ser que ya sea el CardCode o que la tabla no exista)
            logger.debug(f"ℹ️ No se encontró mapeo para empresa '{empresa}', usando empresa como proveedor")
            return empresa
            
        except Exception as e:
            logger.warning(f"⚠️ Error al buscar proveedor en tabla cliente: {e}")
            # Si hay error, retornar empresa como fallback
            return empresa
        finally:
            cursor.close()
    
    def insert_cabecera(self, datos_cabecera: Dict[str, Any]) -> str:
        """
        Inserta un registro en orden_compra_cabecera.
        
        Args:
            datos_cabecera: Diccionario con datos de cabecera (sin oc_id)
            
        Returns:
            oc_id (UUID) generado
            
        Raises:
            Exception: Si falla la inserción
        """
        cursor = self.conn.cursor()
        
        try:
            # Generar UUID para oc_id
            oc_id = str(cursor.execute("SELECT NEWID()").fetchone()[0])
            
            # SQL para insertar (estructura real de la tabla)
            sql = """
            INSERT INTO orden_compra_cabecera (
                oc_id,
                despacho_id,
                proveedor,
                fecha_generacion,
                referencia_despacho,
                created_at
            ) VALUES (?, ?, ?, ?, ?, GETDATE())
            """
            
            values = (
                oc_id,
                datos_cabecera.get("despacho_id"),
                datos_cabecera.get("proveedor"),
                datos_cabecera.get("fecha_generacion"),
                datos_cabecera.get("referencia_despacho"),
            )
            
            cursor.execute(sql, values)
            self.conn.commit()
            
            logger.debug(f"✅ Orden compra cabecera insertada: {oc_id} - Despacho: {datos_cabecera.get('despacho_id')}")
            return oc_id
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar orden_compra_cabecera: {e}")
            logger.error(f"   Despacho ID: {datos_cabecera.get('despacho_id')}")
            raise
        finally:
            cursor.close()
    
    def insert_detalles(self, oc_id: str, detalles: List[Dict[str, Any]]) -> int:
        """
        Inserta múltiples líneas de detalle en orden_compra_detalle.
        
        Args:
            oc_id: UUID de la cabecera de orden de compra
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
            INSERT INTO orden_compra_detalle (
                oc_detalle_id,
                oc_id,
                sku_sap,
                cantidad_sap,
                unidad_sap,
                referencia_detalle,
                precio_unitario,
                total_linea,
                cantidad_origen
            ) VALUES (NEWID(), ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            for detalle in detalles:
                try:
                    values = (
                        oc_id,
                        detalle.get("sku_sap"),
                        detalle.get("cantidad_sap"),
                        detalle.get("unidad_sap"),
                        detalle.get("referencia_detalle"),
                        detalle.get("precio_unitario"),
                        detalle.get("total_linea"),
                        detalle.get("cantidad_origen"),
                    )
                    
                    cursor.execute(sql, values)
                    inserted_count += 1
                    logger.debug(f"   → Línea OC insertada: {detalle.get('sku_sap')}")
                    
                except Exception as e:
                    logger.warning(f"   ⚠️ Error al insertar línea de detalle OC: {e}")
                    logger.warning(f"      SKU: {detalle.get('sku_sap')}")
                    continue
            
            self.conn.commit()
            logger.debug(f"✅ {inserted_count} líneas de detalle OC insertadas")
            return inserted_count
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar orden_compra_detalle: {e}")
            raise
        finally:
            cursor.close()
    
    def find_by_despacho_id(self, despacho_id: str) -> Optional[str]:
        """
        Busca una orden de compra por despacho_id.
        
        Args:
            despacho_id: UUID del despacho
            
        Returns:
            oc_id si existe, None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT oc_id FROM orden_compra_cabecera WHERE despacho_id = ?",
                (despacho_id,)
            )
            result = cursor.fetchone()
            return str(result[0]) if result else None
        finally:
            cursor.close()

