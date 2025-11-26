"""
Configuración y constantes para la API de consultas MBA3.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Configuración de límites
MAX_QUERY_LENGTH = 5000  # Longitud máxima de consulta en caracteres

# Ruta para guardar la última consulta (en la raíz del proyecto)
# Si api_server.py está en src/, subir un nivel para llegar a la raíz
_current_file = Path(__file__).resolve()
if _current_file.parent.name == "src":
    PROJECT_ROOT = _current_file.parent.parent
else:
    PROJECT_ROOT = _current_file.parent

QUERY_STORAGE_FILE = PROJECT_ROOT / "ultima_consulta.json"

# Ruta estándar para guardar resultados de consultas MBA3
# Siempre en la raíz del proyecto
RESULTADO_API_FILE = PROJECT_ROOT / "resultado_api.json"

# Cargar variables de entorno desde .env si existe
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    # print(f"✅ Variables de entorno cargadas desde: {env_path}")
else:
    # print(f"⚠️ Archivo .env no encontrado en: {env_path}")
    pass

# ============================================================================
# Configuración de MBA3
# ============================================================================
# Estas credenciales se usan para inicializar el cliente MBA3 cuando se reciben consultas dinámicas
# Se pueden configurar en el archivo .env o usar valores por defecto

MBA3_BASE_URL = os.getenv("MBA3_BASE_URL", "http://192.168.2.159:8081")
MBA3_SERVICE_CODE = os.getenv("MBA3_CODIGO", os.getenv("MBA3_SERVICE_CODE", "CDB002"))
MBA3_SERVICE_PASSWORD = os.getenv("MBA3_PWD", os.getenv("MBA3_SERVICE_PASSWORD", "***REMOVED***"))
MBA3_DIGEST_USERNAME = os.getenv("MBA3_DIGEST_USERNAME", MBA3_SERVICE_CODE)
MBA3_DIGEST_PASSWORD = os.getenv("MBA3_DIGEST_PASSWORD", MBA3_SERVICE_PASSWORD)

# ============================================================================
# Configuración de SQL Server (Principal - para almacenar datos)
# ============================================================================
# Para usar variables de entorno, configura en el archivo .env:
# - SQL_SERVER_DRIVER={ODBC Driver 17 for SQL Server}
# - SQL_SERVER_SERVER=tu_servidor
# - SQL_SERVER_DATABASE=tu_base_de_datos
# - SQL_SERVER_UID=tu_usuario (opcional para Windows Auth)
# - SQL_SERVER_PWD=tu_contraseña (opcional para Windows Auth)
# - ENABLE_SQL_SERVER_STORAGE=true

SQL_SERVER_DRIVER = os.getenv("SQL_SERVER_DRIVER", "{ODBC Driver 17 for SQL Server}")
SQL_SERVER_SERVER = os.getenv("SQL_SERVER_SERVER", "localhost")
SQL_SERVER_DATABASE = os.getenv("SQL_SERVER_DATABASE", "TuBaseDeDatos")
SQL_SERVER_UID = os.getenv("SQL_SERVER_UID", "")
SQL_SERVER_PWD = os.getenv("SQL_SERVER_PWD", "")

# Habilitar guardado en SQL Server (poner a False para deshabilitar)
ENABLE_SQL_SERVER_STORAGE = os.getenv("ENABLE_SQL_SERVER_STORAGE", "true").lower() == "true"

# ============================================================================
# Configuración de SQL Server SAP (para consultas OPENQUERY)
# ============================================================================
# Este servidor es diferente y se usa SOLO para ejecutar consultas OPENQUERY a SAP
# Debe tener el servidor vinculado [MYHANADB] configurado
# Si no se configuran estas variables, se usan las del servidor principal

SQL_SERVER_SAP_DRIVER = os.getenv("SQL_SERVER_SAP_DRIVER", SQL_SERVER_DRIVER)
SQL_SERVER_SAP_SERVER = os.getenv("SQL_SERVER_SAP_SERVER", SQL_SERVER_SERVER)
SQL_SERVER_SAP_DATABASE = os.getenv("SQL_SERVER_SAP_DATABASE", SQL_SERVER_DATABASE)
SQL_SERVER_SAP_UID = os.getenv("SQL_SERVER_SAP_UID", SQL_SERVER_UID)
SQL_SERVER_SAP_PWD = os.getenv("SQL_SERVER_SAP_PWD", SQL_SERVER_PWD)

# ============================================================================
# Configuración de SAP (HANA)
# ============================================================================
# Configuración para consultas a SAP usando OPENQUERY desde SQL Server
# El servidor vinculado debe estar configurado en SQL Server como [MYHANADB]

# Nombre del servidor vinculado en SQL Server (configurado con OPENQUERY)
SAP_LINKED_SERVER = os.getenv("SAP_LINKED_SERVER", "MYHANADB")

# Base de datos y esquema de SAP
SAP_DATABASE = os.getenv("SAP_DATABASE", "SBO_MABEL_PROD")
SAP_SCHEMA = os.getenv("SAP_SCHEMA", "SBO_MABEL_PROD")

# Habilitar consultas a SAP (poner a False para deshabilitar)
ENABLE_SAP_QUERIES = os.getenv("ENABLE_SAP_QUERIES", "true").lower() == "true"

# Tiempo de vida del cache en días (cuántos días antes de re-consultar SAP)
SAP_CACHE_DAYS = int(os.getenv("SAP_CACHE_DAYS", "30"))

