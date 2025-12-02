"""
Repositorio para operaciones CRUD de despachos en SQL Server.
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


def serialize_decimal(value):
    """
    Convierte un objeto Decimal de pyodbc a float para JSON serialization.
    
    Args:
        value: Objeto Decimal, float, int, o None
        
    Returns:
        float o None
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    
    def get_existing_cabecera(self, despacho_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene los datos existentes de una cabecera de despacho.
        
        Args:
            despacho_id: UUID del despacho
            
        Returns:
            Diccionario con los datos existentes, o None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT empresa, codigo_cliente, fecha_despacho, codigo_factura,
                       anulada, numero_pedido_sistema, numero_orden, numero_factura,
                       tipo_documento, orden_compra, orden_compra_cliente,
                       remision_facturada, num_id_factura_relacionada, fecha_factura,
                       codigo_despacho, codigo_bodega, confirmado
                FROM despacho_cabecera
                WHERE despacho_id = ?
                """,
                (despacho_id,)
            )
            result = cursor.fetchone()
            if not result:
                return None
            
            return {
                "empresa": result[0],
                "codigo_cliente": result[1],
                "fecha_despacho": result[2],
                "codigo_factura": result[3],
                "anulada": result[4],
                "numero_pedido_sistema": result[5],
                "numero_orden": result[6],
                "numero_factura": result[7],
                "tipo_documento": result[8],
                "orden_compra": result[9],
                "orden_compra_cliente": result[10],
                "remision_facturada": result[11],
                "num_id_factura_relacionada": result[12],
                "fecha_factura": result[13],
                "codigo_despacho": result[14],
                "codigo_bodega": result[15],
                "confirmado": result[16],
            }
        finally:
            cursor.close()
    
    def update_cabecera(self, despacho_id: str, datos_cabecera: Dict[str, Any]) -> bool:
        """
        Actualiza un registro existente en despacho_cabecera.
        
        Si algún campo en datos_cabecera es None, se preserva el valor existente
        en la base de datos para evitar violar restricciones NOT NULL.
        
        Args:
            despacho_id: UUID del despacho a actualizar
            datos_cabecera: Diccionario con datos actualizados (sin despacho_id)
            
        Returns:
            True si se actualizó correctamente
            
        Raises:
            Exception: Si falla la actualización
        """
        cursor = self.conn.cursor()
        
        try:
            # Obtener valores existentes para campos que son None
            existing = self.get_existing_cabecera(despacho_id)
            if not existing:
                logger.warning(f"⚠️ No se encontró despacho para actualizar: {despacho_id}")
                return False
            
            # Fusionar datos: usar nuevo valor si existe y no es None, sino usar existente
            merged = {}
            for key in existing.keys():
                new_value = datos_cabecera.get(key)
                if new_value is not None:
                    merged[key] = new_value
                else:
                    merged[key] = existing[key]
            
            # SQL para actualizar (todos los campos excepto despacho_id y created_at)
            sql = """
            UPDATE despacho_cabecera SET
                empresa = ?,
                codigo_cliente = ?,
                fecha_despacho = ?,
                codigo_factura = ?,
                anulada = ?,
                numero_pedido_sistema = ?,
                numero_orden = ?,
                numero_factura = ?,
                tipo_documento = ?,
                orden_compra = ?,
                orden_compra_cliente = ?,
                remision_facturada = ?,
                num_id_factura_relacionada = ?,
                fecha_factura = ?,
                codigo_despacho = ?,
                codigo_bodega = ?,
                confirmado = ?,
                updated_at = GETDATE()
            WHERE despacho_id = ?
            """
            
            values = (
                merged["empresa"],
                merged["codigo_cliente"],
                merged["fecha_despacho"],
                merged["codigo_factura"],
                merged["anulada"],
                merged["numero_pedido_sistema"],
                merged["numero_orden"],
                merged["numero_factura"],
                merged["tipo_documento"],
                merged["orden_compra"],
                merged["orden_compra_cliente"],
                merged["remision_facturada"],
                merged["num_id_factura_relacionada"],
                merged["fecha_factura"],
                merged["codigo_despacho"],
                merged.get("codigo_bodega"),
                merged.get("confirmado", 0),  # BIT: 0 o 1, por defecto 0
                despacho_id,
            )
            
            cursor.execute(sql, values)
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.debug(f"✅ Despacho cabecera actualizado: {despacho_id} - {merged.get('codigo_factura', 'N/A')}")
                return True
            else:
                logger.warning(f"⚠️ No se encontró despacho para actualizar: {despacho_id}")
                return False
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar despacho_cabecera: {e}")
            logger.error(f"   Despacho ID: {despacho_id}")
            raise
        finally:
            cursor.close()
    
    def delete_detalles(self, despacho_id: str) -> int:
        """
        Elimina todos los detalles de un despacho.
        
        Args:
            despacho_id: UUID del despacho
            
        Returns:
            Número de detalles eliminados
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute(
                "DELETE FROM despacho_detalle WHERE despacho_id = ?",
                (despacho_id,)
            )
            rows_deleted = cursor.rowcount
            self.conn.commit()
            
            if rows_deleted > 0:
                logger.debug(f"✅ {rows_deleted} detalles eliminados para despacho: {despacho_id}")
            
            return rows_deleted
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al eliminar detalles: {e}")
            logger.error(f"   Despacho ID: {despacho_id}")
            raise
        finally:
            cursor.close()
    
    def insert_cabecera(self, datos_cabecera: Dict[str, Any]) -> str:
        """
        Inserta un registro en despacho_cabecera.
        
        Valida que los campos requeridos (empresa) no sean None antes de insertar.
        
        Args:
            datos_cabecera: Diccionario con datos de cabecera (sin despacho_id)
            
        Returns:
            despacho_id (UUID) generado
            
        Raises:
            ValueError: Si campos requeridos son None
            Exception: Si falla la inserción
        """
        # Validar campos críticos requeridos (NOT NULL)
        # Nota: empresa, codigo_cliente, numero_factura y tipo_documento tienen valores por defecto
        # en el mapper, así que solo validamos codigo_factura que es crítico
        codigo_factura = datos_cabecera.get("codigo_factura")
        if not codigo_factura:
            raise ValueError(
                f"El campo 'codigo_factura' es requerido y no puede ser NULL. "
                f"Verifique que el campo CODIGO_FACTURA esté presente en los datos de MBA3."
            )
        
        # Validar que los campos con valores por defecto no sean None (por si acaso)
        campos_faltantes = []
        if datos_cabecera.get("empresa") is None:
            campos_faltantes.append("empresa")
        if datos_cabecera.get("codigo_cliente") is None:
            campos_faltantes.append("codigo_cliente")
        if datos_cabecera.get("numero_factura") is None:
            campos_faltantes.append("numero_factura")
        if datos_cabecera.get("tipo_documento") is None:
            campos_faltantes.append("tipo_documento")
        if datos_cabecera.get("fecha_despacho") is None:
            campos_faltantes.append("fecha_despacho")
        
        if campos_faltantes:
            # Esto no debería ocurrir con los valores por defecto, pero lo validamos por seguridad
            logger.warning(
                f"⚠️ Campos con valores por defecto faltantes (esto no debería ocurrir): {', '.join(campos_faltantes)}. "
                f"Código de factura: {codigo_factura}"
            )
            raise ValueError(
                f"Los siguientes campos son requeridos y no pueden ser NULL: {', '.join(campos_faltantes)}. "
                f"Código de factura: {codigo_factura}. "
                f"Esto indica un problema en el mapper que debería proporcionar valores por defecto."
            )
        
        cursor = self.conn.cursor()
        
        try:
            # Generar UUID para despacho_id
            cursor.execute("SELECT NEWID()")
            uuid_result = cursor.fetchone()
            if uuid_result is None:
                raise ValueError("No se pudo generar UUID para despacho_id")
            despacho_id = str(uuid_result[0])
            
            # SQL para insertar (incluyendo todos los campos de la tabla)
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
                fecha_factura,
                codigo_despacho,
                codigo_bodega,
                confirmado,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
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
                datos_cabecera["fecha_factura"],
                datos_cabecera["codigo_despacho"],
                datos_cabecera.get("codigo_bodega"),
                datos_cabecera.get("confirmado", 0),  # BIT: 0 o 1, por defecto 0
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
                cantidad_docena_mba3,
                subtotal_sap,
                cantidad_pack_sap,
                unidad_sap,
                precio_unitario_mba3,
                descuento,
                total_linea_mba3,
                impuesto,
                nombre_producto,
                tipo_linea,
                precio_unitario_sap
            ) VALUES (NEWID(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            for detalle in detalles:
                try:
                    values = (
                        despacho_id,
                        detalle["sku"],
                        detalle["cantidad"],  # cantidad_docena_mba3
                        detalle.get("total_producto"),  # subtotal_sap - NULL o igual a total_linea
                        detalle.get("cantidad_sap"),  # cantidad_pack_sap - NULL si no existe
                        detalle.get("unidad_sap"),  # unidad_sap - NULL si no existe
                        detalle["precio_unitario"],  # precio_unitario_mba3
                        detalle["descuento"],
                        detalle["total_linea"],  # total_linea_mba3
                        detalle.get("impuesto"),  # NULL si no existe
                        detalle.get("nombre_producto"),  # NULL si no existe
                        detalle["tipo_linea"],
                        detalle.get("precio_unitario_sap"),  # precio_unitario_sap - NULL si no existe
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
    
    def get_detalles(self, despacho_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene todos los detalles de un despacho.
        
        Args:
            despacho_id: UUID del despacho
            
        Returns:
            Lista de diccionarios con los datos de detalle
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT detalle_id, despacho_id, sku, cantidad_docena_mba3,
                       subtotal_sap, cantidad_pack_sap, unidad_sap,
                       precio_unitario_mba3, descuento, total_linea_mba3,
                       impuesto, nombre_producto, tipo_linea, precio_unitario_sap
                FROM despacho_detalle
                WHERE despacho_id = ?
                ORDER BY detalle_id
                """,
                (despacho_id,)
            )
            results = cursor.fetchall()
            
            detalles = []
            for row in results:
                detalles.append({
                    "detalle_id": str(row[0]),
                    "despacho_id": str(row[1]),
                    "sku": row[2],
                    "cantidad_docena_mba3": serialize_decimal(row[3]),
                    "subtotal_sap": serialize_decimal(row[4]),
                    "cantidad_pack_sap": serialize_decimal(row[5]),
                    "unidad_sap": row[6],
                    "precio_unitario_mba3": serialize_decimal(row[7]),
                    "descuento": serialize_decimal(row[8]),
                    "total_linea_mba3": serialize_decimal(row[9]),
                    "impuesto": serialize_decimal(row[10]),
                    "nombre_producto": row[11],
                    "tipo_linea": row[12],
                    "precio_unitario_sap": serialize_decimal(row[13]),
                })
            
            return detalles
        finally:
            cursor.close()
    
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
        
        Incluye información de ambas tablas (despacho_cabecera y orden_compra_cabecera)
        y sus respectivos detalles (despacho_detalle y orden_compra_detalle).
        Si un despacho no tiene OC asociada, los campos de OC serán None.
        
        Args:
            limit: Número máximo de registros a retornar (opcional, para paginación)
            
        Returns:
            Lista de diccionarios con información combinada de despachos, OCs y sus detalles
        """
        cursor = self.conn.cursor()
        try:
            # Query con LEFT JOIN para obtener despachos con y sin OC
            sql = """
                SELECT 
                    dc.despacho_id,
                    dc.empresa,
                    dc.codigo_cliente,
                    dc.fecha_despacho,
                    dc.codigo_factura,
                    dc.anulada,
                    dc.numero_pedido_sistema,
                    dc.numero_orden,
                    dc.numero_factura,
                    dc.tipo_documento,
                    dc.orden_compra,
                    dc.orden_compra_cliente,
                    dc.remision_facturada,
                    dc.num_id_factura_relacionada,
                    dc.fecha_factura,
                    dc.codigo_despacho,
                    dc.codigo_bodega,
                    dc.confirmado,
                    dc.created_at AS despacho_created_at,
                    dc.updated_at AS despacho_updated_at,
                    oc.oc_id,
                    oc.proveedor,
                    oc.fecha_generacion,
                    oc.referencia_despacho,
                    oc.estado AS oc_estado,
                    oc.numero_oc_sap,
                    oc.created_at AS oc_created_at
                FROM despacho_cabecera dc
                LEFT JOIN orden_compra_cabecera oc ON dc.despacho_id = oc.despacho_id
                ORDER BY dc.created_at DESC
            """
            
            # Aplicar límite si se especifica (validado por FastAPI como int opcional)
            if limit and isinstance(limit, int) and limit > 0:
                sql += f" OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"
            
            cursor.execute(sql)
            results = cursor.fetchall()
            
            despachos = []
            for row in results:
                despacho_id = str(row[0])
                oc_id = str(row[20]) if row[20] else None
                
                despacho_info = {
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
                    "orden_compra": row[10],  # Campo de despacho_cabecera
                    "orden_compra_cliente": row[11],
                    "remision_facturada": bool(row[12]) if row[12] is not None else None,
                    "num_id_factura_relacionada": row[13],
                    "fecha_factura": serialize_date(row[14]),
                    "codigo_despacho": row[15],
                    "codigo_bodega": row[16],
                    "confirmado": bool(row[17]) if row[17] is not None else None,
                    "despacho_created_at": serialize_date(row[18]),
                    "despacho_updated_at": serialize_date(row[19]),
                    # Obtener detalles del despacho
                    "despacho_detalles": self.get_detalles(despacho_id),
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
                despachos.append(despacho_info)
            
            return despachos
        finally:
            cursor.close()


