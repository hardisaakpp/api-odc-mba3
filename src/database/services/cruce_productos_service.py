"""
Servicio para realizar cruce de productos entre MBA3 y SAP.
Identifica productos homologados, homologables y no encontrados.
"""

import logging
from typing import List, Dict, Any, Tuple, Optional, Callable

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
        Normaliza un código de producto (wrapper para compatibilidad).
        
        IMPORTANTE: Ahora usa función centralizada que incluye TODOS los separadores:
        ., -, /, _, espacio
        
        DEPRECATED: Usar normalizar_codigo_producto de src.utils directamente.
        Este wrapper se mantiene por compatibilidad con código existente.
        
        Args:
            codigo: Código a normalizar
            
        Returns:
            Código normalizado
        """
        from src.utils import normalizar_codigo_producto
        return normalizar_codigo_producto(codigo)
    
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
                    productos_sin_normalizado = 0
                    for producto in productos:
                        product_id_normalizado = producto.get("product_id_normalizado")
                        
                        # Validación: asegurar que siempre haya código normalizado
                        if not product_id_normalizado:
                            productos_sin_normalizado += 1
                            logger.warning(f"⚠️ Producto MBA3 {producto['product_id']} sin product_id_normalizado en staging, normalizando en tiempo real")
                            product_id_normalizado = self.normalizar_codigo(producto["product_id"])
                        
                        productos_normalizados.append({
                            "product_id": producto["product_id"],
                            "product_name": producto["product_name"],
                            "corp": producto["corp"],
                            "grupo_prenda": producto["grupo_prenda"],
                            "talla": producto["talla"],
                            "presentacion": producto["presentacion"],
                            "product_id_normalizado": product_id_normalizado
                        })
                    
                    if productos_sin_normalizado > 0:
                        logger.warning(f"⚠️ {productos_sin_normalizado} productos MBA3 sin product_id_normalizado en staging. Considera re-sincronizar.")
                    
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
    
    @staticmethod
    def _get_field(producto: dict, *keys):
        for key in keys:
            val = producto.get(key)
            if val:
                return val
        return None

    @staticmethod
    def _extraer_productos_raw(result) -> list:
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for value in result.values():
                if isinstance(value, list):
                    return value
            if result:
                return [result]
        return []

    def _normalizar_producto_api(self, producto: dict) -> Optional[dict]:
        product_id = self._get_field(producto, "PRODUCT_ID", "product_id", "Product_ID")
        if not product_id:
            return None
        product_name = self._get_field(producto, "PRODUCT_NAME", "product_name", "Product_Name")
        corp = self._get_field(producto, "CORP", "corp", "Corp")
        grupo_prenda = self._get_field(producto, "GrupoPrenda", "grupoPrenda", "grupo_prenda")
        talla = self._get_field(producto, "Talla", "talla")
        presentacion = self._get_field(producto, "PRESENTACION", "presentacion", "Presentacion")
        descontinuado = self._get_field(producto, "Descontinuado", "descontinuado")
        group_code = self._get_field(producto, "GROUP_CODE", "group_code", "Group_Code")
        inactive = self._get_field(producto, "INACTIVE", "inactive", "Inactive")
        tipo_origen = self._get_field(producto, "Tipo_Origen", "tipo_origen")
        return {
            "product_id": str(product_id).strip(),
            "product_name": str(product_name).strip() if product_name else "Sin nombre",
            "corp": str(corp).strip() if corp else "",
            "grupo_prenda": str(grupo_prenda).strip() if grupo_prenda else "",
            "talla": str(talla).strip() if talla else "",
            "presentacion": str(presentacion).strip() if presentacion else "",
            "descontinuado": str(descontinuado).strip() if descontinuado else "",
            "group_code": str(group_code).strip() if group_code else "",
            "inactive": str(inactive).strip() if inactive else "",
            "tipo_origen": str(tipo_origen).strip() if tipo_origen else "",
            "product_id_normalizado": self.normalizar_codigo(product_id),
        }

    def _obtener_productos_mba3_directo(self) -> List[Dict[str, Any]]:
        """
        Obtiene productos MBA3 directamente desde API (método interno).

        Returns:
            Lista de productos con código y nombre
        """
        try:
            # Query actualizada con campos adicionales y filtros mejorados
            # Calcular fecha límite (últimos 365 días) - formato YYYY-MM-DD para 4D
            # COMENTADO: Filtro de fechas deshabilitado
            # fecha_limite = datetime.now() - timedelta(days=365)
            # fecha_limite_str = fecha_limite.strftime("%Y-%m-%d")

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
                "Tipo_Origen, "
                "SELL, "
                "CODE_PROV_O_ALT, "
                "CATEGORY, "
                "Familia, "
                "Codigo_Marca, "
                "PRODUCT_NAME_2, "
                "Fecha_Ultima_Venta, "
                "FechaUltimoMovimiento "
                "FROM INVT_FICHA_PRINCIPAL "
                "WHERE PRODUCT_ID IS NOT NULL "
                "AND Descontinuado = 'false' "
                "AND GROUP_CODE = 'PTERM' "
                "AND INACTIVE = 'false' "
                "AND Tipo_Origen != 'ESPEC' "
                "AND Tipo_Origen != 'EXPOR' "
                "AND Tipo_Origen != 'MAPRO' "
                "AND GrupoPrenda IS NOT NULL "
                "AND PRODUCT_NAME IS NOT NULL "
                "AND SELL > 0 "
                # COMENTADO: Filtro de fechas deshabilitado
                # f"AND (FechaUltimoMovimiento >= '{fecha_limite_str}' OR Fecha_Ultima_Venta >= '{fecha_limite_str}')"
            )

            logger.info("🔍 Consultando productos desde MBA3 API (directo)...")
            result = self.mba3_service.execute_query(query)

            productos_normalizados = []
            for producto in self._extraer_productos_raw(result):
                normalizado = self._normalizar_producto_api(producto)
                if normalizado:
                    productos_normalizados.append(normalizado)

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
                    productos_sin_normalizado = 0
                    for producto in productos:
                        item_code_normalizado = producto.get("item_code_normalizado")
                        
                        # Validación: asegurar que siempre haya código normalizado
                        if not item_code_normalizado:
                            productos_sin_normalizado += 1
                            logger.warning(f"⚠️ Producto SAP {producto['item_code']} sin item_code_normalizado en staging, normalizando en tiempo real")
                            item_code_normalizado = self.normalizar_codigo(producto["item_code"])
                        
                        productos_normalizados.append({
                            "item_code": producto["item_code"],
                            "item_name": producto["item_name"],
                            "pack": producto["pack"],
                            "group_code": producto["group_code"],
                            "active": producto["active"],
                            "item_code_normalizado": item_code_normalizado
                        })
                    
                    if productos_sin_normalizado > 0:
                        logger.warning(f"⚠️ {productos_sin_normalizado} productos SAP sin item_code_normalizado en staging. Considera re-sincronizar.")
                    
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
    
    @staticmethod
    def _row_get(row, index, default: Optional[str] = ""):
        return row[index] if len(row) > index and row[index] else default

    def _normalizar_row_sap(self, row) -> Optional[dict]:
        item_code = row[0] if row[0] else ""
        if not item_code:
            return None
        item_name = row[1] if row[1] else "Sin nombre"
        pack = row[2] if row[2] else ""
        sal_unit_msr = self._row_get(row, 3)
        code_bars = self._row_get(row, 4)
        itms_grp_nam = self._row_get(row, 5)
        group_code = self._row_get(row, 6, None)
        # SAP devuelve 'Y'/'N' para validFor, no boolean
        valid_for_raw = row[7] if len(row) > 7 else None
        valid_for = str(valid_for_raw).upper() == 'Y' if valid_for_raw is not None else False
        invnt_item_raw = row[8] if len(row) > 8 else None
        invnt_item = str(invnt_item_raw).upper() == 'Y' if invnt_item_raw is not None else False
        return {
            "item_code": str(item_code).strip(),
            "item_name": str(item_name).strip(),
            "pack": str(pack).strip(),
            "sal_unit_msr": str(sal_unit_msr).strip() if sal_unit_msr else "",
            "code_bars": str(code_bars).strip() if code_bars else "",
            "itms_grp_nam": str(itms_grp_nam).strip() if itms_grp_nam else "",
            "group_code": group_code,
            "active": valid_for,
            "invnt_item": invnt_item,
            "item_code_normalizado": self.normalizar_codigo(str(item_code).strip()),
        }

    def _obtener_productos_sap_directo(self) -> List[Dict[str, Any]]:
        """
        Obtiene productos SAP directamente desde OPENQUERY (método interno).

        Returns:
            Lista de productos con código y nombre
        """
        conn = None
        try:
            # Query mejorada: Solo productos activos, vendibles y con ventas recientes (últimos 365 días)
            query = f"""
            SELECT
                T0."ItemCode",
                T0."ItemName",
                T0."U_IXX_PACK",
                T0."SalUnitMsr",
                T0."CodeBars",
                T0."ItmsGrpNam",
                T0."ItmsGrpCod",
                T0."validFor",
                T0."InvntItem"
            FROM OPENQUERY([{SAP_LINKED_SERVER}], '
                SELECT
                    OITM."ItemCode",
                    OITM."ItemName",
                    OITM."U_IXX_PACK",
                    OITM."SalUnitMsr",
                    OITM."CodeBars",
                    OITB."ItmsGrpNam",
                    OITM."ItmsGrpCod",
                    OITM."validFor",
                    OITM."InvntItem"
                FROM "{SAP_DATABASE}"."OITM" OITM
                INNER JOIN "{SAP_DATABASE}"."OITB" OITB
                    ON OITM."ItmsGrpCod" = OITB."ItmsGrpCod"
                WHERE OITM."ItemCode" IS NOT NULL
                  AND OITM."ItemName" IS NOT NULL
                  AND OITM."validFor" = ''Y''
                  AND OITM."SellItem" = ''Y''
                  AND OITB."ItmsGrpNam" IN (''R-MEDIAS'', ''RD-INDUM MEDIAS'')
                  AND EXISTS (
                      SELECT 1
                      FROM "{SAP_DATABASE}"."INV1" INV1
                      INNER JOIN "{SAP_DATABASE}"."OINV" OINV
                          ON INV1."DocEntry" = OINV."DocEntry"
                      WHERE INV1."ItemCode" = OITM."ItemCode"
                        AND OINV."DocDate" >= ADD_DAYS(CURRENT_DATE, -365)
                  )
            ') T0
            ORDER BY T0."ItemCode";
            """

            logger.info("🔍 Consultando productos desde SAP OPENQUERY (directo)...")
            conn = get_sap_db_connection()
            cursor = conn.cursor()

            cursor.execute(query)
            results = cursor.fetchall()

            productos = []
            for row in results:
                producto = self._normalizar_row_sap(row)
                if producto:
                    productos.append(producto)

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
                except Exception:
                    pass

    def _indexar_productos_mba3(self, productos: List[Dict[str, Any]]) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
        """
        Indexa productos MBA3 por código exacto y normalizado.
        
        IMPORTANTE: Usa SIEMPRE product_id_normalizado del staging si está disponible.
        Solo normaliza en tiempo real como fallback de emergencia.
        
        Args:
            productos: Lista de productos MBA3
            
        Returns:
            Tupla con (dict_exacto, dict_normalizado)
        """
        mba3_dict_exacto = {}
        mba3_dict_normalizado = {}
        
        for producto in productos:
            codigo_original = producto["product_id"]
            codigo_normalizado = producto.get("product_id_normalizado")
            
            if not codigo_normalizado:
                # Fallback solo si realmente no existe (no debería pasar si staging está bien)
                logger.warning(f"⚠️ Producto MBA3 {codigo_original} sin product_id_normalizado, normalizando en tiempo real")
                codigo_normalizado = self.normalizar_codigo(codigo_original)
            
            if codigo_original not in mba3_dict_exacto:
                mba3_dict_exacto[codigo_original] = []
            mba3_dict_exacto[codigo_original].append(producto)
            
            if codigo_normalizado not in mba3_dict_normalizado:
                mba3_dict_normalizado[codigo_normalizado] = []
            mba3_dict_normalizado[codigo_normalizado].append(producto)
        
        return mba3_dict_exacto, mba3_dict_normalizado
    
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
            # IMPORTANTE: Usar SIEMPRE item_code_normalizado del staging
            codigo_normalizado = producto.get("item_code_normalizado")
            if not codigo_normalizado:
                # Fallback solo si realmente no existe (no debería pasar si staging está bien)
                logger.warning(f"⚠️ Producto SAP {codigo_original} sin item_code_normalizado, normalizando en tiempo real")
                codigo_normalizado = self.normalizar_codigo(codigo_original)
            
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

    def _buscar_sap_match(
        self,
        codigo_mba3_original: str,
        codigo_normalizado: str,
        productos_sap_list: List[Dict[str, Any]],
        sap_procesados: set
    ):
        """
        Busca el primer producto SAP compatible con un producto MBA3 dado.

        Retorna (producto_sap, codigo_sap_normalizado) si hay match, o None si no lo hay.
        """
        for producto_sap in productos_sap_list:
            codigo_sap_original = producto_sap["item_code"]
            if codigo_sap_original in sap_procesados:
                continue
            if codigo_mba3_original == codigo_sap_original:
                continue
            codigo_sap_normalizado = producto_sap.get("item_code_normalizado")
            if not codigo_sap_normalizado:
                logger.warning(f"⚠️ Producto SAP {codigo_sap_original} sin item_code_normalizado en homologables")
                codigo_sap_normalizado = self.normalizar_codigo(codigo_sap_original)
            if codigo_normalizado != codigo_sap_normalizado:
                logger.warning(
                    f"⚠️ Inconsistencia: MBA3 normalizado={codigo_normalizado}, "
                    f"SAP normalizado={codigo_sap_normalizado} para códigos {codigo_mba3_original}/{codigo_sap_original}"
                )
                continue
            return producto_sap, codigo_sap_normalizado
        return None

    def _cruzar_homologables(
        self,
        mba3_dict_normalizado: Dict[str, List[Dict[str, Any]]],
        sap_dict_normalizado: Dict[str, List[Dict[str, Any]]],
        productos_mba3_procesados: set,
        productos_sap_procesados: set
    ) -> Tuple[List[Dict[str, Any]], set, set]:
        """
        Cruza productos con coincidencia normalizada pero códigos diferentes.

        REGLAS DE CLASIFICACIÓN (DETERMINISTAS):
        - Un producto MBA3 puede tener solo UN match en SAP (primero encontrado)
        - Un producto SAP puede tener solo UN match en MBA3 (primero encontrado)
        - Esto evita duplicados pero puede ocultar matches alternativos legítimos
        - Si hay varios MBA3 que normalizan igual a un SAP, solo el primero se marca
        - Si hay varios SAP que normalizan igual a un MBA3, solo el primero se marca

        IMPORTANTE: Usa SIEMPRE campos *_normalizado del staging para consistencia.

        Args:
            mba3_dict_normalizado: Diccionario indexado de productos MBA3 por código normalizado
            sap_dict_normalizado: Diccionario indexado de productos SAP por código normalizado
            productos_mba3_procesados: Set de códigos MBA3 ya procesados (exactos)
            productos_sap_procesados: Set de códigos SAP ya procesados (exactos)

        Returns:
            Tupla con (lista_homologables, set_mba3_procesados_actualizado, set_sap_procesados_actualizado)
        """
        homologables = []
        mba3_procesados = productos_mba3_procesados.copy()
        sap_procesados = productos_sap_procesados.copy()

        for codigo_normalizado, productos_mba3_list in mba3_dict_normalizado.items():
            if codigo_normalizado not in sap_dict_normalizado:
                continue
            productos_sap_list = sap_dict_normalizado[codigo_normalizado]
            for producto_mba3 in productos_mba3_list:
                codigo_mba3_original = producto_mba3["product_id"]
                if codigo_mba3_original in mba3_procesados:
                    continue
                match = self._buscar_sap_match(
                    codigo_mba3_original, codigo_normalizado, productos_sap_list, sap_procesados
                )
                if match:
                    producto_sap, codigo_sap_normalizado = match
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
                    mba3_procesados.add(codigo_mba3_original)
                    sap_procesados.add(producto_sap["item_code"])
                    break

        return homologables, mba3_procesados, sap_procesados
    
    def _obtener_solo_en_mba3(
        self,
        productos_mba3: List[Dict[str, Any]],
        productos_procesados: set,
        sap_dict_normalizado: Dict[str, List[Dict[str, Any]]],
        sap_dict_exacto: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        Obtiene productos que solo están en MBA3 (sin match en SAP).
        
        IMPORTANTE: Valida explícitamente que el código NO exista en SAP
        (ni por código exacto ni por código normalizado) para maximizar las coincidencias
        y evitar que productos que existen en SAP aparezcan incorrectamente en esta lista.
        
        Args:
            productos_mba3: Lista completa de productos MBA3
            productos_procesados: Set de códigos MBA3 ya procesados (que tienen match en SAP)
            sap_dict_normalizado: Diccionario indexado de productos SAP por código normalizado
            sap_dict_exacto: Diccionario indexado de productos SAP por código exacto
            
        Returns:
            Lista de productos solo en MBA3 (validados para no existir en SAP)
        """
        solo_en_mba3 = []
        productos_omitidos = 0
        
        for producto in productos_mba3:
            codigo = producto["product_id"]
            
            # Validación: no incluir si ya fue procesado (tiene match en SAP)
            if codigo in productos_procesados:
                continue
            
            # CORRECCIÓN CRÍTICA 1: Validar que el código exacto NO exista en SAP
            if codigo in sap_dict_exacto:
                productos_omitidos += 1
                logger.warning(
                    f"⚠️ Producto MBA3 {codigo} existe en SAP (código exacto). "
                    f"Omitiendo de solo_en_mba3. Esto indica un problema en la lógica de cruce."
                )
                continue
            
            # CORRECCIÓN CRÍTICA 2: Validar que el código normalizado NO exista en SAP
            # Esto asegura maximizar las coincidencias y evitar productos SAP en esta lista
            codigo_normalizado = producto.get("product_id_normalizado")
            if not codigo_normalizado:
                # Si no tiene normalizado, normalizar ahora
                codigo_normalizado = self.normalizar_codigo(codigo)
            
            # Si existe en SAP (por código normalizado), no incluir en solo_en_mba3
            # Esto puede pasar si:
            # 1. Hay un bug en la lógica de procesamiento anterior
            # 2. Hay múltiples productos MBA3 con el mismo código normalizado y solo uno se procesó
            # 3. Todos los productos SAP con ese código normalizado ya fueron procesados pero el MBA3 no
            if codigo_normalizado in sap_dict_normalizado:
                productos_omitidos += 1
                logger.warning(
                    f"⚠️ Producto MBA3 {codigo} (normalizado: {codigo_normalizado}) "
                    f"existe en SAP pero no fue marcado como procesado. Omitiendo de solo_en_mba3."
                )
                continue
            
            solo_en_mba3.append({
                "codigo_mba3": producto["product_id"],
                "nombre_mba3": producto["product_name"],
                "corp": producto.get("corp", ""),
                "grupo_prenda": producto.get("grupo_prenda", ""),
                "talla": producto.get("talla", ""),
                "presentacion": producto.get("presentacion", ""),
                "tipo_coincidencia": "solo_mba3"
            })
        
        if productos_omitidos > 0:
            logger.warning(
                f"⚠️ {productos_omitidos} productos MBA3 fueron omitidos de solo_en_mba3 "
                f"porque existen en SAP (código exacto o normalizado coincidente). "
                f"Esto puede indicar un problema en la lógica de cruce o datos contaminados."
            )
        
        return solo_en_mba3
    
    def _obtener_solo_en_sap(
        self,
        productos_sap: List[Dict[str, Any]],
        productos_procesados: set,
        mba3_dict_normalizado: Dict[str, List[Dict[str, Any]]],
        mba3_dict_exacto: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        Obtiene productos que solo están en SAP (sin match en MBA3).
        
        IMPORTANTE: Valida explícitamente que el código NO exista en MBA3
        (ni por código exacto ni por código normalizado) para evitar que
        productos que existen en MBA3 aparezcan incorrectamente en esta lista.
        
        Args:
            productos_sap: Lista completa de productos SAP
            productos_procesados: Set de códigos SAP ya procesados (que tienen match en MBA3)
            mba3_dict_normalizado: Diccionario indexado de productos MBA3 por código normalizado
            mba3_dict_exacto: Diccionario indexado de productos MBA3 por código exacto
            
        Returns:
            Lista de productos solo en SAP (validados para no existir en MBA3)
        """
        solo_en_sap = []
        productos_omitidos = 0
        
        for producto in productos_sap:
            codigo = producto["item_code"]
            
            # Validación 1: no incluir si ya fue procesado (tiene match en MBA3)
            if codigo in productos_procesados:
                continue
            
            # CORRECCIÓN CRÍTICA 1: Validar que el código exacto NO exista en MBA3
            if codigo in mba3_dict_exacto:
                productos_omitidos += 1
                logger.warning(
                    f"⚠️ Producto SAP {codigo} existe en MBA3 (código exacto). "
                    f"Omitiendo de solo_en_sap. Esto indica un problema en la lógica de cruce."
                )
                continue
            
            # CORRECCIÓN CRÍTICA 2: Validar que el código normalizado NO exista en MBA3
            # Esto asegura maximizar las coincidencias y evitar productos MBA3 en esta lista
            codigo_normalizado = producto.get("item_code_normalizado")
            if not codigo_normalizado:
                # Si no tiene normalizado, normalizar ahora
                codigo_normalizado = self.normalizar_codigo(codigo)
            
            # Si existe en MBA3 (por código normalizado), no incluir en solo_en_sap
            # Esto puede pasar si:
            # 1. Hay un bug en la lógica de procesamiento anterior
            # 2. Hay múltiples productos SAP con el mismo código normalizado y solo uno se procesó
            # 3. Todos los productos MBA3 con ese código normalizado ya fueron procesados pero el SAP no
            if codigo_normalizado in mba3_dict_normalizado:
                productos_omitidos += 1
                logger.warning(
                    f"⚠️ Producto SAP {codigo} (normalizado: {codigo_normalizado}) "
                    f"existe en MBA3 pero no fue marcado como procesado. Omitiendo de solo_en_sap."
                )
                continue
            
            solo_en_sap.append({
                "codigo_sap": producto["item_code"],
                "nombre_sap": producto["item_name"],
                "pack_sap": producto.get("pack", ""),
                "group_code": producto.get("group_code"),
                "active": producto.get("active", True),
                "tipo_coincidencia": "solo_sap"
            })
        
        if productos_omitidos > 0:
            logger.warning(
                f"⚠️ {productos_omitidos} productos SAP fueron omitidos de solo_en_sap "
                f"porque existen en MBA3 (código exacto o normalizado coincidente). "
                f"Esto puede indicar un problema en la lógica de cruce o datos contaminados."
            )
        
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

    @staticmethod
    def _indexar_por_codigo(productos: list, campo: str) -> dict:
        resultado = {}
        for p in productos:
            codigo = p[campo]
            if codigo not in resultado:
                resultado[codigo] = []
            resultado[codigo].append(p)
        return resultado

    def _indexar_por_codigo_normalizado(self, productos: list, campo: str, campo_normalizado: str) -> dict:
        resultado = {}
        for p in productos:
            codigo = p.get(campo_normalizado) or self.normalizar_codigo(p[campo])
            if codigo not in resultado:
                resultado[codigo] = []
            resultado[codigo].append(p)
        return resultado

    def realizar_cruce(
        self,
        progress_callback: Optional[Callable[[str, int, str, Optional[dict]], None]] = None
    ) -> Dict[str, Any]:
        """
        Realiza el cruce completo entre productos de MBA3 y SAP.
        
        OPTIMIZACIÓN: Primero compara exactos (sin normalizar), luego normaliza solo
        los productos sin match exacto para buscar coincidencias normalizadas.
        
        Args:
            progress_callback: Función opcional callback(step, progress, message, data=None)
                              para reportar progreso del proceso.
                              - step: Paso actual del proceso
                              - progress: Porcentaje de progreso (0-100)
                              - message: Mensaje descriptivo
                              - data: Datos adicionales opcionales
        
        REGLAS DE CLASIFICACIÓN (DETERMINISTAS):
        
        1. EXACTOS (homologados_exactos):
           - product_id == item_code (códigos originales idénticos)
           - Un producto EXACTO no puede estar en otra categoría
        
        2. HOMOLOGABLES:
           - product_id_normalizado == item_code_normalizado
           - AND product_id != item_code (códigos originales diferentes)
           - Un producto HOMOLOGABLE no puede estar en otra categoría
        
        3. SOLO MBA3 (solo_en_mba3):
           - product_id_normalizado NO existe en ningún item_code_normalizado de SAP
           - Y NO está en exactos ni homologables
        
        4. SOLO SAP (solo_en_sap):
           - item_code_normalizado NO existe en ningún product_id_normalizado de MBA3
           - Y NO está en exactos ni homologables
        
        VALIDACIÓN:
        - Un producto solo puede aparecer en UNA categoría
        - Si aparece en múltiples → BUG (revisar normalización)
        
        FLUJO OPTIMIZADO:
        1. Comparación exacta PRODUCT_ID === ItemCode (sin normalizar)
        2. Clasificación y agrupación de exactos
        3. Normalización solo de productos sin match exacto
        4. Búsqueda de coincidencias normalizadas
        
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
        def _reportar_progreso(step: str, progress: int, message: str, data: Optional[dict] = None):
            """Helper para reportar progreso."""
            if progress_callback:
                progress_callback(step, progress, message, data)
            logger.info(f"📊 [{step}] {progress}% - {message}")
        
        _reportar_progreso("iniciando", 0, "Iniciando cruce de productos...")
        logger.info("🔍 Iniciando cruce de productos MBA3 vs SAP...")
        
        # Obtener productos de ambas fuentes
        _reportar_progreso("obteniendo_mba3", 10, "Obteniendo productos MBA3...")
        productos_mba3 = self.obtener_productos_mba3()
        _reportar_progreso("obteniendo_mba3", 15, f"Obtenidos {len(productos_mba3)} productos MBA3",
                          data={"total_mba3": len(productos_mba3)})
        
        _reportar_progreso("obteniendo_sap", 20, "Obteniendo productos SAP...")
        productos_sap = self.obtener_productos_sap()
        _reportar_progreso("obteniendo_sap", 25, f"Obtenidos {len(productos_sap)} productos SAP",
                          data={"total_sap": len(productos_sap)})
        
        # Validación: asegurar que hay datos para procesar
        if not productos_mba3 and not productos_sap:
            raise RuntimeError(
                "No hay datos para procesar. Las tablas de staging están vacías. "
                "Ejecuta primero POST /cruce-productos/sincronizar-maestros"
            )
        
        if not productos_mba3:
            logger.warning("⚠️ No se obtuvieron productos de MBA3 - la tabla de staging está vacía")
        if not productos_sap:
            logger.warning("⚠️ No se obtuvieron productos de SAP - la tabla de staging está vacía")
        
        # PASO 1: Indexar SOLO por código exacto (sin normalizar aún)
        # Esto es más eficiente: solo normalizamos productos que no tienen match exacto
        _reportar_progreso("indexando", 30, "Indexando productos por código exacto...")
        logger.info("📊 Indexando productos por código exacto (sin normalizar)...")
        mba3_dict_exacto = self._indexar_por_codigo(productos_mba3, "product_id")
        sap_dict_exacto = self._indexar_por_codigo(productos_sap, "item_code")
        
        # PASO 2: Cruzar productos EXACTOS primero (PRODUCT_ID === ItemCode)
        _reportar_progreso("exactos", 40, "Buscando coincidencias exactas (PRODUCT_ID === ItemCode)...")
        logger.info("🔍 Buscando coincidencias exactas (PRODUCT_ID === ItemCode)...")
        homologados_exactos, mba3_procesados, sap_procesados = self._cruzar_exactos(
            mba3_dict_exacto, sap_dict_exacto
        )
        
        _reportar_progreso("exactos", 50, f"Encontrados {len(homologados_exactos)} productos con coincidencia exacta",
                          data={"exactos_count": len(homologados_exactos)})
        logger.info(f"✅ Encontrados {len(homologados_exactos)} productos con coincidencia exacta")
        
        # PASO 3: Filtrar productos que NO tienen match exacto
        # Solo estos productos necesitan normalización
        _reportar_progreso("filtrando", 55, "Filtrando productos sin match exacto...")
        productos_mba3_sin_match = [
            p for p in productos_mba3 
            if p["product_id"] not in mba3_procesados
        ]
        productos_sap_sin_match = [
            p for p in productos_sap 
            if p["item_code"] not in sap_procesados
        ]
        
        _reportar_progreso("filtrando", 60, 
                          f"Productos sin match exacto: {len(productos_mba3_sin_match)} MBA3, {len(productos_sap_sin_match)} SAP",
                          data={"sin_match_mba3": len(productos_mba3_sin_match), "sin_match_sap": len(productos_sap_sin_match)})
        logger.info(
            f"📦 Productos sin match exacto: "
            f"{len(productos_mba3_sin_match)} MBA3, "
            f"{len(productos_sap_sin_match)} SAP"
        )
        
        # PASO 4: Normalizar SOLO los productos sin match exacto
        _reportar_progreso("normalizando", 65, "Normalizando códigos de productos sin match exacto...")
        logger.info("🔄 Normalizando códigos de productos sin match exacto...")
        mba3_dict_normalizado = self._indexar_por_codigo_normalizado(
            productos_mba3_sin_match, "product_id", "product_id_normalizado"
        )
        sap_dict_normalizado = self._indexar_por_codigo_normalizado(
            productos_sap_sin_match, "item_code", "item_code_normalizado"
        )
        _reportar_progreso("normalizando", 70, "Normalización completada")
        
        # PASO 5: Cruzar productos HOMOLOGABLES (normalizados)
        _reportar_progreso("homologables", 75, "Buscando coincidencias normalizadas (homologables)...")
        logger.info("🔍 Buscando coincidencias normalizadas (homologables)...")
        homologables, mba3_procesados, sap_procesados = self._cruzar_homologables(
            mba3_dict_normalizado,
            sap_dict_normalizado,
            mba3_procesados,
            sap_procesados
        )
        
        _reportar_progreso("homologables", 80, f"Encontrados {len(homologables)} productos homologables",
                          data={"homologables_count": len(homologables)})
        logger.info(f"✅ Encontrados {len(homologables)} productos homologables")
        
        # PASO 6: Obtener productos sin match (ni exacto ni normalizado)
        _reportar_progreso("sin_match", 85, "Identificando productos sin match...")
        logger.info("🔍 Identificando productos sin match...")
        solo_en_mba3 = self._obtener_solo_en_mba3(
            productos_mba3, 
            mba3_procesados, 
            sap_dict_normalizado,
            sap_dict_exacto
        )
        solo_en_sap = self._obtener_solo_en_sap(
            productos_sap, 
            sap_procesados,
            mba3_dict_normalizado,
            mba3_dict_exacto
        )
        
        _reportar_progreso("sin_match", 90, f"Productos sin match: {len(solo_en_mba3)} solo MBA3, {len(solo_en_sap)} solo SAP",
                          data={"solo_mba3_count": len(solo_en_mba3), "solo_sap_count": len(solo_en_sap)})
        
        # Calcular estadísticas
        _reportar_progreso("estadisticas", 95, "Calculando estadísticas finales...")
        estadisticas = self._calcular_estadisticas(
            len(productos_mba3),
            len(productos_sap),
            homologados_exactos,
            homologables,
            solo_en_mba3,
            solo_en_sap
        )
        
        resultado = {
            "homologados_exactos": homologados_exactos,
            "homologables": homologables,
            "solo_en_mba3": solo_en_mba3,
            "solo_en_sap": solo_en_sap,
            "estadisticas": estadisticas
        }
        
        _reportar_progreso("completado", 100, "Cruce completado exitosamente",
                          data={"estadisticas": estadisticas})
        logger.info(
            f"✅ Cruce completado: "
            f"{estadisticas['homologados_exactos']} exactas, "
            f"{estadisticas['homologables']} homologables, "
            f"{estadisticas['solo_en_mba3']} solo MBA3, "
            f"{estadisticas['solo_en_sap']} solo SAP"
        )
        
        return resultado

