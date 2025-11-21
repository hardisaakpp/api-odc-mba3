"""
Aplicación para consumir la API de MBA3 (4D) con autenticación Digest.

Realiza consultas a la base de datos mediante peticiones POST.

Según la documentación, se requiere primero hacer LOGIN para obtener un JWT (sesión).

"""

import requests
from requests.auth import HTTPDigestAuth
import json
from typing import Dict, Any, Optional
from mba3_client import MBA3Client


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
            print("Intentando hacer LOGIN usando el método de mba3_client...")
            token = self.login_client.login(self.service_code, self.service_password)
            if token:
                self.jwt_token = token
                print(f"[OK] Login exitoso. JWT obtenido.")
                print(f"  JWT (primeros 50 caracteres): {self.jwt_token[:50]}...")
                return True
            return False
        except Exception as e:
            print(f"[ERROR] No se pudo hacer login: {e}")
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
                print("[INFO] No se pudo obtener JWT. Intentando consulta directa sin JWT...")
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
            if "SELECT" in query_upper and "FROM" in query_upper:
                # Parsear SELECT
                select_part = query_upper.split("SELECT")[1].split("FROM")[0].strip()
                select_fields = select_part if select_part else "*"
                
                # Parsear FROM
                from_part = query_upper.split("FROM")[1]
                if "WHERE" in from_part:
                    from_table = from_part.split("WHERE")[0].strip()
                elif "ORDER BY" in from_part:
                    from_table = from_part.split("ORDER BY")[0].strip()
                elif "LIMIT" in from_part:
                    from_table = from_part.split("LIMIT")[0].strip()
                else:
                    from_table = from_part.strip()
                
                # Parsear WHERE
                if "WHERE" in query_upper:
                    where_part = query_upper.split("WHERE")[1]
                    if "ORDER BY" in where_part:
                        where_clause = where_part.split("ORDER BY")[0].strip()
                    elif "LIMIT" in where_part:
                        where_clause = where_part.split("LIMIT")[0].strip()
                    else:
                        where_clause = where_part.strip()
                
                # Parsear ORDER BY
                if "ORDER BY" in query_upper:
                    order_part = query_upper.split("ORDER BY")[1]
                    if "LIMIT" in order_part:
                        order_by_clause = order_part.split("LIMIT")[0].strip()
                    else:
                        order_by_clause = order_part.strip()
                
                # Parsear LIMIT
                if "LIMIT" in query_upper:
                    limit_part = query_upper.split("LIMIT")[1].strip().split()[0]
                    limit_value = limit_part
        
        # Validar que tenemos al menos la tabla
        if not from_table:
            print("[ERROR] No se pudo determinar la tabla desde la consulta SQL.")
            print("  Usa el formato: select * from clnt_factura_principal")
            return None
        
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
                    print(f"[OK] Consulta exitosa!")
                    return result
                except json.JSONDecodeError:
                    print(f"[WARNING] La respuesta no es JSON válido.")
                    print(f"Respuesta recibida: {response.text[:500]}")
                    return {'raw_response': response.text}
            
            elif response.status_code == 401:
                # Token inválido o expirado, intentar login nuevamente
                if self.jwt_token:
                    print("[INFO] Token inválido o expirado. Intentando login nuevamente...")
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
                
                print(f"[ERROR] Error 401 - No autorizado. Verifica tus credenciales.")
                return None
            else:
                print(f"[ERROR] Error HTTP {response.status_code}")
                print(f"Respuesta del servidor: {response.text[:500]}")
                return None
                
        except requests.exceptions.HTTPError as e:
            print(f"[ERROR] Error HTTP: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"Respuesta: {e.response.text[:500]}")
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Error en la petición: {e}")
            return None


def main():
    """Función principal para probar la conexión a la API."""
    
    # Configuración de la API
    BASE_URL = "http://192.168.2.159:8081"
    
    # Según la documentación, el LOGIN requiere:
    # - código: Código del servicio
    # - pwd: Contraseña del servicio
    # El usuario mencionó CDB002 como usuario Digest y 88888 como contraseña
    # Probablemente CDB002 es el código del servicio y 88888 es la contraseña del servicio
    SERVICE_CODE = "CDB002"
    SERVICE_PASSWORD = "***REMOVED***"
    
    # También mantener Digest Auth por si es necesario
    DIGEST_USERNAME = "CDB002"
    DIGEST_PASSWORD = "***REMOVED***"
    
    # Consulta SQL a ejecutar
    #query = "select * from clnt_factura_principal where NUMERO_PEDIDO_SISTEMA='176120'"
    query = "select CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada from CLNT_FACTURA_PRINCIPAL where NUMERO_PEDIDO_SISTEMA='176120'"
    
    # Crear cliente de API
    client = MBA3APIClient(
        base_url=BASE_URL,
        service_code=SERVICE_CODE,
        service_password=SERVICE_PASSWORD,
        digest_username=DIGEST_USERNAME,
        digest_password=DIGEST_PASSWORD
    )
    
    print("=" * 70)
    print("Consultando API de MBA3 (4D)")
    print("=" * 70)
    print(f"URL: {BASE_URL}")
    print(f"Codigo de servicio: {SERVICE_CODE}")
    print(f"Query: {query}")
    print("-" * 70)
    
    # El JWT es necesario según la documentación
    print("\nEjecutando consulta con JWT...")
    result = client.execute_query(query, require_jwt=True)
    
    if result:
        print("\n[OK] Respuesta exitosa recibida (200 OK)!")
        print("\n" + "=" * 70)
        print("DATOS RECIBIDOS:")
        print("=" * 70)
        
        # Mostrar todos los datos completos (sin truncar)
        result_json = json.dumps(result, indent=2, ensure_ascii=False)
        print(result_json)
        
        # Guardar resultado en archivo JSON (sobrescribe el archivo anterior)
        from config import RESULTADO_API_FILE
        try:
            with open(RESULTADO_API_FILE, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"\n[OK] Resultado completo guardado en: {RESULTADO_API_FILE}")
            
            # Mostrar estadísticas del resultado
            if isinstance(result, list):
                print(f"Total de registros obtenidos: {len(result)}")
            elif isinstance(result, dict):
                print(f"Datos guardados exitosamente (estructura: diccionario)")
                
        except Exception as e:
            print(f"\n[ERROR] No se pudo guardar el resultado: {e}")
    else:
        print("\n[ERROR] No se pudo obtener respuesta de la API.")
        print("\nSugerencias:")
        print("1. Verifica que el código de servicio y contraseña sean correctos")
        print("2. Verifica que la URL sea correcta")
        print("3. Verifica que el servidor esté accesible")
        print("4. Revisa la documentación para confirmar el endpoint del LOGIN")


if __name__ == "__main__":
    main()

