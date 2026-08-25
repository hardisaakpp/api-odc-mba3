"""
GET /api/plantillas/sap-info-productos

Consulta puntual de Pack / PVP / código de barras en SAP. La usa el modal de
corrección de plantillas: cuando el usuario elige una sugerencia para un código
inválido, con esto sabe en el momento si esa elección además va a chocar en
Pack/PVP — y resuelve todo en una sola ronda, en vez de descubrirlo al reintentar.
"""

import threading

import pytest
from fastapi import HTTPException


class TestParseoDeCodigos:
    def test_divide_limpia_y_deduplica_preservando_orden(self):
        from src.endpoints.plantillas import _parsear_codigos_sap_info

        assert _parsear_codigos_sap_info(" A , B ,A,, C ") == ["A", "B", "C"]

    def test_lista_vacia_es_400(self):
        from src.endpoints.plantillas import _parsear_codigos_sap_info

        with pytest.raises(HTTPException) as exc:
            _parsear_codigos_sap_info("  , ,")
        assert exc.value.status_code == 400

    def test_pasarse_del_tope_es_400_y_no_consulta_sap(self):
        from src.endpoints.plantillas import _parsear_codigos_sap_info, MAX_CODIGOS_SAP_INFO

        codigos = ",".join(f"COD{i}" for i in range(MAX_CODIGOS_SAP_INFO + 1))
        with pytest.raises(HTTPException) as exc:
            _parsear_codigos_sap_info(codigos)
        assert exc.value.status_code == 400
        assert str(MAX_CODIGOS_SAP_INFO) in str(exc.value.detail)

    def test_el_tope_exacto_se_acepta(self):
        from src.endpoints.plantillas import _parsear_codigos_sap_info, MAX_CODIGOS_SAP_INFO

        codigos = ",".join(f"COD{i}" for i in range(MAX_CODIGOS_SAP_INFO))
        assert len(_parsear_codigos_sap_info(codigos)) == MAX_CODIGOS_SAP_INFO


class TestMapeoDeRespuesta:
    def _fake_service(self, monkeypatch, resultados):
        import src.database.services.sap_service as mod

        class FakeSAPService:
            def get_or_fetch_productos_batch(self, codigos, force_refresh=False):
                return resultados

        monkeypatch.setattr(mod, "SAPService", FakeSAPService)

    def test_producto_encontrado_expone_pack_pvp_y_barras(self, monkeypatch):
        from src.endpoints.plantillas import _consultar_sap_info_productos

        self._fake_service(monkeypatch, {
            "R311.AMAZ-4-1012": {
                "pack_sap": "X1",
                "pvp_sap": 6.99,
                "codigo_barras": "7861215678025",
                "item_name": "COLORS C. CASUAL LISA TUCAN SURTIDO X1",
            }
        })

        out = _consultar_sap_info_productos(["R311.AMAZ-4-1012"])["R311.AMAZ-4-1012"]

        assert out == {
            "encontrado": True,
            "motivo": None,
            "pack_sap": "X1",
            "pvp_sap": 6.99,
            "codigo_barras": "7861215678025",
            "item_name": "COLORS C. CASUAL LISA TUCAN SURTIDO X1",
        }

    @pytest.mark.parametrize("error_type", ["no_existe", "inactivo", "mismatch"])
    def test_los_errores_de_sap_no_tumban_la_consulta(self, monkeypatch, error_type):
        """Un código problemático se reporta, no revienta el resto del batch."""
        from src.endpoints.plantillas import _consultar_sap_info_productos

        self._fake_service(monkeypatch, {
            "MALO": {"_error": True, "_error_type": error_type},
            "BUENO": {"pack_sap": "X3", "pvp_sap": 3.99, "codigo_barras": None, "item_name": "OK"},
        })

        out = _consultar_sap_info_productos(["MALO", "BUENO"])

        assert out["MALO"]["encontrado"] is False
        assert out["MALO"]["motivo"] == error_type
        assert out["MALO"]["pvp_sap"] is None
        assert out["BUENO"]["encontrado"] is True
        assert out["BUENO"]["pvp_sap"] == 3.99

    def test_codigo_sin_resolver_vuelve_como_no_encontrado(self, monkeypatch):
        """SAP deshabilitado o batch fallido devuelven None para ese SKU."""
        from src.endpoints.plantillas import _consultar_sap_info_productos

        self._fake_service(monkeypatch, {"X": None})

        out = _consultar_sap_info_productos(["X"])["X"]
        assert out["encontrado"] is False
        assert out["motivo"] is None

    def test_todos_los_codigos_pedidos_aparecen_en_la_respuesta(self, monkeypatch):
        """El frontend indexa por código: ninguno puede faltar en el mapa."""
        from src.endpoints.plantillas import _consultar_sap_info_productos

        self._fake_service(monkeypatch, {})  # el servicio no devolvió nada

        out = _consultar_sap_info_productos(["A", "B", "C"])
        assert sorted(out.keys()) == ["A", "B", "C"]
        assert all(v["encontrado"] is False for v in out.values())


class TestNoBloqueaElEventLoop:
    """
    Misma invariante que el resto de rutas que tocan SAP/SQL: el trabajo bloqueante
    va a un thread. Ver tests/test_encolado_no_bloquea_event_loop.py.
    """

    @pytest.mark.asyncio
    async def test_la_consulta_a_sap_corre_fuera_del_event_loop(self, monkeypatch):
        from src.endpoints import plantillas

        hilo_de_la_consulta = {}

        def fake_consultar(codigos):
            hilo_de_la_consulta["id"] = threading.get_ident()
            return {c: {"encontrado": False} for c in codigos}

        monkeypatch.setattr(plantillas, "_consultar_sap_info_productos", fake_consultar)

        respuesta = await plantillas._sap_info_productos_handler("A,B")

        assert respuesta.status_code == 200
        assert hilo_de_la_consulta["id"] != threading.get_ident(), (
            "_consultar_sap_info_productos() corrió en el event loop: consulta el "
            "cache en SQL Server y el middleware. Debe ir con asyncio.to_thread."
        )
