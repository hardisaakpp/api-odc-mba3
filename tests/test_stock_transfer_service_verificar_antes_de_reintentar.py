"""
Fase 3 del arreglo de raíz: antes de cada reintento individual de una ITR
(tras un timeout que retry_operation sigue considerando transitorio), verifica
contra SAP real si esa tienda específica ya quedó creada -- cierra el vector
de hasta RETRY_MAX_ATTEMPTS-1 POST ciegos que podían duplicar un ITR que SAP
ya había creado, solo que la confirmación se perdió por timeout.
"""

from unittest.mock import MagicMock, patch

from src.database.services.stock_transfer_service import StockTransferService


def _service():
    service = StockTransferService.__new__(StockTransferService)
    service.sap_client = MagicMock()
    return service


class TestVerificarItrIndividualEnSap:
    def test_none_sin_comentario(self):
        service = _service()
        assert service._verificar_itr_individual_en_sap(None, "RL-CD", "TRL-QSN") is None
        service.sap_client.get_inventory_transfer_requests_by_comment.assert_not_called()

    def test_none_si_no_encuentra_la_tienda(self):
        service = _service()
        service.sap_client.get_inventory_transfer_requests_by_comment.return_value = [
            {"comments": "Transferencia desde OC 24715 - Pedido X", "from_warehouse": "RL-CD",
             "to_warehouse": "TRL-OTRA", "doc_num": 1, "doc_entry": 2},
        ]
        resultado = service._verificar_itr_individual_en_sap(
            "Transferencia desde OC 24715 - Pedido X", "RL-CD", "TRL-QSN"
        )
        assert resultado is None

    def test_encuentra_la_tienda_y_la_adopta(self):
        service = _service()
        service.sap_client.get_inventory_transfer_requests_by_comment.return_value = [
            {"comments": "Transferencia desde OC 24715 - Pedido X", "from_warehouse": "RL-CD",
             "to_warehouse": "TRL-PSM", "doc_num": 70215585, "doc_entry": 400970},
        ]
        resultado = service._verificar_itr_individual_en_sap(
            "Transferencia desde OC 24715 - Pedido X", "RL-CD", "TRL-PSM"
        )
        assert resultado == {"success": True, "doc_entry": 400970, "doc_num": 70215585}


class TestEnviarItrConReintentoCheckBeforeRetry:
    def test_sin_comentario_no_verifica_contra_sap_entre_intentos(self):
        """Sin comentario_exacto (comportamiento previo a la Fase 3), un timeout
        agotado NO debe disparar ninguna búsqueda en SAP entre intentos."""
        service = _service()
        service.sap_client.create_stock_transfer.return_value = {
            "success": False, "status_code": 503, "error": "timeout"
        }

        with patch.object(service, "RETRY_MAX_ATTEMPTS", 2), \
             patch.object(service, "RETRY_BASE_DELAY_SECONDS", 0.0), \
             patch.object(service, "RETRY_MAX_JITTER_SECONDS", 0.0):
            resultado = service._enviar_itr_con_reintento(
                payload={"ToWarehouse": "TRL-QSN"}, bodega_origen="RL-CD", tienda_codigo="TRL-QSN",
            )

        assert resultado["success"] is False
        assert service.sap_client.create_stock_transfer.call_count == 2
        service.sap_client.get_inventory_transfer_requests_by_comment.assert_not_called()

    def test_con_comentario_adopta_si_sap_ya_lo_tenia(self):
        """El caso real del incidente a nivel de una sola tienda: el primer POST
        expira por timeout, pero SAP sí había creado el ITR -- el reintento debe
        adoptarlo (vía búsqueda por comentario) en vez de mandar un 2do POST que
        lo duplicaría."""
        service = _service()
        service.sap_client.create_stock_transfer.return_value = {
            "success": False, "status_code": 503, "error": "timeout"
        }
        service.sap_client.get_inventory_transfer_requests_by_comment.return_value = [
            {"comments": "Transferencia desde OC 24715 - Pedido X", "from_warehouse": "RL-CD",
             "to_warehouse": "TRL-PSM", "doc_num": 70215585, "doc_entry": 400970},
        ]

        with patch.object(service, "RETRY_MAX_ATTEMPTS", 3), \
             patch.object(service, "RETRY_BASE_DELAY_SECONDS", 0.0), \
             patch.object(service, "RETRY_MAX_JITTER_SECONDS", 0.0):
            resultado = service._enviar_itr_con_reintento(
                payload={"ToWarehouse": "TRL-PSM"}, bodega_origen="RL-CD", tienda_codigo="TRL-PSM",
                comentario_exacto="Transferencia desde OC 24715 - Pedido X",
            )

        assert resultado["success"] is True
        assert resultado["response"] == {"success": True, "doc_entry": 400970, "doc_num": 70215585}
        # Un solo POST real -- el 2do "intento" se resolvió por verificación, no por reenvío.
        assert service.sap_client.create_stock_transfer.call_count == 1

    def test_con_comentario_pero_sap_no_lo_tenia_reintenta_normal(self):
        """Si la verificación no encuentra nada, el reintento normal (con su
        propio POST) sigue su curso -- comportamiento idéntico al de antes de
        la Fase 3 salvo por la consulta de verificación de por medio."""
        service = _service()
        service.sap_client.create_stock_transfer.side_effect = [
            {"success": False, "status_code": 503, "error": "timeout"},
            {"success": True, "doc_entry": 1, "doc_num": 2},
        ]
        service.sap_client.get_inventory_transfer_requests_by_comment.return_value = []

        with patch.object(service, "RETRY_MAX_ATTEMPTS", 3), \
             patch.object(service, "RETRY_BASE_DELAY_SECONDS", 0.0), \
             patch.object(service, "RETRY_MAX_JITTER_SECONDS", 0.0):
            resultado = service._enviar_itr_con_reintento(
                payload={"ToWarehouse": "TRL-QSN"}, bodega_origen="RL-CD", tienda_codigo="TRL-QSN",
                comentario_exacto="Transferencia desde OC 24715 - Pedido X",
            )

        assert resultado["success"] is True
        assert service.sap_client.create_stock_transfer.call_count == 2
        service.sap_client.get_inventory_transfer_requests_by_comment.assert_called_once()
