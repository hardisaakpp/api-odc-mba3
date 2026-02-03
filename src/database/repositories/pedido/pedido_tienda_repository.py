"""
Repositorio especializado para operaciones de tiendas y distribuciones.

CHANGELOG:
- 2026-01-23: Extraído de pedido_repository.py
"""

import logging
import pyodbc
from typing import Dict, Any, List, Optional

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

    def insert_distribuciones(
        self,
        pedido_detalle_id: str,
        distribuciones: List[Dict[str, Any]]
    ) -> int:
        """
        Inserta distribuciones de un detalle por tiendas.
        
        Args:
            pedido_detalle_id: UUID del detalle
            distribuciones: Lista de dicts con tienda_id, cantidad y opcionalmente fila_origen, es_bodega
            
        Returns:
            Número de distribuciones insertadas
        """
        if not distribuciones:
            return 0
        
        cursor = self.conn.cursor()
        inserted_count = 0
        
        try:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido_detalle_tienda' 
                AND COLUMN_NAME = 'fila_origen'
            """)
            row = cursor.fetchone()
            tiene_fila_origen = (row[0] if row else 0) > 0
            
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido_detalle_tienda' 
                AND COLUMN_NAME = 'es_bodega'
            """)
            row = cursor.fetchone()
            tiene_es_bodega = (row[0] if row else 0) > 0
            
            columnas = ["id", "pedido_detalle_id", "tienda_id", "cantidad"]
            valores_placeholders = ["NEWID()", "?", "?", "?"]
            
            if tiene_fila_origen:
                columnas.append("fila_origen")
                valores_placeholders.append("?")
            
            if tiene_es_bodega:
                columnas.append("es_bodega")
                valores_placeholders.append("?")
            
            columnas.append("created_at")
            valores_placeholders.append("GETDATE()")
            
            sql = f"""
                INSERT INTO pedido_detalle_tienda (
                    {', '.join(columnas)}
                ) VALUES ({', '.join(valores_placeholders)})
                """
            
            for dist in distribuciones:
                try:
                    tienda_id = dist.get("tienda_id")
                    cantidad = dist.get("cantidad")
                    fila_origen = dist.get("fila_origen")
                    es_bodega = dist.get("es_bodega", False)
                    
                    if not tienda_id or not cantidad or cantidad <= 0:
                        continue
                    
                    if es_bodega:
                        logger.info(f"📦 Insertando bodega en BD: pedido_detalle_id={pedido_detalle_id}, tienda_id={tienda_id}, cantidad={cantidad}, es_bodega={es_bodega}, tiene_es_bodega_col={tiene_es_bodega}")
                    
                    valores = [pedido_detalle_id, tienda_id, cantidad]
                    
                    if tiene_fila_origen:
                        valores.append(fila_origen)
                    
                    if tiene_es_bodega:
                        valores.append(1 if es_bodega else 0)
                    
                    cursor.execute(sql, tuple(valores))
                    inserted_count += 1
                    
                except pyodbc.IntegrityError:
                    logger.debug(f"⚠️ Relación detalle-tienda ya existe: {pedido_detalle_id} - {dist.get('tienda_id')}")
                    continue
                except Exception as e:
                    logger.warning(f"⚠️ Error al insertar distribución: {e}")
                    continue
            
            self.conn.commit()
            logger.debug(f"✅ {inserted_count} distribuciones insertadas para detalle {pedido_detalle_id}")
            return inserted_count
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar distribuciones: {e}")
            raise
        finally:
            cursor.close()

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
            nombre_sap = None
            if (not nombre or nombre.strip() == "" or nombre.strip().upper() == codigo.strip().upper()) and consultar_sap:
                try:
                    from ...services.bodega_sap_service import BodegaSAPService
                    bodega_sap_service = BodegaSAPService()
                    bodega_info = bodega_sap_service.get_or_fetch_bodega_info(codigo, force_refresh=False)
                    if bodega_info:
                        whs_name = bodega_info.get("WhsName")
                        if whs_name:
                            nombre_sap = whs_name.strip()
                            logger.info(f"✅ Nombre de tienda obtenido (caché o SAP): {codigo} → '{nombre_sap}'")
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo obtener nombre de tienda {codigo} (caché o SAP): {e}")
            
            nombre_final = nombre_sap if nombre_sap else nombre
            
            cursor.execute("SELECT tienda_id, nombre FROM tienda WHERE codigo = ?", (codigo,))
            row = cursor.fetchone()
            
            if row:
                tienda_id = str(row[0])
                nombre_existente = row[1] if len(row) > 1 else None
                
                codigo_upper = codigo.strip().upper()
                nombre_existente_upper = str(nombre_existente).strip().upper() if nombre_existente else ""
                
                debe_actualizar = False
                if nombre_final and nombre_final.strip():
                    nombre_upper = nombre_final.strip().upper()
                    if (not nombre_existente or 
                        nombre_existente.strip() == "" or 
                        nombre_existente_upper == codigo_upper or
                        (nombre_upper != codigo_upper and nombre_upper != nombre_existente_upper)):
                        debe_actualizar = True
                
                if debe_actualizar and nombre_final:
                    nombre_final_stripped = nombre_final.strip()
                    cursor.execute("UPDATE tienda SET nombre = ?, updated_at = GETDATE() WHERE codigo = ?", (nombre_final_stripped, codigo))
                    self.conn.commit()
                    origen = "SAP" if nombre_sap else "Excel"
                    logger.info(f"✅ Nombre de tienda actualizado desde {origen}: {codigo} → '{nombre_final_stripped}' (anterior: '{nombre_existente}')")
                
                logger.debug(f"✅ Tienda existente encontrada: {codigo} ({tienda_id})")
                return tienda_id
            
            cursor.execute("SELECT NEWID()")
            uuid_result = cursor.fetchone()
            if uuid_result is None:
                raise ValueError("No se pudo generar UUID para tienda_id")
            tienda_id = str(uuid_result[0])
            
            nombre_guardar = None
            if nombre_final and nombre_final.strip():
                nombre_stripped = nombre_final.strip()
                if nombre_stripped.upper() != codigo.strip().upper():
                    nombre_guardar = nombre_stripped
                    origen = "SAP" if nombre_sap else "Excel"
                    logger.info(f"✅ Creando tienda con nombre desde {origen}: {codigo} → '{nombre_guardar}'")
                else:
                    logger.warning(f"⚠️ El nombre '{nombre_stripped}' es igual al código '{codigo}', guardando NULL")
            else:
                logger.warning(f"⚠️ No se pudo obtener nombre para tienda '{codigo}', guardando NULL")
            
            sql = """
            INSERT INTO tienda (
                tienda_id,
                codigo,
                nombre,
                activa,
                created_at
            ) VALUES (?, ?, ?, 1, GETDATE())
            """
            
            cursor.execute(sql, (tienda_id, codigo, nombre_guardar))
            self.conn.commit()
            
            logger.debug(f"✅ Nueva tienda creada: {codigo} ({tienda_id})")
            return tienda_id
            
        except pyodbc.IntegrityError as e:
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
        self, pedido_id: str, cursor: Optional[pyodbc.Cursor] = None
    ) -> int:
        """
        Elimina todas las filas de pedido_detalle_tienda asociadas a un pedido.
        Si se pasa cursor, no hace commit (para uso en transacción).

        Returns:
            Número de filas eliminadas.
        """
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
