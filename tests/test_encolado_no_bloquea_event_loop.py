"""
Regresión: encolar en Celery no debe correr sobre el event loop.

Incidente dev 2026-08-06 (ocurrió dos veces en 15 minutos): la API completa
quedaba congelada al subir una plantilla — ni /docs respondía y no había un solo
error en el log. Causa: los handlers `async def` llamaban DIRECTAMENTE a funciones
síncronas que hablan con Redis (`control.inspect().ping()` y `tarea.delay()`).
Con Redis degradado (port-forward de Docker Desktop/WSL2) y sin timeouts de socket
configurados, esas llamadas esperaban indefinidamente y congelaban el event loop,
tumbando TODAS las peticiones, no solo la del upload.

Estos tests fijan la invariante estructural: el trabajo bloqueante se ejecuta en
un thread distinto al del event loop. No dependen de Redis ni de un worker.
"""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest
from fastapi.responses import JSONResponse


def _hilo_actual():
    return threading.get_ident()


class TestPlantillaUploadAsyncNoBloquea:
    """POST /api/plantillas/upload-async"""

    @pytest.mark.asyncio
    async def test_ping_de_workers_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints import plantillas

        hilo_del_ping = {}

        def fake_workers_available():
            hilo_del_ping["id"] = _hilo_actual()
            return False  # fuerza fallback sync y corta el flujo temprano

        monkeypatch.setattr(plantillas, "_celery_workers_available", fake_workers_available)

        async def fake_leer(_file):
            return b"contenido-excel"

        monkeypatch.setattr(plantillas, "_leer_y_validar_archivo", fake_leer)
        monkeypatch.setattr(plantillas, "get_user_id", lambda _user: "u1")

        async def fake_fallback(*_args, **_kwargs):
            return JSONResponse(status_code=200, content={"fallback": "sync"})

        monkeypatch.setattr(plantillas, "_procesar_plantilla_sync_fallback", fake_fallback)

        await plantillas._upload_plantilla_async_handler(
            file=object(),
            validar=True,
            bloquea_con_errores=True,
            modo_tiendas="validar_estricto",
            confirmar_sincronizacion=False,
            force_sync=False,
            correcciones_codigos=None,
            user={"email": "x@y.z"},
        )

        assert "id" in hilo_del_ping, "no se llegó a consultar la disponibilidad de workers"
        assert hilo_del_ping["id"] != _hilo_actual(), (
            "_celery_workers_available() corrió en el event loop: un Redis lento "
            "congelaría toda la API. Debe invocarse con asyncio.to_thread."
        )

    @pytest.mark.asyncio
    async def test_encolado_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints import plantillas

        hilo_del_encolado = {}

        def fake_encolar(*_args, **_kwargs):
            hilo_del_encolado["id"] = _hilo_actual()
            return JSONResponse(status_code=202, content={"status": "accepted"})

        monkeypatch.setattr(plantillas, "_celery_workers_available", lambda: True)
        monkeypatch.setattr(plantillas, "_encolar_plantilla_async", fake_encolar)

        async def fake_leer(_file):
            return b"contenido-excel"

        monkeypatch.setattr(plantillas, "_leer_y_validar_archivo", fake_leer)
        monkeypatch.setattr(plantillas, "get_user_id", lambda _user: "u1")

        respuesta = await plantillas._upload_plantilla_async_handler(
            file=object(),
            validar=True,
            bloquea_con_errores=True,
            modo_tiendas="validar_estricto",
            confirmar_sincronizacion=False,
            force_sync=False,
            correcciones_codigos=None,
            user={"email": "x@y.z"},
        )

        assert respuesta.status_code == 202
        assert "id" in hilo_del_encolado, "no se llegó a encolar"
        assert hilo_del_encolado["id"] != _hilo_actual(), (
            "_encolar_plantilla_async() corrió en el event loop: toca SQL Server, "
            "MinIO y Redis de forma síncrona. Debe invocarse con asyncio.to_thread."
        )

    @pytest.mark.asyncio
    async def test_el_event_loop_sigue_atendiendo_mientras_se_encola(self, monkeypatch):
        """
        La prueba de fuego del incidente: con el encolado tardando, otras
        peticiones deben seguir avanzando en paralelo.
        """
        from src.endpoints import plantillas

        def encolar_lento(*_args, **_kwargs):
            threading.Event().wait(0.4)  # simula Redis degradado
            return JSONResponse(status_code=202, content={"status": "accepted"})

        monkeypatch.setattr(plantillas, "_celery_workers_available", lambda: True)
        monkeypatch.setattr(plantillas, "_encolar_plantilla_async", encolar_lento)

        async def fake_leer(_file):
            return b"contenido-excel"

        monkeypatch.setattr(plantillas, "_leer_y_validar_archivo", fake_leer)
        monkeypatch.setattr(plantillas, "get_user_id", lambda _user: "u1")

        latidos = 0
        latidos_al_terminar_la_subida = None

        async def otra_peticion():
            """Simula el resto del tráfico de la API latiendo cada 20 ms."""
            nonlocal latidos
            for _ in range(20):
                await asyncio.sleep(0.02)
                latidos += 1

        async def subir():
            # Se mide el contador EN EL INSTANTE en que termina la subida, no al
            # final del gather: si se midiera al final, los latidos alcanzarían a
            # completarse igual después del bloqueo y el test pasaría en falso.
            nonlocal latidos_al_terminar_la_subida
            respuesta = await plantillas._upload_plantilla_async_handler(
                file=object(),
                validar=True,
                bloquea_con_errores=True,
                modo_tiendas="validar_estricto",
                confirmar_sincronizacion=False,
                force_sync=False,
                correcciones_codigos=None,
                user={"email": "x@y.z"},
            )
            latidos_al_terminar_la_subida = latidos
            return respuesta

        respuesta, _ = await asyncio.gather(subir(), otra_peticion())

        assert respuesta.status_code == 202
        # Encolado de 400 ms con latidos de 20 ms: sin bloqueo se esperan ~20;
        # con el event loop congelado se quedarían en 0. El umbral de 5 deja
        # margen de sobra para máquinas lentas sin volverse vacuo.
        assert latidos_al_terminar_la_subida >= 5, (
            f"el event loop quedó bloqueado durante el encolado "
            f"(solo {latidos_al_terminar_la_subida} latidos mientras se encolaba): "
            "el resto de las peticiones se habría congelado, que es exactamente el "
            "incidente del 2026-08-06."
        )


