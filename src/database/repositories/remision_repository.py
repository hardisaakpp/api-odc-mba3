"""
Repositorio para operaciones CRUD de remisiones en SQL Server.
"""

import logging
import pyodbc
from typing import Optional, Dict, Any

from src.utils.timezone import ahora_naive

from .common.serialization import serialize_date

logger = logging.getLogger(__name__)


class RemisionRepository:
    """Repositorio para operaciones de remision_cabecera."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def find_by_codigo_factura(self, codigo_factura: str) -> Optional[str]:
        """
        Busca una remisión por código de factura.
        
        Args:
            codigo_factura: Código de factura a buscar
            
        Returns:
            remision_id si existe, None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT remision_id FROM remision_cabecera WHERE codigo_factura = ?",
                (codigo_factura,)
            )
            result = cursor.fetchone()
            return str(result[0]) if result else None
        finally:
            cursor.close()
    
    def get_existing_cabecera(self, remision_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene los datos existentes de una cabecera de remisión.
        
        Args:
            remision_id: UUID de la remisión
            
        Returns:
            Diccionario con los datos existentes, o None si no existe
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT empresa, codigo_cliente, fecha_remision, codigo_factura,
                       anulada, numero_pedido_sistema, numero_orden, numero_factura,
                       tipo_documento, orden_compra, orden_compra_cliente,
                       remision_facturada, factura_impresa, confirmado, fecha_factura
                FROM remision_cabecera
                WHERE remision_id = ?
                """,
                (remision_id,)
            )
            result = cursor.fetchone()
            if not result:
                return None
            
            return {
                "empresa": result[0],
                "codigo_cliente": result[1],
                "fecha_remision": result[2],
                "codigo_factura": result[3],
                "anulada": result[4],
                "numero_pedido_sistema": result[5],
                "numero_orden": result[6],
                "numero_factura": result[7],
                "tipo_documento": result[8],
                "orden_compra": result[9],
                "orden_compra_cliente": result[10],
                "remision_facturada": result[11],
                "factura_impresa": result[12],
                "confirmado": result[13],
                "fecha_factura": result[14],
            }
        finally:
            cursor.close()
    
    def update_cabecera(self, remision_id: str, datos_cabecera: Dict[str, Any]) -> bool:
        """
        Actualiza un registro existente en remision_cabecera.
        
        Si algún campo en datos_cabecera es None, se preserva el valor existente
        en la base de datos para evitar violar restricciones NOT NULL.
        
        Args:
            remision_id: UUID de la remisión a actualizar
            datos_cabecera: Diccionario con datos actualizados (sin remision_id)
            
        Returns:
            True si se actualizó correctamente
            
        Raises:
            Exception: Si falla la actualización
        """
        cursor = self.conn.cursor()
        
        try:
            # Obtener valores existentes para campos que son None
            existing = self.get_existing_cabecera(remision_id)
            if not existing:
                logger.warning(f"⚠️ No se encontró remisión para actualizar: {remision_id}")
                return False
            
            # Fusionar datos: usar nuevo valor si existe y no es None, sino usar existente
            merged = {}
            for key in existing.keys():
                new_value = datos_cabecera.get(key)
                if new_value is not None:
                    merged[key] = new_value
                else:
                    merged[key] = existing[key]
            
            # SQL para actualizar (todos los campos excepto remision_id y created_at)
            sql = """
            UPDATE remision_cabecera SET
                empresa = ?,
                codigo_cliente = ?,
                fecha_remision = ?,
                codigo_factura = ?,
                anulada = ?,
                numero_pedido_sistema = ?,
                numero_orden = ?,
                numero_factura = ?,
                tipo_documento = ?,
                orden_compra = ?,
                orden_compra_cliente = ?,
                remision_facturada = ?,
                factura_impresa = ?,
                confirmado = ?,
                fecha_factura = ?,
                updated_at = ?
            WHERE remision_id = ?
            """
            
            values = (
                merged["empresa"],
                merged["codigo_cliente"],
                merged["fecha_remision"],
                merged["codigo_factura"],
                merged["anulada"],
                merged["numero_pedido_sistema"],
                merged["numero_orden"],
                merged["numero_factura"],
                merged["tipo_documento"],
                merged["orden_compra"],
                merged["orden_compra_cliente"],
                merged["remision_facturada"],
                merged["factura_impresa"],
                merged.get("confirmado", 0),  # BIT: 0 o 1, por defecto 0
                merged["fecha_factura"],
                ahora_naive(),
                remision_id,
            )
            
            cursor.execute(sql, values)
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.debug(f"✅ Remisión cabecera actualizada: {remision_id} - {merged.get('codigo_factura', 'N/A')}")
                return True
            else:
                logger.warning(f"⚠️ No se encontró remisión para actualizar: {remision_id}")
                return False
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar remision_cabecera: {e}")
            logger.error(f"   Remisión ID: {remision_id}")
            raise
        finally:
            cursor.close()
    
    def insert_cabecera(self, datos_cabecera: Dict[str, Any]) -> str:
        """
        Inserta un registro en remision_cabecera.
        
        Valida que los campos requeridos no sean None antes de insertar.
        
        Args:
            datos_cabecera: Diccionario con datos de cabecera (sin remision_id)
            
        Returns:
            remision_id (UUID) generado
            
        Raises:
            ValueError: Si campos requeridos son None
            Exception: Si falla la inserción
        """
        # Validar campos críticos requeridos (NOT NULL)
        codigo_factura = datos_cabecera.get("codigo_factura")
        if not codigo_factura:
            raise ValueError(
                "El campo 'codigo_factura' es requerido y no puede ser NULL. "
                "Verifique que el campo CODIGO_FACTURA esté presente en los datos de MBA3."
            )
        
        # Validar que los campos con valores por defecto no sean None
        campos_faltantes = []
        if datos_cabecera.get("empresa") is None:
            campos_faltantes.append("empresa")
        if datos_cabecera.get("codigo_cliente") is None:
            campos_faltantes.append("codigo_cliente")
        if datos_cabecera.get("numero_factura") is None:
            campos_faltantes.append("numero_factura")
        if datos_cabecera.get("tipo_documento") is None:
            campos_faltantes.append("tipo_documento")
        if datos_cabecera.get("fecha_remision") is None:
            campos_faltantes.append("fecha_remision")
        
        if campos_faltantes:
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
            # Generar UUID para remision_id
            cursor.execute("SELECT NEWID()")
            uuid_result = cursor.fetchone()
            if uuid_result is None:
                raise ValueError("No se pudo generar UUID para remision_id")
            remision_id = str(uuid_result[0])
            
            # SQL para insertar (incluyendo todos los campos de la tabla)
            sql = """
            INSERT INTO remision_cabecera (
                remision_id,
                empresa,
                codigo_cliente,
                fecha_remision,
                codigo_factura,
                anulada,
                numero_pedido_sistema,
                numero_orden,
                numero_factura,
                tipo_documento,
                orden_compra,
                orden_compra_cliente,
                remision_facturada,
                factura_impresa,
                confirmado,
                fecha_factura,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            _ahora = ahora_naive()
            values = (
                remision_id,
                datos_cabecera["empresa"],
                datos_cabecera["codigo_cliente"],
                datos_cabecera["fecha_remision"],
                datos_cabecera["codigo_factura"],
                datos_cabecera["anulada"],
                datos_cabecera["numero_pedido_sistema"],
                datos_cabecera["numero_orden"],
                datos_cabecera["numero_factura"],
                datos_cabecera["tipo_documento"],
                datos_cabecera["orden_compra"],
                datos_cabecera["orden_compra_cliente"],
                datos_cabecera["remision_facturada"],
                datos_cabecera["factura_impresa"],
                datos_cabecera.get("confirmado", 0),  # BIT: 0 o 1, por defecto 0
                datos_cabecera["fecha_factura"],
                _ahora,
                _ahora,
            )
            
            cursor.execute(sql, values)
            self.conn.commit()
            
            logger.debug(f"✅ Remisión cabecera insertada: {remision_id} - {datos_cabecera['codigo_factura']}")
            return remision_id
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar remision_cabecera: {e}")
            logger.error(f"   Factura: {datos_cabecera.get('codigo_factura')}")
            raise
        finally:
            cursor.close()
    
    def get_remisiones_paginadas(
        self, 
        page: int = 1, 
        page_size: int = 10
    ) -> Dict[str, Any]:
        """
        Obtiene remisiones con paginación.
        
        Args:
            page: Número de página (empezando en 1)
            page_size: Tamaño de página
            
        Returns:
            Dict con datos paginados y metadata
        """
        cursor = self.conn.cursor()
        try:
            # Calcular offset
            offset = (page - 1) * page_size
            
            # Contar total de registros
            cursor.execute("SELECT COUNT(*) FROM remision_cabecera")
            count_result = cursor.fetchone()
            total = count_result[0] if count_result else 0
            
            # Obtener registros paginados
            sql = """
            SELECT 
                remision_id,
                empresa,
                codigo_cliente,
                fecha_remision,
                codigo_factura,
                anulada,
                numero_pedido_sistema,
                numero_orden,
                numero_factura,
                tipo_documento,
                orden_compra,
                orden_compra_cliente,
                remision_facturada,
                factura_impresa,
                confirmado,
                fecha_factura,
                created_at,
                updated_at
            FROM remision_cabecera
            ORDER BY fecha_remision DESC, created_at DESC
            OFFSET ? ROWS
            FETCH NEXT ? ROWS ONLY
            """
            
            cursor.execute(sql, (offset, page_size))
            results = cursor.fetchall()
            
            # Convertir a diccionarios con nombres en UPPER_CASE para el frontend
            remisiones = []
            for row in results:
                remision = {
                    "CODIGO_FACTURA": row[4],
                    "ANULADA": bool(row[5]) if row[5] is not None else False,
                    "NUMERO_PEDIDO_SISTEMA": row[6],
                    "NUMERO_ORDEN": row[7],
                    "FACTURA_IMPRESA": bool(row[13]) if row[13] is not None else False,
                    "NUMERO_FACTURA": row[8],
                    "EMPRESA": row[1],
                    "CODIGO_CLIENTE": row[2],
                    "FECHA_FACTURA": serialize_date(row[15]) or serialize_date(row[3]) or None,  # fecha_factura o fecha_remision
                    "TIPO_DOCUMENTO": row[9],
                    "ObjDatosFactura": None,  # Las remisiones no tienen detalles
                    "ORDEN_COMPRA": row[10],
                    "ORDEN_COMPRA_CLIENTE": row[11],
                    "Remision_Facturada": bool(row[12]) if row[12] is not None else False,
                    "CONFIRMADO": bool(row[14]) if row[14] is not None else False
                }
                remisiones.append(remision)
            
            # Calcular total de páginas
            total_pages = (total + page_size - 1) // page_size if total > 0 else 0
            
            return {
                "data": remisiones,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
        finally:
            cursor.close()

