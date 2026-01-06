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
# ⚠️ IMPORTANTE: Configurar en .env (sin defaults por seguridad)
# En desarrollo puedes dejar vacío, pero en producción es obligatorio

MBA3_BASE_URL = os.getenv("MBA3_BASE_URL", "")
MBA3_SERVICE_CODE = os.getenv("MBA3_CODIGO", os.getenv("MBA3_SERVICE_CODE", ""))
MBA3_SERVICE_PASSWORD = os.getenv("MBA3_PWD", os.getenv("MBA3_SERVICE_PASSWORD", ""))
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
# Configurar en .env para no exponer nombres en el código
SAP_DATABASE = os.getenv("SAP_DATABASE", "")
SAP_SCHEMA = os.getenv("SAP_SCHEMA", "")

# Habilitar consultas a SAP (poner a False para deshabilitar)
ENABLE_SAP_QUERIES = os.getenv("ENABLE_SAP_QUERIES", "true").lower() == "true"

# Tiempo de vida del cache en días (cuántos días antes de re-consultar SAP)
SAP_CACHE_DAYS = int(os.getenv("SAP_CACHE_DAYS", "30"))

# ============================================================================
# Configuración de SAP Service Layer (API REST)
# ============================================================================
# Configuración para enviar órdenes de compra a SAP Business One usando Service Layer

# URL base del Service Layer (ej: http://localhost:50000/b1s/v1)
SAP_SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "http://localhost:50000/b1s/v1")

# Credenciales de autenticación
SAP_SERVICE_LAYER_USERNAME = os.getenv("SAP_SERVICE_LAYER_USERNAME", "")
SAP_SERVICE_LAYER_PASSWORD = os.getenv("SAP_SERVICE_LAYER_PASSWORD", "")
SAP_SERVICE_LAYER_DATABASE = os.getenv("SAP_SERVICE_LAYER_DATABASE", "")

# Habilitar envío de ODC a SAP Service Layer
ENABLE_SAP_SERVICE_LAYER = os.getenv("ENABLE_SAP_SERVICE_LAYER", "false").lower() == "true"

# Timeout para requests a Service Layer (segundos)
SAP_SERVICE_LAYER_TIMEOUT = int(os.getenv("SAP_SERVICE_LAYER_TIMEOUT", "30"))

# Verificación SSL (deshabilitar solo para desarrollo/pruebas con certificados autofirmados)
# ⚠️ ADVERTENCIA: Deshabilitar verificación SSL es inseguro. Solo usar en desarrollo/pruebas.
SAP_SERVICE_LAYER_VERIFY_SSL = os.getenv("SAP_SERVICE_LAYER_VERIFY_SSL", "true").lower() == "true"

# ============================================================================
# Configuración de Seguridad (Opcional)
# ============================================================================
# Todas las funcionalidades de seguridad están DESHABILITADAS por defecto
# Actívalas configurando las variables a "true" en .env

# Autenticación mediante API Keys
ENABLE_AUTH = os.getenv("ENABLE_AUTH", "false").lower() == "true"
API_KEY = os.getenv("API_KEY", "")  # API Key requerida si ENABLE_AUTH=true

# Autenticación JWT (integración con SCNexus.Core)
# ⚠️ DEBE SER LA MISMA CLAVE DEL CORE
# Configura estas variables en .env para que coincidan con appsettings.json del Core
JWT_SECRET = os.getenv('JWT_SECRET', 'clave_super_secreta_para_jwt_12345')
JWT_ISSUER = os.getenv('JWT_ISSUER', 'SCNexus.Core')
JWT_AUDIENCE = os.getenv('JWT_AUDIENCE', 'SCNexus.Users')

# Habilitar autenticación JWT (requiere token válido del Core)
# Cuando está habilitado, los endpoints protegidos requerirán JWT válido
ENABLE_JWT_AUTH = os.getenv("ENABLE_JWT_AUTH", "false").lower() == "true"

# Rate Limiting (límite de requests)
ENABLE_RATE_LIMITING = os.getenv("ENABLE_RATE_LIMITING", "false").lower() == "true"
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")  # Límite por defecto

# CORS Restrictivo
ENABLE_CORS_RESTRICTION = os.getenv("ENABLE_CORS_RESTRICTION", "false").lower() == "true"
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")  # Lista separada por comas

# Ocultar Swagger en producción
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")  # development, staging, production
HIDE_SWAGGER_IN_PROD = os.getenv("HIDE_SWAGGER_IN_PROD", "true").lower() == "true"

# ============================================================================
# Validaciones de Seguridad
# ============================================================================
import logging
logger = logging.getLogger(__name__)

