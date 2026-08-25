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

import pytest


@pytest.fixture(autouse=True)
def _reset_celery_availability_cache():
    """Resetea el cache single-flight de disponibilidad de workers Celery antes
    de cada test. Sin esto, un resultado True/False cacheado por un test se
    filtraría al siguiente (mismo proceso de pytest, estado a nivel de módulo),
    haciendo que las aserciones dependan del orden de ejecución de los tests.

    Con timestamp=0.0 la edad del cache siempre supera el TTL por defecto
    (CELERY_WORKER_AVAILABILITY_CACHE_TTL), así que cada test dispara una
    comprobación real la primera vez que llama a _celery_workers_available().
    """
    from src.endpoints import plantillas
    from src.endpoints.pedidos.redistribucion import endpoints_proceso as ep

    for mod in (plantillas, ep):
        mod._disponibilidad_cache["resultado"] = False
        mod._disponibilidad_cache["timestamp"] = 0.0
        mod._disponibilidad_cache["verificando"] = False
    yield


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


class _InspectLento:
    """Simula el comportamiento real confirmado en vivo: ping() excede levemente
    el `timeout` que se le pasó a inspect(), pero igual responde con éxito."""

    def __init__(self, segundos, respuesta):
        self._segundos = segundos
        self._respuesta = respuesta

    def ping(self):
        threading.Event().wait(self._segundos)
        return self._respuesta


class _ControlLento:
    def __init__(self, segundos, respuesta):
        self._segundos = segundos
        self._respuesta = respuesta

    def inspect(self, timeout=None):
        return _InspectLento(self._segundos, self._respuesta)


class _CeleryAppFalso:
    def __init__(self, control):
        self.control = control


class _InspectContador:
    """Responde siempre con pong exitoso y cuenta cuántas veces se llamó a
    ping(), para probar que el cache evita pings duplicados."""

    def __init__(self):
        self.llamadas = 0

    def ping(self):
        self.llamadas += 1
        return {"celery@host": {"ok": "pong"}}


class _ControlContador:
    def __init__(self):
        self.inspector = _InspectContador()

    def inspect(self, timeout=None):
        return self.inspector


class _InspectBloqueante:
    """Simula un ping en curso: marca `evento_entrada` en cuanto arranca
    (para que el test sepa determinísticamente que ya está "en vuelo") y se
    queda esperando a que el test libere `evento_liberar` antes de responder
    con éxito. Sin sleeps: la sincronización es 100% por Event."""

    def __init__(self, evento_entrada, evento_liberar):
        self._evento_entrada = evento_entrada
        self._evento_liberar = evento_liberar

    def ping(self):
        self._evento_entrada.set()
        self._evento_liberar.wait(timeout=5.0)
        return {"celery@host": {"ok": "pong"}}


class _ControlBloqueante:
    def __init__(self, evento_entrada, evento_liberar):
        self._evento_entrada = evento_entrada
        self._evento_liberar = evento_liberar

    def inspect(self, timeout=None):
        return _InspectBloqueante(self._evento_entrada, self._evento_liberar)


def test_plantillas_no_espera_mas_alla_del_timeout_aunque_ping_se_cuelgue(monkeypatch):
    import src.celery_app as celery_app_module
    from src.endpoints import plantillas

    monkeypatch.setattr(plantillas, "CELERY_WORKER_PING_TIMEOUT", 0.3)
    monkeypatch.setattr(plantillas, "CELERY_WORKER_PING_JOIN_BUFFER", 0.0)
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


def test_plantillas_no_da_falso_negativo_si_ping_excede_levemente_su_propio_timeout(monkeypatch):
    """Regresión del bug real: inspect(timeout=0.3).ping() tarda 0.5s (excede su
    propio timeout) pero responde con éxito; el buffer del join externo debe
    absorber ese overshoot y no descartar un worker sano."""
    import src.celery_app as celery_app_module
    from src.endpoints import plantillas

    monkeypatch.setattr(plantillas, "CELERY_WORKER_PING_TIMEOUT", 0.3)
    monkeypatch.setattr(
        celery_app_module,
        "celery_app",
        _CeleryAppFalso(_ControlLento(0.5, {"celery@host": {"ok": "pong"}})),
    )

    assert plantillas._celery_workers_available() is True


