"""
Configuracion y constantes para la API de consultas MBA3.
"""

import logging
import os
from pathlib import Path
from importlib import import_module

_dotenv_module = None
try:
    _dotenv_module = import_module("dotenv")
except ModuleNotFoundError:
    _dotenv_module = None

if _dotenv_module is not None:
    load_dotenv = _dotenv_module.load_dotenv
else:
    # Permite correr sin python-dotenv (e.g. en entornos de análisis estático).
    def load_dotenv(*args, **kwargs):
        return False

# Configuracion de li­mites
MAX_QUERY_LENGTH = 5000  # Longitud maxima de consulta en caracteres

# Ruta para guardar la Ãºltima consulta (en la raÃ­z del proyecto)
# Si api_server.py estÃ¡ en src/, subir un nivel para llegar a la raÃ­z
_current_file = Path(__file__).resolve()
if _current_file.parent.name == "src":
    PROJECT_ROOT = _current_file.parent.parent
else:
    PROJECT_ROOT = _current_file.parent

QUERY_STORAGE_FILE = PROJECT_ROOT / "ultima_consulta.json"

# Ruta estÃ¡ndar para guardar resultados de consultas MBA3
# Siempre en la raÃ­z del proyecto
RESULTADO_API_FILE = PROJECT_ROOT / "resultado_api.json"

def _normalize_environment(env_value: str) -> str:
    """Normaliza aliases de ambiente a un set acotado."""
    env = (env_value or "").strip().lower()
    mapping = {
        "dev": "development",
        "develop": "development",
        "development": "development",
        "qa": "test",
        "testing": "test",
        "test": "test",
        "prod": "production",
        "production": "production",
        "stage": "staging",
        "staging": "staging",
    }
    return mapping.get(env, "development")


def _resolve_env_file_path(project_root: Path) -> Path:
    """
    Determina qué archivo .env cargar (ruta absoluta o bajo project_root).

    Orden (sin fallback silencioso a un `.env` genérico sin nombre):

    1) Si existe ``ENV_FILE`` -> ese archivo debe existir (típico en systemd:
       ``Environment=ENV_FILE=/opt/odc-sap/.env``).
    2) Si no -> ``.env.develop`` | ``.env.test`` | ``.env.staging`` | ``.env.production``
       según ``ENVIRONMENT`` (normalizado; por defecto ``development`` → ``.env.develop``).

    El valor lógico de ambiente (``APP_ENV``) se fija **después** de ``load_dotenv``,
    para que ``ENVIRONMENT`` definido dentro del archivo cargado (o solo ahí) aplique
    correctamente cuando se usa ``ENV_FILE``.
    """
    explicit_env_file = os.getenv("ENV_FILE", "").strip()
    if explicit_env_file:
        explicit_path = Path(explicit_env_file).expanduser()
        if not explicit_path.is_absolute():
            explicit_path = project_root / explicit_path
        if not explicit_path.is_file():
            raise FileNotFoundError(
                f"ENV_FILE apunta a un archivo inexistente: {explicit_path}"
            )
        return explicit_path

    env_hint = os.getenv("ENVIRONMENT", "development")
    normalized_env = _normalize_environment(env_hint)
    env_file_suffix = "develop" if normalized_env == "development" else normalized_env
    env_file = project_root / f".env.{env_file_suffix}"
    if not env_file.is_file():
        raise FileNotFoundError(
            f"Archivo de entorno obligatorio no encontrado: {env_file}\n"
            f"Ambiente: {normalized_env} (ENVIRONMENT={env_hint!r}). "
            "Crea ese archivo en la raíz del proyecto o define ENV_FILE con la ruta a tu .env."
        )
    return env_file


ENV_FILE_USED = _resolve_env_file_path(PROJECT_ROOT)
load_dotenv(ENV_FILE_USED)
APP_ENV = _normalize_environment(os.getenv("ENVIRONMENT", "development"))

