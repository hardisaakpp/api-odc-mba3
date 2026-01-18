"""
Servicio para consultar SAP y poblar el cache de productos.
"""

import logging
from typing import Optional, Dict, Any

from src.config import SAP_CACHE_DAYS, ENABLE_SAP_QUERIES
from ..connection import get_db_connection
from ..clients.sap_client import SAPClient
from ..repositories.producto_sap_repository import ProductoSAPRepository

logger = logging.getLogger(__name__)


class SAPService:
    """Servicio para gestionar consultas a SAP y cache de productos."""
    
    def __init__(self):
        """Inicializa el servicio SAP."""
        self.sap_client = SAPClient()
        self.enabled = ENABLE_SAP_QUERIES
    
    def get_or_fetch_producto_info(self, sku: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de un producto desde el cache o consulta SAP si es necesario.
        
        Este método:
        1. Busca en el cache si existe y es válido
        2. Si no existe o expiró, consulta SAP
        3. Valida que el SKU de MBA3 coincida exactamente con el ItemCode de SAP
        4. Guarda/actualiza el cache con la información obtenida (solo si hay coincidencia)
        5. Retorna la información del producto
        
        IMPORTANTE: Si el SKU de MBA3 no coincide con el ItemCode de SAP, retorna None
        para evitar realizar conversiones incorrectas.
        
        Args:
            sku: SKU del producto a consultar (desde MBA3)
            force_refresh: Si True, fuerza la consulta a SAP incluso si el cache es válido
            
        Returns:
            Diccionario con información del producto:
            {
                "sku": "5-0012.9",
                "item_code": "5-0012.9",
                "item_name": "Nombre del producto",
                "pack_sap": "X3",
                "unidad_conversion": 4.0,
                "pack_id": "X3",
                "grupo_articulos": "R-MEDIAS"
            }
            O None si:
            - No se encuentra en SAP
            - El SKU de MBA3 no coincide con el ItemCode de SAP (mismatch)
            - Hay error al consultar
        """
        if not self.enabled:
            logger.debug(f"⏭️ Servicio SAP deshabilitado para SKU: {sku}")
            return None
        
        if not sku or not sku.strip():
            logger.warning("⚠️ SKU vacío o inválido")
            return None
        
        conn = None
        try:
            conn = get_db_connection()
            repository = ProductoSAPRepository(conn)
            
            # Verificar cache si no se fuerza refresh
            if not force_refresh:
                cache_valid = repository.is_cache_valid(sku, cache_days=SAP_CACHE_DAYS)
                if cache_valid:
                    producto = repository.find_by_sku(sku)
                    if producto:
                        # Validar que el SKU de MBA3 coincida con el ItemCode de SAP
                        item_code_cached = producto.get("item_code", "").strip()
                        sku_normalized = sku.strip()
                        
                        if item_code_cached.lower() != sku_normalized.lower():
                            logger.warning(
                                f"⚠️ MISMATCH detectado en cache: SKU MBA3='{sku_normalized}' "
                                f"no coincide con ItemCode SAP='{item_code_cached}'. "
                                f"No se realizarán conversiones para este producto."
                            )
                            # Retornar diccionario especial para indicar mismatch
                            return {
                                "_error": True,
                                "_error_type": "mismatch",
                                "_sku": sku_normalized,
                                "_item_code_sap": item_code_cached
                            }
                        
                        logger.debug(f"📦 Información de {sku} obtenida del cache")
                        return {
                            "sku": producto["sku"],
                            "item_code": producto["item_code"],
                            "item_name": producto["item_name"],
                            "pack_sap": producto["pack_sap"],
                            "unidad_conversion": producto["unidad_conversion"],
                            "pack_id": producto["pack_id"],
                            "grupo_articulos": producto.get("grupo_articulos"),
                        }
            
            # Cache no válido o force_refresh=True, consultar SAP
            logger.debug(f"🔍 Consultando SAP para SKU: {sku}")
            sap_info = self.sap_client.get_producto_info(sku)
            
            if not sap_info:
                logger.debug(f"⚠️ SKU no encontrado en SAP: {sku}")
                # Retornar diccionario especial para indicar que no existe en SAP
                return {
                    "_error": True,
                    "_error_type": "no_existe",
                    "_sku": sku,
                    "_item_code_sap": None
                }
            
            # ✅ VALIDACIÓN: Verificar que el SKU de MBA3 coincida con el ItemCode de SAP
            item_code_sap = sap_info.get("ItemCode", "").strip()
            sku_normalized = sku.strip()
            
            if item_code_sap.lower() != sku_normalized.lower():
                logger.warning(
                    f"⚠️ MISMATCH detectado: SKU MBA3='{sku_normalized}' "
                    f"no coincide con ItemCode SAP='{item_code_sap}'. "
                    f"No se realizarán conversiones para este producto."
                )
                # Retornar diccionario especial para indicar mismatch
                return {
                    "_error": True,
                    "_error_type": "mismatch",
                    "_sku": sku_normalized,
                    "_item_code_sap": item_code_sap
                }
            
            # Obtener unidad de conversión desde pack_conversion
            pack_sap = sap_info.get("U_IXX_PACK")
            unidad_conversion = None
            if pack_sap:
                unidad_conversion = repository.get_unidad_conversion_by_pack(pack_sap)
            
            # Preparar datos para guardar en cache
            producto_data = {
                "sku": sku,
                "item_code": sap_info.get("ItemCode", sku),
                "item_name": sap_info.get("ItemName"),
                "pack_sap": pack_sap,
                "unidad_conversion": unidad_conversion,
                "pack_id": pack_sap,  # pack_id es igual a pack_sap
                "grupo_articulos": sap_info.get("ItmsGrpNam"),
            }
            
            # Guardar/actualizar en cache
            try:
                repository.insert_or_update(producto_data)
                logger.info(
                    f"✅ Información SAP obtenida y cacheada para {sku}: "
                    f"Pack={pack_sap}, Unidad={unidad_conversion}, Grupo={producto_data.get('grupo_articulos')}"
                )
            except Exception as cache_error:
                # Log específico del error de cache, pero continuar retornando la información
                logger.warning(
                    f"⚠️ Error al guardar en cache para {sku}: {cache_error}. "
                    f"Continuando sin cachear, pero retornando información SAP obtenida."
                )
                # No retornar None, retornar la información aunque no se cachee
                # (el error ya se logueó en insert_or_update también)
            
            return producto_data
            
        except Exception as e:
            logger.error(f"❌ Error al obtener información SAP para {sku}: {e}", exc_info=True)
            # Retornar diccionario especial para indicar error
            return {
                "_error": True,
                "_error_type": "error",
                "_sku": sku,
                "_item_code_sap": None,
                "_error_message": str(e)
            }
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def get_unidad_conversion(self, sku: str) -> Optional[float]:
        """
        Obtiene la unidad de conversión para un SKU.
        
        Este es un método de conveniencia que obtiene solo la unidad de conversión.
        
        Args:
            sku: SKU del producto
            
        Returns:
            Unidad de conversión (float) o None si no se encuentra
        """
        producto_info = self.get_or_fetch_producto_info(sku)
        if producto_info:
            return producto_info.get("unidad_conversion")
        return None
    
    def get_pack_sap(self, sku: str) -> Optional[str]:
        """
        Obtiene el pack SAP para un SKU.
        
        Args:
            sku: SKU del producto
            
        Returns:
            Pack SAP (X1, X2, X3, etc.) o None si no se encuentra
        """
        producto_info = self.get_or_fetch_producto_info(sku)
        if producto_info:
            return producto_info.get("pack_sap")
        return None

