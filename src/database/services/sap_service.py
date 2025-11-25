"""
Servicio para consultar SAP y poblar el cache de productos.
"""

import logging
from typing import Optional, Dict, Any

from config import SAP_CACHE_DAYS, ENABLE_SAP_QUERIES
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
        3. Guarda/actualiza el cache con la información obtenida
        4. Retorna la información del producto
        
        Args:
            sku: SKU del producto a consultar
            force_refresh: Si True, fuerza la consulta a SAP incluso si el cache es válido
            
        Returns:
            Diccionario con información del producto:
            {
                "sku": "5-0012.9",
                "item_code": "5-0012.9",
                "item_name": "Nombre del producto",
                "pack_sap": "X3",
                "unidad_conversion": 4.0,
                "pack_id": "X3"
            }
            O None si no se encuentra o hay error
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
                        logger.debug(f"📦 Información de {sku} obtenida del cache")
                        return {
                            "sku": producto["sku"],
                            "item_code": producto["item_code"],
                            "item_name": producto["item_name"],
                            "pack_sap": producto["pack_sap"],
                            "unidad_conversion": producto["unidad_conversion"],
                            "pack_id": producto["pack_id"],
                        }
            
            # Cache no válido o force_refresh=True, consultar SAP
            logger.info(f"🔍 Consultando SAP para SKU: {sku}")
            sap_info = self.sap_client.get_producto_info(sku)
            
            if not sap_info:
                logger.warning(f"⚠️ No se encontró información en SAP para SKU: {sku}")
                return None
            
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
            }
            
            # Guardar/actualizar en cache
            repository.insert_or_update(producto_data)
            
            logger.info(
                f"✅ Información SAP obtenida y cacheada para {sku}: "
                f"Pack={pack_sap}, Unidad={unidad_conversion}"
            )
            
            return producto_data
            
        except Exception as e:
            logger.error(f"❌ Error al obtener información SAP para {sku}: {e}", exc_info=True)
            return None
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