# ============================================================================
# ConfiguraciÃ³n de MBA3
# ============================================================================
# âš ï¸ IMPORTANTE: Configurar en .env (sin defaults por seguridad)
# En desarrollo puedes dejar vacÃ­o, pero en producciÃ³n es obligatorio

MBA3_BASE_URL = os.getenv("MBA3_BASE_URL", "")
MBA3_SERVICE_CODE = os.getenv("MBA3_CODIGO", os.getenv("MBA3_SERVICE_CODE", ""))
MBA3_SERVICE_PASSWORD = os.getenv("MBA3_PWD", os.getenv("MBA3_SERVICE_PASSWORD", ""))
MBA3_DIGEST_USERNAME = os.getenv("MBA3_DIGEST_USERNAME", MBA3_SERVICE_CODE)
MBA3_DIGEST_PASSWORD = os.getenv("MBA3_DIGEST_PASSWORD", MBA3_SERVICE_PASSWORD)

# ============================================================================
# ConfiguraciÃ³n de SQL Server (Principal - para almacenar datos)
# ============================================================================
# Para usar variables de entorno, configura en el archivo .env:
# - SQL_SERVER_DRIVER={ODBC Driver 18 for SQL Server}
# - SQL_SERVER_SERVER=tu_servidor
# - SQL_SERVER_DATABASE=tu_base_de_datos
# - SQL_SERVER_UID=tu_usuario (opcional para Windows Auth)
# - SQL_SERVER_PWD=tu_contraseÃ±a (opcional para Windows Auth)
# - ENABLE_SQL_SERVER_STORAGE=true

SQL_SERVER_DRIVER = os.getenv("SQL_SERVER_DRIVER", "{ODBC Driver 18 for SQL Server}")
SQL_SERVER_SERVER = os.getenv("SQL_SERVER_SERVER", "localhost")
SQL_SERVER_DATABASE = os.getenv("SQL_SERVER_DATABASE", "TuBaseDeDatos")
SQL_SERVER_UID = os.getenv("SQL_SERVER_UID", "")
SQL_SERVER_PWD = os.getenv("SQL_SERVER_PWD", "")

# Habilitar guardado en SQL Server (poner a False para deshabilitar)
ENABLE_SQL_SERVER_STORAGE = os.getenv("ENABLE_SQL_SERVER_STORAGE", "true").lower() == "true"

# ============================================================================
# ConfiguraciÃ³n de SQL Server SAP (para consultas OPENQUERY)
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
# ConfiguraciÃ³n de SAP (HANA)
# ============================================================================
# ConfiguraciÃ³n para consultas a SAP usando OPENQUERY desde SQL Server
# El servidor vinculado debe estar configurado en SQL Server como [MYHANADB]

# Nombre del servidor vinculado en SQL Server (configurado con OPENQUERY)
SAP_LINKED_SERVER = os.getenv("SAP_LINKED_SERVER", "MYHANADB")

# Base de datos y esquema de SAP
# Configurar en .env para no exponer nombres en el cÃ³digo
SAP_DATABASE = os.getenv("SAP_DATABASE", "")
SAP_SCHEMA = os.getenv("SAP_SCHEMA", "")

# Habilitar consultas a SAP (poner a False para deshabilitar)
ENABLE_SAP_QUERIES = os.getenv("ENABLE_SAP_QUERIES", "true").lower() == "true"

# Tiempo de vida del cache en dÃ­as (cuÃ¡ntos dÃ­as antes de re-consultar SAP)
SAP_CACHE_DAYS = int(os.getenv("SAP_CACHE_DAYS", "30"))

# ============================================================================
# ConfiguraciÃ³n de SAP Service Layer (API REST)
# ============================================================================
# Contrato validado con Postman: Login, PurchaseOrders, InventoryTransferRequests (puerto 50001).
# No hardcodear credenciales en servicios; usar variables de entorno.

