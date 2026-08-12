"""
Regresión: _celery_workers_available() debe respetar un límite de tiempo real,
incluso si celery_app.control.inspect().ping() no respeta su propio `timeout`.

Incidente 2026-08-12: en el entorno real, inspect(timeout=2.5).ping() se quedaba
colgado 15-30+ segundos en vez de cortar a los 2.5s configurados. Como esta
función se usa para decidir si una subida de plantilla (u otro proceso) se
encola en Celery o se procesa en primer plano, ese cuelgue se arrastraba
directo a la petición HTTP de subida, agotando el timeout del cliente
(60s en el frontend) y mostrando "El servidor tardó demasiado en responder".

La corrección ejecuta el ping en un hilo daemon y usa join(timeout=...) como
límite externo real, sin depender de que Celery honre su propio timeout.
"""

import threading
import time


class _InspectQueSeCuelga:
    def __init__(self, segundos):
        self._segundos = segundos

    def ping(self):
        threading.Event().wait(self._segundos)
        return None


class _ControlQueSeCuelga:
    def __init__(self, segundos):
        self._segundos = segundos

    def inspect(self, timeout=None):
        return _InspectQueSeCuelga(self._segundos)


class _InspectConWorker:
    def ping(self):
        return {"celery@host": {"ok": "pong"}}


class _ControlConWorker:
    def inspect(self, timeout=None):
        return _InspectConWorker()


class _CeleryAppFalso:
    def __init__(self, control):
        self.control = control


def test_plantillas_no_espera_mas_alla_del_timeout_aunque_ping_se_cuelgue(monkeypatch):
    import src.celery_app as celery_app_module
    from src.endpoints import plantillas

    monkeypatch.setattr(plantillas, "CELERY_WORKER_PING_TIMEOUT", 0.3)
    monkeypatch.setattr(celery_app_module, "celery_app", _CeleryAppFalso(_ControlQueSeCuelga(5)))

    t0 = time.time()
    resultado = plantillas._celery_workers_available()
    transcurrido = time.time() - t0

    assert resultado is False
    assert transcurrido < 1.0, (
        f"_celery_workers_available() tardó {transcurrido:.2f}s; debía cortar cerca de "
        "CELERY_WORKER_PING_TIMEOUT (0.3s) en vez de esperar a que ping() termine (5s)."
    )


def test_plantillas_retorna_true_si_hay_worker_respondiendo(monkeypatch):
    import src.celery_app as celery_app_module
    from src.endpoints import plantillas

    monkeypatch.setattr(plantillas, "CELERY_WORKER_PING_TIMEOUT", 2.5)
    monkeypatch.setattr(celery_app_module, "celery_app", _CeleryAppFalso(_ControlConWorker()))

    assert plantillas._celery_workers_available() is True


def test_endpoints_proceso_no_espera_mas_alla_del_timeout_aunque_ping_se_cuelgue(monkeypatch):
    import src.celery_app as celery_app_module
    from src.endpoints.pedidos.redistribucion import endpoints_proceso as ep

    monkeypatch.setattr(ep, "CELERY_WORKER_PING_TIMEOUT", 0.3)
    monkeypatch.setattr(celery_app_module, "celery_app", _CeleryAppFalso(_ControlQueSeCuelga(5)))

    t0 = time.time()
    resultado = ep._celery_workers_available()
    transcurrido = time.time() - t0

    assert resultado is False
    assert transcurrido < 1.0, (
        f"_celery_workers_available() tardó {transcurrido:.2f}s; debía cortar cerca de "
        "CELERY_WORKER_PING_TIMEOUT (0.3s) en vez de esperar a que ping() termine (5s)."
    )


def test_endpoints_proceso_retorna_true_si_hay_worker_respondiendo(monkeypatch):
    import src.celery_app as celery_app_module
    from src.endpoints.pedidos.redistribucion import endpoints_proceso as ep

    monkeypatch.setattr(ep, "CELERY_WORKER_PING_TIMEOUT", 2.5)
    monkeypatch.setattr(celery_app_module, "celery_app", _CeleryAppFalso(_ControlConWorker()))

    assert ep._celery_workers_available() is True
