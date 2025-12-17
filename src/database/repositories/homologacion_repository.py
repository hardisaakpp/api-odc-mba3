"""
Repositorio para operaciones relacionadas con homologación de productos.
"""

import logging
import pyodbc
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date
from decimal import Decimal

logger = logging.getLogger(__name__)


def serialize_date(value):
    """Convierte date/datetime a string ISO."""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def serialize_decimal(value):
    """Convierte Decimal a float."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class HomologacionRepository:
    """Repositorio para consultar productos no homologados."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def get_productos_no_homologados(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los productos de MBA3 que NO están homologados en SAP.
        
        Un producto NO está homologado si:
        - Existe en despacho_detalle (viene de MBA3)
        - NO existe en producto_sap_cache (nunca se consultó en SAP o no existe)
        
        Returns:
            Lista de diccionarios con información de productos no homologados:
            [
                {
                    "sku": "5-0012.9",
                    "nombre_producto": "Nombre del producto",
                    "veces_usado": 15,
                    "total_docenas": 456.0,
                    "total_valor": 2120.4,
                    "primera_aparicion": "2024-01-15",
                    "ultima_aparicion": "2024-03-20"
                },
                ...
            ]
        """
        cursor = self.conn.cursor()
        try:
            query = """
            SELECT 
                dd.sku,
                dd.nombre_producto,
                COUNT(*) AS veces_usado,
                SUM(dd.cantidad_docena_mba3) AS total_docenas,
                SUM(dd.total_linea_mba3) AS total_valor,
                MIN(dc.fecha_despacho) AS primera_aparicion,
                MAX(dc.fecha_despacho) AS ultima_aparicion
            FROM despacho_detalle dd
            INNER JOIN despacho_cabecera dc ON dd.despacho_id = dc.despacho_id
            LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
            WHERE dd.sku IS NOT NULL 
              AND dd.sku != ''
              AND psc.sku IS NULL  -- NO está en cache SAP (no homologado)
            GROUP BY dd.sku, dd.nombre_producto
            ORDER BY COUNT(*) DESC, dd.sku
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            productos = []
            for row in results:
                productos.append({
                    "sku": row[0],
                    "nombre_producto": row[1] if row[1] else "Sin nombre",
                    "veces_usado": row[2],
                    "total_docenas": float(row[3]) if row[3] is not None else 0.0,
                    "total_valor": float(row[4]) if row[4] is not None else 0.0,
                    "primera_aparicion": row[5].strftime("%Y-%m-%d") if row[5] else None,
                    "ultima_aparicion": row[6].strftime("%Y-%m-%d") if row[6] else None,
                })
            
            logger.debug(f"✅ Encontrados {len(productos)} productos no homologados")
            return productos
            
        except Exception as e:
            logger.error(f"❌ Error al consultar productos no homologados: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_estadisticas_homologacion(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas generales de homologación.
        
        Returns:
            Diccionario con estadísticas:
            {
                "total_productos_mba3": 150,
                "productos_homologados": 145,
                "productos_no_homologados": 5,
                "porcentaje_homologacion": 96.67
            }
        """
        cursor = self.conn.cursor()
        try:
            query = """
            SELECT 
                (SELECT COUNT(DISTINCT dd.sku) 
                 FROM despacho_detalle dd 
                 WHERE dd.sku IS NOT NULL AND dd.sku != '') AS total_productos_mba3,
                (SELECT COUNT(DISTINCT psc.sku) 
                 FROM producto_sap_cache psc 
                 WHERE psc.activo = 1) AS productos_homologados,
                (SELECT COUNT(DISTINCT dd.sku) 
                 FROM despacho_detalle dd
                 LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
                 WHERE dd.sku IS NOT NULL 
                   AND dd.sku != ''
                   AND psc.sku IS NULL) AS productos_no_homologados
            """
            
            cursor.execute(query)
            result = cursor.fetchone()
            
            if result:
                total_mba3 = result[0] or 0
                homologados = result[1] or 0
                no_homologados = result[2] or 0
                
                porcentaje = (homologados * 100.0 / total_mba3) if total_mba3 > 0 else 0.0
                
                return {
                    "total_productos_mba3": total_mba3,
                    "productos_homologados": homologados,
                    "productos_no_homologados": no_homologados,
                    "porcentaje_homologacion": round(porcentaje, 2)
                }
            
            return {
                "total_productos_mba3": 0,
                "productos_homologados": 0,
                "productos_no_homologados": 0,
                "porcentaje_homologacion": 0.0
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener estadísticas de homologación: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_skus_no_homologados(self) -> List[str]:
        """
        Obtiene una lista simple de SKUs no homologados.
        
        Returns:
            Lista de SKUs (strings)
        """
        cursor = self.conn.cursor()
        try:
            query = """
            SELECT DISTINCT dd.sku
            FROM despacho_detalle dd
            LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
            WHERE dd.sku IS NOT NULL 
              AND dd.sku != ''
              AND psc.sku IS NULL
            ORDER BY dd.sku
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            skus = [row[0] for row in results]
            return skus
            
        except Exception as e:
            logger.error(f"❌ Error al obtener SKUs no homologados: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_productos_no_homologados_por_empresa(self) -> List[Dict[str, Any]]:
        """
        Obtiene productos no homologados agrupados por empresa.
        
        Returns:
            Lista de diccionarios con información agrupada por empresa
        """
        cursor = self.conn.cursor()
        try:
            query = """
            SELECT 
                dc.empresa,
                dd.sku,
                dd.nombre_producto,
                COUNT(*) AS veces_usado,
                SUM(dd.cantidad_docena_mba3) AS total_docenas
            FROM despacho_detalle dd
            INNER JOIN despacho_cabecera dc ON dd.despacho_id = dc.despacho_id
            LEFT JOIN producto_sap_cache psc ON dd.sku = psc.sku AND psc.activo = 1
            WHERE dd.sku IS NOT NULL 
              AND dd.sku != ''
              AND psc.sku IS NULL
            GROUP BY dc.empresa, dd.sku, dd.nombre_producto
            ORDER BY dc.empresa, COUNT(*) DESC
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            productos = []
            for row in results:
                productos.append({
                    "empresa": row[0],
                    "sku": row[1],
                    "nombre_producto": row[2] if row[2] else "Sin nombre",
                    "veces_usado": row[3],
                    "total_docenas": float(row[4]) if row[4] is not None else 0.0,
                })
            
            return productos
            
        except Exception as e:
            logger.error(f"❌ Error al consultar productos no homologados por empresa: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def is_sku_ya_notificado(self, sku: str) -> bool:
        """
        Verifica si un SKU ya fue notificado anteriormente.
        
        Args:
            sku: SKU del producto a verificar
            
        Returns:
            True si ya fue notificado, False en caso contrario
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT COUNT(*) 
                FROM productos_no_homologados_notificados
                WHERE sku = ? AND activo = 1
                """,
                (sku,)
            )
            result = cursor.fetchone()
            return result[0] > 0 if result else False
        except Exception as e:
            logger.error(f"❌ Error al verificar si SKU ya fue notificado: {e}", exc_info=True)
            # En caso de error, retornar False para no bloquear la notificación
            return False
        finally:
            cursor.close()
    
    def get_skus_ya_notificados(self) -> set:
        """
        Obtiene el conjunto de SKUs que ya fueron notificados.
        
        Returns:
            Set de SKUs ya notificados
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                SELECT sku 
                FROM productos_no_homologados_notificados
                WHERE activo = 1
                """
            )
            results = cursor.fetchall()
            return {row[0] for row in results}
        except Exception as e:
            logger.error(f"❌ Error al obtener SKUs ya notificados: {e}", exc_info=True)
            # En caso de error, retornar set vacío
            return set()
        finally:
            cursor.close()
    
    def registrar_producto_notificado(self, sku: str) -> bool:
        """
        Registra un producto como notificado (o actualiza si ya existe).
        
        Args:
            sku: SKU del producto notificado
            
        Returns:
            True si se registró correctamente, False en caso contrario
        """
        cursor = self.conn.cursor()
        try:
            # Verificar si ya existe
            cursor.execute(
                """
                SELECT notificacion_id, veces_notificado
                FROM productos_no_homologados_notificados
                WHERE sku = ? AND activo = 1
                """,
                (sku,)
            )
            existing = cursor.fetchone()
            
            if existing:
                # ACTUALIZAR: incrementar contador y actualizar fecha
                cursor.execute(
                    """
                    UPDATE productos_no_homologados_notificados
                    SET veces_notificado = veces_notificado + 1,
                        ultima_notificacion = GETDATE(),
                        updated_at = GETDATE()
                    WHERE sku = ? AND activo = 1
                    """,
                    (sku,)
                )
                logger.debug(f"✅ Producto {sku} actualizado en notificados (veces: {existing[1] + 1})")
            else:
                # INSERTAR: primera notificación
                cursor.execute(
                    """
                    INSERT INTO productos_no_homologados_notificados (
                        sku,
                        fecha_notificacion,
                        veces_notificado,
                        ultima_notificacion,
                        activo,
                        created_at,
                        updated_at
                    ) VALUES (?, GETDATE(), 1, GETDATE(), 1, GETDATE(), GETDATE())
                    """,
                    (sku,)
                )
                logger.debug(f"✅ Producto {sku} registrado como notificado")
            
            self.conn.commit()
            return True
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al registrar producto notificado: {e}", exc_info=True)
            return False
        finally:
            cursor.close()
    
    def registrar_productos_notificados(self, skus: List[str]) -> int:
        """
        Registra múltiples productos como notificados.
        
        Args:
            skus: Lista de SKUs a registrar
            
        Returns:
            Número de productos registrados exitosamente
        """
        if not skus:
            return 0
        
        registrados = 0
        for sku in skus:
            if self.registrar_producto_notificado(sku):
                registrados += 1
        
        logger.info(f"✅ Registrados {registrados} de {len(skus)} productos como notificados")
        return registrados
    
    # =========================================================================
    # MÉTODOS PARA GESTIÓN DE HOMOLOGACIONES SKU (CRUD)
    # =========================================================================
    
    def get_homologaciones_sku(
        self, 
        page: int = 1, 
        page_size: int = 10,
        estado: Optional[str] = None,
        tiene_diferencias: Optional[bool] = None,
        tiene_datos_sap: Optional[bool] = None,
        sku: Optional[str] = None
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
            
            if sku:
                where_clauses.append("(sku_mba3 LIKE ? OR sku_sap LIKE ?)")
                params.extend([f"%{sku}%", f"%{sku}%"])
            
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
    
    def get_estadisticas_homologaciones_sku(self) -> Dict[str, int]:
        """
        Obtiene estadísticas de homologaciones por estado.
        
        Returns:
            Diccionario con conteos por estado
        """
        cursor = self.conn.cursor()
        try:
            query = """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN estado = 'PENDIENTE' THEN 1 ELSE 0 END) as pendientes,
                    SUM(CASE WHEN estado = 'HOMOLOGADO' THEN 1 ELSE 0 END) as homologados,
                    SUM(CASE WHEN estado = 'ERROR' THEN 1 ELSE 0 END) as errores
                FROM sku_homologacion
            """
            cursor.execute(query)
            row = cursor.fetchone()
            
            if row:
                return {
                    "count": row[0] or 0,
                    "total_pendientes": row[1] or 0,
                    "total_homologados": row[2] or 0,
                    "total_errores": row[3] or 0
                }
            
            return {
                "count": 0,
                "total_pendientes": 0,
                "total_homologados": 0,
                "total_errores": 0
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener estadísticas de homologaciones: {e}", exc_info=True)
            return {
                "count": 0,
                "total_pendientes": 0,
                "total_homologados": 0,
                "total_errores": 0
            }
        finally:
            cursor.close()