# URL base (sin /Login). Prioridad: SAP_SL_BASE_URL > SAP_SERVICE_LAYER_URL
_sl_url = os.getenv("SAP_SL_BASE_URL") or os.getenv("SAP_SERVICE_LAYER_URL", "http://localhost:50001/b1s/v1")
SAP_SERVICE_LAYER_URL = _sl_url.rstrip("/").replace("/Login", "").replace("/login", "")

# CompanyDB, UserName, Password (Login). Compatibilidad con vars legacy.
SAP_COMPANY_DB = os.getenv("SAP_COMPANY_DB") or os.getenv("SAP_SERVICE_LAYER_DATABASE", "")
SAP_USER = os.getenv("SAP_USER") or os.getenv("SAP_SERVICE_LAYER_USERNAME", "")
SAP_PASSWORD = os.getenv("SAP_PASSWORD") or os.getenv("SAP_SERVICE_LAYER_PASSWORD", "")
SAP_SERVICE_LAYER_USERNAME = SAP_USER
SAP_SERVICE_LAYER_PASSWORD = SAP_PASSWORD
SAP_SERVICE_LAYER_DATABASE = SAP_COMPANY_DB

# Habilitar envÃ­o de ODC a SAP Service Layer
ENABLE_SAP_SERVICE_LAYER = os.getenv("ENABLE_SAP_SERVICE_LAYER", "false").lower() == "true"

# Timeout para requests a Service Layer (segundos)
SAP_SERVICE_LAYER_TIMEOUT = int(os.getenv("SAP_SERVICE_LAYER_TIMEOUT", "30"))

# Reintentos ante fallos transitorios (SL caído, RemoteDisconnected, timeouts, 502/503/504)
# Número de reintentos *adicionales* tras el primer intento (3 => hasta 4 intentos en total)
try:
    SAP_SERVICE_LAYER_TRANSIENT_RETRIES = max(0, int(os.getenv("SAP_SERVICE_LAYER_TRANSIENT_RETRIES", "3")))
except ValueError:
    SAP_SERVICE_LAYER_TRANSIENT_RETRIES = 3
try:
    SAP_SERVICE_LAYER_RETRY_BACKOFF_SECONDS = float(os.getenv("SAP_SERVICE_LAYER_RETRY_BACKOFF_SECONDS", "0.5"))
except ValueError:
    SAP_SERVICE_LAYER_RETRY_BACKOFF_SECONDS = 0.5

# VerificaciÃ³n SSL (deshabilitar solo para desarrollo/pruebas con certificados autofirmados)
# âš ï¸ ADVERTENCIA: Deshabilitar verificaciÃ³n SSL es inseguro. Solo usar en desarrollo/pruebas.
SAP_SERVICE_LAYER_VERIFY_SSL = os.getenv("SAP_SERVICE_LAYER_VERIFY_SSL", "true").lower() == "true"

# Bodega origen para InventoryTransferRequests (FromWarehouse).
# âš ï¸ REGLA: Solo se usa como FALLBACK si no hay codigo_bodega en la OC (que viene de Excel).
# Prioridad: 1) codigo_bodega de la OC (desde Excel), 2) SAP_ST_FROM_WAREHOUSE (fallback).
# Si estÃ¡ vacÃ­o y no hay bodega en la OC, las ITR no se crearÃ¡n.
SAP_ST_FROM_WAREHOUSE = os.getenv("SAP_ST_FROM_WAREHOUSE", "")

# Reintentos automáticos para Inventory Transfer Requests (ITR) por tienda.
# Se aplican cuando una ODC fue enviada pero algunas o todas las ITR fallan.
SAP_ITR_RETRY_MAX_ATTEMPTS = max(1, int(os.getenv("SAP_ITR_RETRY_MAX_ATTEMPTS", "3")))
SAP_ITR_RETRY_BASE_DELAY_SECONDS = max(0.1, float(os.getenv("SAP_ITR_RETRY_BASE_DELAY_SECONDS", "3.0")))
SAP_ITR_RETRY_MAX_JITTER_SECONDS = max(0.0, float(os.getenv("SAP_ITR_RETRY_MAX_JITTER_SECONDS", "1.0")))

