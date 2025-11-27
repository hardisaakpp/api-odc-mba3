"""
Aplicación para consumir la API de MBA3 (4D) con autenticación Digest.

Realiza consultas a la base de datos mediante peticiones POST.

Según la documentación, se requiere primero hacer LOGIN para obtener un JWT (sesión).

"""

import requests
from requests.auth import HTTPDigestAuth
import json
import logging
from typing import Dict, Any, Optional
from mba3_client import MBA3Client
from exceptions import MBA3QueryError

logger = logging.getLogger(__name__)


class MBA3APIClient:
    """Cliente para interactuar con la API de MBA3 (4D)."""
    
    def __init__(self, base_url: str, service_code: str, service_password: str, 
                 digest_username: str = None, digest_password: str = None):
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
                logger.info(f"Login exitoso. JWT obtenido (primeros 50 caracteres): {self.jwt_token[:50]}...")
                return True
            return False
        except Exception as e:
            logger.error(f"No se pudo hacer login: {e}")
            return False
    
    def execute_query(self, query: str, require_jwt: bool = True) -> Optional[Dict[Any, Any]]:
        """
        Ejecuta una consulta SQL en la base de datos MBA3.
        Según la documentación, se debe incluir el JWT en el header SetRequestHeader.
        
        Args:
            query: Consulta SQL a ejecutar
            require_jwt: Si es True, intenta obtener JWT primero. Si es False, intenta sin JWT.
            
        Returns:
            Respuesta JSON de la API como diccionario, o None si hay error
        """
        # Si require_jwt es True y no hay JWT, intentar hacer login primero
        if require_jwt and not self.jwt_token:
            if not self.login():
                logger.warning("No se pudo obtener JWT. Intentando consulta directa sin JWT...")
                # Intentar sin JWT (el Digest Auth podría ser suficiente)
                return self.execute_query(query, require_jwt=False)
        
        url = f"{self.base_url}/ws_Consulta_externa_MBA3/"
        
        # Parsear la consulta SQL si se proporciona como string completo
        # Formato esperado: "select campo1,campo2 from tabla where condicion order by campo limit 10"
        select_fields = "*"
        from_table = None
        where_clause = None
        order_by_clause = None
        limit_value = None
        
        if query:
            query_upper = query.upper().strip()
            query_original = query.strip()
            
            if "SELECT" in query_upper and "FROM" in query_upper:
                # Parsear SELECT - usar original para preservar mayúsculas/minúsculas
                select_idx = query_upper.find("SELECT")
                from_idx = query_upper.find("FROM")
                select_part = query_original[select_idx + 6:from_idx].strip()
                select_fields = select_part if select_part else "*"
                
                # Parsear FROM - usar original para preservar mayúsculas/minúsculas
                from_start = from_idx + 4
                from_rest_upper = query_upper[from_start:]
                from_rest_original = query_original[from_start:]
                
                # Encontrar posiciones de WHERE, ORDER BY, LIMIT en la parte después de FROM
                where_pos = from_rest_upper.find(" WHERE ")
                order_by_pos = from_rest_upper.find(" ORDER BY ")
                limit_pos = from_rest_upper.find(" LIMIT ")
                
                # Determinar fin de la tabla
                table_end = len(from_rest_original)
                if where_pos >= 0:
                    table_end = where_pos
                elif order_by_pos >= 0:
                    table_end = order_by_pos
                elif limit_pos >= 0:
                    table_end = limit_pos
                
                from_table = from_rest_original[:table_end].strip()
                
                # Parsear WHERE - usar original para preservar valores exactos
                if where_pos >= 0:
                    where_start = where_pos + 7  # " WHERE " tiene 7 caracteres
                    where_rest_original = from_rest_original[where_start:]
                    
                    # Encontrar fin del WHERE clause
                    where_end = len(where_rest_original)
                    if order_by_pos >= 0 and order_by_pos > where_pos:
                        where_end = order_by_pos - where_pos - 7
                    elif limit_pos >= 0 and limit_pos > where_pos:
                        where_end = limit_pos - where_pos - 7
                    
                    where_clause = where_rest_original[:where_end].strip()
                
                # Parsear ORDER BY - usar original
                if order_by_pos >= 0:
                    order_by_start = order_by_pos + 10  # " ORDER BY " tiene 10 caracteres
                    order_by_rest_original = from_rest_original[order_by_start:]
                    
                    order_by_end = len(order_by_rest_original)
                    if limit_pos >= 0 and limit_pos > order_by_pos:
                        order_by_end = limit_pos - order_by_pos - 10
                    
                    order_by_clause = order_by_rest_original[:order_by_end].strip()
                
                # Parsear LIMIT - usar original
                if limit_pos >= 0:
                    limit_start = limit_pos + 7  # " LIMIT " tiene 7 caracteres
                    limit_rest_original = from_rest_original[limit_start:]
                    limit_value = limit_rest_original.strip().split()[0] if limit_rest_original.strip() else None
        
        # Validar que tenemos al menos la tabla
        if not from_table:
            error_msg = "No se pudo determinar la tabla desde la consulta SQL. Usa el formato: select * from clnt_factura_principal"
            logger.error(error_msg)
            raise MBA3QueryError(error_msg)
        
        # Preparar form-data según el formato esperado por el API
        # Según el código JavaScript: data.append("select", "..."), data.append("from", "..."), etc.
        form_data = {
            'select': select_fields,
            'from': from_table,
        }
        
        # Agregar campos opcionales si están presentes
        if where_clause:
            form_data['where'] = where_clause
        if order_by_clause:
            form_data['orderBy'] = order_by_clause
        if limit_value:
            form_data['limit'] = limit_value
        
        # Log detallado de lo que se está enviando
        logger.debug(f"URL: {url}")
        logger.debug(f"Form-data a enviar: {form_data}")
        logger.info(f"Ejecutando consulta - Tabla: {from_table}, WHERE: {where_clause or 'N/A'}")
        
        # Preparar headers con el JWT
        # Según el código JavaScript: xhr.setRequestHeader("Authorization", localStorage.jwt);
        # El JWT se envía directamente en el header Authorization, sin prefijo "Bearer"
        headers = {}
        if self.jwt_token:
            headers['Authorization'] = self.jwt_token
        
        try:
            response = self.session.post(
                url,
                data=form_data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    logger.info("Consulta exitosa!")
                    return result
                except json.JSONDecodeError:
                    logger.warning(f"La respuesta no es JSON válido. Respuesta recibida: {response.text[:500]}")
                    return {'raw_response': response.text}
            
            elif response.status_code == 401:
                # Token inválido o expirado, intentar login nuevamente
                if self.jwt_token:
                    logger.info("Token inválido o expirado. Intentando login nuevamente...")
                    if self.login():
                        headers['Authorization'] = self.jwt_token
                        # Reintentar la consulta
                        response = self.session.post(
                            url,
                            data=form_data,
                            headers=headers,
                            timeout=30
                        )
                        if response.status_code == 200:
                            try:
                                return response.json()
                            except json.JSONDecodeError:
                                return {'raw_response': response.text}
                
                error_msg = f"Error 401 - No autorizado. Verifica tus credenciales. Respuesta: {response.text[:500]}"
                logger.error(error_msg)
                raise MBA3QueryError(error_msg)
            else:
                # Capturar respuesta completa de MBA3 para diagnóstico
                error_detail = response.text[:1000] if response.text else "Sin respuesta del servidor"
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
                
        except MBA3QueryError:
            # Re-lanzar excepciones de MBA3QueryError sin modificar
            raise
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            if hasattr(e, 'response') and e.response:
                error_detail = e.response.text[:1000] if e.response.text else "Sin respuesta"
            error_msg = f"Error HTTP al comunicarse con MBA3: {str(e)}. Respuesta: {error_detail}"
            logger.error(error_msg, exc_info=True)
            raise MBA3QueryError(error_msg)
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Error en la petición a MBA3: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise MBA3QueryError(error_msg)

