"""
API HTTP para consultar y gestionar facturas desde MBA3, con integración a SQL Server y SAP.

Servicio FastAPI que proporciona endpoints para:
- Consultar y migrar despachos desde MBA3
- Procesar órdenes de compra
- Integrar con SAP Service Layer

Esta versión usa una arquitectura mejorada con:
- Capa de servicios para lógica de negocio
- Repositorios para acceso a datos
- Exception handlers centralizados

Endpoints principales:
- GET /consultar: Consulta despachos desde MBA3 (solo lectura)
- GET /migrar: Consulta y guarda en base de datos
- GET /procesar-oc: Copia despachos a órdenes de compra
- POST /integrar-sap: Envía ODCs a SAP Service Layer
- GET /health: Health check del servicio
"""

import logging
import uvicorn
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Agregar el directorio src al PYTHONPATH si no está
# Esto permite ejecutar el script directamente con: python src/api_server.py
src_dir = Path(__file__).parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from endpoints import create_endpoints
from middleware.exception_handlers import setup_exception_handlers
from config import (
    ENABLE_CORS_RESTRICTION,
    CORS_ALLOWED_ORIGINS,
    ENVIRONMENT,
    HIDE_SWAGGER_IN_PROD,
    ENABLE_SQL_SERVER_STORAGE
)
from security.rate_limit import setup_rate_limiting

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
    version="2.0.0",
    # Ocultar Swagger en producción si está configurado
    docs_url="/docs" if not (ENVIRONMENT == "production" and HIDE_SWAGGER_IN_PROD) else None,
    redoc_url="/redoc" if not (ENVIRONMENT == "production" and HIDE_SWAGGER_IN_PROD) else None,
    # Agregar descripciones de tags para organizar Swagger
    openapi_tags=[
        {
            "name": "Sistema",
            "description": "Endpoints de salud y estado del sistema"
        },
        {
            "name": "Consultas MBA3",
            "description": "Endpoints para consultar y migrar datos desde MBA3"
        },
        {
            "name": "Procesamiento",
            "description": "Endpoints para procesar despachos y órdenes de compra"
        },
        {
            "name": "Integración SAP",
            "description": "Endpoints para integrar con SAP Service Layer y HANA"
        },
        {
            "name": "Órdenes de Compra",
            "description": "Endpoints para gestionar órdenes de compra"
        },
        {
            "name": "Historial",
            "description": "Endpoints para consultar historial y logs"
        },
        {
            "name": "Pruebas",
            "description": "Endpoints de prueba y debugging"
        }
    ]
)

# Configurar CORS (restrictivo o permisivo según configuración)
if ENABLE_CORS_RESTRICTION:
    # CORS restrictivo: solo origenes permitidos
    allowed_origins = [origin.strip() for origin in CORS_ALLOWED_ORIGINS if origin.strip() != "*"]
    if not allowed_origins:
        logger.warning("⚠️ ENABLE_CORS_RESTRICTION=true pero CORS_ALLOWED_ORIGINS está vacío o es '*'")
        logger.warning("   Usando configuración permisiva por seguridad")
        allowed_origins = ["*"]
    else:
        logger.info(f"✅ CORS restrictivo habilitado: {allowed_origins}")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
else:
    # CORS permisivo (por defecto, para desarrollo)
    logger.info("ℹ️ CORS permisivo (desarrollo). Configura ENABLE_CORS_RESTRICTION=true para producción")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Configurar rate limiting (opcional)
setup_rate_limiting(app)

# Configurar exception handlers centralizados
setup_exception_handlers(app)

# Registrar todos los endpoints
create_endpoints(app)


@app.on_event("startup")
async def startup_event():
    """
    Evento de inicio que inicializa recursos críticos antes de aceptar peticiones.
    
    Esto resuelve el problema del error 500 en la primera llamada al hacer warm-up de:
    - Cliente MBA3 (inicialización y login)
    - Conexión a SQL Server (si está habilitada)
    """
    logger.info("=" * 70)
    logger.info("🚀 Inicializando recursos críticos...")
    logger.info("=" * 70)
    
    # 1. Inicializar cliente MBA3 (warm-up)
    try:
        logger.info("📡 Inicializando cliente MBA3...")
        from query_handler import get_mba3_client
        
        client = get_mba3_client()
        logger.info("✅ Cliente MBA3 inicializado")
        
        # Intentar hacer login para verificar que funciona
        if client.login():
            logger.info("✅ Login MBA3 exitoso - JWT obtenido")
        else:
            logger.warning("⚠️ No se pudo hacer login en MBA3, pero el cliente está inicializado")
            logger.warning("   El login se intentará automáticamente en la primera consulta")
    except Exception as e:
        logger.error(f"❌ Error al inicializar cliente MBA3: {e}")
        logger.error("   El sistema intentará inicializarlo en la primera consulta")
        logger.error("   Esto puede causar un error 500 en la primera llamada")
    
    # 2. Verificar conexión a SQL Server (si está habilitada)
    if ENABLE_SQL_SERVER_STORAGE:
        try:
            logger.info("💾 Verificando conexión a SQL Server...")
            from database.connection import get_db_connection
            
            conn = get_db_connection()
            if conn:
                # Verificar que la conexión funciona
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                conn.close()
                logger.info("✅ Conexión a SQL Server verificada")
            else:
                logger.warning("⚠️ No se pudo establecer conexión a SQL Server")
        except Exception as e:
            logger.error(f"❌ Error al verificar conexión a SQL Server: {e}")
            logger.error("   El sistema intentará conectarse en la primera operación")
            logger.error("   Esto puede causar un error 500 en la primera llamada")
    else:
        logger.info("⏭️ SQL Server storage deshabilitado (ENABLE_SQL_SERVER_STORAGE=false)")
    
    logger.info("=" * 70)
    logger.info("✅ Inicialización completada - Servidor listo para recibir peticiones")
    logger.info("=" * 70)


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
