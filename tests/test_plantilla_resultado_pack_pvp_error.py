"""
Regresión: el flujo async de carga de plantilla (Celery + polling) debe exponer
error_code y validacion_pack_pvp al frontend igual que ya hace con validacion_sap.

Bug real detectado en uso: GET /api/plantillas/resultado/{id} solo copiaba
validacion_sap desde error_data, nunca error_code ni validacion_pack_pvp. Sin
error_code, el frontend no podía distinguir el error PACK_PVP_INVALIDOS_SAP del
error genérico de "código no encontrado en SAP" (el mensaje de ambos contiene
"SAP"), y mostraba el modal equivocado sin el selector SAP/Excel.
"""
import asyncio
import pytest
from unittest.mock import MagicMock

from src.database.services.proceso_estado_service import ProcesoEstadoService
import src.endpoints.plantillas as plantillas_module


class FakeRedisClient:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value


class TestMarcarErrorGuardaErrorCode:
    def _service_con_estado_inicial(self, process_id="plantilla-abc123"):
        service = ProcesoEstadoService.__new__(ProcesoEstadoService)
        service.redis_client = FakeRedisClient()
        service._guardar_estado(process_id, {
            "process_id": process_id,
            "status": "processing",
            "progress": 50,
            "version": 1,
        })
        return service

    def test_marcar_error_guarda_error_code_y_error_data(self):
        service = self._service_con_estado_inicial()
        service.marcar_error(
            "plantilla-abc123",
            "Existen 4 discrepancia(s) de Pack/PVP contra SAP",
            error_data={"validacion_pack_pvp": {"pack_mismatches": [{"codigo": "R311.AMAZ-4-1012"}]}},
            error_code="PACK_PVP_INVALIDOS_SAP",
        )
        estado = service._obtener_estado("plantilla-abc123")
        assert estado["error_code"] == "PACK_PVP_INVALIDOS_SAP"
        assert estado["error_data"]["validacion_pack_pvp"]["pack_mismatches"][0]["codigo"] == "R311.AMAZ-4-1012"

    def test_marcar_error_sin_error_code_no_agrega_la_clave(self):
        service = self._service_con_estado_inicial()
        service.marcar_error("plantilla-abc123", "Error genérico")
        estado = service._obtener_estado("plantilla-abc123")
        assert "error_code" not in estado


class TestObtenerResultadoPlantillaExponeValidacionPackPvp:
    @pytest.fixture(autouse=True)
    def _mock_proceso_estado_service(self, monkeypatch):
        self._estado = {
            "status": "error",
            "message": "Error: Existen 4 discrepancia(s) de Pack/PVP contra SAP",
            "error": "Existen 4 discrepancia(s) de Pack/PVP contra SAP",
            "error_code": "PACK_PVP_INVALIDOS_SAP",
            "error_data": {
                "validacion_pack_pvp": {
                    "pack_mismatches": [{"codigo": "R311.AMAZ-4-1012", "pack_excel": "X6", "pack_sap": "X1"}],
                    "pvp_mismatches": [],
                    "mensajes": ["Pack no coincide para R311.AMAZ-4-1012"],
                }
            },
            "user_id": None,
        }
        fake_service = MagicMock()
        fake_service.obtener_estado.return_value = self._estado
        monkeypatch.setattr(plantillas_module, "ProcesoEstadoService", lambda: fake_service)
        monkeypatch.setattr(plantillas_module, "get_user_id", lambda user: "cortiz@mabeltrading.com.ec")

    def test_incluye_error_code_y_validacion_pack_pvp_en_la_respuesta(self):
        response = asyncio.run(
            plantillas_module._obtener_resultado_plantilla_handler("plantilla-cd9612fd5e84", user={})
        )
        assert response.status_code == 400
        import json
        content = json.loads(response.body)
        assert content["error_code"] == "PACK_PVP_INVALIDOS_SAP"
        assert content["validacion_pack_pvp"]["pack_mismatches"][0]["codigo"] == "R311.AMAZ-4-1012"
