"""
Servicio para realizar cruce de productos entre MBA3 y SAP.
Identifica productos homologados, homologables y no encontrados.
"""

import logging
import re
from typing import List, Dict, Any, Tuple, Optional

from src.services.mba3_service import MBA3Service
from ..connection import get_sap_db_connection, get_db_connection
from src.config import SAP_LINKED_SERVER, SAP_DATABASE, USE_PRODUCT_STAGING, ALLOW_ERP_FALLBACK, ENVIRONMENT
from ..repositories.producto_mba3_staging_repository import ProductoMBA3StagingRepository
from ..repositories.producto_sap_staging_repository import ProductoSAPStagingRepository

logger = logging.getLogger(__name__)


class CruceProductosService:
    """Servicio para cruzar productos entre MBA3 y SAP."""
    
    def __init__(self, use_staging: Optional[bool] = None):
        """
        Inicializa el servicio.
        
        Args:
            use_staging: Si True, lee de staging. Si False, consulta directo.
                        Si None, usa configuración USE_PRODUCT_STAGING.
        """
        self.mba3_service = MBA3Service()
        self.use_staging = use_staging if use_staging is not None else USE_PRODUCT_STAGING
        self.allow_fallback = ALLOW_ERP_FALLBACK and ENVIRONMENT != 'production'
    
    def normalizar_codigo(self, codigo: str) -> str:
        """
        Normaliza un código de producto para comparación.
        
        Elimina puntos y espacios, convierte a mayúsculas.
        Ejemplo: "8040.10" -> "804010", "8040.1" -> "80401"
        
        Args:
            codigo: Código a normalizar
            
        Returns:
            Código normalizado
        """
        if not codigo:
            return ""
        # Eliminar puntos y espacios, convertir a mayúsculas
        return re.sub(r'[.\s]', '', codigo.strip().upper())
    
    def obtener_productos_mba3(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los productos desde staging o API MBA3 (fallback controlado).
        
        Returns:
            Lista de productos con código y nombre
        """
        if self.use_staging:
            try:
                logger.info("📦 Leyendo productos MBA3 desde staging...")
                conn = get_db_connection()
                try:
                    mba3_staging_repo = ProductoMBA3StagingRepository(conn)
                    productos = mba3_staging_repo.get_all_active()
                    
                    # Convertir formato de staging a formato esperado por el cruce
                    productos_normalizados = []
                    for producto in productos:
                        productos_normalizados.append({
                            "product_id": producto["product_id"],
                            "product_name": producto["product_name"],
                            "corp": producto["corp"],
                            "grupo_prenda": producto["grupo_prenda"],
                            "talla": producto["talla"],
                            "presentacion": producto["presentacion"],
                            "product_id_normalizado": producto.get("product_id_normalizado")  # Usar normalizado del staging
                        })
                    
                    logger.info(f"✅ Obtenidos {len(productos_normalizados)} productos desde staging MBA3")
                    return productos_normalizados
                finally:
                    conn.close()
            except Exception as e:
                logger.error(f"❌ Error leyendo staging MBA3: {e}", exc_info=True)
                
                # CORRECCIÓN: Fallback solo si está permitido
                if self.allow_fallback:
                    logger.warning("⚠️ Fallback a API MBA3 (solo permitido en DEV)")
                    return self._obtener_productos_mba3_directo()
                else:
                    raise RuntimeError(
                        "Staging MBA3 no disponible y fallback a ERP deshabilitado. "
                        "Ejecuta sincronización manual primero."
                    )
        else:
            return self._obtener_productos_mba3_directo()
    
    def _obtener_productos_mba3_directo(self) -> List[Dict[str, Any]]:
        """
        Obtiene productos MBA3 directamente desde API (método interno).
        
        Returns:
            Lista de productos con código y nombre
        """
        try:
            # Query según lo definido con ChatGPT
            query = (
                "SELECT "
                "PRODUCT_NAME, "
                "PRODUCT_ID, "
                "GrupoPrenda, "
                "CORP, "
                "Talla, "
                "PRESENTACION, "
                "Descontinuado, "
                "GROUP_CODE, "
                "INACTIVE, "
                "Tipo_Origen "
                "FROM INVT_FICHA_PRINCIPAL "
                "WHERE PRODUCT_ID IS NOT NULL "
                "AND Descontinuado = 'false' "
                "AND GROUP_CODE = 'PTERM' "
                "AND INACTIVE = 'false' "
                "AND Tipo_Origen != 'ESPEC' "
                "AND Tipo_Origen != 'EXPOR' "
                "AND Tipo_Origen != 'MAPRO'"
            )
            
            logger.info("🔍 Consultando productos desde MBA3 API (directo)...")
            result = self.mba3_service.execute_query(query)
            
            # El resultado puede ser una lista o un dict con una clave que contiene la lista
            productos = []
            if isinstance(result, list):
                productos = result
            elif isinstance(result, dict):
                # Buscar la clave que contiene la lista de resultados
                for key, value in result.items():
                    if isinstance(value, list):
                        productos = value
                        break
                # Si no hay lista, intentar usar el dict completo como un solo registro
                if not productos and result:
                    productos = [result]
            
            # Normalizar estructura de datos
            productos_normalizados = []
            for producto in productos:
                # Manejar diferentes formatos de respuesta del API
                product_id = producto.get("PRODUCT_ID") or producto.get("product_id") or producto.get("Product_ID")
                product_name = producto.get("PRODUCT_NAME") or producto.get("product_name") or producto.get("Product_Name")
                corp = producto.get("CORP") or producto.get("corp") or producto.get("Corp")
                grupo_prenda = producto.get("GrupoPrenda") or producto.get("grupoPrenda") or producto.get("grupo_prenda")
                talla = producto.get("Talla") or producto.get("talla")
                presentacion = producto.get("PRESENTACION") or producto.get("presentacion") or producto.get("Presentacion")
                descontinuado = producto.get("Descontinuado") or producto.get("descontinuado")
                group_code = producto.get("GROUP_CODE") or producto.get("group_code") or producto.get("Group_Code")
                inactive = producto.get("INACTIVE") or producto.get("inactive") or producto.get("Inactive")
                tipo_origen = producto.get("Tipo_Origen") or producto.get("tipo_origen") or producto.get("Tipo_Origen")
                
                if product_id:  # Solo incluir si tiene código
                    productos_normalizados.append({
                        "product_id": str(product_id).strip(),
                        "product_name": str(product_name).strip() if product_name else "Sin nombre",
                        "corp": str(corp).strip() if corp else "",
                        "grupo_prenda": str(grupo_prenda).strip() if grupo_prenda else "",
                        "talla": str(talla).strip() if talla else "",
                        "presentacion": str(presentacion).strip() if presentacion else "",
                        "descontinuado": str(descontinuado).strip() if descontinuado else "",
                        "group_code": str(group_code).strip() if group_code else "",
                        "inactive": str(inactive).strip() if inactive else "",
                        "tipo_origen": str(tipo_origen).strip() if tipo_origen else ""
                    })
            
            logger.info(f"✅ Obtenidos {len(productos_normalizados)} productos desde MBA3 API")
            return productos_normalizados
            
        except Exception as e:
            logger.error(f"❌ Error al obtener productos de MBA3: {e}", exc_info=True)
            return []
    
    def obtener_productos_sap(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los productos desde staging o OPENQUERY SAP (fallback controlado).
        
        Returns:
            Lista de productos con código y nombre
        """
        if self.use_staging:
            try:
                logger.info("📦 Leyendo productos SAP desde staging...")
                conn = get_db_connection()
                try:
                    sap_staging_repo = ProductoSAPStagingRepository(conn)
                    productos = sap_staging_repo.get_all_active()
                    
                    # Convertir formato de staging a formato esperado por el cruce
                    productos_normalizados = []
                    for producto in productos:
                        productos_normalizados.append({
                            "item_code": producto["item_code"],
                            "item_name": producto["item_name"],
                            "pack": producto["pack"],
                            "group_code": producto["group_code"],
                            "active": producto["active"],
                            "item_code_normalizado": producto.get("item_code_normalizado")  # Usar normalizado del staging
                        })
                    
                    logger.info(f"✅ Obtenidos {len(productos_normalizados)} productos desde staging SAP")
                    return productos_normalizados
                finally:
                    conn.close()
            except Exception as e:
                logger.error(f"❌ Error leyendo staging SAP: {e}", exc_info=True)
                
                # CORRECCIÓN: Fallback solo si está permitido
                if self.allow_fallback:
                    logger.warning("⚠️ Fallback a OPENQUERY SAP (solo permitido en DEV)")
                    return self._obtener_productos_sap_directo()
                else:
                    raise RuntimeError(
                        "Staging SAP no disponible y fallback a ERP deshabilitado. "
                        "Ejecuta sincronización manual primero."
                    )
        else:
            return self._obtener_productos_sap_directo()
    
    def _obtener_productos_sap_directo(self) -> List[Dict[str, Any]]:
        """
        Obtiene productos SAP directamente desde OPENQUERY (método interno).
        
        Returns:
            Lista de productos con código y nombre
        """
        conn = None
        try:
            # Query según lo definido con ChatGPT
            query = f"""
            SELECT 
                T0."ItemCode",
                T0."ItemName",
                T0."U_IXX_PACK",
                T0."ItmsGrpCod",
                T0."validFor"
            FROM OPENQUERY([{SAP_LINKED_SERVER}], '
                SELECT 
                    OITM."ItemCode",
                    OITM."ItemName",
                    OITM."U_IXX_PACK",
                    OITM."ItmsGrpCod",
                    OITM."validFor"
                FROM "{SAP_DATABASE}"."OITM" OITM
                INNER JOIN "{SAP_DATABASE}"."OITB" OITB 
                    ON OITM."ItmsGrpCod" = OITB."ItmsGrpCod"
                WHERE OITM."ItemCode" IS NOT NULL
                  AND OITB."ItmsGrpNam" IN (''R-MEDIAS'', ''RD-INDUM MEDIAS'')
            ') T0;
            """
            
            logger.info("🔍 Consultando productos desde SAP OPENQUERY (directo)...")
            conn = get_sap_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            productos = []
            for row in results:
                item_code = row[0] if row[0] else ""
                item_name = row[1] if row[1] else "Sin nombre"
                pack = row[2] if row[2] else ""
                group_code = row[3] if row[3] else None
                # SAP devuelve 'Y'/'N' para validFor, no boolean
                valid_for_raw = row[4] if row[4] is not None else 'N'
                valid_for = True if str(valid_for_raw).upper() == 'Y' else False
                
                if item_code:  # Solo incluir si tiene código
                    productos.append({
                        "item_code": str(item_code).strip(),
                        "item_name": str(item_name).strip(),
                        "pack": str(pack).strip(),
                        "group_code": group_code,
                        "active": valid_for
                    })
            
            logger.info(f"✅ Obtenidos {len(productos)} productos desde SAP OPENQUERY")
            return productos
            
        except Exception as e:
            logger.error(f"❌ Error al obtener productos de SAP: {e}", exc_info=True)
            return []
        finally:
            if conn:
                try:
                    cursor.close()
                    conn.close()
                except:
                    pass
    
    def _indexar_productos_mba3(self, productos: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Indexa productos MBA3 por código exacto.
        
        Args:
            productos: Lista de productos MBA3
            
        Returns:
            Diccionario con código como clave y lista de productos como valor
        """
        mba3_dict = {}
        for producto in productos:
            codigo_original = producto["product_id"]
            if codigo_original not in mba3_dict:
                mba3_dict[codigo_original] = []
            mba3_dict[codigo_original].append(producto)
        return mba3_dict
    
    def _indexar_productos_sap(self, productos: List[Dict[str, Any]]) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
        """
        Indexa productos SAP por código exacto y normalizado.
        
        Si el producto viene de staging y tiene item_code_normalizado, lo usa.
        Si no, normaliza en tiempo real (fallback).
        
        Args:
            productos: Lista de productos SAP
            
        Returns:
            Tupla con (dict_exacto, dict_normalizado)
        """
        sap_dict_exacto = {}
        sap_dict_normalizado = {}
        
        for producto in productos:
            codigo_original = producto["item_code"]
            # Usar normalizado del staging si está disponible, sino normalizar
            codigo_normalizado = producto.get("item_code_normalizado") or self.normalizar_codigo(codigo_original)
            
            if codigo_original not in sap_dict_exacto:
                sap_dict_exacto[codigo_original] = []
            sap_dict_exacto[codigo_original].append(producto)
            
            if codigo_normalizado not in sap_dict_normalizado:
                sap_dict_normalizado[codigo_normalizado] = []
            sap_dict_normalizado[codigo_normalizado].append(producto)
        
        return sap_dict_exacto, sap_dict_normalizado
    
    def _cruzar_exactos(
        self,
        mba3_dict: Dict[str, List[Dict[str, Any]]],
        sap_dict: Dict[str, List[Dict[str, Any]]]
    ) -> Tuple[List[Dict[str, Any]], set, set]:
        """
        Cruza productos con coincidencia exacta (PRODUCT_ID === ItemCode).
        
        Args:
            mba3_dict: Diccionario indexado de productos MBA3
            sap_dict: Diccionario indexado de productos SAP
            
        Returns:
            Tupla con (lista_homologados_exactos, set_mba3_procesados, set_sap_procesados)
        """
        homologados_exactos = []
        productos_mba3_procesados = set()
        productos_sap_procesados = set()
        
        for codigo_mba3, productos_mba3_list in mba3_dict.items():
            if codigo_mba3 in sap_dict:
                productos_sap_list = sap_dict[codigo_mba3]
                # Crear todas las combinaciones
                for producto_mba3 in productos_mba3_list:
                    for producto_sap in productos_sap_list:
                        homologados_exactos.append({
                            "codigo_mba3": producto_mba3["product_id"],
                            "nombre_mba3": producto_mba3["product_name"],
                            "corp": producto_mba3.get("corp", ""),
                            "grupo_prenda": producto_mba3.get("grupo_prenda", ""),
                            "talla": producto_mba3.get("talla", ""),
                            "presentacion": producto_mba3.get("presentacion", ""),
                            "codigo_sap": producto_sap["item_code"],
                            "nombre_sap": producto_sap["item_name"],
                            "pack_sap": producto_sap.get("pack", ""),
                            "tipo_coincidencia": "exacta"
                        })
                        productos_mba3_procesados.add(codigo_mba3)
                        productos_sap_procesados.add(producto_sap["item_code"])
        
        return homologados_exactos, productos_mba3_procesados, productos_sap_procesados
    
    def _cruzar_homologables(
        self,
        mba3_dict: Dict[str, List[Dict[str, Any]]],
        sap_dict_normalizado: Dict[str, List[Dict[str, Any]]],
        productos_mba3_procesados: set,
        productos_sap_procesados: set
    ) -> Tuple[List[Dict[str, Any]], set, set]:
        """
        Cruza productos con coincidencia normalizada pero códigos diferentes.
        
        REGLA DE NEGOCIO:
        - Un producto MBA3 puede tener solo UN match en SAP (primero encontrado)
        - Un producto SAP puede tener solo UN match en MBA3 (primero encontrado)
        - Esto evita duplicados pero puede ocultar matches alternativos legítimos
        - Si hay varios MBA3 que normalizan igual a un SAP, solo el primero se marca
        - Si hay varios SAP que normalizan igual a un MBA3, solo el primero se marca
        
        Args:
            mba3_dict: Diccionario indexado de productos MBA3
            sap_dict_normalizado: Diccionario indexado de productos SAP por código normalizado
            productos_mba3_procesados: Set de códigos MBA3 ya procesados
            productos_sap_procesados: Set de códigos SAP ya procesados
            
        Returns:
            Tupla con (lista_homologables, set_mba3_procesados_actualizado, set_sap_procesados_actualizado)
        """
        homologables = []
        mba3_procesados = productos_mba3_procesados.copy()
        sap_procesados = productos_sap_procesados.copy()
        
        for codigo_mba3, productos_mba3_list in mba3_dict.items():
            if codigo_mba3 in mba3_procesados:
                continue  # Ya procesado como exacto
            
            # Usar normalizado del staging si está disponible, sino normalizar
            producto_mba3 = productos_mba3_list[0]  # Tomar el primero para obtener normalizado
            codigo_normalizado = producto_mba3.get("product_id_normalizado") or self.normalizar_codigo(codigo_mba3)
            
            if codigo_normalizado in sap_dict_normalizado:
                productos_sap_list = sap_dict_normalizado[codigo_normalizado]
                
                # Verificar que los códigos originales sean diferentes
                for producto_sap in productos_sap_list:
                    if producto_sap["item_code"] not in sap_procesados:
                        if codigo_mba3 != producto_sap["item_code"]:  # Diferentes originales
                            for producto_mba3 in productos_mba3_list:
                                # Usar normalizado del staging si está disponible
                                codigo_sap_normalizado = producto_sap.get("item_code_normalizado") or self.normalizar_codigo(producto_sap["item_code"])
                                
                                homologables.append({
                                    "codigo_mba3": producto_mba3["product_id"],
                                    "nombre_mba3": producto_mba3["product_name"],
                                    "corp": producto_mba3.get("corp", ""),
                                    "grupo_prenda": producto_mba3.get("grupo_prenda", ""),
                                    "talla": producto_mba3.get("talla", ""),
                                    "presentacion": producto_mba3.get("presentacion", ""),
                                    "codigo_sap": producto_sap["item_code"],
                                    "nombre_sap": producto_sap["item_name"],
                                    "pack_sap": producto_sap.get("pack", ""),
                                    "codigo_mba3_normalizado": codigo_normalizado,
                                    "codigo_sap_normalizado": codigo_sap_normalizado,
                                    "tipo_coincidencia": "homologable"
                                })
                                mba3_procesados.add(codigo_mba3)
                                sap_procesados.add(producto_sap["item_code"])
                                break  # Solo un match por producto SAP
                            break  # Solo un match por código MBA3
        
        return homologables, mba3_procesados, sap_procesados
    
    def _obtener_solo_en_mba3(
        self,
        productos_mba3: List[Dict[str, Any]],
        productos_procesados: set
    ) -> List[Dict[str, Any]]:
        """
        Obtiene productos que solo están en MBA3 (sin match en SAP).
        
        Args:
            productos_mba3: Lista completa de productos MBA3
            productos_procesados: Set de códigos MBA3 ya procesados
            
        Returns:
            Lista de productos solo en MBA3
        """
        solo_en_mba3 = []
        for producto in productos_mba3:
            codigo = producto["product_id"]
            if codigo not in productos_procesados:
                solo_en_mba3.append({
                    "codigo_mba3": producto["product_id"],
                    "nombre_mba3": producto["product_name"],
                    "corp": producto.get("corp", ""),
                    "grupo_prenda": producto.get("grupo_prenda", ""),
                    "talla": producto.get("talla", ""),
                    "presentacion": producto.get("presentacion", ""),
                    "tipo_coincidencia": "solo_mba3"
                })
        return solo_en_mba3
    
    def _obtener_solo_en_sap(
        self,
        productos_sap: List[Dict[str, Any]],
        productos_procesados: set
    ) -> List[Dict[str, Any]]:
        """
        Obtiene productos que solo están en SAP (sin match en MBA3).
        
        Args:
            productos_sap: Lista completa de productos SAP
            productos_procesados: Set de códigos SAP ya procesados
            
        Returns:
            Lista de productos solo en SAP
        """
        solo_en_sap = []
        for producto in productos_sap:
            codigo = producto["item_code"]
            if codigo not in productos_procesados:
                solo_en_sap.append({
                    "codigo_sap": producto["item_code"],
                    "nombre_sap": producto["item_name"],
                    "pack_sap": producto.get("pack", ""),
                    "group_code": producto.get("group_code"),
                    "active": producto.get("active", True),
                    "tipo_coincidencia": "solo_sap"
                })
        return solo_en_sap
    
    def _calcular_estadisticas(
        self,
        total_mba3: int,
        total_sap: int,
        homologados_exactos: List[Dict],
        homologables: List[Dict],
        solo_en_mba3: List[Dict],
        solo_en_sap: List[Dict]
    ) -> Dict[str, Any]:
        """
        Calcula estadísticas del cruce.
        
        Args:
            total_mba3: Total de productos en MBA3
            total_sap: Total de productos en SAP
            homologados_exactos: Lista de homologados exactos
            homologables: Lista de homologables
            solo_en_mba3: Lista de productos solo en MBA3
            solo_en_sap: Lista de productos solo en SAP
            
        Returns:
            Diccionario con estadísticas
        """
        total_exactas = len(homologados_exactos)
        total_homologables = len(homologables)
        total_solo_mba3 = len(solo_en_mba3)
        total_solo_sap = len(solo_en_sap)
        
        porcentaje_homologacion = ((total_exactas + total_homologables) * 100.0 / total_mba3) if total_mba3 > 0 else 0.0
        
        return {
            "total_productos_mba3": total_mba3,
            "total_productos_sap": total_sap,
            "homologados_exactos": total_exactas,
            "homologables": total_homologables,
            "solo_en_mba3": total_solo_mba3,
            "solo_en_sap": total_solo_sap,
            "porcentaje_homologacion": round(porcentaje_homologacion, 2)
        }
    
    def realizar_cruce(self) -> Dict[str, Any]:
        """
        Realiza el cruce completo entre productos de MBA3 y SAP.
        
        Clasifica productos en:
        - Homologados exactos: PRODUCT_ID === ItemCode
        - Homologables: normalizar(PRODUCT_ID) === normalizar(ItemCode) pero códigos diferentes
        - Solo en MBA3: productos que no tienen match en SAP
        - Solo en SAP: productos que no tienen match en MBA3
        
        Returns:
            Diccionario con resultados del cruce:
            {
                "homologados_exactos": [...],
                "homologables": [...],
                "solo_en_mba3": [...],
                "solo_en_sap": [...],
                "estadisticas": {...}
            }
        """
        logger.info("🔍 Iniciando cruce de productos MBA3 vs SAP...")
        
        # Obtener productos de ambas fuentes
        productos_mba3 = self.obtener_productos_mba3()
        productos_sap = self.obtener_productos_sap()
        
        if not productos_mba3:
            logger.warning("⚠️ No se obtuvieron productos de MBA3")
        if not productos_sap:
            logger.warning("⚠️ No se obtuvieron productos de SAP")
        
        # Indexar productos para búsqueda rápida
        mba3_dict = self._indexar_productos_mba3(productos_mba3)
        sap_dict_exacto, sap_dict_normalizado = self._indexar_productos_sap(productos_sap)
        
        # Cruzar productos exactos
        homologados_exactos, mba3_procesados, sap_procesados = self._cruzar_exactos(
            mba3_dict, sap_dict_exacto
        )
        
        # Cruzar productos homologables
        homologables, mba3_procesados, sap_procesados = self._cruzar_homologables(
            mba3_dict, sap_dict_normalizado, mba3_procesados, sap_procesados
        )
        
        # Obtener productos sin match
        solo_en_mba3 = self._obtener_solo_en_mba3(productos_mba3, mba3_procesados)
        solo_en_sap = self._obtener_solo_en_sap(productos_sap, sap_procesados)
        
        # Calcular estadísticas
        estadisticas = self._calcular_estadisticas(
            len(productos_mba3),
            len(productos_sap),
            homologados_exactos,
            homologables,
            solo_en_mba3,
            solo_en_sap
        )
        
        logger.info(
            f"✅ Cruce completado: "
            f"{estadisticas['homologados_exactos']} exactas, "
            f"{estadisticas['homologables']} homologables, "
            f"{estadisticas['solo_en_mba3']} solo MBA3, "
            f"{estadisticas['solo_en_sap']} solo SAP"
        )
        
        return {
            "homologados_exactos": homologados_exactos,
            "homologables": homologables,
            "solo_en_mba3": solo_en_mba3,
            "solo_en_sap": solo_en_sap,
            "estadisticas": estadisticas
        }

