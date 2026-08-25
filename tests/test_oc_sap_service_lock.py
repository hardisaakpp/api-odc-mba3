"""
Tests para el lock distribuido de envío de ODC a SAP (redis_lock_envio_odc).

Bug real que corrige: 2 requests concurrentes para el mismo oc_id (ej. doble clic
en "Reintentar", o un reintento manual mientras el anterior seguía procesando por
SAP saturado) podían correr en paralelo sin este lock. Si el primero llegaba a SAP
con éxito (DocEntry asignado) pero el segundo fallaba después su propia
prevalidación, su manejador de error pisaba el estado de la OC de vuelta a ERROR
aunque ya estuviera ENVIADA con DocEntry real -- dejando la ODC en un loop: cada
reintento posterior se resetea a PENDIENTE pero la validación de idempotencia (ya
tiene DocEntry) la rechaza de inmediato y la vuelve a marcar ERROR.
"""

from unittest.mock import MagicMock, patch

from src.database.services.oc_sap_service import OCSAPService, redis_lock_envio_odc


class TestRedisLockEnvioOdc:
    def test_lock_adquirido_libera_al_salir(self):
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_client = MagicMock()
        mock_client.lock.return_value = mock_lock
        with patch(
            "src.database.services.oc_sap_service.get_redis_client", return_value=mock_client
        ):
            with redis_lock_envio_odc("oc-1", blocking_timeout=1.0) as acquired:
                assert acquired is True
        mock_lock.release.assert_called_once()

    def test_lock_no_adquirido_no_libera(self):
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = False
        mock_client = MagicMock()
        mock_client.lock.return_value = mock_lock
        with patch(
            "src.database.services.oc_sap_service.get_redis_client", return_value=mock_client
        ):
            with redis_lock_envio_odc("oc-1", blocking_timeout=1.0) as acquired:
                assert acquired is False
        mock_lock.release.assert_not_called()


class TestEnviarOcASapConLockOcupado:
    def _service_con_lock_ocupado(self):
        service = OCSAPService.__new__(OCSAPService)
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = False
        mock_client = MagicMock()
        mock_client.lock.return_value = mock_lock
        return service, mock_client

    def test_no_toca_bd_ni_marca_error_si_otro_envio_esta_en_curso(self):
        """Si el lock no se adquiere, no debe llamarse a la BD en absoluto -- el
        envío en curso es el único que debe determinar el estado final de la ODC."""
        service, mock_client = self._service_con_lock_ocupado()
        oc_repo = MagicMock()

        with patch(
            "src.database.services.oc_sap_service.get_redis_client", return_value=mock_client
        ):
            result = service.enviar_oc_a_sap(oc_repo, "oc-1")

        assert result["success"] is False
        assert result["retry_recommended"] is True
        assert "en curso" in result["error"]
        oc_repo.get_existing_cabecera.assert_not_called()
        oc_repo.update_estado.assert_not_called()
