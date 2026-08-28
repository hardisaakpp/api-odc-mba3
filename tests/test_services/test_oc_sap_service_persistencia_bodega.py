"""
Persistencia de ITR entre bodegas en OCSAPService._enviar_itrs_por_bodega. Antes,
el resultado de estas ITR (RL-CD/RG-CD/OUT-CD usadas como destino en la plantilla
Excel, no una tienda real) solo se devolvía en la respuesta HTTP -- nunca quedaba
en base de datos, así que ni la reconciliación automática ni un reintento manual
podían detectar una que falló. Usa tablas propias (solicitud_transferencia_bodega)
para no interferir con la lógica de reintento de tiendas (ver
scripts/migrations/create_solicitud_transferencia_bodega.sql).
"""

from unittest.mock import MagicMock, patch

from src.database.services.oc_sap_service import OCSAPService

_REPO_PATH = (
    "src.database.repositories.solicitud_transferencia_bodega_repository."
    "SolicitudTransferenciaBodegaRepository"
)
_MAPPER_PATH = "src.database.mappers.sap_stock_transfer_mapper.SAPStockTransferMapper"


def _service():
    return OCSAPService.__new__(OCSAPService)


def _payloads(*to_warehouses):
    return [{"ToWarehouse": wh, "FromWarehouse": "RL-CD"} for wh in to_warehouses]


class TestSinConnNoIntentaPersistir:
    def test_comportamiento_existente_no_cambia(self):
        """Llamadas existentes (sin los nuevos kwargs) no deben romper nada ni
        intentar tocar la BD -- compatibilidad con cualquier caller que aún no
        pase conn/oc_id/pedido_id."""
        service = _service()
        result = {}
        with patch(f"{_MAPPER_PATH}.to_sap_inventory_transfer_requests_by_bodega", return_value=_payloads("OUT-CD")), \
             patch.object(
                 service, "_enviar_itr_con_reintento",
                 return_value={"success": True, "response": {"success": True, "doc_entry": 1, "doc_num": 2}, "attempts": 1},
             ), \
             patch(_REPO_PATH) as MockRepo:
            service._enviar_itrs_por_bodega(
                oc_detalles=[{"codigo_bodega": "OUT-CD"}],
                from_wh="RL-CD",
                doc_num=123,
                doc_date_itr="2026-08-28",
                serie_itr=None,
                result=result,
            )

        MockRepo.assert_not_called()
        assert result["inventory_transfer_requests"]["created"] == 1