# Reintentos automáticos para envío de ODC (Purchase Orders) a SAP Service Layer.
SAP_ODC_RETRY_MAX_ATTEMPTS = max(1, int(os.getenv("SAP_ODC_RETRY_MAX_ATTEMPTS", "3")))
SAP_ODC_RETRY_BASE_DELAY_SECONDS = max(0.1, float(os.getenv("SAP_ODC_RETRY_BASE_DELAY_SECONDS", "3.0")))
SAP_ODC_RETRY_MAX_JITTER_SECONDS = max(0.0, float(os.getenv("SAP_ODC_RETRY_MAX_JITTER_SECONDS", "1.0")))

# ============================================================================
# ConfiguraciÃ³n de Seguridad (Opcional)
# ============================================================================
# Todas las funcionalidades de seguridad estÃ¡n DESHABILITADAS por defecto
# ActÃ­valas configurando las variables a "true" en .env

# AutenticaciÃ³n mediante API Keys
ENABLE_AUTH = os.getenv("ENABLE_AUTH", "false").lower() == "true"
API_KEY = os.getenv("API_KEY", "")  # API Key requerida si ENABLE_AUTH=true

# AutenticaciÃ³n JWT (integraciÃ³n con SCNexus.Core)
# âš ï¸ DEBE SER LA MISMA CLAVE DEL CORE
# Configura estas variables en .env para que coincidan con appsettings.json del Core
JWT_SECRET = os.getenv('JWT_SECRET', 'clave_super_secreta_para_jwt_12345')
JWT_ISSUER = os.getenv('JWT_ISSUER', 'SCNexus.Core')
JWT_AUDIENCE = os.getenv('JWT_AUDIENCE', 'SCNexus.Users')

# ============================================================================
# ConfiguraciÃ³n de SCNexus.Core API (Active Directory)
# ============================================================================
# URL base del Core para llamadas a la API de permisos y otros servicios
# El Core gestiona la integraciÃ³n con Active Directory y asigna permisos
# a usuarios y roles de AD segÃºn las pÃ¡ginas a las que pueden tener acceso
CORE_API_URL = os.getenv("CORE_API_URL", "http://192.168.2.12:8080")
CORE_API_TIMEOUT = int(os.getenv("CORE_API_TIMEOUT", "30"))  # Timeout en segundos

# Habilitar autenticaciÃ³n JWT (requiere token vÃ¡lido del Core)
# Cuando estÃ¡ habilitado, los endpoints protegidos requerirÃ¡n JWT vÃ¡lido
ENABLE_JWT_AUTH = os.getenv("ENABLE_JWT_AUTH", "false").lower() == "true"

# Rate Limiting (lÃ­mite de requests)
ENABLE_RATE_LIMITING = os.getenv("ENABLE_RATE_LIMITING", "false").lower() == "true"
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")  # LÃ­mite por defecto

# CORS Restrictivo
ENABLE_CORS_RESTRICTION = os.getenv("ENABLE_CORS_RESTRICTION", "false").lower() == "true"
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")  # Lista separada por comas

# Ocultar Swagger en producciÃ³n
ENVIRONMENT = APP_ENV  # development, test, staging, production
HIDE_SWAGGER_IN_PROD = os.getenv("HIDE_SWAGGER_IN_PROD", "true").lower() == "true"

# ============================================================================
# Validaciones de Seguridad
# ============================================================================
logger = logging.getLogger(__name__)

