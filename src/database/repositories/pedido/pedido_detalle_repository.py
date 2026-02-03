"""
Repositorio especializado para operaciones de pedido_detalle.

CHANGELOG:
- 2026-01-23: Extraído de pedido_repository.py
"""

import logging
import pyodbc
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class PedidoDetalleRepository:
    """Repositorio para operaciones de pedido_detalle."""

    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.

        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn

    def insert(self, pedido_id: str, datos_detalle: Dict[str, Any]) -> str:
        """
        Inserta un registro en pedido_detalle (artículo).
        
        ENFOQUE: Solo persiste lo que viene, sin recalcular totales.
        
        Args:
            pedido_id: UUID del pedido
            datos_detalle: Diccionario con datos del detalle (sin pedido_detalle_id)
            
        Returns:
            pedido_detalle_id (UUID) generado
        """
        cursor = self.conn.cursor()
        
        try:
            # Generar UUID para pedido_detalle_id
            cursor.execute("SELECT NEWID()")
            uuid_result = cursor.fetchone()
            if uuid_result is None:
                raise ValueError("No se pudo generar UUID para pedido_detalle_id")
            pedido_detalle_id = str(uuid_result[0])
            
            # Verificar si existe la columna comentario antes de incluirla en el INSERT
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido_detalle' 
                AND COLUMN_NAME = 'comentario'
            """)
            result = cursor.fetchone()
            tiene_comentario = result[0] > 0 if result else False
            
            if tiene_comentario:
                sql = """
                INSERT INTO pedido_detalle (
                    pedido_detalle_id,
                    pedido_id,
                    codigo_interno,
                    descripcion_sap,
                    marca,
                    codigo_barras,
                    pack,
                    costo_doc_sin_iva,
                    descuento_1,
                    pvp,
                    subtotal,
                    total,
                    comentario,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
                """
                
                values = (
                    pedido_detalle_id,
                    pedido_id,
                    datos_detalle.get("codigo_interno"),
                    datos_detalle.get("descripcion_sap"),
                    datos_detalle.get("marca"),
                    datos_detalle.get("codigo_barras"),
                    datos_detalle.get("pack"),
                    datos_detalle.get("costo_doc_sin_iva"),
                    datos_detalle.get("descuento_1"),
                    datos_detalle.get("pvp"),
                    datos_detalle.get("subtotal"),
                    datos_detalle.get("total"),
                    datos_detalle.get("comentario"),
                )
            else:
                sql = """
                INSERT INTO pedido_detalle (
                    pedido_detalle_id,
                    pedido_id,
                    codigo_interno,
                    descripcion_sap,
                    marca,
                    codigo_barras,
                    pack,
                    costo_doc_sin_iva,
                    descuento_1,
                    pvp,
                    subtotal,
                    total,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
                """
                
                values = (
                    pedido_detalle_id,
                    pedido_id,
                    datos_detalle.get("codigo_interno"),
                    datos_detalle.get("descripcion_sap"),
                    datos_detalle.get("marca"),
                    datos_detalle.get("codigo_barras"),
                    datos_detalle.get("pack"),
                    datos_detalle.get("costo_doc_sin_iva"),
                    datos_detalle.get("descuento_1"),
                    datos_detalle.get("pvp"),
                    datos_detalle.get("subtotal"),
                    datos_detalle.get("total"),
                )
            
            cursor.execute(sql, values)
            self.conn.commit()
            
            logger.debug(f"✅ Pedido detalle insertado: {pedido_detalle_id}")
            return pedido_detalle_id
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar pedido_detalle: {e}")
            raise
        finally:
            cursor.close()

    def delete_by_pedido_id(
        self, pedido_id: str, cursor: Optional[pyodbc.Cursor] = None
    ) -> int:
        """
        Elimina todos los registros de pedido_detalle de un pedido.
        Si se pasa cursor, no hace commit (para uso en transacción).

        Returns:
            Número de filas eliminadas.
        """
        own_cursor = cursor is None
        cur = cursor or self.conn.cursor()
        try:
            cur.execute("""
                DELETE FROM pedido_detalle WHERE pedido_id = ?
            """, (pedido_id,))
            count = cur.rowcount
            if own_cursor:
                self.conn.commit()
            if count > 0:
                logger.debug(f"✅ {count} detalles eliminados para pedido {pedido_id}")
            return count
        except Exception as e:
            if own_cursor:
                self.conn.rollback()
            logger.error(f"❌ Error al eliminar detalles del pedido {pedido_id}: {e}", exc_info=True)
            raise
        finally:
            if own_cursor:
                cur.close()

    def update_costo(
        self,
        pedido_detalle_id: str,
        nuevo_costo: float,
        modificado_por: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Actualiza el costo unitario de un detalle de pedido.
        
        Args:
            pedido_detalle_id: UUID del detalle del pedido
            nuevo_costo: Nuevo valor del costo unitario (DECIMAL)
            modificado_por: ID del usuario que realiza la modificación (opcional)
            
        Returns:
            Dict con información de la actualización
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT costo_doc_sin_iva, pedido_id
                FROM pedido_detalle
                WHERE pedido_detalle_id = ?
            """, (pedido_detalle_id,))
            
            row = cursor.fetchone()
            if not row:
                return {
                    "success": False,
                    "pedido_detalle_id": pedido_detalle_id,
                    "costo_anterior": None,
                    "costo_nuevo": float(nuevo_costo),
                    "mensaje": f"No se encontró el detalle del pedido con ID: {pedido_detalle_id}"
                }
            
            costo_anterior = row[0]
            costo_anterior_float = float(costo_anterior) if costo_anterior is not None else None
            
            set_clauses = [
                "costo_doc_sin_iva = ?",
                "updated_at = GETDATE()",
                "costo_modificado_manual = 1"
            ]
            values: List[Any] = [nuevo_costo]
            
            if modificado_por:
                set_clauses.append("modificado_por = ?")
                values.append(modificado_por)
            
            values.append(pedido_detalle_id)
            
            cursor.execute(f"""
                UPDATE pedido_detalle
                SET {', '.join(set_clauses)}
                WHERE pedido_detalle_id = ?
            """, values)
            
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.info(f"✅ Costo actualizado para pedido_detalle {pedido_detalle_id}")
                return {
                    "success": True,
                    "pedido_detalle_id": pedido_detalle_id,
                    "costo_anterior": costo_anterior_float,
                    "costo_nuevo": float(nuevo_costo),
                    "mensaje": "Costo actualizado correctamente"
                }
            else:
                return {
                    "success": False,
                    "pedido_detalle_id": pedido_detalle_id,
                    "costo_anterior": costo_anterior_float,
                    "costo_nuevo": float(nuevo_costo),
                    "mensaje": "No se pudo actualizar el costo (0 filas afectadas)"
                }
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar costo de pedido_detalle: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def update_total(
        self,
        pedido_detalle_id: str,
        nuevo_total: float,
        modificado_por: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Actualiza el total de un detalle de pedido.
        
        Args:
            pedido_detalle_id: UUID del detalle del pedido
            nuevo_total: Nuevo valor del total (DECIMAL)
            modificado_por: ID del usuario que realiza la modificación (opcional)
            
        Returns:
            Dict con información de la actualización
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT total, costo_doc_sin_iva, pedido_id
                FROM pedido_detalle
                WHERE pedido_detalle_id = ?
            """, (pedido_detalle_id,))
            
            row = cursor.fetchone()
            if not row:
                return {
                    "success": False,
                    "pedido_detalle_id": pedido_detalle_id,
                    "total_anterior": None,
                    "total_nuevo": nuevo_total,
                    "costo_actualizado": None,
                    "mensaje": f"No se encontró el detalle del pedido con ID: {pedido_detalle_id}"
                }
            
            total_anterior = row[0]
            costo_anterior = row[1]
            total_anterior_float = float(total_anterior) if total_anterior is not None else None
            costo_anterior_float = float(costo_anterior) if costo_anterior is not None else None
            
            set_clauses = [
                "total = ?",
                "updated_at = GETDATE()",
                "total_modificado_manual = 1"
            ]
            values: List[Any] = [nuevo_total]
            
            if modificado_por:
                set_clauses.append("modificado_por = ?")
                values.append(modificado_por)
            
            values.append(pedido_detalle_id)
            
            cursor.execute(f"""
                UPDATE pedido_detalle
                SET {', '.join(set_clauses)}
                WHERE pedido_detalle_id = ?
            """, values)
            
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.info(f"✅ Total actualizado para pedido_detalle {pedido_detalle_id}")
                return {
                    "success": True,
                    "pedido_detalle_id": pedido_detalle_id,
                    "total_anterior": total_anterior_float,
                    "total_nuevo": float(nuevo_total),
                    "costo_actualizado": costo_anterior_float,
                    "mensaje": "Total actualizado correctamente"
                }
            else:
                return {
                    "success": False,
                    "pedido_detalle_id": pedido_detalle_id,
                    "total_anterior": total_anterior_float,
                    "total_nuevo": float(nuevo_total),
                    "costo_actualizado": costo_anterior_float,
                    "mensaje": "No se pudo actualizar el total (0 filas afectadas)"
                }
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar total de pedido_detalle: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def update_comentario(
        self,
        pedido_detalle_id: str,
        nuevo_comentario: Optional[str],
        modificado_por: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Actualiza el comentario de un detalle de pedido.
        
        Args:
            pedido_detalle_id: UUID del detalle del pedido
            nuevo_comentario: Nuevo comentario (puede ser None para limpiar)
            modificado_por: ID del usuario que realiza la modificación (opcional)
            
        Returns:
            Dict con información de la actualización
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT comentario
                FROM pedido_detalle
                WHERE pedido_detalle_id = ?
            """, (pedido_detalle_id,))
            
            row = cursor.fetchone()
            if not row:
                return {
                    "success": False,
                    "pedido_detalle_id": pedido_detalle_id,
                    "comentario_anterior": None,
                    "comentario_nuevo": nuevo_comentario,
                    "mensaje": f"No se encontró el detalle del pedido con ID: {pedido_detalle_id}"
                }
            
            comentario_anterior = row[0]
            comentario_anterior_str = comentario_anterior if comentario_anterior else None
            nuevo_comentario_str = nuevo_comentario.strip() if nuevo_comentario and nuevo_comentario.strip() else None
            
            set_clauses = ["comentario = ?", "updated_at = GETDATE()"]
            if nuevo_comentario_str:
                set_clauses.append("comentario_modificado_manual = 1")
            
            values = [nuevo_comentario_str]
            
            if modificado_por:
                set_clauses.append("modificado_por = ?")
                values.append(modificado_por)
            
            values.append(pedido_detalle_id)
            
            cursor.execute(f"""
                UPDATE pedido_detalle
                SET {', '.join(set_clauses)}
                WHERE pedido_detalle_id = ?
            """, values)
            
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.info(f"✅ Comentario actualizado para pedido_detalle {pedido_detalle_id}")
                return {
                    "success": True,
                    "pedido_detalle_id": pedido_detalle_id,
                    "comentario_anterior": comentario_anterior_str,
                    "comentario_nuevo": nuevo_comentario_str,
                    "mensaje": "Comentario actualizado correctamente"
                }
            else:
                return {
                    "success": False,
                    "pedido_detalle_id": pedido_detalle_id,
                    "comentario_anterior": comentario_anterior_str,
                    "comentario_nuevo": nuevo_comentario_str,
                    "mensaje": "No se pudo actualizar el comentario (0 filas afectadas)"
                }
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar comentario de pedido_detalle: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def guardar_modificaciones_columnas(
        self,
        numero_pedido: str,
        modificaciones: List[Dict[str, str]],
        modificado_por: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Guarda o actualiza modificaciones de columnas para un pedido.
        
        Args:
            numero_pedido: Número del pedido
            modificaciones: Lista de diccionarios con formato:
                [{"pedido_detalle_id": "uuid", "columna_key": "costo_doc_sin_iva"}, ...]
            modificado_por: ID del usuario que realiza la modificación (opcional)
        
        Returns:
            Dict con información de las modificaciones guardadas
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT pedido_id
                FROM pedido
                WHERE numero_pedido = ?
            """, (numero_pedido,))
            
            row = cursor.fetchone()
            if not row:
                return {
                    "success": False,
                    "numero_pedido": numero_pedido,
                    "modificaciones_guardadas": 0,
                    "mensaje": f"No se encontró el pedido con número: {numero_pedido}"
                }
            
            pedido_id = str(row[0])
            columnas_validas = {'costo_doc_sin_iva', 'total', 'comentario'}
            modificaciones_count = 0
            errores = []
            
            for mod in modificaciones:
                pedido_detalle_id = mod.get('pedido_detalle_id')
                columna_key = mod.get('columna_key')
                
                if not pedido_detalle_id or not columna_key:
                    errores.append(f"Modificación inválida: {mod}")
                    continue
                
                if columna_key not in columnas_validas:
                    errores.append(f"Columna inválida '{columna_key}' para detalle {pedido_detalle_id}")
                    continue
                
                cursor.execute("""
                    SELECT pedido_detalle_id
                    FROM pedido_detalle
                    WHERE pedido_detalle_id = ?
                    AND pedido_id = ?
                """, (pedido_detalle_id, pedido_id))
                
                detalle_row = cursor.fetchone()
                if not detalle_row:
                    errores.append(f"Detalle {pedido_detalle_id} no pertenece al pedido {numero_pedido}")
                    continue
                
                cursor.execute("""
                    MERGE pedido_detalle_modificacion_columna AS target
                    USING (SELECT ? AS pedido_detalle_id, ? AS columna_key, ? AS modificado_por) AS source
                    ON target.pedido_detalle_id = source.pedido_detalle_id 
                    AND target.columna_key = source.columna_key
                    WHEN MATCHED THEN
                        UPDATE SET 
                            modificado_por = source.modificado_por,
                            fecha_modificacion = GETDATE()
                    WHEN NOT MATCHED THEN
                        INSERT (pedido_detalle_id, columna_key, modificado_por, fecha_modificacion)
                        VALUES (source.pedido_detalle_id, source.columna_key, source.modificado_por, GETDATE());
                """, (pedido_detalle_id, columna_key, modificado_por))
                
                modificaciones_count += 1
            
            self.conn.commit()
            
            mensaje = f"Se guardaron {modificaciones_count} modificaciones correctamente"
            if errores:
                mensaje += f". Errores: {len(errores)}"
                logger.warning(f"⚠️ Errores al guardar modificaciones: {errores}")
            
            logger.info(f"✅ Guardadas {modificaciones_count} modificaciones para pedido {numero_pedido}")
            
            return {
                "success": True,
                "numero_pedido": numero_pedido,
                "modificaciones_guardadas": modificaciones_count,
                "mensaje": mensaje,
                "errores": errores if errores else None
            }
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al guardar modificaciones de columnas: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

    def obtener_modificaciones_columnas(
        self,
        numero_pedido: str
    ) -> Dict[str, Any]:
        """
        Obtiene las modificaciones de columnas para un pedido.
        
        Args:
            numero_pedido: Número del pedido
        
        Returns:
            Dict con las modificaciones encontradas
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT pedido_id
                FROM pedido
                WHERE numero_pedido = ?
            """, (numero_pedido,))
            
            row = cursor.fetchone()
            if not row:
                return {
                    "success": False,
                    "numero_pedido": numero_pedido,
                    "modificaciones": [],
                    "mensaje": f"No se encontró el pedido con número: {numero_pedido}"
                }
            
            pedido_id = str(row[0])
            
            cursor.execute("""
                SELECT 
                    m.pedido_detalle_id,
                    m.columna_key,
                    m.modificado_por,
                    m.fecha_modificacion
                FROM pedido_detalle_modificacion_columna m
                INNER JOIN pedido_detalle d ON m.pedido_detalle_id = d.pedido_detalle_id
                WHERE d.pedido_id = ?
                ORDER BY m.fecha_modificacion DESC
            """, (pedido_id,))
            
            rows = cursor.fetchall()
            modificaciones = []
            
            for row in rows:
                fecha_mod = row[3]
                fecha_mod_iso = fecha_mod.isoformat() if fecha_mod else None
                
                modificaciones.append({
                    "pedido_detalle_id": str(row[0]),
                    "columna_key": row[1],
                    "modificado_por": row[2] if row[2] else None,
                    "fecha_modificacion": fecha_mod_iso
                })
            
            logger.info(f"✅ Obtenidas {len(modificaciones)} modificaciones para pedido {numero_pedido}")
            
            return {
                "success": True,
                "numero_pedido": numero_pedido,
                "modificaciones": modificaciones,
                "mensaje": f"Se encontraron {len(modificaciones)} modificaciones"
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener modificaciones de columnas: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
