"""
Configuración y constantes para la API de consultas MBA3.
"""

from pathlib import Path

# Configuración de límites
MAX_QUERY_LENGTH = 5000  # Longitud máxima de consulta en caracteres

# Ruta para guardar la última consulta (en la raíz del proyecto)
# Si api_server.py está en src/, subir un nivel para llegar a la raíz
_current_file = Path(__file__).resolve()
if _current_file.parent.name == "src":
    QUERY_STORAGE_FILE = _current_file.parent.parent / "ultima_consulta.json"
else:
    QUERY_STORAGE_FILE = _current_file.parent / "ultima_consulta.json"

# Configuración de MBA3 (mismas credenciales que usa mba3_query_client.py)
# Estas credenciales se usan para inicializar el cliente MBA3 cuando se reciben consultas dinámicas
MBA3_BASE_URL = "http://192.168.2.159:8081"
MBA3_SERVICE_CODE = "CDB002"
MBA3_SERVICE_PASSWORD = "***REMOVED***"
MBA3_DIGEST_USERNAME = "CDB002"
MBA3_DIGEST_PASSWORD = "***REMOVED***"

