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
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_CONFIRMADO_ENVIADO,
    ESTADO_DESPACHAR_Y_FACTURAR,
    ESTADO_FINALIZADO,
    ESTADO_CANCELADO,
    ESTADO_CANCELADO_POR_EL_RAYO,
    ESTADO_CONFIRMADO_POR_PRODUCCION,
    ESTADO_PRODUCCION_POSPUESTA,
    estado_id_desde_legacy,
)

# Import para type hints sin dependencia circular
if TYPE_CHECKING:
    from src.utils.audit_context import AuditContext

from src.database.services.audit_log_service import AuditLogService

logger = logging.getLogger(__name__)

# Literales reutilizados (evita duplicación detectada por SonarQube)
_SQL_NOMBRE_ESTADO_POR_ID = "SELECT nombre FROM pedido_estado WHERE id = ?"
_SEP_AND = " AND "


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

    # ------------------------------------------------------------------
    # Helpers de mapeo fila → dict (reducen complejidad y duplicación)
    # ------------------------------------------------------------------
    @staticmethod
    def _map_pedido_estado_id(row) -> Dict[str, Any]:
        """Fila de 16 columnas con estado_id (estado_id@13, estado_nombre@14, creado_en@15)."""
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

    @staticmethod
    def _map_pedido_estado(row) -> Dict[str, Any]:
        """Fila de 15 columnas con estado string (estado@13, creado_en@14)."""
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

    @staticmethod
    def _map_pedido_confirmado_legacy(row) -> Dict[str, Any]:
        """Fila confirmados sin estado_id (creado_en@13, estado@14)."""
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
            "estado": row[14],
        }

    @staticmethod
    def _map_pedido_filtros_estado_id(row) -> Dict[str, Any]:
        """Fila de filtros con estado_id (incluye modificado_fecha@16, modificado_por@17)."""
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
            "modificado_fecha": row[16].isoformat() if row[16] else None,
            "modificado_por": row[17],
        }

    @staticmethod
    def _map_pedido_filtros_legacy(row, tiene_estado: bool) -> Dict[str, Any]:
        """Fila de filtros sin estado_id (estado opcional en columna string @16)."""
        pedido = {
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
            "modificado_fecha": row[14].isoformat() if row[14] else None,
            "modificado_por": row[15],
        }
        pedido["estado"] = row[16] if tiene_estado else None
        return pedido

    def _preparar_datos_insert(
        self, datos_cabecera: Dict[str, Any], audit_context: Optional["AuditContext"]
    ) -> Dict[str, Any]:
        """Copia datos_cabecera aplicando auditoría y normalización de fechas."""
        datos = dict(datos_cabecera)

        # Aplicar campos de auditoría si se proporciona contexto
        if audit_context:
            if not datos.get("creado_por"):
                datos["creado_por"] = audit_context.get_creado_por()
            if not datos.get("origen"):
                datos["origen"] = audit_context.origen
            if not datos.get("ip_origen"):
                datos["ip_origen"] = audit_context.ip_origen

        if "fecha_pedido" in datos:
            datos["fecha_pedido"] = self.utils.normalizar_fecha(datos["fecha_pedido"])

        if "fecha_entrega" in datos:
            fecha_entrega = datos["fecha_entrega"]
            if fecha_entrega is not None and not isinstance(fecha_entrega, str):
                datos["fecha_entrega"] = self.utils.normalizar_fecha(fecha_entrega)

        return datos

    def _construir_insert_sql_values(
        self, pedido_id: str, datos: Dict[str, Any], tiene_estado_id: bool, tiene_estado: bool
    ):
        """
        Construye (sql, values, estado_inicial) para insertar el pedido según las
        columnas de estado disponibles.
        """
        _ahora = ahora_naive()

        if tiene_estado_id:
            estado_id = datos.get("estado_id", ESTADO_BORRADOR)
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
            values = (
                pedido_id,
                datos.get("numero_pedido"),
                datos.get("fecha_pedido"),
                datos.get("fecha_entrega"),
                datos.get("forma_pago"),
                datos.get("mensaje"),
                datos.get("proveedor_nombre"),
                datos.get("comprador_nombre"),
                datos.get("comprador_codigo"),
                datos.get("origen_traslado"),
                datos.get("serie"),
                datos.get("archivo_nombre"),
                datos.get("creado_por"),
                estado_id,
                datos.get("origen"),  # Campo de auditoría
                datos.get("ip_origen"),  # Campo de auditoría
                _ahora,  # creado_en
                datos.get("creado_por"),  # modificado_por = creado_por al crear
                _ahora,  # modificado_fecha
            )
            return sql, values, estado_id

        if tiene_estado:
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
            estado = datos.get("estado", "PENDIENTE_CONFIRMACION_PROVEEDOR")
            values = (
                pedido_id,
                datos.get("numero_pedido"),
                datos.get("fecha_pedido"),
                datos.get("fecha_entrega"),
                datos.get("forma_pago"),
                datos.get("mensaje"),
                datos.get("proveedor_nombre"),
                datos.get("comprador_nombre"),
                datos.get("comprador_codigo"),
                datos.get("origen_traslado"),
                datos.get("serie"),
                datos.get("archivo_nombre"),
                datos.get("creado_por"),
                estado,
                _ahora,  # creado_en
                datos.get("creado_por"),  # modificado_por = creado_por al crear
                _ahora,  # modificado_fecha
            )
            return sql, values, ESTADO_BORRADOR

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
        values = (
            pedido_id,
            datos.get("numero_pedido"),
            datos.get("fecha_pedido"),
            datos.get("fecha_entrega"),
            datos.get("forma_pago"),
            datos.get("mensaje"),
            datos.get("proveedor_nombre"),
            datos.get("comprador_nombre"),
            datos.get("comprador_codigo"),
            datos.get("origen_traslado"),
            datos.get("serie"),
            datos.get("archivo_nombre"),
            datos.get("creado_por"),
            _ahora,  # creado_en
            datos.get("creado_por"),  # modificado_por = creado_por al crear
            _ahora,  # modificado_fecha
        )
        return sql, values, ESTADO_BORRADOR

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
        datos_cabecera_normalizado = self._preparar_datos_insert(datos_cabecera, audit_context)

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

            sql, values, estado_inicial = self._construir_insert_sql_values(
                pedido_id, datos_cabecera_normalizado, tiene_estado_id, tiene_estado
            )

            cursor.execute(sql, values)

            # Req. 1.2: pedido_padre_id (pedido "hijo" generado con la diferencia no
            # entregada) -- UPDATE aparte, misma transacción, en vez de sumar una 4ta
            # variante a _construir_insert_sql_values (ya se ramifica por
            # tiene_estado_id/tiene_estado).
            if datos_cabecera_normalizado.get("pedido_padre_id"):
                cursor.execute("""
                    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'pedido' AND COLUMN_NAME = 'pedido_padre_id'
                """)
                row_padre = cursor.fetchone()
                if row_padre and row_padre[0] > 0:
                    cursor.execute(
                        "UPDATE pedido SET pedido_padre_id = ? WHERE pedido_id = ?",
                        (datos_cabecera_normalizado["pedido_padre_id"], pedido_id),
                    )

            # Registrar creación inicial en pedido_estado_historial
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
                        p.modificado_por, p.fecha_facturacion
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
                        modificado_por, fecha_facturacion
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
                        modificado_por, fecha_facturacion
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
                        p.modificado_por, p.fecha_facturacion
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
                        modificado_por, fecha_facturacion
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
                        modificado_por, fecha_facturacion
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

    def get_fecha_confirmacion_estado(
        self, pedido_id: str, estado_id: int = ESTADO_REDISTRIBUCION
    ) -> Optional[datetime]:
        """
        Obtiene la fecha/hora en que el pedido transicionó a `estado_id` (por defecto
        ESTADO_REDISTRIBUCION = "CONFIRMADO POR EL RAYO"), según pedido_estado_historial.

        Si hay varias transiciones al mismo estado, se toma la más reciente.
        `fecha_cambio` se guarda con SYSUTCDATETIME(); se convierte a hora Colombia
        (UTC-5, sin horario de verano) para consistencia con el resto del sistema.

        Returns:
            datetime naive en hora Colombia, o None si no existe la tabla o el registro.
        """
        cursor = self.conn.cursor()
        try:
            if not self._tiene_tabla_historial(cursor):
                return None
            cursor.execute(
                """
                SELECT TOP 1 DATEADD(HOUR, -5, fecha_cambio)
                FROM pedido_estado_historial
                WHERE pedido_id = ? AND estado_nuevo_id = ?
                ORDER BY fecha_cambio DESC
                """,
                (pedido_id, estado_id),
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else None
        finally:
            cursor.close()

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
                    _SQL_NOMBRE_ESTADO_POR_ID, (estado_id,)
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

    def _cargar_existing_update(
        self, cursor: pyodbc.Cursor, pedido_id: str, tiene_estado: bool
    ) -> Optional[Dict[str, Any]]:
        """Lee el pedido existente y devuelve el dict de campos fusionables, o None si no existe."""
        if tiene_estado:
            cursor.execute("""
                SELECT
                    pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                    forma_pago, mensaje, proveedor_nombre, comprador_nombre,
                    comprador_codigo, origen_traslado, serie, archivo_nombre,
                    creado_por, estado, fecha_facturacion
                FROM pedido
                WHERE pedido_id = ?
            """, (pedido_id,))
        else:
            cursor.execute("""
                SELECT
                    pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                    forma_pago, mensaje, proveedor_nombre, comprador_nombre,
                    comprador_codigo, origen_traslado, serie, archivo_nombre,
                    creado_por, fecha_facturacion
                FROM pedido
                WHERE pedido_id = ?
            """, (pedido_id,))

        row = cursor.fetchone()
        if not row:
            return None

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
            "fecha_facturacion": row[-1].isoformat() if row[-1] else None,
        }
        if tiene_estado:
            existing["estado"] = row[13]
        return existing

    def _fusionar_datos_update(
        self, cursor: pyodbc.Cursor, existing: Dict[str, Any], datos_cabecera: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fusiona datos nuevos sobre los existentes (preserva existente si el nuevo es None)."""
        merged = {}
        for key in existing.keys():
            new_value = datos_cabecera.get(key)
            merged[key] = new_value if new_value is not None else existing[key]

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
        return merged

    def _construir_update_sql_values(
        self, merged: Dict[str, Any], tiene_estado: bool,
        modificado_por, modificado_fecha, audit, pedido_id: str
    ):
        """Construye (sql, values) para el UPDATE de la cabecera del pedido."""
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
                fecha_facturacion = ?,
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
                merged.get("fecha_facturacion"),
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
                fecha_facturacion = ?,
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
                merged.get("fecha_facturacion"),
                modificado_por,
                modificado_fecha,
                pedido_id,
            )
        return sql, values

    @staticmethod
    def _calcular_cambios(existing: Dict[str, Any], merged: Dict[str, Any]) -> Dict[str, Any]:
        """Determina qué campos cambiaron entre existing y merged (para audit log)."""
        cambios = {}
        for campo in existing:
            val_anterior = existing[campo]
            val_nuevo = merged.get(campo)
            if str(val_anterior) != str(val_nuevo):
                cambios[campo] = {"anterior": val_anterior, "nuevo": val_nuevo}
        return cambios

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

            existing = self._cargar_existing_update(cursor, pedido_id, tiene_estado)
            if existing is None:
                logger.warning(f"⚠️ No se encontró pedido para actualizar: {pedido_id}")
                return False

            merged = self._fusionar_datos_update(cursor, existing, datos_cabecera)

            # Campos de auditoría
            modificado_por = audit.get_modificado_por()
            modificado_fecha = ahora_naive()

            sql, values = self._construir_update_sql_values(
                merged, tiene_estado, modificado_por, modificado_fecha, audit, pedido_id
            )

            cursor.execute(sql, values)
            rows_affected = cursor.rowcount

            # Registrar cambios en audit log
            cambios = self._calcular_cambios(existing, merged)

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
                return [self._map_pedido_estado_id(row) for row in cursor.fetchall()]

            # Solo columna estado: filtrar por string; si recibimos int, resolver nombre
            filtro_estado: str
            if isinstance(estado, str):
                filtro_estado = estado
            else:
                cursor.execute(_SQL_NOMBRE_ESTADO_POR_ID, (estado_id,))
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
            return [self._map_pedido_estado(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"❌ Error al obtener pedidos por estado: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def _filtro_estado(
        self, cursor, estado, tiene_estado_id: bool, tiene_estado: bool
    ) -> tuple:
        """Condición y parámetros para filtrar por estado."""
        conditions: List[str] = []
        params: List[Any] = []
        if estado is not None and (tiene_estado_id or tiene_estado):
            estado_id = int(estado) if isinstance(estado, int) else estado_id_desde_legacy(estado)
            if tiene_estado_id:
                conditions.append("p.estado_id = ?")
                params.append(estado_id)
            else:
                cursor.execute(_SQL_NOMBRE_ESTADO_POR_ID, (estado_id,))
                r = cursor.fetchone()
                nom = r[0] if r and r[0] else str(estado_id)
                conditions.append("p.estado = ?")
                params.append(nom)
        return conditions, params

    def _filtro_excluir_borrador(self, tiene_estado_id: bool) -> tuple:
        """Condición y parámetros para excluir pedidos en borrador."""
        if tiene_estado_id:
            return (
                ["(p.estado_id IS NULL OR p.estado_id <> ?)"],
                [ESTADO_BORRADOR],
            )
        return (
            ["(p.estado IS NULL OR (p.estado <> N'BORRADOR' AND p.estado <> N'PENDIENTE_CONFIRMACION_PROVEEDOR'))"],
            [],
        )

    def _filtro_redistribucion(self, tiene_estado_id: bool) -> tuple:
        """Condición y parámetros para la vista de redistribución.

        Incluye solo pedidos con estado >= 4 (CONFIRMADO POR EL RAYO) y excluye
        DESPACHAR_Y_FACTURAR (17), FINALIZADO (18), CANCELADO (19), CANCELADO POR
        EL RAYO (20), CONFIRMADO POR PRODUCCION (23) y PRODUCCION POSPUESTA (22).
        Estos 2 últimos tienen id numérico > 4 pero ocurren ANTES en el flujo real
        (entre GESTIONAR_PEDIDO y REDISTRIBUCION); sin la exclusión explícita, el
        ">=" los deja pasar aunque el pedido todavía no llegó a redistribución.
        """
        if tiene_estado_id:
            return (
                ["p.estado_id >= ?", "p.estado_id NOT IN (?, ?, ?, ?, ?, ?)"],
                [
                    ESTADO_REDISTRIBUCION,
                    ESTADO_DESPACHAR_Y_FACTURAR,
                    ESTADO_FINALIZADO,
                    ESTADO_CANCELADO,
                    ESTADO_CANCELADO_POR_EL_RAYO,
                    ESTADO_CONFIRMADO_POR_PRODUCCION,
                    ESTADO_PRODUCCION_POSPUESTA,
                ],
            )
        # Fallback para bases de datos sin columna estado_id
        return (
            ["p.estado NOT IN (N'BORRADOR', N'NUEVO_PEDIDO', N'GESTIONAR_PEDIDO', N'PENDIENTE_CONFIRMACION_PROVEEDOR', N'DESPACHAR_Y_FACTURAR', N'DESPACHAR Y FACTURAR', N'FINALIZADO', N'CANCELADO', N'CANCELADO POR EL RAYO', N'CONFIRMADO POR PRODUCCION', N'CONFIRMADO_POR_PRODUCCION', N'PRODUCCION POSPUESTA', N'PRODUCCION_POSPUESTA')"],
            [],
        )

    def _filtro_pendientes_accion(self, tiene_estado_id: bool) -> tuple:
        """Condición y parámetros para filtrar estados que requieren acción."""
        from src.database.pedido_estados import (
            ESTADOS_REQUIERE_ACCION_IDS,
            ESTADOS_REQUIERE_ACCION_NOMBRES,
        )
        if tiene_estado_id:
            placeholders = ",".join("?" * len(ESTADOS_REQUIERE_ACCION_IDS))
            return (
                [f"p.estado_id IN ({placeholders})"],
                list(sorted(ESTADOS_REQUIERE_ACCION_IDS)),
            )
        legacy_placeholders = ",".join("?" * len(ESTADOS_REQUIERE_ACCION_NOMBRES))
        return (
            [f"p.estado IN ({legacy_placeholders})"],
            list(ESTADOS_REQUIERE_ACCION_NOMBRES),
        )

    def _filtro_estados_produccion_el_rayo(self, tiene_estado_id: bool) -> tuple:
        """Condición y parámetros para restringir el listado al perfil Producción
        El Rayo (req. 1.8, permiso produccion-elrayo.view): solo NUEVO_PEDIDO y
        GESTIONAR_PEDIDO."""
        from src.database.pedido_estados import (
            ESTADOS_PRODUCCION_EL_RAYO_IDS,
            ESTADOS_PRODUCCION_EL_RAYO_NOMBRES,
        )
        if tiene_estado_id:
            placeholders = ",".join("?" * len(ESTADOS_PRODUCCION_EL_RAYO_IDS))
            return (
                [f"p.estado_id IN ({placeholders})"],
                list(sorted(ESTADOS_PRODUCCION_EL_RAYO_IDS)),
            )
        legacy_placeholders = ",".join("?" * len(ESTADOS_PRODUCCION_EL_RAYO_NOMBRES))
        return (
            [f"p.estado IN ({legacy_placeholders})"],
            list(ESTADOS_PRODUCCION_EL_RAYO_NOMBRES),
        )

    def _filtro_exclusion_estados_produccion_el_rayo(self, tiene_estado_id: bool) -> tuple:
        """Condición y parámetros para EXCLUIR NUEVO_PEDIDO/GESTIONAR_PEDIDO del
        listado (req. 1.8 segunda fase, permiso odcsap.view): esos 2 estados pasan
        a ser exclusivos de Producción El Rayo."""
        from src.database.pedido_estados import (
            ESTADOS_PRODUCCION_EL_RAYO_IDS,
            ESTADOS_PRODUCCION_EL_RAYO_NOMBRES,
        )
        if tiene_estado_id:
            placeholders = ",".join("?" * len(ESTADOS_PRODUCCION_EL_RAYO_IDS))
            return (
                [f"(p.estado_id IS NULL OR p.estado_id NOT IN ({placeholders}))"],
                list(sorted(ESTADOS_PRODUCCION_EL_RAYO_IDS)),
            )
        legacy_placeholders = ",".join("?" * len(ESTADOS_PRODUCCION_EL_RAYO_NOMBRES))
        return (
            [f"(p.estado IS NULL OR p.estado NOT IN ({legacy_placeholders}))"],
            list(ESTADOS_PRODUCCION_EL_RAYO_NOMBRES),
        )

    def _construir_filtros_pedidos(
        self, cursor, *,
        estado, excluir_borrador, solo_redistribucion, solo_pendientes_accion,
        restringir_produccion_el_rayo, excluir_estados_produccion_el_rayo,
        fecha_desde, fecha_hasta, proveedor_nombre, numero_pedido, creado_por,
        tiene_estado_id, tiene_estado,
    ):
        """Construye (where_conditions, params) para get_pedidos_con_filtros."""
        where_conditions: List[str] = []
        params: List[Any] = []

        c, p = self._filtro_estado(cursor, estado, tiene_estado_id, tiene_estado)
        where_conditions.extend(c)
        params.extend(p)

        if excluir_borrador and (tiene_estado_id or tiene_estado):
            c, p = self._filtro_excluir_borrador(tiene_estado_id)
            where_conditions.extend(c)
            params.extend(p)

        if solo_redistribucion and (tiene_estado_id or tiene_estado):
            c, p = self._filtro_redistribucion(tiene_estado_id)
            where_conditions.extend(c)
            params.extend(p)

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

        if solo_pendientes_accion and (tiene_estado_id or tiene_estado):
            c, p = self._filtro_pendientes_accion(tiene_estado_id)
            where_conditions.extend(c)
            params.extend(p)

        if restringir_produccion_el_rayo and (tiene_estado_id or tiene_estado):
            c, p = self._filtro_estados_produccion_el_rayo(tiene_estado_id)
            where_conditions.extend(c)
            params.extend(p)

        if excluir_estados_produccion_el_rayo and (tiene_estado_id or tiene_estado):
            c, p = self._filtro_exclusion_estados_produccion_el_rayo(tiene_estado_id)
            where_conditions.extend(c)
            params.extend(p)

        return where_conditions, params

    @staticmethod
    def _construir_data_query_filtros(where_clause: str, tiene_estado_id: bool, tiene_estado: bool) -> str:
        """Construye el SELECT paginable para get_pedidos_con_filtros."""
        if tiene_estado_id:
            select_fields = """
                p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
                p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                p.creado_por, p.estado_id, pe.nombre AS estado_nombre, p.creado_en,
                p.modificado_fecha, p.modificado_por
            """
            return f"""
                SELECT {select_fields}
                FROM pedido p
                LEFT JOIN pedido_estado pe ON pe.id = p.estado_id
                WHERE {where_clause}
                ORDER BY p.creado_en DESC
            """

        select_fields = """
            p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
            p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
            p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
            p.creado_por, p.creado_en, p.modificado_fecha, p.modificado_por
        """
        if tiene_estado:
            select_fields += ", p.estado"
        return f"""
            SELECT {select_fields}
            FROM pedido p
            WHERE {where_clause}
            ORDER BY p.creado_en DESC
        """

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
        solo_pendientes_accion: bool = False,
        restringir_produccion_el_rayo: bool = False,
        excluir_estados_produccion_el_rayo: bool = False,
    ) -> Dict[str, Any]:
        """
        Obtiene pedidos con filtros y paginación.

        Args:
            estado: estado_id (int) o nombre legacy (str) para filtrar
            fecha_desde, fecha_hasta, proveedor_nombre, numero_pedido, creado_por, limit, offset
            excluir_borrador: si True, excluye pedidos en estado BORRADOR (estado_id=1)
            solo_redistribucion: si True, solo incluye pedidos aptos para redistribución
                (estado_id >= 4 "CONFIRMADO POR EL RAYO", excluyendo CANCELADO (19),
                CANCELADO POR EL RAYO (20), CONFIRMADO POR PRODUCCION (23) y
                PRODUCCION POSPUESTA (22) — ver `_filtro_redistribucion`)
            solo_pendientes_accion: si True, solo estados que requieren acción del proveedor
            restringir_produccion_el_rayo: si True, solo incluye NUEVO_PEDIDO y GESTIONAR_PEDIDO
                (req. 1.8, perfil Producción El Rayo); se combina (AND) con `estado` si también se indica
            excluir_estados_produccion_el_rayo: si True, excluye NUEVO_PEDIDO y GESTIONAR_PEDIDO
                (req. 1.8 segunda fase, perfil odcsap.view); mutuamente excluyente en la práctica
                con restringir_produccion_el_rayo (ver _debe_excluir_estados_el_rayo)
        """
        cursor = self.conn.cursor()
        try:
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            tiene_estado_id = self.utils.tiene_columna_estado_id(cursor)

            where_conditions, params = self._construir_filtros_pedidos(
                cursor,
                estado=estado,
                excluir_borrador=excluir_borrador,
                solo_redistribucion=solo_redistribucion,
                solo_pendientes_accion=solo_pendientes_accion,
                restringir_produccion_el_rayo=restringir_produccion_el_rayo,
                excluir_estados_produccion_el_rayo=excluir_estados_produccion_el_rayo,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                proveedor_nombre=proveedor_nombre,
                numero_pedido=numero_pedido,
                creado_por=creado_por,
                tiene_estado_id=tiene_estado_id,
                tiene_estado=tiene_estado,
            )

            where_clause = _SEP_AND.join(where_conditions) if where_conditions else "1=1"

            count_query = f"SELECT COUNT(*) FROM pedido p WHERE {where_clause}"
            cursor.execute(count_query, params)
            result = cursor.fetchone()
            total = result[0] if result else 0

            data_query = self._construir_data_query_filtros(where_clause, tiene_estado_id, tiene_estado)
            if limit is not None:
                data_query += f" OFFSET {offset or 0} ROWS FETCH NEXT {limit} ROWS ONLY"

            cursor.execute(data_query, params)

            if tiene_estado_id:
                pedidos = [self._map_pedido_filtros_estado_id(row) for row in cursor.fetchall()]
            else:
                pedidos = [self._map_pedido_filtros_legacy(row, tiene_estado) for row in cursor.fetchall()]

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

    @staticmethod
    def _base_confirmados(tiene_estado_id: bool):
        """Devuelve (where_clause, params, select_fields) base para pedidos confirmados."""
        if tiene_estado_id:
            # Desde CONFIRMADO REDISTRIBUCION (10) en adelante,
            # excluyendo estados de cancelación (19, 20). Este filtro aplica tanto
            # cuando solo_redistribucion_confirmada es True como cuando es False,
            # para incluir también estados posteriores como DESPACHAR_Y_FACTURAR (17)
            # y FINALIZADO (18) en la pantalla Revisar Redistribución.
            where_clause = "p.estado_id >= ? AND p.estado_id NOT IN (?, ?)"
            params: List[Any] = [
                ESTADO_PEDIDO_CONFIRMADO,
                ESTADO_CANCELADO,
                ESTADO_CANCELADO_POR_EL_RAYO,
            ]
            select_fields = """
                p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
                p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                p.creado_por, p.estado_id, pe.nombre AS estado_nombre, p.creado_en
            """
            return where_clause, params, select_fields

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
        params = []
        select_fields = """
            p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
            p.forma_pago, p.mensaje, p.proveedor_nombre, p.comprador_nombre,
            p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
            p.creado_por, p.creado_en, p.estado
        """
        return where_clause, params, select_fields

    @staticmethod
    def _aplicar_filtros_extra_confirmados(
        where_clause, params, fecha_desde, fecha_hasta, proveedor_nombre, numero_pedido, creado_por
    ):
        """Agrega filtros opcionales (fechas, proveedor, número, creador) a la consulta base."""
        extra_conditions: List[str] = []
        if fecha_desde:
            extra_conditions.append("CAST(p.fecha_pedido AS DATE) >= CAST(? AS DATE)")
            params.append(fecha_desde)
        if fecha_hasta:
            extra_conditions.append("CAST(p.fecha_pedido AS DATE) <= CAST(? AS DATE)")
            params.append(fecha_hasta)
        if proveedor_nombre:
            extra_conditions.append("p.proveedor_nombre LIKE ?")
            params.append(f"%{proveedor_nombre}%")
        if numero_pedido:
            extra_conditions.append("p.numero_pedido LIKE ?")
            params.append(f"%{numero_pedido}%")
        if creado_por:
            extra_conditions.append("p.creado_por = ?")
            params.append(creado_por)
        if extra_conditions:
            where_clause = f"({where_clause}){_SEP_AND}" + _SEP_AND.join(extra_conditions)
        return where_clause, params

    @staticmethod
    def _data_query_confirmados(where_clause: str, select_fields: str, tiene_estado_id: bool) -> str:
        """Construye el SELECT de datos para pedidos confirmados."""
        if tiene_estado_id:
            return f"""
                SELECT {select_fields}
                FROM pedido p
                LEFT JOIN pedido_estado pe ON pe.id = p.estado_id
                WHERE {where_clause}
                ORDER BY p.creado_en DESC
            """
        return f"""
            SELECT {select_fields}
            FROM pedido p
            WHERE {where_clause}
            ORDER BY p.creado_en DESC
        """

    def get_pedidos_confirmados(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        fecha_desde: Optional[str] = None,
        fecha_hasta: Optional[str] = None,
        proveedor_nombre: Optional[str] = None,
        numero_pedido: Optional[str] = None,
        creado_por: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Obtiene pedidos para la pantalla Revisar Redistribución.

        Incluye pedidos desde CONFIRMADO REDISTRIBUCION (10) en adelante,
        excluyendo los estados CANCELADO (19) y CANCELADO POR EL RAYO (20).

        Args:
            limit: Límite de registros
            offset: Desplazamiento para paginación
        """
        cursor = self.conn.cursor()
        try:
            tiene_estado_id = self.utils.tiene_columna_estado_id(cursor)
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            if not tiene_estado_id and not tiene_estado:
                return {"data": [], "total": 0, "limit": limit, "offset": offset or 0, "has_more": False}

            where_clause, params, select_fields = self._base_confirmados(tiene_estado_id)
            where_clause, params = self._aplicar_filtros_extra_confirmados(
                where_clause, params, fecha_desde, fecha_hasta, proveedor_nombre, numero_pedido, creado_por
            )

            count_query = f"SELECT COUNT(*) FROM pedido p WHERE {where_clause}"
            cursor.execute(count_query, params)
            result = cursor.fetchone()
            total = result[0] if result else 0

            data_query = self._data_query_confirmados(where_clause, select_fields, tiene_estado_id)
            if limit is not None:
                data_query += f" OFFSET {offset or 0} ROWS FETCH NEXT {limit} ROWS ONLY"

            cursor.execute(data_query, params)
            if tiene_estado_id:
                pedidos = [self._map_pedido_estado_id(row) for row in cursor.fetchall()]
            else:
                pedidos = [self._map_pedido_confirmado_legacy(row) for row in cursor.fetchall()]

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

    def contar_hijos(self, pedido_padre_id: str) -> int:
        """Req. 1.2: cantidad de pedidos "hijo" ya generados a partir de este pedido
        (pedido_padre_id), usado para calcular el siguiente sufijo de numero_pedido
        (".01", ".02", ...). Devuelve 0 si la columna pedido_padre_id no existe todavía
        en este ambiente (migración 643 sin aplicar)."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = 'pedido' AND COLUMN_NAME = 'pedido_padre_id'
            """)
            row = cursor.fetchone()
            if not (row and row[0] > 0):
                return 0
            cursor.execute("SELECT COUNT(*) FROM pedido WHERE pedido_padre_id = ?", (pedido_padre_id,))
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            cursor.close()

    def _map_ultimo_pedido(self, row, tiene_estado_id: bool, tiene_estado: bool) -> Dict[str, Any]:
        """Mapea una fila de BD al dict de respuesta de get_ultimo_pedido."""
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

            return self._map_ultimo_pedido(row, tiene_estado_id, tiene_estado)
        except Exception as e:
            logger.error(f"❌ Error al obtener último pedido del usuario {usuario_id}: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def _ejecutar_query_ultimo_confirmado(
        self, cursor, tiene_estado_id: bool, usuario_id: Optional[str]
    ) -> None:
        """Ejecuta la query de get_ultimo_pedido_respuesta_proveedor_cargada según columnas disponibles."""
        if tiene_estado_id:
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

    def get_ultimo_pedido_respuesta_proveedor_cargada(
        self, usuario_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene el último pedido para la pantalla Revisar Redistribución.

        Solo incluye pedidos con estado CONFIRMADO_ENVIADO (12).
        Usado en /redistribucion: carga el último pedido ya enviado al proveedor.
        """
        cursor = self.conn.cursor()
        try:
            tiene_estado_id = self.utils.tiene_columna_estado_id(cursor)
            tiene_estado = self.utils.tiene_columna_estado(cursor)
            if not tiene_estado_id and not tiene_estado:
                return None

            self._ejecutar_query_ultimo_confirmado(cursor, tiene_estado_id, usuario_id)
            row = cursor.fetchone()
            if not row:
                return None

            return self._map_ultimo_pedido(row, tiene_estado_id, tiene_estado)
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

            where_clause = _SEP_AND.join(where_conditions) if where_conditions else "1=1"

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
