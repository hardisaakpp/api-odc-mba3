"""
Fase 2 (tiempo real) del arreglo de raíz: crear_solicitudes_transferencia_desde_pedido
debe registrar el alias oc_id<->process_id (ProcesoEstadoService.crear_alias_oc) al
inicio, ANTES de tocar la base de datos -- así, aunque el resto del envío falle, una
reconciliación posterior (botón manual "Reintentar ST" o Celery Beat) puede seguir
localizando el proceso SAP original vía obtener_process_id_por_oc y corregir su
snapshot congelado.
"""

from unittest.mock import patch

from src.database.services.stock_transfer_service import StockTransferService


def _service():
    return StockTransferService.__new__(StockTransferService)


class TestRegistroAliasOc:
    def test_registra_alias_cuando_hay_process_id_y_oc_id(self):
        service = _service()
        with patch(
            "src.database.services.proceso_estado_service.ProcesoEstadoService"
        ) as mock_peservice_cls, patch(
            "src.database.services.stock_transfer_service.get_db_connection_context",
            side_effect=RuntimeError("db no disponible en este test"),
        ):
            resultado = service.crear_solicitudes_transferencia_desde_pedido(
                pedido_id="pedido-1",
                oc_id="oc-1",
                process_id="proceso-sap-abc123",
            )

        mock_peservice_cls.return_value.crear_alias_oc.assert_called_once_with(
            "proceso-sap-abc123", "oc-1"
        )
        # El fallo de BD posterior se captura y se reporta en el resultado
        # (no debe propagar); el alias ya se registró antes de llegar ahí.
        assert "db no disponible" in resultado["error"]

    def test_no_registra_alias_sin_process_id(self):
        service = _service()
        with patch(
            "src.database.services.proceso_estado_service.ProcesoEstadoService"
        ) as mock_peservice_cls, patch(
            "src.database.services.stock_transfer_service.get_db_connection_context",
            side_effect=RuntimeError("db no disponible en este test"),
        ):
            service.crear_solicitudes_transferencia_desde_pedido(
                pedido_id="pedido-1",
                oc_id="oc-1",
            )

        mock_peservice_cls.return_value.crear_alias_oc.assert_not_called()

    def test_no_registra_alias_sin_oc_id(self):
        service = _service()
        with patch(
            "src.database.services.proceso_estado_service.ProcesoEstadoService"
        ) as mock_peservice_cls, patch(
            "src.database.services.stock_transfer_service.get_db_connection_context",
            side_effect=RuntimeError("db no disponible en este test"),
        ):
            service.crear_solicitudes_transferencia_desde_pedido(
                pedido_id="pedido-1",
                process_id="proceso-sap-abc123",
            )

        mock_peservice_cls.return_value.crear_alias_oc.assert_not_called()

    def test_fallo_al_registrar_alias_no_rompe_el_envio(self):
        """Best-effort: si crear_alias_oc falla (ej. Redis caído), el envío de
        ST debe seguir su curso normal, no abortar."""
        service = _service()
        with patch(
            "src.database.services.proceso_estado_service.ProcesoEstadoService"
        ) as mock_peservice_cls, patch(
            "src.database.services.stock_transfer_service.get_db_connection_context",
            side_effect=RuntimeError("db no disponible en este test"),
        ):
            mock_peservice_cls.return_value.crear_alias_oc.side_effect = Exception("redis caído")
            resultado = service.crear_solicitudes_transferencia_desde_pedido(
                pedido_id="pedido-1",
                oc_id="oc-1",
                process_id="proceso-sap-abc123",
            )

        # No debió propagar el error de Redis -- el error reportado es el de BD
        # (que sí es el fallo real de este intento), no el de crear_alias_oc.
        assert "db no disponible" in resultado["error"]
