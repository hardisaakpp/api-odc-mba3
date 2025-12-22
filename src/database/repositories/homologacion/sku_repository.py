"""
Repositorio interno para gestión CRUD de homologaciones SKU.
"""

import logging
import pyodbc
from typing import List, Dict, Any, Optional, Tuple

from .utils import serialize_date, serialize_decimal

logger = logging.getLogger(__name__)


class SkuRepository:
    """Repositorio para gestionar homologaciones SKU (CRUD)."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def get_homologaciones_sku(
        self, 
        page: int = 1, 
        page_size: int = 10,
        estado: Optional[str] = None,
        tiene_diferencias: Optional[bool] = None,
        tiene_datos_sap: Optional[bool] = None,
        sku: Optional[str] = None,
        search: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Obtiene lista de homologaciones SKU con filtros y paginación.
        
        Args:
            page: Número de página (empezando en 1)
            page_size: Cantidad de registros por página
            estado: Filtro por estado (PENDIENTE, HOMOLOGADO, ERROR)
            tiene_diferencias: Filtro por diferencias MBA3 vs SAP
            tiene_datos_sap: Filtro por presencia de datos SAP
            sku: Búsqueda por SKU (MBA3 o SAP)
            search: Búsqueda general en SKU y nombres de producto (MBA3 y SAP)
            
        Returns:
            Tupla (lista_homologaciones, total_registros)
        """
        cursor = self.conn.cursor()
        try:
            # Construir WHERE dinámicamente
            where_clauses = []
            params = []
            
            if estado:
                where_clauses.append("estado = ?")
                params.append(estado)
            
            if tiene_diferencias is not None:
                where_clauses.append("tiene_diferencias = ?")
                params.append(1 if tiene_diferencias else 0)
            
            if tiene_datos_sap is not None:
                where_clauses.append("tiene_datos_sap = ?")
                params.append(1 if tiene_datos_sap else 0)
            
            # Búsqueda por SKU específico (prioridad sobre search)
            if sku:
                where_clauses.append("(sku_mba3 LIKE ? OR sku_sap LIKE ?)")
                params.extend([f"%{sku}%", f"%{sku}%"])
            # Búsqueda general (si no hay sku específico)
            elif search:
                search_pattern = f"%{search}%"
                where_clauses.append(
                    "(sku_mba3 LIKE ? OR sku_sap LIKE ? OR "
                    "nombre_producto_mba3 LIKE ? OR nombre_producto_sap LIKE ?)"
                )
                params.extend([search_pattern, search_pattern, search_pattern, search_pattern])
            
            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            
            # Contar total de registros (para paginación)
            count_query = f"""
                SELECT COUNT(*) 
                FROM sku_homologacion 
                {where_sql}
            """
            cursor.execute(count_query, params)
            result = cursor.fetchone()
            total = result[0] if result else 0
            
            # Obtener registros paginados
            offset = (page - 1) * page_size
            data_query = f"""
                SELECT 
                    homologacion_id,
                    sku_mba3,
                    nombre_producto_mba3,
                    precio_unitario_mba3,
                    cantidad_docena_mba3,
                    total_linea_mba3,
                    sku_sap,
                    nombre_producto_sap,
                    precio_unitario_sap,
                    cantidad_pack_sap,
                    unidad_sap,
                    subtotal_sap,
                    estado,
                    tiene_diferencias,
                    tiene_datos_sap,
                    detalle_id,
                    despacho_id,
                    created_at,
                    updated_at,
                    ultima_modificacion,
                    modificado_por
                FROM sku_homologacion
                {where_sql}
                ORDER BY created_at DESC
                OFFSET ? ROWS
                FETCH NEXT ? ROWS ONLY
            """
            cursor.execute(data_query, params + [offset, page_size])
            rows = cursor.fetchall()
            
            homologaciones = []
            for row in rows:
                homologaciones.append({
                    "homologacion_id": str(row[0]),
                    "sku_mba3": row[1],
                    "nombre_producto_mba3": row[2],
                    "precio_unitario_mba3": serialize_decimal(row[3]),
                    "cantidad_docena_mba3": serialize_decimal(row[4]),
                    "total_linea_mba3": serialize_decimal(row[5]),
                    "sku_sap": row[6],
                    "nombre_producto_sap": row[7],
                    "precio_unitario_sap": serialize_decimal(row[8]),
                    "cantidad_pack_sap": serialize_decimal(row[9]),
                    "unidad_sap": row[10],
                    "subtotal_sap": serialize_decimal(row[11]),
                    "estado": row[12],
                    "tiene_diferencias": bool(row[13]),
                    "tiene_datos_sap": bool(row[14]),
                    "detalle_id": str(row[15]) if row[15] else None,
                    "despacho_id": str(row[16]) if row[16] else None,
                    "created_at": serialize_date(row[17]),
                    "updated_at": serialize_date(row[18]),
                    "ultima_modificacion": serialize_date(row[19]),
                    "modificado_por": row[20]
                })
            
            logger.debug(f"✅ Obtenidas {len(homologaciones)} homologaciones (total: {total})")
            return homologaciones, total
            
        except Exception as e:
            logger.error(f"❌ Error al obtener homologaciones SKU: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_homologacion_by_id(self, homologacion_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene una homologación por ID.
        
        Args:
            homologacion_id: UUID de la homologación
            
        Returns:
            Diccionario con la homologación o None si no existe
        """
        cursor = self.conn.cursor()
        try:
            query = """
                SELECT 
                    homologacion_id,
                    sku_mba3,
                    nombre_producto_mba3,
                    precio_unitario_mba3,
                    cantidad_docena_mba3,
                    total_linea_mba3,
                    sku_sap,
                    nombre_producto_sap,
                    precio_unitario_sap,
                    cantidad_pack_sap,
                    unidad_sap,
                    subtotal_sap,
                    estado,
                    tiene_diferencias,
                    tiene_datos_sap,
                    detalle_id,
                    despacho_id,
                    created_at,
                    updated_at,
                    ultima_modificacion,
                    modificado_por
                FROM sku_homologacion
                WHERE homologacion_id = ?
            """
            cursor.execute(query, (homologacion_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return {
                "homologacion_id": str(row[0]),
                "sku_mba3": row[1],
                "nombre_producto_mba3": row[2],
                "precio_unitario_mba3": serialize_decimal(row[3]),
                "cantidad_docena_mba3": serialize_decimal(row[4]),
                "total_linea_mba3": serialize_decimal(row[5]),
                "sku_sap": row[6],
                "nombre_producto_sap": row[7],
                "precio_unitario_sap": serialize_decimal(row[8]),
                "cantidad_pack_sap": serialize_decimal(row[9]),
                "unidad_sap": row[10],
                "subtotal_sap": serialize_decimal(row[11]),
                "estado": row[12],
                "tiene_diferencias": bool(row[13]),
                "tiene_datos_sap": bool(row[14]),
                "detalle_id": str(row[15]) if row[15] else None,
                "despacho_id": str(row[16]) if row[16] else None,
                "created_at": serialize_date(row[17]),
                "updated_at": serialize_date(row[18]),
                "ultima_modificacion": serialize_date(row[19]),
                "modificado_por": row[20]
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener homologación {homologacion_id}: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def update_homologacion_sku(
        self, 
        homologacion_id: str, 
        data: Dict[str, Any],
        modificado_por: Optional[str] = None
    ) -> bool:
        """
        Actualiza una homologación SKU.
        
        Args:
            homologacion_id: UUID de la homologación
            data: Diccionario con campos a actualizar
            modificado_por: Usuario que realiza la modificación
            
        Returns:
            True si se actualizó, False si no existe
        """
        cursor = self.conn.cursor()
        try:
            # Construir SET dinámicamente
            set_clauses = []
            params = []
            
            # Campos actualizables
            updatable_fields = {
                'sku_sap': 'sku_sap',
                'nombre_producto_sap': 'nombre_producto_sap',
                'precio_unitario_sap': 'precio_unitario_sap',
                'cantidad_pack_sap': 'cantidad_pack_sap',
                'unidad_sap': 'unidad_sap',
                'subtotal_sap': 'subtotal_sap',
                'estado': 'estado'
            }
            
            for field, column in updatable_fields.items():
                if field in data:
                    set_clauses.append(f"{column} = ?")
                    params.append(data[field])
            
            if not set_clauses:
                logger.warning("No hay campos para actualizar")
                return False
            
            # Recalcular flags
            tiene_datos_sap = any([
                data.get('sku_sap'),
                data.get('nombre_producto_sap'),
                data.get('precio_unitario_sap'),
                data.get('cantidad_pack_sap'),
                data.get('unidad_sap'),
                data.get('subtotal_sap')
            ])
            
            set_clauses.extend([
                "tiene_datos_sap = ?",
                "updated_at = GETDATE()",
                "ultima_modificacion = GETDATE()"
            ])
            params.append(1 if tiene_datos_sap else 0)
            
            if modificado_por:
                set_clauses.append("modificado_por = ?")
                params.append(modificado_por)
            
            # Agregar homologacion_id al final
            params.append(homologacion_id)
            
            update_query = f"""
                UPDATE sku_homologacion
                SET {', '.join(set_clauses)}
                WHERE homologacion_id = ?
            """
            
            cursor.execute(update_query, params)
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.info(f"✅ Homologación {homologacion_id} actualizada")
                return True
            else:
                logger.warning(f"⚠️ Homologación {homologacion_id} no encontrada")
                return False
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar homologación {homologacion_id}: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def bulk_update_homologaciones(
        self, 
        updates: List[Dict[str, Any]],
        modificado_por: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Actualiza múltiples homologaciones en lote.
        
        Args:
            updates: Lista de diccionarios con homologacion_id y data
            modificado_por: Usuario que realiza la modificación
            
        Returns:
            Diccionario con resultados: {actualizadas, errores, detalles}
        """
        actualizadas = 0
        errores = 0
        detalles = []
        
        for update in updates:
            homologacion_id = update.get('homologacion_id')
            data = update.get('data', {})
            
            if not homologacion_id:
                errores += 1
                detalles.append({
                    "homologacion_id": None,
                    "success": False,
                    "error": "ID de homologación no proporcionado"
                })
                continue
            
            try:
                success = self.update_homologacion_sku(homologacion_id, data, modificado_por)
                if success:
                    actualizadas += 1
                    detalles.append({
                        "homologacion_id": homologacion_id,
                        "success": True
                    })
                else:
                    errores += 1
                    detalles.append({
                        "homologacion_id": homologacion_id,
                        "success": False,
                        "error": "No encontrada"
                    })
            except Exception as e:
                errores += 1
                detalles.append({
                    "homologacion_id": homologacion_id,
                    "success": False,
                    "error": str(e)
                })
        
        logger.info(f"✅ Actualización masiva: {actualizadas} exitosas, {errores} errores")
        return {
            "actualizadas": actualizadas,
            "errores": errores,
            "detalles": detalles
        }
    
    def sincronizar_homologaciones_desde_despachos(self) -> Dict[str, Any]:
        """
        Sincroniza homologaciones desde los despachos.
        Detecta SKUs que existen en despacho_detalle y busca diferencias con SAP.
        
        Returns:
            Diccionario con estadísticas de sincronización
        """
        cursor = self.conn.cursor()
        try:
            # Buscar productos en despachos con sus datos MBA3 y SAP
            query = """
                SELECT DISTINCT
                    dd.detalle_id,
                    dd.despacho_id,
                    dd.sku AS sku_mba3,
                    dd.nombre_producto AS nombre_producto_mba3,
                    dd.precio_unitario_mba3,
                    dd.cantidad_docena_mba3,
                    dd.total_linea_mba3,
                    psc.sku AS sku_sap,
                    psc.item_name AS nombre_producto_sap,
                    NULL AS precio_unitario_sap,
                    NULL AS cantidad_pack_sap,
                    psc.pack_sap AS unidad_sap
                FROM despacho_detalle dd
                LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
                WHERE dd.sku IS NOT NULL AND dd.sku != ''
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            homologaciones_encontradas = len(rows)
            homologaciones_nuevas = 0
            homologaciones_actualizadas = 0
            
            for row in rows:
                detalle_id = row[0]
                despacho_id = row[1]
                sku_mba3 = row[2]
                
                # Verificar si ya existe homologación para este detalle
                cursor.execute(
                    "SELECT homologacion_id FROM sku_homologacion WHERE detalle_id = ?",
                    (detalle_id,)
                )
                existing = cursor.fetchone()
                
                # Calcular flags
                tiene_datos_sap = bool(row[7] or row[8] or row[9] or row[10] or row[11])
                tiene_diferencias = False
                
                if tiene_datos_sap:
                    # Detectar diferencias
                    if row[2] != row[7]:  # SKU diferente
                        tiene_diferencias = True
                    elif row[4] and row[9]:  # Comparar precios
                        precio_mba3 = float(row[4]) if row[4] else 0
                        precio_sap = float(row[9]) if row[9] else 0
                        if abs(precio_mba3 - precio_sap) > 0.01:  # Tolerancia de 1 centavo
                            tiene_diferencias = True
                
                estado = 'PENDIENTE' if tiene_diferencias or not tiene_datos_sap else 'HOMOLOGADO'
                
                if existing:
                    # Actualizar existente
                    cursor.execute("""
                        UPDATE sku_homologacion
                        SET sku_sap = ?,
                            nombre_producto_sap = ?,
                            precio_unitario_sap = ?,
                            cantidad_pack_sap = ?,
                            unidad_sap = ?,
                            tiene_datos_sap = ?,
                            tiene_diferencias = ?,
                            estado = ?,
                            updated_at = GETDATE()
                        WHERE homologacion_id = ?
                    """, (
                        row[7], row[8], row[9], row[10], row[11],
                        1 if tiene_datos_sap else 0,
                        1 if tiene_diferencias else 0,
                        estado,
                        existing[0]
                    ))
                    homologaciones_actualizadas += 1
                else:
                    # Insertar nueva
                    cursor.execute("""
                        INSERT INTO sku_homologacion (
                            detalle_id,
                            despacho_id,
                            sku_mba3,
                            nombre_producto_mba3,
                            precio_unitario_mba3,
                            cantidad_docena_mba3,
                            total_linea_mba3,
                            sku_sap,
                            nombre_producto_sap,
                            precio_unitario_sap,
                            cantidad_pack_sap,
                            unidad_sap,
                            tiene_datos_sap,
                            tiene_diferencias,
                            estado
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        detalle_id, despacho_id,
                        row[2], row[3], row[4], row[5], row[6],
                        row[7], row[8], row[9], row[10], row[11],
                        1 if tiene_datos_sap else 0,
                        1 if tiene_diferencias else 0,
                        estado
                    ))
                    homologaciones_nuevas += 1
            
            self.conn.commit()
            
            resultado = {
                "homologaciones_encontradas": homologaciones_encontradas,
                "homologaciones_nuevas": homologaciones_nuevas,
                "homologaciones_actualizadas": homologaciones_actualizadas,
                "mensaje": "Sincronización completada"
            }
            
            logger.info(f"✅ Sincronización completada: {resultado}")
            return resultado
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al sincronizar homologaciones: {e}", exc_info=True)
            raise
        finally:
            cursor.close()

