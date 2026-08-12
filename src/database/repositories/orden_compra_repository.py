"""
Repositorio para operaciones CRUD de órdenes de compra en SQL Server.

CHANGELOG:
- 2026-02-06: Agregado soporte para campos de auditoría (Buenas Prácticas - Sección 3)
"""

import logging
import pyodbc
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from src.utils.timezone import ahora_naive

from .common.serialization import serialize_date

if TYPE_CHECKING:
    from src.utils.audit_context import AuditContext

logger = logging.getLogger(__name__)

_OC_CABECERA_SELECT = """
    oc_id, despacho_id, pedido_id, proveedor, fecha_generacion,
    estado, numero_oc_sap, doc_entry, referencia_despacho, codigo_bodega, created_at,
    respuesta_sap, fecha_procesado, error_message, error_code, error_source, updated_at
"""


def _map_oc_cabecera_row(row: Any) -> Dict[str, Any]:
    """Mapea una fila de orden_compra_cabecera al dict usado por la API."""
    return {
        "oc_id": str(row[0]),
        "despacho_id": str(row[1]) if row[1] else None,
        "pedido_id": str(row[2]) if row[2] else None,
        "proveedor": row[3],
        "fecha_generacion": serialize_date(row[4]),
        "estado": row[5],
        "numero_oc_sap": row[6],
        "doc_num": row[6],
        "doc_entry": row[7],
        "referencia_despacho": row[8],
        "codigo_bodega": row[9],
        "created_at": serialize_date(row[10]),
        "respuesta_sap": row[11],
        "fecha_procesado": serialize_date(row[12]),
        "error_message": row[13],
        "error_code": row[14],
        "error_source": row[15],
        "updated_at": serialize_date(row[16]),
    }


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
            "TEXTILES EL RAYO S.A.": "P1790389219001",
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
    
    def insert_cabecera(
        self, 
        datos_cabecera: Dict[str, Any],
        audit_context: Optional["AuditContext"] = None
    ) -> str:
        """
        Inserta un registro en orden_compra_cabecera.
        
        Args:
            datos_cabecera: Diccionario con datos de cabecera (sin oc_id)
            audit_context: Contexto de auditoría opcional (Buenas Prácticas - Sección 3)
            
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
            
            # Campos de auditoría (Buenas Prácticas - Sección 3)
            creado_por = None
            origen = None
            ip_origen = None
            if audit_context:
                creado_por = audit_context.get_creado_por()
                origen = audit_context.origen
                ip_origen = audit_context.ip_origen
            
            sql = """
            INSERT INTO orden_compra_cabecera (
                oc_id,
                despacho_id,
                pedido_id,
                proveedor,
                fecha_generacion,
                referencia_despacho,
                codigo_bodega,
                estado,
                creado_por,
                origen,
                ip_origen,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            values = (
                oc_id,
                datos_cabecera.get("despacho_id"),
                datos_cabecera.get("pedido_id"),
                datos_cabecera.get("proveedor"),
                datos_cabecera.get("fecha_generacion"),
                datos_cabecera.get("referencia_despacho"),
                datos_cabecera.get("codigo_bodega"),
                estado,
                creado_por,
                origen,
                ip_origen,
                ahora_naive(),
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
    
    def insert_detalles(
        self, 
        oc_id: str, 
        detalles: List[Dict[str, Any]],
        audit_context: Optional["AuditContext"] = None
    ) -> int:
        """
        Inserta múltiples líneas de detalle en orden_compra_detalle.
        
        Args:
            oc_id: UUID de la cabecera de orden de compra
            detalles: Lista de diccionarios con datos de detalle
            audit_context: Contexto de auditoría opcional (Buenas Prácticas - Sección 3)
            
        Returns:
            Número de líneas insertadas
        """
        if not detalles:
            return 0
        
        cursor = self.conn.cursor()
        inserted_count = 0
        
        # Campos de auditoría (Buenas Prácticas - Sección 3)
        creado_por = None
        origen = None
        ip_origen = None
        if audit_context:
            creado_por = audit_context.get_creado_por()
            origen = audit_context.origen
            ip_origen = audit_context.ip_origen
        
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
                cantidad_origen,
                codigo_bodega,
                creado_por,
                origen,
                ip_origen
            ) VALUES (NEWID(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            for detalle in detalles:
                try:
                    # Redondear a 4 decimales (tabla orden_compra_detalle: DECIMAL(18,4))
                    precio_unitario = detalle.get("precio_unitario")
                    precio_unitario = round(float(precio_unitario), 4) if precio_unitario is not None else None
                    total_linea = detalle.get("total_linea")
                    total_linea = round(float(total_linea), 4) if total_linea is not None else None

                    values = (
                        oc_id,
                        detalle.get("sku_sap"),
                        detalle.get("cantidad_sap"),
                        detalle.get("unidad_sap"),
                        detalle.get("referencia_detalle"),
                        precio_unitario,
                        total_linea,
                        detalle.get("cantidad_origen"),
                        detalle.get("codigo_bodega"),  # ⭐ NUEVO: Persistir bodega por línea
                        creado_por,
                        origen,
                        ip_origen,
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
    
    def find_by_pedido_id(self, pedido_id: str) -> Optional[str]:
        """
        Busca una orden de compra por pedido_id.
        
        Args:
            pedido_id: UUID del pedido
            
        Returns:
            oc_id si existe, None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT oc_id FROM orden_compra_cabecera WHERE pedido_id = ?",
                (pedido_id,)
            )
            result = cursor.fetchone()
            return str(result[0]) if result else None
        finally:
            cursor.close()
    
    def get_doc_num_by_pedido_id(self, pedido_id: str) -> Optional[str]:
        """
        Obtiene el DocNum (numero_oc_sap) de la OC más reciente enviada a SAP para un pedido.

        Args:
            pedido_id: UUID del pedido

        Returns:
            DocNum como string si existe una OC con numero_oc_sap registrado, None si no.
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT TOP 1 numero_oc_sap
                FROM orden_compra_cabecera
                WHERE pedido_id = ? AND numero_oc_sap IS NOT NULL
                ORDER BY created_at DESC
                """,
                (pedido_id,)
            )
            result = cursor.fetchone()
            return str(result[0]) if result and result[0] is not None else None
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
                SELECT oc_id, despacho_id, pedido_id, proveedor, fecha_generacion,
                       estado, numero_oc_sap, doc_entry, referencia_despacho, codigo_bodega, created_at,
                       respuesta_sap, fecha_procesado, error_message, error_code, error_source, updated_at
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
                "despacho_id": str(result[1]) if result[1] else None,
                "pedido_id": str(result[2]) if result[2] else None,
                "proveedor": result[3],
                "fecha_generacion": serialize_date(result[4]),
                "estado": result[5],
                "numero_oc_sap": result[6],
                "doc_num": result[6],  # Número de documento SAP (mismo que numero_oc_sap, para frontend)
                "doc_entry": result[7],
                "referencia_despacho": result[8],
                "codigo_bodega": result[9],
                "created_at": serialize_date(result[10]),
                "respuesta_sap": result[11],
                "fecha_procesado": serialize_date(result[12]),
                "error_message": result[13],
                "error_code": result[14],
                "error_source": result[15],
                "updated_at": serialize_date(result[16]),
            }
        finally:
            cursor.close()
    
    def get_by_pedido_id(self, pedido_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene todas las órdenes de compra asociadas a un pedido.
        
        Args:
            pedido_id: UUID del pedido
            
        Returns:
            Lista de diccionarios con información de las ODC del pedido
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT oc_id, despacho_id, pedido_id, proveedor, fecha_generacion,
                       estado, numero_oc_sap, doc_entry, referencia_despacho, codigo_bodega, created_at,
                       respuesta_sap, fecha_procesado, error_message, error_code, error_source, updated_at
                FROM orden_compra_cabecera
                WHERE pedido_id = ?
                ORDER BY created_at ASC
                """,
                (pedido_id,)
            )
            rows = cursor.fetchall()
            
            return [
                {
                    "oc_id": str(row[0]),
                    "despacho_id": str(row[1]) if row[1] else None,
                    "pedido_id": str(row[2]) if row[2] else None,
                    "proveedor": row[3],
                    "fecha_generacion": serialize_date(row[4]),
                    "estado": row[5],
                    "numero_oc_sap": row[6],
                    "doc_num": row[6],  # Número de documento SAP (para columna Docnum en frontend)
                    "doc_entry": row[7],
                    "referencia_despacho": row[8],
                    "codigo_bodega": row[9],
                    "created_at": serialize_date(row[10]),
                    "respuesta_sap": row[11],
                    "fecha_procesado": serialize_date(row[12]),
                    "error_message": row[13],
                    "error_code": row[14],
                    "error_source": row[15],
                    "updated_at": serialize_date(row[16]),
                }
                for row in rows
            ]
        finally:
            cursor.close()
    
    def list_paginated(
        self,
        *,
        estado: Optional[str] = None,
        referencia_despacho: Optional[str] = None,
        numero_oc_sap: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Lista órdenes de compra con filtros y paginación en servidor.

        Args:
            estado: Filtrar por estado (PENDIENTE, ENVIADA, ERROR, etc.)
            referencia_despacho: Búsqueda parcial por referencia de despacho
            numero_oc_sap: Búsqueda parcial por número de OC en SAP
            search: Búsqueda parcial en referencia_despacho o numero_oc_sap
            limit: Máximo de filas a devolver
            offset: Desplazamiento para paginación

        Returns:
            Dict con keys ``data`` (lista) y ``total`` (conteo sin paginar)
        """
        cursor = self.conn.cursor()
        try:
            where_conditions: List[str] = []
            params: List[Any] = []

            if estado:
                where_conditions.append("estado = ?")
                params.append(estado.strip().upper())

            if referencia_despacho:
                where_conditions.append("referencia_despacho LIKE ?")
                params.append(f"%{referencia_despacho.strip()}%")

            if numero_oc_sap:
                where_conditions.append(
                    "(CAST(numero_oc_sap AS NVARCHAR(50)) LIKE ? OR CAST(doc_entry AS NVARCHAR(50)) LIKE ?)"
                )
                term = f"%{numero_oc_sap.strip()}%"
                params.extend([term, term])

            if search:
                term = f"%{search.strip()}%"
                where_conditions.append(
                    "(referencia_despacho LIKE ? OR CAST(numero_oc_sap AS NVARCHAR(50)) LIKE ? OR CAST(doc_entry AS NVARCHAR(50)) LIKE ?)"
                )
                params.extend([term, term, term])

            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

            count_query = f"SELECT COUNT(*) FROM orden_compra_cabecera WHERE {where_clause}"
            cursor.execute(count_query, params)
            count_row = cursor.fetchone()
            total = int(count_row[0]) if count_row else 0

            data_query = f"""
                SELECT {_OC_CABECERA_SELECT.strip()}
                FROM orden_compra_cabecera
                WHERE {where_clause}
                ORDER BY created_at DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """
            data_params = list(params) + [offset, limit]
            cursor.execute(data_query, data_params)
            oc_list = [_map_oc_cabecera_row(row) for row in cursor.fetchall()]

            return {
                "data": oc_list,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + len(oc_list)) < total,
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
                SELECT oc_id, despacho_id, pedido_id, proveedor, fecha_generacion,
                       estado, numero_oc_sap, doc_entry, referencia_despacho, codigo_bodega, created_at,
                       respuesta_sap, fecha_procesado, error_message, error_code, error_source, updated_at
                FROM orden_compra_cabecera
                WHERE estado = ?
                ORDER BY created_at DESC
                """,
                (estado,)
            )
            return [_map_oc_cabecera_row(row) for row in cursor.fetchall()]
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
                SELECT oc_id, despacho_id, pedido_id, proveedor, fecha_generacion,
                       estado, numero_oc_sap, doc_entry, referencia_despacho, codigo_bodega, created_at,
                       respuesta_sap, fecha_procesado, error_message, error_code, error_source, updated_at
                FROM orden_compra_cabecera
                ORDER BY created_at DESC
                """
            )
            return [_map_oc_cabecera_row(row) for row in cursor.fetchall()]
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
                SELECT oc_id, despacho_id, pedido_id, proveedor, fecha_generacion,
                       estado, numero_oc_sap, doc_entry, referencia_despacho, codigo_bodega, created_at,
                       respuesta_sap, fecha_procesado, error_message, error_code, error_source, updated_at
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
                "despacho_id": str(result[1]) if result[1] else None,
                "pedido_id": str(result[2]) if result[2] else None,
                "proveedor": result[3],
                "fecha_generacion": serialize_date(result[4]),
                "estado": result[5],
                "numero_oc_sap": result[6],
                "doc_num": result[6],  # Número de documento SAP (para modal y tabla en frontend)
                "doc_entry": result[7],
                "referencia_despacho": result[8],
                "codigo_bodega": result[9],
                "created_at": serialize_date(result[10]),
                "respuesta_sap": result[11],
                "fecha_procesado": serialize_date(result[12]),
                "error_message": result[13],
                "error_code": result[14],
                "error_source": result[15],
                "updated_at": serialize_date(result[16]),
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
            # Incluir estado, numero_oc_sap, codigo_bodega y nuevos campos de respuesta SAP si están presentes
            sql = """
            UPDATE orden_compra_cabecera SET
                proveedor = ?,
                fecha_generacion = ?,
                referencia_despacho = ?,
                codigo_bodega = ?,
                estado = ?,
                numero_oc_sap = ?,
                respuesta_sap = ?,
                fecha_procesado = ?,
                error_message = ?,
                error_code = ?,
                error_source = ?,
                updated_at = ?
            WHERE oc_id = ?
            """
            
            values = (
                merged.get("proveedor"),
                merged.get("fecha_generacion"),
                merged.get("referencia_despacho"),
                merged.get("codigo_bodega"),  # Puede ser None
                merged.get("estado"),  # Puede ser None, se preservará el existente
                merged.get("numero_oc_sap"),  # Puede ser None
                merged.get("respuesta_sap"),  # Puede ser None
                merged.get("fecha_procesado"),  # Puede ser None
                merged.get("error_message"),  # Puede ser None
                merged.get("error_code"),  # Puede ser None
                merged.get("error_source"),  # Puede ser None
                ahora_naive(),
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
    
    def update_estado(
        self, 
        oc_id: str, 
        estado: str, 
        numero_oc_sap: Optional[str] = None,
        doc_entry: Optional[int] = None,
        respuesta_sap: Optional[str] = None,
        error_message: Optional[str] = None,
        error_code: Optional[str] = None,
        error_source: Optional[str] = None,
        audit_context: Optional["AuditContext"] = None
    ) -> bool:
        """
        Actualiza el estado de una orden de compra y respuesta de SAP.
        
        Método helper para cambiar el estado de una OC fácilmente.
        Útil para cuando se implemente la integración con SAP.
        
        Args:
            oc_id: UUID de la orden de compra
            estado: Nuevo estado (PENDIENTE, ENVIADA, CONFIRMADA, ERROR, etc.)
            numero_oc_sap: Número de OC asignado por SAP (opcional)
            doc_entry: DocEntry de SAP (ID interno) (opcional)
            respuesta_sap: Mensaje o respuesta de SAP (opcional)
            error_message: Mensaje de error si falla (opcional)
            error_code: Código de error de SAP (opcional)
            error_source: Origen del error (SAP, BACKEND, SAP_CONNECTION) (opcional)
            audit_context: Contexto de auditoría opcional (Buenas Prácticas - Sección 3)
            
        Returns:
            True si se actualizó correctamente, False en caso contrario
        """
        cursor = self.conn.cursor()
        
        try:
            # Construir SQL dinámicamente según campos proporcionados
            set_clauses = ["estado = ?", "updated_at = ?"]
            values: List[Any] = [estado, ahora_naive()]
            
            # Siempre actualizar fecha_procesado cuando se cambia el estado
            set_clauses.append("fecha_procesado = ?")
            values.append(ahora_naive())
            
            # Campos de auditoría (Buenas Prácticas - Sección 3)
            if audit_context:
                set_clauses.append("modificado_por = ?")
                values.append(audit_context.get_modificado_por())
                set_clauses.append("modificado_fecha = ?")
                values.append(ahora_naive())
            
            if numero_oc_sap is not None:
                set_clauses.append("numero_oc_sap = ?")
                values.append(numero_oc_sap)
            
            if doc_entry is not None:
                set_clauses.append("doc_entry = ?")
                values.append(doc_entry)
            
            if respuesta_sap is not None:
                set_clauses.append("respuesta_sap = ?")
                values.append(respuesta_sap)
            
            if error_message is not None:
                set_clauses.append("error_message = ?")
                values.append(error_message)
            
            if error_code is not None:
                set_clauses.append("error_code = ?")
                values.append(error_code)
            
            if error_source is not None:
                set_clauses.append("error_source = ?")
                values.append(error_source)
            
            # Si es estado ENVIADA, limpiar campos de error
            if estado == "ENVIADA":
                set_clauses.extend([
                    "error_message = NULL",
                    "error_code = NULL",
                    "error_source = NULL"
                ])
            
            sql = f"""
            UPDATE orden_compra_cabecera SET
                {', '.join(set_clauses)}
            WHERE oc_id = ?
            """
            
            values.append(oc_id)
            
            cursor.execute(sql, values)
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.info(f"✅ Estado de OC actualizado: {oc_id} → {estado}" + 
                          (f" (SAP: DocNum={numero_oc_sap}, DocEntry={doc_entry})" if numero_oc_sap or doc_entry else ""))
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
    
    def update_sap_refs(
        self,
        oc_id: str,
        doc_entry: Optional[int] = None,
        doc_num: Optional[str] = None
    ) -> bool:
        """
        Actualiza referencias de SAP (DocEntry y DocNum) en una orden de compra.
        
        Args:
            oc_id: UUID de la orden de compra
            doc_entry: DocEntry de SAP (ID interno)
            doc_num: DocNum de SAP (número visible)
            
        Returns:
            True si se actualizó correctamente, False en caso contrario
        """
        cursor = self.conn.cursor()
        
        try:
            set_clauses = ["updated_at = ?"]
            values: List[Any] = [ahora_naive()]
            
            if doc_entry is not None:
                set_clauses.append("doc_entry = ?")
                values.append(doc_entry)
            
            if doc_num is not None:
                set_clauses.append("numero_oc_sap = ?")
                values.append(doc_num)
            
            if len(values) == 1:
                # No hay nada que actualizar
                return False
            
            sql = f"""
            UPDATE orden_compra_cabecera SET
                {', '.join(set_clauses)}
            WHERE oc_id = ?
            """
            
            values.append(oc_id)
            
            cursor.execute(sql, values)
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.info(
                    f"✅ Referencias SAP actualizadas: {oc_id} → "
                    f"DocEntry={doc_entry}, DocNum={doc_num}"
                )
                return True
            else:
                logger.warning(f"⚠️ No se encontró OC para actualizar referencias SAP: {oc_id}")
                return False
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar referencias SAP: {e}")
            logger.error(f"   OC ID: {oc_id}, DocEntry: {doc_entry}, DocNum: {doc_num}")
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
                       referencia_detalle, precio_unitario, total_linea, cantidad_origen, codigo_bodega
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
                    "codigo_bodega": row[9] if len(row) > 9 and row[9] else None,  # ⭐ NUEVO: Devolver bodega por línea
                    # created_at y updated_at no existen en la tabla, se omiten
                })
            
            return detalles
        finally:
            cursor.close()
    
    def update_sku_detalle(
        self,
        oc_detalle_id: str,
        nuevo_sku_sap: str,
        validar_existencia: bool = True
    ) -> bool:
        """
        Actualiza el SKU de un detalle de orden de compra.
        
        Args:
            oc_detalle_id: UUID del detalle de orden de compra a actualizar
            nuevo_sku_sap: Nuevo SKU (ItemCode) de SAP
            validar_existencia: Si True, valida que el detalle exista antes de actualizar
            
        Returns:
            True si se actualizó correctamente, False si no se encontró el detalle
            
        Raises:
            ValueError: Si el nuevo SKU está vacío o es inválido
        """
        if not nuevo_sku_sap or not nuevo_sku_sap.strip():
            raise ValueError("El nuevo SKU no puede estar vacío")
        
        nuevo_sku_sap = nuevo_sku_sap.strip()
        
        # Validar longitud
        if len(nuevo_sku_sap) > 50:
            raise ValueError(f"El SKU excede la longitud máxima (50 caracteres): {len(nuevo_sku_sap)}")
        
        cursor = self.conn.cursor()
        
        try:
            # Validar que el detalle exista si se requiere
            if validar_existencia:
                cursor.execute(
                    """
                    SELECT oc_detalle_id, oc_id, sku_sap
                    FROM orden_compra_detalle
                    WHERE oc_detalle_id = ?
                    """,
                    (oc_detalle_id,)
                )
                detalle_existente = cursor.fetchone()
                
                if not detalle_existente:
                    logger.warning(f"⚠️ No se encontró detalle con ID: {oc_detalle_id}")
                    return False
                
                oc_id = detalle_existente[1]
                sku_anterior = detalle_existente[2]
                
                logger.info(f"📝 Actualizando SKU en detalle {oc_detalle_id}: '{sku_anterior}' → '{nuevo_sku_sap}'")
            else:
                # Obtener oc_id para logging
                cursor.execute(
                    "SELECT oc_id, sku_sap FROM orden_compra_detalle WHERE oc_detalle_id = ?",
                    (oc_detalle_id,)
                )
                detalle_existente = cursor.fetchone()
                if detalle_existente:
                    oc_id = detalle_existente[0]
                    sku_anterior = detalle_existente[1]
                else:
                    oc_id = None
                    sku_anterior = None
            
            # Actualizar el SKU
            cursor.execute(
                """
                UPDATE orden_compra_detalle
                SET sku_sap = ?,
                    updated_at = ?
                WHERE oc_detalle_id = ?
                """,
                (nuevo_sku_sap, ahora_naive(), oc_detalle_id)
            )
            
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.info(f"✅ SKU actualizado en detalle {oc_detalle_id[:8]}... (OC: {str(oc_id)[:8] if oc_id else 'N/A'}...)")
                return True
            else:
                logger.warning(f"⚠️ No se encontró detalle para actualizar: {oc_detalle_id}")
                return False
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar SKU en detalle: {e}")
            logger.error(f"   Detalle ID: {oc_detalle_id}, Nuevo SKU: {nuevo_sku_sap}")
            raise
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

