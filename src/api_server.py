"""
API HTTP para recibir, validar y ejecutar consultas SQL contra MBA3.

Servicio FastAPI que recibe consultas SQL (SELECT) desde Postman, las valida,
y las ejecuta contra MBA3 usando MBA3APIClient.

Esta versión usa una arquitectura mejorada con:
- Capa de servicios para lógica de negocio
- Helpers para parsing de requests
- Exception handlers centralizados

Endpoints disponibles:
- /consulta: Ejecuta consultas dinámicas contra MBA3 y retorna el resultado JSON
- /query: Recibe y valida consultas SQL (solo validación y almacenamiento)
- /health: Health check del servicio
- /test: Endpoint de prueba para verificar comunicación Postman → API
"""

import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from endpoints import create_endpoints
from middleware.exception_handlers import setup_exception_handlers

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI
app = FastAPI(
    title="MBA3 Query API",
    description="API para recibir, validar y procesar consultas SQL (SELECT)",
    version="2.0.0"
)

# Configurar CORS para permitir pruebas desde Postman y otros clientes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar exception handlers centralizados
setup_exception_handlers(app)

# Registrar todos los endpoints
create_endpoints(app)


if __name__ == "__main__":
    # Ejecutar servidor con uvicorn
    # Nota: host="0.0.0.0" significa que escucha en todas las interfaces de red
    # Para acceder desde el navegador, usa: http://localhost:8000 o http://127.0.0.1:8000
    print("=" * 70)
    print("Iniciando servidor FastAPI...")
    print("=" * 70)
    print("URLs disponibles:")
    print("  - http://localhost:8000")
    print("  - http://127.0.0.1:8000")
    print("  - http://0.0.0.0:8000 (solo para escuchar, no para acceder)")
    print("=" * 70)
    print("\nDocumentación interactiva disponible en:")
    print("  - http://localhost:8000/docs (Swagger UI)")
    print("  - http://localhost:8000/redoc (ReDoc)")
    print("\nEndpoint de health check:")
    print("  - http://localhost:8000/health")
    print("\nPresiona Ctrl+C para detener el servidor\n")
    print("=" * 70 + "\n")
    
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",  # Escucha en todas las interfaces
        port=8000,
        reload=True,
        log_level="info"
    )
