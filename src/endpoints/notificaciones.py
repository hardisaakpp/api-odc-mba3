"""
Endpoints de notificaciones en tiempo real (SSE).

Proporciona:
- GET /notificaciones/stream  → Conexión SSE para recibir notificaciones en tiempo real
- GET /notificaciones/status  → Estado del sistema de notificaciones (listeners activos)

El frontend se conecta al stream SSE al iniciar sesión y recibe notificaciones
dirigidas según los permisos del usuario autenticado.

Autor: SCNexus
Fecha: 2026-02-09
"""

import asyncio
import json
import logging
import time
from typing import Dict

from fastapi import FastAPI, Depends, Request
from fastapi.responses import StreamingResponse, JSONResponse

from src.security.jwt_auth import verify_jwt_token
from src.utils.notification_manager import notification_manager

logger = logging.getLogger(__name__)

# Intervalo de heartbeat en segundos (mantiene la conexión SSE viva)
HEARTBEAT_INTERVAL = 30


def register_notificaciones_endpoints(app: FastAPI):
    """Registra los endpoints de notificaciones en tiempo real."""

    @app.get("/notificaciones/stream", tags=["Notificaciones"])
    async def stream_notificaciones(
        request: Request,
        user: Dict = Depends(verify_jwt_token),
    ):
        """
        Conexión SSE para recibir notificaciones en tiempo real.

        El usuario se suscribe automáticamente a las notificaciones
        dirigidas a sus permisos (ej: odcsap.view, mabel.view).

        **Eventos SSE:**
        - `notification`: Nueva notificación para mostrar como toast
        - `heartbeat`: Mantiene la conexión viva (cada 30s)
        - `connected`: Confirmación de conexión exitosa

        **Formato del evento `notification`:**
        ```json
        {
            "id": "uuid",
            "type": "success|error|info|warning",
            "title": "Título del toast",
            "message": "Mensaje descriptivo",
            "target_permission": "odcsap.view",
            "timestamp": 1234567890.123,
            "metadata": {
                "numero_pedido": "P-12.03 - 12 - 2025",
                "pedido_id": "uuid"
            }
        }
        ```
        """
        permissions = user.get("permissions", [])
        username = user.get("username", "unknown")

        # Filtrar solo permisos relevantes para notificaciones
        relevant_permissions = [
            p for p in permissions
            if p in ("odcsap.view", "mabel.view")
        ]

        if not relevant_permissions:
            # Si el usuario es Admin, suscribir a ambos canales
            roles = user.get("roles", [])
            if "Admin" in roles:
                relevant_permissions = ["odcsap.view", "mabel.view"]
            else:
                logger.warning(
                    f"📢 Usuario {username} sin permisos relevantes para notificaciones"
                )
                relevant_permissions = []

        logger.info(
            f"📢 Nueva conexión SSE de '{username}' con permisos: {relevant_permissions}"
        )

        # Suscribir al bus de notificaciones
        queue = await notification_manager.subscribe(relevant_permissions)

        async def event_stream():
            """Generador de eventos SSE."""
            try:
                # Evento de conexión exitosa
                connected_data = json.dumps({
                    "username": username,
                    "permissions": relevant_permissions,
                    "timestamp": time.time(),
                })
                yield f"event: connected\ndata: {connected_data}\n\n"

                last_heartbeat = time.time()

                while True:
                    # Verificar si el cliente se desconectó
                    if await request.is_disconnected():
                        logger.info(f"📢 Cliente '{username}' desconectado del stream SSE")
                        break

                    try:
                        # Esperar notificación con timeout para heartbeat
                        notification = await asyncio.wait_for(
                            queue.get(), timeout=HEARTBEAT_INTERVAL
                        )
                        # Enviar notificación como evento SSE
                        event_data = json.dumps(notification.to_dict())
                        yield f"event: notification\ndata: {event_data}\n\n"

                    except asyncio.TimeoutError:
                        # Sin notificaciones: enviar heartbeat
                        now = time.time()
                        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                            heartbeat_data = json.dumps({"timestamp": now})
                            yield f"event: heartbeat\ndata: {heartbeat_data}\n\n"
                            last_heartbeat = now

            except asyncio.CancelledError:
                logger.info(f"📢 Stream SSE cancelado para '{username}'")
            except Exception as e:
                logger.error(f"📢 Error en stream SSE para '{username}': {e}")
            finally:
                # Limpiar suscripción
                await notification_manager.unsubscribe(queue, relevant_permissions)
                logger.info(f"📢 Suscripción SSE limpiada para '{username}'")

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
            },
        )

    @app.get("/notificaciones/status", tags=["Notificaciones"])
    async def notificaciones_status(
        user: Dict = Depends(verify_jwt_token),
    ):
        """
        Estado del sistema de notificaciones.

        Muestra la cantidad de listeners activos por permiso.
        Útil para debugging y monitoreo.
        """
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "active_listeners": notification_manager.active_listeners_count,
                "timestamp": time.time(),
            },
        )
