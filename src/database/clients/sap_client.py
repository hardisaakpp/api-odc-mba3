"""
Cliente para consultar información de productos desde SAP (HANA) usando OPENQUERY.

Este cliente ejecuta consultas OPENQUERY desde SQL Server hacia SAP HANA
para obtener información de productos (ItemCode, ItemName, U_IXX_PACK, ItmsGrpNam).
"""

import logging
import re
import pyodbc
from typing import Optional, Dict, Any, List

from src.config import (
    SAP_LINKED_SERVER,
    SAP_DATABASE,
    ENABLE_SAP_QUERIES
)
from ..connection import get_sap_db_connection

logger = logging.getLogger(__name__)


class SAPClient:
    """Cliente para consultar información de productos desde SAP."""
    
    # Patrón permitido para ItemCode: alfanumérico, guiones, puntos, espacios, barra, guion bajo
    # SAP puede usar códigos como R463.1012.GR/AZ; longitud máxima 50 caracteres
    ITEM_CODE_PATTERN = re.compile(r'^[A-Za-z0-9.\-_/ ]{1,50}$')
    
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
    
    def _build_producto_dict(self, result) -> Dict[str, Any]:
        valid_for = result[4] if len(result) > 4 and result[4] is not None else "N"
        return {
            "ItemCode": result[0] or None,
            "ItemName": result[1] or None,
            "U_IXX_PACK": result[2] or None,
            "ItmsGrpNam": result[3] or None,
            "validFor": str(valid_for).strip().upper() if valid_for else "N",
        }

    @staticmethod
    def _safe_close(conn, cursor) -> None:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

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
        
        # Construir consulta OPENQUERY (incluye validFor para validar ítems activos en carga de plantilla)
        query = f"""
        SELECT 
            T0."ItemCode",
            T0."ItemName",
            T0."U_IXX_PACK",
            T0."ItmsGrpNam",
            T0."validFor"
        FROM OPENQUERY([{SAP_LINKED_SERVER}], '
            SELECT 
                T0."ItemCode",
                T0."ItemName",
                T0."U_IXX_PACK",
                T1."ItmsGrpNam",
                T0."validFor"
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
                producto_info = self._build_producto_dict(result)
                logger.info(f"✅ Producto encontrado en SAP: {item_code_normalized} - Pack: {producto_info.get('U_IXX_PACK')}, Grupo: {producto_info.get('ItmsGrpNam')}, validFor: {producto_info.get('validFor')}")
                return producto_info
            logger.warning(f"⚠️ Producto no encontrado en SAP: {item_code_normalized}")
            return None
                
        except pyodbc.Error as e:
            error_msg = f"Error al consultar SAP para ItemCode {item_code_normalized}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            # No lanzar excepción, retornar None para que el sistema continúe
            return None
        except Exception as e:
            error_msg = f"Error inesperado al consultar SAP para ItemCode {item_code_normalized}: {str(e)}"
            logger.exception(f"❌ {error_msg}")
            return None
        finally:
            if conn:
                SAPClient._safe_close(conn, cursor)

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
    
    def _buscar_skus_en_staging(
        self,
        sku_clean: str,
        sku_normalizado: str,
        limite_ajustado: int,
        solo_activos: bool,
        longitud_minima: int,
    ):
        """Busca SKUs en staging. Retorna lista de productos o None si falla o no hay resultados."""
        import time
        start_time = time.time()
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
                    longitud_minima=longitud_minima,
                )
                elapsed = time.time() - start_time
                if productos:
                    logger.info(
                        f"✅ Staging: {len(productos)} productos encontrados en {elapsed:.3f}s "
                        f"para '{sku_clean}' (normalizado: '{sku_normalizado}')"
                    )
                    return productos
                logger.debug(
                    f"⚠️ Staging: 0 productos encontrados en {elapsed:.3f}s, usando fallback a SAP"
                )
                return None
            finally:
                conn.close()
        except Exception as e:
            elapsed = time.time() - start_time
            logger.warning(f"⚠️ Error en staging ({elapsed:.3f}s), usando fallback a SAP: {e}")
            return None

    def _build_where_clause(
        self,
        sku_escaped: str,
        prefijo: Optional[str],
        numero_principal: Optional[str],
        solo_activos: bool,
    ) -> str:
        """Construye la cláusula WHERE para la búsqueda de SKUs similares en SAP."""
        condiciones = [f"T0.\"ItemCode\" LIKE ''%{sku_escaped}%''"]

        if prefijo and numero_principal:
            p_esc = prefijo.replace("'", "''").replace("%", "[%]").replace("_", "[_]")
            n_esc = numero_principal.replace("'", "''").replace("%", "[%]").replace("_", "[_]")
            condiciones.append(
                f"(T0.\"ItemCode\" LIKE ''%{p_esc}%'' AND T0.\"ItemCode\" LIKE ''%{n_esc}%'')"
            )

        if numero_principal and len(numero_principal) >= 4:
            n_esc = numero_principal.replace("'", "''").replace("%", "[%]").replace("_", "[_]")
            condiciones.append(f"T0.\"ItemCode\" LIKE ''%{n_esc}%''")

        where_clause = " OR ".join(f"({cond})" for cond in condiciones)

        if solo_activos:
            where_clause = f"({where_clause}) AND T0.\"validFor\" = ''Y''"

        return where_clause

    def _buscar_skus_en_sap(
        self,
        sku_clean: str,
        sku_normalizado: str,
        limite_ajustado: int,
        solo_activos: bool,
    ) -> List[Dict[str, Any]]:
        """Busca SKUs similares directamente en SAP vía OPENQUERY (fallback)."""
        import time

        if not self.enabled:
            logger.debug(f"⏭️ Consultas SAP deshabilitadas para: {sku_clean}")
            return []

        start_time_sap = time.time()
        sku_escaped = sku_clean.replace("'", "''").replace("%", "[%]").replace("_", "[_]")

        prefijo_match = re.match(r'^([A-Za-z]+)', sku_clean)
        prefijo = prefijo_match.group(1) if prefijo_match else None
        numeros = re.findall(r'\d+', sku_clean)
        numero_principal = numeros[0] if numeros else None

        where_clause = self._build_where_clause(sku_escaped, prefijo, numero_principal, solo_activos)

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

            productos = [
                {
                    "ItemCode": row[0] or None,
                    "ItemName": row[1] or None,
                    "U_IXX_PACK": row[2] or None,
                    "ItmsGrpNam": row[3] or None,
                    "validFor": row[4] or "N",
                    "ItmsGrpCod": row[5] or None,
                }
                for row in results
            ]

            elapsed_sap = time.time() - start_time_sap
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
            logger.exception(f"❌ SAP directo ({elapsed_sap:.3f}s): {error_msg}")
            return []
        finally:
            if conn:
                SAPClient._safe_close(conn, cursor)

    def buscar_skus_similares(
        self,
        sku_referencia: str,
        limite: int = 20,
        solo_activos: bool = True,
        usar_staging: bool = True,
        longitud_minima: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Busca SKUs similares usando staging (preferido) o OPENQUERY SAP (fallback).

        VALIDACIONES: #1 normalización  #2 SKU corto  #3 duplicados por scoring
                      #4 límite 3x      #5 observabilidad staging vs SAP
        """
        from src.utils import normalizar_codigo_producto, validar_longitud_minima_codigo

        if not sku_referencia or not sku_referencia.strip():
            return []

        sku_clean = sku_referencia.strip()
        if len(sku_clean) > 50:
            logger.warning(f"⚠️ SKU de referencia demasiado largo: {len(sku_clean)} caracteres")
            return []

        sku_normalizado = normalizar_codigo_producto(sku_clean)
        if not sku_normalizado:
            logger.warning(f"⚠️ SKU '{sku_clean}' se normalizó a string vacío")
            return []

        if not validar_longitud_minima_codigo(sku_normalizado, longitud_minima):
            logger.warning(
                f"⚠️ SKU normalizado muy corto ({len(sku_normalizado)} < {longitud_minima}): "
                f"'{sku_normalizado}' (original: '{sku_clean}'). "
                f"La búsqueda puede devolver muchos resultados."
            )
            limite_ajustado = min(limite, 10)
        else:
            limite_ajustado = limite

        if usar_staging:
            resultado = self._buscar_skus_en_staging(
                sku_clean, sku_normalizado, limite_ajustado, solo_activos, longitud_minima
            )
            if resultado is not None:
                return resultado

        return self._buscar_skus_en_sap(sku_clean, sku_normalizado, limite_ajustado, solo_activos)

    def get_bodega_info(self, whs_code: str) -> Optional[Dict[str, Any]]:
        """
        Consulta información de una bodega desde SAP usando OPENQUERY.
        
        Args:
            whs_code: Código de bodega (WhsCode) a consultar
            
        Returns:
            Diccionario con información de la bodega:
            {
                "WhsCode": "RL-CD",
                "WhsName": "BODEGA ROLAND CD"
            }
            O None si no se encuentra o hay error
            
        Raises:
            Exception: Si hay error de conexión o consulta
        """
        if not self.enabled:
            logger.debug(f"⏭️ Consulta SAP deshabilitada para WhsCode: {whs_code}")
            return None
        
        # Validar formato del whs_code antes de procesarlo
        if not whs_code or not whs_code.strip():
            logger.warning("⚠️ WhsCode vacío")
            return None
        
        # Normalizar whs_code (quitar espacios)
        whs_code_normalized = whs_code.strip()
        
        # Escapar comillas simples
        whs_code_escaped = whs_code_normalized.replace("'", "''")
        
        query = f"""
        SELECT 
            T0."WhsCode" AS "WhsCode",
            T0."WhsName" AS "WhsName"
        FROM OPENQUERY([{SAP_LINKED_SERVER}], '
            SELECT 
                "WhsCode",
                "WhsName"
            FROM "{SAP_DATABASE}"."OWHS"
            WHERE "WhsCode" = ''{whs_code_escaped}''
        ') T0;
        """
        
        conn = None
        try:
            logger.info(f"🔍 SAP: Consultando bodega WhsCode='{whs_code_normalized}'")
            conn = get_sap_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(query)
            row = cursor.fetchone()
            
            if row:
                bodega_info = {
                    "WhsCode": row[0] if row[0] else None,
                    "WhsName": row[1] if row[1] else None
                }
                logger.info(f"✅ SAP: Bodega '{whs_code_normalized}' encontrada: {bodega_info['WhsName']}")
                return bodega_info
            else:
                logger.warning(f"⚠️ SAP: Bodega '{whs_code_normalized}' no encontrada en OWHS")
                return None
                
        except pyodbc.Error as e:
            error_msg = f"Error al consultar bodega '{whs_code_normalized}': {str(e)}"
            logger.error(f"❌ SAP: {error_msg}")
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = f"Error inesperado al consultar bodega '{whs_code_normalized}': {str(e)}"
            logger.exception(f"❌ SAP: {error_msg}")
            raise RuntimeError(error_msg) from e
        finally:
            if conn:
                SAPClient._safe_close(conn, cursor)
    
    def get_todas_bodegas(self) -> List[Dict[str, Any]]:
        """
        Obtiene TODAS las bodegas desde SAP tabla OWHS.
        
        Returns:
            Lista de diccionarios con información de bodegas:
            [
                {"WhsCode": "RL-CD", "WhsName": "BODEGA ROLAND CD"},
                {"WhsCode": "TRL-QSN", "WhsName": "ROLAND QUICENTRO NORTE"},
                ...
            ]
            O lista vacía si hay error
        """
        if not self.enabled:
            logger.debug("⏭️ Consulta SAP deshabilitada para obtener todas las bodegas")
            return []
        
        query = f"""
        SELECT 
            T0."WhsCode" AS "WhsCode",
            T0."WhsName" AS "WhsName"
        FROM OPENQUERY([{SAP_LINKED_SERVER}], '
            SELECT 
                "WhsCode",
                "WhsName"
            FROM "{SAP_DATABASE}"."OWHS"
            ORDER BY "WhsCode"
        ') T0;
        """
        
        conn = None
        try:
            logger.info("🔍 SAP: Consultando TODAS las bodegas desde OWHS")
            conn = get_sap_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            bodegas = []
            for row in rows:
                bodegas.append({
                    "WhsCode": row[0] if row[0] else None,
                    "WhsName": row[1] if row[1] else None
                })
            
            logger.info(f"✅ SAP: {len(bodegas)} bodegas encontradas en OWHS")
            return bodegas
                
        except pyodbc.Error as e:
            error_msg = f"Error al consultar todas las bodegas: {str(e)}"
            logger.error(f"❌ SAP: {error_msg}")
            return []
        except Exception as e:
            error_msg = f"Error inesperado al consultar todas las bodegas: {str(e)}"
            logger.exception(f"❌ SAP: {error_msg}")
            return []
        finally:
            if conn:
                SAPClient._safe_close(conn, cursor)