# Validar configuraciones críticas en producción
if ENVIRONMENT == "production":
    # Validar MBA3
    if not MBA3_BASE_URL:
        raise ValueError(
            "❌ MBA3_BASE_URL es obligatorio en producción. "
            "Configura en .env"
        )
    if not MBA3_SERVICE_CODE:
        raise ValueError(
            "❌ MBA3_SERVICE_CODE (o MBA3_CODIGO) es obligatorio en producción. "
            "Configura en .env"
        )
    if not MBA3_SERVICE_PASSWORD:
        raise ValueError(
            "❌ MBA3_SERVICE_PASSWORD (o MBA3_PWD) es obligatorio en producción. "
            "Configura en .env"
        )
    
    # Validar JWT_SECRET si JWT está habilitado
    if ENABLE_JWT_AUTH:
        if not JWT_SECRET or JWT_SECRET == 'clave_super_secreta_para_jwt_12345':
            raise ValueError(
                "❌ JWT_SECRET debe configurarse en .env en producción con un valor seguro. "
                "No usar la clave por defecto. Genera una con: "
                "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
    
    # Advertencia sobre SSL deshabilitado
    if ENABLE_SAP_SERVICE_LAYER and not SAP_SERVICE_LAYER_VERIFY_SSL:
        logger.warning("=" * 70)
        logger.warning("⚠️ ADVERTENCIA DE SEGURIDAD EN PRODUCCIÓN")
        logger.warning("   SAP_SERVICE_LAYER_VERIFY_SSL=false")
        logger.warning("   La verificación SSL está DESHABILITADA")
        logger.warning("   Esto es INSEGURO en producción")
        logger.warning("   Considera usar certificados válidos")
        logger.warning("=" * 70)

# Warnings en desarrollo
elif ENVIRONMENT == "development":
    warnings_found = False
    
    if not MBA3_BASE_URL or not MBA3_SERVICE_CODE or not MBA3_SERVICE_PASSWORD:
        if not warnings_found:
            logger.warning("=" * 70)
            logger.warning("⚠️ CONFIGURACIÓN INCOMPLETA (Desarrollo)")
            warnings_found = True
        logger.warning("   Credenciales MBA3 no configuradas en .env")
    
    if ENABLE_JWT_AUTH and (not JWT_SECRET or JWT_SECRET == 'clave_super_secreta_para_jwt_12345'):
        if not warnings_found:
            logger.warning("=" * 70)
            logger.warning("⚠️ CONFIGURACIÓN INCOMPLETA (Desarrollo)")
            warnings_found = True
        logger.warning("   JWT_SECRET usando valor por defecto (inseguro)")
    
    if ENABLE_SAP_SERVICE_LAYER and not SAP_SERVICE_LAYER_VERIFY_SSL:
        if not warnings_found:
            logger.warning("=" * 70)
            logger.warning("⚠️ CONFIGURACIÓN INCOMPLETA (Desarrollo)")
            warnings_found = True
        logger.warning("   SAP SSL verification deshabilitada")
    
    if warnings_found:
        logger.warning("   Esto está OK para desarrollo, pero corrige en producción")
        logger.warning("=" * 70)

# ============================================================================
# Configuración de Migración Automática
# ============================================================================
# Habilitar migración automática (ejecuta /migrar cada N minutos)
ENABLE_AUTO_MIGRATE = os.getenv("ENABLE_AUTO_MIGRATE", "true").lower() == "true"

# Intervalo en minutos entre ejecuciones automáticas
# Configurar en .env: AUTO_MIGRATE_INTERVAL_MINUTES=15
AUTO_MIGRATE_INTERVAL_MINUTES = int(os.getenv("AUTO_MIGRATE_INTERVAL_MINUTES", "15"))

# Días hacia atrás para el filtro de fecha en migración (automática y manual)
# Ambos procesos (automático y manual) usan la misma configuración
# Por defecto: 365 días (1 año) desde hoy
# Configurable en .env con MIGRATE_DATE_FILTER_DAYS
# 
# Compatibilidad hacia atrás: Si existe AUTO_MIGRATE_DATE_FILTER_DAYS o 
# MANUAL_MIGRATE_DATE_FILTER_DAYS en .env, se usará ese valor.
# Si no, se usa MIGRATE_DATE_FILTER_DAYS o el valor por defecto (365).
_migrate_days = os.getenv("MIGRATE_DATE_FILTER_DAYS") or \
                os.getenv("AUTO_MIGRATE_DATE_FILTER_DAYS") or \
                os.getenv("MANUAL_MIGRATE_DATE_FILTER_DAYS") or \
                "365"
MIGRATE_DATE_FILTER_DAYS = int(_migrate_days)

# ============================================================================
# Configuración de Celery y Tareas Automatizadas
# ============================================================================
# ⚠️ Configurar en .env para personalizar, o usar defaults para desarrollo

# URL de Redis para Celery (broker y backend)
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Horario de sincronización de productos (hora en formato 24h)
SYNC_PRODUCTOS_HOUR = int(os.getenv('SYNC_PRODUCTOS_HOUR', '3'))  # Default: 3:00 AM
SYNC_PRODUCTOS_MINUTE = int(os.getenv('SYNC_PRODUCTOS_MINUTE', '0'))  # Default: minuto 0

# ============================================================================
# Configuración de Notificaciones por Email
# ============================================================================
# Habilitar notificaciones por correo electrónico
ENABLE_EMAIL_NOTIFICATIONS = os.getenv("ENABLE_EMAIL_NOTIFICATIONS", "true").lower() == "true"

# Configuración SMTP (Outlook)
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "mabeltrading-com-ec.mail.protection.outlook.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "25"))  # Puerto 25 para relay interno (sin TLS)
EMAIL_SMTP_USER = os.getenv("EMAIL_SMTP_USER", "")
EMAIL_SMTP_PASSWORD = os.getenv("EMAIL_SMTP_PASSWORD", "")  # Vacío para relay interno sin autenticación

# Direcciones de correo
EMAIL_FROM = os.getenv("EMAIL_FROM", "integrationsap@mabeltrading.com.ec")
# Nombre del remitente para los correos
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "INTEGRACIÓN SAP")

