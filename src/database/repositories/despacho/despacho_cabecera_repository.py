"""
Repositorio especializado para operaciones de despacho_cabecera.

CHANGELOG:
- 2026-01-08: Extraído de despacho_repository.py
- 2026-02-06: Agregado soporte para campos de auditoría (Buenas Prácticas - Sección 3)
"""

import logging
import pyodbc
from datetime import datetime

from src.utils.timezone import ahora_naive
from typing import Optional, Dict, Any, TYPE_CHECKING

from ..common.serialization import serialize_date

if TYPE_CHECKING:
    from src.utils.audit_context import AuditContext

logger = logging.getLogger(__name__)


class DespachoCabeceraRepository:
    """Repositorio para operaciones de despacho_cabecera."""

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

    def get_by_id(self, despacho_id: str) -> Optional[Dict[str, Any]]:
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

    def insert(
        self, 
        datos_cabecera: Dict[str, Any],
        audit_context: Optional["AuditContext"] = None
    ) -> str:
        """
        Inserta un registro en despacho_cabecera.

        Args:
            datos_cabecera: Diccionario con datos de cabecera (sin despacho_id)
            audit_context: Contexto de auditoría opcional (Buenas Prácticas - Sección 3)

        Returns:
            despacho_id (UUID) generado

        Raises:
            ValueError: Si campos requeridos son None
            Exception: Si falla la inserción
        """
        self._validar_campos_requeridos(datos_cabecera)

        cursor = self.conn.cursor()

        try:
            # Generar UUID para despacho_id
            cursor.execute("SELECT NEWID()")
            uuid_result = cursor.fetchone()
            if uuid_result is None:
                raise ValueError("No se pudo generar UUID para despacho_id")
            despacho_id = str(uuid_result[0])

            # Campos de auditoría (Buenas Prácticas - Sección 3)
            creado_por = None
            origen = None
            ip_origen = None
            if audit_context:
                creado_por = audit_context.get_creado_por()
                origen = audit_context.origen
                ip_origen = audit_context.ip_origen

            sql = """
            INSERT INTO despacho_cabecera (
                despacho_id, empresa, codigo_cliente, fecha_despacho,
                codigo_factura, anulada, numero_pedido_sistema, numero_orden,
                numero_factura, tipo_documento, orden_compra, orden_compra_cliente,
                remision_facturada, num_id_factura_relacionada, fecha_factura,
                codigo_despacho, codigo_bodega, confirmado,
                creado_por, origen, ip_origen,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                datos_cabecera.get("confirmado", 0),
                creado_por,
                origen,
                ip_origen,
                ahora_naive(),
                ahora_naive(),
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

    def update(
        self, 
        despacho_id: str, 
        datos_cabecera: Dict[str, Any],
        audit_context: Optional["AuditContext"] = None
    ) -> bool:
        """
        Actualiza un registro existente en despacho_cabecera.

        Si algún campo en datos_cabecera es None, se preserva el valor existente.

        Args:
            despacho_id: UUID del despacho a actualizar
            datos_cabecera: Diccionario con datos actualizados (sin despacho_id)
            audit_context: Contexto de auditoría opcional (Buenas Prácticas - Sección 3)

        Returns:
            True si se actualizó correctamente
        """
        cursor = self.conn.cursor()

        try:
            # Obtener valores existentes para campos que son None
            existing = self.get_by_id(despacho_id)
            if not existing:
                logger.warning(f"⚠️ No se encontró despacho para actualizar: {despacho_id}")
                return False

            # Fusionar datos
            merged = {}
            for key in existing.keys():
                new_value = datos_cabecera.get(key)
                if new_value is not None:
                    merged[key] = new_value
                else:
                    merged[key] = existing[key]

            # Campos de auditoría (Buenas Prácticas - Sección 3)
            modificado_por = None
            modificado_fecha = None
            if audit_context:
                modificado_por = audit_context.get_modificado_por()
                modificado_fecha = ahora_naive()

            sql = """
            UPDATE despacho_cabecera SET
                empresa = ?, codigo_cliente = ?, fecha_despacho = ?,
                codigo_factura = ?, anulada = ?, numero_pedido_sistema = ?,
                numero_orden = ?, numero_factura = ?, tipo_documento = ?,
                orden_compra = ?, orden_compra_cliente = ?, remision_facturada = ?,
                num_id_factura_relacionada = ?, fecha_factura = ?,
                codigo_despacho = ?, codigo_bodega = ?, confirmado = ?,
                modificado_por = ?, modificado_fecha = ?,
                updated_at = ?
            WHERE despacho_id = ?
            """

            values = (
                merged["empresa"], merged["codigo_cliente"], merged["fecha_despacho"],
                merged["codigo_factura"], merged["anulada"], merged["numero_pedido_sistema"],
                merged["numero_orden"], merged["numero_factura"], merged["tipo_documento"],
                merged["orden_compra"], merged["orden_compra_cliente"], merged["remision_facturada"],
                merged["num_id_factura_relacionada"], merged["fecha_factura"],
                merged["codigo_despacho"], merged.get("codigo_bodega"), merged.get("confirmado", 0),
                modificado_por, modificado_fecha,
                ahora_naive(),
                despacho_id,
            )

            cursor.execute(sql, values)
            rows_affected = cursor.rowcount
            self.conn.commit()

            if rows_affected > 0:
                logger.debug(f"✅ Despacho cabecera actualizado: {despacho_id}")
                return True
            else:
                logger.warning(f"⚠️ No se encontró despacho para actualizar: {despacho_id}")
                return False

        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar despacho_cabecera: {e}")
            raise
        finally:
            cursor.close()

    def _validar_campos_requeridos(self, datos_cabecera: Dict[str, Any]) -> None:
        """Valida que los campos requeridos no sean None."""
        codigo_factura = datos_cabecera.get("codigo_factura")
        if not codigo_factura:
            raise ValueError(
                "El campo 'codigo_factura' es requerido y no puede ser NULL. "
                "Verifique que el campo CODIGO_FACTURA esté presente en los datos de MBA3."
            )

        campos_faltantes = []
        campos_requeridos = ["empresa", "codigo_cliente", "numero_factura", "tipo_documento", "fecha_despacho"]
        for campo in campos_requeridos:
            if datos_cabecera.get(campo) is None:
                campos_faltantes.append(campo)

        if campos_faltantes:
            logger.warning(
                f"⚠️ Campos requeridos faltantes: {', '.join(campos_faltantes)}. "
                f"Código de factura: {codigo_factura}"
            )
            raise ValueError(
                f"Los siguientes campos son requeridos y no pueden ser NULL: {', '.join(campos_faltantes)}. "
                f"Código de factura: {codigo_factura}."
            )

