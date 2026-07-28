"""
Cliente directo a SAP Business One Service Layer API (sin middleware).

Implementacion previa a la integracion del middleware .NET (restaurada desde el
historial de git). Se usa cuando SAP_USE_MIDDLEWARE=false en .env: permite seguir
probando la app (Purchase Orders, Inventory Transfer Requests) contra SAP directamente
mientras se resuelve algun problema puntual del middleware. Ver factory
SAPServiceLayerClient() en sap_service_layer_client.py.

Maneja la autenticacion y el envio de ordenes de compra (Purchase Orders) e Inventory
Transfer Requests a SAP Business One usando Service Layer REST API directamente.

Usa TLS 1.2+ (default); si la conexion con requests falla, reintenta una vez via curl
como ultimo recurso. Hasta 2026-07 tambien reintentaba con TLS 1.1/1.0 para servidores
SAP obsoletos; se quito tras confirmar en logs de produccion (~7 semanas, 125
autenticaciones) que el servidor SAP actual siempre negocia TLS 1.2+.
"""

import logging
import ssl
import subprocess
import json
import time
import requests
from typing import List, Optional, Dict, Any, Tuple, Union
from datetime import datetime, timedelta

from src.utils.timezone import ahora_naive
from requests.adapters import HTTPAdapter

from src.config import (
    SAP_SERVICE_LAYER_URL,
    SAP_SERVICE_LAYER_USERNAME,
    SAP_SERVICE_LAYER_PASSWORD,
    SAP_SERVICE_LAYER_DATABASE,
    ENABLE_SAP_SERVICE_LAYER,
    SAP_SERVICE_LAYER_TIMEOUT,
    SAP_SERVICE_LAYER_VERIFY_SSL,
    SAP_SERVICE_LAYER_TRANSIENT_RETRIES,
    SAP_SERVICE_LAYER_RETRY_BACKOFF_SECONDS,
)
from src.exceptions import SAPDataMasterError

logger = logging.getLogger(__name__)

JSON_CONTENT_TYPE = "application/json"
SESSION_ERROR_MESSAGE = "❌ No se pudo establecer sesión con SAP Service Layer"


