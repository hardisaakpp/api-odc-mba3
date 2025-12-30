"""
Cliente para consultar información de productos desde SAP (HANA) usando OPENQUERY.

Este cliente ejecuta consultas OPENQUERY desde SQL Server hacia SAP HANA
para obtener información de productos (ItemCode, ItemName, U_IXX_PACK, ItmsGrpNam).
"""

import logging
import re
import pyodbc
from typing import Optional, Dict, Any, List
from datetime import datetime

from src.config import (
    SAP_LINKED_SERVER,
    SAP_DATABASE,
    SAP_SCHEMA,
    ENABLE_SAP_QUERIES
)
from ..connection import get_sap_db_connection

logger = logging.getLogger(__name__)


class SAPClient:
    """Cliente para consultar información de productos desde SAP."""
    
    # Patrón permitido para ItemCode: alfanumérico, guiones, puntos, espacios
    # Longitud máxima: 50 caracteres (ajustable según necesidades)
    ITEM_CODE_PATTERN = re.compile(r'^[A-Za-z0-9.\- ]{1,50}$')
    
    def __init__(self):
        """Inicializa el cliente SAP."""
        self.enabled = ENABLE_SAP_QUERIES
        if not self.enabled:
            logger.warning("⚠️ Consultas SAP deshabilitadas (ENABLE_SAP_QUERIES=False)")
    
    def _validate_item_code(self, item_code: str) -> bool:
        """
        Valida que el item_code tenga un formato seguro antes de usarlo en SQL.
        
        Args:
            item_code: Código del producto a validar
            
        Returns:
            True si es válido, False en caso contrario
        """
        if not item_code or not item_code.strip():
            return False
        
        # Normalizar: quitar espacios al inicio y final
        normalized = item_code.strip()
        
        # Validar longitud
        if len(normalized) > 50:
            logger.warning(f"⚠️ ItemCode excede longitud máxima (50): {len(normalized)} caracteres")
            return False
        
        # Validar formato con regex (solo caracteres alfanuméricos, guiones, puntos, espacios)
        if not self.ITEM_CODE_PATTERN.match(normalized):
            logger.warning(f"⚠️ ItemCode contiene caracteres no permitidos: {item_code}")
            return False
        
        return True
    
    def get_producto_info(self, item_code: str) -> Optional[Dict[str, Any]]:
        """
        Consulta información de un producto desde SAP usando OPENQUERY.
        
        Args:
            item_code: Código del producto (ItemCode) a consultar
            
        Returns:
            Diccionario con información del producto:
            {
                "ItemCode": "5-0012.9",
                "ItemName": "Nombre del producto",
                "U_IXX_PACK": "X3",
                "ItmsGrpNam": "R-MEDIAS"
            }
            O None si no se encuentra o hay error
            
        Raises:
            Exception: Si hay error de conexión o consulta
        """
        if not self.enabled:
            logger.debug(f"⏭️ Consulta SAP deshabilitada para ItemCode: {item_code}")
            return None
        
        # Validar formato del item_code antes de procesarlo
        if not self._validate_item_code(item_code):
            logger.warning(f"⚠️ ItemCode inválido o inseguro: {item_code}")
            return None
        
        # Normalizar item_code (quitar espacios)
        item_code_normalized = item_code.strip()
        
        # Escapar comillas simples en el item_code para la consulta SQL
        # (aunque ya está validado, esto es una capa adicional de seguridad)
        item_code_escaped = item_code_normalized.replace("'", "''")
        
        # Construir consulta OPENQUERY
        # Nota: El servidor vinculado debe estar configurado en SQL Server
        query = f"""
        SELECT 
            T0."ItemCode",
            T0."ItemName",
            T0."U_IXX_PACK",
            T0."ItmsGrpNam"
        FROM OPENQUERY([{SAP_LINKED_SERVER}], '
            SELECT 
                T0."ItemCode",
                T0."ItemName",
                T0."U_IXX_PACK",
                T1."ItmsGrpNam"
            FROM "{SAP_DATABASE}"."OITM" T0
            LEFT JOIN "{SAP_DATABASE}"."OITB" T1 ON T0."ItmsGrpCod" = T1."ItmsGrpCod"
            WHERE T0."ItemCode" = ''{item_code_escaped}''
        ') T0;
        """
        
        conn = None
        try:
            logger.debug(f"🔍 Consultando SAP para ItemCode: {item_code_normalized}")
            # Usar conexión específica para SAP (servidor con OPENQUERY)
            conn = get_sap_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(query)
            result = cursor.fetchone()
            
            if result:
                producto_info = {
                    "ItemCode": result[0] if result[0] else None,
                    "ItemName": result[1] if result[1] else None,
                    "U_IXX_PACK": result[2] if result[2] else None,
                    "ItmsGrpNam": result[3] if result[3] else None,
                }
                logger.info(f"✅ Producto encontrado en SAP: {item_code_normalized} - Pack: {producto_info.get('U_IXX_PACK')}, Grupo: {producto_info.get('ItmsGrpNam')}")
                return producto_info
            else:
                logger.warning(f"⚠️ Producto no encontrado en SAP: {item_code_normalized}")
                return None
                
        except pyodbc.Error as e:
            error_msg = f"Error al consultar SAP para ItemCode {item_code_normalized}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            # No lanzar excepción, retornar None para que el sistema continúe
            return None
        except Exception as e:
            error_msg = f"Error inesperado al consultar SAP para ItemCode {item_code_normalized}: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            return None
        finally:
            if conn:
                try:
                    cursor.close()
                    conn.close()
                except:
                    pass
    
    def get_productos_info_batch(self, item_codes: list[str]) -> Dict[str, Dict[str, Any]]:
        """
        Consulta información de múltiples productos desde SAP en batch.
        
        Args:
            item_codes: Lista de códigos de productos a consultar
            
        Returns:
            Diccionario con ItemCode como clave y información del producto como valor:
            {
                "5-0012.9": {
                    "ItemCode": "5-0012.9",
                    "ItemName": "Nombre",
                    "U_IXX_PACK": "X3",
                    "ItmsGrpNam": "R-MEDIAS"
                },
                ...
            }
        """
        if not self.enabled:
            logger.debug(f"⏭️ Consulta SAP batch deshabilitada para {len(item_codes)} productos")
            return {}
        
        if not item_codes:
            return {}
        
        resultados = {}
        
        # Consultar cada producto individualmente
        # (Se podría optimizar con una consulta IN, pero OPENQUERY puede tener limitaciones)
        # Filtrar y validar item_codes antes de procesarlos
        valid_item_codes = [code for code in item_codes if self._validate_item_code(code)]
        invalid_count = len(item_codes) - len(valid_item_codes)
        
        if invalid_count > 0:
            logger.warning(f"⚠️ {invalid_count} códigos de producto inválidos filtrados antes de consultar SAP")
        
        for item_code in valid_item_codes:
            try:
                info = self.get_producto_info(item_code)
                if info:
                    resultados[item_code] = info
            except Exception as e:
                logger.warning(f"⚠️ Error al consultar {item_code}: {e}")
                continue
        
        logger.info(f"✅ Consultados {len(resultados)} de {len(item_codes)} productos desde SAP")
        return resultados
    
    def buscar_skus_similares(
        self, 
        sku_referencia: str, 
        limite: int = 20,
        solo_activos: bool = True,
        usar_staging: bool = True,
        longitud_minima: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Busca SKUs similares usando staging (preferido) o OPENQUERY SAP (fallback).
        
        VALIDACIONES IMPLEMENTADAS:
        #1: Normalización consistente (usa función centralizada)
        #2: Validación de SKU corto/genérico
        #3: Duplicados semánticos (manejados por scoring)
        #4: Límite antes del scoring (pide 3x más)
        #5: Observabilidad (métricas de staging vs SAP)
        
        Args:
            sku_referencia: SKU de referencia para buscar similares
            limite: Límite máximo de resultados (default: 20)
            solo_activos: Si True, solo busca productos activos
            usar_staging: Si True, intenta usar staging primero (recomendado)
            longitud_minima: Longitud mínima del código normalizado para validación
            
        Returns:
            Lista de productos SAP ordenados por relevancia:
            [{
                "ItemCode": "5-0012.9",
                "ItemName": "Nombre del producto",
                "U_IXX_PACK": "X3",
                "ItmsGrpNam": "R-MEDIAS",
                "validFor": "Y",
                "ItmsGrpCod": 103
            }, ...]
        """
        import time
        
        # Validar y normalizar SKU de referencia
        if not sku_referencia or not sku_referencia.strip():
            return []
        
        sku_clean = sku_referencia.strip()
        
        # Validar longitud máxima
        if len(sku_clean) > 50:
            logger.warning(f"⚠️ SKU de referencia demasiado largo: {len(sku_clean)} caracteres")
            return []
        
        # VALIDACIÓN #1: Normalización consistente (función centralizada)
        from src.utils import normalizar_codigo_producto, validar_longitud_minima_codigo
        sku_normalizado = normalizar_codigo_producto(sku_clean)
        
        if not sku_normalizado:
            logger.warning(f"⚠️ SKU '{sku_clean}' se normalizó a string vacío")
            return []
        
        # VALIDACIÓN #2: SKU corto/genérico
        if not validar_longitud_minima_codigo(sku_normalizado, longitud_minima):
            logger.warning(
                f"⚠️ SKU normalizado muy corto ({len(sku_normalizado)} < {longitud_minima}): "
                f"'{sku_normalizado}' (original: '{sku_clean}'). "
                f"La búsqueda puede devolver muchos resultados."
            )
            # Ajustar límite para SKUs cortos (más restrictivo)
            limite_ajustado = min(limite, 10)
        else:
            limite_ajustado = limite
        
        # INTENTO 1: Buscar en staging (rápido y eficiente)
        if usar_staging:
            start_time_staging = time.time()
            try:
                from ..connection import get_db_connection
                from ..repositories.producto_sap_staging_repository import ProductoSAPStagingRepository
                
                conn = get_db_connection()
                try:
                    staging_repo = ProductoSAPStagingRepository(conn)
                    productos = staging_repo.buscar_por_normalizado_similar(
                        codigo_normalizado=sku_normalizado,
                        limite=limite_ajustado,
                        solo_activos=solo_activos,
                        longitud_minima=longitud_minima
                    )
                    
                    elapsed_staging = time.time() - start_time_staging
                    
                    # VALIDACIÓN #5: Observabilidad
                    if productos:
                        logger.info(
                            f"✅ Staging: {len(productos)} productos encontrados en {elapsed_staging:.3f}s "
                            f"para '{sku_clean}' (normalizado: '{sku_normalizado}')"
                        )
                        return productos
                    else:
                        logger.debug(
                            f"⚠️ Staging: 0 productos encontrados en {elapsed_staging:.3f}s, "
                            f"usando fallback a SAP"
                        )
                finally:
                    conn.close()
            except Exception as e:
                elapsed_staging = time.time() - start_time_staging
                logger.warning(
                    f"⚠️ Error en staging ({elapsed_staging:.3f}s), usando fallback a SAP: {e}"
                )
                # Continuar con fallback
        
        # FALLBACK: Buscar directamente en SAP (más lento, pero funciona)
        start_time_sap = time.time()
        
        if not self.enabled:
            logger.debug(f"⏭️ Consultas SAP deshabilitadas para: {sku_clean}")
            return []
        
        # Búsqueda mejorada con múltiples condiciones OR para manejar diferentes separadores
        import re
        sku_escaped = sku_clean.replace("'", "''").replace("%", "[%]").replace("_", "[_]")
        
        # Extraer partes para búsqueda más flexible
        prefijo_match = re.match(r'^([A-Za-z]+)', sku_clean)
        prefijo = prefijo_match.group(1) if prefijo_match else None
        numeros = re.findall(r'\d+', sku_clean)
        numero_principal = numeros[0] if numeros else None
        
        # Construir condiciones OR
        condiciones = []
        
        # Condición 1: Búsqueda exacta (código tal cual)
        condiciones.append(f"T0.\"ItemCode\" LIKE ''%{sku_escaped}%''")
        
        # Condición 2: Prefijo + número principal (más flexible)
        if prefijo and numero_principal:
            prefijo_escaped = prefijo.replace("'", "''").replace("%", "[%]").replace("_", "[_]")
            numero_escaped = numero_principal.replace("'", "''").replace("%", "[%]").replace("_", "[_]")
            condiciones.append(
                f"(T0.\"ItemCode\" LIKE ''%{prefijo_escaped}%'' AND T0.\"ItemCode\" LIKE ''%{numero_escaped}%'')"
            )
        
        # Condición 3: Solo número principal (si es largo, 4+ dígitos)
        if numero_principal and len(numero_principal) >= 4:
            numero_escaped = numero_principal.replace("'", "''").replace("%", "[%]").replace("_", "[_]")
            condiciones.append(f"T0.\"ItemCode\" LIKE ''%{numero_escaped}%''")
        
        where_clause = " OR ".join(f"({cond})" for cond in condiciones)
        if solo_activos:
            where_clause = f"({where_clause}) AND T0.\"validFor\" = ''Y''"
        
        # VALIDACIÓN #4: Pedir más resultados antes del scoring
        limite_busqueda = limite_ajustado * 3
        
        query = f"""
        SELECT 
            T0."ItemCode",
            T0."ItemName",
            T0."U_IXX_PACK",
            T0."ItmsGrpNam",
            T0."validFor",
            T0."ItmsGrpCod"
        FROM OPENQUERY([{SAP_LINKED_SERVER}], '
            SELECT 
                T0."ItemCode",
                T0."ItemName",
                T0."U_IXX_PACK",
                T1."ItmsGrpNam",
                T0."validFor",
                T0."ItmsGrpCod"
            FROM "{SAP_DATABASE}"."OITM" T0
            LEFT JOIN "{SAP_DATABASE}"."OITB" T1 ON T0."ItmsGrpCod" = T1."ItmsGrpCod"
            WHERE {where_clause}
            ORDER BY T0."ItemCode"
            LIMIT {limite_busqueda}
        ') T0
        ORDER BY T0."ItemCode";
        """
        
        conn = None
        try:
            logger.info(
                f"🔍 SAP directo: Buscando SKUs similares a '{sku_clean}' "
                f"(normalizado: '{sku_normalizado}', límite: {limite_busqueda})"
            )
            conn = get_sap_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            productos = []
            for row in results:
                productos.append({
                    "ItemCode": row[0] if row[0] else None,
                    "ItemName": row[1] if row[1] else None,
                    "U_IXX_PACK": row[2] if row[2] else None,
                    "ItmsGrpNam": row[3] if row[3] else None,
                    "validFor": row[4] if row[4] else "N",
                    "ItmsGrpCod": row[5] if row[5] else None,
                })
            
            elapsed_sap = time.time() - start_time_sap
            
            # VALIDACIÓN #5: Observabilidad
            logger.info(
                f"{'✅' if productos else '⚠️'} SAP directo: {len(productos)} productos encontrados "
                f"en {elapsed_sap:.3f}s para '{sku_clean}'"
            )
            
            return productos
            
        except pyodbc.Error as e:
            elapsed_sap = time.time() - start_time_sap
            error_msg = f"Error al buscar SKUs similares para '{sku_clean}': {str(e)}"
            logger.error(f"❌ SAP directo ({elapsed_sap:.3f}s): {error_msg}")
            return []
        except Exception as e:
            elapsed_sap = time.time() - start_time_sap
            error_msg = f"Error inesperado al buscar SKUs similares para '{sku_clean}': {str(e)}"
            logger.error(f"❌ SAP directo ({elapsed_sap:.3f}s): {error_msg}", exc_info=True)
            return []
        finally:
            if conn:
                try:
                    cursor.close()
                    conn.close()
                except:
                    pass

