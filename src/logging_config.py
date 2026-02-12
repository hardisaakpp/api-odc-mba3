"""
Configuración centralizada de logging para la aplicación.

Implementa las buenas prácticas de logging (Guía Sección 5):
- Logs técnicos: fecha, usuario, endpoint, request, response, tiempo
- Logs funcionales: id_usuario, monto, id_tienda, id_transaccion
- Rotación de archivos para evitar llenar disco
- Formato estructurado para análisis

Uso:
    from src.logging_config import setup_logging, log_business_operation
    
    # Al inicio de la aplicación
    setup_logging()
    
    # Para logs funcionales/de negocio
    log_business_operation(
        operation="crear_pedido",
        id_usuario="user123",
        id_tienda="T001",
        id_transaccion="abc-123",
        monto=1500.00,
        detalles={"items": 5}
    )
"""

import os
import logging
import json
from datetime import datetime

from src.utils.timezone import ahora, ahora_naive
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional, Any, Dict

# ============================================================================
# Configuración de Logging
# ============================================================================
# NOTA: No importamos de src.config para evitar dependencias circulares
# Las variables se obtienen directamente del entorno o se calculan aquí

# Calcular PROJECT_ROOT (igual que en config.py)
_current_file = Path(__file__).resolve()
if _current_file.parent.name == "src":
    PROJECT_ROOT = _current_file.parent.parent
else:
    PROJECT_ROOT = _current_file.parent

# Obtener ambiente directamente del entorno
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Directorio para archivos de log
LOG_DIR = PROJECT_ROOT / "logs"

# Tamaño máximo de archivo de log (10 MB)
MAX_LOG_FILE_SIZE = 10 * 1024 * 1024

# Número de archivos de backup a mantener
BACKUP_COUNT = 5

# Nivel de log según ambiente
LOG_LEVEL = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO


class JsonFormatter(logging.Formatter):
    """
    Formatter que genera logs en formato JSON para análisis.
    
    Útil para integración con sistemas de monitoreo como ELK, Splunk, etc.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": ahora().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Agregar campos extra si existen
        correlation_id = getattr(record, 'correlation_id', None)
        if correlation_id is not None:
            log_data['correlation_id'] = correlation_id
        user = getattr(record, 'user', None)
        if user is not None:
            log_data['user'] = user
        extra_data = getattr(record, 'extra_data', None)
        if extra_data is not None:
            log_data['data'] = extra_data
        
        # Agregar excepción si existe
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """
    Formatter legible para consola con colores y emojis.
    """
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        # Formato base
        timestamp = ahora_naive().strftime('%Y-%m-%d %H:%M:%S')
        level = record.levelname
        
        # Color según nivel (solo si es terminal)
        color = self.COLORS.get(level, '')
        reset = self.RESET if color else ''
        
        # Construir mensaje
        message = f"{timestamp} - {color}{level}{reset} - {record.getMessage()}"
        
        # Agregar excepción si existe
        if record.exc_info:
            message += f"\n{self.formatException(record.exc_info)}"
        
        return message


def setup_logging() -> None:
    """
    Configura el sistema de logging de la aplicación.
    
    Configura:
    - Handler de consola (formato legible)
    - Handler de archivo con rotación por tamaño (formato JSON)
    - Handler de archivo con rotación diaria para errores
    
    Los logs se guardan en el directorio 'logs/' del proyecto.
    """
    # Crear directorio de logs si no existe
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Obtener logger raíz
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)
    
    # Limpiar handlers existentes para evitar duplicados
    root_logger.handlers.clear()
    
    # ========================================
    # Handler 1: Consola (formato legible)
    # ========================================
    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_LEVEL)
    console_handler.setFormatter(ConsoleFormatter())
    root_logger.addHandler(console_handler)
    
    # ========================================
    # Handler 2: Archivo general con rotación por tamaño
    # ========================================
    general_log_file = LOG_DIR / "api.log"
    file_handler = RotatingFileHandler(
        filename=str(general_log_file),
        maxBytes=MAX_LOG_FILE_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(JsonFormatter())
    root_logger.addHandler(file_handler)
    
    # ========================================
    # Handler 3: Archivo de errores con rotación diaria
    # ========================================
    error_log_file = LOG_DIR / "errors.log"
    error_handler = TimedRotatingFileHandler(
        filename=str(error_log_file),
        when='midnight',
        interval=1,
        backupCount=30,  # Mantener 30 días de errores
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JsonFormatter())
    root_logger.addHandler(error_handler)
    
    # ========================================
    # Handler 4: Archivo de logs de negocio
    # ========================================
    business_log_file = LOG_DIR / "business.log"
    business_handler = RotatingFileHandler(
        filename=str(business_log_file),
        maxBytes=MAX_LOG_FILE_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    business_handler.setLevel(logging.INFO)
    business_handler.setFormatter(JsonFormatter())
    
    # Logger específico para operaciones de negocio
    business_logger = logging.getLogger('business')
    business_logger.addHandler(business_handler)
    business_logger.setLevel(logging.INFO)
    
    # Log de inicio
    logging.info(f"✅ Sistema de logging configurado")
    logging.info(f"   📁 Directorio de logs: {LOG_DIR}")
    logging.info(f"   📝 Log general: {general_log_file}")
    logging.info(f"   ❌ Log de errores: {error_log_file}")
    logging.info(f"   💼 Log de negocio: {business_log_file}")
    logging.info(f"   🔧 Nivel: {logging.getLevelName(LOG_LEVEL)}")


# ============================================================================
# Helper para Logs Funcionales (Negocio)
# ============================================================================

# Logger específico para operaciones de negocio
_business_logger = logging.getLogger('business')


def log_business_operation(
    operation: str,
    id_usuario: Optional[str] = None,
    id_tienda: Optional[str] = None,
    id_transaccion: Optional[str] = None,
    monto: Optional[float] = None,
    success: bool = True,
    detalles: Optional[Dict[str, Any]] = None,
    **kwargs
) -> None:
    """
    Registra una operación de negocio con contexto estandarizado.
    
    Cumple con las buenas prácticas de logs funcionales (Sección 5):
    - id_usuario: identificador del usuario que realiza la operación
    - monto: valor monetario si aplica
    - id_tienda: identificador de la tienda si aplica
    - id_transaccion: identificador único de la transacción/correlación
    
    Args:
        operation: Nombre de la operación (ej: "crear_pedido", "cancelar_odc")
        id_usuario: ID o username del usuario
        id_tienda: ID o código de la tienda
        id_transaccion: ID de correlación/transacción (puede ser correlation_id)
        monto: Monto monetario si la operación involucra dinero
        success: Si la operación fue exitosa
        detalles: Diccionario con detalles adicionales específicos
        **kwargs: Campos adicionales para logging
        
    Ejemplo:
        log_business_operation(
            operation="crear_pedido",
            id_usuario="jperez",
            id_tienda="T001",
            id_transaccion="abc-123-def",
            monto=15000.50,
            detalles={"items": 10, "proveedor": "ACME"}
        )
    """
    # Construir datos del log
    log_data = {
        "timestamp": ahora().isoformat(),
        "operation": operation,
        "success": success,
        "id_usuario": id_usuario,
        "id_tienda": id_tienda,
        "id_transaccion": id_transaccion,
        "monto": monto,
    }
    
    # Agregar detalles si existen
    if detalles:
        log_data["detalles"] = detalles
    
    # Agregar kwargs adicionales
    log_data.update(kwargs)
    
    # Filtrar valores None para un log más limpio
    log_data = {k: v for k, v in log_data.items() if v is not None}
    
    # Crear mensaje legible
    status_icon = "✅" if success else "❌"
    user_str = f"User:{id_usuario}" if id_usuario else "User:system"
    
    message_parts = [
        f"{status_icon} [BUSINESS]",
        operation.upper(),
        user_str,
    ]
    
    if id_tienda:
        message_parts.append(f"Tienda:{id_tienda}")
    if id_transaccion:
        message_parts.append(f"TxID:{id_transaccion[:8]}...")
    if monto is not None:
        message_parts.append(f"Monto:${monto:,.2f}")
    
    message = " - ".join(message_parts)
    
    # Crear registro con datos extra
    extra: Dict[str, Any] = {'extra_data': log_data}
    if id_transaccion:
        extra['correlation_id'] = id_transaccion
    if id_usuario:
        extra['user'] = id_usuario
    
    # Registrar en el logger de negocio
    if success:
        _business_logger.info(message, extra=extra)
    else:
        _business_logger.error(message, extra=extra)
    
    # También registrar en el logger general para visibilidad
    logger = logging.getLogger(__name__)
    if success:
        logger.info(message)
    else:
        logger.error(message)


def get_correlation_id_from_request(request) -> Optional[str]:
    """
    Obtiene el correlation_id del request state.
    
    Útil para usar en logs funcionales el mismo ID de correlación
    que se generó en el middleware.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        correlation_id o None si no existe
    """
    if hasattr(request, 'state') and hasattr(request.state, 'correlation_id'):
        return request.state.correlation_id
    return None