class TestConConnPersisteEncabezadoYDetalle:
    def test_crea_encabezado_con_oc_id_pedido_id_y_bodega_origen(self):
        service = _service()
        result = {}
        conn = MagicMock()
        with patch(f"{_MAPPER_PATH}.to_sap_inventory_transfer_requests_by_bodega", return_value=_payloads("OUT-CD")), \
             patch.object(
                 service, "_enviar_itr_con_reintento",
                 return_value={"success": True, "response": {"success": True, "doc_entry": 1, "doc_num": 2}, "attempts": 1},
             ), \
             patch(_REPO_PATH) as MockRepo:
            MockRepo.return_value.insert.return_value = "solicitud-bodega-1"
            service._enviar_itrs_por_bodega(
                oc_detalles=[{"codigo_bodega": "OUT-CD"}],
                from_wh="RL-CD",
                doc_num=456,
                doc_date_itr="2026-08-28",
                serie_itr=None,
                result=result,
                conn=conn,
                oc_id="oc-1",
                pedido_id="pedido-1",
            )

        for call in MockRepo.call_args_list:
            assert call.args == (conn,)
        MockRepo.return_value.insert.assert_called_once_with(
            oc_id="oc-1", pedido_id="pedido-1", oc_doc_num=456, bodega_origen="RL-CD"
        )

    def test_persiste_detalle_exitoso_de_inmediato(self):
        service = _service()
        result = {}
        conn = MagicMock()
        with patch(f"{_MAPPER_PATH}.to_sap_inventory_transfer_requests_by_bodega", return_value=_payloads("OUT-CD")), \
             patch.object(
                 service, "_enviar_itr_con_reintento",
                 return_value={"success": True, "response": {"success": True, "doc_entry": 400970, "doc_num": 70215585}, "attempts": 1},
             ), \
             patch(_REPO_PATH) as MockRepo:
            MockRepo.return_value.insert.return_value = "solicitud-bodega-1"
            service._enviar_itrs_por_bodega(
                oc_detalles=[{"codigo_bodega": "OUT-CD"}],
                from_wh="RL-CD",
                doc_num=456,
                doc_date_itr="2026-08-28",
                serie_itr=None,
                result=result,
                conn=conn,
                oc_id="oc-1",
                pedido_id="pedido-1",
            )

        MockRepo.return_value.insert_detalle_individual.assert_called_once()
        args = MockRepo.return_value.insert_detalle_individual.call_args.args
        assert args[0] == "solicitud-bodega-1"
        assert args[1]["bodega_codigo"] == "OUT-CD"
        assert args[1]["success"] is True
        assert args[1]["doc_entry"] == 400970

    def test_persiste_detalle_de_error(self):
        service = _service()
        result = {}
        conn = MagicMock()
        with patch(f"{_MAPPER_PATH}.to_sap_inventory_transfer_requests_by_bodega", return_value=_payloads("OUT-CD")), \
             patch.object(
                 service, "_enviar_itr_con_reintento",
                 return_value={"success": False, "response": None, "error": "Sin respuesta de SAP", "attempts": 3},
             ), \
             patch(_REPO_PATH) as MockRepo:
            MockRepo.return_value.insert.return_value = "solicitud-bodega-1"
            service._enviar_itrs_por_bodega(
                oc_detalles=[{"codigo_bodega": "OUT-CD"}],
                from_wh="RL-CD",
                doc_num=456,
                doc_date_itr="2026-08-28",
                serie_itr=None,
                result=result,
                conn=conn,
                oc_id="oc-1",
                pedido_id="pedido-1",
            )

        args = MockRepo.return_value.insert_detalle_individual.call_args.args
        assert args[1]["success"] is False
        assert args[1]["error"] == "Sin respuesta de SAP"

    def test_cierra_resumen_con_contadores_finales(self):
        service = _service()
        result = {}
        conn = MagicMock()
        with patch(f"{_MAPPER_PATH}.to_sap_inventory_transfer_requests_by_bodega", return_value=_payloads("OUT-CD", "RG-CD")), \
             patch.object(
                 service, "_enviar_itr_con_reintento",
                 side_effect=[
                     {"success": True, "response": {"success": True, "doc_entry": 1, "doc_num": 2}, "attempts": 1},
                     {"success": False, "response": None, "error": "timeout", "attempts": 3},
                 ],
             ), \
             patch(_REPO_PATH) as MockRepo:
            MockRepo.return_value.insert.return_value = "solicitud-bodega-1"
            service._enviar_itrs_por_bodega(
                oc_detalles=[{"codigo_bodega": "OUT-CD"}, {"codigo_bodega": "RG-CD"}],
                from_wh="RL-CD",
                doc_num=456,
                doc_date_itr="2026-08-28",
                serie_itr=None,
                result=result,
                conn=conn,
                oc_id="oc-1",
                pedido_id="pedido-1",
            )

        MockRepo.return_value.update_resumen.assert_called_once_with(
            "solicitud-bodega-1", {"created": 1, "errors": 1, "total": 2}
        )


