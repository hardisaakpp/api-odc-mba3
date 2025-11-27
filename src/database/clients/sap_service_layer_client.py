"""
Cliente para interactuar con SAP Business One Service Layer API.

Este cliente maneja la autenticación y el envío de órdenes de compra (Purchase Orders)
a SAP Business One usando Service Layer REST API.
"""

import logging
import requests
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from config import (
    SAP_SERVICE_LAYER_URL,
    SAP_SERVICE_LAYER_USERNAME,
    SAP_SERVICE_LAYER_PASSWORD,
    SAP_SERVICE_LAYER_DATABASE,
    ENABLE_SAP_SERVICE_LAYER,
    SAP_SERVICE_LAYER_TIMEOUT
)

logger = logging.getLogger(__name__)


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
        
        if not self.enabled:
            logger.warning("⚠️ SAP Service Layer deshabilitado (ENABLE_SAP_SERVICE_LAYER=False)")
        elif not self.username or not self.password:
            logger.warning("⚠️ Credenciales de SAP Service Layer no configuradas")
    
    def _is_session_valid(self) -> bool:
        """Verifica si la sesión actual es válida."""
        if not self.session_id:
            return False
        if not self.session_expires:
            return False
        # Renovar sesión si expira en menos de 5 minutos
        return datetime.now() < (self.session_expires - timedelta(minutes=5))
    
    def login(self) -> bool:
        """
        Autentica con SAP Service Layer y obtiene un session ID.
        
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
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                # Extraer session ID de las cookies
                session_cookie = response.cookies.get('B1SESSION')
                if session_cookie:
                    self.session_id = session_cookie
                    # Las sesiones de SAP suelen durar 30 minutos
                    self.session_expires = datetime.now() + timedelta(minutes=25)
                    logger.info("✅ Autenticación exitosa con SAP Service Layer")
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
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error de conexión al autenticar con SAP Service Layer: {e}")
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
                "Cookie": f"B1SESSION={self.session_id}"
            }
            
            logger.info(f"📤 Enviando Purchase Order a SAP Service Layer...")
            logger.debug(f"   URL: {url}")
            logger.debug(f"   Datos: {purchase_order_data}")
            
            response = requests.post(
                url,
                json=purchase_order_data,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                doc_entry = result.get("DocEntry")
                doc_num = result.get("DocNum")
                logger.info(f"✅ Purchase Order creada exitosamente en SAP: DocEntry={doc_entry}, DocNum={doc_num}")
                return {
                    "success": True,
                    "doc_entry": doc_entry,
                    "doc_num": doc_num,
                    "data": result
                }
            else:
                error_msg = f"Error al crear Purchase Order: {response.status_code}"
                try:
                    error_body = response.json()
                    error_detail = error_body.get("error", {})
                    error_msg = error_detail.get("message", {}).get("value", error_msg)
                    error_code = error_detail.get("code", "")
                    logger.error(f"❌ {error_msg} (Código: {error_code})")
                except:
                    error_msg = f"{error_msg} - {response.text}"
                    logger.error(f"❌ {error_msg}")
                
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code
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
            
            response = requests.post(url, headers=headers, timeout=self.timeout)
            
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