# Validar configuraciones crÃ­ticas en producciÃ³n
if ENVIRONMENT == "production":
    # Validar MBA3
    if not MBA3_BASE_URL:
        raise ValueError(
            "âŒ MBA3_BASE_URL es obligatorio en producciÃ³n. "
            "Configura en .env"
        )
    if not MBA3_SERVICE_CODE:
        raise ValueError(
            "âŒ MBA3_SERVICE_CODE (o MBA3_CODIGO) es obligatorio en producciÃ³n. "
            "Configura en .env"
        )
    if not MBA3_SERVICE_PASSWORD:
        raise ValueError(
            "âŒ MBA3_SERVICE_PASSWORD (o MBA3_PWD) es obligatorio en producciÃ³n. "
            "Configura en .env"
        )
    
    # Validar JWT_SECRET si JWT está habilitado
    if ENABLE_JWT_AUTH:
        if not JWT_SECRET:
            raise ValueError(
                "JWT_SECRET debe configurarse en .env en produccion. No puede estar vacio."
            )
        if JWT_SECRET == 'clave_super_secreta_para_jwt_12345':
            logger.warning(
                "[TEMPORAL] JWT_SECRET usa valor por defecto (compatibilidad con Core). "
                "Cuando Core migre a secret seguro, actualizar mba3-consultas."
            )
    
    # Advertencia sobre SSL deshabilitado
    if ENABLE_SAP_SERVICE_LAYER and not SAP_SERVICE_LAYER_VERIFY_SSL:
        logger.warning("=" * 70)
        logger.warning("âš ï¸ ADVERTENCIA DE SEGURIDAD EN PRODUCCIÃ“N")
        logger.warning("   SAP_SERVICE_LAYER_VERIFY_SSL=false")
        logger.warning("   La verificaciÃ³n SSL estÃ¡ DESHABILITADA")
        logger.warning("   Esto es INSEGURO en producciÃ³n")
        logger.warning("   Considera usar certificados vÃ¡lidos")
        logger.warning("=" * 70)

# Warnings en desarrollo
elif ENVIRONMENT == "development":
    warnings_found = False
    
    if not MBA3_BASE_URL or not MBA3_SERVICE_CODE or not MBA3_SERVICE_PASSWORD:
        if not warnings_found:
            logger.warning("=" * 70)
            logger.warning("âš ï¸ CONFIGURACIÃ“N INCOMPLETA (Desarrollo)")
            warnings_found = True
        logger.warning("   Credenciales MBA3 no configuradas en .env")
    
    if ENABLE_JWT_AUTH and (not JWT_SECRET or JWT_SECRET == 'clave_super_secreta_para_jwt_12345'):
        if not warnings_found:
            logger.warning("=" * 70)
            logger.warning("âš ï¸ CONFIGURACIÃ“N INCOMPLETA (Desarrollo)")
            warnings_found = True
        logger.warning("   JWT_SECRET usando valor por defecto (inseguro)")
    
    if ENABLE_SAP_SERVICE_LAYER and not SAP_SERVICE_LAYER_VERIFY_SSL:
        if not warnings_found:
            logger.warning("=" * 70)
            logger.warning("âš ï¸ CONFIGURACIÃ“N INCOMPLETA (Desarrollo)")
            warnings_found = True
        logger.warning("   SAP SSL verification deshabilitada")
    
    if warnings_found:
        logger.warning("   Esto estÃ¡ OK para desarrollo, pero corrige en producciÃ³n")
        logger.warning("=" * 70)

# ============================================================================
# ConfiguraciÃ³n de MigraciÃ³n AutomÃ¡tica (LEGACY - deshabilitada por defecto)
# ============================================================================
# Habilitar migraciÃ³n automÃ¡tica (ejecuta /migrar cada N minutos).
# Por defecto false: no se programa en Celery Beat. Activar con ENABLE_AUTO_MIGRATE=true en .env
ENABLE_AUTO_MIGRATE = os.getenv("ENABLE_AUTO_MIGRATE", "false").lower() == "true"

