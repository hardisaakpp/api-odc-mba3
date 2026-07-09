# src/main.py
"""
Script principal para interactuar con la API de MBA3.

Permite:
- Obtener JWT (sesión) mediante LOGIN
- Ejecutar consultas SQL en la base de datos
- Ejecutar ambos en secuencia

Según documentación técnica de MBA3:
- El usuario debe crear un LOGIN, necesario para el uso de los servicios
- Credenciales: código (código del servicio), pwd (contraseña del servicio)
- Si los datos son correctos, regresa un JWT (sesión)
- Es importante almacenar el JWT en una variable en memoria para hacer uso 
  en todas las peticiones de los Servicios creados
"""
import os
import argparse
from src.mba3_client import MBA3Client
from src.mba3_query_client import MBA3APIClient
from src.config import (
    MBA3_BASE_URL,
    MBA3_SERVICE_CODE,
    MBA3_SERVICE_PASSWORD,
    MBA3_DIGEST_USERNAME,
    MBA3_DIGEST_PASSWORD,
    RESULTADO_API_FILE,
    ENV_FILE_USED,
)

BASE_URL = MBA3_BASE_URL
CODIGO = MBA3_SERVICE_CODE
PWD = MBA3_SERVICE_PASSWORD
DIGEST_USERNAME = MBA3_DIGEST_USERNAME
DIGEST_PASSWORD = MBA3_DIGEST_PASSWORD
QUERY = os.getenv("MBA3_QUERY", None)  # Consulta SQL opcional desde .env

if not (BASE_URL and CODIGO and PWD):
    raise SystemExit(f"Falta configurar BASE_URL, CODIGO o PWD en {ENV_FILE_USED}")


def do_login():
    """
    Obtiene el JWT (sesión) mediante LOGIN.
    
    Returns:
        JWT token como string, o None si hay error
    """
    if not BASE_URL or not CODIGO or not PWD:
        raise SystemExit(f"Falta configurar BASE_URL, CODIGO o PWD en {ENV_FILE_USED}")
    
    client = MBA3Client(BASE_URL)
    try:
        token = client.login(CODIGO, PWD)
        print("\n" + "="*60)
        print("✅ LOGIN EXITOSO - JWT (sesión) obtenido")
        print("="*60)
        print(f"\nJWT: {token}")
        print("\n⚠️  IMPORTANTE: Almacena este JWT para usarlo en tus peticiones.")
        print("   El JWT tiene un tiempo de expiración limitado.")
        print("   Si expira, deberás realizar un nuevo LOGIN.\n")
        return token
    except Exception as e:
        print("\n" + "="*60)
        print("❌ ERROR EN LOGIN")
        print("="*60)
        print(f"\n{str(e)}\n")
        return None


