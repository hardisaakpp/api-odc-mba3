"""
Repositorio especializado para operaciones de pedido (cabecera).

CHANGELOG:
- 2026-02-06: Bitácora de transiciones de estado (pedido_estado_historial) en update_estado()
- 2026-02-06: Agregado soporte para campos de auditoría (origen, ip_origen, modificado_por, modificado_fecha)
- 2026-01-23: Extraído de pedido_repository.py
"""

import logging
import pyodbc
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from datetime import date, datetime

from src.utils.timezone import ahora_naive

from .pedido_utils import PedidoUtils, clamp_pedido_mensaje

from src.database.pedido_estados import (
    ESTADO_BORRADOR,
    ESTADO_REDISTRIBUCION,
    ESTADO_CONFIRMADO_PROVEEDOR,
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_CONFIRMADO_ENVIADO,
    ESTADO_DESPACHAR_Y_FACTURAR,
    ESTADO_FINALIZADO,
    ESTADO_CANCELADO,
    ESTADO_CANCELADO_POR_EL_RAYO,
    estado_id_desde_legacy,
)

# Import para type hints sin dependencia circular
if TYPE_CHECKING:
    from src.utils.audit_context import AuditContext

from src.database.services.audit_log_service import AuditLogService

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

    def insert(self, datos_cabecera: Dict[str, Any], audit_context: Optional["AuditContext"] = None) -> str:
        """
        Inserta un registro en pedido.
        
        Args:
            datos_cabecera: Diccionario con datos de cabecera (sin pedido_id)
                Puede incluir campos de auditoría: origen, ip_origen
            audit_context: Contexto de auditoría opcional (Buenas Prácticas - Sección 3)
            
        Returns:
            pedido_id (UUID) generado
            
        Raises:
            Exception: Si falla la inserción
        """
        datos_cabecera_normalizado = dict(datos_cabecera)
        
        # Aplicar campos de auditoría si se proporciona contexto
        if audit_context:
            if not datos_cabecera_normalizado.get("creado_por"):
                datos_cabecera_normalizado["creado_por"] = audit_context.get_creado_por()
            if not datos_cabecera_normalizado.get("origen"):
                datos_cabecera_normalizado["origen"] = audit_context.origen
            if not datos_cabecera_normalizado.get("ip_origen"):
                datos_cabecera_normalizado["ip_origen"] = audit_context.ip_origen
        
        if "fecha_pedido" in datos_cabecera_normalizado:
            datos_cabecera_normalizado["fecha_pedido"] = self.utils.normalizar_fecha(
                datos_cabecera_normalizado["fecha_pedido"]
            )
        
        if "fecha_entrega" in datos_cabecera_normalizado:
            fecha_entrega = datos_cabecera_normalizado["fecha_entrega"]
            if fecha_entrega is not None and not isinstance(fecha_entrega, str):
                datos_cabecera_normalizado["fecha_entrega"] = self.utils.normalizar_fecha(fecha_entrega)

        cursor = self.conn.cursor()
        max_mensaje = self.utils.get_mensaje_column_max_len(cursor, "pedido")
        if "mensaje" in datos_cabecera_normalizado:
            datos_cabecera_normalizado["mensaje"] = clamp_pedido_mensaje(
                datos_cabecera_normalizado.get("mensaje"),
                max_length=max_mensaje,
            )

        try:
            cursor.execute("SELECT NEWID()")
            uuid_result = cursor.fetchone()
            if uuid_result is None:
                raise ValueError("No se pudo generar UUID para pedido_id")
            pedido_id = str(uuid_result[0])
            
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            tiene_estado_id = self.utils.tiene_columna_estado_id(cursor)

            if tiene_estado_id:
                estado_id = datos_cabecera_normalizado.get("estado_id", ESTADO_BORRADOR)
                if isinstance(estado_id, str):
                    estado_id = estado_id_desde_legacy(estado_id)
                # SQL con campos de auditoría (origen, ip_origen) - Buenas Prácticas Sección 3
                sql = """
                INSERT INTO pedido (
                    pedido_id,
                    numero_pedido,
                    fecha_pedido,
                    fecha_entrega,
                    forma_pago,
                    mensaje,
                    proveedor_nombre,
                    comprador_nombre,
                    comprador_codigo,
                    origen_traslado,
                    serie,
                    archivo_nombre,
                    creado_por,
                    estado_id,
                    origen,
                    ip_origen,
                    creado_en,
                    modificado_por,
                    modificado_fecha
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                _ahora = ahora_naive()
                values = (
                    pedido_id,
                    datos_cabecera_normalizado.get("numero_pedido"),
                    datos_cabecera_normalizado.get("fecha_pedido"),
                    datos_cabecera_normalizado.get("fecha_entrega"),
                    datos_cabecera_normalizado.get("forma_pago"),
                    datos_cabecera_normalizado.get("mensaje"),
                    datos_cabecera_normalizado.get("proveedor_nombre"),
                    datos_cabecera_normalizado.get("comprador_nombre"),
                    datos_cabecera_normalizado.get("comprador_codigo"),
                    datos_cabecera_normalizado.get("origen_traslado"),
                    datos_cabecera_normalizado.get("serie"),
                    datos_cabecera_normalizado.get("archivo_nombre"),
                    datos_cabecera_normalizado.get("creado_por"),
                    estado_id,
                    datos_cabecera_normalizado.get("origen"),  # Campo de auditoría
                    datos_cabecera_normalizado.get("ip_origen"),  # Campo de auditoría
                    _ahora,  # creado_en
                    datos_cabecera_normalizado.get("creado_por"),  # modificado_por = creado_por al crear
                    _ahora,  # modificado_fecha
                )
            elif tiene_estado:
                sql = """
                INSERT INTO pedido (
                    pedido_id,
                    numero_pedido,
                    fecha_pedido,
                    fecha_entrega,
                    forma_pago,
                    mensaje,
                    proveedor_nombre,
                    comprador_nombre,
                    comprador_codigo,
                    origen_traslado,
                    serie,
                    archivo_nombre,
                    creado_por,
                    estado,
                    creado_en,
                    modificado_por,
                    modificado_fecha
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                estado = datos_cabecera_normalizado.get("estado", "PENDIENTE_CONFIRMACION_PROVEEDOR")
                _ahora = ahora_naive()
                values = (
                    pedido_id,
                    datos_cabecera_normalizado.get("numero_pedido"),
                    datos_cabecera_normalizado.get("fecha_pedido"),
                    datos_cabecera_normalizado.get("fecha_entrega"),
                    datos_cabecera_normalizado.get("forma_pago"),
                    datos_cabecera_normalizado.get("mensaje"),
                    datos_cabecera_normalizado.get("proveedor_nombre"),
                    datos_cabecera_normalizado.get("comprador_nombre"),
                    datos_cabecera_normalizado.get("comprador_codigo"),
                    datos_cabecera_normalizado.get("origen_traslado"),
                    datos_cabecera_normalizado.get("serie"),
                    datos_cabecera_normalizado.get("archivo_nombre"),
                    datos_cabecera_normalizado.get("creado_por"),
                    estado,
                    _ahora,  # creado_en
                    datos_cabecera_normalizado.get("creado_por"),  # modificado_por = creado_por al crear
                    _ahora,  # modificado_fecha
                )
            else:
                sql = """
                INSERT INTO pedido (
                    pedido_id,
                    numero_pedido,
                    fecha_pedido,
                    fecha_entrega,
                    forma_pago,
                    mensaje,
                    proveedor_nombre,
                    comprador_nombre,
                    comprador_codigo,
                    origen_traslado,
                    serie,
                    archivo_nombre,
                    creado_por,
                    creado_en,
                    modificado_por,
                    modificado_fecha
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                _ahora = ahora_naive()
                values = (
                    pedido_id,
                    datos_cabecera_normalizado.get("numero_pedido"),
                    datos_cabecera_normalizado.get("fecha_pedido"),
                    datos_cabecera_normalizado.get("fecha_entrega"),
                    datos_cabecera_normalizado.get("forma_pago"),
                    datos_cabecera_normalizado.get("mensaje"),
                    datos_cabecera_normalizado.get("proveedor_nombre"),
                    datos_cabecera_normalizado.get("comprador_nombre"),
                    datos_cabecera_normalizado.get("comprador_codigo"),
                    datos_cabecera_normalizado.get("origen_traslado"),
                    datos_cabecera_normalizado.get("serie"),
                    datos_cabecera_normalizado.get("archivo_nombre"),
                    datos_cabecera_normalizado.get("creado_por"),
                    _ahora,  # creado_en
                    datos_cabecera_normalizado.get("creado_por"),  # modificado_por = creado_por al crear
                    _ahora,  # modificado_fecha
                )
            
            cursor.execute(sql, values)
            
            # Registrar creación inicial en pedido_estado_historial
            estado_inicial = (
                estado_id if tiene_estado_id
                else ESTADO_BORRADOR
            )
            self._registrar_transicion_estado(
                cursor, pedido_id,
                estado_anterior_id=None,
                estado_nuevo_id=estado_inicial,
                audit_context=audit_context,
            )
            
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
            Dict con cabecera, detalles (con sus tiendas), o None si no existe.
            Si el pedido está en estado CONFIRMADO_ENVIADO, incluye numero_oc_sap y doc_entry.
        """
        cursor = self.conn.cursor()
        
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            tiene_estado_id = self.utils.tiene_columna_estado_id(cursor)

            if tiene_estado_id:
                cursor.execute("""
                    SELECT 
                        p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                        p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
                        p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                        p.creado_por, p.estado_id, pe.nombre AS estado_nombre, p.creado_en,
                        p.modificado_por
                    FROM pedido p
                    LEFT JOIN pedido_estado pe ON pe.id = p.estado_id
                    WHERE p.pedido_id = ?
                """, (pedido_id,))
            elif tiene_estado:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, mensaje, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, estado, creado_en,
                        modificado_por
                    FROM pedido
                    WHERE pedido_id = ?
                """, (pedido_id,))
            else:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, mensaje, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, creado_en,
                        modificado_por
                    FROM pedido
                    WHERE pedido_id = ?
                """, (pedido_id,))

            row = cursor.fetchone()
            if not row:
                return None

            cabecera = self.utils.construir_cabecera_desde_row(
                row, tiene_estado or tiene_estado_id, tiene_estado_id
            )
            detalles = self.utils.obtener_detalles_pedido(cursor, pedido_id)
            
            # Si el pedido está en estado CONFIRMADO_ENVIADO, obtener datos de SAP
            estado_id = cabecera.get("estado_id")
            if estado_id == ESTADO_CONFIRMADO_ENVIADO:
                cabecera = self._agregar_datos_sap_a_cabecera(cursor, pedido_id, cabecera)
            
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
            Dict con cabecera, detalles (con sus tiendas), o None si no existe.
            Si el pedido está en estado CONFIRMADO_ENVIADO, incluye numero_oc_sap y doc_entry.
        """
        cursor = self.conn.cursor()
        
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            tiene_estado_id = self.utils.tiene_columna_estado_id(cursor)

            if tiene_estado_id:
                cursor.execute("""
                    SELECT 
                        p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                        p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
                        p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                        p.creado_por, p.estado_id, pe.nombre AS estado_nombre, p.creado_en,
                        p.modificado_por
                    FROM pedido p
                    LEFT JOIN pedido_estado pe ON pe.id = p.estado_id
                    WHERE p.numero_pedido = ?
                """, (numero_pedido,))
            elif tiene_estado:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, mensaje, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, estado, creado_en,
                        modificado_por
                    FROM pedido
                    WHERE numero_pedido = ?
                """, (numero_pedido,))
            else:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, mensaje, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, creado_en,
                        modificado_por
                    FROM pedido
                    WHERE numero_pedido = ?
                """, (numero_pedido,))

            row = cursor.fetchone()
            if not row:
                return None

            pedido_id = str(row[0])
            cabecera = self.utils.construir_cabecera_desde_row(
                row, tiene_estado or tiene_estado_id, tiene_estado_id
            )
            detalles = self.utils.obtener_detalles_pedido(cursor, pedido_id)
            
            # Si el pedido está en estado CONFIRMADO_ENVIADO, obtener datos de SAP
            estado_id = cabecera.get("estado_id")
            if estado_id == ESTADO_CONFIRMADO_ENVIADO:
                cabecera = self._agregar_datos_sap_a_cabecera(cursor, pedido_id, cabecera)
            
            return {
                "cabecera": cabecera,
                "detalles": detalles
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener pedido completo por número: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Cache: existencia de tabla pedido_estado_historial (una vez por conexión)
    # ------------------------------------------------------------------
    _tiene_historial: Optional[bool] = None

    def _tiene_tabla_historial(self, cursor: pyodbc.Cursor) -> bool:
        """Verifica si existe la tabla pedido_estado_historial (cacheado)."""
        if PedidoCabeceraRepository._tiene_historial is None:
            cursor.execute(
                "SELECT OBJECT_ID(N'[dbo].[pedido_estado_historial]', N'U')"
            )
            row = cursor.fetchone()
            PedidoCabeceraRepository._tiene_historial = row is not None and row[0] is not None
        return PedidoCabeceraRepository._tiene_historial

    def _registrar_transicion_estado(
        self,
        cursor: pyodbc.Cursor,
        pedido_id: str,
        estado_anterior_id: Optional[int],
        estado_nuevo_id: int,
        audit_context: Optional["AuditContext"] = None,
    ) -> None:
        """
        Inserta un registro en pedido_estado_historial.

        Solo se invoca cuando estado_anterior_id != estado_nuevo_id.
        Si la tabla no existe todavía, se omite silenciosamente.

        Args:
            cursor: Cursor activo (dentro de la misma transacción)
            pedido_id: UUID del pedido
            estado_anterior_id: Estado previo (None para creación inicial)
            estado_nuevo_id: Nuevo estado
            audit_context: Contexto de auditoría opcional
        """
        if not self._tiene_tabla_historial(cursor):
            return

        usuario = audit_context.get_modificado_por() if audit_context else None
        origen = audit_context.origen if audit_context else None
        ip_origen = audit_context.ip_origen if audit_context else None

        try:
            cursor.execute("""
                INSERT INTO pedido_estado_historial (
                    pedido_id,
                    estado_anterior_id,
                    estado_nuevo_id,
                    fecha_cambio,
                    usuario_cambio,
                    origen,
                    ip_origen,
                    accion
                ) VALUES (?, ?, ?, SYSUTCDATETIME(), ?, ?, ?, ?)
            """, (
                pedido_id,
                estado_anterior_id,
                estado_nuevo_id,
                usuario,
                origen,
                ip_origen,
                "MANUAL",
            ))
            logger.debug(
                f"📝 Historial: pedido {pedido_id} "
                f"estado {estado_anterior_id} → {estado_nuevo_id} "
                f"(usuario={usuario})"
            )
        except Exception as e:
            # No fallar la operación principal por un error de historial
            logger.warning(
                f"⚠️ No se pudo registrar historial de estado para pedido {pedido_id}: {e}"
            )

    def update_estado(
        self, 
        pedido_id: str, 
        estado: int | str,
        audit_context: Optional["AuditContext"] = None
    ) -> bool:
        """
        Actualiza el estado de un pedido y registra la transición en la bitácora.

        Flujo:
            1. Obtiene el estado actual del pedido
            2. Si estado_actual != estado_nuevo → inserta en pedido_estado_historial
            3. Actualiza pedido.estado_id, modificado_por, modificado_fecha
            4. Commit (ambas operaciones en la misma transacción)

        Args:
            pedido_id: UUID del pedido
            estado: Nuevo estado_id (int) o nombre legacy (str); se normaliza a estado_id.
            audit_context: Contexto de auditoría opcional (Buenas Prácticas - Sección 3)

        Returns:
            True si se actualizó correctamente, False si no existe el pedido o no hay columna estado/estado_id.
        """
        cursor = self.conn.cursor()
        try:
            tiene_estado_id = self.utils.tiene_columna_estado_id(cursor)
            tiene_estado = self.utils.tiene_columna_estado(cursor)

            estado_id = int(estado) if isinstance(estado, int) else estado_id_desde_legacy(estado)
            
            # Campos de auditoría (Buenas Prácticas - Sección 3)
            modificado_por = audit_context.get_modificado_por() if audit_context else None
            modificado_fecha = ahora_naive()

            # ── Obtener estado anterior para la bitácora ──
            estado_anterior_id: Optional[int] = None
            if tiene_estado_id:
                cursor.execute(
                    "SELECT estado_id FROM pedido WHERE pedido_id = ?", (pedido_id,)
                )
                row_ant = cursor.fetchone()
                if row_ant is not None:
                    estado_anterior_id = row_ant[0]

            # ── Registrar transición si el estado cambió ──
            if estado_anterior_id is not None and estado_anterior_id != estado_id:
                self._registrar_transicion_estado(
                    cursor, pedido_id, estado_anterior_id, estado_id, audit_context
                )

            # ── Actualizar estado en tabla pedido ──
            if tiene_estado_id:
                # COALESCE evita NULL en p.estado si no existe la fila en pedido_estado (ej. estado nuevo no migrado)
                # Incluye campos de auditoría: modificado_por, modificado_fecha
                cursor.execute("""
                    UPDATE p SET 
                        p.estado_id = ?, 
                        p.estado = COALESCE(pe.nombre, CAST(? AS NVARCHAR(100))),
                        p.modificado_por = COALESCE(?, p.modificado_por),
                        p.modificado_fecha = ?
                    FROM pedido p
                    LEFT JOIN pedido_estado pe ON pe.id = ?
                    WHERE p.pedido_id = ?
                """, (estado_id, estado_id, modificado_por, modificado_fecha, estado_id, pedido_id))
            elif tiene_estado:
                cursor.execute(
                    "SELECT nombre FROM pedido_estado WHERE id = ?", (estado_id,)
                )
                nom = cursor.fetchone()
                nombre = nom[0] if nom and nom[0] else str(estado_id)
                # Incluye campos de auditoría
                cursor.execute("""
                    UPDATE pedido SET 
                        estado = ?,
                        modificado_por = COALESCE(?, modificado_por),
                        modificado_fecha = ?
                    WHERE pedido_id = ?
                """, (nombre, modificado_por, modificado_fecha, pedido_id))
            else:
                logger.warning("⚠️ Columna 'estado'/'estado_id' no existe en tabla pedido.")
                return False

            rows_affected = cursor.rowcount
            self.conn.commit()
            if rows_affected > 0:
                logger.debug(f"✅ Estado actualizado para pedido {pedido_id}: estado_id={estado_id}")
                return True
            logger.warning(f"⚠️ No se encontró pedido con ID: {pedido_id}")
            return False
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar estado del pedido: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def _agregar_datos_sap_a_cabecera(
        self, cursor: pyodbc.Cursor, pedido_id: str, cabecera: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Agrega numero_oc_sap y doc_entry a la cabecera del pedido.
        
        Obtiene estos datos de la orden de compra asociada al pedido.
        Si hay múltiples órdenes de compra, toma la primera (más antigua).
        
        Args:
            cursor: Cursor de base de datos activo
            pedido_id: UUID del pedido
            cabecera: Diccionario con datos de cabecera existentes
            
        Returns:
            Cabecera actualizada con numero_oc_sap y doc_entry (pueden ser None)
        """
        try:
            cursor.execute("""
                SELECT TOP 1 numero_oc_sap, doc_entry
                FROM orden_compra_cabecera
                WHERE pedido_id = ?
                ORDER BY created_at ASC
            """, (pedido_id,))
            
            row = cursor.fetchone()
            if row:
                cabecera["numero_oc_sap"] = row[0]
                cabecera["doc_entry"] = row[1]
            else:
                cabecera["numero_oc_sap"] = None
                cabecera["doc_entry"] = None
                
        except Exception as e:
            logger.warning(f"⚠️ No se pudieron obtener datos SAP para pedido {pedido_id}: {e}")
            cabecera["numero_oc_sap"] = None
            cabecera["doc_entry"] = None
            
        return cabecera

    def delete(
        self,
        pedido_id: str,
        cursor: Optional[pyodbc.Cursor] = None,
        audit_context: Optional["AuditContext"] = None,
    ) -> bool:
        """
        Elimina la cabecera del pedido (una sola fila).
        Si se pasa cursor, no hace commit (para uso en transacción).
        Registra snapshot en pedido_audit_log antes de eliminar.

        Returns:
            True si se eliminó una fila, False si no existía.
        """
        from src.utils.audit_context import ensure_audit_context
        audit = ensure_audit_context(audit_context)
        
        own_cursor = cursor is None
        cur = cursor or self.conn.cursor()
        try:
            # Snapshot del registro antes de eliminar
            cur.execute("""
                SELECT pedido_id, numero_pedido, fecha_pedido, proveedor_nombre,
                       comprador_nombre, estado_id, creado_por, creado_en
                FROM pedido WHERE pedido_id = ?
            """, (pedido_id,))
            row = cur.fetchone()
            snapshot = None
            if row:
                snapshot = {
                    "pedido_id": str(row[0]),
                    "numero_pedido": row[1],
                    "fecha_pedido": str(row[2]) if row[2] else None,
                    "proveedor_nombre": row[3],
                    "comprador_nombre": row[4],
                    "estado_id": row[5],
                    "creado_por": row[6],
                    "creado_en": str(row[7]) if row[7] else None,
                }
            
            # Registrar en audit log antes del DELETE
            audit_svc = AuditLogService(self.conn)
            audit_svc.registrar_delete(
                pedido_id=pedido_id,
                entidad="pedido",
                entidad_id=pedido_id,
                audit_context=audit,
                datos_eliminados=snapshot,
                comentario="Eliminación de pedido cabecera",
                cursor=cur,
            )
            
            cur.execute("DELETE FROM pedido WHERE pedido_id = ?", (pedido_id,))
            rows = cur.rowcount
            if own_cursor:
                self.conn.commit()
            if rows > 0:
                logger.debug(f"✅ Pedido cabecera eliminada: {pedido_id}")
            return rows > 0
        except Exception as e:
            if own_cursor:
                self.conn.rollback()
            logger.error(f"❌ Error al eliminar pedido {pedido_id}: {e}", exc_info=True)
            raise
        finally:
            if own_cursor:
                cur.close()

    def update(
        self,
        pedido_id: str,
        datos_cabecera: Dict[str, Any],
        audit_context: Optional["AuditContext"] = None,
    ) -> bool:
        """
        Actualiza la cabecera de un pedido.
        
        Si algún campo en datos_cabecera es None, se preserva el valor existente.
        No se puede modificar: pedido_id, numero_pedido (business key), creado_por, creado_en.
        
        Args:
            pedido_id: UUID del pedido
            datos_cabecera: Diccionario con datos actualizados (sin pedido_id)
            audit_context: Contexto de auditoría (Buenas Prácticas - Sección 3)
            
        Returns:
            True si se actualizó correctamente, False si no existe el pedido
        """
        from src.utils.audit_context import ensure_audit_context
        audit = ensure_audit_context(audit_context)
        
        cursor = self.conn.cursor()
        
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            
            if tiene_estado:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, mensaje, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, estado
                    FROM pedido
                    WHERE pedido_id = ?
                """, (pedido_id,))
            else:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, mensaje, proveedor_nombre, comprador_nombre,
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
                "mensaje": row[5],
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

            if "mensaje" in merged:
                max_m = self.utils.get_mensaje_column_max_len(cursor, "pedido")
                merged["mensaje"] = clamp_pedido_mensaje(
                    merged.get("mensaje"),
                    max_length=max_m,
                )

            # Campos de auditoría
            modificado_por = audit.get_modificado_por()
            modificado_fecha = ahora_naive()
            
            if tiene_estado:
                sql = """
                UPDATE pedido SET
                    fecha_pedido = ?,
                    fecha_entrega = ?,
                    forma_pago = ?,
                    mensaje = ?,
                    proveedor_nombre = ?,
                    comprador_nombre = ?,
                    comprador_codigo = ?,
                    origen_traslado = ?,
                    serie = ?,
                    estado = ?,
                    modificado_por = ?,
                    modificado_fecha = ?,
                    origen = COALESCE(?, origen),
                    ip_origen = COALESCE(?, ip_origen)
                WHERE pedido_id = ?
                """
                values = (
                    merged.get("fecha_pedido"),
                    merged.get("fecha_entrega"),
                    merged.get("forma_pago"),
                    merged.get("mensaje"),
                    merged.get("proveedor_nombre"),
                    merged.get("comprador_nombre"),
                    merged.get("comprador_codigo"),
                    merged.get("origen_traslado"),
                    merged.get("serie"),
                    merged.get("estado"),
                    modificado_por,
                    modificado_fecha,
                    audit.origen,
                    audit.ip_origen,
                    pedido_id,
                )
            else:
                sql = """
                UPDATE pedido SET
                    fecha_pedido = ?,
                    fecha_entrega = ?,
                    forma_pago = ?,
                    mensaje = ?,
                    proveedor_nombre = ?,
                    comprador_nombre = ?,
                    comprador_codigo = ?,
                    origen_traslado = ?,
                    serie = ?,
                    modificado_por = ?,
                    modificado_fecha = ?
                WHERE pedido_id = ?
                """
                values = (
                    merged.get("fecha_pedido"),
                    merged.get("fecha_entrega"),
                    merged.get("forma_pago"),
                    merged.get("mensaje"),
                    merged.get("proveedor_nombre"),
                    merged.get("comprador_nombre"),
                    merged.get("comprador_codigo"),
                    merged.get("origen_traslado"),
                    merged.get("serie"),
                    modificado_por,
                    modificado_fecha,
                    pedido_id,
                )
            
            cursor.execute(sql, values)
            rows_affected = cursor.rowcount
            
            # Registrar cambios en audit log
            cambios = {}
            for campo in existing:
                val_anterior = existing[campo]
                val_nuevo = merged.get(campo)
                if str(val_anterior) != str(val_nuevo):
                    cambios[campo] = {"anterior": val_anterior, "nuevo": val_nuevo}
            
            if cambios:
                audit_svc = AuditLogService(self.conn)
                audit_svc.registrar_cambios(
                    pedido_id=pedido_id,
                    entidad="pedido",
                    entidad_id=pedido_id,
                    audit_context=audit,
                    cambios=cambios,
                    cursor=cursor,
                )
            
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

    def get_by_estado(self, estado: str | int) -> List[Dict[str, Any]]:
        """
        Obtiene todos los pedidos con un estado específico.

        Args:
            estado: estado_id (int) o nombre legacy (str) a filtrar.

        Returns:
            Lista de diccionarios con datos de pedidos (incluye estado_id/estado_nombre si existe).
        """
        cursor = self.conn.cursor()
        try:
            tiene_estado_id = self.utils.tiene_columna_estado_id(cursor)
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            if not tiene_estado_id and not tiene_estado:
                logger.warning("⚠️ Columna 'estado'/'estado_id' no existe en tabla pedido")
                return []

            estado_id = int(estado) if isinstance(estado, int) else estado_id_desde_legacy(estado)

            if tiene_estado_id:
                cursor.execute("""
                    SELECT 
                        p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                        p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
                        p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                        p.creado_por, p.estado_id, pe.nombre AS estado_nombre, p.creado_en
                    FROM pedido p
                    LEFT JOIN pedido_estado pe ON pe.id = p.estado_id
                    WHERE p.estado_id = ?
                    ORDER BY p.creado_en DESC
                """, (estado_id,))
                pedidos = []
                for row in cursor.fetchall():
                    pedidos.append({
                        "pedido_id": str(row[0]),
                        "numero_pedido": row[1],
                        "fecha_pedido": row[2].isoformat() if row[2] else None,
                        "fecha_entrega": row[3],
                        "forma_pago": row[4],
                        "mensaje": row[5],
                        "proveedor_nombre": row[6],
                        "comprador_nombre": row[7],
                        "comprador_codigo": row[8],
                        "origen_traslado": row[9],
                        "serie": row[10],
                        "archivo_nombre": row[11],
                        "creado_por": row[12],
                        "estado_id": row[13],
                        "estado_nombre": row[14],
                        "estado": row[14],
                        "creado_en": row[15].isoformat() if row[15] else None,
                    })
                return pedidos

            # Solo columna estado: filtrar por string; si recibimos int, resolver nombre
            filtro_estado: str
            if isinstance(estado, str):
                filtro_estado = estado
            else:
                cursor.execute("SELECT nombre FROM pedido_estado WHERE id = ?", (estado_id,))
                r = cursor.fetchone()
                filtro_estado = r[0] if r and r[0] else str(estado_id)
            cursor.execute("""
                SELECT 
                    pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                    forma_pago, mensaje, proveedor_nombre, comprador_nombre,
                    comprador_codigo, origen_traslado, serie, archivo_nombre,
                    creado_por, estado, creado_en
                FROM pedido
                WHERE estado = ?
                ORDER BY creado_en DESC
            """, (filtro_estado,))
            pedidos = []
            for row in cursor.fetchall():
                pedidos.append({
                    "pedido_id": str(row[0]),
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "mensaje": row[5],
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
        estado: Optional[str | int] = None,
        fecha_desde: Optional[str] = None,
        fecha_hasta: Optional[str] = None,
        proveedor_nombre: Optional[str] = None,
        numero_pedido: Optional[str] = None,
        creado_por: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        excluir_borrador: bool = False,
        solo_redistribucion: bool = False,
    ) -> Dict[str, Any]:
        """
        Obtiene pedidos con filtros y paginación.

        Args:
            estado: estado_id (int) o nombre legacy (str) para filtrar
            fecha_desde, fecha_hasta, proveedor_nombre, numero_pedido, creado_por, limit, offset
            excluir_borrador: si True, excluye pedidos en estado BORRADOR (estado_id=1)
            solo_redistribucion: si True, solo incluye pedidos aptos para redistribución
                (estado_id >= 4 "CONFIRMADO POR EL RAYO" y excluye CANCELADO (19) y CANCELADO POR EL RAYO (20))
        """
        cursor = self.conn.cursor()
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            tiene_estado_id = self.utils.tiene_columna_estado_id(cursor)

            where_conditions = []
            params: List[Any] = []

            if estado is not None and (tiene_estado_id or tiene_estado):
                estado_id = int(estado) if isinstance(estado, int) else estado_id_desde_legacy(estado)
                if tiene_estado_id:
                    where_conditions.append("p.estado_id = ?")
                    params.append(estado_id)
                else:
                    cursor.execute("SELECT nombre FROM pedido_estado WHERE id = ?", (estado_id,))
                    r = cursor.fetchone()
                    nom = r[0] if r and r[0] else str(estado_id)
                    where_conditions.append("p.estado = ?")
                    params.append(nom)

            if excluir_borrador and (tiene_estado_id or tiene_estado):
                if tiene_estado_id:
                    where_conditions.append("(p.estado_id IS NULL OR p.estado_id <> ?)")
                    params.append(ESTADO_BORRADOR)
                else:
                    where_conditions.append("(p.estado IS NULL OR (p.estado <> N'BORRADOR' AND p.estado <> N'PENDIENTE_CONFIRMACION_PROVEEDOR'))")

            # Filtro para vista de redistribución: solo pedidos con estado >= 4 (CONFIRMADO POR EL RAYO)
            # y excluir DESPACHAR_Y_FACTURAR (17), FINALIZADO (18), CANCELADO (19) y CANCELADO POR EL RAYO (20)
            if solo_redistribucion and (tiene_estado_id or tiene_estado):
                if tiene_estado_id:
                    where_conditions.append("p.estado_id >= ?")
                    params.append(ESTADO_REDISTRIBUCION)
                    where_conditions.append("p.estado_id NOT IN (?, ?, ?, ?)")
                    params.extend([ESTADO_DESPACHAR_Y_FACTURAR, ESTADO_FINALIZADO, ESTADO_CANCELADO, ESTADO_CANCELADO_POR_EL_RAYO])
                else:
                    # Fallback para bases de datos sin columna estado_id
                    where_conditions.append("p.estado NOT IN (N'BORRADOR', N'NUEVO_PEDIDO', N'GESTIONAR_PEDIDO', N'PENDIENTE_CONFIRMACION_PROVEEDOR', N'DESPACHAR_Y_FACTURAR', N'DESPACHAR Y FACTURAR', N'FINALIZADO', N'CANCELADO', N'CANCELADO POR EL RAYO')")

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

            if tiene_estado_id:
                select_fields = """
                    p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                    p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
                    p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                    p.creado_por, p.estado_id, pe.nombre AS estado_nombre, p.creado_en,
                    p.modificado_fecha, p.modificado_por
                """
                data_query = f"""
                    SELECT {select_fields}
                    FROM pedido p
                    LEFT JOIN pedido_estado pe ON pe.id = p.estado_id
                    WHERE {where_clause}
                    ORDER BY p.creado_en DESC
                """
            else:
                select_fields = """
                    p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                    p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
                    p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                    p.creado_por, p.creado_en, p.modificado_fecha, p.modificado_por
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
                if tiene_estado_id:
                    pedido = {
                        "pedido_id": str(row[idx]),
                        "numero_pedido": row[idx + 1],
                        "fecha_pedido": row[idx + 2].isoformat() if row[idx + 2] else None,
                        "fecha_entrega": row[idx + 3],
                        "forma_pago": row[idx + 4],
                        "mensaje": row[idx + 5],
                        "proveedor_nombre": row[idx + 6],
                        "comprador_nombre": row[idx + 7],
                        "comprador_codigo": row[idx + 8],
                        "origen_traslado": row[idx + 9],
                        "serie": row[idx + 10],
                        "archivo_nombre": row[idx + 11],
                        "creado_por": row[idx + 12],
                        "estado_id": row[idx + 13],
                        "estado_nombre": row[idx + 14],
                        "estado": row[idx + 14],
                        "creado_en": row[idx + 15].isoformat() if row[idx + 15] else None,
                        "modificado_fecha": row[idx + 16].isoformat() if row[idx + 16] else None,
                        "modificado_por": row[idx + 17],
                    }
                else:
                    pedido = {
                        "pedido_id": str(row[idx]),
                        "numero_pedido": row[idx + 1],
                        "fecha_pedido": row[idx + 2].isoformat() if row[idx + 2] else None,
                        "fecha_entrega": row[idx + 3],
                        "forma_pago": row[idx + 4],
                        "mensaje": row[idx + 5],
                        "proveedor_nombre": row[idx + 6],
                        "comprador_nombre": row[idx + 7],
                        "comprador_codigo": row[idx + 8],
                        "origen_traslado": row[idx + 9],
                        "serie": row[idx + 10],
                        "archivo_nombre": row[idx + 11],
                        "creado_por": row[idx + 12],
                        "creado_en": row[idx + 13].isoformat() if row[idx + 13] else None,
                        "modificado_fecha": row[idx + 14].isoformat() if row[idx + 14] else None,
                        "modificado_por": row[idx + 15],
                    }
                    pedido["estado"] = row[idx + 16] if tiene_estado else None
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
        Obtiene pedidos para la pantalla Revisar Redistribución.
        
        - Si `solo_redistribucion_confirmada` es True: incluye todos los pedidos desde
          CONFIRMADO REDISTRIBUCION (10) en adelante, excluyendo los estados CANCELADO (19)
          y CANCELADO POR EL RAYO (20).
        - En caso contrario: aplica el mismo filtro general de pedidos confirmados
          (desde 10 en adelante, excluyendo cancelados).
        
        Esta función se usa en la interfaz /revisar-redistribucion que debe mostrar
        únicamente pedidos que ya pasaron por el proceso de redistribución.
        
        Args:
            limit: Límite de registros
            offset: Desplazamiento para paginación
            solo_redistribucion_confirmada: Si True, solo pedidos que ya pasaron por redistribución
        """
        cursor = self.conn.cursor()
        try:
            tiene_estado_id = self.utils.tiene_columna_estado_id(cursor)
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            if not tiene_estado_id and not tiene_estado:
                return {"data": [], "total": 0, "limit": limit, "offset": offset or 0, "has_more": False}

            if tiene_estado_id:
                # Desde CONFIRMADO REDISTRIBUCION (10) en adelante,
                # excluyendo estados de cancelación (19, 20). Este filtro aplica tanto
                # cuando solo_redistribucion_confirmada es True como cuando es False,
                # para incluir también estados posteriores como DESPACHAR_Y_FACTURAR (17)
                # y FINALIZADO (18) en la pantalla Revisar Redistribución.
                where_clause = "p.estado_id >= ? AND p.estado_id NOT IN (?, ?)"
                params_list = [
                    ESTADO_PEDIDO_CONFIRMADO,
                    ESTADO_CANCELADO,
                    ESTADO_CANCELADO_POR_EL_RAYO,
                ]
                params: List[Any] = list(params_list)
                count_query = f"SELECT COUNT(*) FROM pedido p WHERE {where_clause}"
                cursor.execute(count_query, params)
                result = cursor.fetchone()
                total = result[0] if result else 0
                select_fields = """
                    p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                    p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
                    p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                    p.creado_por, p.estado_id, pe.nombre AS estado_nombre, p.creado_en
                """
                data_query = f"""
                    SELECT {select_fields}
                    FROM pedido p
                    LEFT JOIN pedido_estado pe ON pe.id = p.estado_id
                    WHERE {where_clause}
                    ORDER BY p.creado_en DESC
                """
            else:
                # Fallback para bases de datos sin columna estado_id (usando campo estado string).
                # Estados desde CONFIRMADO REDISTRIBUCION (10) en adelante,
                # excluyendo cancelados. Usar strings legacy mapeados en LEGACY_STRING_TO_ID.
                # Incluye también DESPACHAR_Y_FACTURAR y FINALIZADO.
                where_clause = (
                    "p.estado IN ("
                    "N'PEDIDO_CONFIRMADO', "
                    "N'CONFIRMADO REDISTRIBUCION', "
                    "N'CONFIRMADO_ENVIADO', "
                    "N'PENDIENTE_LOGISTICA', "
                    "N'ERROR_DATOS_MAESTROS', "
                    "N'DESPACHAR_Y_FACTURAR', "
                    "N'DESPACHAR Y FACTURAR', "
                    "N'FINALIZADO'"
                    ")"
                )
                params_list = []
                params: List[Any] = list(params_list)
                count_query = f"SELECT COUNT(*) FROM pedido p WHERE {where_clause}"
                cursor.execute(count_query, params)
                result = cursor.fetchone()
                total = result[0] if result else 0
                select_fields = """
                    p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                    p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
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
                if tiene_estado_id:
                    pedido = {
                        "pedido_id": str(row[idx]),
                        "numero_pedido": row[idx + 1],
                        "fecha_pedido": row[idx + 2].isoformat() if row[idx + 2] else None,
                        "fecha_entrega": row[idx + 3],
                        "forma_pago": row[idx + 4],
                        "mensaje": row[idx + 5],
                        "proveedor_nombre": row[idx + 6],
                        "comprador_nombre": row[idx + 7],
                        "comprador_codigo": row[idx + 8],
                        "origen_traslado": row[idx + 9],
                        "serie": row[idx + 10],
                        "archivo_nombre": row[idx + 11],
                        "creado_por": row[idx + 12],
                        "estado_id": row[idx + 13],
                        "estado_nombre": row[idx + 14],
                        "estado": row[idx + 14],
                        "creado_en": row[idx + 15].isoformat() if row[idx + 15] else None,
                    }
                else:
                    pedido = {
                        "pedido_id": str(row[idx]),
                        "numero_pedido": row[idx + 1],
                        "fecha_pedido": row[idx + 2].isoformat() if row[idx + 2] else None,
                        "fecha_entrega": row[idx + 3],
                        "forma_pago": row[idx + 4],
                        "mensaje": row[idx + 5],
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
        Devuelve estado_id y estado_nombre cuando existe columna estado_id.
        """
        cursor = self.conn.cursor()
        try:
            tiene_estado_id = self.utils.tiene_columna_estado_id(cursor)
            tiene_estado = self.utils.tiene_columna_estado(cursor)

            if tiene_estado_id:
                cursor.execute("""
                    SELECT TOP 1
                        p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                        p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
                        p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                        p.creado_por, p.estado_id, pe.nombre AS estado_nombre, p.creado_en
                    FROM pedido p
                    LEFT JOIN pedido_estado pe ON pe.id = p.estado_id
                    WHERE p.creado_por = ?
                    ORDER BY p.creado_en DESC
                """, (usuario_id,))
            elif tiene_estado:
                cursor.execute("""
                    SELECT TOP 1
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, mensaje, proveedor_nombre, comprador_nombre,
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
                        forma_pago, mensaje, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, creado_en
                    FROM pedido
                    WHERE creado_por = ?
                    ORDER BY creado_en DESC
                """, (usuario_id,))

            row = cursor.fetchone()
            if not row:
                return None

            if tiene_estado_id:
                return {
                    "pedido_id": str(row[0]),
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "mensaje": row[5],
                    "proveedor_nombre": row[6],
                    "comprador_nombre": row[7],
                    "comprador_codigo": row[8],
                    "origen_traslado": row[9],
                    "serie": row[10],
                    "archivo_nombre": row[11],
                    "creado_por": row[12],
                    "estado_id": row[13],
                    "estado_nombre": row[14],
                    "estado": row[14],
                    "creado_en": row[15].isoformat() if row[15] else None,
                }
            if tiene_estado:
                return {
                    "pedido_id": str(row[0]),
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "mensaje": row[5],
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
            return {
                "pedido_id": str(row[0]),
                "numero_pedido": row[1],
                "fecha_pedido": row[2].isoformat() if row[2] else None,
                "fecha_entrega": row[3],
                "forma_pago": row[4],
                "mensaje": row[5],
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
        Obtiene el último pedido para la pantalla Revisar Redistribución.
        
        Solo incluye pedidos con estado:
        - CONFIRMADO_ENVIADO (12)
        
        Usado en pantalla Revisar Redistribución: al entrar en /redistribucion se carga el último
        pedido que ya haya sido enviado.
        """
        cursor = self.conn.cursor()
        try:
            tiene_estado_id = self.utils.tiene_columna_estado_id(cursor)
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            if not tiene_estado_id and not tiene_estado:
                return None

            if tiene_estado_id:
                # Filtrar solo por estado: CONFIRMADO_ENVIADO (12)
                if usuario_id is not None:
                    cursor.execute("""
                        SELECT TOP 1
                            p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                            p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
                            p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                            p.creado_por, p.estado_id, pe.nombre AS estado_nombre, p.creado_en
                        FROM pedido p
                        LEFT JOIN pedido_estado pe ON pe.id = p.estado_id
                        WHERE p.estado_id = ? AND p.creado_por = ?
                        ORDER BY p.creado_en DESC
                    """, (ESTADO_CONFIRMADO_ENVIADO, usuario_id))
                else:
                    cursor.execute("""
                        SELECT TOP 1
                            p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                            p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
                            p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                            p.creado_por, p.estado_id, pe.nombre AS estado_nombre, p.creado_en
                        FROM pedido p
                        LEFT JOIN pedido_estado pe ON pe.id = p.estado_id
                        WHERE p.estado_id = ?
                        ORDER BY p.creado_en DESC
                    """, (ESTADO_CONFIRMADO_ENVIADO,))
            else:
                # Fallback para bases de datos sin columna estado_id (usando campo estado string)
                # Solo incluir estado: CONFIRMADO_ENVIADO
                if usuario_id is not None:
                    cursor.execute("""
                        SELECT TOP 1
                            pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                            forma_pago, mensaje, proveedor_nombre, comprador_nombre,
                            comprador_codigo, origen_traslado, serie, archivo_nombre,
                            creado_por, estado, creado_en
                        FROM pedido
                        WHERE estado = ? AND creado_por = ?
                        ORDER BY creado_en DESC
                    """, ("CONFIRMADO_ENVIADO", usuario_id))
                else:
                    cursor.execute("""
                        SELECT TOP 1
                            pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                            forma_pago, mensaje, proveedor_nombre, comprador_nombre,
                            comprador_codigo, origen_traslado, serie, archivo_nombre,
                            creado_por, estado, creado_en
                        FROM pedido
                        WHERE estado = ?
                        ORDER BY creado_en DESC
                    """, ("CONFIRMADO_ENVIADO",))

            row = cursor.fetchone()
            if not row:
                return None

            if tiene_estado_id:
                return {
                    "pedido_id": str(row[0]),
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "mensaje": row[5],
                    "proveedor_nombre": row[6],
                    "comprador_nombre": row[7],
                    "comprador_codigo": row[8],
                    "origen_traslado": row[9],
                    "serie": row[10],
                    "archivo_nombre": row[11],
                    "creado_por": row[12],
                    "estado_id": row[13],
                    "estado_nombre": row[14],
                    "estado": row[14],
                    "creado_en": row[15].isoformat() if row[15] else None,
                }
            return {
                "pedido_id": str(row[0]),
                "numero_pedido": row[1],
                "fecha_pedido": row[2].isoformat() if row[2] else None,
                "fecha_entrega": row[3],
                "forma_pago": row[4],
                "mensaje": row[5],
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
                "❌ Error al obtener último pedido CONFIRMADO/CONFIRMADO REDISTRIBUCION: %s", e, exc_info=True
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

    def get_estados(
        self,
        solo_activos: bool = True,
        excluir_ids: Optional[List[int]] = None,
        solo_ids: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene la lista de estados de pedido desde la tabla pedido_estado.
        
        Diseñado para alimentar los dropdowns de "Filtros de Búsqueda" en las
        interfaces de listas de pedidos, devolviendo los estados que el usuario
        realmente visualiza en la UI.
        
        Args:
            solo_activos: Si True, solo devuelve estados con activo=1 (default True)
            excluir_ids: Lista opcional de estado_id a excluir del resultado
                         (ej: [1] para excluir BORRADOR en la lista general)
            solo_ids: Lista opcional de estado_id a incluir exclusivamente
                      (ej: [4,5,6,9] para vista de redistribución)
        
        Returns:
            Lista de dicts con id, nombre y orden, ordenados por orden ASC
        """
        cursor = self.conn.cursor()
        try:
            where_conditions: List[str] = []
            params: List[Any] = []

            if solo_activos:
                where_conditions.append("pe.activo = 1")

            if solo_ids:
                placeholders = ",".join("?" for _ in solo_ids)
                where_conditions.append(f"pe.id IN ({placeholders})")
                params.extend(solo_ids)
            elif excluir_ids:
                placeholders = ",".join("?" for _ in excluir_ids)
                where_conditions.append(f"pe.id NOT IN ({placeholders})")
                params.extend(excluir_ids)

            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

            query = f"""
                SELECT pe.id, pe.nombre, pe.orden
                FROM pedido_estado pe
                WHERE {where_clause}
                ORDER BY pe.orden ASC
            """

            cursor.execute(query, params)
            estados = []
            for row in cursor.fetchall():
                estados.append({
                    "id": row[0],
                    "nombre": row[1],
                    "orden": row[2],
                })

            logger.debug(f"✓ Estados obtenidos: {len(estados)} estado(s)")
            return estados

        except Exception as e:
            logger.error(f"❌ Error al obtener estados de pedido: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