# Intervalo en minutos entre ejecuciones automÃ¡ticas
# Configurar en .env: AUTO_MIGRATE_INTERVAL_MINUTES=15
AUTO_MIGRATE_INTERVAL_MINUTES = int(os.getenv("AUTO_MIGRATE_INTERVAL_MINUTES", "15"))

# DÃ­as hacia atrÃ¡s para el filtro de fecha en migraciÃ³n (automÃ¡tica y manual)
# Ambos procesos (automÃ¡tico y manual) usan la misma configuraciÃ³n
# Por defecto: 365 dÃ­as (1 aÃ±o) desde hoy
# Configurable en .env con MIGRATE_DATE_FILTER_DAYS
# 
# Compatibilidad hacia atrÃ¡s: Si existe AUTO_MIGRATE_DATE_FILTER_DAYS o 
# MANUAL_MIGRATE_DATE_FILTER_DAYS en .env, se usarÃ¡ ese valor.
# Si no, se usa MIGRATE_DATE_FILTER_DAYS o el valor por defecto (365).
_migrate_days = os.getenv("MIGRATE_DATE_FILTER_DAYS") or \
                os.getenv("AUTO_MIGRATE_DATE_FILTER_DAYS") or \
                os.getenv("MANUAL_MIGRATE_DATE_FILTER_DAYS") or \
                "365"
MIGRATE_DATE_FILTER_DAYS = int(_migrate_days)

# ============================================================================
# ConfiguraciÃ³n de Celery y Tareas Automatizadas
# ============================================================================
# âš ï¸ Configurar en .env para personalizar, o usar defaults para desarrollo

# URL de Redis para Celery (broker y backend)
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Horario de sincronizaciÃ³n de productos (hora en formato 24h)
SYNC_PRODUCTOS_HOUR = int(os.getenv('SYNC_PRODUCTOS_HOUR', '3'))  # Default: 3:00 AM
SYNC_PRODUCTOS_MINUTE = int(os.getenv('SYNC_PRODUCTOS_MINUTE', '0'))  # Default: minuto 0

# ============================================================================
# ConfiguraciÃ³n de Notificaciones por Email
# ============================================================================
# Habilitar notificaciones por correo electronico
ENABLE_EMAIL_NOTIFICATIONS = os.getenv("ENABLE_EMAIL_NOTIFICATIONS", "true").lower() == "true"

# ConfiguraciÃ³n SMTP (Outlook)
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "mabeltrading-com-ec.mail.protection.outlook.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "25"))  # Puerto 25 para relay interno (sin TLS)
EMAIL_SMTP_USER = os.getenv("EMAIL_SMTP_USER", "")
EMAIL_SMTP_PASSWORD = os.getenv("EMAIL_SMTP_PASSWORD", "")  # VacÃ­o para relay interno sin autenticaciÃ³n
# Perfil primario autenticado. Si hay usuario/password, se intenta primero este SMTP.
EMAIL_SMTP_AUTH_SERVER = os.getenv("EMAIL_SMTP_AUTH_SERVER", "smtp.office365.com")
EMAIL_SMTP_AUTH_PORT = int(os.getenv("EMAIL_SMTP_AUTH_PORT", "587"))
# Perfil secundario: relay interno sin autenticaciÃ³n.
EMAIL_SMTP_RELAY_SERVER = os.getenv("EMAIL_SMTP_RELAY_SERVER", EMAIL_SMTP_SERVER)
EMAIL_SMTP_RELAY_PORT = int(os.getenv("EMAIL_SMTP_RELAY_PORT", str(EMAIL_SMTP_PORT)))
# Timeout en segundos para conexiones SMTP (evita que la app quede colgada si el servidor no responde)
EMAIL_SMTP_TIMEOUT = float(os.getenv("EMAIL_SMTP_TIMEOUT", "5.0"))

# Direcciones de correo
EMAIL_FROM = os.getenv("EMAIL_FROM", "integrationsap@mabeltrading.com.ec")
# Nombre del remitente para los correos
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "INTEGRACIÃ“N SAP")

