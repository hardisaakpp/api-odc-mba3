"""
Tests de la tarea de reconciliación automática de Solicitudes de Transferencia.

Cubre: antigüedad, notificación única vía Redis, clasificación transitorio vs.
no-transitorio, y el enrutamiento de resultados en _reconciliar_oc (éxito / sin
pendientes / escalamiento inmediato / escalamiento por tiempo).
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from src.tasks.celery_reconciliar_transferencias import (
    _horas_desde_envio,
    _ya_fue_notificado,
    _marcar_notificado,
    _tiene_error_no_transitorio,
    _evaluar_escalamiento_por_tiempo,
    _reconciliar_oc,
)
from src.utils.timezone import ahora_naive


class TestHorasDesdeEnvio:
    def test_sin_updated_at_retorna_cero(self):
        assert _horas_desde_envio({}) == 0.0

    def test_valor_invalido_retorna_cero(self):
        assert _horas_desde_envio({"updated_at": "no-es-fecha"}) == 0.0

    def test_calcula_horas_transcurridas(self):
        hace_5h = (ahora_naive() - timedelta(hours=5)).isoformat()
        horas = _horas_desde_envio({"updated_at": hace_5h})
        assert 4.9 < horas < 5.1


class TestNotificacionRedis:
    def test_ya_fue_notificado_true(self):
        client = MagicMock()
        client.exists.return_value = 1
        assert _ya_fue_notificado(client, "oc-1") is True

    def test_ya_fue_notificado_false(self):
        client = MagicMock()
        client.exists.return_value = 0
        assert _ya_fue_notificado(client, "oc-1") is False

    def test_marcar_notificado_usa_ttl(self):
        client = MagicMock()
        _marcar_notificado(client, "oc-1")
        client.setex.assert_called_once()
        args = client.setex.call_args[0]
        assert args[0] == "reconciliar-st:notificado:oc-1"
        assert args[1] == 24 * 3600


class TestTieneErrorNoTransitorio:
    def test_sin_resultados_es_false(self):
        assert _tiene_error_no_transitorio({}) is False

    def test_todas_exitosas_es_false(self):
        resultado_st = {"resultados": [{"success": True}]}
        assert _tiene_error_no_transitorio(resultado_st) is False

    def test_error_transitorio_es_false(self):
        resultado_st = {"resultados": [{"success": False, "error": "Error de conexión con SAP"}]}
        assert _tiene_error_no_transitorio(resultado_st) is False

    def test_error_no_transitorio_es_true(self):
        resultado_st = {
            "resultados": [
                {"success": False, "error": "Artículo no habilitado para compra en esta bodega"},
            ]
        }
        assert _tiene_error_no_transitorio(resultado_st) is True

    def test_una_transitoria_y_otra_no_es_true(self):
        resultado_st = {
            "resultados": [
                {"success": False, "error": "Timeout de conexión"},
                {"success": False, "error": "Item congelado"},
            ]
        }
        assert _tiene_error_no_transitorio(resultado_st) is True


class TestReconciliarOc:
    def test_omite_si_ya_notificado(self):
        redis_client = MagicMock()
        with patch(
            "src.tasks.celery_reconciliar_transferencias._ya_fue_notificado", return_value=True
        ):
            resultado = _reconciliar_oc("oc-1", redis_client)
        assert resultado is None

    def test_omite_si_lock_ocupado(self):
        redis_client = MagicMock()
        with patch(
            "src.tasks.celery_reconciliar_transferencias._ya_fue_notificado", return_value=False
        ), patch(
            "src.tasks.celery_reconciliar_transferencias.redis_lock_reintento_st"
        ) as mock_lock:
            mock_lock.return_value.__enter__.return_value = False
            resultado = _reconciliar_oc("oc-1", redis_client)
        assert resultado is None

    def test_no_pendientes_no_escala(self):
        redis_client = MagicMock()
        with patch(
            "src.tasks.celery_reconciliar_transferencias._ya_fue_notificado", return_value=False
        ), patch(
            "src.tasks.celery_reconciliar_transferencias.redis_lock_reintento_st"
        ) as mock_lock, patch(
            "src.tasks.celery_reconciliar_transferencias.StockTransferService"
        ) as MockService, patch(
            "src.tasks.celery_reconciliar_transferencias._evaluar_escalamiento_por_tiempo"
        ) as mock_escalar, patch(
            "src.tasks.celery_reconciliar_transferencias._escalar_inmediato"
        ) as mock_inmediato:
            mock_lock.return_value.__enter__.return_value = True
            MockService.return_value.reintentar_pendientes.return_value = {"status": "no_pendientes"}
            resultado = _reconciliar_oc("oc-1", redis_client)
        assert resultado is not None
        assert resultado["status"] == "no_pendientes"
        mock_escalar.assert_not_called()
        mock_inmediato.assert_not_called()

    def test_exito_no_escala(self):
        redis_client = MagicMock()
        with patch(
            "src.tasks.celery_reconciliar_transferencias._ya_fue_notificado", return_value=False
        ), patch(
            "src.tasks.celery_reconciliar_transferencias.redis_lock_reintento_st"
        ) as mock_lock, patch(
            "src.tasks.celery_reconciliar_transferencias.StockTransferService"
        ) as MockService, patch(
            "src.tasks.celery_reconciliar_transferencias._evaluar_escalamiento_por_tiempo"
        ) as mock_escalar, patch(
            "src.tasks.celery_reconciliar_transferencias._escalar_inmediato"
        ) as mock_inmediato:
            mock_lock.return_value.__enter__.return_value = True
            MockService.return_value.reintentar_pendientes.return_value = {"status": "success"}
            resultado = _reconciliar_oc("oc-1", redis_client)
        assert resultado is not None
        assert resultado["status"] == "success"
        mock_escalar.assert_not_called()
        mock_inmediato.assert_not_called()

    def test_partial_con_error_transitorio_evalua_por_tiempo(self):
        redis_client = MagicMock()
        resultado_st = {"resultados": [{"success": False, "error": "Timeout de conexión"}]}
        with patch(
            "src.tasks.celery_reconciliar_transferencias._ya_fue_notificado", return_value=False
        ), patch(
            "src.tasks.celery_reconciliar_transferencias.redis_lock_reintento_st"
        ) as mock_lock, patch(
            "src.tasks.celery_reconciliar_transferencias.StockTransferService"
        ) as MockService, patch(
            "src.tasks.celery_reconciliar_transferencias._evaluar_escalamiento_por_tiempo"
        ) as mock_escalar, patch(
            "src.tasks.celery_reconciliar_transferencias._escalar_inmediato"
        ) as mock_inmediato:
            mock_lock.return_value.__enter__.return_value = True
            MockService.return_value.reintentar_pendientes.return_value = {
                "status": "partial", "resultado_st": resultado_st,
            }
            resultado = _reconciliar_oc("oc-1", redis_client)
        assert resultado is not None
        assert resultado["status"] == "partial"
        mock_escalar.assert_called_once_with("oc-1", resultado_st, redis_client)
        mock_inmediato.assert_not_called()

    def test_partial_con_error_no_transitorio_escala_inmediato(self):
        redis_client = MagicMock()
        resultado_st = {"resultados": [{"success": False, "error": "Item congelado en SAP"}]}
        with patch(
            "src.tasks.celery_reconciliar_transferencias._ya_fue_notificado", return_value=False
        ), patch(
            "src.tasks.celery_reconciliar_transferencias.redis_lock_reintento_st"
        ) as mock_lock, patch(
            "src.tasks.celery_reconciliar_transferencias.StockTransferService"
        ) as MockService, patch(
            "src.tasks.celery_reconciliar_transferencias._evaluar_escalamiento_por_tiempo"
        ) as mock_escalar, patch(
            "src.tasks.celery_reconciliar_transferencias._escalar_inmediato"
        ) as mock_inmediato:
            mock_lock.return_value.__enter__.return_value = True
            MockService.return_value.reintentar_pendientes.return_value = {
                "status": "partial", "resultado_st": resultado_st,
            }
            resultado = _reconciliar_oc("oc-1", redis_client)
        assert resultado is not None
        assert resultado["status"] == "partial"
        mock_inmediato.assert_called_once_with("oc-1", resultado_st, redis_client)
        mock_escalar.assert_not_called()


class TestEvaluarEscalamientoPorTiempo:
    def test_no_escala_bajo_el_umbral(self):
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {"updated_at": ahora_naive().isoformat()}
        with patch(
            "src.tasks.celery_reconciliar_transferencias.OrdenCompraRepository", return_value=oc_repo
        ), patch(
            "src.tasks.celery_reconciliar_transferencias.get_db_connection_context"
        ) as mock_ctx, patch(
            "src.tasks.celery_reconciliar_transferencias._escalar_a_tecnicos"
        ) as mock_escalar, patch(
            "src.tasks.celery_reconciliar_transferencias._marcar_notificado"
        ) as mock_marcar:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            _evaluar_escalamiento_por_tiempo("oc-1", {}, MagicMock())
        mock_escalar.assert_not_called()
        mock_marcar.assert_not_called()

    def test_escala_pasado_el_umbral(self):
        hace_5h = (ahora_naive() - timedelta(hours=5)).isoformat()
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {"updated_at": hace_5h}
        redis_client = MagicMock()
        resultado_st = {"resultados": [{"success": False, "error": "Timeout"}]}
        with patch(
            "src.tasks.celery_reconciliar_transferencias.OrdenCompraRepository", return_value=oc_repo
        ), patch(
            "src.tasks.celery_reconciliar_transferencias.get_db_connection_context"
        ) as mock_ctx, patch(
            "src.tasks.celery_reconciliar_transferencias._escalar_a_tecnicos"
        ) as mock_escalar, patch(
            "src.tasks.celery_reconciliar_transferencias._marcar_notificado"
        ) as mock_marcar:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            _evaluar_escalamiento_por_tiempo("oc-1", resultado_st, redis_client)
        mock_escalar.assert_called_once_with(oc_repo.get_existing_cabecera.return_value, resultado_st)
        mock_marcar.assert_called_once_with(redis_client, "oc-1")
