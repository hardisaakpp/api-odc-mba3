"""
Repositorio para operaciones CRUD de órdenes de compra en SQL Server.
"""

import logging
import pyodbc
from typing import Optional, Dict, Any, List
from datetime import date, datetime

logger = logging.getLogger(__name__)


def serialize_date(value):
    """
    Convierte un objeto date o datetime a string ISO format para JSON serialization.
    
    Args:
        value: Objeto date, datetime, o None
        
    Returns:
        String en formato ISO o None
    """
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


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
        Si no encuentra en la tabla, usa un diccionario de mapeo hardcodeado como fallback.
        
        Args:
            empresa: Nombre de la empresa
            
        Returns:
            CardCode (proveedor) si se encuentra, empresa si no existe mapeo
        """
        if not empresa:
            return None
        
        # Diccionario de mapeo hardcodeado (fallback)
        MAPEO_EMPRESA_PROVEEDOR = {
            "TRAYO": "P1790389219001",
            # Agregar más mapeos aquí si es necesario en el futuro
        }
        
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
            
            # Opción 3: Usar diccionario hardcodeado como fallback
            if empresa in MAPEO_EMPRESA_PROVEEDOR:
                card_code = MAPEO_EMPRESA_PROVEEDOR[empresa]
                logger.info(f"✅ Mapeo hardcodeado encontrado: {empresa} → {card_code}")
                return card_code
            
            # Si no se encuentra mapeo, retornar la empresa misma
            # (puede ser que ya sea el CardCode o que la tabla no exista)
            logger.debug(f"ℹ️ No se encontró mapeo para empresa '{empresa}', usando empresa como proveedor")
            return empresa
            
        except Exception as e:
            logger.warning(f"⚠️ Error al buscar proveedor en tabla cliente: {e}")
            # Si hay error, intentar diccionario hardcodeado
            if empresa in MAPEO_EMPRESA_PROVEEDOR:
                return MAPEO_EMPRESA_PROVEEDOR[empresa]
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
            cursor.execute("SELECT NEWID()")
            uuid_result = cursor.fetchone()
            if uuid_result is None:
                raise ValueError("No se pudo generar UUID para oc_id")
            oc_id = str(uuid_result[0])
            
            # SQL para insertar (estructura real de la tabla)
            # Inicializar estado como 'PENDIENTE' si no se proporciona
            estado = datos_cabecera.get("estado", "PENDIENTE")
            
            sql = """
            INSERT INTO orden_compra_cabecera (
                oc_id,
                despacho_id,
                proveedor,
                fecha_generacion,
                referencia_despacho,
                estado,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, GETDATE())
            """
            
            values = (
                oc_id,
                datos_cabecera.get("despacho_id"),
                datos_cabecera.get("proveedor"),
                datos_cabecera.get("fecha_generacion"),
                datos_cabecera.get("referencia_despacho"),
                estado,
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
    
    def find_by_referencia_despacho(self, referencia_despacho: str) -> Optional[Dict[str, Any]]:
        """
        Busca una orden de compra por referencia_despacho (número de factura).
        
        Args:
            referencia_despacho: Número de factura/despacho a buscar
            
        Returns:
            Diccionario con datos de la OC si existe, None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT oc_id, despacho_id, proveedor, fecha_generacion,
                       estado, numero_oc_sap, referencia_despacho, created_at
                FROM orden_compra_cabecera
                WHERE referencia_despacho = ?
                """,
                (referencia_despacho,)
            )
            result = cursor.fetchone()
            if not result:
                return None
            
            return {
                "oc_id": str(result[0]),
                "despacho_id": str(result[1]),
                "proveedor": result[2],
                "fecha_generacion": serialize_date(result[3]),
                "estado": result[4],
                "numero_oc_sap": result[5],
                "referencia_despacho": result[6],
                "created_at": serialize_date(result[7]),
            }
        finally:
            cursor.close()
    
    def get_by_estado(self, estado: str) -> List[Dict[str, Any]]:
        """
        Obtiene todas las órdenes de compra con un estado específico.
        
        Útil para consultar ODC pendientes, enviadas, confirmadas, etc.
        
        Args:
            estado: Estado a filtrar (PENDIENTE, ENVIADA, CONFIRMADA, ERROR, etc.)
            
        Returns:
            Lista de diccionarios con información de las ODC
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT oc_id, despacho_id, proveedor, fecha_generacion,
                       estado, numero_oc_sap, referencia_despacho, created_at
                FROM orden_compra_cabecera
                WHERE estado = ?
                ORDER BY created_at DESC
                """,
                (estado,)
            )
            results = cursor.fetchall()
            
            oc_list = []
            for row in results:
                oc_list.append({
                    "oc_id": str(row[0]),
                    "despacho_id": str(row[1]),
                    "proveedor": row[2],
                    "fecha_generacion": serialize_date(row[3]),
                    "estado": row[4],
                    "numero_oc_sap": row[5],
                    "referencia_despacho": row[6],
                    "created_at": serialize_date(row[7]),
                    # updated_at no existe en la tabla, se omite
                })
            
            return oc_list
        finally:
            cursor.close()
    
    def get_all(self) -> List[Dict[str, Any]]:
        """
        Obtiene todas las órdenes de compra sin filtro de estado.
        
        Útil para consultar todas las ODC independientemente de su estado.
        
        Returns:
            Lista de diccionarios con información de todas las ODC
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT oc_id, despacho_id, proveedor, fecha_generacion,
                       estado, numero_oc_sap, referencia_despacho, created_at
                FROM orden_compra_cabecera
                ORDER BY created_at DESC
                """
            )
            results = cursor.fetchall()
            
            oc_list = []
            for row in results:
                oc_list.append({
                    "oc_id": str(row[0]),
                    "despacho_id": str(row[1]),
                    "proveedor": row[2],
                    "fecha_generacion": serialize_date(row[3]),
                    "estado": row[4],
                    "numero_oc_sap": row[5],
                    "referencia_despacho": row[6],
                    "created_at": serialize_date(row[7]),
                })
            
            return oc_list
        finally:
            cursor.close()
    
    def get_existing_cabecera(self, oc_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene los datos existentes de una cabecera de orden de compra.
        
        Args:
            oc_id: UUID de la orden de compra
            
        Returns:
            Diccionario con los datos existentes, o None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT oc_id, despacho_id, proveedor, fecha_generacion,
                       estado, numero_oc_sap, referencia_despacho
                FROM orden_compra_cabecera
                WHERE oc_id = ?
                """,
                (oc_id,)
            )
            result = cursor.fetchone()
            if not result:
                return None
            
            return {
                "oc_id": str(result[0]),
                "despacho_id": str(result[1]),
                "proveedor": result[2],
                "fecha_generacion": serialize_date(result[3]),
                "estado": result[4],
                "numero_oc_sap": result[5],
                "referencia_despacho": result[6],
            }
        finally:
            cursor.close()
    
    def update_cabecera(self, oc_id: str, datos_cabecera: Dict[str, Any]) -> bool:
        """
        Actualiza un registro existente en orden_compra_cabecera.
        
        Si algún campo en datos_cabecera es None, se preserva el valor existente
        en la base de datos para evitar violar restricciones NOT NULL.
        
        Args:
            oc_id: UUID de la orden de compra a actualizar
            datos_cabecera: Diccionario con datos actualizados (sin oc_id)
            
        Returns:
            True si se actualizó correctamente
            
        Raises:
            Exception: Si falla la actualización
        """
        cursor = self.conn.cursor()
        
        try:
            # Obtener valores existentes para campos que son None
            existing = self.get_existing_cabecera(oc_id)
            if not existing:
                logger.warning(f"⚠️ No se encontró orden de compra para actualizar: {oc_id}")
                return False
            
            # Fusionar datos: usar nuevo valor si existe y no es None, sino usar existente
            merged = {}
            for key in existing.keys():
                if key == "oc_id":  # No actualizar oc_id
                    continue
                new_value = datos_cabecera.get(key)
                if new_value is not None:
                    merged[key] = new_value
                else:
                    merged[key] = existing[key]
            
            # SQL para actualizar (campos actualizables)
            # Incluir estado y numero_oc_sap si están presentes
            sql = """
            UPDATE orden_compra_cabecera SET
                proveedor = ?,
                fecha_generacion = ?,
                referencia_despacho = ?,
                estado = ?,
                numero_oc_sap = ?
            WHERE oc_id = ?
            """
            
            values = (
                merged.get("proveedor"),
                merged.get("fecha_generacion"),
                merged.get("referencia_despacho"),
                merged.get("estado"),  # Puede ser None, se preservará el existente
                merged.get("numero_oc_sap"),  # Puede ser None
                oc_id,
            )
            
            cursor.execute(sql, values)
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.debug(f"✅ Orden compra cabecera actualizada: {oc_id} - Despacho: {merged.get('despacho_id', 'N/A')}")
                return True
            else:
                logger.warning(f"⚠️ No se encontró orden de compra para actualizar: {oc_id}")
                return False
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar orden_compra_cabecera: {e}")
            logger.error(f"   OC ID: {oc_id}")
            raise
        finally:
            cursor.close()
    
    def update_estado(self, oc_id: str, estado: str, numero_oc_sap: Optional[str] = None) -> bool:
        """
        Actualiza el estado de una orden de compra.
        
        Método helper para cambiar el estado de una OC fácilmente.
        Útil para cuando se implemente la integración con SAP.
        
        Args:
            oc_id: UUID de la orden de compra
            estado: Nuevo estado (PENDIENTE, ENVIADA, CONFIRMADA, ERROR, etc.)
            numero_oc_sap: Número de OC asignado por SAP (opcional)
            
        Returns:
            True si se actualizó correctamente, False en caso contrario
        """
        cursor = self.conn.cursor()
        
        try:
            if numero_oc_sap:
                sql = """
                UPDATE orden_compra_cabecera SET
                    estado = ?,
                    numero_oc_sap = ?
                WHERE oc_id = ?
                """
                values = (estado, numero_oc_sap, oc_id)
            else:
                sql = """
                UPDATE orden_compra_cabecera SET
                    estado = ?
                WHERE oc_id = ?
                """
                values = (estado, oc_id)
            
            cursor.execute(sql, values)
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.info(f"✅ Estado de OC actualizado: {oc_id} → {estado}" + 
                          (f" (SAP: {numero_oc_sap})" if numero_oc_sap else ""))
                return True
            else:
                logger.warning(f"⚠️ No se encontró orden de compra para actualizar estado: {oc_id}")
                return False
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar estado de orden_compra: {e}")
            logger.error(f"   OC ID: {oc_id}, Estado: {estado}")
            raise
        finally:
            cursor.close()
    
    def get_detalles(self, oc_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene todos los detalles de una orden de compra.
        
        Args:
            oc_id: UUID de la orden de compra
            
        Returns:
            Lista de diccionarios con los detalles de la ODC
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT oc_detalle_id, oc_id, sku_sap, cantidad_sap, unidad_sap,
                       referencia_detalle, precio_unitario, total_linea, cantidad_origen
                FROM orden_compra_detalle
                WHERE oc_id = ?
                ORDER BY oc_detalle_id ASC
                """,
                (oc_id,)
            )
            results = cursor.fetchall()
            
            detalles = []
            for row in results:
                detalles.append({
                    "oc_detalle_id": str(row[0]),
                    "oc_id": str(row[1]),
                    "sku_sap": row[2],
                    "cantidad_sap": float(row[3]) if row[3] is not None else 0.0,
                    "unidad_sap": row[4],
                    "referencia_detalle": str(row[5]) if row[5] else None,
                    "precio_unitario": float(row[6]) if row[6] is not None else 0.0,
                    "total_linea": float(row[7]) if row[7] is not None else 0.0,
                    "cantidad_origen": float(row[8]) if row[8] is not None else None,
                    # created_at y updated_at no existen en la tabla, se omiten
                })
            
            return detalles
        finally:
            cursor.close()
    
    def delete_detalles(self, oc_id: str) -> int:
        """
        Elimina todos los detalles de una orden de compra.
        
        Args:
            oc_id: UUID de la orden de compra
            
        Returns:
            Número de detalles eliminados
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute(
                "DELETE FROM orden_compra_detalle WHERE oc_id = ?",
                (oc_id,)
            )
            rows_deleted = cursor.rowcount
            self.conn.commit()
            
            if rows_deleted > 0:
                logger.debug(f"✅ {rows_deleted} detalles eliminados para OC: {oc_id}")
            
            return rows_deleted
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al eliminar detalles de OC: {e}")
            logger.error(f"   OC ID: {oc_id}")
            raise
        finally:
            cursor.close()
    
    def delete_cabecera(self, oc_id: str) -> bool:
        """
        Elimina una orden de compra completa (detalles y cabecera).
        
        Primero elimina los detalles y luego la cabecera para respetar
        las restricciones de clave foránea.
        
        Args:
            oc_id: UUID de la orden de compra a eliminar
            
        Returns:
            True si se eliminó correctamente, False si no se encontró
            
        Raises:
            Exception: Si falla la eliminación
        """
        cursor = self.conn.cursor()
        
        try:
            # Verificar que la OC existe
            existing = self.get_existing_cabecera(oc_id)
            if not existing:
                logger.warning(f"⚠️ No se encontró orden de compra para eliminar: {oc_id}")
                return False
            
            # 1. Eliminar detalles primero (por restricciones de FK)
            detalles_eliminados = self.delete_detalles(oc_id)
            logger.debug(f"   → {detalles_eliminados} detalles eliminados")
            
            # 2. Eliminar cabecera
            cursor.execute(
                "DELETE FROM orden_compra_cabecera WHERE oc_id = ?",
                (oc_id,)
            )
            rows_deleted = cursor.rowcount
            self.conn.commit()
            
            if rows_deleted > 0:
                logger.info(f"✅ Orden de compra eliminada: {oc_id} (detalles: {detalles_eliminados})")
                return True
            else:
                logger.warning(f"⚠️ No se pudo eliminar orden de compra: {oc_id}")
                return False
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al eliminar orden de compra: {e}")
            logger.error(f"   OC ID: {oc_id}")
            raise
        finally:
            cursor.close()