class TLSAdapter(HTTPAdapter):
    """
    Adaptador HTTP personalizado para conectarse a SAP Service Layer con TLS 1.2+ (default),
    con opción de deshabilitar la verificación SSL (self.verify_ssl, solo desarrollo/pruebas).

    NOTA: hasta 2026-07 soportaba forzar TLS 1.0/1.1 para servidores SAP obsoletos. Se quitó
    tras confirmar en logs de producción (~7 semanas, 125 autenticaciones) que el servidor SAP
    actual siempre negocia TLS 1.2+ y nunca requirió ese fallback.
    """

    def __init__(self, verify_ssl=True, **kwargs):
        self.verify_ssl = verify_ssl
        super().__init__(**kwargs)

    def _apply_verify_ssl_settings(self, ctx):
        if self.verify_ssl:
            return
        ctx.verify_mode = ssl.CERT_NONE
        # Permitir ciphers antiguos cuando se deshabilita verificación
        # (necesario para servidores SAP con configuraciones obsoletas)
        try:
            ctx.set_ciphers('DEFAULT:@SECLEVEL=1')
        except (AttributeError, ssl.SSLError):
            # Si no se puede configurar, continuar sin cambios
            pass

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Crea un contexto SSL con TLS 1.2+ como mínimo y la configuración de verificación."""
        ctx = ssl.create_default_context()
        self._apply_verify_ssl_settings(ctx)
        if hasattr(ssl.TLSVersion, "TLSv1_2"):
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        return ctx

    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = self._create_ssl_context()
        return super().init_poolmanager(*args, **kwargs)


class DirectSAPServiceLayerClient:
    """Cliente para interactuar directamente con SAP Business One Service Layer API (sin middleware)."""
    
    def __init__(self):
        """Inicializa el cliente SAP Service Layer."""
        self.base_url = SAP_SERVICE_LAYER_URL.rstrip('/')
        self.username = SAP_SERVICE_LAYER_USERNAME
        self.password = SAP_SERVICE_LAYER_PASSWORD
        self.database = SAP_SERVICE_LAYER_DATABASE
        self.enabled = ENABLE_SAP_SERVICE_LAYER
        self.session_id: Optional[str] = None
        self.session_expires: Optional[datetime] = None
        self.timeout = SAP_SERVICE_LAYER_TIMEOUT
        self.verify_ssl = SAP_SERVICE_LAYER_VERIFY_SSL
        self.transient_retries = SAP_SERVICE_LAYER_TRANSIENT_RETRIES
        self.retry_backoff_seconds = SAP_SERVICE_LAYER_RETRY_BACKOFF_SECONDS
        self.working_session: Optional[requests.Session] = None
        self.working_tls_version: Optional[str] = None
        
        if not self.enabled:
            logger.warning("⚠️ SAP Service Layer deshabilitado (ENABLE_SAP_SERVICE_LAYER=False)")
        elif not self.username or not self.password:
            logger.warning("⚠️ Credenciales de SAP Service Layer no configuradas")
        
        if not self.verify_ssl:
            logger.warning("⚠️ VERIFICACIÓN SSL DESHABILITADA - Solo para desarrollo/pruebas")
            # Suprimir warnings de urllib3 sobre SSL
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def _is_session_valid(self) -> bool:
        """Verifica si la sesión actual es válida."""
        if not self.session_id:
            return False
        if not self.session_expires:
            return False
        # Renovar sesión si expira en menos de 5 minutos
        return ahora_naive() < (self.session_expires - timedelta(minutes=5))
    
    def _create_session(self) -> requests.Session:
        """Crea una sesión de requests con TLS 1.2+ (default)."""
        session = requests.Session()
        adapter = TLSAdapter(verify_ssl=self.verify_ssl)
        session.mount('https://', adapter)
        session.verify = self.verify_ssl
        return session

    def _try_request_with_fallback(self, method: str, url: str, **kwargs) -> Tuple[Optional[requests.Response], Optional[str]]:
        """
        Intenta realizar una petición HTTP con TLS 1.2+ (default); si falla por SSL/conexión,
        usa curl como último recurso.

        NOTA: hasta 2026-07 reintentaba con TLS 1.1/1.0 para servidores SAP obsoletos. Se quitó
        tras confirmar en logs de producción (~7 semanas, 125 autenticaciones) que el servidor
        SAP actual siempre negocia TLS 1.2+ y nunca requirió ese fallback.

        Args:
            method: Método HTTP (GET, POST, etc.)
            url: URL a la que hacer la petición
            **kwargs: Argumentos adicionales para requests (json, headers, etc.)

        Returns:
            Tupla (Response, tls_version_usada) o (None, None) si todos los intentos fallan
        """
        last_error = None

        try:
            session = self._create_session()
            response = session.request(method, url, timeout=self.timeout, **kwargs)

            if self.working_tls_version != "1.2+ (default)":
                logger.info("✅ Conexión exitosa usando TLS 1.2+ (default)")
                self.working_tls_version = "1.2+ (default)"
                self.working_session = session

            return response, "1.2+ (default)"

        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
            last_error = e
            logger.debug(f"⚠️ TLS 1.2+ (default) falló: {str(e)[:100]}")

        # Si requests falló por SSL/conexión, intentar con curl como último recurso
        logger.warning("⚠️ Conexión con requests falló, intentando con curl...")
        try:
            response = self._try_request_with_curl(method, url, **kwargs)
            if response:
                logger.info("✅ Conexión exitosa usando curl (fallback)")
                return response, "curl (fallback)"
        except Exception as e:
            logger.error(f"❌ Fallback con curl también falló: {e}")
            last_error = e

        logger.error(f"❌ Todos los métodos de conexión fallaron. Último error: {last_error}")
        return None, None
    
    def _try_request_with_curl(self, method: str, url: str, **kwargs) -> Optional[Union[requests.Response, Any]]:
        """
        Intenta realizar una petición usando curl como subproceso.
        
        Útil como último recurso cuando Python no puede negociar TLS con servidores obsoletos.
        
        Args:
            method: Método HTTP
            url: URL a la que hacer la petición
            **kwargs: Argumentos adicionales (json, headers, etc.)
            
        Returns:
            Response object simulado o None si falla
        """
        try:
            # Construir comando curl
            cmd = ["curl", "-k", "-s", "-S", "-X", method.upper()]
            
            # Agregar headers
            headers = kwargs.get('headers', {})
            for key, value in headers.items():
                cmd.extend(["-H", f"{key}: {value}"])
            
            # Agregar datos JSON si existen
            if 'json' in kwargs:
                cmd.extend(["-H", "Content-Type: application/json"])
                cmd.extend(["-d", json.dumps(kwargs['json'])])
            
            # Agregar timeout
            timeout = kwargs.get('timeout', self.timeout)
            cmd.extend(["--max-time", str(timeout)])
            
            # Agregar URL
            cmd.append(url)
            
            logger.debug(f"🔄 Ejecutando curl: {' '.join(cmd[:10])}...")
            
            # Ejecutar curl
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 5
            )
            
            if result.returncode == 0:
                # Simular un objeto Response básico
                # Nota: Esto es limitado, pero suficiente para login básico
                class MockResponse:
                    def __init__(self, text, status_code, cookies_str):
                        self.text = text
                        self.status_code = status_code
                        self._cookies = {}
                        # Parsear cookies básicas de curl output
                        if cookies_str:
                            for cookie in cookies_str.split(';'):
                                if '=' in cookie:
                                    key, value = cookie.split('=', 1)
                                    self._cookies[key.strip()] = value.strip()
                    
                    def json(self):
                        return json.loads(self.text)
                    
                    @property
                    def cookies(self):
                        class CookieJar:
                            def __init__(self, cookies_dict):
                                self._cookies = cookies_dict
                            
                            def get(self, key, default=None):
                                return self._cookies.get(key, default)
                        return CookieJar(self._cookies)
                
                # Intentar extraer status code y cookies del output
                status_code = 200  # curl no muestra status code fácilmente, asumir 200 si no hay error
                cookies_str = ""
                
                # Buscar cookies en stderr (curl las muestra ahí)
                if "Set-Cookie" in result.stderr:
                    # Extraer cookies básicas
                    pass
                
                return MockResponse(result.stdout, status_code, cookies_str)
            else:
                logger.error(f"❌ curl falló con código {result.returncode}: {result.stderr}")
                return None
                
        except FileNotFoundError:
            logger.warning("⚠️ curl no está disponible en el sistema")
            return None
        except Exception as e:
            logger.error(f"❌ Error al ejecutar curl: {e}")
            return None
    
    def login(self) -> bool:
        """
        Autentica con SAP Service Layer y obtiene un session ID.
        
        Usa fallback automático de TLS si el servidor solo soporta versiones antiguas.
        
        Returns:
            True si la autenticación fue exitosa, False en caso contrario
        """
        if not self.enabled:
            logger.debug("⏭️ Login a SAP Service Layer deshabilitado")
            return False
        
        if not self.username or not self.password:
            logger.error("❌ Credenciales de SAP Service Layer no configuradas")
            return False
        
        try:
            url = f"{self.base_url}/Login"
            payload = {
                "CompanyDB": self.database,
                "UserName": self.username,
                "Password": self.password
            }
            
            logger.debug(f"🔐 Autenticando con SAP Service Layer: {url}")
            
            # Usar sistema de fallback TLS
            response, tls_version = self._try_request_with_fallback(
                "POST",
                url,
                json=payload,
                headers={"Content-Type": JSON_CONTENT_TYPE}
            )
            
            if response is None:
                logger.error("❌ No se pudo establecer conexión con SAP Service Layer después de todos los intentos")
                return False
            
            if response.status_code == 200:
                # Extraer session ID de las cookies
                session_cookie = response.cookies.get('B1SESSION')
                if session_cookie:
                    self.session_id = session_cookie
                    # Las sesiones de SAP suelen durar 30 minutos
                    self.session_expires = ahora_naive() + timedelta(minutes=25)
                    logger.info(f"✅ Autenticación exitosa con SAP Service Layer (TLS: {tls_version})")
                    return True
                else:
                    logger.error("❌ No se recibió session ID en la respuesta")
                    return False
            else:
                error_msg = f"Error en autenticación: {response.status_code}"
                try:
                    error_body = response.json()
                    error_msg = error_body.get("error", {}).get("message", {}).get("value", error_msg)
                except Exception:
                    error_msg = f"{error_msg} - {response.text}"
                
                logger.error(f"❌ {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error inesperado al autenticar con SAP Service Layer: {e}", exc_info=True)
            return False
    
    def _ensure_session(self) -> bool:
        """Asegura que hay una sesión válida, renovándola si es necesario."""
        if self._is_session_valid():
            return True
        return self.login()

    @staticmethod
    def _is_transient_request_exception(exc: BaseException) -> bool:
        """Errores de red típicos cuando el Service Layer cierra la conexión o no responde a tiempo."""
        if isinstance(
            exc,
            (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
            ),
        ):
            return True
        return False

    @staticmethod
    def _is_transient_http_status(status_code: int) -> bool:
        return status_code in (502, 503, 504)

    def _should_retry(self, attempt: int, max_attempts: int) -> bool:
        return attempt < max_attempts - 1

    def _wait_and_log_retry(self, attempt: int, max_attempts: int, reason: str) -> None:
        wait = self.retry_backoff_seconds * (2**attempt)
        logger.warning(
            f"⚠️ {reason} (intento {attempt + 1}/{max_attempts}), reintento en {wait:.1f}s..."
        )
        time.sleep(wait)

    def _get_request_with_transient_retries(
        self,
        url: str,
        headers: Dict[str, str],
        *,
        operation_label: str = "SAP SL GET",
    ) -> Optional[requests.Response]:
        """
        Ejecuta GET con reintentos ante fallos transitorios (segfaults en SL, proxies, etc.).
        """
        max_attempts = 1 + max(0, self.transient_retries)
        for attempt in range(max_attempts):
            try:
                if self.working_session:
                    response = self.working_session.get(
                        url, headers=headers, timeout=self.timeout
                    )
                else:
                    response, _ = self._try_request_with_fallback("GET", url, headers=headers)
                    if response is None:
                        if self._should_retry(attempt, max_attempts):
                            self._wait_and_log_retry(
                                attempt,
                                max_attempts,
                                f"{operation_label}: sin respuesta",
                            )
                            continue
                        return None

                if self._is_transient_http_status(response.status_code):
                    if self._should_retry(attempt, max_attempts):
                        self._wait_and_log_retry(
                            attempt,
                            max_attempts,
                            f"{operation_label}: HTTP {response.status_code}",
                        )
                        continue
                return response

            except requests.exceptions.RequestException as e:
                if self._is_transient_request_exception(e) and self._should_retry(attempt, max_attempts):
                    self._wait_and_log_retry(
                        attempt,
                        max_attempts,
                        f"{operation_label}: error transitorio ({e!s})",
                    )
                    continue
                logger.error(f"❌ {operation_label}: error de conexión (sin más reintentos): {e}")
                return None

        return None

    def _post_json_with_transient_retries(
        self,
        url: str,
        headers: Dict[str, str],
        json_data: Dict[str, Any],
        *,
        operation_label: str = "SAP SL POST",
    ) -> Optional[requests.Response]:
        """POST JSON con reintentos ante fallos transitorios."""
        max_attempts = 1 + max(0, self.transient_retries)
        for attempt in range(max_attempts):
            try:
                if self.working_session:
                    response = self.working_session.post(
                        url,
                        json=json_data,
                        headers=headers,
                        timeout=self.timeout,
                    )
                else:
                    response, _ = self._try_request_with_fallback(
                        "POST",
                        url,
                        json=json_data,
                        headers=headers,
                    )
                    if response is None:
                        if self._should_retry(attempt, max_attempts):
                            self._wait_and_log_retry(
                                attempt,
                                max_attempts,
                                f"{operation_label}: sin respuesta",
                            )
                            continue
                        return None

                if self._is_transient_http_status(response.status_code):
                    if self._should_retry(attempt, max_attempts):
                        self._wait_and_log_retry(
                            attempt,
                            max_attempts,
                            f"{operation_label}: HTTP {response.status_code}",
                        )
                        continue
                return response

            except requests.exceptions.RequestException as e:
                if self._is_transient_request_exception(e) and self._should_retry(attempt, max_attempts):
                    self._wait_and_log_retry(
                        attempt,
                        max_attempts,
                        f"{operation_label}: error transitorio ({e!s})",
                    )
                    continue
                logger.error(f"❌ {operation_label}: error de conexión (sin más reintentos): {e}")
                return None

        return None
    
    def _get_stock_from_warehouses(
        self,
        item_code: str,
        warehouse_code: str,
        warehouses: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Extrae la información de stock para la bodega solicitada a partir de la colección de bodegas."""
        if not warehouses:
            raise SAPDataMasterError(
                item_code=item_code,
                warehouse_code=warehouse_code,
                error_type="no_warehouse_info",
                available_warehouses=[],
            )

        warehouse_info = None
        available_warehouses = []
        for warehouse in warehouses:
            warehouse_code_value = warehouse.get("WarehouseCode", "")
            available_warehouses.append(warehouse_code_value)
            if warehouse_code_value.upper() == warehouse_code.upper():
                warehouse_info = warehouse
                break

        logger.info(
            f"🔍 {item_code} → Búsqueda {warehouse_code}: "
            f"{'ENCONTRADA' if warehouse_info else f'NO ENCONTRADA (entre {len(available_warehouses)} bodegas)'}"
        )

        if not warehouse_info:
            raise SAPDataMasterError(
                item_code=item_code,
                warehouse_code=warehouse_code,
                error_type="warehouse_not_found",
                available_warehouses=available_warehouses,
            )

        in_stock_raw = float(warehouse_info.get("InStock") or 0)
        is_committed = float(warehouse_info.get("IsCommited") or 0)
        in_stock = in_stock_raw - is_committed
        uom_code = warehouse_info.get("UomCode")
        locked = warehouse_info.get("Locked")

        if uom_code is None:
            logger.warning(f"⚠️ {item_code}: UomCode=NULL - validación en unidades base")

        if locked == "tYES":
            logger.warning(
                f"⚠️ {item_code} en {warehouse_code} está BLOQUEADO (Locked=tYES). "
                f"Stock disponible: {in_stock} (InStock={in_stock_raw}, Comprometido={is_committed})"
            )

        logger.info(
            f"✅ Stock disponible calculado: {item_code} en {warehouse_code} = {in_stock} "
            f"(InStock={in_stock_raw}, Comprometido={is_committed}, "
            f"UomCode={uom_code if uom_code else 'NULL'}, "
            f"Locked={locked if locked else 'NULL'})"
        )

        return {
            "InStock": in_stock,
            "UomCode": uom_code,
            "WarehouseCode": warehouse_code,
            "Locked": locked,
            "IsCommited": is_committed,
        }

    def _log_stock_error(self, item_code: str, warehouse_code: str, url: str, response: requests.Response) -> None:
        """Registra el detalle de un error HTTP al consultar stock."""
        logger.error(
            f"❌ ERROR HTTP de SAP al consultar stock de {item_code}:\n"
            f"   URL consultada: {url}\n"
            f"   Status Code: {response.status_code}\n"
            f"   Headers de respuesta: {dict(response.headers)}\n"
            f"   Texto de respuesta (primeros 500 chars): {response.text[:500]}"
        )

        error_msg = f"Error al consultar stock: {response.status_code}"
        try:
            error_body = response.json()
            logger.error(
                f"❌ RESPUESTA CRUDA DE ERROR de SAP (JSON):\n"
                f"   {error_body}"
            )
            error_detail = error_body.get("error", {})
            if isinstance(error_detail.get("message"), dict):
                error_msg = error_detail.get("message", {}).get("value", error_msg)
            elif isinstance(error_detail.get("message"), str):
                error_msg = error_detail.get("message", error_msg)
        except Exception as json_error:
            logger.error(
                f"❌ No se pudo parsear respuesta de error como JSON: {json_error}\n"
                f"   Respuesta completa (primeros 1000 chars): {response.text[:1000]}"
            )
            error_msg = f"{error_msg} - {response.text[:200]}"

        logger.error(f"❌ Error procesado: {error_msg}")

    def create_purchase_order(self, purchase_order_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Crea una orden de compra (Purchase Order) en SAP.
        
        Args:
            purchase_order_data: Diccionario con los datos de la orden de compra en formato SAP
            
        Returns:
            Diccionario con la respuesta de SAP incluyendo el DocEntry y DocNum, o None si falla
            
        Ejemplo de purchase_order_data:
        {
            "CardCode": "PROVEEDOR001",
            "DocDate": "2025-01-21",
            "DocDueDate": "2025-01-21",
            "TaxDate": "2025-01-21",
            "Comments": "Ref: 900125351",
            "DocumentLines": [
                {
                    "ItemCode": "5-0012.9",
                    "Quantity": 1824.0,
                    "UnitPrice": 1.1625,
                    "LineTotal": 2120.4
                }
            ]
        }
        """
        if not self.enabled:
            logger.debug("⏭️ Creación de Purchase Order deshabilitada")
            return None
        
        if not self._ensure_session():
            logger.error(SESSION_ERROR_MESSAGE)
            return None
        
        try:
            url = f"{self.base_url}/PurchaseOrders"
            headers = {
                "Content-Type": JSON_CONTENT_TYPE,
                "Cookie": f"B1SESSION={self.session_id}",
            }
            logger.info(f"📤 POST {url} (Purchase Orders)")
            logger.debug(f"   Request: {json.dumps(purchase_order_data, ensure_ascii=False, default=str)[:2500]}")
            
            response = self._post_json_with_transient_retries(
                url,
                headers,
                purchase_order_data,
                operation_label="POST PurchaseOrders",
            )
            if response is None:
                logger.error("❌ No se pudo establecer conexión con SAP Service Layer")
                return {
                    "success": False,
                    "error": "No se pudo establecer conexión con SAP Service Layer",
                }
            
            if response.status_code in [200, 201]:
                result = response.json()
                doc_entry = result.get("DocEntry")
                doc_num = result.get("DocNum")
                doc_date = result.get("DocDate")
                logger.info(
                    f"✅ Purchase Order creada en SAP: DocEntry={doc_entry}, DocNum={doc_num}"
                    + (f", DocDate={doc_date}" if doc_date else "")
                )
                logger.debug(f"   Response: {json.dumps(result, ensure_ascii=False, default=str)[:1500]}")
                return {
                    "success": True,
                    "doc_entry": doc_entry,
                    "doc_num": doc_num,
                    "doc_date": doc_date,
                    "data": result,
                }
            else:
                # Procesar error de SAP
                error_msg = f"Error al crear Purchase Order: {response.status_code}"
                error_code = None
                error_details = None
                
                try:
                    error_body = response.json()
                    error_detail = error_body.get("error", {})
                    
                    # Extraer mensaje de error de SAP
                    if isinstance(error_detail.get("message"), dict):
                        error_msg = error_detail.get("message", {}).get("value", error_msg)
                    elif isinstance(error_detail.get("message"), str):
                        error_msg = error_detail.get("message", error_msg)
                    
                    # Extraer código de error de SAP
                    error_code = error_detail.get("code", "")
                    
                    # Guardar detalles completos del error para debugging
                    error_details = error_body
                    
                    logger.error(f"❌ {error_msg} (Código: {error_code})")
                    logger.debug(f"   Response error: {json.dumps(error_body, ensure_ascii=False)[:1000]}")
                except Exception as e:
                    error_msg = f"{error_msg} - {response.text[:500]}"
                    logger.error(f"❌ {error_msg}")
                    logger.debug(f"   Response text: {response.text[:500]}; parse error: {e}")
                    error_details = {"raw": response.text[:1000]}
                    error_code = None
                
                return {
                    "success": False,
                    "error": error_msg,
                    "error_code": error_code,
                    "status_code": response.status_code,
                    "sap_error_details": error_details,
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error de conexión al crear Purchase Order: {e}")
            return {
                "success": False,
                "error": f"Error de conexión: {str(e)}"
            }
        except Exception as e:
            logger.error(f"❌ Error inesperado al crear Purchase Order: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Error inesperado: {str(e)}"
            }
    
    def create_stock_transfer(self, stock_transfer_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Crea una solicitud de transferencia de stock en SAP usando InventoryTransferRequests.
        
        ⚠️ IMPORTANTE: Este método usa el endpoint correcto de Service Layer:
           POST /InventoryTransferRequests
        
        Args:
            stock_transfer_data: Diccionario con los datos de la solicitud de transferencia en formato SAP
            
        Returns:
            Diccionario con la respuesta de SAP incluyendo el DocEntry y DocNum, o None si falla
            
        Ejemplo de stock_transfer_data:
        {
            "DocDate": "2025-01-21",
            "DueDate": "2025-01-21",
            "FromWarehouse": "OUT-CON",
            "ToWarehouse": "RG-CD",
            "Comments": "Transferencia desde OC 12345 - Pedido P-12.48",
            "StockTransferLines": [
                {
                    "ItemCode": "R5082-15.1012",
                    "Quantity": 10.0
                }
            ]
        }
        """
        if not self.enabled:
            logger.debug("⏭️ Creación de Inventory Transfer Request deshabilitada")
            return None
        
        if not self._ensure_session():
            logger.error(SESSION_ERROR_MESSAGE)
            return None
        
        try:
            # ⚠️ CORRECCIÓN CRÍTICA: Usar endpoint correcto de Service Layer
            url = f"{self.base_url}/InventoryTransferRequests"
            headers = {
                "Content-Type": JSON_CONTENT_TYPE,
                "Cookie": f"B1SESSION={self.session_id}"
            }
            
            logger.info(f"📤 POST {url} (Inventory Transfer Requests)")
            logger.debug(f"   Request: {json.dumps(stock_transfer_data, ensure_ascii=False, default=str)[:1500]}")
            
            response = self._post_json_with_transient_retries(
                url,
                headers,
                stock_transfer_data,
                operation_label="POST InventoryTransferRequests",
            )
            if response is None:
                logger.error("❌ No se pudo establecer conexión con SAP Service Layer")
                return {
                    "success": False,
                    "error": "No se pudo establecer conexión con SAP Service Layer",
                }
            
            if response.status_code in [200, 201]:
                result = response.json()
                doc_entry = result.get("DocEntry")
                doc_num = result.get("DocNum")
                logger.info(f"✅ Inventory Transfer Request creada en SAP: DocEntry={doc_entry}, DocNum={doc_num}")
                logger.debug(f"   Response: {json.dumps(result, ensure_ascii=False, default=str)[:1000]}")
                return {
                    "success": True,
                    "doc_entry": doc_entry,
                    "doc_num": doc_num,
                    "data": result,
                }
            else:
                error_msg = f"Error al crear Inventory Transfer Request: {response.status_code}"
                error_code = None
                error_details = None
                try:
                    error_body = response.json()
                    error_detail = error_body.get("error", {})
                    if isinstance(error_detail.get("message"), dict):
                        error_msg = error_detail.get("message", {}).get("value", error_msg)
                    elif isinstance(error_detail.get("message"), str):
                        error_msg = error_detail.get("message", error_msg)
                    error_code = error_detail.get("code", "")
                    error_details = error_body
                    logger.error(f"❌ {error_msg} (Código: {error_code})")
                    logger.debug(f"   Response error: {json.dumps(error_body, ensure_ascii=False)[:1000]}")
                except Exception as e:
                    error_msg = f"{error_msg} - {response.text[:500]}"
                    logger.error(f"❌ {error_msg}")
                    logger.debug(f"   Response text: {response.text[:500]}; parse error: {e}")
                    error_details = {"raw": response.text[:1000]}
                    error_code = None
                return {
                    "success": False,
                    "error": error_msg,
                    "error_code": error_code,
                    "status_code": response.status_code,
                    "sap_error_details": error_details,
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error de conexión al crear Inventory Transfer Request: {e}")
            return {
                "success": False,
                "error": f"Error de conexión: {str(e)}"
            }
        except Exception as e:
            logger.error(f"❌ Error inesperado al crear Inventory Transfer Request: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Error inesperado: {str(e)}"
            }
    
    def get_inventory_transfer_requests_by_comment(
        self,
        comment_filter: str,
    ) -> List[Dict[str, Any]]:
        """
        Consulta Inventory Transfer Requests en SAP filtrando por texto en Comments.

        Retorna una lista de dicts con DocNum, DocEntry, ToWarehouse, FromWarehouse y Comments.
        Si SAP no está disponible o la consulta falla, retorna lista vacía.
        """
        if not self.enabled:
            logger.debug("⏭️ Consulta de ITR deshabilitada")
            return []

        if not self._ensure_session():
            logger.error(f"{SESSION_ERROR_MESSAGE} para consultar ITR")
            return []

        try:
            # Escapar comillas simples para OData
            safe_filter = comment_filter.replace("'", "''")

            # SAP B1 Service Layer soporta contains() en $filter
            url = (
                f"{self.base_url}/InventoryTransferRequests"
                f"?$select=DocNum,DocEntry,ToWarehouse,FromWarehouse,Comments"
                f"&$filter=contains(Comments, '{safe_filter}')"
                f"&$orderby=DocNum asc"
            )

            headers = {
                "Content-Type": JSON_CONTENT_TYPE,
                "Cookie": f"B1SESSION={self.session_id}",
                "Prefer": "odata.maxpagesize=500",
            }

            logger.info(f"🔍 GET InventoryTransferRequests (filter: '{comment_filter}')")

            if self.working_session:
                response = self.working_session.get(url, headers=headers, timeout=self.timeout)
            else:
                response, _ = self._try_request_with_fallback("GET", url, headers=headers)
                if response is None:
                    logger.warning("⚠️ No se pudo consultar ITR en SAP")
                    return []

            if response.status_code == 200:
                data = response.json()
                items = data.get("value", [])
                logger.info(f"✅ ITR encontrados: {len(items)}")
                return [
                    {
                        "doc_num": item.get("DocNum"),
                        "doc_entry": item.get("DocEntry"),
                        "to_warehouse": item.get("ToWarehouse"),
                        "from_warehouse": item.get("FromWarehouse"),
                        "comments": item.get("Comments"),
                    }
                    for item in items
                ]
            else:
                logger.warning(
                    f"⚠️ Error al consultar ITR: {response.status_code} - "
                    f"{response.text[:500] if response.text else 'Sin detalle'}"
                )
                return []

        except Exception as e:
            logger.warning(f"⚠️ Error al consultar Inventory Transfer Requests: {e}")
            return []

    def get_stock_by_warehouse(
        self, 
        item_code: str, 
        warehouse_code: str
    ) -> Optional[Dict[str, Any]]:
        """
        Consulta el stock disponible (InStock) y UomCode de un artículo en una bodega específica.
        
        ⭐ CORRECCIÓN SAP B1 9.3: Usa GET /Items('X') y extrae ItemWarehouseInfoCollection
        del objeto completo, ya que el endpoint de navegación no funciona en todas las versiones.
        
        Args:
            item_code: Código del artículo en SAP (ej: "R5000.1012-3")
            warehouse_code: Código de la bodega (ej: "RL-CD", "OUT-CD", "RG-CD")
        
        Returns:
            Diccionario con información de stock:
            {
                "InStock": float,  # Stock disponible (descontando comprometido)
                "UomCode": str o None,  # Código de unidad de medida (NULL si solo conoce unidad base)
                "WarehouseCode": str,
                "Locked": str o None,  # Estado de bloqueo (tYES/tNO)
                "IsCommited": float  # Stock comprometido
            }
            O None si hay error de conexión.
            Lanza SAPDataMasterError si el artículo no tiene bodegas configuradas.
        """
        if not self.enabled:
            logger.debug("⏭️ Consulta de stock deshabilitada")
            return None
        
        if not self._ensure_session():
            logger.error(SESSION_ERROR_MESSAGE)
            return None
        
        try:
            item_code_escaped = item_code.replace("'", "''")
            url = f"{self.base_url}/Items('{item_code_escaped}')"
            headers = {
                "Content-Type": JSON_CONTENT_TYPE,
                "Cookie": f"B1SESSION={self.session_id}",
            }

            logger.debug(f"🔍 Consultando stock de {item_code} en {warehouse_code}...")

            response = self._get_request_with_transient_retries(
                url,
                headers,
                operation_label=f"GET Items (stock) '{item_code}'",
            )
            if response is None:
                logger.error("❌ No se pudo consultar stock en SAP")
                return None

            if response.status_code == 200:
                data = response.json()
                warehouses = data.get("ItemWarehouseInfoCollection", [])
                logger.debug(
                    f"🔍 {item_code} → ItemWarehouseInfoCollection: "
                    f"{'VACÍO' if not warehouses else f'{len(warehouses)} bodega(s)'}"
                )
                return self._get_stock_from_warehouses(item_code, warehouse_code, warehouses)

            self._log_stock_error(item_code, warehouse_code, url, response)
            return None
                
        except SAPDataMasterError:
            # Propagar errores de datos maestros para que el llamador pueda manejarlos
            raise
        except Exception as e:
            logger.error(f"❌ Error inesperado al consultar stock de {item_code} en {warehouse_code}: {e}", exc_info=True)
            return None
    
    def get_business_partner(self, card_code: str) -> Optional[Dict[str, Any]]:
        """
        Consulta un Business Partner (proveedor/cliente) en SAP Service Layer.
        
        Usa el endpoint: GET /BusinessPartners('CARD_CODE')
        
        Args:
            card_code: Código del socio de negocios (ej: "P1790389219001")
        
        Returns:
            Diccionario con información del BP si existe:
            {
                "CardCode": str,
                "CardName": str,
                "CardType": str,  # "cSupplier", "cCustomer"
                "Valid": str,  # "tYES", "tNO"
                "Frozen": str,  # "tYES", "tNO"
                ...
            }
            O None si hay error de conexión.
            Retorna {"_error": True, "_error_type": "no_existe"} si el BP no existe.
        """
        if not self.enabled:
            logger.debug("⏭️ Consulta de Business Partner deshabilitada")
            return None
        
        if not self._ensure_session():
            logger.error(SESSION_ERROR_MESSAGE)
            return None
        
        try:
            # Escapar caracteres especiales para OData
            card_code_escaped = card_code.replace("'", "''")
            
            url = f"{self.base_url}/BusinessPartners('{card_code_escaped}')"
            
            headers = {
                "Content-Type": JSON_CONTENT_TYPE,
                "Cookie": f"B1SESSION={self.session_id}"
            }
            
            logger.debug(f"🔍 Consultando Business Partner: {card_code}...")
            
            response = self._get_request_with_transient_retries(
                url,
                headers,
                operation_label=f"GET BusinessPartners('{card_code}')",
            )
            if response is None:
                logger.error(
                    "❌ No se pudo consultar Business Partner en SAP (sin respuesta tras reintentos): %s",
                    card_code,
                )
                return None
            
            if response.status_code == 200:
                data = response.json()
                logger.info(
                    f"✅ Business Partner encontrado: {card_code} - "
                    f"{data.get('CardName', 'N/A')} ({data.get('CardType', 'N/A')})"
                )
                return data
            elif response.status_code == 404:
                logger.warning(f"⚠️ Business Partner no encontrado: {card_code}")
                return {
                    "_error": True,
                    "_error_type": "no_existe",
                    "_error_message": f"Business Partner '{card_code}' no existe en SAP"
                }
            else:
                error_msg = f"Error al consultar Business Partner: {response.status_code}"
                try:
                    error_body = response.json()
                    error_detail = error_body.get("error", {})
                    if isinstance(error_detail.get("message"), dict):
                        error_msg = error_detail.get("message", {}).get("value", error_msg)
                    elif isinstance(error_detail.get("message"), str):
                        error_msg = error_detail.get("message", error_msg)
                except Exception:
                    error_msg = f"{error_msg} - {response.text[:200]}"
                
                logger.error(f"❌ {error_msg}")
                return {
                    "_error": True,
                    "_error_type": "error",
                    "_error_message": error_msg
                }
                
        except Exception as e:
            logger.error(f"❌ Error inesperado al consultar Business Partner {card_code}: {e}", exc_info=True)
            return None
    
    def get_item(self, item_code: str) -> Optional[Dict[str, Any]]:
        """
        Consulta un artículo (Item) en SAP Service Layer.
        
        Usa el endpoint: GET /Items('ITEM_CODE')
        
        Args:
            item_code: Código del artículo (ej: "MTF123.9", "R5082-15.1012")
        
        Returns:
            Diccionario con información del artículo si existe:
            {
                "ItemCode": str,
                "ItemName": str,
                "PurchaseItem": str,  # "tYES" si es comprable, "tNO" si no
                "SalesItem": str,  # "tYES" si es vendible
                "InventoryItem": str,  # "tYES" si maneja inventario
                "Valid": str,  # "tYES", "tNO"
                "Frozen": str,  # "tYES", "tNO"
                "ItemType": str,  # "itItems", "itService"
                ...
            }
            O None si hay error de conexión.
            Retorna {"_error": True, "_error_type": "no_existe"} si el artículo no existe.
        """
        if not self.enabled:
            logger.debug("⏭️ Consulta de Item deshabilitada")
            return None
        
        if not self._ensure_session():
            logger.error(SESSION_ERROR_MESSAGE)
            return None
        
        try:
            # Escapar caracteres especiales para OData
            item_code_escaped = item_code.replace("'", "''")
            
            url = f"{self.base_url}/Items('{item_code_escaped}')"
            
            headers = {
                "Content-Type": JSON_CONTENT_TYPE,
                "Cookie": f"B1SESSION={self.session_id}"
            }
            
            logger.debug(f"🔍 Consultando Item: {item_code}...")
            
            response = self._get_request_with_transient_retries(
                url,
                headers,
                operation_label=f"GET Items('{item_code}')",
            )
            if response is None:
                logger.error(
                    "❌ No se pudo consultar Item en SAP (sin respuesta tras reintentos): %s",
                    item_code,
                )
                return None
            
            if response.status_code == 200:
                data = response.json()
                is_purchase = data.get('PurchaseItem', 'tNO')
                is_valid = data.get('Valid', 'tNO')
                is_frozen = data.get('Frozen', 'tNO')
                
                # Log compacto con información relevante
                logger.info(
                    f"✅ Item encontrado: {item_code} - "
                    f"Comprable={is_purchase}, Valid={is_valid}, Frozen={is_frozen}"
                )
                return data
            elif response.status_code == 404:
                logger.warning(f"⚠️ Item no encontrado: {item_code}")
                return {
                    "_error": True,
                    "_error_type": "no_existe",
                    "_error_message": f"Item '{item_code}' no existe en SAP"
                }
            else:
                error_msg = f"Error al consultar Item: {response.status_code}"
                try:
                    error_body = response.json()
                    error_detail = error_body.get("error", {})
                    if isinstance(error_detail.get("message"), dict):
                        error_msg = error_detail.get("message", {}).get("value", error_msg)
                    elif isinstance(error_detail.get("message"), str):
                        error_msg = error_detail.get("message", error_msg)
                except Exception:
                    error_msg = f"{error_msg} - {response.text[:200]}"
                
                logger.error(f"❌ {error_msg}")
                return {
                    "_error": True,
                    "_error_type": "error",
                    "_error_message": error_msg
                }
                
        except Exception as e:
            logger.error(f"❌ Error inesperado al consultar Item {item_code}: {e}", exc_info=True)
            return None
    
    def validate_item_in_warehouse(
        self, 
        item_code: str, 
        warehouse_code: str
    ) -> Dict[str, Any]:
        """
        Valida que un artículo exista y esté configurado en una bodega específica.
        
        Combina get_item() + get_stock_by_warehouse() para validación completa.
        
        Args:
            item_code: Código del artículo
            warehouse_code: Código de la bodega
        
        Returns:
            {
                "valid": bool,
                "item_exists": bool,
                "is_purchase_item": bool,
                "warehouse_configured": bool,
                "stock": float o None,
                "errors": List[str]
            }
        """
        result = {
            "valid": False,
            "item_exists": False,
            "is_purchase_item": False,
            "warehouse_configured": False,
            "stock": None,
            "errors": []
        }
        
        # 1. Validar que el artículo existe
        item = self.get_item(item_code)
        
        if item is None:
            result["errors"].append(f"Error de conexión al validar artículo {item_code}")
            return result
        
        if item.get("_error"):
            if item.get("_error_type") == "no_existe":
                result["errors"].append(f"Artículo '{item_code}' no existe en SAP")
            else:
                result["errors"].append(item.get("_error_message", f"Error al validar {item_code}"))
            return result
        
        result["item_exists"] = True
        
        # 2. Validar que sea artículo de compra
        if item.get("PurchaseItem") != "tYES":
            result["errors"].append(
                f"Artículo '{item_code}' no está habilitado para compra (PurchaseItem={item.get('PurchaseItem')})"
            )
            return result
        
        result["is_purchase_item"] = True
        
        # 3. Validar que el artículo está configurado en la bodega
        try:
            stock_info = self.get_stock_by_warehouse(item_code, warehouse_code)
            
            if stock_info is None:
                result["errors"].append(f"Error de conexión al validar bodega {warehouse_code}")
                return result
            
            # get_stock_by_warehouse retorna info de bodega si está configurada
            result["warehouse_configured"] = True
            result["stock"] = stock_info.get("InStock", 0)
            result["valid"] = True
            
        except SAPDataMasterError as e:
            # El artículo no está configurado en la bodega especificada
            if e.available_warehouses:
                result["errors"].append(
                    f"Artículo '{item_code}' no está configurado en bodega '{warehouse_code}'. "
                    f"Bodegas disponibles: {', '.join(e.available_warehouses)}"
                )
            else:
                result["errors"].append(
                    f"Artículo '{item_code}' no tiene bodegas configuradas en SAP. "
                    f"Contacte a logística para dar de alta el artículo en la bodega '{warehouse_code}'."
                )
        except Exception as e:
            result["errors"].append(f"Error inesperado al validar artículo en bodega: {str(e)}")
        
        return result
    
    # -- Capacidades agregadas despues de la migracion a middleware --------
    # (get_all_warehouses / validate_warehouses_batch / validate_purchase_order_batch)
    # No existian en el flujo directo original. Retornan None (mismo contrato que
    # "middleware no disponible") para que los callers (BodegaSAPService, ordenes_compra)
    # hagan su fallback ya existente a OPENQUERY / validacion linea por linea. Estas
    # rutas ademas estan detras de sus propios flags (USE_MIDDLEWARE_WAREHOUSES,
    # USE_BATCH_VALIDATION), que por defecto son false, asi que en la practica no
    # deberian invocarse en modo directo.

    def get_all_warehouses(self) -> Optional[List[Dict[str, Any]]]:
        """No disponible en el cliente directo; el caller hace fallback a OPENQUERY."""
        logger.debug("(direct) get_all_warehouses no disponible en modo directo (sin middleware)")
        return None

    def validate_warehouses_batch(self, warehouse_codes: List[str]) -> Optional[Dict[str, Any]]:
        """No disponible en el cliente directo; el caller hace fallback a OPENQUERY."""
        logger.debug("(direct) validate_warehouses_batch no disponible en modo directo (sin middleware)")
        return None

    def validate_purchase_order_batch(
        self,
        card_code: Optional[str],
        lines: List[Dict[str, str]],
    ):
        """No disponible en el cliente directo; el caller hace fallback linea por linea."""
        logger.debug("(direct) validate_purchase_order_batch no disponible en modo directo (sin middleware)")
        return None

    def get_items_batch(self, item_codes: List[str]) -> Optional[Dict[str, Dict[str, Any]]]:
        """No disponible en el cliente directo; el caller resuelve codigo por codigo."""
        logger.debug("(direct) get_items_batch no disponible en modo directo (sin middleware)")
        return None

    def logout(self) -> bool:
        """
        Cierra la sesión en SAP Service Layer.
        
        Returns:
            True si el logout fue exitoso
        """
        if not self.session_id:
            return True
        
        try:
            url = f"{self.base_url}/Logout"
            headers = {
                "Cookie": f"B1SESSION={self.session_id}"
            }
            
            # Usar sesión existente si está disponible, sino usar fallback
            if self.working_session:
                response = self.working_session.post(url, headers=headers, timeout=self.timeout)
            else:
                response, _ = self._try_request_with_fallback("POST", url, headers=headers)
                if response is None:
                    logger.warning("⚠️ No se pudo establecer conexión para logout")
                    return False
            
            if response.status_code == 204:
                logger.debug("✅ Sesión cerrada en SAP Service Layer")
                self.session_id = None
                self.session_expires = None
                return True
            else:
                logger.warning(f"⚠️ Error al cerrar sesión: {response.status_code}")
                return False
                
        except Exception as e:
            logger.warning(f"⚠️ Error al cerrar sesión: {e}")
            return False
        finally:
            self.session_id = None
            self.session_expires = None
