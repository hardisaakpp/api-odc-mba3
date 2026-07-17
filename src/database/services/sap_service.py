"""
Servicio para consultar SAP y poblar el cache de productos.
"""

import logging
from enum import Enum, auto
from typing import Literal, Optional, Dict, Any, Union

from src.config import SAP_CACHE_DAYS, ENABLE_SAP_QUERIES, USE_MIDDLEWARE_PRODUCTO_INFO
from ..connection import get_db_connection
from ..clients.sap_client import SAPClient
from ..clients.sap_service_layer_client import SAPServiceLayerClient
from ..repositories.producto_sap_repository import ProductoSAPRepository

logger = logging.getLogger(__name__)


class _MiddlewareSentinel(Enum):
    """Sentinel para distinguir "middleware no disponible" (fallback a OPENQUERY) de
    "no existe en SAP" (respuesta definitiva, que se representa con None)."""

    SIN_RESPUESTA = auto()


_SIN_RESPUESTA_MIDDLEWARE = _MiddlewareSentinel.SIN_RESPUESTA


class SAPService:
    """Servicio para gestionar consultas a SAP y cache de productos."""
    
    def __init__(self):
        """Inicializa el servicio SAP."""
        self.sap_client = SAPClient()
        self.enabled = ENABLE_SAP_QUERIES

    @staticmethod
    def _consultar_producto_via_middleware(
        sku: str,
    ) -> Union[Dict[str, Any], None, Literal[_MiddlewareSentinel.SIN_RESPUESTA]]:
        """
        Consulta el producto vía middleware (GET /api/v1/items/{code}).

        Returns:
            Dict con el mismo formato que SAPClient.get_producto_info,
            None si el middleware confirmó que el SKU no existe (404 definitivo),
            o _SIN_RESPUESTA_MIDDLEWARE si no está disponible y el caller debe
            hacer fallback a OPENQUERY.
        """
        item = SAPServiceLayerClient().get_item(sku)
        if item is None:
            return _SIN_RESPUESTA_MIDDLEWARE  # sin conexión: fallback
        if item.get("_error"):
            if item.get("_error_type") == "no_existe":
                return None
            return _SIN_RESPUESTA_MIDDLEWARE  # otro error: fallback
        return {
            "ItemCode": item.get("ItemCode"),
            "ItemName": item.get("ItemName"),
            "U_IXX_PACK": item.get("U_IXX_PACK"),
            "ItmsGrpNam": item.get("ItmsGrpNam"),
            "validFor": "Y" if item.get("Valid") == "tYES" else "N",
        }

    def _consultar_producto_sap(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Consulta info del producto en SAP: middleware primero
        (USE_MIDDLEWARE_PRODUCTO_INFO), con fallback automático a OPENQUERY
        si el middleware no responde.
        """
        if USE_MIDDLEWARE_PRODUCTO_INFO:
            resultado = self._consultar_producto_via_middleware(sku)
            if resultado is not _SIN_RESPUESTA_MIDDLEWARE:
                return resultado
            logger.warning(
                f"⚠️ Middleware no disponible para producto {sku}; fallback a OPENQUERY"
            )
        return self.sap_client.get_producto_info(sku)
    
    def _consultar_cache(
        self, repository: "ProductoSAPRepository", sku: str, force_refresh: bool
    ) -> Optional[Dict[str, Any]]:
        """
        Intenta satisfacer la consulta desde el cache local.

        Retorna el dict del producto (hit de cache), un dict de error ``_error``
        (mismatch detectado en cache), o ``None`` si no hay cache válido y el
        llamador debe continuar consultando SAP.
        """
        if force_refresh:
            return None
        if not repository.is_cache_valid(sku, cache_days=SAP_CACHE_DAYS):
            return None
        producto = repository.find_by_sku(sku)
        if not producto:
            return None
        item_code_cached = producto.get("item_code", "").strip()
        sku_normalized = sku.strip()
        if item_code_cached.lower() != sku_normalized.lower():
            logger.warning(
                f"⚠️ MISMATCH detectado en cache: SKU MBA3='{sku_normalized}' "
                f"no coincide con ItemCode SAP='{item_code_cached}'. "
                f"No se realizarán conversiones para este producto."
            )
            return {
                "_error": True,
                "_error_type": "mismatch",
                "_sku": sku_normalized,
                "_item_code_sap": item_code_cached,
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

            cached = self._consultar_cache(repository, sku, force_refresh)
            if cached is not None:
                return cached

            # Cache no válido o force_refresh=True: consultar SAP
            # (middleware primero, fallback a OPENQUERY)
            logger.debug(f"🔍 Consultando SAP para SKU: {sku}")
            sap_info = self._consultar_producto_sap(sku)

            if not sap_info:
                logger.debug(f"⚠️ SKU no encontrado en SAP: {sku}")
                return {"_error": True, "_error_type": "no_existe", "_sku": sku, "_item_code_sap": None}

            # ✅ VALIDACIÓN: Ítems inactivos en SAP se consideran no válidos para carga/ITR (generan sugerencias)
            valid_for = (sap_info.get("validFor") or sap_info.get("ValidFor") or "N").strip().upper()
            if valid_for != "Y":
                logger.warning(f"⚠️ SKU existe en SAP pero está Inactivo (validFor={valid_for}): {sku}")
                return {"_error": True, "_error_type": "inactivo", "_sku": sku, "_item_code_sap": sap_info.get("ItemCode")}

            # ✅ VALIDACIÓN: Verificar que el SKU de MBA3 coincida con el ItemCode de SAP
            item_code_sap = sap_info.get("ItemCode", "").strip()
            sku_normalized = sku.strip()
            if item_code_sap.lower() != sku_normalized.lower():
                logger.warning(
                    f"⚠️ MISMATCH detectado: SKU MBA3='{sku_normalized}' "
                    f"no coincide con ItemCode SAP='{item_code_sap}'. "
                    f"No se realizarán conversiones para este producto."
                )
                return {"_error": True, "_error_type": "mismatch", "_sku": sku_normalized, "_item_code_sap": item_code_sap}

            # Obtener unidad de conversión desde pack_conversion
            pack_sap = sap_info.get("U_IXX_PACK")
            unidad_conversion = None
            if pack_sap:
                unidad_conversion = repository.get_unidad_conversion_by_pack(pack_sap)

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

            return producto_data

        except Exception as e:
            logger.error(f"❌ Error al obtener información SAP para {sku}: {e}", exc_info=True)
            return {"_error": True, "_error_type": "error", "_sku": sku, "_item_code_sap": None, "_error_message": str(e)}
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
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

