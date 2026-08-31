"""
Tests del puente Redis pub/sub entre workers de Celery y notification_manager
(ver src/utils/sse_redis_bridge.py).

Requieren una instancia de Redis real y alcanzable (REDIS_URL / redis://localhost:6379/0
por defecto en dev) -- son tests de integración, no unitarios: verifican el round-trip
real publish_notification_from_worker() -> escuchar_notificaciones_redis() ->
notification_manager, que es exactamente lo que un worker de Celery hace en producción
al notificar un evento (ver src/tasks/celery_proceso_sap.py, celery_reconciliar_transferencias.py).
"""
import asyncio

import pytest

from src.utils.notification_manager import NotificationManager, NotificationType
from src.utils.sse_redis_bridge import (
    escuchar_notificaciones_redis,
    publish_notification_from_worker,
    publish_notification_from_worker_multi,
)

pytestmark = pytest.mark.integration


async def _iniciar_listener_y_esperar_suscripcion():
    """Arranca el listener y espera a que la suscripción a Redis quede confirmada
    (ready_event) antes de publicar -- un mensaje publicado antes de que el SUBSCRIBE
    se confirme en el servidor se pierde (semántica normal de pub/sub de Redis)."""
    ready = asyncio.Event()
    task = asyncio.create_task(escuchar_notificaciones_redis(ready_event=ready))
    await asyncio.wait_for(ready.wait(), timeout=5.0)
    return task


async def _detener_listener(task):
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


class TestPublishNotificationFromWorker:
    @pytest.mark.asyncio
    async def test_mensaje_publicado_llega_al_notification_manager(self, monkeypatch):
        """Simula lo que hace un worker de Celery (proceso aparte): publica una
        notificación por Redis y verifica que el listener del proceso FastAPI la
        reenvía, con título/mensaje/tipo/metadata intactos, a un cliente SSE
        suscrito al permiso correcto."""
        import src.utils.notification_manager as nm_module

        manager = NotificationManager()
        monkeypatch.setattr(nm_module, "notification_manager", manager)

        queue = await manager.subscribe(["odcsap.view"], username="test-listener")
        listener_task = await _iniciar_listener_y_esperar_suscripcion()
        try:
            publish_notification_from_worker(
                "odcsap.view",
                "Título de prueba",
                "Mensaje de prueba",
                "success",
                {"accion": "test_bridge", "pedido_id": "abc-123"},
            )
            notification = await asyncio.wait_for(queue.get(), timeout=5.0)
        finally:
            await _detener_listener(listener_task)

        assert notification.title == "Título de prueba"
        assert notification.message == "Mensaje de prueba"
        assert notification.type == NotificationType.SUCCESS
        assert notification.target_permission == "odcsap.view"
        assert notification.metadata["accion"] == "test_bridge"
        assert notification.metadata["pedido_id"] == "abc-123"

    @pytest.mark.asyncio
    async def test_mensaje_no_llega_a_permiso_no_suscrito(self, monkeypatch):
        """Un listener suscrito a mabel.view no debe recibir nada publicado para
        odcsap.view -- el enrutamiento por permiso debe seguir funcionando igual
        que con el camino normal (notify() en el proceso FastAPI)."""
        import src.utils.notification_manager as nm_module

        manager = NotificationManager()
        monkeypatch.setattr(nm_module, "notification_manager", manager)

        queue = await manager.subscribe(["mabel.view"], username="test-listener")
        listener_task = await _iniciar_listener_y_esperar_suscripcion()
        try:
            publish_notification_from_worker(
                "odcsap.view", "No debería llegar", "...", "info",
            )
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(queue.get(), timeout=1.0)
        finally:
            await _detener_listener(listener_task)

    @pytest.mark.asyncio
    async def test_publish_multi_notifica_a_ambos_permisos(self, monkeypatch):
        """publish_notification_from_worker_multi (usado por la reconciliación
        automática para avisar tanto a odcsap.view como a mabel.view) entrega el
        mismo mensaje a cada permiso de la lista."""
        import src.utils.notification_manager as nm_module

        manager = NotificationManager()
        monkeypatch.setattr(nm_module, "notification_manager", manager)

        queue_odcsap = await manager.subscribe(["odcsap.view"], username="rayo")
        queue_mabel = await manager.subscribe(["mabel.view"], username="mabel")
        listener_task = await _iniciar_listener_y_esperar_suscripcion()
        try:
            publish_notification_from_worker_multi(
                ["odcsap.view", "mabel.view"],
                "Pedido desbloqueado automáticamente",
                "El pedido X se desbloqueó.",
                "success",
            )
            n1 = await asyncio.wait_for(queue_odcsap.get(), timeout=5.0)
            n2 = await asyncio.wait_for(queue_mabel.get(), timeout=5.0)
        finally:
            await _detener_listener(listener_task)

        assert n1.target_permission == "odcsap.view"
        assert n2.target_permission == "mabel.view"
        assert n1.message == n2.message == "El pedido X se desbloqueó."

    def test_publish_no_lanza_si_redis_no_disponible(self, monkeypatch):
        """Best-effort: si Redis falla, publish_notification_from_worker no debe
        propagar la excepción -- no debe romper la tarea de Celery que lo llama
        (el envío a SAP / la reconciliación ya reportan su resultado real por
        otros canales)."""
        import src.database.services.proceso_estado_service as pes_module

        def _boom():
            raise ConnectionError("Redis no disponible (simulado)")

        monkeypatch.setattr(pes_module, "get_redis_client", _boom)
        publish_notification_from_worker("odcsap.view", "t", "m", "info")
