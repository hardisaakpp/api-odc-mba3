"""
Servicio para gestionar la detección y notificación de productos no homologados.
"""

import logging
from typing import List, Dict, Any, Set, Optional
from datetime import datetime

from ..connection import get_db_connection
from ..repositories.homologacion_repository import HomologacionRepository

logger = logging.getLogger(__name__)


class HomologacionService:
    """Servicio para gestionar productos no homologados."""
    
    def __init__(self):
        """Inicializa el servicio de homologación."""
        self._productos_no_homologados_detectados: Set[str] = set()
        # Diccionario para almacenar el tipo de problema por SKU
        # Clave: SKU, Valor: "no_existe" | "mismatch" | "error"
        self._tipos_problema: Dict[str, str] = {}
        # Diccionario para almacenar información adicional (ItemCode SAP en caso de mismatch)
        self._info_adicional: Dict[str, Any] = {}
    
    def detectar_producto_no_homologado(self, sku: str, tipo_problema: str = "no_existe", info_adicional: Optional[Dict[str, Any]] = None):
        """
        Registra un producto como no homologado durante el proceso de migración.
        
        Este método se llama cuando se detecta que un producto de MBA3
        no existe en SAP o hay un mismatch entre SKU e ItemCode.
        
        Args:
            sku: SKU del producto no homologado
            tipo_problema: Tipo de problema ("no_existe", "mismatch", "error")
            info_adicional: Información adicional (ej: item_code_sap para mismatch)
        """
        if sku and sku.strip():
            sku_normalized = sku.strip()
            self._productos_no_homologados_detectados.add(sku_normalized)
            self._tipos_problema[sku_normalized] = tipo_problema
            if info_adicional:
                self._info_adicional[sku_normalized] = info_adicional
            logger.debug(f"🔍 Producto no homologado detectado: {sku} (tipo: {tipo_problema})")
    
    def get_productos_detectados(self) -> List[str]:
        """
        Obtiene la lista de productos no homologados detectados en esta sesión.
        
        Returns:
            Lista de SKUs detectados como no homologados
        """
        return list(self._productos_no_homologados_detectados)
    
    def limpiar_detecciones(self):
        """Limpia la lista de productos detectados (para nueva sesión)."""
        self._productos_no_homologados_detectados.clear()
        self._tipos_problema.clear()
        self._info_adicional.clear()
    
    def get_productos_no_homologados_nuevos(self) -> List[Dict[str, Any]]:
        """
        Obtiene productos no homologados detectados en esta sesión que AÚN NO han sido notificados.
        
        Filtra los productos detectados para incluir solo aquellos que no han sido
        notificados anteriormente, evitando spam de emails.
        
        Returns:
            Lista de productos nuevos no homologados con información detallada
        """
        conn = None
        try:
            # Si no hay productos detectados en esta sesión, retornar vacío
            if not self._productos_no_homologados_detectados:
                logger.debug("✅ No hay productos detectados en esta sesión")
                return []
            
            conn = get_db_connection()
            repository = HomologacionRepository(conn)
            
            # Obtener SKUs que ya fueron notificados anteriormente
            skus_ya_notificados = repository.get_skus_ya_notificados()
            logger.debug(f"📋 SKUs ya notificados: {len(skus_ya_notificados)}")
            
            # Filtrar productos detectados: solo los que NO han sido notificados
            skus_nuevos_para_notificar = self._productos_no_homologados_detectados - skus_ya_notificados
            
            if not skus_nuevos_para_notificar:
                logger.info("✅ Todos los productos detectados ya fueron notificados anteriormente")
                return []
            
            logger.info(f"🔍 Productos nuevos para notificar: {len(skus_nuevos_para_notificar)} (de {len(self._productos_no_homologados_detectados)} detectados)")
            
            # Obtener todos los productos no homologados de la BD
            # (esto incluye los que se acaban de guardar en esta sesión)
            productos_existentes = repository.get_productos_no_homologados()
            
            # Crear diccionario para búsqueda rápida por SKU
            productos_dict = {p["sku"]: p for p in productos_existentes}
            
            # Obtener información detallada solo de los productos nuevos para notificar
            productos_info = []
            for sku in skus_nuevos_para_notificar:
                tipo_problema = self._tipos_problema.get(sku, "no_existe")
                info_adicional = self._info_adicional.get(sku, {})
                
                if sku in productos_dict:
                    # Producto existe en BD, usar información completa
                    producto = productos_dict[sku].copy()
                    producto["tipo_problema"] = tipo_problema
                    if info_adicional:
                        producto.update(info_adicional)
                    productos_info.append(producto)
                else:
                    # Producto muy nuevo (aún no está en la consulta de BD), crear entrada básica
                    producto = {
                        "sku": sku,
                        "nombre_producto": "Sin nombre",
                        "veces_usado": 1,
                        "total_docenas": 0.0,
                        "total_valor": 0.0,
                        "primera_aparicion": datetime.now().strftime("%Y-%m-%d"),
                        "ultima_aparicion": datetime.now().strftime("%Y-%m-%d"),
                        "tipo_problema": tipo_problema
                    }
                    if info_adicional:
                        producto.update(info_adicional)
                    productos_info.append(producto)
            
            logger.info(f"✅ Encontrados {len(productos_info)} productos NUEVOS para notificar")
            return productos_info
            
        except Exception as e:
            logger.error(f"❌ Error al obtener productos nuevos no homologados: {e}", exc_info=True)
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def registrar_productos_notificados(self, skus: List[str]) -> int:
        """
        Registra productos como notificados después de enviar el email.
        
        Args:
            skus: Lista de SKUs que fueron notificados
            
        Returns:
            Número de productos registrados exitosamente
        """
        if not skus:
            return 0
        
        conn = None
        try:
            conn = get_db_connection()
            repository = HomologacionRepository(conn)
            
            registrados = repository.registrar_productos_notificados(skus)
            logger.info(f"✅ Registrados {registrados} productos como notificados")
            return registrados
            
        except Exception as e:
            logger.error(f"❌ Error al registrar productos notificados: {e}", exc_info=True)
            return 0
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def get_todos_productos_no_homologados(self) -> Dict[str, Any]:
        """
        Obtiene todos los productos no homologados con estadísticas.
        
        Returns:
            Diccionario con:
            {
                "productos": [...],  # Lista de productos no homologados
                "estadisticas": {...},  # Estadísticas generales
                "skus": [...]  # Lista simple de SKUs
            }
        """
        conn = None
        try:
            conn = get_db_connection()
            repository = HomologacionRepository(conn)
            
            productos = repository.get_productos_no_homologados()
            estadisticas = repository.get_estadisticas_homologacion()
            skus = repository.get_skus_no_homologados()
            
            return {
                "productos": productos,
                "estadisticas": estadisticas,
                "skus": skus,
                "total": len(productos)
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener productos no homologados: {e}", exc_info=True)
            return {
                "productos": [],
                "estadisticas": {
                    "total_productos_mba3": 0,
                    "productos_homologados": 0,
                    "productos_no_homologados": 0,
                    "porcentaje_homologacion": 0.0
                },
                "skus": [],
                "total": 0
            }
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    # =========================================================================
    # MÉTODOS PARA GESTIÓN DE HOMOLOGACIONES SKU
    # =========================================================================
    
    def get_homologaciones_sku_paginadas(
        self,
        page: int = 1,
        page_size: int = 10,
        estado: Optional[str] = None,
        tiene_diferencias: Optional[bool] = None,
        tiene_datos_sap: Optional[bool] = None,
        sku: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Obtiene lista paginada de homologaciones SKU con filtros.
        
        Args:
            page: Número de página
            page_size: Tamaño de página
            estado: Filtro por estado
            tiene_diferencias: Filtro por diferencias
            tiene_datos_sap: Filtro por datos SAP
            sku: Búsqueda por SKU
            
        Returns:
            Diccionario con data, metadata, paginación
        """
        conn = None
        try:
            conn = get_db_connection()
            repository = HomologacionRepository(conn)
            
            # Obtener datos paginados
            homologaciones, total = repository.get_homologaciones_sku(
                page=page,
                page_size=page_size,
                estado=estado,
                tiene_diferencias=tiene_diferencias,
                tiene_datos_sap=tiene_datos_sap,
                sku=sku
            )
            
            # Obtener estadísticas
            estadisticas = repository.get_estadisticas_homologaciones_sku()
            
            # Calcular total de páginas
            total_pages = (total + page_size - 1) // page_size if total > 0 else 0
            
            return {
                "status": "success",
                "data": homologaciones,
                "metadata": {
                    **estadisticas,
                    "filters": {
                        "estado": estado,
                        "tiene_diferencias": tiene_diferencias,
                        "tiene_datos_sap": tiene_datos_sap,
                        "sku": sku
                    }
                },
                "total": total,
                "page": page,
                "pageSize": page_size,
                "totalPages": total_pages
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener homologaciones paginadas: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "data": [],
                "metadata": {
                    "count": 0,
                    "total_pendientes": 0,
                    "total_homologados": 0,
                    "total_errores": 0,
                    "filters": {}
                },
                "total": 0,
                "page": page,
                "pageSize": page_size,
                "totalPages": 0
            }
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def get_homologacion_by_id(self, homologacion_id: str) -> Dict[str, Any]:
        """
        Obtiene una homologación por ID.
        
        Args:
            homologacion_id: UUID de la homologación
            
        Returns:
            Diccionario con status y data
        """
        conn = None
        try:
            conn = get_db_connection()
            repository = HomologacionRepository(conn)
            
            homologacion = repository.get_homologacion_by_id(homologacion_id)
            
            if homologacion:
                return {
                    "status": "success",
                    "data": homologacion
                }
            else:
                return {
                    "status": "error",
                    "message": "Homologación no encontrada",
                    "error_code": "NOT_FOUND"
                }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener homologación {homologacion_id}: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "error_code": "INTERNAL_ERROR"
            }
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def update_homologacion_sku(
        self,
        homologacion_id: str,
        data: Dict[str, Any],
        modificado_por: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Actualiza una homologación SKU.
        
        Args:
            homologacion_id: UUID de la homologación
            data: Datos a actualizar
            modificado_por: Usuario que modifica
            
        Returns:
            Diccionario con status y resultado
        """
        conn = None
        try:
            conn = get_db_connection()
            repository = HomologacionRepository(conn)
            
            # Validar datos
            if 'precio_unitario_sap' in data and data['precio_unitario_sap'] is not None:
                if data['precio_unitario_sap'] < 0:
                    return {
                        "status": "error",
                        "message": "El precio unitario SAP debe ser mayor o igual a 0",
                        "error_code": "VALIDATION_ERROR"
                    }
            
            if 'cantidad_pack_sap' in data and data['cantidad_pack_sap'] is not None:
                if data['cantidad_pack_sap'] < 0:
                    return {
                        "status": "error",
                        "message": "La cantidad pack SAP debe ser mayor o igual a 0",
                        "error_code": "VALIDATION_ERROR"
                    }
            
            if 'estado' in data:
                if data['estado'] not in ['PENDIENTE', 'HOMOLOGADO', 'ERROR']:
                    return {
                        "status": "error",
                        "message": "Estado inválido. Debe ser PENDIENTE, HOMOLOGADO o ERROR",
                        "error_code": "VALIDATION_ERROR"
                    }
            
            # Actualizar
            success = repository.update_homologacion_sku(homologacion_id, data, modificado_por)
            
            if success:
                # Obtener registro actualizado
                homologacion_actualizada = repository.get_homologacion_by_id(homologacion_id)
                return {
                    "status": "success",
                    "data": homologacion_actualizada,
                    "message": "Homologación actualizada correctamente"
                }
            else:
                return {
                    "status": "error",
                    "message": "Homologación no encontrada",
                    "error_code": "NOT_FOUND"
                }
            
        except Exception as e:
            logger.error(f"❌ Error al actualizar homologación {homologacion_id}: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "error_code": "INTERNAL_ERROR"
            }
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def bulk_update_homologaciones(
        self,
        updates: List[Dict[str, Any]],
        modificado_por: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Actualiza múltiples homologaciones en lote.
        
        Args:
            updates: Lista de actualizaciones
            modificado_por: Usuario que modifica
            
        Returns:
            Diccionario con resultados
        """
        conn = None
        try:
            conn = get_db_connection()
            repository = HomologacionRepository(conn)
            
            resultado = repository.bulk_update_homologaciones(updates, modificado_por)
            
            return {
                "status": "success",
                "data": resultado
            }
            
        except Exception as e:
            logger.error(f"❌ Error al actualizar homologaciones en lote: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "error_code": "INTERNAL_ERROR"
            }
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def sincronizar_homologaciones(self) -> Dict[str, Any]:
        """
        Sincroniza homologaciones desde los despachos.
        
        Returns:
            Diccionario con resultados de sincronización
        """
        conn = None
        try:
            conn = get_db_connection()
            repository = HomologacionRepository(conn)
            
            resultado = repository.sincronizar_homologaciones_desde_despachos()
            
            return {
                "status": "success",
                "data": resultado
            }
            
        except Exception as e:
            logger.error(f"❌ Error al sincronizar homologaciones: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "error_code": "INTERNAL_ERROR"
            }
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass


