"""
Cliente para interactuar con SAP Business One Service Layer API.

Este cliente maneja la autenticación y el envío de órdenes de compra (Purchase Orders)
a SAP Business One usando Service Layer REST API.

Incluye soporte para fallback automático de TLS cuando el servidor SAP solo soporta
versiones antiguas de TLS (1.0, 1.1) debido a configuraciones obsoletas.
"""

import logging
import ssl
import subprocess
import json
import requests
from typing import Optional, Dict, Any, Tuple, Union
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter

from src.config import (
    SAP_SERVICE_LAYER_URL,
    SAP_SERVICE_LAYER_USERNAME,
    SAP_SERVICE_LAYER_PASSWORD,
    SAP_SERVICE_LAYER_DATABASE,
    ENABLE_SAP_SERVICE_LAYER,
    SAP_SERVICE_LAYER_TIMEOUT,
    SAP_SERVICE_LAYER_VERIFY_SSL
)
from src.exceptions import SAPDataMasterError

logger = logging.getLogger(__name__)


class TLSAdapter(HTTPAdapter):
    """
    Adaptador HTTP personalizado que permite especificar la versión de TLS.
    
    Útil para conectarse a servidores SAP Service Layer que solo soportan
    versiones antiguas de TLS (1.0, 1.1) debido a configuraciones obsoletas.
    """
    
    def __init__(self, ssl_version=None, verify_ssl=True, **kwargs):
        self.ssl_version = ssl_version
        self.verify_ssl = verify_ssl
        super().__init__(**kwargs)
    
    def init_poolmanager(self, *args, **kwargs):
        # Crear contexto SSL personalizado
        ctx = ssl.create_default_context()
        
        if self.ssl_version:
            # Intentar configurar versión específica de TLS
            try:
                if self.ssl_version == ssl.PROTOCOL_TLSv1:
                    # TLS 1.0 - usar el mínimo soportado (puede no estar disponible en Python 3.10+)
                    try:
                        ctx.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
                        ctx.maximum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
                    except AttributeError:
                        # Python < 3.7, usar protocolo directamente
                        ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
                elif self.ssl_version == ssl.PROTOCOL_TLSv1_1:
                    # TLS 1.1 - puede no estar disponible
                    try:
                        ctx.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
                    except AttributeError:
                        try:
                            ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1_1)
                        except AttributeError:
                            # TLS 1.1 no disponible, usar mínimo
                            pass
                else:
                    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            except (AttributeError, ValueError) as e:
                # Si falla, usar contexto por defecto
                logger.debug(f"⚠️ No se pudo configurar TLS específico: {e}")
                ctx = ssl.create_default_context()
        
        # Deshabilitar verificación si es necesario
        if not self.verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            # Permitir ciphers antiguos cuando se deshabilita verificación
            # (necesario para servidores SAP con configuraciones obsoletas)
            try:
                ctx.set_ciphers('DEFAULT:@SECLEVEL=1')
            except (AttributeError, ssl.SSLError):
                # Si no se puede configurar, continuar sin cambios
                pass
        
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)


class SAPServiceLayerClient:
    """Cliente para interactuar con SAP Business One Service Layer API."""
    
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
        return datetime.now() < (self.session_expires - timedelta(minutes=5))
    
    def _create_session_with_tls(self, tls_version: Optional[ssl._SSLMethod] = None, tls_name: str = "default") -> requests.Session:
        """
        Crea una sesión de requests con una versión específica de TLS.
        
        Args:
            tls_version: Versión de TLS a usar (ssl.PROTOCOL_TLSv1, etc.) o None para default
            tls_name: Nombre descriptivo de la versión TLS para logging
            
        Returns:
            Sesión de requests configurada
        """
        session = requests.Session()
        
        if tls_version:
            # Usar adaptador personalizado con TLS específico
            adapter = TLSAdapter(ssl_version=tls_version, verify_ssl=self.verify_ssl)
            session.mount('https://', adapter)
            logger.debug(f"🔐 Sesión creada con TLS {tls_name}")
        else:
            # Sesión por defecto (intenta TLS 1.2+)
            logger.debug("🔐 Sesión creada con TLS por defecto (1.2+)")
        
        # Configurar verificación SSL
        session.verify = self.verify_ssl
        
        return session
    
    def _try_request_with_fallback(self, method: str, url: str, **kwargs) -> Tuple[Optional[requests.Response], Optional[str]]:
        """
        Intenta realizar una petición HTTP con fallback automático de TLS.
        
        Intenta en este orden:
        1. TLS 1.2+ (default)
        2. TLS 1.1 (si está disponible)
        3. TLS 1.0 (para servidores SAP obsoletos)
        4. curl como último recurso
        
        Args:
            method: Método HTTP (GET, POST, etc.)
            url: URL a la que hacer la petición
            **kwargs: Argumentos adicionales para requests (json, headers, etc.)
            
        Returns:
            Tupla (Response, tls_version_usada) o (None, None) si todos los intentos fallan
        """
        # Lista de versiones TLS a intentar (en orden de preferencia)
        tls_attempts = [
            (None, "1.2+ (default)"),
            (ssl.PROTOCOL_TLSv1_1, "1.1"),
            (ssl.PROTOCOL_TLSv1, "1.0"),
        ]
        
        last_error = None
        
        for tls_version, tls_name in tls_attempts:
            try:
                session = self._create_session_with_tls(tls_version, tls_name)
                logger.debug(f"🔄 Intentando conexión con TLS {tls_name}...")
                
                # Realizar la petición
                response = session.request(method, url, timeout=self.timeout, **kwargs)
                
                # Si llegamos aquí, la conexión fue exitosa
                if self.working_tls_version != tls_name:
                    logger.info(f"✅ Conexión exitosa usando TLS {tls_name}")
                    self.working_tls_version = tls_name
                    self.working_session = session
                
                return response, tls_name
                
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                last_error = e
                logger.debug(f"⚠️ TLS {tls_name} falló: {str(e)[:100]}")
                continue
            except Exception as e:
                # Otros errores (timeout, etc.) no son problemas de TLS
                last_error = e
                logger.debug(f"⚠️ Error con TLS {tls_name}: {str(e)[:100]}")
                # Si no es un error de SSL, retornar el error
                if not isinstance(e, (requests.exceptions.SSLError, requests.exceptions.ConnectionError)):
                    raise
        
        # Si todos los intentos con requests fallaron, intentar con curl como último recurso
        logger.warning("⚠️ Todos los intentos con requests fallaron, intentando con curl...")
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
                headers={"Content-Type": "application/json"}
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
                    self.session_expires = datetime.now() + timedelta(minutes=25)
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
                except:
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
            logger.error("❌ No se pudo establecer sesión con SAP Service Layer")
            return None
        
        try:
            url = f"{self.base_url}/PurchaseOrders"
            headers = {
                "Content-Type": "application/json",
                "Cookie": f"B1SESSION={self.session_id}",
            }
            logger.info(f"📤 POST {url} (Purchase Orders)")
            logger.debug(f"   Request: {json.dumps(purchase_order_data, ensure_ascii=False, default=str)[:2500]}")
            
            # Usar sesión existente si está disponible, sino usar fallback
            if self.working_session:
                response = self.working_session.post(
                    url,
                    json=purchase_order_data,
                    headers=headers,
                    timeout=self.timeout
                )
            else:
                # Usar sistema de fallback TLS
                response, _ = self._try_request_with_fallback(
                    "POST",
                    url,
                    json=purchase_order_data,
                    headers=headers
                )
                
                if response is None:
                    logger.error("❌ No se pudo establecer conexión con SAP Service Layer")
                    return {
                        "success": False,
                        "error": "No se pudo establecer conexión con SAP Service Layer"
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
            logger.error("❌ No se pudo establecer sesión con SAP Service Layer")
            return None
        
        try:
            # ⚠️ CORRECCIÓN CRÍTICA: Usar endpoint correcto de Service Layer
            url = f"{self.base_url}/InventoryTransferRequests"
            headers = {
                "Content-Type": "application/json",
                "Cookie": f"B1SESSION={self.session_id}"
            }
            
            logger.info(f"📤 POST {url} (Inventory Transfer Requests)")
            logger.debug(f"   Request: {json.dumps(stock_transfer_data, ensure_ascii=False, default=str)[:1500]}")
            
            # Usar sesión existente si está disponible, sino usar fallback
            if self.working_session:
                response = self.working_session.post(
                    url,
                    json=stock_transfer_data,
                    headers=headers,
                    timeout=self.timeout
                )
            else:
                # Usar sistema de fallback TLS
                response, _ = self._try_request_with_fallback(
                    "POST",
                    url,
                    json=stock_transfer_data,
                    headers=headers
                )
                
                if response is None:
                    logger.error("❌ No se pudo establecer conexión con SAP Service Layer")
                    return {
                        "success": False,
                        "error": "No se pudo establecer conexión con SAP Service Layer"
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
    
    def get_stock_by_warehouse(
        self, 
        item_code: str, 
        warehouse_code: str
    ) -> Optional[Dict[str, Any]]:
        """
        Consulta el stock disponible (InStock) y UomCode de un artículo en una bodega específica.
        
        ⭐ CORRECCIÓN: Usa navegación desde Items ya que el endpoint independiente no existe.
        SAP no permite filtrar dentro de la navegación, por lo que se filtra en el cliente.
        
        Usa el endpoint de SAP Service Layer:
        GET /Items('ITEM_CODE')/ItemWarehouseInfoCollection
        
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
            O None si hay error.
            Retorna {"InStock": 0.0, "UomCode": None} si no existe información de bodega.
        """
        if not self.enabled:
            logger.debug("⏭️ Consulta de stock deshabilitada")
            return None
        
        if not self._ensure_session():
            logger.error("❌ No se pudo establecer sesión con SAP Service Layer")
            return None
        
        try:
            # Escapar caracteres especiales para OData
            # SAP Service Layer requiere escapar comillas simples duplicándolas
            item_code_escaped = item_code.replace("'", "''")
            
            # ⭐ CORRECCIÓN: Usar navegación desde Items (el endpoint independiente no existe)
            # Endpoint correcto: /Items('ITEM_CODE')/ItemWarehouseInfoCollection
            # Nota: SAP no permite filtrar dentro de la navegación, por lo que filtramos en el cliente
            url = (
                f"{self.base_url}/Items('{item_code_escaped}')/ItemWarehouseInfoCollection"
            )
            
            headers = {
                "Content-Type": "application/json",
                "Cookie": f"B1SESSION={self.session_id}"
            }
            
            logger.debug(f"🔍 Consultando stock de {item_code} en {warehouse_code}...")
            
            # Usar el sistema de fallback TLS existente
            if self.working_session:
                response = self.working_session.get(url, headers=headers, timeout=self.timeout)
            else:
                response, _ = self._try_request_with_fallback("GET", url, headers=headers)
                if response is None:
                    logger.error("❌ No se pudo consultar stock en SAP")
                    return None
            
            if response.status_code == 200:
                data = response.json()
                
                # ⭐ AJUSTE: Service Layer SIEMPRE retorna objeto con "value" (array)
                warehouses = data.get("value", [])
                
                # 🔍 LOGGING COMPACTO: Solo información esencial
                bodegas_codes = [wh.get('WarehouseCode', 'N/A') for wh in warehouses] if warehouses else []
                logger.info(
                    f"🔍 {item_code} → ItemWarehouseInfoCollection: "
                    f"{'VACÍO' if not warehouses else f'{len(warehouses)} bodega(s)'} | "
                    f"WhsCodes: {bodegas_codes if bodegas_codes else 'NINGUNO'}"
                )
                
                # 🔍 LOGGING DETALLADO: Solo en modo DEBUG
                logger.debug(
                    f"📦 RESPUESTA CRUDA SAP para {item_code}: URL={url}, "
                    f"Keys={list(data.keys()) if isinstance(data, dict) else 'N/A'}, "
                    f"Respuesta completa={data}"
                )
                
                if not warehouses:
                    # ❌ CORTAR FLUJO: Lanzar excepción de dominio en lugar de retornar stock 0.0
                    # ❌ NO loguear aquí - se logueará una sola vez agrupado en el servicio
                    raise SAPDataMasterError(
                        item_code=item_code,
                        warehouse_code=warehouse_code,
                        error_type="no_warehouse_info",
                        available_warehouses=[]
                    )
                
                # ⭐ Filtrar en el cliente por WarehouseCode (SAP no permite filtro en navegación)
                warehouse_info = None
                bodegas_encontradas = []
                for wh in warehouses:
                    whs_code = wh.get("WarehouseCode", "")
                    bodegas_encontradas.append(whs_code)
                    if whs_code.upper() == warehouse_code.upper():
                        warehouse_info = wh
                        break
                
                # 🔍 LOGGING COMPACTO: Búsqueda de bodega específica
                logger.info(
                    f"🔍 {item_code} → Búsqueda {warehouse_code}: "
                    f"{'ENCONTRADA' if warehouse_info else 'NO ENCONTRADA'} | "
                    f"Disponibles: {bodegas_encontradas if bodegas_encontradas else 'NINGUNA'}"
                )
                
                if not warehouse_info:
                    # ❌ CORTAR FLUJO: Lanzar excepción de dominio en lugar de retornar stock 0.0
                    # ❌ NO loguear aquí - se logueará una sola vez agrupado en el servicio
                    raise SAPDataMasterError(
                        item_code=item_code,
                        warehouse_code=warehouse_code,
                        error_type="warehouse_not_found",
                        available_warehouses=bodegas_encontradas
                    )
                
                # 🔍 LOGGING COMPACTO: Información de bodega encontrada
                logger.info(
                    f"✅ {item_code} en {warehouse_code}: "
                    f"InStock={warehouse_info.get('InStock', 'N/A')}, "
                    f"Comprometido={warehouse_info.get('IsCommited', 'N/A')}, "
                    f"UomCode={warehouse_info.get('UomCode', 'NULL')}, "
                    f"Locked={warehouse_info.get('Locked', 'NULL')}"
                )
                
                # ⭐ AJUSTE: Calcular stock disponible descontando comprometido
                in_stock_raw = float(warehouse_info.get("InStock", 0))
                is_committed = float(warehouse_info.get("IsCommited", 0))
                in_stock = in_stock_raw - is_committed
                
                uom_code = warehouse_info.get("UomCode")  # Puede ser None
                locked = warehouse_info.get("Locked")  # tYES/tNO
                
                # 🔍 DIAGNÓSTICO: Análisis de UomCode (solo si es NULL)
                if uom_code is None:
                    logger.warning(
                        f"⚠️ {item_code}: UomCode=NULL - validación en unidades base"
                    )
                
                # ⭐ VALIDACIÓN: Verificar si está bloqueado
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
                    "InStock": in_stock,  # Stock disponible (descontando comprometido)
                    "UomCode": uom_code,
                    "WarehouseCode": warehouse_code,
                    "Locked": locked,
                    "IsCommited": is_committed
                }
            else:
                # 🔍 LOGGING DIAGNÓSTICO: Error HTTP de SAP
                logger.error(
                    f"❌ ERROR HTTP de SAP al consultar stock de {item_code}:\n"
                    f"   URL consultada: {url}\n"
                    f"   Status Code: {response.status_code}\n"
                    f"   Headers de respuesta: {dict(response.headers)}\n"
                    f"   Texto de respuesta (primeros 500 chars): {response.text[:500]}"
                )
                
                # Procesar error de SAP
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
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error de conexión al consultar stock: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado al consultar stock de {item_code} en {warehouse_code}: {e}", exc_info=True)
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
