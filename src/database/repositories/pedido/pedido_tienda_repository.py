"""
Repositorio especializado para operaciones de tiendas y distribuciones.

CHANGELOG:
- 2026-02-12: Agregado soporte para audit_context en insert/delete de distribuciones
- 2026-01-23: Extraído de pedido_repository.py
"""

import logging
import pyodbc
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from src.utils.timezone import ahora_naive

if TYPE_CHECKING:
    from src.utils.audit_context import AuditContext

from src.database.services.audit_log_service import AuditLogService

logger = logging.getLogger(__name__)


class PedidoTiendaRepository:
    """Repositorio para operaciones de tiendas y distribuciones."""

    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.

        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn

    def _detectar_columnas_tienda(self, cursor: pyodbc.Cursor):
        def _tiene(col: str) -> bool:
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = 'pedido_detalle_tienda' AND COLUMN_NAME = ?
            """, (col,))
            row = cursor.fetchone()
            return (row[0] if row else 0) > 0
        return _tiene('fila_origen'), _tiene('es_bodega'), _tiene('creado_por')

    def _construir_insert_tienda_sql(
        self,
        tiene_fila_origen: bool,
        tiene_es_bodega: bool,
        tiene_audit_cols: bool,
    ) -> str:
        columnas = ["id", "pedido_detalle_id", "tienda_id", "cantidad"]
        valores_placeholders = ["NEWID()", "?", "?", "?"]
        if tiene_fila_origen:
            columnas.append("fila_origen")
            valores_placeholders.append("?")
        if tiene_es_bodega:
            columnas.append("es_bodega")
            valores_placeholders.append("?")
        if tiene_audit_cols:
            columnas.extend(["creado_por", "origen", "ip_origen"])
            valores_placeholders.extend(["?", "?", "?"])
        columnas.append("created_at")
        valores_placeholders.append("?")
        return f"INSERT INTO pedido_detalle_tienda ({', '.join(columnas)}) VALUES ({', '.join(valores_placeholders)})"

    def _insertar_una_distribucion(
        self,
        cursor: pyodbc.Cursor,
        sql: str,
        dist: Dict[str, Any],
        pedido_detalle_id: str,
        audit,
        tiene_fila_origen: bool,
        tiene_es_bodega: bool,
        tiene_audit_cols: bool,
    ) -> bool:
        tienda_id = dist.get("tienda_id")
        cantidad = dist.get("cantidad")
        if not tienda_id or cantidad is None or cantidad < 0:
            return False
        cantidad_decimal = float(cantidad)
        es_bodega = dist.get("es_bodega", False)
        if es_bodega:
            logger.info(f"📦 Insertando bodega en BD: pedido_detalle_id={pedido_detalle_id}, tienda_id={tienda_id}, cantidad={cantidad_decimal}, es_bodega={es_bodega}, tiene_es_bodega_col={tiene_es_bodega}")
        valores = [pedido_detalle_id, tienda_id, cantidad_decimal]
        if tiene_fila_origen:
            valores.append(dist.get("fila_origen"))
        if tiene_es_bodega:
            valores.append(1 if es_bodega else 0)
        if tiene_audit_cols:
            valores.extend([audit.get_creado_por(), audit.origen, audit.ip_origen])
        valores.append(ahora_naive())
        cursor.execute(sql, tuple(valores))
        return True

    def insert_distribuciones(
        self,
        pedido_detalle_id: str,
        distribuciones: List[Dict[str, Any]],
        audit_context: Optional["AuditContext"] = None,
    ) -> int:
        """
        Inserta distribuciones de un detalle por tiendas.
        
        Args:
            pedido_detalle_id: UUID del detalle
            distribuciones: Lista de dicts con tienda_id, cantidad y opcionalmente fila_origen, es_bodega
            
        Returns:
            Número de distribuciones insertadas
        """
        from src.utils.audit_context import ensure_audit_context
        audit = ensure_audit_context(audit_context)

        if not distribuciones:
            return 0

        cursor = self.conn.cursor()
        inserted_count = 0

        try:
            tiene_fila_origen, tiene_es_bodega, tiene_audit_cols = self._detectar_columnas_tienda(cursor)
            sql = self._construir_insert_tienda_sql(tiene_fila_origen, tiene_es_bodega, tiene_audit_cols)

            for dist in distribuciones:
                try:
                    if self._insertar_una_distribucion(
                        cursor, sql, dist, pedido_detalle_id, audit,
                        tiene_fila_origen, tiene_es_bodega, tiene_audit_cols,
                    ):
                        inserted_count += 1
                except pyodbc.IntegrityError:
                    logger.debug(f"⚠️ Relación detalle-tienda ya existe: {pedido_detalle_id} - {dist.get('tienda_id')}")
                except Exception as e:
                    logger.warning(f"⚠️ Error al insertar distribución: {e}")

            self.conn.commit()
            logger.debug(f"✅ {inserted_count} distribuciones insertadas para detalle {pedido_detalle_id}")
            return inserted_count

        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar distribuciones: {e}")
            raise
        finally:
            cursor.close()

    def _necesita_nombre_sap(self, codigo: str, nombre: Optional[str]) -> bool:
        return not nombre or nombre.strip() == "" or nombre.strip().upper() == codigo.strip().upper()

    def _buscar_marca(self, codigo: str) -> Optional[str]:
        """Resuelve la marca (ROLAND/REGIONS/DESCUENTON) de una tienda contra sc_maestros.

        No bloqueante: MarcaTiendaService ya traga sus propios errores y retorna
        None si sc_maestros no está disponible o el código no tiene marca conocida.
        """
        try:
            from ...services.marca_tienda_service import MarcaTiendaService
            return MarcaTiendaService().buscar_marca(codigo)
        except Exception as e:
            logger.warning(f"⚠️ No se pudo obtener marca de tienda {codigo}: {e}")
            return None

    def _buscar_nombre_sap(self, codigo: str) -> Optional[str]:
        try:
            from ...services.bodega_sap_service import BodegaSAPService
            bodega_sap_service = BodegaSAPService()
            bodega_info = bodega_sap_service.get_or_fetch_bodega_info(codigo, force_refresh=False)
            if bodega_info:
                whs_name = bodega_info.get("WhsName")
                if whs_name:
                    nombre_sap = whs_name.strip()
                    logger.info(f"✅ Nombre de tienda obtenido (caché o SAP): {codigo} → '{nombre_sap}'")
                    return nombre_sap
        except Exception as e:
            logger.warning(f"⚠️ No se pudo obtener nombre de tienda {codigo} (caché o SAP): {e}")
        return None

    def _debe_actualizar_nombre_tienda(
        self,
        nombre_final: Optional[str],
        nombre_existente: Optional[str],
        codigo_upper: str,
    ) -> bool:
        if not nombre_final or not nombre_final.strip():
            return False
        nombre_upper = nombre_final.strip().upper()
        nombre_existente_upper = str(nombre_existente).strip().upper() if nombre_existente else ""
        return (
            not nombre_existente
            or nombre_existente.strip() == ""
            or nombre_existente_upper == codigo_upper
            or (nombre_upper != codigo_upper and nombre_upper != nombre_existente_upper)
        )

    def _actualizar_nombre_tienda(
        self,
        cursor: pyodbc.Cursor,
        codigo: str,
        nombre_final: str,
        nombre_sap: Optional[str],
        nombre_existente: Optional[str],
    ) -> None:
        nombre_final_stripped = nombre_final.strip()
        cursor.execute(
            "UPDATE tienda SET nombre = ?, updated_at = ? WHERE codigo = ?",
            (nombre_final_stripped, ahora_naive(), codigo),
        )
        self.conn.commit()
        origen = "SAP" if nombre_sap else "Excel"
        logger.info(f"✅ Nombre de tienda actualizado desde {origen}: {codigo} → '{nombre_final_stripped}' (anterior: '{nombre_existente}')")

    def _determinar_nombre_guardar_tienda(
        self,
        codigo: str,
        nombre_final: Optional[str],
        nombre_sap: Optional[str],
    ) -> Optional[str]:
        if not nombre_final or not nombre_final.strip():
            logger.warning(f"⚠️ No se pudo obtener nombre para tienda '{codigo}', guardando NULL")
            return None
        nombre_stripped = nombre_final.strip()
        if nombre_stripped.upper() == codigo.strip().upper():
            logger.warning(f"⚠️ El nombre '{nombre_stripped}' es igual al código '{codigo}', guardando NULL")
            return None
        origen = "SAP" if nombre_sap else "Excel"
        logger.info(f"✅ Creando tienda con nombre desde {origen}: {codigo} → '{nombre_stripped}'")
        return nombre_stripped

    def get_or_create_tienda(
        self, 
        codigo: str, 
        nombre: Optional[str] = None, 
        consultar_sap: bool = True
    ) -> str:
        """
        Obtiene el ID de una tienda existente o la crea si no existe.
        
        Args:
            codigo: Código de la tienda
            nombre: Nombre de la tienda (opcional, si no se proporciona se consulta SAP)
            consultar_sap: Si True, consulta SAP para obtener el nombre si no se proporciona
            
        Returns:
            tienda_id (UUID)
        """
        cursor = self.conn.cursor()
        try:
            nombre_sap = self._buscar_nombre_sap(codigo) if self._necesita_nombre_sap(codigo, nombre) and consultar_sap else None
            nombre_final = nombre_sap if nombre_sap else nombre

            cursor.execute("SELECT tienda_id, nombre FROM tienda WHERE codigo = ?", (codigo,))
            row = cursor.fetchone()

            if row:
                tienda_id = str(row[0])
                nombre_existente = row[1] if len(row) > 1 else None
                codigo_upper = codigo.strip().upper()
                if self._debe_actualizar_nombre_tienda(nombre_final, nombre_existente, codigo_upper) and nombre_final:
                    self._actualizar_nombre_tienda(cursor, codigo, nombre_final, nombre_sap, nombre_existente)
                logger.debug(f"✅ Tienda existente encontrada: {codigo} ({tienda_id})")
                return tienda_id

            cursor.execute("SELECT NEWID()")
            uuid_result = cursor.fetchone()
            if uuid_result is None:
                raise ValueError("No se pudo generar UUID para tienda_id")
            tienda_id = str(uuid_result[0])

            nombre_guardar = self._determinar_nombre_guardar_tienda(codigo, nombre_final, nombre_sap)
            marca = self._buscar_marca(codigo) if consultar_sap else None

            cursor.execute("""
                INSERT INTO tienda (tienda_id, codigo, nombre, marca, activa, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
            """, (tienda_id, codigo, nombre_guardar, marca, ahora_naive()))
            self.conn.commit()

            logger.debug(f"✅ Nueva tienda creada: {codigo} ({tienda_id})")
            return tienda_id

        except pyodbc.IntegrityError:
            self.conn.rollback()
            cursor.execute("SELECT tienda_id FROM tienda WHERE codigo = ?", (codigo,))
            row = cursor.fetchone()
            if row:
                return str(row[0])
            raise
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al crear/obtener tienda {codigo}: {e}")
            raise
        finally:
            cursor.close()

    def get_tienda_id_by_codigo(self, codigo: str) -> Optional[str]:
        """
        Obtiene el tienda_id por código.

        Args:
            codigo: Código de tienda

        Returns:
            tienda_id o None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT tienda_id FROM tienda WHERE codigo = ?", (codigo,))
            row = cursor.fetchone()
            return str(row[0]) if row else None
        finally:
            cursor.close()

    def get_nombre_by_codigo(self, codigo: str) -> Optional[str]:
        """
        Obtiene el nombre de la tienda por código.
        Usado para enriquecer distribucion_tiendas cuando el nombre viene vacío (ej. cantidades < 1).

        Args:
            codigo: Código de tienda

        Returns:
            nombre de la tienda o None si no existe o no tiene nombre
        """
        if not codigo or not str(codigo).strip():
            return None
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT nombre FROM tienda WHERE codigo = ?", (codigo.strip(),))
            row = cursor.fetchone()
            if row and row[0] and str(row[0]).strip():
                return str(row[0]).strip()
            return None
        finally:
            cursor.close()

    def buscar_tiendas(self, query: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Busca tiendas activas del catálogo maestro por nombre o código (búsqueda parcial).

        Usado por el buscador de "agregar tienda" en la redistribución de pedidos hijo
        (req. redistribución a tiendas fuera del Excel original).

        Args:
            query: Texto a buscar en código o nombre (None o vacío devuelve las primeras `limit`)
            limit: Máximo de resultados a devolver

        Returns:
            Lista de dicts con tienda_id, codigo, nombre, ordenados por nombre
        """
        cursor = self.conn.cursor()
        try:
            texto = (query or "").strip()
            if texto:
                patron = f"%{texto}%"
                cursor.execute("""
                    SELECT TOP (?) tienda_id, codigo, nombre
                    FROM tienda
                    WHERE activa = 1 AND (codigo LIKE ? OR nombre LIKE ?)
                    ORDER BY nombre
                """, (limit, patron, patron))
            else:
                cursor.execute("""
                    SELECT TOP (?) tienda_id, codigo, nombre
                    FROM tienda
                    WHERE activa = 1
                    ORDER BY nombre
                """, (limit,))

            return [
                {"tienda_id": str(row[0]), "codigo": row[1], "nombre": row[2]}
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()

    def validar_tiendas_existen(
        self,
        codigos_tiendas: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Valida si las tiendas existen y están activas.
        
        Args:
            codigos_tiendas: Lista de códigos de tiendas a validar
            
        Returns:
            Dict con formato:
            {
                "codigo_tienda": {
                    "existe": bool,
                    "activa": bool,
                    "tienda_id": str (si existe)
                }
            }
        """
        if not codigos_tiendas:
            return {}
        
        cursor = self.conn.cursor()
        resultado = {}
        
        try:
            placeholders = ','.join('?' * len(codigos_tiendas))
            cursor.execute(f"""
                SELECT tienda_id, codigo, activa
                FROM tienda
                WHERE codigo IN ({placeholders})
            """, codigos_tiendas)
            
            for codigo in codigos_tiendas:
                resultado[codigo.upper()] = {
                    "existe": False,
                    "activa": False,
                    "tienda_id": None
                }
            
            for row in cursor.fetchall():
                tienda_id = str(row[0])
                codigo = str(row[1]).upper()
                activa = bool(row[2])
                
                if codigo in resultado:
                    resultado[codigo] = {
                        "existe": True,
                        "activa": activa,
                        "tienda_id": tienda_id
                    }
            
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error al validar tiendas: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def delete_distribuciones_by_pedido_id(
        self,
        pedido_id: str,
        cursor: Optional[pyodbc.Cursor] = None,
        audit_context: Optional["AuditContext"] = None,
    ) -> int:
        """
        Elimina todas las filas de pedido_detalle_tienda asociadas a un pedido.
        Si se pasa cursor, no hace commit (para uso en transacción).
        Registra snapshot en pedido_audit_log antes de eliminar.

        Returns:
            Número de filas eliminadas.
        """
        from src.utils.audit_context import ensure_audit_context
        audit = ensure_audit_context(audit_context)
        
        own_cursor = cursor is None
        cur = cursor or self.conn.cursor()
        try:
            cur.execute("""
                DELETE FROM pedido_detalle_tienda
                WHERE pedido_detalle_id IN (
                    SELECT pedido_detalle_id FROM pedido_detalle WHERE pedido_id = ?
                )
            """, (pedido_id,))
            count = cur.rowcount
            
            # Registrar en audit log (resumen, no por cada fila para performance)
            if count > 0:
                audit_svc = AuditLogService(self.conn)
                audit_svc.registrar_delete(
                    pedido_id=pedido_id,
                    entidad="pedido_detalle_tienda",
                    entidad_id=pedido_id,
                    audit_context=audit,
                    datos_eliminados={"total_distribuciones_eliminadas": count},
                    comentario=f"Eliminadas {count} distribuciones del pedido",
                    cursor=cur,
                )
            
            if own_cursor:
                self.conn.commit()
            if count > 0:
                logger.debug(f"✅ {count} distribuciones eliminadas para pedido {pedido_id}")
            return count
        except Exception as e:
            if own_cursor:
                self.conn.rollback()
            logger.error(f"❌ Error al eliminar distribuciones del pedido {pedido_id}: {e}", exc_info=True)
            raise
        finally:
            if own_cursor:
                cur.close()
