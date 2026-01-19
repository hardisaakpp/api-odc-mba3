"""
Servicio para consultar SAP y poblar el cache de bodegas/tiendas.
"""

import logging
from typing import Optional, Dict, Any, List

from src.config import SAP_CACHE_DAYS, ENABLE_SAP_QUERIES
from ..connection import get_db_connection
from ..clients.sap_client import SAPClient
from ..repositories.bodega_sap_repository import BodegaSAPRepository

logger = logging.getLogger(__name__)


class BodegaSAPService:
    """Servicio para gestionar consultas a SAP y cache de bodegas/tiendas."""
    
    def __init__(self):
        """Inicializa el servicio SAP."""
        self.sap_client = SAPClient()
        self.enabled = ENABLE_SAP_QUERIES
    
    def _es_bodega_central(self, whs_code: str) -> bool:
        """
        Determina si un código es una bodega central basándose en los códigos conocidos.
        
        Args:
            whs_code: Código de bodega/tienda
            
        Returns:
            True si es bodega central (RL-CD, OUT-CD, REG-CD), False si es tienda
        """
        whs_code_upper = whs_code.strip().upper()
        bodegas_centrales = {'RL-CD', 'OUT-CD', 'REG-CD'}
        return whs_code_upper in bodegas_centrales
    
    def get_or_fetch_bodega_info(self, whs_code: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de una bodega/tienda desde el cache o consulta SAP si es necesario.
        
        Este método:
        1. Busca en el cache si existe y es válido
        2. Si no existe o expiró, consulta SAP
        3. Guarda/actualiza el cache con la información obtenida
        4. Retorna la información de la bodega/tienda
        
        Args:
            whs_code: Código de bodega/tienda (WhsCode) a consultar
            force_refresh: Si True, fuerza la consulta a SAP incluso si el cache es válido
            
        Returns:
            Diccionario con información de la bodega/tienda:
            {
                "WhsCode": "RL-CD",
                "WhsName": "BODEGA ROLAND CD",
                "es_bodega": True
            }
            O None si:
            - No se encuentra en SAP
            - Hay error al consultar
        """
        if not self.enabled:
            logger.debug(f"⏭️ Servicio SAP deshabilitado para WhsCode: {whs_code}")
            return None
        
        if not whs_code or not whs_code.strip():
            logger.warning("⚠️ WhsCode vacío o inválido")
            return None
        
        whs_code_normalized = whs_code.strip().upper()
        es_bodega_central = self._es_bodega_central(whs_code_normalized)
        
        conn = None
        try:
            conn = get_db_connection()
            repository = BodegaSAPRepository(conn)
            
            # Verificar cache si no se fuerza refresh
            if not force_refresh:
                cache_valid = repository.is_cache_valid(whs_code_normalized, cache_days=SAP_CACHE_DAYS)
                if cache_valid:
                    bodega = repository.find_by_whs_code(whs_code_normalized)
                    if bodega:
                        logger.info(f"📦 Información de bodega/tienda {whs_code_normalized} obtenida del cache: '{bodega.get('whs_name')}'")
                        return {
                            "WhsCode": bodega["whs_code"],
                            "WhsName": bodega["whs_name"],
                            "es_bodega": bodega.get("es_bodega", es_bodega_central)
                        }
            
            # Cache no válido o force_refresh=True, consultar SAP
            logger.debug(f"🔍 Consultando SAP para bodega/tienda: {whs_code_normalized}")
            sap_info = self.sap_client.get_bodega_info(whs_code_normalized)
            
            if not sap_info:
                logger.debug(f"⚠️ Bodega/Tienda no encontrada en SAP: {whs_code_normalized}")
                return None
            
            # Preparar datos para guardar en cache
            bodega_data = {
                "whs_code": whs_code_normalized,
                "whs_name": sap_info.get("WhsName"),
                "es_bodega": es_bodega_central,  # Determinar si es bodega central
                "activo": True
            }
            
            # Guardar/actualizar en cache
            try:
                repository.insert_or_update(bodega_data)
                logger.info(
                    f"✅ Información SAP obtenida y cacheada para {whs_code_normalized}: "
                    f"Nombre={sap_info.get('WhsName')}, EsBodega={es_bodega_central}"
                )
            except Exception as cache_error:
                # Log específico del error de cache, pero continuar retornando la información
                logger.warning(
                    f"⚠️ Error al guardar en cache para {whs_code_normalized}: {cache_error}. "
                    f"Continuando sin cachear, pero retornando información SAP obtenida."
                )
            
            return {
                "WhsCode": whs_code_normalized,
                "WhsName": sap_info.get("WhsName"),
                "es_bodega": es_bodega_central
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener información SAP para {whs_code_normalized}: {e}", exc_info=True)
            return None
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def validate_codigos_bodegas_tiendas(
        self, 
        codigos: List[str], 
        force_refresh: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """
        Valida una lista de códigos de bodegas/tiendas consultando caché primero y SAP solo si es necesario.
        
        Este método es más eficiente que obtener todas las bodegas:
        1. Verifica qué códigos ya están en caché (y son válidos)
        2. Solo consulta SAP para los códigos que NO están en caché
        3. Guarda los nuevos códigos en caché
        4. Retorna un diccionario con la información de todos los códigos
        
        Args:
            codigos: Lista de códigos de bodegas/tiendas a validar
            force_refresh: Si True, fuerza la consulta a SAP incluso si están en caché
            
        Returns:
            Diccionario con información de cada código:
            {
                "RL-CD": {"WhsCode": "RL-CD", "WhsName": "...", "es_bodega": True, "encontrado": True},
                "TIENDA01": {"WhsCode": "TIENDA01", "WhsName": "...", "es_bodega": False, "encontrado": True},
                "NOEXISTE": {"WhsCode": "NOEXISTE", "encontrado": False}
            }
        """
        if not self.enabled:
            logger.debug("⏭️ Servicio SAP deshabilitado para validar códigos")
            return {}
        
        if not codigos:
            return {}
        
        conn = None
        resultado = {}
        codigos_a_consultar_sap = []
        
        try:
            conn = get_db_connection()
            repository = BodegaSAPRepository(conn)
            
            # Normalizar códigos y limpiar
            codigos_normalizados = [c.strip().upper() for c in codigos if c and c.strip()]
            
            # Paso 1: Verificar qué códigos están en caché y son válidos
            for codigo in codigos_normalizados:
                if force_refresh:
                    # Si se fuerza refresh, todos van a SAP
                    codigos_a_consultar_sap.append(codigo)
                    continue
                
                cache_valid = repository.is_cache_valid(codigo, cache_days=SAP_CACHE_DAYS)
                if cache_valid:
                    bodega = repository.find_by_whs_code(codigo)
                    if bodega:
                        resultado[codigo] = {
                            "WhsCode": bodega["whs_code"],
                            "WhsName": bodega["whs_name"],
                            "es_bodega": bodega.get("es_bodega", self._es_bodega_central(codigo)),
                            "encontrado": True,
                            "fuente": "cache"
                        }
                        logger.info(f"📦 Código {codigo} encontrado en caché: '{bodega.get('whs_name')}'")
                    else:
                        # No está en caché, consultar SAP
                        codigos_a_consultar_sap.append(codigo)
                else:
                    # Cache expirado o no existe, consultar SAP
                    codigos_a_consultar_sap.append(codigo)
            
            # Paso 2: Consultar SAP solo para códigos que faltan en caché
            if codigos_a_consultar_sap:
                logger.info(f"🔍 Consultando SAP para {len(codigos_a_consultar_sap)} códigos nuevos/faltantes: {codigos_a_consultar_sap[:5]}...")
                
                # Consultar SAP individualmente para cada código faltante
                nuevos_en_cache = []
                for codigo in codigos_a_consultar_sap:
                    try:
                        sap_info = self.sap_client.get_bodega_info(codigo)
                        
                        if sap_info:
                            # Encontrado en SAP, guardar en caché
                            es_bodega_central = self._es_bodega_central(codigo)
                            bodega_data = {
                                "whs_code": codigo,
                                "whs_name": sap_info.get("WhsName"),
                                "es_bodega": es_bodega_central,
                                "activo": True
                            }
                            
                            try:
                                repository.insert_or_update(bodega_data)
                                nuevos_en_cache.append(codigo)
                            except Exception as cache_error:
                                logger.warning(f"⚠️ Error al guardar en caché {codigo}: {cache_error}")
                            
                            resultado[codigo] = {
                                "WhsCode": codigo,
                                "WhsName": sap_info.get("WhsName"),
                                "es_bodega": es_bodega_central,
                                "encontrado": True,
                                "fuente": "sap"
                            }
                            logger.debug(f"✅ Código {codigo} encontrado en SAP y guardado en caché")
                        else:
                            # No encontrado en SAP
                            resultado[codigo] = {
                                "WhsCode": codigo,
                                "encontrado": False,
                                "fuente": "sap"
                            }
                            logger.debug(f"⚠️ Código {codigo} NO encontrado en SAP")
                    except Exception as e:
                        logger.warning(f"⚠️ Error al consultar SAP para {codigo}: {e}")
                        resultado[codigo] = {
                            "WhsCode": codigo,
                            "encontrado": False,
                            "error": str(e),
                            "fuente": "sap"
                        }
                
                if nuevos_en_cache:
                    logger.info(f"✅ {len(nuevos_en_cache)} códigos nuevos guardados en caché: {nuevos_en_cache[:5]}...")
            
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error al validar códigos: {e}", exc_info=True)
            # Retornar diccionario vacío o parcial en caso de error
            return resultado
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def get_or_fetch_all_bodegas(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Obtiene TODAS las bodegas/tiendas desde el cache o consulta SAP si es necesario.
        
        Este método:
        1. Busca en el cache todas las bodegas válidas
        2. Si el cache está incompleto o expiró, consulta SAP
        3. Guarda/actualiza el cache con todas las bodegas obtenidas
        4. Retorna la lista completa de bodegas/tiendas
        
        Args:
            force_refresh: Si True, fuerza la consulta a SAP incluso si el cache es válido
            
        Returns:
            Lista de diccionarios con información de bodegas/tiendas:
            [
                {
                    "WhsCode": "RL-CD",
                    "WhsName": "BODEGA ROLAND CD",
                    "es_bodega": True
                },
                ...
            ]
            O lista vacía si hay error
        """
        if not self.enabled:
            logger.debug("⏭️ Servicio SAP deshabilitado para obtener todas las bodegas")
            return []
        
        conn = None
        try:
            conn = get_db_connection()
            repository = BodegaSAPRepository(conn)
            
            # Verificar cache si no se fuerza refresh
            if not force_refresh:
                bodegas_cache = repository.find_all_valid(cache_days=SAP_CACHE_DAYS)
                if bodegas_cache and len(bodegas_cache) > 0:
                    logger.debug(f"📦 {len(bodegas_cache)} bodegas/tiendas obtenidas del cache")
                    return [
                        {
                            "WhsCode": b["whs_code"],
                            "WhsName": b["whs_name"],
                            "es_bodega": b.get("es_bodega", self._es_bodega_central(b["whs_code"]))
                        }
                        for b in bodegas_cache
                    ]
            
            # Cache no válido o force_refresh=True, consultar SAP
            logger.debug("🔍 Consultando SAP para obtener TODAS las bodegas/tiendas")
            todas_bodegas_sap = self.sap_client.get_todas_bodegas()
            
            if not todas_bodegas_sap:
                logger.warning("⚠️ No se pudieron obtener bodegas desde SAP")
                return []
            
            # Preparar datos para guardar en cache (batch)
            bodegas_data = []
            for bodega_sap in todas_bodegas_sap:
                whs_code = bodega_sap.get("WhsCode")
                if whs_code:
                    whs_code_normalized = whs_code.strip().upper()
                    bodegas_data.append({
                        "whs_code": whs_code_normalized,
                        "whs_name": bodega_sap.get("WhsName"),
                        "es_bodega": self._es_bodega_central(whs_code_normalized),
                        "activo": True
                    })
            
            # Guardar/actualizar en cache (batch)
            try:
                repository.insert_or_update_batch(bodegas_data)
                logger.info(
                    f"✅ {len(bodegas_data)} bodegas/tiendas obtenidas y cacheadas desde SAP"
                )
            except Exception as cache_error:
                logger.warning(
                    f"⚠️ Error al guardar en cache (batch): {cache_error}. "
                    f"Continuando sin cachear, pero retornando información SAP obtenida."
                )
            
            return [
                {
                    "WhsCode": b["whs_code"],
                    "WhsName": b["whs_name"],
                    "es_bodega": b["es_bodega"]
                }
                for b in bodegas_data
            ]
            
        except Exception as e:
            logger.error(f"❌ Error al obtener todas las bodegas desde SAP: {e}", exc_info=True)
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
