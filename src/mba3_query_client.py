"""
Aplicación para consumir la API de MBA3 (4D) con autenticación Digest.

Realiza consultas a la base de datos mediante peticiones POST.

Según la documentación, se requiere primero hacer LOGIN para obtener un JWT (sesión).

"""

import requests
from requests.auth import HTTPDigestAuth
import json
import logging
import time
import re
from typing import Dict, Any, Optional, Union, List
from src.mba3_client import MBA3Client
from src.exceptions import MBA3QueryError, MBA3ConnectionError
from src.config import ENVIRONMENT

logger = logging.getLogger(__name__)

# Timeouts: conexión corta para fallar rápido si MBA3 no está disponible; lectura larga para consultas pesadas
MBA3_CONNECT_TIMEOUT = 10  # segundos para establecer conexión (evita colgar cuando el servidor no responde)
MBA3_READ_TIMEOUT = 90     # segundos para leer respuesta (consultas grandes)
_NO_SERVER_RESPONSE = "Sin respuesta del servidor"


class MBA3APIClient:
    """Cliente para interactuar con la API de MBA3 (4D)."""

    def __init__(self, base_url: str, service_code: str, service_password: str,
                 digest_username: Optional[str] = None, digest_password: Optional[str] = None):
        """
        Inicializa el cliente de API.

        Args:
            base_url: URL base de la API
            service_code: Código del servicio (código) para el LOGIN
            service_password: Contraseña del servicio (pwd) para el LOGIN
            digest_username: Usuario para autenticación Digest (opcional)
            digest_password: Contraseña para autenticación Digest (opcional)
        """
        self.base_url = base_url.rstrip('/')
        self.service_code = service_code
        self.service_password = service_password
        self.jwt_token = None
        self.session = requests.Session()
        self.last_login_time = None  # Rastrear cuándo se hizo el último login

        # Si se proporcionan credenciales Digest, configurarlas
        if digest_username and digest_password:
            self.session.auth = HTTPDigestAuth(digest_username, digest_password)

        # Usar el cliente de login que ya funciona
        self.login_client = MBA3Client(base_url)

    def login(self) -> bool:
        """
        Realiza el LOGIN para obtener el JWT (sesión) usando el método de mba3_client.py.

        Returns:
            True si el login fue exitoso, False en caso contrario
        """
        try:
            logger.info("Intentando hacer LOGIN usando el método de mba3_client...")
            token = self.login_client.login(self.service_code, self.service_password)
            if token:
                self.jwt_token = token
                self.last_login_time = time.time()
                if ENVIRONMENT == "development":
                    logger.debug(f"Login exitoso. JWT obtenido (primeros 20 caracteres): {self.jwt_token[:20]}...")
                else:
                    logger.info("Login exitoso. JWT obtenido")
                return True
            return False
        except Exception as e:
            logger.error(f"No se pudo hacer login: {e}")
            return False

    def _wait_for_fresh_jwt(self) -> None:
        """Espera si el JWT fue obtenido hace menos de 5 segundos para que MBA3 lo procese."""
        if self.jwt_token and self.last_login_time:
            time_since_login = time.time() - self.last_login_time
            if time_since_login < 5.0:
                wait_time = 5.0 - time_since_login
                logger.info(
                    f"⏳ JWT reciente (obtenido hace {time_since_login:.1f}s). "
                    f"Esperando {wait_time:.1f} segundos adicionales para que MBA3 lo procese..."
                )
                time.sleep(wait_time)

    def _parse_sql_to_form_data(self, query: str) -> dict:
        """Parsea una consulta SQL y devuelve el form_data para la API de MBA3."""
        from_table, select_fields, where_clause, order_by_clause, limit_value = self._parsear_clausulas_sql(query)
        if not from_table:
            error_msg = "No se pudo determinar la tabla desde la consulta SQL. Usa el formato: select * from clnt_factura_principal"
            logger.error(error_msg)
            raise MBA3QueryError(error_msg)
        return self._construir_form_data(select_fields, from_table, where_clause, order_by_clause, limit_value)

    def _parsear_clausulas_sql(self, query: str) -> tuple:
        """Extrae las cláusulas SQL (SELECT, FROM, WHERE, ORDER BY, LIMIT) de la query."""
        select_fields = "*"
        from_table = None
        where_clause = None
        order_by_clause = None
        limit_value = None
        if not query:
            return from_table, select_fields, where_clause, order_by_clause, limit_value
        query_upper = query.upper().strip()
        query_original = query.strip()
        if "SELECT" not in query_upper or "FROM" not in query_upper:
            return from_table, select_fields, where_clause, order_by_clause, limit_value
        select_idx = query_upper.find("SELECT")
        from_idx = query_upper.find("FROM")
        select_fields = self._extraer_select_fields(query_original, select_idx, from_idx)
        from_start = from_idx + 4
        from_rest_upper = query_upper[from_start:]
        from_rest_original = query_original[from_start:]
        where_pos = from_rest_upper.find(" WHERE ")
        order_by_pos = from_rest_upper.find(" ORDER BY ")
        limit_pos = from_rest_upper.find(" LIMIT ")
        from_table = self._extraer_tabla_from(from_rest_original, where_pos, order_by_pos, limit_pos)
        where_clause = self._extraer_where_clause(from_rest_original, where_pos, order_by_pos, limit_pos)
        order_by_clause = self._extraer_order_by_clause(from_rest_original, order_by_pos, limit_pos)
        limit_value = self._extraer_limit_value(from_rest_original, limit_pos)
        return from_table, select_fields, where_clause, order_by_clause, limit_value

    def _extraer_select_fields(self, query_original: str, select_idx: int, from_idx: int) -> str:
        """Extrae y normaliza el fragmento SELECT entre las palabras clave SELECT y FROM."""
        select_part = query_original[select_idx + 6:from_idx].strip()
        logger.debug(f"SELECT original parseado: '{select_part}'")
        if not select_part:
            return "*"
        select_fields = re.sub(r'\s+', ' ', select_part).strip()
        select_fields = re.sub(r',\s+', ',', select_fields)
        logger.debug(f"SELECT normalizado: '{select_fields}'")
        return select_fields

    def _extraer_tabla_from(self, from_rest_original: str, where_pos: int, order_by_pos: int, limit_pos: int) -> str:
        """Extrae el nombre de la tabla desde la porción de query después de FROM."""
        table_end = len(from_rest_original)
        if where_pos >= 0:
            table_end = where_pos
        elif order_by_pos >= 0:
            table_end = order_by_pos
        elif limit_pos >= 0:
            table_end = limit_pos
        return from_rest_original[:table_end].strip()

    def _extraer_where_clause(self, from_rest_original: str, where_pos: int,
                               order_by_pos: int, limit_pos: int) -> Optional[str]:
        """Extrae la cláusula WHERE si existe."""
        if where_pos < 0:
            return None
        where_start = where_pos + 7
        where_rest = from_rest_original[where_start:]
        where_end = len(where_rest)
        if order_by_pos >= 0 and order_by_pos > where_pos:
            where_end = order_by_pos - where_pos - 7
        elif limit_pos >= 0 and limit_pos > where_pos:
            where_end = limit_pos - where_pos - 7
        return where_rest[:where_end].strip()

    def _extraer_order_by_clause(self, from_rest_original: str, order_by_pos: int, limit_pos: int) -> Optional[str]:
        """Extrae la cláusula ORDER BY si existe."""
        if order_by_pos < 0:
            return None
        order_by_start = order_by_pos + 10
        order_by_rest = from_rest_original[order_by_start:]
        order_by_end = len(order_by_rest)
        if limit_pos >= 0 and limit_pos > order_by_pos:
            order_by_end = limit_pos - order_by_pos - 10
        return order_by_rest[:order_by_end].strip()

    def _extraer_limit_value(self, from_rest_original: str, limit_pos: int) -> Optional[str]:
        """Extrae el valor LIMIT si existe."""
        if limit_pos < 0:
            return None
        limit_rest = from_rest_original[limit_pos + 7:]
        return limit_rest.strip().split()[0] if limit_rest.strip() else None

    def _construir_form_data(self, select_fields: str, from_table: str, where_clause: Optional[str],
                              order_by_clause: Optional[str], limit_value: Optional[str]) -> dict:
        """Valida los campos parseados y construye el dict form_data para la API de MBA3."""
        logger.info(f"Ejecutando consulta - Tabla: {from_table}, SELECT: {select_fields}, WHERE: {where_clause or 'N/A'}")
        logger.info(f"🔍 Campo SELECT que se envía a MBA3: '{select_fields}' (longitud: {len(select_fields)})")
        if not select_fields or select_fields.strip() == "":
            logger.warning("⚠️ Campo 'select' está vacío, usando '*' por defecto")
            select_fields = "*"
        if not from_table or from_table.strip() == "":
            error_msg = "No se pudo determinar la tabla desde la consulta SQL. Campo 'from' está vacío."
            logger.error(error_msg)
            raise MBA3QueryError(error_msg)
        form_data: dict = {'select': select_fields, 'from': from_table}
        if where_clause:
            form_data['where'] = where_clause
        if order_by_clause:
            form_data['orderBy'] = order_by_clause
        if limit_value:
            form_data['limit'] = limit_value
        return form_data

    def _build_auth_headers(self) -> dict:
        """Construye los headers de autenticación con el JWT actual."""
        headers: dict = {}
        if self.jwt_token:
            headers['Authorization'] = self.jwt_token
            if ENVIRONMENT == "development":
                logger.debug(f"JWT presente en headers (primeros 20 caracteres): {self.jwt_token[:20]}...")
            else:
                logger.debug("JWT presente en headers")
            if not self.jwt_token.strip():
                logger.error("⚠️ JWT está vacío, intentando obtener nuevo JWT...")
                if not self.login():
                    logger.error("❌ No se pudo obtener nuevo JWT")
                else:
                    headers['Authorization'] = self.jwt_token
                    logger.info("✅ Nuevo JWT obtenido")
        else:
            logger.warning("⚠️ No hay JWT disponible para esta consulta")
        return headers

    def _extract_json_from_response(self, response_text: str):
        """Intenta extraer JSON válido de una respuesta que puede contener texto adicional."""
        text = response_text.strip()
        start_idx = -1
        start_char = None
        for i, char in enumerate(text):
            if char in ['[', '{']:
                start_idx = i
                start_char = char
                break
        if start_idx == -1:
            return None
        end_char = ']' if start_char == '[' else '}'
        depth = 0
        end_idx = -1
        for i in range(start_idx, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break
        if end_idx == -1:
            return None
        try:
            json_text = text[start_idx:end_idx + 1]
            result = json.loads(json_text)
            logger.info(
                f"✅ JSON válido extraído de respuesta con texto adicional "
                f"(extraído {len(json_text)} chars de {len(text)} totales)"
            )
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"No se pudo parsear JSON extraído: {e}")
            return None

    def _handle_200_response(self, response):
        """Parsea una respuesta HTTP 200 y devuelve el resultado."""
        try:
            result = response.json()
            logger.info("Consulta exitosa!")
            if isinstance(result, list):
                self._log_list_response(result)
            elif isinstance(result, dict):
                self._log_dict_response(result)
            return result
        except json.JSONDecodeError:
            logger.warning(f"La respuesta no es JSON válido. Respuesta recibida: {response.text[:500]}")
            extracted = self._extract_json_from_response(response.text)
            if extracted is not None:
                return extracted
            return {'raw_response': response.text}

    def _log_list_response(self, result: list) -> None:
        """Registra en debug los metadatos de una respuesta de tipo lista."""
        logger.debug(f"Respuesta es lista con {len(result)} elementos")
        if result:
            logger.debug(f"Primer elemento tipo: {type(result[0])}")
            if isinstance(result[0], dict):
                campos = list(result[0].keys())
                logger.debug(f"Campos en primer elemento: {campos} ({len(campos)} campos)")
                logger.debug(f"Muestra del primer elemento (primeros 500 chars): {str(result[0])[:500]}")

    def _log_dict_response(self, result: dict) -> None:
        """Registra en debug los metadatos de una respuesta de tipo diccionario."""
        logger.debug(f"Respuesta es diccionario con claves: {list(result.keys())}")
        logger.debug(f"Muestra del diccionario (primeros 500 chars): {str(result)[:500]}")
        for key, value in result.items():
            if isinstance(value, list) and value:
                logger.debug(f"Encontrada lista en clave '{key}' con {len(value)} elementos")
                if isinstance(value[0], dict):
                    campos = list(value[0].keys())
                    logger.debug(f"Campos en primer elemento de '{key}': {campos} ({len(campos)} campos)")
                    logger.debug(f"Muestra del primer elemento de '{key}' (primeros 500 chars): {str(value[0])[:500]}")

    def _handle_401_response(self, response, url: str, form_data: dict, headers: dict):
        """Maneja HTTP 401 intentando re-login y reintento de consulta."""
        if self.jwt_token:
            logger.info("Token inválido o expirado. Intentando login nuevamente...")
            if self.login():
                headers['Authorization'] = self.jwt_token
                response = self.session.post(
                    url,
                    data=form_data,
                    headers=headers,
                    timeout=(MBA3_CONNECT_TIMEOUT, 30)
                )
                if response.status_code == 200:
                    try:
                        return response.json()
                    except json.JSONDecodeError:
                        return {'raw_response': response.text}
        error_msg = f"Error 401 - No autorizado. Verifica tus credenciales. Respuesta: {response.text[:500]}"
        logger.error(error_msg)
        raise MBA3QueryError(error_msg)

    def _handle_500_response(self, response, query: str, url: str, form_data: dict, headers: dict):
        """Maneja HTTP 500 con lógica de reintento y re-login."""
        error_text = response.text.lower() if response.text else ""
        is_object_collection_error = "object or collection expected" in error_text
        max_retries = 3
        retry_delay = 3.0 if is_object_collection_error else 1
        if is_object_collection_error:
            logger.warning("⚠️ Detectado error 'Object or Collection Expected' - MBA3 necesita más tiempo para procesar el JWT")
        for retry_attempt in range(max_retries):
            logger.warning(f"Error 500 del servidor MBA3. Intento de recuperación {retry_attempt + 1}/{max_retries}...")
            if retry_attempt > 0:
                wait_time = retry_delay * (2 ** (retry_attempt - 1))
                logger.info(f"Esperando {wait_time} segundos antes del siguiente intento...")
                time.sleep(wait_time)
            resultado, retry_delay = self._intentar_reintento_500(
                response, query, url, form_data, headers,
                retry_attempt, max_retries, is_object_collection_error, retry_delay
            )
            if resultado is not None:
                return resultado
        error_detail = response.text[:1000] if response.text else _NO_SERVER_RESPONSE
        raise MBA3QueryError(
            f"Error HTTP 500 persistente en MBA3 después de {max_retries} intentos.\n"
            f"Consulta: {query}\n"
            f"Respuesta del servidor: {error_detail}\n\n"
            f"Esto indica un problema en el servidor MBA3."
        )

    def _esperar_post_login(self, is_object_collection_error: bool) -> None:
        """Espera si el JWT acaba de obtenerse para que MBA3 lo procese antes de reintentar."""
        if is_object_collection_error or (self.last_login_time and (time.time() - self.last_login_time) < 2):
            wait_after_login = 3.0 if is_object_collection_error else 2.0
            logger.info(f"⏳ Esperando {wait_after_login} segundos después del login para que MBA3 procese el JWT...")
            time.sleep(wait_after_login)

    def _manejar_500_en_reintento(self, response, query: str, retry_attempt: int,
                                   max_retries: int, retry_delay: float) -> float:
        """Procesa status 500 recibido durante un reintento. Returns nuevo retry_delay. Raises en último intento."""
        new_error_text = response.text.lower() if response.text else ""
        is_still_object_error = "object or collection expected" in new_error_text
        logger.warning(f"Intento {retry_attempt + 1} falló con 500. Continuando...")
        if retry_attempt == max_retries - 1:
            error_detail = response.text[:1000] if response.text else _NO_SERVER_RESPONSE
            raise MBA3QueryError(
                f"Error HTTP 500 persistente en MBA3 después de {max_retries} intentos de recuperación.\n"
                f"Consulta: {query}\n"
                f"Respuesta del servidor: {error_detail}\n\n"
                f"Esto indica un problema en el servidor MBA3, no en la autenticación."
            )
        return 5.0 if is_still_object_error else retry_delay

    def _intentar_reintento_500(self, response, query: str, url: str, form_data: dict, headers: dict,
                                 retry_attempt: int, max_retries: int,
                                 is_object_collection_error: bool, retry_delay: float) -> tuple:
        """Ejecuta un ciclo de re-login + re-consulta para recuperarse de un error 500.
        Returns (result, retry_delay); result=None indica continuar el loop de reintentos."""
        if not self.login():
            logger.warning(f"No se pudo hacer login en intento {retry_attempt + 1}")
            if retry_attempt == max_retries - 1:
                error_detail = response.text[:1000] if response.text else _NO_SERVER_RESPONSE
                raise MBA3QueryError(
                    f"Error HTTP 500 al ejecutar consulta en MBA3.\n"
                    f"Consulta: {query}\n"
                    f"Respuesta del servidor: {error_detail}\n\n"
                    f"No se pudo hacer login después de {max_retries} intentos."
                )
            return None, retry_delay
        headers['Authorization'] = self.jwt_token
        self._esperar_post_login(is_object_collection_error)
        logger.info(f"Login exitoso. Reintentando consulta (intento {retry_attempt + 1}/{max_retries})...")
        response = self.session.post(url, data=form_data, headers=headers, timeout=(MBA3_CONNECT_TIMEOUT, 30))
        if response.status_code == 200:
            logger.info(f"✅ Consulta exitosa después del reintento {retry_attempt + 1}")
            return self._handle_200_response(response), retry_delay
        if response.status_code == 500:
            new_delay = self._manejar_500_en_reintento(response, query, retry_attempt, max_retries, retry_delay)
            return None, new_delay
        error_detail = response.text[:1000] if response.text else _NO_SERVER_RESPONSE
        raise MBA3QueryError(
            f"Error HTTP {response.status_code} al ejecutar consulta en MBA3 después de reintento.\n"
            f"Consulta: {query}\n"
            f"Respuesta del servidor: {error_detail}"
        )

    def _handle_connection_error(self, e: Exception) -> None:
        error_msg = (
            f"No se pudo conectar al servidor MBA3 en {self.base_url}.\n"
            f"Error: {str(e)}\n\n"
            f"Posibles causas:\n"
            f"- El servidor MBA3 no está disponible o no está ejecutándose\n"
            f"- El servidor está en una red diferente o no es accesible desde este equipo\n"
            f"- Verifica la configuración de MBA3_BASE_URL en tu archivo .env\n"
            f"- Verifica que el firewall permita la conexión al puerto {self.base_url.split(':')[-1] if ':' in self.base_url else '8081'}"
        )
        logger.error(error_msg, exc_info=True)
        raise MBA3ConnectionError(error_msg)

    def _handle_timeout_error(self, e: Exception) -> None:
        error_msg = (
            f"Timeout al conectar con el servidor MBA3 en {self.base_url}.\n"
            f"El servidor no respondió a tiempo.\n\n"
            f"Posibles causas:\n"
            f"- El servidor está sobrecargado\n"
            f"- Problemas de red\n"
            f"- El servidor está inactivo o no responde"
        )
        logger.error(error_msg, exc_info=True)
        raise MBA3ConnectionError(error_msg)

    def _handle_http_exception(self, e: Exception) -> None:
        error_detail = ""
        if hasattr(e, 'response') and getattr(e, 'response'):
            resp_text = getattr(e.response, 'text', '')
            error_detail = resp_text[:1000] if resp_text else "Sin respuesta"
        error_msg = f"Error HTTP al comunicarse con MBA3: {str(e)}. Respuesta: {error_detail}"
        logger.error(error_msg, exc_info=True)
        raise MBA3QueryError(error_msg)

    def _handle_request_exception(self, e: Exception) -> None:
        error_str = str(e).lower()
        if any(keyword in error_str for keyword in ['connection', 'refused', 'unreachable', 'no connection', 'failed to establish']):
            error_msg = (
                f"No se pudo conectar al servidor MBA3 en {self.base_url}.\n"
                f"Error: {str(e)}\n\n"
                f"Verifica que el servidor MBA3 esté disponible y accesible."
            )
            logger.error(error_msg, exc_info=True)
            raise MBA3ConnectionError(error_msg)
        else:
            error_msg = f"Error en la petición a MBA3: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise MBA3QueryError(error_msg)

    def _do_request(self, query: str, url: str, form_data: dict, headers: dict):
        """Ejecuta la petición HTTP y despacha el manejo según el código de respuesta."""
        try:
            response = self.session.post(
                url,
                data=form_data,
                headers=headers,
                timeout=(MBA3_CONNECT_TIMEOUT, MBA3_READ_TIMEOUT)
            )
            return self._despachar_respuesta(response, query, url, form_data, headers)
        except MBA3QueryError:
            raise
        except requests.exceptions.ConnectionError as e:
            self._handle_connection_error(e)
        except requests.exceptions.Timeout as e:
            self._handle_timeout_error(e)
        except requests.exceptions.HTTPError as e:
            self._handle_http_exception(e)
        except requests.exceptions.RequestException as e:
            self._handle_request_exception(e)

    def _despachar_respuesta(self, response, query: str, url: str, form_data: dict, headers: dict):
        """Despacha la respuesta HTTP al handler correspondiente según el status code."""
        if response.status_code == 200:
            return self._handle_200_response(response)
        if response.status_code == 401:
            return self._handle_401_response(response, url, form_data, headers)
        if response.status_code == 500:
            return self._handle_500_response(response, query, url, form_data, headers)
        error_detail = response.text[:1000] if response.text else _NO_SERVER_RESPONSE
        error_msg = (
            f"Error HTTP {response.status_code} al ejecutar consulta en MBA3.\n"
            f"Consulta: {query}\n"
            f"Respuesta del servidor: {error_detail}"
        )
        logger.error(f"Error HTTP {response.status_code}")
        logger.error(f"Consulta enviada: {query}")
        logger.error(f"Form-data enviado: {form_data}")
        logger.error(f"Respuesta del servidor: {error_detail}")
        raise MBA3QueryError(error_msg)

    def execute_query(self, query: str, require_jwt: bool = True) -> Optional[Union[List[Any], Dict[Any, Any]]]:
        """
        Ejecuta una consulta SQL en la base de datos MBA3.
        Según la documentación, se debe incluir el JWT en el header SetRequestHeader.

        Args:
            query: Consulta SQL a ejecutar
            require_jwt: Si es True, intenta obtener JWT primero. Si es False, intenta sin JWT.

        Returns:
            Respuesta JSON de la API como lista o diccionario, o None si hay error
        """
        if require_jwt and not self.jwt_token:
            logger.info("No hay JWT disponible. Intentando hacer login...")
            if not self.login():
                logger.warning("No se pudo obtener JWT. Intentando consulta directa sin JWT...")
                return self.execute_query(query, require_jwt=False)
            logger.info("✅ JWT obtenido exitosamente")
            logger.info("⏳ Esperando 2.0 segundos después del login para que MBA3 procese el JWT...")
            time.sleep(2.0)

        self._wait_for_fresh_jwt()
        url = f"{self.base_url}/ws_Consulta_externa_MBA3/"
        form_data = self._parse_sql_to_form_data(query)
        logger.debug(f"URL: {url}")
        logger.debug(f"Form-data a enviar: {form_data}")
        headers = self._build_auth_headers()
        return self._do_request(query, url, form_data, headers)