# EMAIL_TO - SEGMENTADO POR TIPO (fallback desde .env)
# La app lee primero de la tabla notificacion_destinatarios; si no hay datos, usa estas listas.
# Tipos: OPERACIONES, MABEL_TRADING, HOMOLOGACIONES, TECNICOS (ver get_destinatarios_por_tipo).
# Usuario Principal: Operaciones/Despachos (recibe notificaciones de NUEVOS DESPACHOS)
_email_operaciones = os.getenv("EMAIL_TO_OPERACIONES", "cortiz@mabeltrading.com.ec,pchafuel@mabeltrading.com.ec")
EMAIL_TO_OPERACIONES = [email.strip() for email in _email_operaciones.split(",") if email.strip()]

# Usuario Homologaciones: Productos no homologados (recibe notificaciones de SKUs faltantes)
_email_homologaciones = os.getenv("EMAIL_TO_HOMOLOGACIONES", "cortiz@mabeltrading.com.ec")
EMAIL_TO_HOMOLOGACIONES = [email.strip() for email in _email_homologaciones.split(",") if email.strip()]

# Usuario TÃ©cnico: Errores y advertencias del sistema (recibe notificaciones tÃ©cnicas)
_email_tecnicos = os.getenv("EMAIL_TO_TECNICOS", "cortiz@mabeltrading.com.ec")
EMAIL_TO_TECNICOS = [email.strip() for email in _email_tecnicos.split(",") if email.strip()]

# EMAIL_TO (legacy - para compatibilidad con cÃ³digo existente)
# Por defecto usa EMAIL_TO_OPERACIONES
_email_to_str = os.getenv("EMAIL_TO", _email_operaciones)
EMAIL_TO = [email.strip() for email in _email_to_str.split(",") if email.strip()]

# Email del proveedor para pruebas (FASE 6)
# Durante fase de pruebas, se usa este email para notificaciones de ODC
# TODO: En producciÃ³n, obtener desde tabla cliente usando CardCode
EMAIL_PROVEEDOR_PRUEBAS = os.getenv("EMAIL_PROVEEDOR_PRUEBAS", "cortiz@mabeltrading.com.ec")

# Email de MABEL TRADING para notificaciones de confirmacion de pedidos
# Usado cuando EL RAYO confirma un pedido y se debe notificar a MABEL TRADING
_email_mabel_trading = os.getenv("EMAIL_MABEL_TRADING", "cortiz@mabeltrading.com.ec,pchafuel@mabeltrading.com.ec")
EMAIL_MABEL_TRADING = [email.strip() for email in _email_mabel_trading.split(",") if email.strip()]

# Override en desarrollo: todos los correos van a este destinatario (ignora BD).
# Solo aplica cuando ENVIRONMENT=development. En producción no se usa.
_email_dev_override_str = os.getenv("EMAIL_DEV_OVERRIDE", "")
EMAIL_DEV_OVERRIDE = [e.strip() for e in _email_dev_override_str.split(",") if e.strip()]

# ConfiguraciÃ³n de advertencias tÃ©cnicas
# Porcentaje del time limit para enviar advertencia
EMAIL_WARNING_TIME_LIMIT_PERCENT = int(os.getenv("EMAIL_WARNING_TIME_LIMIT_PERCENT", "80"))
# NÃºmero de facturas que se considera "alto" para advertir
EMAIL_WARNING_HIGH_VOLUME_THRESHOLD = int(os.getenv("EMAIL_WARNING_HIGH_VOLUME_THRESHOLD", "500"))
# NÃºmero de fallos en 24h para advertir
EMAIL_WARNING_FAILURES_THRESHOLD = int(os.getenv("EMAIL_WARNING_FAILURES_THRESHOLD", "3"))

