"""
Tests de src.services.celery_availability: disponibilidad de workers Celery y el
colchón de seguridad de la reconciliación diaria de ST.
"""

from unittest.mock import MagicMock, patch

from src.services.celery_availability import (
    celery_worker_available,
    reconciliacion_st_al_dia,
    HEARTBEAT_REDIS_KEY,
    RECONCILIAR_ST_LAST_RUN_REDIS_KEY,
)


class TestCeleryWorkerAvailable:
    def test_true_si_heartbeat_vigente(self):
        client = MagicMock()
        client.exists.return_value = 1
        with patch("src.services.celery_availability.get_redis_client", return_value=client):
            assert celery_worker_available() is True
        client.exists.assert_called_once_with(HEARTBEAT_REDIS_KEY)

    def test_false_si_no_hay_heartbeat(self):
        client = MagicMock()
        client.exists.return_value = 0
        with patch("src.services.celery_availability.get_redis_client", return_value=client):
            assert celery_worker_available() is False

    def test_false_si_redis_falla(self):
        with patch(
            "src.services.celery_availability.get_redis_client",
            side_effect=Exception("redis caído"),
        ):
            assert celery_worker_available() is False


class TestReconciliacionStAlDia:
    def test_true_si_ultima_corrida_vigente(self):
        client = MagicMock()
        client.exists.return_value = 1
        with patch("src.services.celery_availability.get_redis_client", return_value=client):
            assert reconciliacion_st_al_dia() is True
        client.exists.assert_called_once_with(RECONCILIAR_ST_LAST_RUN_REDIS_KEY)

    def test_false_si_la_marca_vencio(self):
        client = MagicMock()
        client.exists.return_value = 0
        with patch("src.services.celery_availability.get_redis_client", return_value=client):
            assert reconciliacion_st_al_dia() is False

    def test_true_si_redis_falla_no_genera_alerta_falsa(self):
        """A diferencia de celery_worker_available, ante un error del chequeo mismo
        se asume True: no tiene sentido alertar de la tarea por un problema del
        propio chequeo."""
        with patch(
            "src.services.celery_availability.get_redis_client",
            side_effect=Exception("redis caído"),
        ):
            assert reconciliacion_st_al_dia() is True
