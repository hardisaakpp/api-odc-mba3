"""
Gestor de notificaciones en tiempo real mediante SSE (Server-Sent Events).

Proporciona un bus de notificaciones en memoria que permite:
- Registrar listeners (conexiones SSE) por permiso de usuario, identificados por username
- Enviar notificaciones dirigidas a usuarios según permiso (odcsap.view, mabel.view)
- Excluir al autor de la acción al notificar al mismo permiso (escalabilidad multi-usuario)
- Auto-limpieza de notificaciones antiguas

Flujo:
1. El frontend se conecta al endpoint SSE y queda escuchando (subscribe con username)
2. Cuando ocurre una acción, el endpoint llama a notification_manager.notify_by_actor(...)
3. El manager envía al mismo permiso (excl. autor) y al permiso opuesto
4. El frontend recibe el evento y muestra un toast según target_permission

Autor: SCNexus
Fecha: 2026-02-09
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Permisos que reciben notificaciones y su permiso "opuesto" (otro rol)
NOTIFICATION_PERMISSIONS = ("odcsap.view", "mabel.view")
OPPOSITE_PERMISSION: Dict[str, str] = {"odcsap.view": "mabel.view", "mabel.view": "odcsap.view"}


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

    Mantiene por permiso una lista de (username, queue). Al notificar se puede
    excluir a un usuario (ej. el autor de la acción) para no enviarle el toast
    cuando se notifica al mismo permiso.
    """

    def __init__(self):
        # Mapa: permission -> lista de (username, asyncio.Queue)
        self._listeners: Dict[str, List[Tuple[str, asyncio.Queue]]] = {}
        self._lock = asyncio.Lock()
        logger.info("📢 NotificationManager inicializado")

    async def subscribe(self, permissions: List[str], username: str = "unknown") -> asyncio.Queue:
        """
        Suscribe una conexión SSE a recibir notificaciones para los permisos dados.

        Args:
            permissions: Lista de permisos del usuario (ej: ["odcsap.view"])
            username: Identificador del usuario (para excluir al autor al notificar mismo permiso)

        Returns:
            asyncio.Queue por la cual se recibirán las notificaciones
        """
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            for perm in permissions:
                if perm not in self._listeners:
                    self._listeners[perm] = []
                self._listeners[perm].append((username, queue))
                logger.debug(f"📢 Nuevo listener para permiso '{perm}' usuario={username} (total: {len(self._listeners[perm])})")
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
                if perm not in self._listeners:
                    continue
                self._listeners[perm] = [(u, q) for u, q in self._listeners[perm] if q is not queue]
                logger.debug(f"📢 Listener removido de '{perm}' (quedan: {len(self._listeners[perm])})")
                if not self._listeners[perm]:
                    del self._listeners[perm]

    async def notify(
        self,
        target_permission: str,
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        metadata: Optional[Dict] = None,
        exclude_username: Optional[str] = None,
    ) -> str:
        """
        Envía una notificación a todos los usuarios con el permiso especificado,
        opcionalmente excluyendo a un usuario (ej. el autor de la acción).

        Args:
            target_permission: Permiso destino (ej: "odcsap.view" para EL RAYO)
            title: Título de la notificación
            message: Mensaje descriptivo
            notification_type: Tipo de toast (success, error, info, warning)
            metadata: Datos adicionales (numero_pedido, pedido_id, etc.)
            exclude_username: Si se indica, no se envía a las colas de este usuario (mismo permiso).

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
        stale: List[Tuple[str, asyncio.Queue]] = []
        async with self._lock:
            entries = self._listeners.get(target_permission, [])
            for username, q in entries:
                if exclude_username and username == exclude_username:
                    continue
                try:
                    q.put_nowait(notification)
                    delivered_count += 1
                except asyncio.QueueFull:
                    stale.append((username, q))
                    logger.warning("📢 Cola llena, descartando listener obsoleto")
            for t in stale:
                try:
                    self._listeners[target_permission].remove(t)
                except ValueError:
                    pass
            if target_permission in self._listeners and not self._listeners[target_permission]:
                del self._listeners[target_permission]

        logger.info(
            f"📢 Notificación enviada → permiso='{target_permission}', "
            f"excl={exclude_username or 'ninguno'}, título='{title}', entregada a {delivered_count} listener(s)"
        )
        return notification.id

    async def notify_by_actor(
        self,
        actor_permission: str,
        actor_username: str,
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Notificación escalable: quien realiza la acción (actor) tiene un permiso;
        se notifica a (1) otros usuarios con el mismo permiso (excl. actor) y
        (2) a todos los usuarios del permiso opuesto.

        Ejemplo: si andrea@ (mabel.view) envía un pedido, se notifica a carlos@
        y resto con mabel.view (excl. andrea) y a todos con odcsap.view.

        Args:
            actor_permission: Permiso de quien realiza la acción ("mabel.view" o "odcsap.view")
            actor_username: Usuario que realiza la acción (no recibirá la notificación en su mismo permiso)
            title: Título del toast
            message: Mensaje
            notification_type: Tipo de toast
            metadata: Datos adicionales

        Returns:
            ID de la notificación
        """
        opposite = OPPOSITE_PERMISSION.get(actor_permission)
        nid = None
        # Mismo permiso: otros usuarios (excl. autor)
        nid = await self.notify(
            target_permission=actor_permission,
            title=title,
            message=message,
            notification_type=notification_type,
            metadata=metadata,
            exclude_username=actor_username,
        )
        # Permiso opuesto: todos
        if opposite:
            await self.notify(
                target_permission=opposite,
                title=title,
                message=message,
                notification_type=notification_type,
                metadata=metadata,
            )
        return nid or str(uuid.uuid4())

    async def notify_multiple(
        self,
        target_permissions: List[str],
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        metadata: Optional[Dict] = None,
        exclude_username: Optional[str] = None,
    ) -> str:
        """
        Envía una notificación a múltiples permisos simultáneamente.
        Opcionalmente excluye a un usuario en todos los permisos.
        """
        notification_id = None
        for perm in target_permissions:
            nid = await self.notify(
                target_permission=perm,
                title=title,
                message=message,
                notification_type=notification_type,
                metadata=metadata,
                exclude_username=exclude_username,
            )
            if notification_id is None:
                notification_id = nid
        return notification_id or str(uuid.uuid4())

    @property
    def active_listeners_count(self) -> Dict[str, int]:
        """Retorna la cantidad de listeners activos por permiso."""
        return {perm: len(entries) for perm, entries in self._listeners.items()}


# ─── Instancia singleton ───────────────────────────────────────────────────────
notification_manager = NotificationManager()