# ============================================================================
# Configuración de Storage de Archivos (MinIO/S3)
# ============================================================================
# Tamaño máximo de archivo Excel para uploads (en MB)
try:
    MAX_EXCEL_UPLOAD_SIZE_MB = int(os.getenv("MAX_EXCEL_UPLOAD_SIZE_MB", "10"))
except ValueError:
    MAX_EXCEL_UPLOAD_SIZE_MB = 10
MAX_EXCEL_UPLOAD_SIZE_MB = max(1, MAX_EXCEL_UPLOAD_SIZE_MB)
MAX_EXCEL_UPLOAD_SIZE_BYTES = MAX_EXCEL_UPLOAD_SIZE_MB * 1024 * 1024

# Habilitar almacenamiento de archivos Excel originales para descarga posterior
ENABLE_FILE_STORAGE = os.getenv("ENABLE_FILE_STORAGE", "false").lower() == "true"

# Configuración del storage (compatible con S3 y MinIO)
FILE_STORAGE_ENDPOINT = os.getenv("FILE_STORAGE_ENDPOINT", "http://localhost:9000")
FILE_STORAGE_ACCESS_KEY = os.getenv("FILE_STORAGE_ACCESS_KEY", "minioadmin")
FILE_STORAGE_SECRET_KEY = os.getenv("FILE_STORAGE_SECRET_KEY", "minioadmin")
FILE_STORAGE_BUCKET = os.getenv("FILE_STORAGE_BUCKET", "plantillas-excel")
FILE_STORAGE_REGION = os.getenv("FILE_STORAGE_REGION", "us-east-1")

# Validar configuración de storage en producción
if ENVIRONMENT == "production" and ENABLE_FILE_STORAGE:
    if FILE_STORAGE_ACCESS_KEY == "minioadmin":
        logger.warning(
            "⚠️ FILE_STORAGE usando credenciales por defecto en producción. "
            "Configura FILE_STORAGE_ACCESS_KEY y FILE_STORAGE_SECRET_KEY en .env"
        )

# ============================================================================
# Queries Predefinidas
# ============================================================================
# Query SQL predefinida para consultar facturas desde MBA3
# Usada en los endpoints /consultar y /migrar
MBA3_QUERY_PREDEFINIDA = (
    "SELECT CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,"
    "CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,"
    "ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada,"
    "CONFIRMADO,CODIGO_BODEGA "
    "FROM CLNT_FACTURA_PRINCIPAL "
    "WHERE TIPO_DOCUMENTO='REM' AND ANULADA='false' AND CONFIRMADO='true' "
    "AND Remision_Facturada='false' AND CODIGO_DESPACHO=0 AND NUMERO_FACTURA > 0 "
    "AND ObjDatosFactura IS NOT NULL"
)

# Query SQL predefinida para consultar documentos de remisiÃ³n sin detalles
# Usada en el endpoint /remisiones/consultar
# Estos documentos no tienen ObjDatosFactura ni detalles asociados
MBA3_QUERY_REMISIONES = (
    "SELECT CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,FACTURA_IMPRESA,"
    "NUMERO_FACTURA,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,"
    "ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,CONFIRMADO "
    "FROM CLNT_FACTURA_PRINCIPAL "
    "WHERE TIPO_DOCUMENTO='REM' AND CONFIRMADO='false' AND Remision_Facturada='false' "
    "AND ObjDatosFactura IS NULL AND FACTURA_IMPRESA='false' AND ANULADA='false'"
)# ============================================================================
# ConfiguraciÃ³n de Staging de Productos
# ============================================================================
# Activar staging para productos (maestros MBA3 y SAP)
USE_PRODUCT_STAGING = os.getenv("USE_PRODUCT_STAGING", "true").lower() == "true"
# Permitir fallback a ERP si staging falla (solo fuera de producción)
ALLOW_ERP_FALLBACK = os.getenv("ALLOW_ERP_FALLBACK", "false").lower() == "true" and ENVIRONMENT != "production"