class TestFallosDePersistenciaNoBloqueanElEnvioASap:
    def test_fallo_al_crear_encabezado_no_impide_enviar_a_sap(self):
        service = _service()
        result = {}
        conn = MagicMock()
        with patch(f"{_MAPPER_PATH}.to_sap_inventory_transfer_requests_by_bodega", return_value=_payloads("OUT-CD")), \
             patch.object(
                 service, "_enviar_itr_con_reintento",
                 return_value={"success": True, "response": {"success": True, "doc_entry": 1, "doc_num": 2}, "attempts": 1},
             ) as mock_enviar, \
             patch(_REPO_PATH) as MockRepo:
            MockRepo.return_value.insert.side_effect = Exception("timeout de BD")
            service._enviar_itrs_por_bodega(
                oc_detalles=[{"codigo_bodega": "OUT-CD"}],
                from_wh="RL-CD",
                doc_num=456,
                doc_date_itr="2026-08-28",
                serie_itr=None,
                result=result,
                conn=conn,
                oc_id="oc-1",
                pedido_id="pedido-1",
            )

        mock_enviar.assert_called_once()
        assert result["inventory_transfer_requests"]["created"] == 1
        MockRepo.return_value.insert_detalle_individual.assert_not_called()

    def test_fallo_al_persistir_detalle_no_propaga(self):
        service = _service()
        result = {}
        conn = MagicMock()
        with patch(f"{_MAPPER_PATH}.to_sap_inventory_transfer_requests_by_bodega", return_value=_payloads("OUT-CD")), \
             patch.object(
                 service, "_enviar_itr_con_reintento",
                 return_value={"success": True, "response": {"success": True, "doc_entry": 1, "doc_num": 2}, "attempts": 1},
             ), \
             patch(_REPO_PATH) as MockRepo:
            MockRepo.return_value.insert.return_value = "solicitud-bodega-1"
            MockRepo.return_value.insert_detalle_individual.side_effect = Exception("timeout de BD")
            service._enviar_itrs_por_bodega(
                oc_detalles=[{"codigo_bodega": "OUT-CD"}],
                from_wh="RL-CD",
                doc_num=456,
                doc_date_itr="2026-08-28",
                serie_itr=None,
                result=result,
                conn=conn,
                oc_id="oc-1",
                pedido_id="pedido-1",
            )

        assert result["inventory_transfer_requests"]["created"] == 1


class TestProcesarOcExitosaPropagaConnOcIdPedidoId:
    def test_pasa_conn_oc_id_y_pedido_id_a_enviar_itrs_por_bodega(self):
        """_procesar_oc_exitosa debe pasar oc_repo.conn, oc_id y pedido_id (leído
        ANTES de la llamada, no después) para que _enviar_itrs_por_bodega pueda
        persistir el resultado."""
        service = _service()
        oc_repo = MagicMock()
        oc_repo.conn = "conn-real"
        oc_cabecera = {"codigo_bodega": "RL-CD", "pedido_id": "pedido-1"}
        sap_response = {"success": True, "doc_entry": 111, "doc_num": 222, "doc_date": "2026-08-28T00:00:00"}
        result = {}

        with patch.object(service, "_obtener_serie_itr", return_value=None), \
             patch.object(service, "_enviar_itrs_por_bodega") as mock_bodega, \
             patch.object(service, "_crear_solicitudes_transferencia_oc"), \
             patch.object(service, "_notificar_resultado_oc_st"), \
             patch.object(service, "_cerrar_pedido_desde_resultado_oc"):
            service._procesar_oc_exitosa(
                oc_id="oc-1",
                oc_cabecera=oc_cabecera,
                oc_detalles=[{"codigo_bodega": "OUT-CD"}],
                sap_response=sap_response,
                envio_oc_result={"attempts": 1},
                oc_repo=oc_repo,
                result=result,
            )

        mock_bodega.assert_called_once()
        kwargs = mock_bodega.call_args.kwargs
        assert kwargs["conn"] == "conn-real"
        assert kwargs["oc_id"] == "oc-1"
        assert kwargs["pedido_id"] == "pedido-1"
