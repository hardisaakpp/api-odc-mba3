# src/mba3_client.py
import requests
import json
import logging
from typing import Optional, Union
from src.exceptions import MBA3ConnectionError

# Configurar logging básico similar a la versión anterior
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class MBA3Client:
    """
    Cliente para obtener JWT (sesión) de los Servicios de Acceso Externo de MBA3.
    
    Según documentación:
    - Login requiere: código (código del servicio) y pwd (contraseña del servicio)
    - Respuesta devuelve JWT que debe usarse en todas las peticiones
    - Cada servicio tiene su propio LOGIN y genera una sesión única
    """
    
    def __init__(self, base_url: str):
        """
        Inicializa el cliente MBA3
        
        Args:
            base_url: URL base del servidor MBA3 (ej: https://tu-servidor.mba3.com)
        """
        if not base_url:
            raise ValueError("base_url no puede estar vacío")
        self.base_url = base_url.rstrip('/')
        self.token: Optional[str] = None
        logger.info(f"Cliente MBA3 inicializado con URL: {self.base_url}")

    def _extract_token(self, resp_json: Union[dict, str]) -> Optional[str]:
        """
        Extrae el JWT de la respuesta del servidor.
        
        Según documentación, el JWT viene en la respuesta del login.
        Intenta varios formatos comunes.
        
        Args:
            resp_json: Respuesta del servidor, puede ser un diccionario o un string
        """
        # El JWT puede venir directamente como string o en un campo
        if isinstance(resp_json, str):
            return resp_json
        
        # Intenta campos comunes
        for key in ("jwt", "token", "access_token", "session"):
            if key in resp_json:
                value = resp_json[key]
                if isinstance(value, str):
                    logger.debug(f"JWT encontrado en campo '{key}'")
                    return value
        
        # A veces viene dentro de "data"
        data = resp_json.get("data")
        if isinstance(data, dict):
            for key in ("jwt", "token", "access_token", "session"):
                if key in data:
                    value = data[key]
                    if isinstance(value, str):
                        logger.debug(f"JWT encontrado en data.{key}")
                        return value
        
        # Si la respuesta es directamente el JWT como string en un campo de texto
        if "response" in resp_json:
            resp_value = resp_json["response"]
            if isinstance(resp_value, str) and len(resp_value) > 50:  # JWT típicamente es largo
                return resp_value
        
        return None

    def login(self, codigo: str, pwd: str, timeout: int = 10) -> str:
        """
        Crea un LOGIN y obtiene el JWT (sesión).
        
        Según documentación:
        - Credenciales: código (código del servicio), pwd (contraseña del servicio)
        - Si los datos son correctos, regresa un JWT (sesión)
        - Cada servicio debe tener un LOGIN, cada Login genera una sesión única
        
        Args:
            codigo: Código del servicio configurado en MBA3
            pwd: Contraseña del servicio
            timeout: Timeout en segundos
            
        Returns:
            JWT (sesión) como string
            
        Raises:
            ValueError: Si no se encuentra el token en la respuesta
            requests.RequestException: Si hay error en la petición HTTP
        """
        url = f"{self.base_url}/login_Servicio"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MBA3-Client/1.0",
            "Cache-Control": "no-cache",
        }
        
        # Probar formatos básicos
        payloads_to_try = [
            {"codigo": codigo, "pwd": pwd},
            {"código": codigo, "pwd": pwd},  # Con tilde
        ]
        
        print("\n============================================================")
        print("PASO 1: Creando LOGIN para obtener JWT (sesión)")
        logger.info(f"🔐 Intentando login con código: {codigo[:3]}***")
        
        last_error = None
        
        for i, payload in enumerate(payloads_to_try, 1):
            try:
                logger.debug(f"Intento {i}/{len(payloads_to_try)}: Enviando payload con campos: {list(payload.keys())}")

                # CONVERTIR a JSON string y calcular longitud EXPLÍCITAMENTE
                json_payload = json.dumps(payload, ensure_ascii=False)
                headers["Content-Length"] = str(len(json_payload.encode('utf-8')))

                resp = requests.post(
                    url,
                    data=json_payload,
                    headers=headers,
                    timeout=timeout
                )
                
                logger.debug(f"Status code: {resp.status_code}")
                
                try:
                    body = resp.json()
                    logger.debug(f"Response recibida (tipo: JSON)")
                except Exception:
                    body = resp.text
                    logger.debug(f"Response recibida (tipo: texto)")
                
                if resp.status_code != 200:
                    error_msg = f"Status {resp.status_code}"
                    if isinstance(body, dict):
                        error_msg = body.get("error", body.get("message", str(body)))
                    elif isinstance(body, str):
                        error_msg = body
                    raise ValueError(f"Error en login: {error_msg}")
                
                resp.raise_for_status()
                
                # Manejo de errores específicos
                if isinstance(body, dict) and "error" in body:
                    error_code = body.get("error", "Error desconocido")
                    error_respuesta = body.get("respuesta", "")
                    
                    if error_code == "005" or "No existe configuración de Servicio WEB" in error_respuesta:
                        if i < len(payloads_to_try):
                            logger.warning(f"Error 005 en intento {i}, probando siguiente formato...")
                            continue
                        else:
                            raise ValueError(
                                "❌ Error 005: No existe configuración de Servicio WEB\n\n"
                                "El servidor no encuentra un servicio configurado con las credenciales proporcionadas.\n\n"
                                "VERIFICA EN MBA3:\n"
                                "1. Ve a: Administrador del Sistema > Parámetros > Parámetros Empresa > Parámetros > Acceso Externo\n"
                                "2. Verifica que existe un servicio con:\n"
                                f"   - Código exacto: '{codigo}'\n"
                                f"   - Contraseña exacta: (la que configuraste)\n"
                                "3. Verifica que el servicio está ACTIVO\n"
                                "4. Verifica que el servicio es de tipo 'Consultas Externas' o 'API'\n"
                                "5. Verifica que el usuario asociado tiene licencia empresarial\n\n"
                                "VERIFICA EN TU .env:\n"
                                f"   - MBA3_CODIGO debe ser exactamente: '{codigo}'\n"
                                f"   - MBA3_PWD debe coincidir exactamente con la contraseña del servicio\n"
                                "   - No debe haber espacios extra al inicio o final\n"
                                "   - Respeta mayúsculas/minúsculas\n"
                            )
                    
                    error_msg = f"{error_code}" + (f": {error_respuesta}" if error_respuesta else "")
                    raise ValueError(f"Error en login: {error_msg}")
                
                # Extraer token
                token = self._extract_token(body)
                if not token:
                    if i < len(payloads_to_try):
                        continue
                    raise ValueError(
                        f"No se encontró JWT en la respuesta.\n"
                        f"Respuesta recibida: {json.dumps(body, indent=2, ensure_ascii=False) if isinstance(body, dict) else body}\n"
                        f"Verifica que el servicio esté configurado correctamente."
                    )
                
                self.token = token
                logger.info("✅ Login exitoso, JWT obtenido")
                logger.info(f"JWT (primeros 50 caracteres): {token[:50]}...")
                return token
                
            except requests.exceptions.ConnectionError as e:
                error_msg = (
                    f"No se pudo conectar al servidor MBA3 en {url}.\n"
                    f"Error: {str(e)}\n\n"
                    f"Posibles causas:\n"
                    f"- El servidor MBA3 no está disponible o no está ejecutándose\n"
                    f"- El servidor está en una red diferente o no es accesible desde este equipo\n"
                    f"- Verifica la configuración de MBA3_BASE_URL en tu archivo .env\n"
                    f"- Verifica que el firewall permita la conexión"
                )
                logger.error(error_msg, exc_info=True)
                raise MBA3ConnectionError(error_msg)
            except requests.exceptions.Timeout as e:
                error_msg = (
                    f"Timeout al conectar con el servidor MBA3 en {url}.\n"
                    f"El servidor no respondió a tiempo.\n\n"
                    f"Posibles causas:\n"
                    f"- El servidor está sobrecargado\n"
                    f"- Problemas de red\n"
                    f"- El servidor está inactivo o no responde"
                )
                logger.error(error_msg, exc_info=True)
                raise MBA3ConnectionError(error_msg)
            except requests.exceptions.HTTPError as e:
                logger.error(f"Error HTTP en login (intento {i}): {e}")
                if e.response is not None:
                    status = e.response.status_code
                    if status == 401:
                        raise ValueError("Credenciales inválidas. Verifica código y contraseña.")
                    elif status == 403:
                        raise ValueError("IP vetada. Tu IP ha sido bloqueada.")
                    elif status == 429:
                        raise ValueError("Demasiadas peticiones. Has excedido el límite.")
                
                if i == len(payloads_to_try):
                    raise
                continue
                
            except ValueError as e:
                raise
            except MBA3ConnectionError:
                # Re-lanzar errores de conexión sin modificar
                raise
            except Exception as e:
                # Verificar si es un error de conexión por el mensaje
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ['connection', 'refused', 'unreachable', 'no connection', 'failed to establish']):
                    error_msg = (
                        f"No se pudo conectar al servidor MBA3 en {url}.\n"
                        f"Error: {str(e)}\n\n"
                        f"Verifica que el servidor MBA3 esté disponible y accesible."
                    )
                    logger.error(error_msg, exc_info=True)
                    raise MBA3ConnectionError(error_msg)
                logger.error(f"Error inesperado en intento {i}: {e}")
                if i == len(payloads_to_try):
                    raise
                continue
        
        raise ValueError(f"Error en login después de {len(payloads_to_try)} intentos")

    def is_logged_in(self) -> bool:
        """Verifica si hay una sesión activa (JWT almacenado)"""
        return self.token is not None
