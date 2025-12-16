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


