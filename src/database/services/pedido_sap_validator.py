"""
Validaciones específicas contra SAP para pedidos.
Extraído de pedido_validator.py para mejorar separación de responsabilidades.
"""

import logging
import socket
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from src.exceptions import MBA3ConnectionError

logger = logging.getLogger(__name__)

# Timeout para consultas MBA3 durante validación de plantilla (evitar bloqueo si MBA3 no está disponible)
MBA3_LOOKUP_TIMEOUT_SECONDS = 10
MBA3_REACHABILITY_TIMEOUT_SECONDS = 1.5


class PedidoSAPValidator:
    """
    Validador especializado para validaciones contra SAP.

    Valida:
    - Productos en SAP (ItemCode exacto)
    - Tiendas/Bodegas en SAP OWHS
    """

    _CODIGO_VACIO = "Código vacío"

    def __init__(self):
        """Inicializa el validador SAP."""
        self._mba3_lookup_disabled = False
        self._mba3_lookup_disable_reason: Optional[str] = None
        self._mba3_reachability_checked = False

    @staticmethod
    def _clasificar_tipo_codigo(
        tipo: str, codigo: str,
        validos: List, no_encontrados: List, errores: List, warnings: List
    ) -> None:
        if tipo == "valido":
            validos.append(codigo)
        elif tipo == "no_encontrado":
            no_encontrados.append(codigo)
        elif tipo == "error":
            errores.append(codigo)
        elif tipo == "warning":
            warnings.append(codigo)

    def _registrar_error_producto(
        self, codigo: str, e: Exception, sap_obligatorio: bool,
        detalle: Dict, errores: List, warnings: List, incluir_extras: bool = False
    ) -> None:
        """Registra el detalle y clasifica un código que falló con excepción inesperada."""
        logger.error(f"❌ Error inesperado al validar código {codigo} en SAP: {e}", exc_info=True)
        severity = "ERROR" if sap_obligatorio else "WARNING"
        det = {
            "existe": False,
            "info": None,
            "error": str(e),
            "severity": severity
        }
        if incluir_extras:
            det["mba3"] = None
            det["sugerencias_sap"] = []
        detalle[codigo] = det
        if sap_obligatorio:
            errores.append(codigo)
        else:
            warnings.append(codigo)

    @staticmethod
    def _log_resumen_sugerencias(validos: List, no_encontrados: List, errores: List) -> None:
        """Emite el log resumen de la validación de productos con sugerencias."""
        if no_encontrados or errores:
            logger.warning(
                f"📊 Validación SAP: {len(validos)}✓, {len(no_encontrados)}✗, {len(errores)} errores"
            )
        else:
            logger.debug(f"📊 Validación SAP: {len(validos)} productos válidos")

    def validar_productos_existen_en_sap(
        self,
        codigos_productos: List[str],
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

        if not codigos_productos:
            return {
                "validos": [],
                "no_encontrados": [],
                "errores": [],
                "warnings": [],
                "todos_validos": True,
                "detalle": {}
            }

        resultado_deshabilitado = self._handle_sap_disabled(codigos_productos, sap_obligatorio, "productos")
        if resultado_deshabilitado:
            return resultado_deshabilitado

        detalle = {}
        validos = []
        no_encontrados = []
        errores = []
        warnings = []

        sap_service = SAPService()

        for codigo in codigos_productos:
            try:
                tipo, det = self._procesar_un_codigo_producto(codigo, sap_service, sap_obligatorio)
                detalle[codigo] = det
                self._clasificar_tipo_codigo(tipo, codigo, validos, no_encontrados, errores, warnings)
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

    def _procesar_un_codigo_producto(
        self, codigo: str, sap_service: Any, sap_obligatorio: bool
    ):
        """Normaliza y consulta SAP para un código; retorna (tipo, detalle_dict)."""
        codigo_clean = codigo.strip() if codigo else ""
        if not codigo_clean:
            return "no_encontrado", {
                "existe": False,
                "info": None,
                "error": self._CODIGO_VACIO,
                "severity": "ERROR"
            }
        producto_info = sap_service.get_or_fetch_producto_info(codigo_clean)
        resultado = self._procesar_resultado_producto(codigo_clean, producto_info, sap_obligatorio)
        return resultado["tipo"], resultado["detalle"]

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

        if not codigos_productos:
            return {
                "validos": [],
                "no_encontrados": [],
                "errores": [],
                "warnings": [],
                "todos_validos": True,
                "detalle": {}
            }

        resultado_deshabilitado = self._handle_sap_disabled(codigos_productos, sap_obligatorio, "productos")
        if resultado_deshabilitado:
            return resultado_deshabilitado

        detalle = {}
        validos = []
        no_encontrados = []
        errores = []
        warnings = []

        sap_service = SAPService()

        for codigo in codigos_productos:
            try:
                tipo, det = self._procesar_un_codigo_con_sugerencias(
                    codigo, sap_service, sap_obligatorio, usar_cache, incluir_sugerencias, limite_sugerencias
                )
                detalle[codigo] = det
                self._clasificar_tipo_codigo(tipo, codigo, validos, no_encontrados, errores, warnings)
            except Exception as e:
                self._registrar_error_producto(
                    codigo, e, sap_obligatorio, detalle, errores, warnings, incluir_extras=True
                )

        todos_validos = len(no_encontrados) == 0 and len(errores) == 0

        self._log_resumen_sugerencias(validos, no_encontrados, errores)

        return {
            "validos": validos,
            "no_encontrados": no_encontrados,
            "errores": errores,
            "warnings": warnings,
            "todos_validos": todos_validos,
            "detalle": detalle
        }

    def _procesar_un_codigo_con_sugerencias(
        self, codigo: str, sap_service: Any, sap_obligatorio: bool,
        usar_cache: bool, incluir_sugerencias: bool, limite_sugerencias: int
    ):
        """Normaliza, consulta SAP y agrega MBA3/sugerencias para un código; retorna (tipo, detalle_dict)."""
        codigo_clean = codigo.strip() if codigo else ""
        if not codigo_clean:
            return "no_encontrado", {
                "existe": False,
                "info": None,
                "error": self._CODIGO_VACIO,
                "severity": "ERROR",
                "mba3": None,
                "sugerencias_sap": []
            }
        producto_info = sap_service.get_or_fetch_producto_info(codigo_clean, force_refresh=not usar_cache)
        resultado_codigo = self._procesar_resultado_producto(codigo_clean, producto_info, sap_obligatorio)
        detalle_base = resultado_codigo["detalle"]
        if resultado_codigo["tipo"] == "valido":
            detalle_base["mba3"] = None
            detalle_base["sugerencias_sap"] = []
            return "valido", detalle_base
        info_mba3, sugerencias = self._buscar_mba3_y_sugerencias(codigo_clean, incluir_sugerencias, limite_sugerencias)
        detalle_base["mba3"] = info_mba3
        detalle_base["sugerencias_sap"] = sugerencias
        return resultado_codigo["tipo"], detalle_base

    def _buscar_mba3_y_sugerencias(
        self, codigo_clean: str, incluir_sugerencias: bool, limite_sugerencias: int
    ):
        """Busca en MBA3 y genera sugerencias SAP para un código no encontrado; retorna (info_mba3, sugerencias)."""
        from src.config import ENABLE_SAP_QUERIES
        if not incluir_sugerencias or not ENABLE_SAP_QUERIES:
            return None, []
        try:
            info_mba3 = self._buscar_en_mba3(codigo_clean)
            # ⭐ SIEMPRE generar sugerencias (incluso si no está en MBA3)
            # Esto permite encontrar variaciones del código en SAP
            sugerencias = self._generar_sugerencias_sap(codigo_clean, info_mba3, limite_sugerencias)
            if sugerencias or info_mba3:
                logger.debug(f"🔍 {codigo_clean}: MBA3={'✓' if info_mba3 else '✗'}, Sugerencias={len(sugerencias)}")
            return info_mba3, sugerencias
        except Exception as e:
            logger.warning(f"⚠️ Error al buscar sugerencias para {codigo_clean}: {e}", exc_info=True)
            return None, []

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

            if self._mba3_lookup_disabled:
                logger.debug(
                    "Saltando búsqueda MBA3 para %s porque MBA3 fue marcado como no disponible: %s",
                    codigo,
                    self._mba3_lookup_disable_reason or "sin detalle",
                )
                return None

            if not codigo or not codigo.strip():
                return None

            codigo_clean = codigo.strip()
            # Permitir mismos caracteres que SAP (incl. / y _) para consistencia
            if not re.match(r'^[A-Za-z0-9.\-_/ ]{1,50}$', codigo_clean):
                logger.warning(f"⚠️ Código con formato inválido para MBA3: {codigo_clean}")
                return None

            if not self._mba3_lookup_available():
                return None

            # Escapar comillas simples
            codigo_escaped = codigo_clean.replace("'", "''")

            # Consulta a MBA3 con timeout para no bloquear el flujo si MBA3 no está disponible
            query = (
                "SELECT PRODUCT_ID, PRODUCT_NAME, CORP, GrupoPrenda, Talla, PRESENTACION, "
                "GROUP_CODE, Tipo_Origen, Descontinuado, INACTIVE "
                "FROM INVT_FICHA_PRINCIPAL "
                f"WHERE PRODUCT_ID = '{codigo_escaped}' "
                "LIMIT 1"
            )

            def _run_mba3_query() -> Any:
                mba3_service = MBA3Service()
                return mba3_service.execute_query(query)

            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(_run_mba3_query)
            timed_out = False
            try:
                result = future.result(timeout=MBA3_LOOKUP_TIMEOUT_SECONDS)
            except FuturesTimeoutError:
                timed_out = True
                future.cancel()
                self._disable_mba3_lookup(
                    f"timeout de {MBA3_LOOKUP_TIMEOUT_SECONDS}s consultando {codigo_clean}"
                )
                logger.warning(
                    "⚠️ Timeout al buscar código %s en MBA3 (%ds). MBA3 puede no estar disponible.",
                    codigo_clean,
                    MBA3_LOOKUP_TIMEOUT_SECONDS,
                )
                return None
            finally:
                # Con wait=False el timeout realmente libera el flujo de validación.
                # El request bloqueado terminará solo cuando requests agote su timeout interno.
                executor.shutdown(wait=not timed_out, cancel_futures=True)

            return self._normalizar_resultado_mba3(result, codigo_clean)

        except MBA3ConnectionError as e:
            self._disable_mba3_lookup(str(e).splitlines()[0])
            logger.warning(f"⚠️ Error de conexión al buscar código {codigo} en MBA3: {e}")
            return None
        except Exception as e:
            logger.warning(f"⚠️ Error al buscar código {codigo} en MBA3: {e}")
            return None

    def _normalizar_resultado_mba3(self, result: Any, codigo_clean: str) -> Optional[Dict[str, Any]]:
        """Extrae el primer producto del resultado MBA3 y normaliza sus campos."""
        if isinstance(result, list):
            productos = result
        elif isinstance(result, dict):
            productos = []
            for _key, value in result.items():
                if isinstance(value, list):
                    productos = value
                    break
            if not productos and result:
                productos = [result]
        else:
            productos = []

        if not productos:
            return None

        return self._extraer_campos_producto_mba3(productos[0], codigo_clean)

    def _extraer_campos_producto_mba3(self, producto: Dict[str, Any], codigo_clean: str) -> Dict[str, Any]:
        """Normaliza los nombres de campos de un producto MBA3."""
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

    def _mba3_lookup_available(self) -> bool:
        """Verifica una sola vez si MBA3 acepta conexiones antes de hacer búsquedas de sugerencias."""
        if self._mba3_lookup_disabled:
            return False
        if self._mba3_reachability_checked:
            return True

        try:
            from src.config import MBA3_BASE_URL

            parsed_url = urlparse(MBA3_BASE_URL)
            host = parsed_url.hostname
            if not host:
                self._disable_mba3_lookup("MBA3_BASE_URL no tiene host configurado")
                return False

            port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)
            socket.create_connection((host, port), timeout=MBA3_REACHABILITY_TIMEOUT_SECONDS).close()

            self._mba3_reachability_checked = True
            return True
        except OSError as e:
            self._disable_mba3_lookup(f"MBA3 no responde en {host}:{port} ({e})")
            return False
        except Exception as e:
            self._disable_mba3_lookup(f"no se pudo verificar disponibilidad de MBA3 ({e})")
            return False

    def _disable_mba3_lookup(self, reason: str) -> None:
        if self._mba3_lookup_disabled:
            return
        self._mba3_lookup_disabled = True
        self._mba3_lookup_disable_reason = reason
        logger.warning(
            "⚠️ MBA3 no disponible para sugerencias de productos; "
            "se omitirán búsquedas MBA3 en esta validación. Motivo: %s",
            reason,
        )

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
            logger.info(f"🔍 Validando {len(codigos_bodegas)} códigos de bodegas (caché primero, SAP solo si es necesario)")
            bodegas_validadas = bodega_sap_service.validate_codigos_bodegas_tiendas(
                codigos=codigos_bodegas,
                force_refresh=False
            )

            if not bodegas_validadas:
                logger.error("❌ No se pudo validar códigos de bodegas")
                return self._crear_resultado_error_catalogo(
                    codigos_bodegas, "No se pudo validar códigos"
                )

            for codigo in codigos_bodegas:
                self._clasificar_bodega(codigo, bodegas_validadas, detalle, validas, no_encontradas)

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

    def _clasificar_bodega(
        self, codigo: str, bodegas_validadas: Dict[str, Any],
        detalle: Dict, validas: List, no_encontradas: List
    ) -> None:
        """Evalúa un código de bodega contra el resultado de validación y actualiza las listas."""
        codigo_clean = codigo.strip() if codigo else ""
        if not codigo_clean:
            detalle[codigo] = {
                "existe": False,
                "info": None,
                "error": self._CODIGO_VACIO,
                "severity": "ERROR"
            }
            no_encontradas.append(codigo)
            return
        resultado_validacion = bodegas_validadas.get(codigo_clean.upper())
        if resultado_validacion and resultado_validacion.get("encontrado"):
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
            detalle[codigo] = {
                "existe": False,
                "info": None,
                "error": "no_existe",
                "severity": "ERROR",
                "mensaje": f"La bodega '{codigo_clean}' no existe en SAP OWHS"
            }
            no_encontradas.append(codigo)

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
            logger.info(f"🔍 Validando {len(codigos_tiendas)} códigos de tiendas (caché primero, SAP solo si es necesario)")
            tiendas_validadas = bodega_sap_service.validate_codigos_bodegas_tiendas(
                codigos=codigos_tiendas,
                force_refresh=False
            )

            if tiendas_validadas is None:
                logger.error("❌ No se pudo validar códigos de tiendas")
                return self._crear_resultado_error_catalogo(
                    codigos_tiendas, "No se pudo validar códigos"
                )

            logger.info(f"📋 Validación completada: {len([t for t in tiendas_validadas.values() if t.get('encontrado')])} tiendas encontradas")

            for codigo in codigos_tiendas:
                self._clasificar_tienda(codigo, tiendas_validadas, detalle, validas, no_encontradas)

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

    def _clasificar_tienda(
        self, codigo: str, tiendas_validadas: Dict[str, Any],
        detalle: Dict, validas: List, no_encontradas: List
    ) -> None:
        """Evalúa un código de tienda contra el resultado de validación y actualiza las listas."""
        codigo_clean = codigo.strip() if codigo else ""
        if not codigo_clean:
            detalle[codigo] = {
                "existe": False,
                "info": None,
                "error": self._CODIGO_VACIO,
                "severity": "ERROR"
            }
            no_encontradas.append(codigo)
            return
        resultado_validacion = tiendas_validadas.get(codigo_clean.upper())
        if resultado_validacion and resultado_validacion.get("encontrado"):
            detalle[codigo] = {
                "existe": True,
                "info": {
                    "codigo": resultado_validacion["WhsCode"],
                    "nombre": resultado_validacion.get("WhsName"),
                    "es_bodega": resultado_validacion.get("es_bodega")
                },
                "error": None,
                "severity": None,
                "fuente": resultado_validacion.get("fuente", "cache")
            }
            validas.append(codigo)
            logger.debug(f"✅ Tienda validada: {codigo_clean} (fuente: {resultado_validacion.get('fuente', 'cache')})")
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
        codigo_clean: str,
        producto_info: Dict[str, Any] | None,
        sap_obligatorio: bool
    ) -> Dict[str, Any]:
        """
        Procesa el resultado de una consulta de producto a SAP.

        Args:
            codigo_clean: Código normalizado
            producto_info: Información del producto o None
            sap_obligatorio: Si True, errores bloquean

        Returns:
            {
                "tipo": str,  # "valido", "no_encontrado", "error", "warning"
                "detalle": Dict[str, Any]  # Detalle del resultado
            }
        """
        if producto_info and producto_info.get("_error"):
            return self._resultado_para_error_tipo(
                producto_info.get("_error_type"), codigo_clean, producto_info, sap_obligatorio
            )
        if producto_info:
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

    def _resultado_para_error_tipo(
        self, error_type: Any, codigo_clean: str,
        producto_info: Dict[str, Any], sap_obligatorio: bool
    ) -> Dict[str, Any]:
        """Construye el dict de resultado para cada tipo de error SAP."""
        if error_type == "no_existe":
            return {
                "tipo": "no_encontrado",
                "detalle": {
                    "existe": False, "info": None, "error": "no_existe", "severity": "ERROR",
                    "mensaje": f"El código '{codigo_clean}' no existe en SAP"
                }
            }
        if error_type == "inactivo":
            logger.warning(f"⚠️ Código '{codigo_clean}' existe en SAP pero está Inactivo → se mostrará con sugerencias en la UI")
            return {
                "tipo": "no_encontrado",
                "detalle": {
                    "existe": False, "info": None, "error": "inactivo", "severity": "ERROR",
                    "mensaje": f"El código '{codigo_clean}' existe en SAP pero está Inactivo. Use un código activo (ver sugerencias)."
                }
            }
        if error_type == "mismatch":
            item_code_sap = producto_info.get("_item_code_sap", "N/A")
            return {
                "tipo": "no_encontrado",
                "detalle": {
                    "existe": False, "info": None, "error": "mismatch", "severity": "ERROR",
                    "mensaje": f"El código '{codigo_clean}' no coincide exacto con ItemCode SAP '{item_code_sap}'",
                    "item_code_sap": item_code_sap
                }
            }
        severity = "ERROR" if sap_obligatorio else "WARNING"
        tipo = "error" if sap_obligatorio else "warning"
        if error_type == "error":
            error_msg = producto_info.get("_error_message", "Error desconocido")
            return {
                "tipo": tipo,
                "detalle": {
                    "existe": False, "info": None, "error": error_type, "severity": severity,
                    "mensaje": f"Error al consultar SAP para '{codigo_clean}': {error_msg}"
                }
            }
        return {
            "tipo": tipo,
            "detalle": {
                "existe": False, "info": None,
                "error": error_type or "error_desconocido", "severity": severity
            }
        }

    def _crear_resultado_error_catalogo(
        self,
        codigos: List[str],
        mensaje_error: str
    ) -> Dict[str, Any]:
        """
        Crea un resultado de error cuando no se puede obtener el catálogo SAP.

        Args:
            codigos: Lista de códigos
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
