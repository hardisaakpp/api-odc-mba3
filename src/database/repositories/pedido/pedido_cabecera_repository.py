"""
Repositorio especializado para operaciones de pedido (cabecera).

CHANGELOG:
- 2026-01-23: Extraído de pedido_repository.py
"""

import logging
import pyodbc
from typing import Dict, Any, List, Optional
from datetime import date

from .pedido_utils import PedidoUtils

logger = logging.getLogger(__name__)


class PedidoCabeceraRepository:
    """Repositorio para operaciones de pedido (cabecera)."""

    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.

        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
        self.utils = PedidoUtils(conn)

    def insert(self, datos_cabecera: Dict[str, Any]) -> str:
        """
        Inserta un registro en pedido.
        
        Args:
            datos_cabecera: Diccionario con datos de cabecera (sin pedido_id)
            
        Returns:
            pedido_id (UUID) generado
            
        Raises:
            Exception: Si falla la inserción
        """
        datos_cabecera_normalizado = dict(datos_cabecera)
        
        if "fecha_pedido" in datos_cabecera_normalizado:
            datos_cabecera_normalizado["fecha_pedido"] = self.utils.normalizar_fecha(
                datos_cabecera_normalizado["fecha_pedido"]
            )
        
        if "fecha_entrega" in datos_cabecera_normalizado:
            fecha_entrega = datos_cabecera_normalizado["fecha_entrega"]
            if fecha_entrega is not None and not isinstance(fecha_entrega, str):
                datos_cabecera_normalizado["fecha_entrega"] = self.utils.normalizar_fecha(fecha_entrega)
        
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("SELECT NEWID()")
            uuid_result = cursor.fetchone()
            if uuid_result is None:
                raise ValueError("No se pudo generar UUID para pedido_id")
            pedido_id = str(uuid_result[0])
            
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            
            if tiene_estado:
                sql = """
                INSERT INTO pedido (
                    pedido_id,
                    numero_pedido,
                    fecha_pedido,
                    fecha_entrega,
                    forma_pago,
                    odc,
                    proveedor_nombre,
                    comprador_nombre,
                    comprador_codigo,
                    origen_traslado,
                    serie,
                    archivo_nombre,
                    creado_por,
                    estado,
                    creado_en
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
                """
                estado = datos_cabecera_normalizado.get("estado", "PENDIENTE_CONFIRMACION_PROVEEDOR")
                values = (
                    pedido_id,
                    datos_cabecera_normalizado.get("numero_pedido"),
                    datos_cabecera_normalizado.get("fecha_pedido"),
                    datos_cabecera_normalizado.get("fecha_entrega"),
                    datos_cabecera_normalizado.get("forma_pago"),
                    datos_cabecera_normalizado.get("odc"),
                    datos_cabecera_normalizado.get("proveedor_nombre"),
                    datos_cabecera_normalizado.get("comprador_nombre"),
                    datos_cabecera_normalizado.get("comprador_codigo"),
                    datos_cabecera_normalizado.get("origen_traslado"),
                    datos_cabecera_normalizado.get("serie"),
                    datos_cabecera_normalizado.get("archivo_nombre"),
                    datos_cabecera_normalizado.get("creado_por"),
                    estado,
                )
            else:
                sql = """
                INSERT INTO pedido (
                    pedido_id,
                    numero_pedido,
                    fecha_pedido,
                    fecha_entrega,
                    forma_pago,
                    odc,
                    proveedor_nombre,
                    comprador_nombre,
                    comprador_codigo,
                    origen_traslado,
                    serie,
                    archivo_nombre,
                    creado_por,
                    creado_en
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
                """
                values = (
                    pedido_id,
                    datos_cabecera_normalizado.get("numero_pedido"),
                    datos_cabecera_normalizado.get("fecha_pedido"),
                    datos_cabecera_normalizado.get("fecha_entrega"),
                    datos_cabecera_normalizado.get("forma_pago"),
                    datos_cabecera_normalizado.get("odc"),
                    datos_cabecera_normalizado.get("proveedor_nombre"),
                    datos_cabecera_normalizado.get("comprador_nombre"),
                    datos_cabecera_normalizado.get("comprador_codigo"),
                    datos_cabecera_normalizado.get("origen_traslado"),
                    datos_cabecera_normalizado.get("serie"),
                    datos_cabecera_normalizado.get("archivo_nombre"),
                    datos_cabecera_normalizado.get("creado_por"),
                )
            
            cursor.execute(sql, values)
            self.conn.commit()
            
            logger.debug(f"✅ Pedido cabecera insertada: {pedido_id} - Pedido: {datos_cabecera_normalizado.get('numero_pedido')}")
            return pedido_id
            
        except pyodbc.IntegrityError as e:
            self.conn.rollback()
            if "UQ_pedido_numero_pedido" in str(e):
                numero_pedido = datos_cabecera.get('numero_pedido')
                raise ValueError(
                    f"El número de pedido '{numero_pedido}' ya existe en el sistema. "
                    f"No es posible cargar un pedido con un número de pedido duplicado. "
                    f"Por favor, verifica el número de pedido e intenta con un número diferente."
                )
            raise
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar pedido: {e}")
            logger.error(f"   Número pedido: {datos_cabecera.get('numero_pedido')}")
            raise
        finally:
            cursor.close()

    def get_pedido_completo(self, pedido_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un pedido completo con cabecera, detalles, tiendas y distribuciones.
        
        Args:
            pedido_id: UUID del pedido
            
        Returns:
            Dict con cabecera, detalles (con sus tiendas), o None si no existe
        """
        cursor = self.conn.cursor()
        
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            
            if tiene_estado:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, estado, creado_en
                    FROM pedido
                    WHERE pedido_id = ?
                """, (pedido_id,))
            else:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, creado_en
                    FROM pedido
                    WHERE pedido_id = ?
                """, (pedido_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            cabecera = self.utils.construir_cabecera_desde_row(row, tiene_estado)
            detalles = self.utils.obtener_detalles_pedido(cursor, pedido_id)
            
            return {
                "cabecera": cabecera,
                "detalles": detalles
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener pedido completo: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def get_pedido_completo_por_numero(self, numero_pedido: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un pedido completo con cabecera, detalles, tiendas y distribuciones por número de pedido.
        
        Args:
            numero_pedido: Número de pedido (business key)
            
        Returns:
            Dict con cabecera, detalles (con sus tiendas), o None si no existe
        """
        cursor = self.conn.cursor()
        
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            
            if tiene_estado:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, estado, creado_en
                    FROM pedido
                    WHERE numero_pedido = ?
                """, (numero_pedido,))
            else:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, creado_en
                    FROM pedido
                    WHERE numero_pedido = ?
                """, (numero_pedido,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            pedido_id = str(row[0])
            cabecera = self.utils.construir_cabecera_desde_row(row, tiene_estado)
            detalles = self.utils.obtener_detalles_pedido(cursor, pedido_id)
            
            return {
                "cabecera": cabecera,
                "detalles": detalles
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener pedido completo por número: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def update_estado(self, pedido_id: str, estado: str) -> bool:
        """
        Actualiza el estado de un pedido.
        
        Args:
            pedido_id: UUID del pedido
            estado: Nuevo estado
            
        Returns:
            True si se actualizó correctamente, False si no existe el pedido o no hay columna estado
        """
        cursor = self.conn.cursor()
        
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            
            if not tiene_estado:
                logger.warning("⚠️ Columna 'estado' no existe en tabla pedido. Ejecute el script add_estado_pedido.sql")
                return False
            
            cursor.execute("""
                UPDATE pedido 
                SET estado = ?
                WHERE pedido_id = ?
            """, (estado, pedido_id))
            
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.debug(f"✅ Estado actualizado para pedido {pedido_id}: {estado}")
                return True
            else:
                logger.warning(f"⚠️ No se encontró pedido con ID: {pedido_id}")
                return False
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar estado del pedido: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def update(self, pedido_id: str, datos_cabecera: Dict[str, Any]) -> bool:
        """
        Actualiza la cabecera de un pedido.
        
        Si algún campo en datos_cabecera es None, se preserva el valor existente.
        No se puede modificar: pedido_id, numero_pedido (business key), creado_por, creado_en.
        
        Args:
            pedido_id: UUID del pedido
            datos_cabecera: Diccionario con datos actualizados (sin pedido_id)
            
        Returns:
            True si se actualizó correctamente, False si no existe el pedido
        """
        cursor = self.conn.cursor()
        
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            
            if tiene_estado:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, estado
                    FROM pedido
                    WHERE pedido_id = ?
                """, (pedido_id,))
            else:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por
                    FROM pedido
                    WHERE pedido_id = ?
                """, (pedido_id,))
            
            row = cursor.fetchone()
            if not row:
                logger.warning(f"⚠️ No se encontró pedido para actualizar: {pedido_id}")
                return False
            
            existing = {
                "fecha_pedido": row[2].isoformat() if row[2] else None,
                "fecha_entrega": row[3],
                "forma_pago": row[4],
                "odc": row[5],
                "proveedor_nombre": row[6],
                "comprador_nombre": row[7],
                "comprador_codigo": row[8],
                "origen_traslado": row[9],
                "serie": row[10],
                "archivo_nombre": row[11],
            }
            if tiene_estado:
                existing["estado"] = row[13]
            
            merged = {}
            for key in existing.keys():
                new_value = datos_cabecera.get(key)
                if new_value is not None:
                    merged[key] = new_value
                else:
                    merged[key] = existing[key]
            
            if "fecha_pedido" in merged and merged["fecha_pedido"] is not None:
                fp = merged["fecha_pedido"]
                if isinstance(fp, date):
                    merged["fecha_pedido"] = fp.isoformat()
            
            if tiene_estado:
                sql = """
                UPDATE pedido SET
                    fecha_pedido = ?,
                    fecha_entrega = ?,
                    forma_pago = ?,
                    odc = ?,
                    proveedor_nombre = ?,
                    comprador_nombre = ?,
                    comprador_codigo = ?,
                    origen_traslado = ?,
                    serie = ?,
                    estado = ?
                WHERE pedido_id = ?
                """
                values = (
                    merged.get("fecha_pedido"),
                    merged.get("fecha_entrega"),
                    merged.get("forma_pago"),
                    merged.get("odc"),
                    merged.get("proveedor_nombre"),
                    merged.get("comprador_nombre"),
                    merged.get("comprador_codigo"),
                    merged.get("origen_traslado"),
                    merged.get("serie"),
                    merged.get("estado"),
                    pedido_id,
                )
            else:
                sql = """
                UPDATE pedido SET
                    fecha_pedido = ?,
                    fecha_entrega = ?,
                    forma_pago = ?,
                    odc = ?,
                    proveedor_nombre = ?,
                    comprador_nombre = ?,
                    comprador_codigo = ?,
                    origen_traslado = ?,
                    serie = ?
                WHERE pedido_id = ?
                """
                values = (
                    merged.get("fecha_pedido"),
                    merged.get("fecha_entrega"),
                    merged.get("forma_pago"),
                    merged.get("odc"),
                    merged.get("proveedor_nombre"),
                    merged.get("comprador_nombre"),
                    merged.get("comprador_codigo"),
                    merged.get("origen_traslado"),
                    merged.get("serie"),
                    pedido_id,
                )
            
            cursor.execute(sql, values)
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.debug(f"✅ Pedido cabecera actualizada: {pedido_id}")
                return True
            else:
                logger.warning(f"⚠️ No se encontró pedido para actualizar: {pedido_id}")
                return False
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar cabecera del pedido: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def get_by_estado(self, estado: str) -> List[Dict[str, Any]]:
        """
        Obtiene todos los pedidos con un estado específico.
        
        Args:
            estado: Estado a filtrar
            
        Returns:
            Lista de diccionarios con datos de pedidos
        """
        cursor = self.conn.cursor()
        
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            
            if not tiene_estado:
                logger.warning("⚠️ Columna 'estado' no existe en tabla pedido")
                return []
            
            cursor.execute("""
                SELECT 
                    pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                    forma_pago, odc, proveedor_nombre, comprador_nombre,
                    comprador_codigo, origen_traslado, serie, archivo_nombre,
                    creado_por, estado, creado_en
                FROM pedido
                WHERE estado = ?
                ORDER BY creado_en DESC
            """, (estado,))
            
            pedidos = []
            for row in cursor.fetchall():
                pedidos.append({
                    "pedido_id": str(row[0]),
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "odc": row[5],
                    "proveedor_nombre": row[6],
                    "comprador_nombre": row[7],
                    "comprador_codigo": row[8],
                    "origen_traslado": row[9],
                    "serie": row[10],
                    "archivo_nombre": row[11],
                    "creado_por": row[12],
                    "estado": row[13],
                    "creado_en": row[14].isoformat() if row[14] else None,
                })
            
            return pedidos
            
        except Exception as e:
            logger.error(f"❌ Error al obtener pedidos por estado: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def get_pedidos_con_filtros(
        self,
        estado: Optional[str] = None,
        fecha_desde: Optional[str] = None,
        fecha_hasta: Optional[str] = None,
        proveedor_nombre: Optional[str] = None,
        numero_pedido: Optional[str] = None,
        creado_por: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Obtiene pedidos con filtros y paginación.
        
        Args:
            estado: Estado del pedido
            fecha_desde: Fecha desde (YYYY-MM-DD)
            fecha_hasta: Fecha hasta (YYYY-MM-DD)
            proveedor_nombre: Nombre del proveedor (búsqueda parcial)
            numero_pedido: Número de pedido (búsqueda exacta o parcial)
            creado_por: Usuario que creó el pedido
            limit: Límite de registros
            offset: Offset para paginación
        
        Returns:
            Dict con lista de pedidos y metadata
        """
        cursor = self.conn.cursor()
        
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            
            where_conditions = []
            params = []
            
            if tiene_estado and estado:
                where_conditions.append("p.estado = ?")
                params.append(estado)
            
            if fecha_desde:
                where_conditions.append("CAST(p.fecha_pedido AS DATE) >= CAST(? AS DATE)")
                params.append(fecha_desde)
            
            if fecha_hasta:
                where_conditions.append("CAST(p.fecha_pedido AS DATE) <= CAST(? AS DATE)")
                params.append(fecha_hasta)
            
            if proveedor_nombre:
                where_conditions.append("p.proveedor_nombre LIKE ?")
                params.append(f"%{proveedor_nombre}%")
            
            if numero_pedido:
                where_conditions.append("p.numero_pedido LIKE ?")
                params.append(f"%{numero_pedido}%")
            
            if creado_por:
                where_conditions.append("p.creado_por = ?")
                params.append(creado_por)
            
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            
            count_query = f"SELECT COUNT(*) FROM pedido p WHERE {where_clause}"
            cursor.execute(count_query, params)
            result = cursor.fetchone()
            total = result[0] if result else 0
            
            select_fields = """
                p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                p.forma_pago, p.odc, p.proveedor_nombre, p.comprador_nombre,
                p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                p.creado_por, p.creado_en
            """
            
            if tiene_estado:
                select_fields += ", p.estado"
            
            data_query = f"""
                SELECT {select_fields}
                FROM pedido p
                WHERE {where_clause}
                ORDER BY p.creado_en DESC
            """
            
            if limit is not None:
                data_query += f" OFFSET {offset or 0} ROWS FETCH NEXT {limit} ROWS ONLY"
            
            cursor.execute(data_query, params)
            
            pedidos = []
            for row in cursor.fetchall():
                idx = 0
                pedido = {
                    "pedido_id": str(row[idx]),
                    "numero_pedido": row[idx + 1],
                    "fecha_pedido": row[idx + 2].isoformat() if row[idx + 2] else None,
                    "fecha_entrega": row[idx + 3],
                    "forma_pago": row[idx + 4],
                    "odc": row[idx + 5],
                    "proveedor_nombre": row[idx + 6],
                    "comprador_nombre": row[idx + 7],
                    "comprador_codigo": row[idx + 8],
                    "origen_traslado": row[idx + 9],
                    "serie": row[idx + 10],
                    "archivo_nombre": row[idx + 11],
                    "creado_por": row[idx + 12],
                    "creado_en": row[idx + 13].isoformat() if row[idx + 13] else None,
                }
                
                if tiene_estado:
                    pedido["estado"] = row[idx + 14]
                else:
                    pedido["estado"] = None
                
                pedidos.append(pedido)
            
            has_more = (offset or 0) + len(pedidos) < total if limit else False
            
            return {
                "data": pedidos,
                "total": total,
                "limit": limit,
                "offset": offset or 0,
                "has_more": has_more
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener pedidos con filtros: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def get_pedidos_confirmados(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        solo_redistribucion_confirmada: bool = False
    ) -> Dict[str, Any]:
        """
        Obtiene pedidos en estado confirmado, ordenados por creado_en DESC,
        para uso en pantalla Redistribución.

        Args:
            limit: Límite de registros (ej: 1 para "último confirmado")
            offset: Offset para paginación
            solo_redistribucion_confirmada: Si True, solo pedidos con estado
                PEDIDO_CONFIRMADO (redistribución ya confirmada). Si False,
                incluye CONFIRMADO_PROVEEDOR y PEDIDO_CONFIRMADO.

        Returns:
            Dict con "data", "total", "limit", "offset", "has_more"
        """
        cursor = self.conn.cursor()
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            if not tiene_estado:
                return {"data": [], "total": 0, "limit": limit, "offset": offset or 0, "has_more": False}

            if solo_redistribucion_confirmada:
                where_clause = "p.estado = ?"
                params_list: List[Any] = ["PEDIDO_CONFIRMADO"]
            else:
                where_clause = "p.estado IN (?, ?)"
                params_list = ["CONFIRMADO_PROVEEDOR", "PEDIDO_CONFIRMADO"]
            params: List[Any] = list(params_list)

            count_query = f"SELECT COUNT(*) FROM pedido p WHERE {where_clause}"
            cursor.execute(count_query, params)
            result = cursor.fetchone()
            total = result[0] if result else 0

            select_fields = """
                p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                p.forma_pago, p.odc, p.proveedor_nombre, p.comprador_nombre,
                p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                p.creado_por, p.creado_en, p.estado
            """
            data_query = f"""
                SELECT {select_fields}
                FROM pedido p
                WHERE {where_clause}
                ORDER BY p.creado_en DESC
            """
            if limit is not None:
                data_query += f" OFFSET {offset or 0} ROWS FETCH NEXT {limit} ROWS ONLY"

            cursor.execute(data_query, params)
            pedidos = []
            for row in cursor.fetchall():
                idx = 0
                pedido = {
                    "pedido_id": str(row[idx]),
                    "numero_pedido": row[idx + 1],
                    "fecha_pedido": row[idx + 2].isoformat() if row[idx + 2] else None,
                    "fecha_entrega": row[idx + 3],
                    "forma_pago": row[idx + 4],
                    "odc": row[idx + 5],
                    "proveedor_nombre": row[idx + 6],
                    "comprador_nombre": row[idx + 7],
                    "comprador_codigo": row[idx + 8],
                    "origen_traslado": row[idx + 9],
                    "serie": row[idx + 10],
                    "archivo_nombre": row[idx + 11],
                    "creado_por": row[idx + 12],
                    "creado_en": row[idx + 13].isoformat() if row[idx + 13] else None,
                    "estado": row[idx + 14],
                }
                pedidos.append(pedido)

            has_more = (offset or 0) + len(pedidos) < total if limit else False
            return {
                "data": pedidos,
                "total": total,
                "limit": limit,
                "offset": offset or 0,
                "has_more": has_more,
            }
        except Exception as e:
            logger.error(f"❌ Error al obtener pedidos confirmados: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def existe_numero_pedido(self, numero_pedido: str) -> bool:
        """
        Verifica si un número de pedido ya existe en el sistema.
        
        Args:
            numero_pedido: Número del pedido a verificar
            
        Returns:
            True si el número de pedido ya existe, False si no existe
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM pedido 
                WHERE numero_pedido = ?
            """, (numero_pedido,))
            
            row = cursor.fetchone()
            count = row[0] if row else 0
            
            existe = count > 0
            if existe:
                logger.debug(f"✓ Número de pedido '{numero_pedido}' YA EXISTE en el sistema")
            else:
                logger.debug(f"✓ Número de pedido '{numero_pedido}' disponible (no existe)")
            
            return existe
            
        except Exception as e:
            logger.error(f"❌ Error al verificar existencia de número de pedido '{numero_pedido}': {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def get_ultimo_pedido(self, usuario_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el último pedido cargado por un usuario específico.
        
        Args:
            usuario_id: ID del usuario autenticado (creado_por)
        
        Returns:
            Dict con datos básicos del último pedido del usuario
            o None si el usuario no tiene pedidos
        """
        cursor = self.conn.cursor()
        
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            
            if tiene_estado:
                cursor.execute("""
                    SELECT TOP 1
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, estado, creado_en
                    FROM pedido
                    WHERE creado_por = ?
                    ORDER BY creado_en DESC
                """, (usuario_id,))
            else:
                cursor.execute("""
                    SELECT TOP 1
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, creado_en
                    FROM pedido
                    WHERE creado_por = ?
                    ORDER BY creado_en DESC
                """, (usuario_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            if tiene_estado:
                return {
                    "pedido_id": str(row[0]),
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "odc": row[5],
                    "proveedor_nombre": row[6],
                    "comprador_nombre": row[7],
                    "comprador_codigo": row[8],
                    "origen_traslado": row[9],
                    "serie": row[10],
                    "archivo_nombre": row[11],
                    "creado_por": row[12],
                    "estado": row[13],
                    "creado_en": row[14].isoformat() if row[14] else None,
                }
            else:
                return {
                    "pedido_id": str(row[0]),
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "odc": row[5],
                    "proveedor_nombre": row[6],
                    "comprador_nombre": row[7],
                    "comprador_codigo": row[8],
                    "origen_traslado": row[9],
                    "serie": row[10],
                    "archivo_nombre": row[11],
                    "creado_por": row[12],
                    "creado_en": row[13].isoformat() if row[13] else None,
                }
                
        except Exception as e:
            logger.error(f"❌ Error al obtener último pedido del usuario {usuario_id}: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def get_ultimo_pedido_respuesta_proveedor_cargada(
        self, usuario_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene el último pedido con estado RESPUESTA_PROVEEDOR_CARGADA.
        Misma lógica que get_ultimo_pedido pero filtrado por ese estado;
        usado en la pantalla Redistribución para cargar el último listo para redistribuir.

        Args:
            usuario_id: Si se indica, solo pedidos creados por ese usuario.
                       Si None, último en todo el sistema (creado_en DESC).

        Returns:
            Dict con datos básicos del pedido o None si no hay ninguno en ese estado.
        """
        cursor = self.conn.cursor()
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            if not tiene_estado:
                return None

            if usuario_id is not None:
                cursor.execute("""
                    SELECT TOP 1
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, estado, creado_en
                    FROM pedido
                    WHERE estado = ? AND creado_por = ?
                    ORDER BY creado_en DESC
                """, ("RESPUESTA_PROVEEDOR_CARGADA", usuario_id))
            else:
                cursor.execute("""
                    SELECT TOP 1
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, estado, creado_en
                    FROM pedido
                    WHERE estado = ?
                    ORDER BY creado_en DESC
                """, ("RESPUESTA_PROVEEDOR_CARGADA",))

            row = cursor.fetchone()
            if not row:
                return None

            return {
                "pedido_id": str(row[0]),
                "numero_pedido": row[1],
                "fecha_pedido": row[2].isoformat() if row[2] else None,
                "fecha_entrega": row[3],
                "forma_pago": row[4],
                "odc": row[5],
                "proveedor_nombre": row[6],
                "comprador_nombre": row[7],
                "comprador_codigo": row[8],
                "origen_traslado": row[9],
                "serie": row[10],
                "archivo_nombre": row[11],
                "creado_por": row[12],
                "estado": row[13],
                "creado_en": row[14].isoformat() if row[14] else None,
            }
        except Exception as e:
            logger.error(
                "❌ Error al obtener último pedido RESPUESTA_PROVEEDOR_CARGADA: %s", e, exc_info=True
            )
            raise
        finally:
            cursor.close()

    def tiene_pedidos(self) -> bool:
        """
        Verifica si existe al menos un pedido en la base de datos.
        
        Returns:
            True si hay al menos un pedido, False si no hay pedidos
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM pedido
            """)
            
            row = cursor.fetchone()
            count = row[0] if row else 0
            
            tiene_pedidos = count > 0
            logger.debug(f"✓ Verificación de pedidos: {count} pedido(s) encontrado(s)")
            
            return tiene_pedidos
            
        except Exception as e:
            logger.error(f"❌ Error al verificar existencia de pedidos: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
