"""
Repositorio interno para gestión de notificaciones de productos no homologados.
"""

import logging
import pyodbc
from typing import List

from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)


class NotificacionRepository:
    """Repositorio para gestionar notificaciones de productos no homologados."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
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
                _ahora = ahora_naive()
                cursor.execute(
                    """
                    UPDATE productos_no_homologados_notificados
                    SET veces_notificado = veces_notificado + 1,
                        ultima_notificacion = ?,
                        updated_at = ?
                    WHERE sku = ? AND activo = 1
                    """,
                    (_ahora, _ahora, sku)
                )
                logger.debug(f"✅ Producto {sku} actualizado en notificados (veces: {existing[1] + 1})")
            else:
                # INSERTAR: primera notificación
                _ahora = ahora_naive()
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
                    ) VALUES (?, ?, 1, ?, 1, ?, ?)
                    """,
                    (sku, _ahora, _ahora, _ahora, _ahora)
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