class TestProcesoSapAsyncNoBloquea:
    """POST /api/pedidos/.../proceso-completo-sap-async"""

    @pytest.mark.asyncio
    async def test_encolado_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints.pedidos.redistribucion import endpoints_proceso as ep

        hilo_del_encolado = {}

        def fake_encolar(*_args, **_kwargs):
            hilo_del_encolado["id"] = _hilo_actual()
            return JSONResponse(status_code=202, content={"status": "accepted"})

        monkeypatch.setattr(ep, "_celery_workers_available", lambda: True)
        monkeypatch.setattr(ep, "_encolar_proceso_sap", fake_encolar)
        monkeypatch.setattr(ep, "get_user_id", lambda _user: "u1")

        respuesta = await ep._handle_proceso_completo_sap_async(
            request=object(),
            numero_pedido="PED-1",
            request_body=object(),
            force_sync=False,
            user={"email": "x@y.z"},
        )

        assert respuesta.status_code == 202
        assert "id" in hilo_del_encolado, "no se llegó a encolar"
        assert hilo_del_encolado["id"] != _hilo_actual(), (
            "_encolar_proceso_sap() corrió en el event loop: toca SQL Server y "
            "Redis de forma síncrona. Debe invocarse con asyncio.to_thread."
        )

    @pytest.mark.asyncio
    async def test_error_al_encolar_sigue_cayendo_al_fallback_sync(self, monkeypatch):
        """El thread no debe tragarse la excepción ni saltarse el fallback."""
        from src.endpoints.pedidos.redistribucion import endpoints_proceso as ep

        def encolar_falla(*_args, **_kwargs):
            raise RuntimeError("Redis caído")

        monkeypatch.setattr(ep, "_celery_workers_available", lambda: True)
        monkeypatch.setattr(ep, "_encolar_proceso_sap", encolar_falla)
        monkeypatch.setattr(ep, "get_user_id", lambda _user: "u1")

        async def fake_fallback(*_args, **_kwargs):
            return JSONResponse(status_code=200, content={"fallback": "sync"})

        monkeypatch.setattr(ep, "_handle_proceso_sap_sync_fallback", fake_fallback)

        respuesta = await ep._handle_proceso_completo_sap_async(
            request=object(),
            numero_pedido="PED-1",
            request_body=object(),
            force_sync=False,
            user={"email": "x@y.z"},
        )

        assert respuesta.status_code == 200


