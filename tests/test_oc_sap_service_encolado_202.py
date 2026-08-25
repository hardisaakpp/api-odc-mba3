"""
Tests para el manejo de HTTP 202 (ODC encolada por el middleware al crear la
Purchase Order) en OCSAPService.

Bug real que corrige: create_purchase_order no distinguía un 202 (SAP saturado,
el middleware encola el job) de un error real de SAP. La ODC quedaba marcada
"ERROR" sin persistir el job_id, y el botón de reintento reenviaba la creación a
ciegas. Incidente real: la ODC 24711 quedó "ERROR" por un 202, pero el job se
completó en SAP en segundo plano; el reintento manual generó una ODC 24712
duplicada con sus 23 Solicitudes de Transferencia también duplicadas.

Ahora un 202 se persiste como estado "ENCOLADA" con su job_id, y antes de
reintentar se consulta primero GET /api/v1/jobs/{jobId} (mismo patrón ya usado
para Solicitudes de Transferencia, ver StockTransferService._resolver_jobs_
encolados_pendientes).
"""

from unittest.mock import MagicMock, patch

from src.database.services.oc_sap_service import OCSAPService


def _service_con_sap_client_mock():
    service = OCSAPService.__new__(OCSAPService)
    service.sap_client = MagicMock()
    return service


class TestManejarFalloEnvioSapQueued:
    def test_202_marca_encolada_no_error_y_persiste_job_id(self):
        oc_repo = MagicMock()
        result = {"success": False}  # estado inicial real que arma enviar_oc_a_sap
        sap_response = {
            "success": False, "queued": True, "job_id": "job-789",
            "job_status": "ENCOLADO", "status_code": 202,
        }

        OCSAPService._manejar_fallo_envio_sap("oc-1", sap_response, {"attempts": 1}, oc_repo, result)

        assert result["success"] is False
        assert result["queued"] is True
        assert result["job_id"] == "job-789"
        assert result["retry_recommended"] is False
        assert "202" not in result["error_message"]  # mensaje honesto, no jerga HTTP

        oc_repo.update_estado.assert_called_once()
        args, kwargs = oc_repo.update_estado.call_args
        assert args[0] == "oc-1"
        assert args[1] == "ENCOLADA"
        assert kwargs["job_id"] == "job-789"

    def test_error_real_de_sap_sigue_marcando_error(self):
        """Regresión: un error real (no queued) debe seguir el camino de siempre."""
        oc_repo = MagicMock()
        result = {"success": False}
        sap_response = {"success": False, "error": "SKU no existe", "error_code": -123}

        OCSAPService._manejar_fallo_envio_sap("oc-1", sap_response, {"attempts": 1}, oc_repo, result)

        assert result["retry_recommended"] is True
        assert "queued" not in result
        args, kwargs = oc_repo.update_estado.call_args
        assert args[1] == "ERROR"


