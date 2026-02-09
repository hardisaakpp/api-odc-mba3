"""
Gestor de notificaciones en tiempo real mediante SSE (Server-Sent Events).

Proporciona un bus de notificaciones en memoria que permite:
- Registrar listeners (conexiones SSE) por permiso de usuario
- Enviar notificaciones dirigidas a usuarios según su permiso (odcsap.view, mabel.view)
- Auto-limpieza de notificaciones antiguas

Flujo:
1. El frontend se conecta al endpoint SSE y queda escuchando
2. Cuando ocurre una acción (enviar pedido, confirmar, cancelar, etc.),
   el endpoint correspondiente llama a notification_manager.notify(...)
3. El manager enruta la notificación a todos los listeners con el permiso destino
4. El frontend recibe el evento y muestra un toast

Autor: SCNexus
Fecha: 2026-02-09
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    """Tipos de notificación que corresponden a tipos de toast en el frontend."""
    SUCCESS = "success"
    ERROR = "error"
    INFO = "info"
    WARNING = "warning"


@dataclass
class Notification:
    """Representa una notificación para enviar al frontend."""
    id: str
    type: NotificationType
    title: str
    message: str
    target_permission: str  # Permiso destino (ej: "odcsap.view", "mabel.view")
    timestamp: float
    metadata: Dict = field(default_factory=dict)  # Datos adicionales (numero_pedido, etc.)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "message": self.message,
            "target_permission": self.target_permission,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class NotificationManager:
    """
    Gestor singleton de notificaciones SSE.

    Mantiene colas asyncio por permiso. Cuando se envía una notificación
    dirigida a un permiso, todos los listeners suscritos a ese permiso
    la reciben.
    """

    def __init__(self):
        # Mapa: permission -> lista de asyncio.Queue (una por conexión SSE activa)
        self._listeners: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        logger.info("📢 NotificationManager inicializado")

    async def subscribe(self, permissions: List[str]) -> asyncio.Queue:
        """
        Suscribe una conexión SSE a recibir notificaciones para los permisos dados.

        Args:
            permissions: Lista de permisos del usuario (ej: ["odcsap.view"])

        Returns:
            asyncio.Queue por la cual se recibirán las notificaciones
        """
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            for perm in permissions:
                if perm not in self._listeners:
                    self._listeners[perm] = []
                self._listeners[perm].append(queue)
                logger.debug(f"📢 Nuevo listener para permiso '{perm}' (total: {len(self._listeners[perm])})")
        return queue

    async def unsubscribe(self, queue: asyncio.Queue, permissions: List[str]):
        """
        Elimina una conexión SSE de las suscripciones.

        Args:
            queue: La cola a eliminar
            permissions: Permisos a los que estaba suscrita
        """
        async with self._lock:
            for perm in permissions:
                if perm in self._listeners:
                    try:
                        self._listeners[perm].remove(queue)
                        logger.debug(f"📢 Listener removido de '{perm}' (quedan: {len(self._listeners[perm])})")
                    except ValueError:
                        pass
                    # Limpiar lista vacía
                    if not self._listeners[perm]:
                        del self._listeners[perm]

    async def notify(
        self,
        target_permission: str,
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Envía una notificación a todos los usuarios con el permiso especificado.

        Args:
            target_permission: Permiso destino (ej: "odcsap.view" para EL RAYO)
            title: Título de la notificación
            message: Mensaje descriptivo
            notification_type: Tipo de toast (success, error, info, warning)
            metadata: Datos adicionales (numero_pedido, pedido_id, etc.)

        Returns:
            ID de la notificación creada
        """
        notification = Notification(
            id=str(uuid.uuid4()),
            type=notification_type,
            title=title,
            message=message,
            target_permission=target_permission,
            timestamp=time.time(),
            metadata=metadata or {},
        )

        delivered_count = 0
        async with self._lock:
            queues = self._listeners.get(target_permission, [])
            stale_queues = []
            for q in queues:
                try:
                    q.put_nowait(notification)
                    delivered_count += 1
                except asyncio.QueueFull:
                    stale_queues.append(q)
                    logger.warning("📢 Cola llena, descartando listener obsoleto")

            # Limpiar colas llenas (listeners que no están consumiendo)
            for sq in stale_queues:
                try:
                    self._listeners[target_permission].remove(sq)
                except ValueError:
                    pass

        logger.info(
            f"📢 Notificación enviada → permiso='{target_permission}', "
            f"título='{title}', entregada a {delivered_count} listener(s)"
        )
        return notification.id

    async def notify_multiple(
        self,
        target_permissions: List[str],
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Envía una notificación a múltiples permisos simultáneamente.

        Args:
            target_permissions: Lista de permisos destino
            title: Título de la notificación
            message: Mensaje descriptivo
            notification_type: Tipo de toast
            metadata: Datos adicionales

        Returns:
            ID de la notificación
        """
        notification_id = None
        for perm in target_permissions:
            nid = await self.notify(
                target_permission=perm,
                title=title,
                message=message,
                notification_type=notification_type,
                metadata=metadata,
            )
            if notification_id is None:
                notification_id = nid
        return notification_id or str(uuid.uuid4())

    @property
    def active_listeners_count(self) -> Dict[str, int]:
        """Retorna la cantidad de listeners activos por permiso."""
        return {perm: len(queues) for perm, queues in self._listeners.items()}


# ─── Instancia singleton ───────────────────────────────────────────────────────
notification_manager = NotificationManager()