def test_endpoints_proceso_no_espera_mas_alla_del_timeout_aunque_ping_se_cuelgue(monkeypatch):
    import src.celery_app as celery_app_module
    from src.endpoints.pedidos.redistribucion import endpoints_proceso as ep

    monkeypatch.setattr(ep, "CELERY_WORKER_PING_TIMEOUT", 0.3)
    monkeypatch.setattr(ep, "CELERY_WORKER_PING_JOIN_BUFFER", 0.0)
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


def test_endpoints_proceso_no_da_falso_negativo_si_ping_excede_levemente_su_propio_timeout(monkeypatch):
    """Regresión del bug real: inspect(timeout=0.3).ping() tarda 0.5s (excede su
    propio timeout) pero responde con éxito; el buffer del join externo debe
    absorber ese overshoot y no descartar un worker sano."""
    import src.celery_app as celery_app_module
    from src.endpoints.pedidos.redistribucion import endpoints_proceso as ep

    monkeypatch.setattr(ep, "CELERY_WORKER_PING_TIMEOUT", 0.3)
    monkeypatch.setattr(
        celery_app_module,
        "celery_app",
        _CeleryAppFalso(_ControlLento(0.5, {"celery@host": {"ok": "pong"}})),
    )

    assert ep._celery_workers_available() is True


# ---------------------------------------------------------------------------
# Regresión (ronda 3): cache single-flight con TTL corto.
#
# Verificado en vivo que el hilo daemon abandonado por un join() que se
# rinde sigue corriendo y CONTIENDE con el hilo de ping de la siguiente
# llamada (aparentemente por un pool de conexiones Kombu/Celery compartido):
# pings aislados ~5.4s, pings contra un hilo abandonado 9.6-14s. Esto seguía
# produciendo falsos negativos en llamadas repetidas/rápidas incluso después
# del fix del buffer de join(). El cache de abajo evita relanzar un hilo de
# ping por cada llamada (TTL) y evita lanzar un hilo COMPETIDOR mientras ya
# hay uno en curso (single-flight).
# ---------------------------------------------------------------------------


def test_plantillas_cache_evita_ping_duplicado_en_llamadas_repetidas(monkeypatch):
    """Dos llamadas seguidas (dentro del TTL) deben devolver True, pero el
    ping subyacente debe haberse invocado una sola vez (la segunda se sirve
    desde cache, no dispara un nuevo hilo de ping)."""
    import src.celery_app as celery_app_module
    from src.endpoints import plantillas

    monkeypatch.setattr(plantillas, "CELERY_WORKER_PING_TIMEOUT", 2.5)
    control = _ControlContador()
    monkeypatch.setattr(celery_app_module, "celery_app", _CeleryAppFalso(control))

    primero = plantillas._celery_workers_available()
    segundo = plantillas._celery_workers_available()

    assert primero is True
    assert segundo is True
    assert control.inspector.llamadas == 1, (
        "La segunda llamada debía servirse desde cache; se detectaron "
        f"{control.inspector.llamadas} invocaciones reales de ping()."
    )


def test_endpoints_proceso_cache_evita_ping_duplicado_en_llamadas_repetidas(monkeypatch):
    """Mismo caso que la versión de plantillas, para endpoints_proceso."""
    import src.celery_app as celery_app_module
    from src.endpoints.pedidos.redistribucion import endpoints_proceso as ep

    monkeypatch.setattr(ep, "CELERY_WORKER_PING_TIMEOUT", 2.5)
    control = _ControlContador()
    monkeypatch.setattr(celery_app_module, "celery_app", _CeleryAppFalso(control))

    primero = ep._celery_workers_available()
    segundo = ep._celery_workers_available()

    assert primero is True
    assert segundo is True
    assert control.inspector.llamadas == 1, (
        "La segunda llamada debía servirse desde cache; se detectaron "
        f"{control.inspector.llamadas} invocaciones reales de ping()."
    )


