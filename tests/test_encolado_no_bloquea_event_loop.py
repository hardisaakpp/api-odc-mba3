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
from fastapi import FastAPI
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


class TestObtenerDistribucionNoBloquea:
    """GET /api/pedidos/{pedido_id}/distribucion"""

    @pytest.mark.asyncio
    async def test_obtener_distribucion_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints.pedidos.redistribucion import endpoints_core as ec

        hilo = {}

        def fake_db_obtener(_pedido_id, _version):
            hilo["id"] = _hilo_actual()
            return ec.DistribucionPedidoResponse(
                pedido_id="p1", numero_pedido="PED-1", version_actual=1,
                estado_pedido="REDISTRIBUIDO", puede_descartar=False, productos=[]
            )

        monkeypatch.setattr(ec, "_db_obtener_distribucion", fake_db_obtener)

        respuesta = await ec._handle_obtener_distribucion("p1", None)

        assert respuesta.pedido_id == "p1"
        assert "id" in hilo, "no se llegó a obtener la distribución"
        assert hilo["id"] != _hilo_actual(), (
            "_db_obtener_distribucion() corrió en el event loop: hace DB (pyodbc). "
            "Debe invocarse con asyncio.to_thread."
        )

    @pytest.mark.asyncio
    async def test_redistribuir_pedido_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints.pedidos.redistribucion import endpoints_core as ec

        hilo = {}

        def fake_db_redistribuir(_pedido_id, _request_body, _user_id, _audit):
            hilo["id"] = _hilo_actual()
            resultado = {"mensaje": "ok", "pedido_id": "p1", "version": 1, "distribuciones_insertadas": 3}
            pedido_data = {"cabecera": {"numero_pedido": "PED-1"}}
            return resultado, pedido_data

        async def fake_notificar(*_a, **_k):
            return None

        monkeypatch.setattr(ec, "_db_redistribuir_pedido", fake_db_redistribuir)
        monkeypatch.setattr(ec, "get_user_id", lambda _user: "u1")
        monkeypatch.setattr(ec, "get_audit_context", lambda *_a, **_k: {})
        monkeypatch.setattr(ec, "notificar_redistribucion_creada", fake_notificar)

        respuesta = await ec._handle_redistribuir_pedido(
            "p1", MagicMock(), user={"username": "u1"}, request=MagicMock()
        )

        assert respuesta.status_code == 200
        assert "id" in hilo, "no se llegó a redistribuir"
        assert hilo["id"] != _hilo_actual(), (
            "_db_redistribuir_pedido() corrió en el event loop: hace DB (pyodbc). "
            "Debe invocarse con asyncio.to_thread."
        )

    @pytest.mark.asyncio
    async def test_obtener_reporte_diferencias_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints.pedidos.redistribucion import endpoints_core as ec

        hilo = {}

        def fake_db_reporte(_pedido_id, _version):
            hilo["id"] = _hilo_actual()
            return ec.ReporteDiferenciasResponse(
                pedido_id="p1", numero_pedido="PED-1", version=1,
                fecha_generacion=ec.ahora_naive(),
                total_productos=0, total_cantidad_solicitada=0, total_cantidad_confirmada=0,
                total_cantidad_asignada=0, total_diferencia_cantidad=0,
                total_costo_original=0, total_costo_ajustado=0, total_diferencia_costo=0,
                diferencias_productos=[], diferencias_tiendas=[]
            )

        monkeypatch.setattr(ec, "_db_obtener_reporte_diferencias", fake_db_reporte)

        respuesta = await ec._handle_obtener_reporte_diferencias("p1", None)

        assert respuesta.pedido_id == "p1"
        assert "id" in hilo, "no se llegó a obtener el reporte"
        assert hilo["id"] != _hilo_actual(), (
            "_db_obtener_reporte_diferencias() corrió en el event loop: hace DB (pyodbc). "
            "Debe invocarse con asyncio.to_thread."
        )

    @pytest.mark.asyncio
    async def test_exportar_reporte_diferencias_excel_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints.pedidos.redistribucion import endpoints_core as ec
        from fastapi.responses import StreamingResponse

        hilo = {}

        def fake_db_exportar(_pedido_id, _version):
            hilo["id"] = _hilo_actual()
            return StreamingResponse(iter([b""]), media_type="application/octet-stream")

        monkeypatch.setattr(ec, "_db_exportar_reporte_diferencias_excel", fake_db_exportar)

        respuesta = await ec._handle_exportar_reporte_diferencias_excel("p1", None)

        assert isinstance(respuesta, StreamingResponse)
        assert "id" in hilo, "no se llegó a exportar"
        assert hilo["id"] != _hilo_actual(), (
            "_db_exportar_reporte_diferencias_excel() corrió en el event loop: hace DB (pyodbc) "
            "y genera el Excel. Debe invocarse con asyncio.to_thread."
        )


