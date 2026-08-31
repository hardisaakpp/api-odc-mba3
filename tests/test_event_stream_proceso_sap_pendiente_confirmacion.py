"""
Fase 2 (tiempo real, F2.4) del arreglo de raíz: el SSE de proceso-sap no debe
cortar de golpe en 'completed' si todavía queda alguna Solicitud de
Transferencia sin confirmar -- le da una ventana extra para que una
reconciliación (manual o Celery Beat) llegue a corregir el resultado mientras
el cliente sigue escuchando (ver _corregir_snapshot_proceso_original).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.endpoints.pedidos.redistribucion.endpoints_proceso import (
    _event_stream_proceso_sap,
    _tiene_st_pendiente_confirmacion,
)


def _resultado(pendientes: int, envios_sap=None):
    envio = {
        "oc_id": "oc-1",
        "solicitudes_transferencia": {"transferencias_pendientes_confirmacion": pendientes},
    }
    return {
        "status": "success",
        "envio_sap": envio,
        "envios_sap": envios_sap if envios_sap is not None else [envio],
    }


class TestTieneStPendienteConfirmacion:
    def test_false_sin_resultado(self):
        assert _tiene_st_pendiente_confirmacion(None) is False
        assert _tiene_st_pendiente_confirmacion({}) is False

    def test_false_sin_pendientes(self):
        assert _tiene_st_pendiente_confirmacion(_resultado(0)) is False

    def test_true_con_pendientes(self):
        assert _tiene_st_pendiente_confirmacion(_resultado(8)) is True

    def test_true_si_cualquier_odc_de_pedido_mixto_tiene_pendientes(self):
        envios = [
            {"oc_id": "oc-RL", "solicitudes_transferencia": {"transferencias_pendientes_confirmacion": 0}},
            {"oc_id": "oc-RG", "solicitudes_transferencia": {"transferencias_pendientes_confirmacion": 3}},
        ]
        assert _tiene_st_pendiente_confirmacion(_resultado(0, envios_sap=envios)) is True

    def test_false_si_solicitudes_transferencia_es_none(self):
        resultado = {"envio_sap": {"oc_id": "oc-1", "solicitudes_transferencia": None}}
        assert _tiene_st_pendiente_confirmacion(resultado) is False


class _FakeRequest:
    async def is_disconnected(self):
        return False


@pytest.mark.asyncio
async def test_sin_pendientes_corta_de_inmediato_como_antes():
    estado_service = MagicMock()
    estado_service.obtener_estado = MagicMock(
        return_value={
            "process_id": "proceso-sap-1",
            "status": "completed",
            "step": "completado",
            "progress": 100,
            "message": "ok",
            "updated_at": "t1",
            "version": 2,
            "resultado": _resultado(0),
        }
    )

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        eventos = [e async for e in _event_stream_proceso_sap(estado_service, "proceso-sap-1", _FakeRequest())]

    assert len(eventos) == 1
    assert '"status": "completed"' in eventos[0]
    mock_sleep.assert_not_called()
    assert estado_service.obtener_estado.call_count == 1


@pytest.mark.asyncio
async def test_con_pendientes_espera_y_corrige_antes_de_cerrar():
    """Simula: 1er tick 'completed' con 8 pendientes; 2do tick (tras la
    reconciliación) ya sin pendientes -- el generador debe emitir AMBOS
    payloads y solo cerrar en el segundo."""
    estados = [
        {
            "process_id": "proceso-sap-1", "status": "completed", "step": "completado", "progress": 100, "message": "ok",
            "updated_at": "t1", "version": 2, "resultado": _resultado(8),
        },
        {
            "process_id": "proceso-sap-1", "status": "completed", "step": "completado", "progress": 100, "message": "ok",
            "updated_at": "t2", "version": 3, "resultado": _resultado(0),
        },
    ]
    estado_service = MagicMock()
    estado_service.obtener_estado = MagicMock(side_effect=estados)

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        eventos = [e async for e in _event_stream_proceso_sap(estado_service, "proceso-sap-1", _FakeRequest())]

    assert len(eventos) == 2
    assert '"version": 2' in eventos[0]
    assert '"version": 3' in eventos[1]
    mock_sleep.assert_called_once_with(5)
    assert estado_service.obtener_estado.call_count == 2


@pytest.mark.asyncio
async def test_con_pendientes_que_nunca_se_resuelven_cierra_tras_la_ventana():
    estado_pendiente = {
        "process_id": "proceso-sap-1", "status": "completed", "step": "completado", "progress": 100, "message": "ok",
        "updated_at": "t1", "version": 2, "resultado": _resultado(8),
    }
    estado_service = MagicMock()
    # Mismo estado siempre (updated_at/version fijos) -- nunca se corrige.
    estado_service.obtener_estado = MagicMock(return_value=estado_pendiente)

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        eventos = [e async for e in _event_stream_proceso_sap(estado_service, "proceso-sap-1", _FakeRequest())]

    # Solo 1 payload (el mismo updated_at/version en todos los ticks siguientes
    # no genera nuevos yields), pero el generador siguió llamando a
    # obtener_estado durante toda la ventana antes de cerrar.
    assert len(eventos) == 1
    # Ventana de 600s en pasos de 5s = 120 iteraciones extra + el tick inicial.
    assert estado_service.obtener_estado.call_count == 121
    assert mock_sleep.call_count == 120


@pytest.mark.asyncio
async def test_error_sigue_cortando_de_inmediato():
    estado_service = MagicMock()
    estado_service.obtener_estado = MagicMock(
        return_value={
            "process_id": "proceso-sap-1", "status": "error", "step": "error", "progress": 50, "message": "falló",
            "updated_at": "t1", "version": 2, "error": "boom",
        }
    )

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        eventos = [e async for e in _event_stream_proceso_sap(estado_service, "proceso-sap-1", _FakeRequest())]

    assert len(eventos) == 1
    mock_sleep.assert_not_called()
