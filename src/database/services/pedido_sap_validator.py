"""
Validaciones específicas contra SAP para pedidos.
Extraído de pedido_validator.py para mejorar separación de responsabilidades.
"""

import logging
import re
import asyncio
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class PedidoSAPValidator:
    """
    Validador especializado para validaciones contra SAP.
    
    Valida:
    - Productos en SAP (ItemCode exacto)
    - Tiendas/Bodegas en SAP OWHS
    """
    
    def __init__(self):
        """Inicializa el validador SAP."""
        pass
    
    def validar_productos_existen_en_sap(
        self,
        codigos_productos: List[str],
        usar_cache: bool = True,
        sap_obligatorio: bool = True
    ) -> Dict[str, Any]:
        """
        Valida que los códigos de producto existan directamente en SAP.
        
        REGLAS DE VALIDACIÓN:
        - ItemCode debe coincidir EXACTO con el código del Excel
        - Si SAP no responde y sap_obligatorio=True → ERROR
        - Si SAP no responde y sap_obligatorio=False → WARNING
        - Código no encontrado → ERROR (siempre)
        
        Args:
            codigos_productos: Lista de códigos de productos a validar (deben ser únicos)
            usar_cache: Si True, usa SAPService que tiene cache. Si False, consulta directamente SAPClient
            sap_obligatorio: Si True, errores de SAP bloquean. Si False, solo WARNING
            
        Returns:
            {
                "validos": List[str],  # Códigos que existen en SAP con ItemCode exacto
                "no_encontrados": List[str],  # Códigos que NO existen en SAP
                "errores": List[str],  # Códigos con error al consultar SAP
                "warnings": List[str],  # Códigos con warnings (SAP no respondió pero no es obligatorio)
                "todos_validos": bool,
                "detalle": Dict[str, Dict[str, Any]]  # {codigo: {"existe": bool, "info": {...}, "error": str, "severity": str}}
            }
        """
        from ..services.sap_service import SAPService
        from src.config import ENABLE_SAP_QUERIES
        
        if not codigos_productos:
            return {
                "validos": [],
                "no_encontrados": [],
                "errores": [],
                "warnings": [],
                "todos_validos": True,
                "detalle": {}
            }
        
        # Verificar si SAP está habilitado
        resultado_deshabilitado = self._handle_sap_disabled(codigos_productos, sap_obligatorio, "productos")
        if resultado_deshabilitado:
            return resultado_deshabilitado
        
        detalle = {}
        validos = []
        no_encontrados = []
        errores = []
        warnings = []
        
        # Usar SAPService que tiene cache
        sap_service = SAPService()
        
        for codigo in codigos_productos:
            try:
                # Normalizar código (quitar espacios)
                codigo_clean = codigo.strip() if codigo else ""
                
                if not codigo_clean:
                    detalle[codigo] = {
                        "existe": False,
                        "info": None,
                        "error": "Código vacío",
                        "severity": "ERROR"
                    }
                    no_encontrados.append(codigo)
                    continue
                
                # Consultar SAP (usa cache si está disponible)
                producto_info = sap_service.get_or_fetch_producto_info(codigo_clean)
                
                # Procesar resultado
                resultado_codigo = self._procesar_resultado_producto(
                    codigo, codigo_clean, producto_info, sap_obligatorio
                )
                
                detalle[codigo] = resultado_codigo["detalle"]
                if resultado_codigo["tipo"] == "valido":
                    validos.append(codigo)
                elif resultado_codigo["tipo"] == "no_encontrado":
                    no_encontrados.append(codigo)
                elif resultado_codigo["tipo"] == "error":
                    errores.append(codigo)
                elif resultado_codigo["tipo"] == "warning":
                    warnings.append(codigo)
                    
            except Exception as e:
                logger.error(f"❌ Error inesperado al validar código {codigo} en SAP: {e}", exc_info=True)
                severity = "ERROR" if sap_obligatorio else "WARNING"
                detalle[codigo] = {
                    "existe": False,
                    "info": None,
                    "error": str(e),
                    "severity": severity
                }
                if sap_obligatorio:
                    errores.append(codigo)
                else:
                    warnings.append(codigo)
        
        todos_validos = len(no_encontrados) == 0 and len(errores) == 0
        
        logger.info(
            f"📊 Validación SAP productos: {len(validos)} válidos, "
            f"{len(no_encontrados)} no encontrados, {len(errores)} errores, {len(warnings)} warnings"
        )
        
        return {
            "validos": validos,
            "no_encontrados": no_encontrados,
            "errores": errores,
            "warnings": warnings,
            "todos_validos": todos_validos,
            "detalle": detalle
        }
    
    def validar_productos_existen_en_sap_con_sugerencias(
        self,
        codigos_productos: List[str],
        usar_cache: bool = True,
        sap_obligatorio: bool = True,
        incluir_sugerencias: bool = True,
        limite_sugerencias: int = 20
    ) -> Dict[str, Any]:
        """
        Valida que los códigos de producto existan en SAP, y si no se encuentran,
        busca en MBA3 y genera sugerencias similares en SAP.
        
        Similar a la funcionalidad de "Buscar SKU" en homologaciones:
        - Busca exacto en SAP (validación estricta)
        - Si no encuentra en SAP, busca en MBA3
        - Genera sugerencias similares en SAP usando normalización flexible
        
        REGLAS DE VALIDACIÓN:
        - ItemCode debe coincidir EXACTO con el código del Excel para ser válido
        - Si no encuentra en SAP, busca en MBA3 y genera sugerencias
        - Las sugerencias usan normalización flexible (sin espacios, guiones, puntos)
        - Si SAP no responde y sap_obligatorio=True → ERROR
        - Si SAP no responde y sap_obligatorio=False → WARNING
        
        Args:
            codigos_productos: Lista de códigos de productos a validar (deben ser únicos)
            usar_cache: Si True, usa SAPService que tiene cache. Si False, consulta directamente SAPClient
            sap_obligatorio: Si True, errores de SAP bloquean. Si False, solo WARNING
            incluir_sugerencias: Si True, busca sugerencias similares cuando no encuentra exacto
            limite_sugerencias: Límite máximo de sugerencias a retornar por código (default: 20)
            
        Returns:
            {
                "validos": List[str],  # Códigos que existen en SAP con ItemCode exacto
                "no_encontrados": List[str],  # Códigos que NO existen en SAP
                "errores": List[str],  # Códigos con error al consultar SAP
                "warnings": List[str],  # Códigos con warnings (SAP no respondió pero no es obligatorio)
                "todos_validos": bool,
                "detalle": Dict[str, Dict[str, Any]]  # {codigo: {
                    #   "existe": bool,
                    #   "info": {...},
                    #   "error": str,
                    #   "severity": str,
                    #   "mba3": {...},  # Información de MBA3 si existe
                    #   "sugerencias_sap": [...]  # Sugerencias similares en SAP
                    # }}
            }
        """
        from ..services.sap_service import SAPService
        from src.config import ENABLE_SAP_QUERIES
        
        if not codigos_productos:
            return {
                "validos": [],
                "no_encontrados": [],
                "errores": [],
                "warnings": [],
                "todos_validos": True,
                "detalle": {}
            }
        
        # Verificar si SAP está habilitado
        resultado_deshabilitado = self._handle_sap_disabled(codigos_productos, sap_obligatorio, "productos")
        if resultado_deshabilitado:
            return resultado_deshabilitado
        
        detalle = {}
        validos = []
        no_encontrados = []
        errores = []
        warnings = []
        
        # Usar SAPService que tiene cache
        sap_service = SAPService()
        
        for codigo in codigos_productos:
            try:
                # Normalizar código (quitar espacios)
                codigo_clean = codigo.strip() if codigo else ""
                
                if not codigo_clean:
                    detalle[codigo] = {
                        "existe": False,
                        "info": None,
                        "error": "Código vacío",
                        "severity": "ERROR",
                        "mba3": None,
                        "sugerencias_sap": []
                    }
                    no_encontrados.append(codigo)
                    continue
                
                # Consultar SAP (usa cache si está disponible)
                producto_info = sap_service.get_or_fetch_producto_info(codigo_clean)
                
                # Procesar resultado
                resultado_codigo = self._procesar_resultado_producto(
                    codigo, codigo_clean, producto_info, sap_obligatorio
                )
                
                detalle_base = resultado_codigo["detalle"]
                
                # Si el producto es válido en SAP, no buscar sugerencias
                if resultado_codigo["tipo"] == "valido":
                    detalle_base["mba3"] = None
                    detalle_base["sugerencias_sap"] = []
                    detalle[codigo] = detalle_base
                    validos.append(codigo)
                else:
                    # Producto no encontrado en SAP: buscar en MBA3 y generar sugerencias
                    info_mba3 = None
                    sugerencias = []
                    
                    if incluir_sugerencias and ENABLE_SAP_QUERIES:
                        try:
                            # Buscar en MBA3
                            info_mba3 = self._buscar_en_mba3(codigo_clean)
                            
                            # ⭐ SIEMPRE generar sugerencias (incluso si no está en MBA3)
                            # Esto permite encontrar variaciones del código en SAP
                            sugerencias = self._generar_sugerencias_sap(
                                codigo_clean,
                                info_mba3,
                                limite_sugerencias
                            )
                            
                            # Log consolidado solo si hay sugerencias o info MBA3
                            if sugerencias or info_mba3:
                                logger.debug(f"🔍 {codigo_clean}: MBA3={'✓' if info_mba3 else '✗'}, Sugerencias={len(sugerencias)}")
                            
                        except Exception as e:
                            logger.warning(f"⚠️ Error al buscar sugerencias para {codigo_clean}: {e}", exc_info=True)
                            # Continuar sin sugerencias
                    
                    detalle_base["mba3"] = info_mba3
                    detalle_base["sugerencias_sap"] = sugerencias
                    detalle[codigo] = detalle_base
                    
                    if resultado_codigo["tipo"] == "no_encontrado":
                        no_encontrados.append(codigo)
                    elif resultado_codigo["tipo"] == "error":
                        errores.append(codigo)
                    elif resultado_codigo["tipo"] == "warning":
                        warnings.append(codigo)
                    
            except Exception as e:
                logger.error(f"❌ Error inesperado al validar código {codigo} en SAP: {e}", exc_info=True)
                severity = "ERROR" if sap_obligatorio else "WARNING"
                detalle[codigo] = {
                    "existe": False,
                    "info": None,
                    "error": str(e),
                    "severity": severity,
                    "mba3": None,
                    "sugerencias_sap": []
                }
                if sap_obligatorio:
                    errores.append(codigo)
                else:
                    warnings.append(codigo)
        
        todos_validos = len(no_encontrados) == 0 and len(errores) == 0
        
        # Log resumido solo si hay problemas
        if no_encontrados or errores:
            logger.warning(
                f"📊 Validación SAP: {len(validos)}✓, {len(no_encontrados)}✗, {len(errores)} errores"
            )
        else:
            logger.debug(f"📊 Validación SAP: {len(validos)} productos válidos")
        
        return {
            "validos": validos,
            "no_encontrados": no_encontrados,
            "errores": errores,
            "warnings": warnings,
            "todos_validos": todos_validos,
            "detalle": detalle
        }
    
    def _buscar_en_mba3(self, codigo: str) -> Optional[Dict[str, Any]]:
        """
        Busca un código de producto en MBA3.
        
        Args:
            codigo: Código del producto a buscar
            
        Returns:
            Diccionario con información del producto en MBA3 o None si no se encuentra
        """
        try:
            from src.services.mba3_service import MBA3Service
            import re
            
            # Validar formato del código
            if not codigo or not codigo.strip():
                return None
            
            codigo_clean = codigo.strip()
            if not re.match(r'^[A-Za-z0-9.\- ]{1,50}$', codigo_clean):
                logger.warning(f"⚠️ Código con formato inválido para MBA3: {codigo_clean}")
                return None
            
            # Escapar comillas simples
            codigo_escaped = codigo_clean.replace("'", "''")
            
            # Consulta a MBA3
            query = (
                "SELECT PRODUCT_ID, PRODUCT_NAME, CORP, GrupoPrenda, Talla, PRESENTACION, "
                "GROUP_CODE, Tipo_Origen, Descontinuado, INACTIVE "
                "FROM INVT_FICHA_PRINCIPAL "
                f"WHERE PRODUCT_ID = '{codigo_escaped}' "
                "LIMIT 1"
            )
            
            mba3_service = MBA3Service()
            result = mba3_service.execute_query(query)
            
            # Normalizar resultado
            if isinstance(result, list):
                productos = result
            elif isinstance(result, dict):
                productos = []
                for key, value in result.items():
                    if isinstance(value, list):
                        productos = value
                        break
                if not productos and result:
                    productos = [result]
            else:
                productos = []
            
            if not productos:
                return None
            
            producto = productos[0]
            
            # Normalizar nombres de campos
            return {
                "codigo": producto.get("PRODUCT_ID") or producto.get("product_id") or producto.get("Product_ID") or codigo_clean,
                "nombre": producto.get("PRODUCT_NAME") or producto.get("product_name") or producto.get("Product_Name") or "",
                "corp": producto.get("CORP") or producto.get("corp") or producto.get("Corp") or "",
                "grupo_prenda": producto.get("GrupoPrenda") or producto.get("grupoPrenda") or producto.get("grupo_prenda") or "",
                "talla": producto.get("Talla") or producto.get("talla") or "",
                "presentacion": producto.get("PRESENTACION") or producto.get("presentacion") or producto.get("Presentacion") or "",
                "group_code": producto.get("GROUP_CODE") or producto.get("group_code") or producto.get("Group_Code") or "",
                "tipo_origen": producto.get("Tipo_Origen") or producto.get("tipo_origen") or producto.get("Tipo_Origen") or "",
                "descontinuado": producto.get("Descontinuado") or producto.get("descontinuado") or False,
                "inactive": producto.get("INACTIVE") or producto.get("inactive") or producto.get("Inactive") or False
            }
            
        except Exception as e:
            logger.warning(f"⚠️ Error al buscar código {codigo} en MBA3: {e}")
            return None
    
    def _generar_sugerencias_sap(
        self,
        codigo: str,
        info_mba3: Optional[Dict[str, Any]],
        limite: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Genera sugerencias similares en SAP para un código de producto.
        
        Args:
            codigo: Código del producto de referencia
            info_mba3: Información del producto en MBA3 (opcional)
            limite: Límite máximo de sugerencias
            
        Returns:
            Lista de sugerencias con scores y motivos
        """
        try:
            from ..clients.sap_client import SAPClient
            from ..services.sugerencias_homologacion_service import SugerenciasHomologacionService
            from src.config import ENABLE_SAP_QUERIES
            
            if not ENABLE_SAP_QUERIES:
                return []
            
            sap_client = SAPClient()
            sugerencias_service = SugerenciasHomologacionService()
            
            # Buscar SKUs similares en SAP
            productos_sap = sap_client.buscar_skus_similares(
                sku_referencia=codigo,
                limite=limite * 2,  # Buscar más para tener mejor selección
                solo_activos=True
            )
            
            if not productos_sap:
                return []
            
            # Preparar producto de referencia (MBA3 o solo código)
            producto_referencia = {
                "codigo_mba3": codigo,
                "nombre_mba3": info_mba3.get("nombre", "") if info_mba3 else "",
            }
            
            # Convertir productos SAP al formato esperado
            productos_sap_formateados = []
            for prod in productos_sap:
                productos_sap_formateados.append({
                    "item_code": prod.get("ItemCode", ""),
                    "item_name": prod.get("ItemName", ""),
                    "pack": prod.get("U_IXX_PACK", ""),
                    "active": prod.get("validFor", "N").upper() == "Y"
                })
            
            # Calcular scores y motivos usando servicio de sugerencias
            sugerencias = sugerencias_service.buscar_sugerencias_para_producto(
                producto_mba3=producto_referencia,
                productos_sap=productos_sap_formateados,
                productos_ya_homologados=set()  # No excluir ningún producto
            )
            
            # Formatear sugerencias con información adicional
            sugerencias_formateadas = []
            productos_sap_dict = {p.get("ItemCode"): p for p in productos_sap}
            
            for sugerencia in sugerencias:
                codigo_sap = sugerencia.get("codigo_sap")
                producto_sap = productos_sap_dict.get(codigo_sap, {})
                
                valid_for = producto_sap.get("validFor", "N")
                estado = "activo" if valid_for.upper() == "Y" else "inactivo"
                
                sugerencias_formateadas.append({
                    "codigo": codigo_sap,
                    "nombre": producto_sap.get("ItemName", ""),
                    "pack": producto_sap.get("U_IXX_PACK", ""),
                    "group_code": producto_sap.get("ItmsGrpCod"),
                    "group_name": producto_sap.get("ItmsGrpNam", ""),
                    "estado": estado,
                    "valid_for": valid_for,
                    "score": sugerencia.get("score", 0.0),
                    "score_porcentaje": round(sugerencia.get("score", 0.0) * 100, 1),
                    "motivos": sugerencia.get("motivos", [])
                })
            
            # Limitar a la cantidad solicitada
            sugerencias_finales = sugerencias_formateadas[:limite]
            
            logger.debug(f"✅ Sugerencias generadas para {codigo}: {len(sugerencias_finales)}/{len(sugerencias_formateadas)}")
            
            return sugerencias_finales
            
        except Exception as e:
            logger.warning(f"⚠️ Error al generar sugerencias SAP para {codigo}: {e}", exc_info=True)
            return []
    
    def validar_bodegas_existen_en_sap(
        self,
        codigos_bodegas: List[str],
        sap_obligatorio: bool = True
    ) -> Dict[str, Any]:
        """
        Valida que los códigos de bodega existan en SAP OWHS.
        Obtiene TODAS las bodegas de SAP y valida contra ese catálogo completo.
        
        Args:
            codigos_bodegas: Lista de códigos de bodegas a validar
            sap_obligatorio: Si True, errores de SAP bloquean
            
        Returns:
            {
                "validas": List[str],  # Códigos que existen en SAP
                "no_encontradas": List[str],  # Códigos que NO existen
                "errores": List[str],  # Códigos con error al consultar
                "warnings": List[str],  # Warnings
                "todas_validas": bool,
                "detalle": Dict[str, Dict[str, Any]]
            }
        """
        from ..clients.sap_client import SAPClient
        from src.config import ENABLE_SAP_QUERIES
        
        if not codigos_bodegas:
            return {
                "validas": [],
                "no_encontradas": [],
                "errores": [],
                "warnings": [],
                "todas_validas": True,
                "detalle": {}
            }
        
        resultado_deshabilitado = self._handle_sap_disabled(codigos_bodegas, sap_obligatorio, "bodegas")
        if resultado_deshabilitado:
            return resultado_deshabilitado
        
        detalle = {}
        validas = []
        no_encontradas = []
        errores = []
        warnings = []
        
        # ⭐ NUEVO: Usar servicio con caché optimizado - solo consulta SAP para códigos nuevos
        from ..services.bodega_sap_service import BodegaSAPService
        bodega_sap_service = BodegaSAPService()
        
        try:
            # Validar códigos: consulta caché primero, SAP solo para los nuevos
            logger.info(f"🔍 Validando {len(codigos_bodegas)} códigos de bodegas (caché primero, SAP solo si es necesario)")
            bodegas_validadas = bodega_sap_service.validate_codigos_bodegas_tiendas(
                codigos=codigos_bodegas,
                force_refresh=False
            )
            
            if not bodegas_validadas:
                logger.error("❌ No se pudo validar códigos de bodegas")
                return self._crear_resultado_error_catalogo(
                    codigos_bodegas, sap_obligatorio, "No se pudo validar códigos"
                )
            
            # Procesar resultados de validación
            for codigo in codigos_bodegas:
                codigo_clean = codigo.strip() if codigo else ""
                
                if not codigo_clean:
                    detalle[codigo] = {
                        "existe": False,
                        "info": None,
                        "error": "Código vacío",
                        "severity": "ERROR"
                    }
                    no_encontradas.append(codigo)
                    continue
                
                # Buscar en los resultados de validación
                resultado_validacion = bodegas_validadas.get(codigo_clean.upper())
                
                if resultado_validacion and resultado_validacion.get("encontrado"):
                    # Código encontrado (en caché o SAP)
                    detalle[codigo] = {
                        "existe": True,
                        "info": {
                            "WhsCode": resultado_validacion["WhsCode"],
                            "WhsName": resultado_validacion.get("WhsName"),
                            "es_bodega": resultado_validacion.get("es_bodega")
                        },
                        "error": None,
                        "severity": None,
                        "fuente": resultado_validacion.get("fuente", "cache")
                    }
                    validas.append(codigo)
                    logger.debug(f"✅ Bodega validada: {codigo_clean} (fuente: {resultado_validacion.get('fuente', 'cache')})")
                else:
                    # Código no encontrado
                    detalle[codigo] = {
                        "existe": False,
                        "info": None,
                        "error": "no_existe",
                        "severity": "ERROR",
                        "mensaje": f"La bodega '{codigo_clean}' no existe en SAP OWHS"
                    }
                    no_encontradas.append(codigo)
                    
        except Exception as e:
            logger.error(f"❌ Error al validar bodegas en SAP: {e}", exc_info=True)
            severity = "ERROR" if sap_obligatorio else "WARNING"
            for codigo in codigos_bodegas:
                detalle[codigo] = {
                    "existe": False,
                    "info": None,
                    "error": str(e),
                    "severity": severity
                }
                if sap_obligatorio:
                    errores.append(codigo)
                else:
                    warnings.append(codigo)
        
        todas_validas = len(no_encontradas) == 0 and len(errores) == 0
        
        logger.info(
            f"📊 Validación bodegas SAP: {len(validas)} válidas, "
            f"{len(no_encontradas)} no encontradas, {len(errores)} errores"
        )
        
        return {
            "validas": validas,
            "no_encontradas": no_encontradas,
            "errores": errores,
            "warnings": warnings,
            "todas_validas": todas_validas,
            "detalle": detalle
        }
    
    def validar_tiendas_existen_en_sap(
        self,
        codigos_tiendas: List[str],
        sap_obligatorio: bool = True
    ) -> Dict[str, Any]:
        """
        Valida que los códigos de tienda existan directamente en SAP OWHS.
        
        NUEVO: Valida ID TIENDA contra SAP sin depender de catálogo Excel.
        Obtiene TODAS las tiendas de SAP y valida contra ese catálogo completo.
        
        Args:
            codigos_tiendas: Lista de códigos de tiendas a validar (ej: ["ROL01", "ROL02"])
            sap_obligatorio: Si True, errores de SAP bloquean
            
        Returns:
            {
                "validas": List[str],  # Códigos que existen en SAP
                "no_encontradas": List[str],  # Códigos que NO existen
                "errores": List[str],  # Códigos con error al consultar
                "warnings": List[str],  # Warnings
                "todas_validas": bool,
                "detalle": Dict[str, Dict[str, Any]]
            }
        """
        from ..clients.sap_client import SAPClient
        from src.config import ENABLE_SAP_QUERIES
        
        if not codigos_tiendas:
            return {
                "validas": [],
                "no_encontradas": [],
                "errores": [],
                "warnings": [],
                "todas_validas": True,
                "detalle": {}
            }
        
        resultado_deshabilitado = self._handle_sap_disabled(codigos_tiendas, sap_obligatorio, "tiendas")
        if resultado_deshabilitado:
            return resultado_deshabilitado
        
        validas = []
        no_encontradas = []
        errores = []
        warnings = []
        detalle = {}
        
        # ⭐ NUEVO: Usar servicio con caché optimizado - solo consulta SAP para códigos nuevos
        from ..services.bodega_sap_service import BodegaSAPService
        bodega_sap_service = BodegaSAPService()
        
        try:
            # Validar códigos: consulta caché primero, SAP solo para los nuevos
            logger.info(f"🔍 Validando {len(codigos_tiendas)} códigos de tiendas (caché primero, SAP solo si es necesario)")
            tiendas_validadas = bodega_sap_service.validate_codigos_bodegas_tiendas(
                codigos=codigos_tiendas,
                force_refresh=False
            )
            
            if tiendas_validadas is None:
                logger.error("❌ No se pudo validar códigos de tiendas")
                return self._crear_resultado_error_catalogo(
                    codigos_tiendas, sap_obligatorio, "No se pudo validar códigos"
                )
            
            # Crear diccionario para búsqueda rápida
            tiendas_sap_dict = {}
            for codigo, resultado in tiendas_validadas.items():
                if resultado.get("encontrado"):
                    tiendas_sap_dict[codigo] = {
                        "WhsCode": resultado["WhsCode"],
                        "WhsName": resultado.get("WhsName"),
                        "es_bodega": resultado.get("es_bodega")
                    }
            
            logger.info(f"📋 Validación completada: {len([t for t in tiendas_validadas.values() if t.get('encontrado')])} tiendas encontradas")
            
            # Procesar resultados de validación
            for codigo in codigos_tiendas:
                codigo_clean = codigo.strip() if codigo else ""
                
                if not codigo_clean:
                    detalle[codigo] = {
                        "existe": False,
                        "info": None,
                        "error": "Código vacío",
                        "severity": "ERROR"
                    }
                    no_encontradas.append(codigo)
                    continue
                
                # Normalizar para búsqueda
                codigo_upper = codigo_clean.upper()
                
                # Buscar en los resultados de validación
                resultado_validacion = tiendas_validadas.get(codigo_upper)
                
                if resultado_validacion and resultado_validacion.get("encontrado"):
                    # Código encontrado (en caché o SAP)
                    tienda_info = {
                        "WhsCode": resultado_validacion["WhsCode"],
                        "WhsName": resultado_validacion.get("WhsName"),
                        "es_bodega": resultado_validacion.get("es_bodega")
                    }
                    detalle[codigo] = {
                        "existe": True,
                        "info": {
                            "codigo": tienda_info.get("WhsCode"),
                            "nombre": tienda_info.get("WhsName"),
                            "es_bodega": tienda_info.get("es_bodega")
                        },
                        "error": None,
                        "severity": None,
                        "fuente": resultado_validacion.get("fuente", "cache")
                    }
                    validas.append(codigo)
                    logger.debug(f"✅ Tienda validada: {codigo_clean} (fuente: {resultado_validacion.get('fuente', 'cache')})")
                else:
                    # Código no encontrado
                    detalle[codigo] = {
                        "existe": False,
                        "info": None,
                        "error": "no_existe",
                        "severity": "ERROR",
                        "mensaje": f"La tienda '{codigo_clean}' no existe en SAP OWHS"
                    }
                    no_encontradas.append(codigo)
                    logger.warning(f"⚠️ Tienda {codigo_clean} no encontrada en SAP")
                    
        except Exception as e:
            logger.error(f"❌ Error al validar tiendas en SAP: {e}", exc_info=True)
            severity = "ERROR" if sap_obligatorio else "WARNING"
            for codigo in codigos_tiendas:
                detalle[codigo] = {
                    "existe": False,
                    "info": None,
                    "error": str(e),
                    "severity": severity
                }
                if sap_obligatorio:
                    errores.append(codigo)
                else:
                    warnings.append(codigo)
        
        todas_validas = len(no_encontradas) == 0 and len(errores) == 0
        
        logger.info(
            f"📊 Validación tiendas SAP: {len(validas)} válidas, "
            f"{len(no_encontradas)} no encontradas, {len(errores)} errores"
        )
        
        return {
            "validas": validas,
            "no_encontradas": no_encontradas,
            "errores": errores,
            "warnings": warnings,
            "todas_validas": todas_validas,
            "detalle": detalle
        }
    
    def _handle_sap_disabled(
        self,
        codigos: List[str],
        sap_obligatorio: bool,
        tipo_entidad: str
    ) -> Dict[str, Any] | None:
        """
        Maneja el caso cuando SAP está deshabilitado.
        
        Args:
            codigos: Lista de códigos a validar
            sap_obligatorio: Si True, errores bloquean
            tipo_entidad: Tipo de entidad ("productos", "bodegas", "tiendas")
            
        Returns:
            Diccionario con resultado si SAP está deshabilitado, None si está habilitado
        """
        from src.config import ENABLE_SAP_QUERIES
        
        if ENABLE_SAP_QUERIES:
            return None
        
        logger.warning(f"⚠️ Consultas SAP deshabilitadas (ENABLE_SAP_QUERIES=False) para {tipo_entidad}")
        
        if sap_obligatorio:
            detalle = {
                codigo: {
                    "existe": False,
                    "info": None,
                    "error": "SAP deshabilitado",
                    "severity": "ERROR"
                }
                for codigo in codigos
            }
            # Para productos: usar "validos", "no_encontrados"
            # Para bodegas/tiendas: usar "validas", "no_encontradas"
            if tipo_entidad == "productos":
                return {
                    "validos": [],
                    "no_encontrados": [],
                    "errores": list(codigos),
                    "warnings": [],
                    "todos_validos": False,
                    "detalle": detalle
                }
            else:
                return {
                    "validas": [],
                    "no_encontradas": [],
                    "errores": list(codigos),
                    "warnings": [],
                    "todas_validas": False,
                    "detalle": detalle
                }
        else:
            detalle = {
                codigo: {
                    "existe": False,
                    "info": None,
                    "error": "SAP deshabilitado",
                    "severity": "WARNING"
                }
                for codigo in codigos
            }
            if tipo_entidad == "productos":
                return {
                    "validos": [],
                    "no_encontrados": [],
                    "errores": [],
                    "warnings": list(codigos),
                    "todos_validos": False,
                    "detalle": detalle
                }
            else:
                return {
                    "validas": [],
                    "no_encontradas": [],
                    "errores": [],
                    "warnings": list(codigos),
                    "todas_validas": False,
                    "detalle": detalle
                }
    
    def _procesar_resultado_producto(
        self,
        codigo: str,
        codigo_clean: str,
        producto_info: Dict[str, Any] | None,
        sap_obligatorio: bool
    ) -> Dict[str, Any]:
        """
        Procesa el resultado de una consulta de producto a SAP.
        
        Args:
            codigo: Código original
            codigo_clean: Código normalizado
            producto_info: Información del producto o None
            sap_obligatorio: Si True, errores bloquean
            
        Returns:
            {
                "tipo": str,  # "valido", "no_encontrado", "error", "warning"
                "detalle": Dict[str, Any]  # Detalle del resultado
            }
        """
        # Verificar si hay error
        if producto_info and producto_info.get("_error"):
            error_type = producto_info.get("_error_type")
            
            if error_type == "no_existe":
                return {
                    "tipo": "no_encontrado",
                    "detalle": {
                        "existe": False,
                        "info": None,
                        "error": "no_existe",
                        "severity": "ERROR",
                        "mensaje": f"El código '{codigo_clean}' no existe en SAP"
                    }
                }
            elif error_type == "mismatch":
                item_code_sap = producto_info.get("_item_code_sap", "N/A")
                return {
                    "tipo": "no_encontrado",
                    "detalle": {
                        "existe": False,
                        "info": None,
                        "error": "mismatch",
                        "severity": "ERROR",
                        "mensaje": f"El código '{codigo_clean}' no coincide exacto con ItemCode SAP '{item_code_sap}'",
                        "item_code_sap": item_code_sap
                    }
                }
            elif error_type == "error":
                error_msg = producto_info.get("_error_message", "Error desconocido")
                severity = "ERROR" if sap_obligatorio else "WARNING"
                tipo = "error" if sap_obligatorio else "warning"
                return {
                    "tipo": tipo,
                    "detalle": {
                        "existe": False,
                        "info": None,
                        "error": error_type,
                        "severity": severity,
                        "mensaje": f"Error al consultar SAP para '{codigo_clean}': {error_msg}"
                    }
                }
            else:
                severity = "ERROR" if sap_obligatorio else "WARNING"
                tipo = "error" if sap_obligatorio else "warning"
                return {
                    "tipo": tipo,
                    "detalle": {
                        "existe": False,
                        "info": None,
                        "error": error_type or "error_desconocido",
                        "severity": severity
                    }
                }
        elif producto_info:
            # ✅ Producto encontrado correctamente
            return {
                "tipo": "valido",
                "detalle": {
                    "existe": True,
                    "info": {
                        "item_code": producto_info.get("item_code"),
                        "item_name": producto_info.get("item_name"),
                        "pack_sap": producto_info.get("pack_sap"),
                        "grupo_articulos": producto_info.get("grupo_articulos"),
                        "unidad_conversion": producto_info.get("unidad_conversion")
                    },
                    "severity": None
                }
            }
        else:
            # None retornado sin error
            return {
                "tipo": "no_encontrado",
                "detalle": {
                    "existe": False,
                    "info": None,
                    "error": "no_existe",
                    "severity": "ERROR",
                    "mensaje": f"No se encontró información en SAP para '{codigo_clean}'"
                }
            }
    
    def _crear_resultado_error_catalogo(
        self,
        codigos: List[str],
        sap_obligatorio: bool,
        mensaje_error: str
    ) -> Dict[str, Any]:
        """
        Crea un resultado de error cuando no se puede obtener el catálogo SAP.
        
        Args:
            codigos: Lista de códigos
            sap_obligatorio: Si True, errores bloquean
            mensaje_error: Mensaje de error
            
        Returns:
            Diccionario con resultado de error
        """
        detalle = {
            codigo: {
                "existe": False,
                "info": None,
                "error": mensaje_error,
                "severity": "ERROR"
            }
            for codigo in codigos
        }
        return {
            "validas": [],
            "no_encontradas": [],
            "errores": list(codigos),
            "warnings": [],
            "todas_validas": False,
            "detalle": detalle
        }