def do_query(query: str | None = None):
    """
    Ejecuta una consulta SQL en la base de datos MBA3.
    
    Args:
        query: Consulta SQL a ejecutar. Si es None, usa la del .env o una por defecto.
    
    Returns:
        Resultado de la consulta como diccionario, o None si hay error
    """
    if not query:
        query = QUERY
        if not query:
            # Consulta por defecto de ejemplo
            query = "select CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada from CLNT_FACTURA_PRINCIPAL where NUMERO_PEDIDO_SISTEMA='176120'"
            print(f"[INFO] Usando consulta por defecto. Configura MBA3_QUERY en {ENV_FILE_USED} para usar otra consulta.")
    
    # Verificar que query no sea None después de las asignaciones
    if not query:
        raise SystemExit("No se pudo determinar la consulta SQL a ejecutar")
    
    # Verificar que las variables de configuración no sean None
    if not BASE_URL or not CODIGO or not PWD:
        raise SystemExit(f"Falta configurar BASE_URL, CODIGO o PWD en {ENV_FILE_USED}")
    
    # Asegurar que DIGEST_USERNAME y DIGEST_PASSWORD no sean None
    digest_user = DIGEST_USERNAME if DIGEST_USERNAME else CODIGO
    digest_pwd = DIGEST_PASSWORD if DIGEST_PASSWORD else PWD
    
    # Crear cliente de API con autenticación Digest
    client = MBA3APIClient(
        base_url=BASE_URL,
        service_code=CODIGO,
        service_password=PWD,
        digest_username=digest_user,
        digest_password=digest_pwd
    )
    
    print("=" * 70)
    print("Consultando API de MBA3 (4D)")
    print("=" * 70)
    print(f"URL: {BASE_URL}")
    print(f"Código de servicio: {CODIGO}")
    print(f"Query: {query}")
    print("-" * 70)
    
    # Ejecutar consulta con JWT
    print("\nEjecutando consulta con JWT...")
    result = client.execute_query(query, require_jwt=True)
    
    if result:
        print("\n[OK] Respuesta exitosa recibida (200 OK)!")
        print("\n" + "=" * 70)
        print("DATOS RECIBIDOS:")
        print("=" * 70)
        
        # Mostrar todos los datos completos (sin truncar)
        import json
        result_json = json.dumps(result, indent=2, ensure_ascii=False)
        print(result_json)
        
        # Guardar resultado en archivo JSON
        try:
            with open(RESULTADO_API_FILE, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"\n[OK] Resultado completo guardado en: {RESULTADO_API_FILE}")
            
            # Mostrar estadísticas del resultado
            if isinstance(result, list):
                print(f"Total de registros obtenidos: {len(result)}")
            elif isinstance(result, dict):
                print("Datos guardados exitosamente (estructura: diccionario)")
                
        except Exception as e:
            print(f"\n[ERROR] No se pudo guardar el resultado: {e}")
        
        return result
    else:
        print("\n[ERROR] No se pudo obtener respuesta de la API.")
        print("\nSugerencias:")
        print("1. Verifica que el código de servicio y contraseña sean correctos")
        print("2. Verifica que la URL sea correcta")
        print("3. Verifica que el servidor esté accesible")
        print("4. Revisa la documentación para confirmar el endpoint del LOGIN")
        return None


def main():
    """
    Función principal que permite ejecutar login, consulta o ambos.
    
    Uso:
        python main.py              # Ejecuta solo login (comportamiento por defecto)
        python main.py --login      # Ejecuta solo login
        python main.py --query      # Ejecuta solo consulta
        python main.py --query "select * from tabla"  # Ejecuta consulta personalizada
        python main.py --all        # Ejecuta login y luego consulta
    """
    parser = argparse.ArgumentParser(
        description='Cliente para interactuar con la API de MBA3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python main.py                    # Solo login
  python main.py --query            # Solo consulta (usa query de .env o por defecto)
  python main.py --query "select * from tabla"  # Consulta personalizada
  python main.py --all              # Login y luego consulta
        """
    )
    
    parser.add_argument('--login', action='store_true',
                       help='Ejecutar solo el login para obtener JWT')
    parser.add_argument('--query', nargs='?', const=True,
                       help='Ejecutar solo una consulta SQL (opcional: proporcionar la query)')
    parser.add_argument('--all', action='store_true',
                       help='Ejecutar login y luego consulta')
    
    args = parser.parse_args()
    
    # Si no se proporcionan argumentos, ejecutar solo login (comportamiento por defecto)
    if not (args.login or args.query or args.all):
        args.login = True
    
    # Ejecutar según los argumentos
    if args.all:
        print("=" * 70)
        print("EJECUTANDO LOGIN Y CONSULTA")
        print("=" * 70)
        token = do_login()
        if token:
            print("\n" + "=" * 70)
            print("CONTINUANDO CON LA CONSULTA...")
            print("=" * 70)
            do_query()
    elif args.login:
        do_login()
    elif args.query:
        query_str: str | None = args.query if isinstance(args.query, str) else None
        do_query(query_str)


if __name__ == "__main__":
    main()