def test_plantillas_no_lanza_ping_competidor_si_ya_hay_uno_en_curso(monkeypatch):
    """Mientras un ping ya está en curso (verificando=True), una segunda
    llamada debe devolver de inmediato el último valor cacheado, sin lanzar
    un hilo de ping competidor ni bloquear esperando al primero."""
    import src.celery_app as celery_app_module
    from src.endpoints import plantillas

    monkeypatch.setattr(plantillas, "CELERY_WORKER_PING_TIMEOUT", 5.0)
    monkeypatch.setattr(plantillas, "CELERY_WORKER_PING_JOIN_BUFFER", 5.0)
    evento_entrada = threading.Event()
    evento_liberar = threading.Event()
    monkeypatch.setattr(
        celery_app_module,
        "celery_app",
        _CeleryAppFalso(_ControlBloqueante(evento_entrada, evento_liberar)),
    )

    resultados = {}

    def _llamar_primero():
        resultados["primero"] = plantillas._celery_workers_available()

    hilo_primero = threading.Thread(target=_llamar_primero)
    hilo_primero.start()

    # Sincronización determinista: espera a que el primer ping haya arrancado
    # de verdad (nada de sleeps como única señal de corrección).
    assert evento_entrada.wait(timeout=2.0), "El primer ping no arrancó a tiempo"
    assert plantillas._disponibilidad_cache["verificando"] is True

    t0 = time.time()
    segundo = plantillas._celery_workers_available()
    transcurrido = time.time() - t0

    assert segundo is False, "Debía devolver el último valor cacheado (nada exitoso todavía)"
    assert transcurrido < 1.0, (
        f"La segunda llamada tardó {transcurrido:.2f}s; debía retornar de inmediato "
        "el valor cacheado en vez de lanzar/esperar un ping competidor."
    )

    evento_liberar.set()
    hilo_primero.join(timeout=5.0)

    assert resultados["primero"] is True
    assert plantillas._disponibilidad_cache["resultado"] is True


def test_endpoints_proceso_no_lanza_ping_competidor_si_ya_hay_uno_en_curso(monkeypatch):
    """Mismo caso que la versión de plantillas, para endpoints_proceso."""
    import src.celery_app as celery_app_module
    from src.endpoints.pedidos.redistribucion import endpoints_proceso as ep

    monkeypatch.setattr(ep, "CELERY_WORKER_PING_TIMEOUT", 5.0)
    monkeypatch.setattr(ep, "CELERY_WORKER_PING_JOIN_BUFFER", 5.0)
    evento_entrada = threading.Event()
    evento_liberar = threading.Event()
    monkeypatch.setattr(
        celery_app_module,
        "celery_app",
        _CeleryAppFalso(_ControlBloqueante(evento_entrada, evento_liberar)),
    )

    resultados = {}

    def _llamar_primero():
        resultados["primero"] = ep._celery_workers_available()

    hilo_primero = threading.Thread(target=_llamar_primero)
    hilo_primero.start()

    assert evento_entrada.wait(timeout=2.0), "El primer ping no arrancó a tiempo"
    assert ep._disponibilidad_cache["verificando"] is True

    t0 = time.time()
    segundo = ep._celery_workers_available()
    transcurrido = time.time() - t0

    assert segundo is False, "Debía devolver el último valor cacheado (nada exitoso todavía)"
    assert transcurrido < 1.0, (
        f"La segunda llamada tardó {transcurrido:.2f}s; debía retornar de inmediato "
        "el valor cacheado en vez de lanzar/esperar un ping competidor."
    )

    evento_liberar.set()
    hilo_primero.join(timeout=5.0)

    assert resultados["primero"] is True
    assert ep._disponibilidad_cache["resultado"] is True