class TestConfirmarRedistribucionNoBloquea:
    """POST /api/pedidos/{pedido_id}/confirmar-redistribucion"""

    @pytest.mark.asyncio
    async def test_ambas_fases_corren_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints.pedidos.redistribucion import endpoints_core as ec

        hilos = {}

        def fake_db_confirmar(_pedido_id, _request_body, _user_id, _audit):
            hilos["fase1"] = _hilo_actual()
            resultado = {"version_confirmada": 2, "mensaje": "ok"}
            pedido_data = {"cabecera": {"numero_pedido": "PED-1"}}
            return resultado, pedido_data, "PENDIENTE"

        def fake_db_procesar_sap(_pedido_id, _user_id, _audit):
            hilos["fase2"] = _hilo_actual()
            return {"status": "success"}, True

        async def fake_notificar(*_a, **_k):
            return None

        monkeypatch.setattr(ec, "_db_confirmar_redistribucion", fake_db_confirmar)
        monkeypatch.setattr(ec, "_db_procesar_sap_redistribucion", fake_db_procesar_sap)
        monkeypatch.setattr(ec, "get_user_id", lambda _user: "u1")
        monkeypatch.setattr(ec, "get_audit_context", lambda *_a, **_k: {})
        monkeypatch.setattr(ec, "notificar_redistribucion_confirmada", fake_notificar)
        monkeypatch.setattr(ec, "notificar_redistribucion_procesada_sap", fake_notificar)

        respuesta = await ec._handle_confirmar_redistribucion(
            "p1", MagicMock(), user={"username": "u1"}, request=MagicMock()
        )

        assert respuesta.estado_nuevo == "CONFIRMADO REDISTRIBUCION"
        assert "fase1" in hilos, "no se llegó a confirmar la redistribución"
        assert "fase2" in hilos, "no se llegó a procesar SAP"
        assert hilos["fase1"] != _hilo_actual(), (
            "_db_confirmar_redistribucion() corrió en el event loop: hace DB (pyodbc). "
            "Debe invocarse con asyncio.to_thread."
        )
        assert hilos["fase2"] != _hilo_actual(), (
            "_db_procesar_sap_redistribucion() corrió en el event loop: hace DB (pyodbc) y "
            "una llamada HTTP a SAP. Debe invocarse con asyncio.to_thread."
        )

    @pytest.mark.asyncio
    async def test_error_en_fase_sap_no_rompe_la_confirmacion_ya_hecha(self, monkeypatch):
        """El error de SAP se degrada a warning: la redistribución ya confirmada en fase 1 se preserva."""
        from src.endpoints.pedidos.redistribucion import endpoints_core as ec

        def fake_db_confirmar(_pedido_id, _request_body, _user_id, _audit):
            resultado = {"version_confirmada": 2, "mensaje": "ok"}
            pedido_data = {"cabecera": {"numero_pedido": "PED-1"}}
            return resultado, pedido_data, "PENDIENTE"

        def fake_db_procesar_sap_falla(_pedido_id, _user_id, _audit):
            raise RuntimeError("SAP caído")

        async def fake_notificar(*_a, **_k):
            return None

        monkeypatch.setattr(ec, "_db_confirmar_redistribucion", fake_db_confirmar)
        monkeypatch.setattr(ec, "_db_procesar_sap_redistribucion", fake_db_procesar_sap_falla)
        monkeypatch.setattr(ec, "get_user_id", lambda _user: "u1")
        monkeypatch.setattr(ec, "get_audit_context", lambda *_a, **_k: {})
        monkeypatch.setattr(ec, "notificar_redistribucion_confirmada", fake_notificar)

        respuesta = await ec._handle_confirmar_redistribucion(
            "p1", MagicMock(), user={"username": "u1"}, request=MagicMock()
        )

        assert respuesta.estado_nuevo == "REDISTRIBUIDO"
        assert respuesta.version_confirmada == 2


