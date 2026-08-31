"""
Tests de la tarea de reconciliación automática de ODC ENCOLADAS (HTTP 202 del
middleware al crear la Purchase Order, sin resolver).

Cubre el enrutamiento de resultados en _reconciliar_oc (colisión con envío en
curso / sigue encolada / éxito / error real) y el recorrido de la tarea
periódica sobre todas las ODC candidatas.

_reconciliar_oc no tiene lock propio: enviar_oc_a_sap ya usa internamente
redis_lock_envio_odc (ver oc_sap_service.py), que protege contra 2 envíos
concurrentes de la misma oc_id sin importar quién llame. Por eso estos tests
no necesitan (ni deben) mockear ningún lock -- solo el resultado que devuelve
OCSAPService().enviar_oc_a_sap.
"""

from unittest.mock import MagicMock, patch

from src.tasks.celery_reconciliar_ordenes_compra import (
    _reconciliar_envio_estancado,
    _reconciliar_oc,
    reconciliar_ordenes_compra_pendientes,
)


def _patch_db_y_service(resultado_enviar_oc_a_sap):
    mock_ctx = patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context")
    mock_repo_cls = patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository")
    mock_service_cls = patch("src.tasks.celery_reconciliar_ordenes_compra.OCSAPService")
    return mock_ctx, mock_repo_cls, mock_service_cls, resultado_enviar_oc_a_sap


class TestReconciliarOc:
    def test_colision_con_envio_en_curso_no_notifica_a_tecnicos(self):
        """enviar_oc_a_sap ya tiene su propio lock interno (redis_lock_envio_odc):
        si otro envío de la misma ODC está en curso justo cuando la reconciliación
        llama a enviar_oc_a_sap (ej. una reconciliación solapada con un reintento
        manual), enviar_oc_a_sap devuelve success=False con ese mensaje puntual.
        Es una colisión transitoria que se resuelve sola en cuanto termine el otro
        envío -- _reconciliar_oc igual cuenta la ODC como procesada este ciclo, y
        NO debe alarmar a técnicos por ella (mensaje_sugiere_reintento_transitorio
        la clasifica como transitoria)."""
        with patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository") as mock_repo_cls, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OCSAPService") as mock_service_cls, \
                patch(
                    "src.tasks.celery_reconciliar_ordenes_compra._notificar_error_real_a_tecnicos"
                ) as mock_notificar:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            mock_repo_cls.return_value.get_existing_cabecera.return_value = {"proveedor": "P1"}
            mock_service_cls.return_value.enviar_oc_a_sap.return_value = {
                "success": False,
                "error": "Ya hay un envío a SAP en curso para esta ODC. Espera a que termine antes de reintentar.",
            }
            resultado = _reconciliar_oc("oc-1")
        assert resultado is True
        mock_notificar.assert_not_called()

    def test_sigue_encolada_no_es_error(self):
        with patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository"), \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OCSAPService") as mock_service_cls:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            mock_service_cls.return_value.enviar_oc_a_sap.return_value = {
                "success": False, "queued": True, "job_id": "job-1",
            }
            resultado = _reconciliar_oc("oc-1")
        assert resultado is True

    def test_job_completado_se_procesa_como_exito(self):
        with patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository"), \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OCSAPService") as mock_service_cls:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            mock_service_cls.return_value.enviar_oc_a_sap.return_value = {
                "success": True, "doc_entry": 555, "doc_num": 24711,
            }
            resultado = _reconciliar_oc("oc-1")
        assert resultado is True

    def test_error_real_no_transitorio_notifica_a_tecnicos(self):
        """Error no transitorio (dato de negocio, ej. artículo no habilitado): nadie
        está mirando la pantalla en este flujo automático, así que se notifica."""
        with patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository") as mock_repo_cls, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OCSAPService") as mock_service_cls, \
                patch(
                    "src.tasks.celery_reconciliar_ordenes_compra._notificar_error_real_a_tecnicos"
                ) as mock_notificar:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            mock_repo_cls.return_value.get_existing_cabecera.return_value = {"proveedor": "P1"}
            mock_service_cls.return_value.enviar_oc_a_sap.return_value = {
                "success": False, "error": "Artículo no habilitado para compra en esta bodega",
            }
            resultado = _reconciliar_oc("oc-1")
        assert resultado is True
        mock_notificar.assert_called_once_with("oc-1", {"proveedor": "P1"}, "Artículo no habilitado para compra en esta bodega")

    def test_error_transitorio_no_notifica_a_tecnicos(self):
        """Error transitorio (ej. caída de conexión): se deja para el próximo ciclo
        de un reintento normal, sin alarmar a técnicos por algo que se resuelve solo."""
        with patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository") as mock_repo_cls, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OCSAPService") as mock_service_cls, \
                patch(
                    "src.tasks.celery_reconciliar_ordenes_compra._notificar_error_real_a_tecnicos"
                ) as mock_notificar:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            mock_repo_cls.return_value.get_existing_cabecera.return_value = {"proveedor": "P1"}
            mock_service_cls.return_value.enviar_oc_a_sap.return_value = {
                "success": False, "error": "Error de conexión con SAP",
            }
            resultado = _reconciliar_oc("oc-1")
        assert resultado is True
        mock_notificar.assert_not_called()