class TestCruceProductosNoBloquea:
    """POST /api/cruce-productos/iniciar"""

    @pytest.mark.asyncio
    async def test_encolado_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints import cruce_productos as cp

        hilo_del_encolado = {}

        def fake_encolar(_user_id):
            hilo_del_encolado["id"] = _hilo_actual()
            return {"status": "success", "process_id": "p1"}

        monkeypatch.setattr(cp, "_encolar_cruce_productos", fake_encolar)

        resultado = await cp._iniciar_cruce_productos_handler({"username": "u1"})

        assert resultado["process_id"] == "p1"
        assert "id" in hilo_del_encolado, "no se llegó a encolar"
        assert hilo_del_encolado["id"] != _hilo_actual(), (
            "_encolar_cruce_productos() corrió en el event loop: toca SQL Server y "
            "Redis de forma síncrona. Debe invocarse con asyncio.to_thread."
        )


class TestNotificacionPersonaCorreoNoBloquea:
    """Endpoints de administración de notificacion_persona_correo."""

    @pytest.mark.asyncio
    async def test_listar_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints import notificacion_persona_correo_endpoints as npc

        hilo = {}

        def fake_db_listar():
            hilo["id"] = _hilo_actual()
            return {"personas_correo": []}

        monkeypatch.setattr(npc, "_db_listar_personas_correo", fake_db_listar)

        resultado = await npc._listar_handler()

        assert resultado == {"personas_correo": []}
        assert "id" in hilo, "no se llegó a consultar"
        assert hilo["id"] != _hilo_actual(), (
            "_db_listar_personas_correo() corrió en el event loop: hace DB (pyodbc). "
            "Debe invocarse con asyncio.to_thread."
        )

    @pytest.mark.asyncio
    async def test_crear_link_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints import notificacion_persona_correo_endpoints as npc

        hilo = {}

        def fake_db_crear(_nombre, _correo, _tipo_correo_id, _creado_por):
            hilo["id"] = _hilo_actual()
            return 42

        monkeypatch.setattr(npc, "_db_crear_link_persona_correo", fake_db_crear)

        body = npc.CrearLinkRequest(nombre="Juan", email="juan@mabeltrading.com.ec", tipo_correo_id=1)
        resultado = await npc._crear_link_handler(body, user={"username": "admin1"})

        assert resultado["id"] == 42
        assert "id" in hilo, "no se llegó a crear el link"
        assert hilo["id"] != _hilo_actual(), (
            "_db_crear_link_persona_correo() corrió en el event loop: hace DB (pyodbc). "
            "Debe invocarse con asyncio.to_thread."
        )

    @pytest.mark.asyncio
    async def test_eliminar_link_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints import notificacion_persona_correo_endpoints as npc

        hilo = {}

        def fake_db_eliminar(_link_id):
            hilo["id"] = _hilo_actual()
            return True

        monkeypatch.setattr(npc, "_db_eliminar_link_persona_correo", fake_db_eliminar)

        resultado = await npc._eliminar_link_handler(7)

        assert resultado == {"success": True}
        assert "id" in hilo, "no se llegó a eliminar el link"
        assert hilo["id"] != _hilo_actual(), (
            "_db_eliminar_link_persona_correo() corrió en el event loop: hace DB (pyodbc). "
            "Debe invocarse con asyncio.to_thread."
        )

    @pytest.mark.asyncio
    async def test_eliminar_persona_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints import notificacion_persona_correo_endpoints as npc

        hilo = {}

        def fake_db_eliminar(_email):
            hilo["id"] = _hilo_actual()
            return True

        monkeypatch.setattr(npc, "_db_eliminar_persona", fake_db_eliminar)

        resultado = await npc._eliminar_persona_handler("juan@mabeltrading.com.ec")

        assert resultado == {"success": True}
        assert "id" in hilo, "no se llegó a eliminar la persona"
        assert hilo["id"] != _hilo_actual(), (
            "_db_eliminar_persona() corrió en el event loop: hace DB (pyodbc). "
            "Debe invocarse con asyncio.to_thread."
        )


