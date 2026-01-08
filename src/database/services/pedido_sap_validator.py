"""
Validaciones específicas contra SAP para pedidos.
Extraído de pedido_validator.py para mejorar separación de responsabilidades.
"""

import logging
from typing import Dict, Any, List

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
        
        sap_client = SAPClient()
        
        try:
            # Obtener TODAS las bodegas de SAP de una sola vez
            logger.info("🔍 Obteniendo catálogo completo de bodegas desde SAP OWHS")
            todas_bodegas_sap = sap_client.get_todas_bodegas()
            
            if not todas_bodegas_sap:
                logger.error("❌ No se pudo obtener el catálogo de bodegas desde SAP")
                return self._crear_resultado_error_catalogo(
                    codigos_bodegas, sap_obligatorio, "No se pudo obtener catálogo SAP"
                )
            
            # Crear diccionario de bodegas SAP para búsqueda rápida
            bodegas_sap_dict = {
                bodega["WhsCode"]: bodega 
                for bodega in todas_bodegas_sap 
                if bodega.get("WhsCode")
            }
            
            logger.info(f"📋 Catálogo SAP: {len(bodegas_sap_dict)} bodegas disponibles")
            
            # Validar cada código contra el catálogo
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
                
                # Buscar en el catálogo SAP
                if codigo_clean in bodegas_sap_dict:
                    bodega_info = bodegas_sap_dict[codigo_clean]
                    detalle[codigo] = {
                        "existe": True,
                        "info": bodega_info,
                        "error": None,
                        "severity": None
                    }
                    validas.append(codigo)
                    logger.debug(f"✅ Bodega validada en SAP: {codigo_clean}")
                else:
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
        
        sap_client = SAPClient()
        
        try:
            # Obtener TODAS las tiendas de SAP de una sola vez
            logger.info("🔍 Obteniendo catálogo completo de tiendas desde SAP OWHS")
            todas_tiendas_sap = sap_client.get_todas_bodegas()
            
            if not todas_tiendas_sap:
                logger.error("❌ No se pudo obtener el catálogo de tiendas desde SAP")
                return self._crear_resultado_error_catalogo(
                    codigos_tiendas, sap_obligatorio, "No se pudo obtener catálogo SAP"
                )
            
            # Crear diccionario de tiendas SAP para búsqueda rápida por código
            # SAP usa WhsCode (ej: "ROL01", "ROL02") como clave
            tiendas_sap_dict = {}
            for tienda in todas_tiendas_sap:
                whscode = tienda.get("WhsCode")
                if whscode:
                    # Normalizar: SAP usa mayúsculas
                    tiendas_sap_dict[whscode.upper()] = tienda
            
            logger.info(f"📋 Catálogo SAP: {len(tiendas_sap_dict)} tiendas disponibles")
            
            # Validar cada código contra el catálogo
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
                
                # Buscar en el catálogo SAP
                if codigo_upper in tiendas_sap_dict:
                    tienda_info = tiendas_sap_dict[codigo_upper]
                    detalle[codigo] = {
                        "existe": True,
                        "info": {
                            "codigo": tienda_info.get("WhsCode"),
                            "nombre": tienda_info.get("WhsName"),
                            "ubicacion": tienda_info.get("Location"),
                            "activa": tienda_info.get("Inactive", "N") != "Y"
                        },
                        "error": None,
                        "severity": None
                    }
                    validas.append(codigo)
                    logger.debug(f"✅ Tienda validada en SAP: {codigo_clean}")
                else:
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
