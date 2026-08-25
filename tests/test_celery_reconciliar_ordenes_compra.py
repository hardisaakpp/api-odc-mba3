"""
Tests de la tarea de reconciliación automática de ODC ENCOLADAS (HTTP 202 del
middleware al crear la Purchase Order, sin resolver).

Cubre el enrutamiento de resultados en _reconciliar_oc (lock ocupado / sigue
encolada / éxito / error real) y el recorrido de la tarea periódica sobre todas
las ODC candidatas.
"""

from unittest.mock import MagicMock, patch

from src.tasks.celery_reconciliar_ordenes_compra import (
    _reconciliar_oc,
    reconciliar_ordenes_compra_pendientes,
)


def _patch_lock(acquired: bool):
    return patch(
        "src.tasks.celery_reconciliar_ordenes_compra.redis_lock_envio_odc",
        **{"return_value.__enter__.return_value": acquired},
    )


def _patch_db_y_service(resultado_enviar_oc_a_sap):
    mock_ctx = patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context")
    mock_repo_cls = patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository")
    mock_service_cls = patch("src.tasks.celery_reconciliar_ordenes_compra.OCSAPService")
    return mock_ctx, mock_repo_cls, mock_service_cls, resultado_enviar_oc_a_sap


class TestReconciliarOc:
    def test_omite_si_lock_ocupado(self):
        with _patch_lock(False):
            resultado = _reconciliar_oc("oc-1")
        assert resultado is False

    def test_sigue_encolada_no_es_error(self):
        with _patch_lock(True), \
                patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OrdenCompraRepository"), \
                patch("src.tasks.celery_reconciliar_ordenes_compra.OCSAPService") as mock_service_cls:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            mock_service_cls.return_value.enviar_oc_a_sap.return_value = {
                "success": False, "queued": True, "job_id": "job-1",
            }
            resultado = _reconciliar_oc("oc-1")
        assert resultado is True

    def test_job_completado_se_procesa_como_exito(self):
        with _patch_lock(True), \
                patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
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
        with _patch_lock(True), \
                patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
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
        with _patch_lock(True), \
                patch("src.tasks.celery_reconciliar_ordenes_compra.get_db_connection_context") as mock_ctx, \
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
        assert resultado == {"procesadas": 0}

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
        assert resultado == {"procesadas": 2, "candidatas": 3}