# EMAIL_TO - SEGMENTADO POR TIPO DE USUARIO
# Usuario Principal: Operaciones/Despachos (recibe notificaciones de NUEVOS DESPACHOS)
_email_operaciones = os.getenv("EMAIL_TO_OPERACIONES", "cortiz@mabeltrading.com.ec")
EMAIL_TO_OPERACIONES = [email.strip() for email in _email_operaciones.split(",") if email.strip()]

# Usuario Homologaciones: Productos no homologados (recibe notificaciones de SKUs faltantes)
_email_homologaciones = os.getenv("EMAIL_TO_HOMOLOGACIONES", "cortiz@mabeltrading.com.ec")
EMAIL_TO_HOMOLOGACIONES = [email.strip() for email in _email_homologaciones.split(",") if email.strip()]

# Usuario Técnico: Errores y advertencias del sistema (recibe notificaciones técnicas)
_email_tecnicos = os.getenv("EMAIL_TO_TECNICOS", "cortiz@mabeltrading.com.ec")
EMAIL_TO_TECNICOS = [email.strip() for email in _email_tecnicos.split(",") if email.strip()]

# EMAIL_TO (legacy - para compatibilidad con código existente)
# Por defecto usa EMAIL_TO_OPERACIONES
_email_to_str = os.getenv("EMAIL_TO", _email_operaciones)
EMAIL_TO = [email.strip() for email in _email_to_str.split(",") if email.strip()]

# Email del proveedor para pruebas (FASE 6)
# Durante fase de pruebas, se usa este email para notificaciones de ODC
# TODO: En producción, obtener desde tabla cliente usando CardCode
EMAIL_PROVEEDOR_PRUEBAS = os.getenv("EMAIL_PROVEEDOR_PRUEBAS", "cortiz@mabeltrading.com.ec")


# Configuración de advertencias técnicas
# Porcentaje del time limit para enviar advertencia
EMAIL_WARNING_TIME_LIMIT_PERCENT = int(os.getenv("EMAIL_WARNING_TIME_LIMIT_PERCENT", "80"))
# Número de facturas que se considera "alto" para advertir
EMAIL_WARNING_HIGH_VOLUME_THRESHOLD = int(os.getenv("EMAIL_WARNING_HIGH_VOLUME_THRESHOLD", "500"))
# Número de fallos en 24h para advertir
EMAIL_WARNING_FAILURES_THRESHOLD = int(os.getenv("EMAIL_WARNING_FAILURES_THRESHOLD", "3"))

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

# Query SQL predefinida para consultar documentos de remisión sin detalles
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
# Configuración de Staging de Productos
# ============================================================================
# Activar staging para productos (maestros MBA3 y SAP)
USE_PRODUCT_STAGING = os.getenv("USE_PRODUCT_STAGING", "true").lower() == "true"# Permitir fallback a ERP si staging falla (solo en desarrollo)
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")  # 'development' | 'production'
ALLOW_ERP_FALLBACK = os.getenv("ALLOW_ERP_FALLBACK", "false").lower() == "true" and ENVIRONMENT != "production"