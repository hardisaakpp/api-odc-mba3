"""
Contexto de auditoría para operaciones de base de datos.

Proporciona funciones helper para extraer y gestionar información de auditoría
que debe incluirse en las operaciones INSERT/UPDATE según las buenas prácticas
(Sección 3 - Campos de auditoría).

Campos de auditoría:
- creado_por: Usuario que creó el registro
- creado_fecha: Fecha/hora de creación (manejado por DB con DEFAULT)
- modificado_por: Usuario que realizó la última modificación
- modificado_fecha: Fecha/hora de la última modificación
- origen: Fuente del registro ('API', 'WEB', 'EXCEL', 'CELERY', 'MANUAL')
- ip_origen: Dirección IP del cliente

Uso:
    from src.utils.audit_context import AuditContext, get_audit_context
    
    # En un endpoint con request
    audit = get_audit_context(request, user)
    repository.create_pedido(data, audit_context=audit)
    
    # En una tarea Celery (sin request)
    audit = AuditContext(
        usuario="celery_worker",
        origen="CELERY",
        ip_origen=None
    )
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import Request

from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)


# Valores válidos para el campo 'origen'
ORIGEN_API = "API"
ORIGEN_WEB = "WEB"
ORIGEN_EXCEL = "EXCEL"
ORIGEN_CELERY = "CELERY"
ORIGEN_MANUAL = "MANUAL"
ORIGEN_LEGACY = "LEGACY"
ORIGEN_SYSTEM = "SYSTEM"

ORIGENES_VALIDOS = {ORIGEN_API, ORIGEN_WEB, ORIGEN_EXCEL, ORIGEN_CELERY, ORIGEN_MANUAL, ORIGEN_LEGACY, ORIGEN_SYSTEM}


@dataclass
class AuditContext:
    """
    Contexto de auditoría para operaciones de base de datos.
    
    Contiene la información necesaria para poblar los campos de auditoría
    en operaciones INSERT y UPDATE.
    
    Attributes:
        usuario: Username del usuario que realiza la operación
        origen: Fuente de la operación (API, WEB, EXCEL, CELERY, MANUAL)
        ip_origen: Dirección IP del cliente (None para operaciones internas)
        fecha: Fecha/hora de la operación (auto-generada si no se especifica)
    """
    usuario: Optional[str] = None
    origen: str = ORIGEN_API
    ip_origen: Optional[str] = None
    fecha: datetime = field(default_factory=ahora_naive)
    
    def __post_init__(self):
        """Valida y normaliza los valores."""
        # Validar origen
        if self.origen not in ORIGENES_VALIDOS:
            self.origen = ORIGEN_API
        
        # Normalizar usuario vacío
        if not self.usuario:
            self.usuario = "SYSTEM"
        
        # Truncar IP si es muy larga (IPv6 máximo 45 chars)
        if self.ip_origen and len(self.ip_origen) > 45:
            self.ip_origen = self.ip_origen[:45]
    
    def to_insert_dict(self) -> Dict[str, Any]:
        """
        Retorna diccionario con campos para INSERT.
        
        Returns:
            Dict con: creado_por, origen, ip_origen
        """
        return {
            "creado_por": self.usuario,
            "origen": self.origen,
            "ip_origen": self.ip_origen,
        }
    
    def to_update_dict(self) -> Dict[str, Any]:
        """
        Retorna diccionario con campos para UPDATE.
        
        Returns:
            Dict con: modificado_por, modificado_fecha, origen, ip_origen
        """
        return {
            "modificado_por": self.usuario,
            "modificado_fecha": self.fecha,
            "origen": self.origen,
            "ip_origen": self.ip_origen,
        }
    
    def get_creado_por(self) -> str:
        """Retorna el usuario para campo creado_por."""
        return self.usuario or "SYSTEM"
    
    def get_modificado_por(self) -> str:
        """Retorna el usuario para campo modificado_por."""
        return self.usuario or "SYSTEM"


def get_client_ip(request: Request) -> Optional[str]:
    """
    Extrae la IP del cliente del request.
    
    Orden de prioridad:
    1. X-Forwarded-For (primer IP si hay múltiples)
    2. X-Real-IP
    3. request.client.host
    
    Args:
        request: FastAPI Request object
        
    Returns:
        IP del cliente o None si no se puede determinar
    """
    if not request:
        return None
    
    # X-Forwarded-For (puede tener múltiples IPs separadas por coma)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Tomar la primera IP (cliente original)
        return forwarded_for.split(",")[0].strip()
    
    # X-Real-IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # IP directa del cliente
    if request.client:
        return request.client.host
    
    return None


def get_username_from_user(user: Optional[Dict[str, Any]]) -> str:
    """
    Extrae el username del diccionario de usuario (JWT decodificado).
    
    Args:
        user: Diccionario con datos del usuario del JWT
        
    Returns:
        Username o 'SYSTEM' si no se puede determinar
    """
    if not user:
        return "SYSTEM"
    
    # Priorizar email para usuarios AD (más legible que UUID)
    # El orden de prioridad asegura que se use información legible antes que IDs técnicos
    username = (
        user.get("email") or      # PRIMERO: Email (más legible para usuarios AD)
        user.get("username") or   # Segundo: Username
        user.get("name") or       # Tercero: Name
        user.get("sub") or        # Cuarto: Subject
        user.get("user_id") or    # Quinto: User ID alternativo
        user.get("id")            # ÚLTIMO RECURSO: UUID (para compatibilidad)
    )
    
    return str(username) if username else "SYSTEM"


def get_audit_context(
    request: Optional[Request] = None,
    user: Optional[Dict[str, Any]] = None,
    origen: str = ORIGEN_API
) -> AuditContext:
    """
    Crea un contexto de auditoría desde el request y usuario.
    
    Esta es la función principal para obtener el contexto de auditoría
    en endpoints de FastAPI.
    
    Args:
        request: FastAPI Request (para extraer IP)
        user: Diccionario de usuario del JWT (para extraer username)
        origen: Tipo de origen ('API', 'WEB', 'EXCEL', etc.)
        
    Returns:
        AuditContext con la información extraída
        
    Example:
        @app.post("/api/pedidos")
        async def crear_pedido(
            request: Request,
            user: Dict = Depends(verify_jwt_token)
        ):
            audit = get_audit_context(request, user, origen=ORIGEN_WEB)
            repository.create(data, audit_context=audit)
    """
    return AuditContext(
        usuario=get_username_from_user(user),
        origen=origen,
        ip_origen=get_client_ip(request) if request else None,
        fecha=ahora_naive()
    )


def get_celery_audit_context(task_name: str = "celery_task") -> AuditContext:
    """
    Crea un contexto de auditoría para tareas Celery.
    
    Args:
        task_name: Nombre de la tarea (para identificación)
        
    Returns:
        AuditContext configurado para Celery
    """
    return AuditContext(
        usuario=f"celery:{task_name}",
        origen=ORIGEN_CELERY,
        ip_origen=None,
        fecha=ahora_naive()
    )


def ensure_audit_context(audit_context: Optional["AuditContext"] = None) -> "AuditContext":
    """
    Garantiza que siempre exista un AuditContext.

    Si se proporciona uno, lo retorna tal cual.  Si es None, crea un
    fallback con usuario='SYSTEM' y origen='LEGACY' y emite un warning
    para que se detecten llamadas sin auditoría durante desarrollo.

    Args:
        audit_context: Contexto de auditoría (puede ser None)

    Returns:
        AuditContext proporcionado o fallback SYSTEM/LEGACY
    """
    if audit_context is not None:
        return audit_context
    logger.warning("⚠️ Operación sin audit_context - usando fallback SYSTEM/LEGACY")
    return AuditContext(usuario="SYSTEM", origen=ORIGEN_LEGACY)


def get_system_audit_context(process_name: str = "system") -> AuditContext:
    """
    Crea un contexto de auditoría para procesos del sistema.
    
    Args:
        process_name: Nombre del proceso
        
    Returns:
        AuditContext configurado para proceso del sistema
    """
    return AuditContext(
        usuario=f"system:{process_name}",
        origen=ORIGEN_SYSTEM,
        ip_origen=None,
        fecha=ahora_naive()
    )
