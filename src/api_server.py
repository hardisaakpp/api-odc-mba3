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

import asyncio
import logging
import uvicorn
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Agregar el directorio src al PYTHONPATH si no está
# Esto permite ejecutar el script directamente con: python src/api_server.py
src_dir = Path(__file__).parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# IMPORTANTE: Configurar logging ANTES de importar otros módulos de src
# Esto asegura que todos los loggers usen la configuración correcta
# (Buenas Prácticas - Sección 5: Logs obligatorios)
from src.logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.endpoints import create_endpoints
from src.middleware.exception_handlers import setup_exception_handlers
from src.middleware.request_logging import setup_request_logging
from src.config import (
    ENABLE_CORS_RESTRICTION,
    CORS_ALLOWED_ORIGINS,
    ENVIRONMENT,
    ENV_FILE_USED,
    HIDE_SWAGGER_IN_PROD,
    API_THREAD_POOL_MAX_WORKERS,
)
from src.security.rate_limit import setup_rate_limiting

logger.info(f"🌿 Ambiente activo: {ENVIRONMENT} | env file: {ENV_FILE_USED}")

# Crear aplicación FastAPI
app = FastAPI(
    title="MBA3 Query API",
    description="API para recibir, validar y procesar consultas SQL (SELECT)",
    version="2.1.0",
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
        },
        {
            "name": "Cruce de Productos",
            "description": "Endpoints para cruzar productos entre MBA3 y SAP"
        },
        {
            "name": "Plantillas",
            "description": "Endpoints para gestión de plantillas Excel"
        },
        {
            "name": "Autenticación",
            "description": "Endpoints de autenticación y autorización"
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

# Configurar logging de requests (Buenas Prácticas - Sección 5: Logs obligatorios)
setup_request_logging(app)

# Registrar todos los endpoints
create_endpoints(app)


def _configurar_executor_thread_pool() -> None:
    # Configurar un ThreadPoolExecutor dedicado como executor por defecto
    # del event loop. Sin esto, asyncio usa su pool por defecto
    # (min(32, os.cpu_count()+4)), compartido por TODAS las llamadas
    # asyncio.to_thread(...) de la app (SQL Server vía pyodbc, HTTP a
    # SAP/middleware, storage de archivos). Bajo carga ese pool por
    # defecto se agota y peticiones quedan encoladas esperando un hilo
    # libre. Tamaño configurable con API_THREAD_POOL_MAX_WORKERS (ver
    # src/config.py).
    loop = asyncio.get_running_loop()
    loop.set_default_executor(
        ThreadPoolExecutor(
            max_workers=API_THREAD_POOL_MAX_WORKERS,
            thread_name_prefix="api-io-worker",
        )
    )
    logger.info(
        f"🧵 Executor por defecto del event loop: ThreadPoolExecutor("
        f"max_workers={API_THREAD_POOL_MAX_WORKERS})"
    )


def _inicializar_cliente_mba3() -> None:
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


def _verificar_conexion_sql_server() -> None:
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


def _ejecutar_migraciones_pendientes(runner, a_aplicar: list) -> None:
    logger.info(f"   📋 Migraciones a aplicar: {', '.join(m['version'] for m in a_aplicar)}")
    for migration in a_aplicar:
        if not runner.execute_migration(migration, dry_run=False):
            logger.error(
                f"   ❌ Migración {migration['version']} ({migration['name']}) falló; "
                "se detiene el auto-apply. Aplícala manualmente con scripts/migration_runner.py."
            )
            break


def _auto_aplicar_migraciones_schema() -> None:
    # Auto-aplicar migraciones de ESQUEMA (ALTER TABLE / catálogo, ver
    # scripts/migration_runner.py) pendientes -- SOLO en development. Evita el
    # patrón que causó el bug de req. 1.2 (2026-08-17): una migración quedaba
    # escrita en scripts/migrations/ y en el manifest, pero nadie la ejecutaba
    # contra la BD local, y el código degradaba en silencio (columna ausente ->
    # valor NULL) en vez de fallar. NO se activa en staging/production: ahí las
    # migraciones se aplican a mano antes del deploy (memoria del equipo: solo
    # si son aditivas), un paso deliberado -- staging/producción no deben
    # mutar su propio esquema en cada arranque, y con >1 instancia arrancando
    # a la vez, correr el mismo ALTER TABLE en paralelo puede bloquearse.
    # No confundir con ENABLE_AUTO_MIGRATE de abajo: aquella es la migración
    # de datos de despachos vía Celery Beat (legacy), un concepto distinto.
    # Se excluyen migraciones category="rollback" (ej. DROP TABLE) del
    # auto-apply: igual que las marcadas manual=true en el manifest, son
    # cambios destructivos que requieren revisión humana antes de ejecutarse.
    if ENVIRONMENT != "development":
        logger.info(
            f"⏭️ Auto-apply de migraciones de esquema deshabilitado (ENVIRONMENT={ENVIRONMENT}); "
            "en este ambiente se aplican a mano con scripts/migration_runner.py antes del deploy"
        )
        return

    try:
        scripts_dir = Path(__file__).parent.parent / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from migration_runner import MigrationRunner

        logger.info("🔧 Auto-aplicando migraciones de esquema pendientes (solo development)...")
        runner = MigrationRunner(
            manifest_path=scripts_dir / "migrations_manifest.yaml",
            scripts_dir=scripts_dir,
        )
        runner.load_manifest()
        runner.connect_db()
        runner.ensure_migration_table()
        runner.load_applied_migrations()

        pending = runner.get_pending_migrations(skip_manual=True)
        excluidas_rollback = [m for m in pending if m.get("category") == "rollback"]
        a_aplicar = [m for m in pending if m.get("category") != "rollback"]

        if excluidas_rollback:
            logger.warning(
                "   ⚠️ Migraciones 'rollback' pendientes, NO auto-aplicadas (requieren revisión manual): "
                + ", ".join(f"{m['version']} ({m['name']})" for m in excluidas_rollback)
            )

        if not a_aplicar:
            logger.info("   ✅ No hay migraciones de esquema pendientes por aplicar")
        else:
            _ejecutar_migraciones_pendientes(runner, a_aplicar)
        runner.conn.close()
    except Exception as e:
        logger.error(f"❌ Error al auto-aplicar migraciones de esquema: {e}")
        logger.error("   El servidor sigue arrancando; aplica manualmente con scripts/migration_runner.py")


def _log_configuracion_migracion_automatica() -> None:
    # IMPORTANTE: NO iniciar asyncio auto_migrate.
    # La migración automática ahora se ejecuta con Celery Beat en un proceso separado.
    # Esto previene el cuello de botella entre el proceso manual y automático.
    try:
        from config import ENABLE_AUTO_MIGRATE, AUTO_MIGRATE_INTERVAL_MINUTES, MIGRATE_DATE_FILTER_DAYS

        logger.info("=" * 70)
        logger.info("📢 CONFIGURACIÓN DE MIGRACIÓN AUTOMÁTICA:")

        if ENABLE_AUTO_MIGRATE:
            logger.info("   ⚠️ Migración automática configurada con CELERY BEAT")
            logger.info("   ⚠️ La migración automática corre en un PROCESO SEPARADO")
            logger.info("   ⚠️ NO usa asyncio (previene cuello de botella con proceso manual)")
            logger.info("")
            logger.info("   📋 Para ejecutar el proceso automático, inicia en terminales separadas:")
            logger.info("")
            logger.info("   Terminal 2 (Worker Celery):")
            logger.info("      celery -A src.celery_app worker --loglevel=info --pool=solo")
            logger.info("")
            logger.info("   Terminal 3 (Beat Celery - Scheduler):")
            logger.info("      celery -A src.celery_app beat --loglevel=info")
            logger.info("")
            logger.info(f"   ⏰ Intervalo: cada {AUTO_MIGRATE_INTERVAL_MINUTES} minutos")
            logger.info(f"   📅 Filtro: últimos {MIGRATE_DATE_FILTER_DAYS} días")
            logger.info("")
            logger.info("   ✅ El proceso automático NO afecta al proceso manual (/migrar/completo)")
            logger.info("   ✅ Cada proceso tiene su propio pool de conexiones")
            logger.info("   ✅ No hay competencia por recursos")
        else:
            logger.info("   ⏭️ Migración automática DESHABILITADA (ENABLE_AUTO_MIGRATE=false)")
            logger.info("   ℹ️ Solo está disponible el proceso manual: GET /migrar/completo")

        logger.info("=" * 70)
    except Exception as e:
        logger.error(f"❌ Error al verificar configuración de migración: {e}")
        logger.error("   La migración manual seguirá funcionando")


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

    # 0. Executor dedicado del event loop (ver detalle en _configurar_executor_thread_pool)
    _configurar_executor_thread_pool()

    # 1. Inicializar cliente MBA3 (warm-up)
    _inicializar_cliente_mba3()

    # 2. Verificar conexión a SQL Server (si está habilitada)
    _verificar_conexion_sql_server()

    # 2.5 Auto-aplicar migraciones de esquema pendientes (ver detalle en _auto_aplicar_migraciones_schema)
    _auto_aplicar_migraciones_schema()

    # 3. Log de configuración de migración automática (Celery Beat)
    _log_configuracion_migracion_automatica()

    # 4. Listener SSE↔Redis: reenvía al bus de notificaciones (notification_manager)
    # los mensajes que publican los workers de Celery (proceso aparte, sin acceso
    # directo a las colas SSE en memoria de este proceso). Ver src/utils/sse_redis_bridge.py.
    from src.utils.sse_redis_bridge import escuchar_notificaciones_redis
    app.state.sse_redis_listener_task = asyncio.create_task(escuchar_notificaciones_redis())

    logger.info("=" * 70)
    logger.info("✅ Inicialización completada - Servidor listo para recibir peticiones")
    logger.info("=" * 70)


@app.on_event("shutdown")
async def shutdown_event():
    """
    Evento de cierre del servidor.
    """
    logger.info("🛑 Cerrando servidor...")

    listener_task = getattr(app.state, "sse_redis_listener_task", None)
    if listener_task is not None:
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"⚠️ Error al detener el listener SSE↔Redis: {e}")

    logger.info("✅ Servidor cerrado")


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
        reload_delay=1.0,  # Espera 1s antes de recargar (agrupa cambios rápidos y evita double-reload)
        reload_dirs=["src"],  # Solo vigilar src/ (ignora output/, logs/, .venv/, etc.)
        log_level="info",
        timeout_keep_alive=120,  # Timeout para mantener conexión viva (120 segundos)
        timeout_graceful_shutdown=30,  # Timeout para cierre ordenado (30 segundos)
        limit_concurrency=100,  # Limitar conexiones concurrentes
        backlog=2048  # Tamaño de la cola de conexiones pendientes
    )
