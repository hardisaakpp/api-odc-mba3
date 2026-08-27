"""
celery_worker_available() (src/services/celery_availability.py) reemplaza el
chequeo anterior basado en celery_app.control.inspect().ping() -- un broadcast
al canal de control de Celery que resultó flaky en producción: el ping no
siempre respetaba su propio timeout y, bajo contención de hilos, devolvía
falsos negativos con workers sanos.

Incidente 2026-08-27: ese falso negativo tiró una carga de plantilla al
fallback síncrono (Celery estaba sano y procesando otras tareas en paralelo);
el procesamiento síncrono tardó 117s por saturación de SAP y el frontend ya
había cortado por su timeout de 60s ("tiempo de espera agotado"), mientras el
backend seguía trabajando sin que nadie escuchara la respuesta.

El nuevo mecanismo es un GET simple a una clave de heartbeat en Redis (la
escribe una tarea periódica de Celery Beat, ver
src/tasks/celery_worker_heartbeat.py) -- sin hilos, sin ping de broadcast, sin
condiciones de carrera posibles.

`plantillas._celery_workers_available` y `endpoints_proceso._celery_workers_available`
son alias de import de `celery_worker_available`, conservados porque
tests/test_encolado_no_bloquea_event_loop.py los monkeypatchea por nombre.
"""

import logging

from src.services import celery_availability


class _RedisFalso:
    def __init__(self, existe: bool = True, error: Exception | None = None):
        self._existe = existe
        self._error = error

    def exists(self, _key):
        if self._error is not None:
            raise self._error
        return self._existe


def test_disponible_si_la_clave_de_heartbeat_existe(monkeypatch):
    monkeypatch.setattr(celery_availability, "get_redis_client", lambda: _RedisFalso(existe=True))
    assert celery_availability.celery_worker_available() is True


def test_no_disponible_si_la_clave_de_heartbeat_no_existe(monkeypatch):
    """Sin heartbeat vigente (TTL vencido o worker nunca lo escribió) => no disponible."""
    monkeypatch.setattr(celery_availability, "get_redis_client", lambda: _RedisFalso(existe=False))
    assert celery_availability.celery_worker_available() is False


def test_no_disponible_si_redis_lanza_una_excepcion(monkeypatch):
    """Ante cualquier error consultando Redis, prioriza el flujo síncrono (False), sin propagar."""
    monkeypatch.setattr(
        celery_availability,
        "get_redis_client",
        lambda: _RedisFalso(error=ConnectionError("Redis no responde")),
    )
    assert celery_availability.celery_worker_available() is False


def test_plantillas_expone_el_mismo_chequeo_por_el_nombre_historico():
    """monkeypatch.setattr(plantillas, "_celery_workers_available", ...) debe seguir
    funcionando (test_encolado_no_bloquea_event_loop.py depende de este atributo)."""
    from src.endpoints import plantillas

    assert plantillas._celery_workers_available is celery_availability.celery_worker_available


def test_endpoints_proceso_expone_el_mismo_chequeo_por_el_nombre_historico():
    from src.endpoints.pedidos.redistribucion import endpoints_proceso as ep

    assert ep._celery_workers_available is celery_availability.celery_worker_available


def test_emitir_heartbeat_escribe_la_clave_esperada_con_ttl(monkeypatch):
    from src.tasks import celery_worker_heartbeat

    llamadas = {}

    class _RedisSetex:
        def setex(self, key, ttl, value):
            llamadas["key"] = key
            llamadas["ttl"] = ttl
            llamadas["value"] = value

    monkeypatch.setattr(celery_worker_heartbeat, "get_redis_client", lambda: _RedisSetex())

    celery_worker_heartbeat.emitir_heartbeat()

    assert llamadas["key"] == celery_availability.HEARTBEAT_REDIS_KEY
    assert llamadas["ttl"] > 0


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="celery.worker.strategy", level=logging.INFO, pathname=__file__,
        lineno=1, msg=msg, args=(), exc_info=None,
    )


def test_filtro_de_heartbeat_silencia_solo_sus_propios_logs():
    """No debe tapar logs de otras tareas: solo los que mencionan la tarea de
    heartbeat (received/succeeded/Sending due task), miles de líneas idénticas
    por día que no aportan señal una vez confirmado que el mecanismo funciona."""
    from src.celery_app import _SilenciarHeartbeatFilter

    filtro = _SilenciarHeartbeatFilter()

    ruidoso = _record("Task src.tasks.celery_worker_heartbeat.emitir_heartbeat[abc] received")
    assert filtro.filter(ruidoso) is False

    otra_tarea = _record(
        "Task src.tasks.celery_reconciliar_ordenes_compra.reconciliar_ordenes_compra_pendientes[xyz] received"
    )
    assert filtro.filter(otra_tarea) is True


def test_filtro_de_heartbeat_esta_registrado_en_los_loggers_de_celery():
    import src.celery_app as celery_app_module

    for nombre in ("celery.worker.strategy", "celery.app.trace", "celery.beat"):
        filtros = logging.getLogger(nombre).filters
        assert any(
            isinstance(f, celery_app_module._SilenciarHeartbeatFilter) for f in filtros
        ), f"Falta el filtro anti-ruido de heartbeat en el logger '{nombre}'"