class TestEliminarOrdenesCompraNoBloquea:
    """DELETE /ordenes-compra/{oc_id} y DELETE /ordenes-compra (batch)"""

    @pytest.mark.asyncio
    async def test_eliminar_una_oc_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints import ordenes_compra as oc_module

        hilo = {}

        def fake_db_eliminar(_oc_id, _source):
            hilo["id"] = _hilo_actual()
            return JSONResponse(status_code=200, content={"status": "success"})

        monkeypatch.setattr(oc_module, "_db_eliminar_orden_compra", fake_db_eliminar)

        request = MagicMock()
        request.headers = {}

        respuesta = await oc_module._delete_orden_compra_handler(request, "oc-1")

        assert respuesta.status_code == 200
        assert "id" in hilo, "no se llegó a eliminar"
        assert hilo["id"] != _hilo_actual(), (
            "_db_eliminar_orden_compra() corrió en el event loop: hace DB (pyodbc). "
            "Debe invocarse con asyncio.to_thread."
        )

    @pytest.mark.asyncio
    async def test_eliminar_ordenes_batch_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints import ordenes_compra as oc_module

        hilo = {}

        def fake_db_eliminar_batch(_oc_ids_list):
            hilo["id"] = _hilo_actual()
            return [{"oc_id": "oc-1", "status": "success"}], {
                "eliminadas": 1, "errores": 0, "no_encontradas": 0, "no_permitidas": 0
            }

        monkeypatch.setattr(oc_module, "_db_eliminar_ordenes_compra", fake_db_eliminar_batch)

        request = MagicMock()
        request.headers = {}

        respuesta = await oc_module._delete_ordenes_compra_handler(request, ["oc-1"])

        assert respuesta.status_code == 200
        assert "id" in hilo, "no se llegó a eliminar"
        assert hilo["id"] != _hilo_actual(), (
            "_db_eliminar_ordenes_compra() corrió en el event loop: hace DB (pyodbc). "
            "Debe invocarse con asyncio.to_thread."
        )


class TestSapTestEndpointsNoBloquean:
    """GET /sap/test y /sap/test/direct"""

    def test_test_sap_query_corre_fuera_del_event_loop(self, client, monkeypatch):
        from src.endpoints import sap

        hilo_de_la_query = {}

        def fake_ejecutar(_request, _sku):
            hilo_de_la_query["id"] = _hilo_actual()
            return {"ok": True}

        monkeypatch.setattr(sap, "_ejecutar_test_sap_query", fake_ejecutar)

        respuesta = client.get("/sap/test", params={"sku": "5-0012.9"})

        assert respuesta.status_code == 200
        assert "id" in hilo_de_la_query, "no se llegó a ejecutar la consulta"
        assert hilo_de_la_query["id"] != _hilo_actual(), (
            "_ejecutar_test_sap_query() corrió en el event loop: hace DB (pyodbc) "
            "vía SAPService. Debe invocarse con asyncio.to_thread."
        )

    def test_test_sap_direct_corre_fuera_del_event_loop(self, client, monkeypatch):
        from src.endpoints import sap

        hilo_de_la_query = {}

        def fake_ejecutar(_request, _sku):
            hilo_de_la_query["id"] = _hilo_actual()
            return {"ok": True}

        monkeypatch.setattr(sap, "_ejecutar_test_sap_direct", fake_ejecutar)

        respuesta = client.get("/sap/test/direct", params={"sku": "5-0012.9"})

        assert respuesta.status_code == 200
        assert "id" in hilo_de_la_query, "no se llegó a ejecutar la consulta"
        assert hilo_de_la_query["id"] != _hilo_actual(), (
            "_ejecutar_test_sap_direct() corrió en el event loop: hace DB (pyodbc) "
            "vía SAPClient (OPENQUERY). Debe invocarse con asyncio.to_thread."
        )


class TestTimeoutsDeRedisConfigurados:
    """
    Sin timeouts de socket, redis-py espera para siempre y el thread nunca vuelve:
    el `to_thread` acotaría el daño a una petición, pero seguiría filtrando threads.
    """

    def test_broker_tiene_timeouts_y_health_check(self):
        from src.celery_app import celery_app

        opts = celery_app.conf.broker_transport_options
        assert opts.get("socket_connect_timeout"), "falta socket_connect_timeout en el broker"
        assert opts.get("socket_timeout"), "falta socket_timeout en el broker"
        assert opts.get("health_check_interval"), "falta health_check_interval en el broker"

    def test_socket_timeout_no_corta_el_brpop_del_worker(self):
        """
        kombu hace BRPOP con un timeout propio (1s por defecto). Si socket_timeout
        quedara por debajo, el worker cortaría su propio bucle de consumo en cada
        poll sin tareas.
        """
        from src.celery_app import celery_app

        opts = celery_app.conf.broker_transport_options
        brpop_timeout = opts.get("brpop_timeout", 1)
        assert opts["socket_timeout"] > brpop_timeout * 5, (
            f"socket_timeout={opts['socket_timeout']} está demasiado cerca del "
            f"brpop_timeout={brpop_timeout} de kombu"
        )

    def test_backend_de_resultados_tambien_tiene_timeouts(self):
        from src.celery_app import celery_app

        opts = celery_app.conf.result_backend_transport_options
        assert opts.get("socket_connect_timeout"), "falta socket_connect_timeout en el backend"
        assert opts.get("socket_timeout"), "falta socket_timeout en el backend"