class TestResolverJobEncoladoPrevio:
    def test_no_encolada_no_hace_nada(self):
        service = _service_con_sap_client_mock()
        oc_cabecera = {"estado": "PENDIENTE"}
        result = {}

        resultado = service._resolver_job_encolado_previo("oc-1", oc_cabecera, [], MagicMock(), result)

        assert resultado is None
        service.sap_client.get_job_status.assert_not_called()

    def test_encolada_sin_job_id_no_bloquea(self):
        service = _service_con_sap_client_mock()
        oc_cabecera = {"estado": "ENCOLADA", "job_id": None}
        result = {}

        resultado = service._resolver_job_encolado_previo("oc-1", oc_cabecera, [], MagicMock(), result)

        assert resultado is None
        service.sap_client.get_job_status.assert_not_called()

    def test_job_no_consultable_no_reintenta_y_no_marca_error(self):
        service = _service_con_sap_client_mock()
        service.sap_client.get_job_status.return_value = None
        oc_cabecera = {"estado": "ENCOLADA", "job_id": "job-1"}
        result = {}

        resultado = service._resolver_job_encolado_previo("oc-1", oc_cabecera, [], MagicMock(), result)

        assert resultado is False
        assert result["queued"] is True
        assert result["retry_recommended"] is False

    def test_job_completado_adopta_doc_entry_sin_recrear(self):
        service = _service_con_sap_client_mock()
        service.sap_client.get_job_status.return_value = {
            "status": "COMPLETADO",
            "result": {"docEntry": 555, "docNum": 24711},
        }
        oc_cabecera = {"estado": "ENCOLADA", "job_id": "job-1"}
        oc_repo = MagicMock()
        result = {}

        with patch.object(service, "_procesar_oc_exitosa") as mock_procesar:
            resultado = service._resolver_job_encolado_previo("oc-1", oc_cabecera, ["detalle"], oc_repo, result)

        assert resultado is False
        mock_procesar.assert_called_once()
        args, kwargs = mock_procesar.call_args
        sap_response_sintetico = args[3]
        assert sap_response_sintetico["doc_entry"] == 555
        assert sap_response_sintetico["doc_num"] == 24711
        assert sap_response_sintetico["success"] is True

    def test_job_completado_sin_doc_entry_se_deja_para_el_proximo_intento(self):
        service = _service_con_sap_client_mock()
        service.sap_client.get_job_status.return_value = {"status": "COMPLETADO", "result": {}}
        oc_cabecera = {"estado": "ENCOLADA", "job_id": "job-1"}
        result = {}

        with patch.object(service, "_procesar_oc_exitosa") as mock_procesar:
            resultado = service._resolver_job_encolado_previo("oc-1", oc_cabecera, [], MagicMock(), result)

        assert resultado is False
        assert result["queued"] is True
        mock_procesar.assert_not_called()

    def test_job_aun_encolado_o_procesando_no_reintenta(self):
        service = _service_con_sap_client_mock()
        for status in ("ENCOLADO", "PROCESANDO"):
            service.sap_client.get_job_status.return_value = {"status": status}
            oc_cabecera = {"estado": "ENCOLADA", "job_id": "job-1"}
            result = {}

            resultado = service._resolver_job_encolado_previo("oc-1", oc_cabecera, [], MagicMock(), result)

            assert resultado is False, status
            assert result["queued"] is True
            assert result["retry_recommended"] is False

    def test_job_error_real_libera_la_oc_para_un_intento_normal(self):
        service = _service_con_sap_client_mock()
        service.sap_client.get_job_status.return_value = {
            "status": "ERROR", "error": "Artículo no habilitado en la bodega",
        }
        oc_cabecera = {"estado": "ENCOLADA", "job_id": "job-1"}
        oc_repo = MagicMock()
        result = {}

        resultado = service._resolver_job_encolado_previo("oc-1", oc_cabecera, [], oc_repo, result)

        assert resultado is True
        assert oc_cabecera["estado"] == "PENDIENTE"
        assert oc_cabecera["job_id"] is None
        args, kwargs = oc_repo.update_estado.call_args
        assert args[1] == "PENDIENTE"
        assert "Artículo no habilitado" in kwargs["respuesta_sap"]


class TestEnviarOcASapYaEnviada:
    def test_no_reenvia_si_ya_esta_enviada(self):
        """No-op idempotente: puede llegar aquí en un reintento del pedido completo
        donde esta ODC en particular ya había tenido éxito (otra ODC hermana fue
        la que falló/quedó encolada)."""
        service = _service_con_sap_client_mock()
        oc_repo = MagicMock()
        oc_repo.get_existing_cabecera.return_value = {
            "estado": "ENVIADA", "doc_entry": 111, "numero_oc_sap": "222",
        }
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_redis = MagicMock()
        mock_redis.lock.return_value = mock_lock

        with patch("src.database.services.oc_sap_service.get_redis_client", return_value=mock_redis):
            result = service.enviar_oc_a_sap(oc_repo, "oc-1")

        assert result["success"] is True
        assert result["already_sent"] is True
        assert result["doc_entry"] == 111
        oc_repo.get_detalles.assert_not_called()
        service.sap_client.create_purchase_order.assert_not_called()