class TestBorradorRedistribucionNoBloquea:
    """Endpoints de borrador y datos iniciales de redistribución."""

    @pytest.mark.asyncio
    async def test_guardar_borrador_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints.pedidos.redistribucion import endpoints_borrador as eb

        hilo = {}

        def fake_db_guardar(_numero_pedido, _request_body, _user_id, _audit):
            hilo["id"] = _hilo_actual()
            return eb.GuardarBorradorResponse(
                pedido_id="p1", numero_pedido="PED-1",
                fecha_guardado=eb.ahora_naive(), message="ok"
            )

        monkeypatch.setattr(eb, "_db_guardar_borrador", fake_db_guardar)
        monkeypatch.setattr(eb, "get_user_id", lambda _user: "u1")
        monkeypatch.setattr(eb, "get_audit_context", lambda *_a, **_k: {})

        ajuste = eb.AjusteDetalle(
            codigo_producto="P1",
            descripcion="Producto 1",
            cantidad_solicitada=10,
            cantidad_confirmada=10,
            cantidad_ajustada=10,
            distribucion_tiendas=[
                eb.DistribucionTiendaFrontend(tienda_codigo="T001", cantidad=10)
            ],
        )
        request_body = eb.GuardarBorradorRequest(ajustes_detalle=[ajuste])
        respuesta = await eb._guardar_borrador_handler(
            request=object(), numero_pedido="PED-1", request_body=request_body, user={"username": "u1"}
        )

        assert respuesta.message == "ok"
        assert "id" in hilo, "no se llegó a guardar el borrador"
        assert hilo["id"] != _hilo_actual(), (
            "_db_guardar_borrador() corrió en el event loop: hace DB (pyodbc). "
            "Debe invocarse con asyncio.to_thread."
        )

    @pytest.mark.asyncio
    async def test_obtener_borrador_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints.pedidos.redistribucion import endpoints_borrador as eb

        hilo = {}

        def fake_db_obtener(_numero_pedido):
            hilo["id"] = _hilo_actual()
            return eb.BorradorResponse(status="success", ajustes_detalle=[], fecha_guardado=None, message="ok")

        monkeypatch.setattr(eb, "_db_obtener_borrador", fake_db_obtener)

        respuesta = await eb._obtener_borrador_handler("PED-1")

        assert respuesta.message == "ok"
        assert "id" in hilo, "no se llegó a obtener el borrador"
        assert hilo["id"] != _hilo_actual(), (
            "_db_obtener_borrador() corrió en el event loop: hace DB (pyodbc). "
            "Debe invocarse con asyncio.to_thread."
        )

    @pytest.mark.asyncio
    async def test_obtener_datos_iniciales_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints.pedidos.redistribucion import endpoints_borrador as eb

        hilo = {}

        def fake_db_datos_iniciales(_numero_pedido, _solo_lectura):
            hilo["id"] = _hilo_actual()
            return eb.BorradorResponse(ajustes_detalle=[], fecha_guardado=eb.ahora_naive())

        monkeypatch.setattr(eb, "_db_obtener_datos_iniciales", fake_db_datos_iniciales)

        respuesta = await eb._obtener_datos_iniciales_handler("PED-1", None)

        assert respuesta.ajustes_detalle == []
        assert "id" in hilo, "no se llegó a obtener los datos iniciales"
        assert hilo["id"] != _hilo_actual(), (
            "_db_obtener_datos_iniciales() corrió en el event loop: hace DB (pyodbc). "
            "Debe invocarse con asyncio.to_thread."
        )


class TestDescargarPedidoExcelNoBloquea:
    """GET /api/pedidos/{pedido_id}/descargar-excel"""

    @pytest.mark.asyncio
    async def test_generar_excel_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints.pedidos import pedidos_descarga_endpoints as descarga

        hilo = {}

        def fake_db_generar(_pedido_id, _username):
            hilo["id"] = _hilo_actual()
            return JSONResponse(status_code=200, content={"status": "ok"})

        monkeypatch.setattr(descarga, "_db_generar_pedido_excel", fake_db_generar)

        app = FastAPI()
        descarga.register_pedidos_descarga_endpoints(app)
        handler = next(
            r for r in app.routes if getattr(r, "path", None) == "/api/pedidos/{pedido_id}/descargar-excel"
        ).endpoint

        respuesta = await handler(pedido_id="ped-1", user={"username": "u1"})

        assert respuesta.status_code == 200
        assert "id" in hilo, "no se llegó a generar el excel"
        assert hilo["id"] != _hilo_actual(), (
            "_db_generar_pedido_excel() corrió en el event loop: hace DB (pyodbc) y "
            "genera el Excel. Debe invocarse con asyncio.to_thread."
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