class TestReconciliarOrdenesCompraPendientes:
    def test_sin_odc_encoladas_no_hace_nada(self):
        with patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository") as mock_repo_cls:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            mock_repo_cls.return_value.get_oc_ids_encoladas.return_value = []
            resultado = reconciliar_ordenes_compra_pendientes()
        assert resultado == {"procesadas": 0, "estancadas": 0}

    def test_procesa_cada_odc_encolada_y_sigue_ante_errores(self):
        with patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository") as mock_repo_cls, \
                patch(
                    "src.tasks.celery_reconciliar_ordenes_compra._reconciliar_oc",
                    side_effect=[True, Exception("boom"), True],
                ) as mock_reconciliar:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            mock_repo_cls.return_value.get_oc_ids_encoladas.return_value = ["oc-1", "oc-2", "oc-3"]
            resultado = reconciliar_ordenes_compra_pendientes()

        assert mock_reconciliar.call_count == 3
        assert resultado == {"procesadas": 2, "candidatas": 3, "estancadas": 0}


class TestReconciliarOcPublicaSse:
    def test_exito_publica_sse_confirmada(self):
        with patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository") as mock_repo_cls, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OCSAPService") as mock_service_cls, \
                patch("src.tasks.celery_reconciliar_ordenes_compra._publicar_sse_reconciliacion") as mock_sse:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            mock_repo_cls.return_value.get_existing_cabecera.return_value = {"referencia_despacho": "900125353"}
            mock_service_cls.return_value.enviar_oc_a_sap.return_value = {
                "success": True, "doc_num": "24711",
            }
            _reconciliar_oc("oc-1")

        mock_sse.assert_called_once()
        args = mock_sse.call_args.args
        assert args[-1] == "reconciliacion_oc_confirmada"

    def test_error_real_publica_sse_error(self):
        with patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository") as mock_repo_cls, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OCSAPService") as mock_service_cls, \
                patch("src.tasks.celery_reconciliar_ordenes_compra._notificar_error_real_a_tecnicos"), \
                patch("src.tasks.celery_reconciliar_ordenes_compra._publicar_sse_reconciliacion") as mock_sse:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            mock_repo_cls.return_value.get_existing_cabecera.return_value = {"referencia_despacho": "900125353"}
            mock_service_cls.return_value.enviar_oc_a_sap.return_value = {
                "success": False, "error": "Artículo no habilitado en la bodega",
            }
            _reconciliar_oc("oc-1")

        mock_sse.assert_called_once()
        args = mock_sse.call_args.args
        assert args[-1] == "reconciliacion_oc_error"

    def test_encolada_sigue_encolada_no_publica_sse(self):
        """Regresión: el caso rutinario 'sigue esperando' no debe generar ruido."""
        with patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository") as mock_repo_cls, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OCSAPService") as mock_service_cls, \
                patch("src.tasks.celery_reconciliar_ordenes_compra._publicar_sse_reconciliacion") as mock_sse:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            mock_repo_cls.return_value.get_existing_cabecera.return_value = {}
            mock_service_cls.return_value.enviar_oc_a_sap.return_value = {"success": False, "queued": True}
            _reconciliar_oc("oc-1")

        mock_sse.assert_not_called()


class TestReconciliarEnvioEstancado:
    def test_flip_exitoso_notifica_por_correo_y_sse(self):
        with patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository") as mock_repo_cls, \
                patch("src.tasks.celery_reconciliar_ordenes_compra._notificar_error_real_a_tecnicos") as mock_email, \
                patch("src.tasks.celery_reconciliar_ordenes_compra._publicar_sse_reconciliacion") as mock_sse:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            mock_repo = mock_repo_cls.return_value
            mock_repo.update_estado.return_value = True
            mock_repo.get_existing_cabecera.return_value = {"referencia_despacho": "900125353"}

            _reconciliar_envio_estancado("oc-1")

        args, kwargs = mock_repo.update_estado.call_args
        assert args[0] == "oc-1"
        assert args[1] == "ERROR"
        assert kwargs["estado_actual_esperado"] == "ENVIANDO"
        mock_email.assert_called_once()
        mock_sse.assert_called_once()
        assert mock_sse.call_args.args[-1] == "oc_envio_estancado"

    def test_carrera_autosanada_no_notifica_nada(self):
        """El envío en realidad terminó (ENVIADA/ERROR) justo antes del UPDATE
        guardado -- rowcount=0, update_estado devuelve False, no se notifica nada."""
        with patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository") as mock_repo_cls, \
                patch("src.tasks.celery_reconciliar_ordenes_compra._notificar_error_real_a_tecnicos") as mock_email, \
                patch("src.tasks.celery_reconciliar_ordenes_compra._publicar_sse_reconciliacion") as mock_sse:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            mock_repo_cls.return_value.update_estado.return_value = False

            _reconciliar_envio_estancado("oc-1")

        mock_email.assert_not_called()
        mock_sse.assert_not_called()
