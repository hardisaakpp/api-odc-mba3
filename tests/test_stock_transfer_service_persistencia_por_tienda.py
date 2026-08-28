"""
Persistencia por tienda en _enviar_itrs_a_sap: cada tienda se guarda en BD apenas
se resuelve (no todo el lote junto al final) -- si el proceso se interrumpe a
mitad del envío a SAP, lo ya confirmado hasta ese punto no se pierde. Cubre
también la re-persistencia de una tienda que se confirma tarde en la
reconciliación de cierre (_reconciliar_pendientes_confirmacion).
"""

import copy
from unittest.mock import MagicMock, patch

from src.database.services.stock_transfer_service import StockTransferService


def _service():
    return StockTransferService.__new__(StockTransferService)


def _result_inicial():
    return {
        "success": False,
        "total_tiendas": 0,
        "transferencias_creadas": 0,
        "transferencias_errores": 0,
        "transferencias_encoladas": 0,
        "transferencias_pendientes_confirmacion": 0,
        "resultados": [],
    }


class TestPersistenciaInmediataEnElLoopPrincipal:
    def test_sin_conn_ni_solicitud_id_no_intenta_persistir(self):
        """Comportamiento por defecto (llamadas existentes sin los nuevos kwargs):
        no debe romper nada ni intentar tocar la BD."""
        service = _service()
        service.sap_client = MagicMock()
        result = _result_inicial()
        with patch.object(
            service, "_enviar_itr_con_reintento",
            return_value={"success": True, "response": {"doc_entry": 1, "doc_num": 2}, "attempts": 1},
        ), patch(
            "src.database.services.stock_transfer_service.SolicitudTransferenciaRepository"
        ) as MockRepo:
            service._enviar_itrs_a_sap(
                stock_transfers_json=[{"ToWarehouse": "TRL-QSN"}],
                distribucion_por_tienda={"tid-1": []},
                bodega_origen="RL-CD",
                mapeo_nombre_tienda={},
                result=result,
            )
        MockRepo.assert_not_called()

    def test_tienda_exitosa_se_persiste_de_inmediato(self):
        service = _service()
        service.sap_client = MagicMock()
        result = _result_inicial()
        conn = MagicMock()
        with patch.object(
            service, "_enviar_itr_con_reintento",
            return_value={"success": True, "response": {"doc_entry": 1, "doc_num": 2}, "attempts": 1},
        ), patch(
            "src.database.services.stock_transfer_service.SolicitudTransferenciaRepository"
        ) as MockRepo:
            service._enviar_itrs_a_sap(
                stock_transfers_json=[{"ToWarehouse": "TRL-QSN"}],
                distribucion_por_tienda={"tid-1": []},
                bodega_origen="RL-CD",
                mapeo_nombre_tienda={},
                result=result,
                conn=conn,
                solicitud_transferencia_id="solicitud-1",
            )
        MockRepo.assert_called_once_with(conn)
        MockRepo.return_value.insert_detalle_individual.assert_called_once()
        args = MockRepo.return_value.insert_detalle_individual.call_args.args
        assert args[0] == "solicitud-1"
        assert args[1]["tienda_codigo"] == "TRL-QSN"
        assert args[1]["estado"] == "confirmada"

    def test_itr_ya_existente_en_sap_tambien_se_persiste_de_inmediato(self):
        service = _service()
        service.sap_client = MagicMock()
        result = _result_inicial()
        conn = MagicMock()
        with patch.object(
            service, "_resultado_desde_itr_existente",
            return_value={"tienda_codigo": "TRL-QSN", "success": True, "doc_entry": 1, "doc_num": 2},
        ), patch(
            "src.database.services.stock_transfer_service.SolicitudTransferenciaRepository"
        ) as MockRepo:
            service._enviar_itrs_a_sap(
                stock_transfers_json=[{"ToWarehouse": "TRL-QSN"}],
                distribucion_por_tienda={"tid-1": []},
                bodega_origen="RL-CD",
                mapeo_nombre_tienda={},
                result=result,
                itrs_existentes={"TRL-QSN": {"doc_entry": 1, "doc_num": 2}},
                conn=conn,
                solicitud_transferencia_id="solicitud-1",
            )
        MockRepo.return_value.insert_detalle_individual.assert_called_once()
        args = MockRepo.return_value.insert_detalle_individual.call_args.args
        assert args[1]["estado"] == "confirmada"

    def test_fallo_al_persistir_no_rompe_el_envio(self):
        """Best-effort: un error de BD al guardar el detalle no debe tumbar el envío."""
        service = _service()
        service.sap_client = MagicMock()
        result = _result_inicial()
        conn = MagicMock()
        with patch.object(
            service, "_enviar_itr_con_reintento",
            return_value={"success": True, "response": {"doc_entry": 1, "doc_num": 2}, "attempts": 1},
        ), patch(
            "src.database.services.stock_transfer_service.SolicitudTransferenciaRepository",
            side_effect=Exception("BD caída"),
        ):
            service._enviar_itrs_a_sap(
                stock_transfers_json=[{"ToWarehouse": "TRL-QSN"}],
                distribucion_por_tienda={"tid-1": []},
                bodega_origen="RL-CD",
                mapeo_nombre_tienda={},
                result=result,
                conn=conn,
                solicitud_transferencia_id="solicitud-1",
            )  # no debe lanzar
        assert result["transferencias_creadas"] == 1


class TestActualizacionTardiaEnReconciliacion:
    def test_tienda_confirmada_tarde_se_reactualiza_en_bd(self):
        """El caso del incidente: una tienda quedó 'Encolada' (pendiente_confirmacion)
        y se confirma al cierre del batch (con job_id) -- debe re-persistirse con el
        estado final, no quedar en BD como 'Encolada' cuando en memoria ya es 'confirmada'."""
        service = _service()
        service.sap_client = MagicMock()
        service.sap_client.get_job_status.return_value = {
            "status": "COMPLETADO",
            "result": {"docEntry": 400970, "docNum": 70215585},
        }
        result = _result_inicial()
        conn = MagicMock()
        # resultado_tienda se muta in-place más tarde (confirmación tardía); para
        # comprobar CON QUÉ estado se llamó insert_detalle_individual hay que
        # capturar una copia en el momento de la llamada, no la referencia mutable.
        llamadas_insert = []
        with patch.object(
            service, "_enviar_itr_con_reintento",
            return_value={
                "success": False,
                "response": {"success": False, "queued": True, "job_id": "job-abc", "error": "SAP saturado"},
                "attempts": 1,
                "error": "SAP saturado",
                "stopped_early": False,
            },
        ), patch(
            "src.database.services.stock_transfer_service.SolicitudTransferenciaRepository"
        ) as MockRepo:
            MockRepo.return_value.insert_detalle_individual.side_effect = (
                lambda sid, r: llamadas_insert.append(copy.deepcopy(r))
            )
            service._enviar_itrs_a_sap(
                stock_transfers_json=[{"ToWarehouse": "TRL-PSM"}],
                distribucion_por_tienda={"tid-1": []},
                bodega_origen="RL-CD",
                mapeo_nombre_tienda={"TRL-PSM": "Portal Shopping Manta"},
                result=result,
                comentario_exacto="Transferencia desde OC 24715",
                conn=conn,
                solicitud_transferencia_id="solicitud-1",
            )

        # 1ra persistencia: la tienda como 'Encolada' (pendiente_confirmacion) en el loop principal.
        assert len(llamadas_insert) == 1
        assert llamadas_insert[0]["estado"] == "pendiente_confirmacion"

        # 2da: la re-actualización a 'confirmada' tras la reconciliación de cierre.
        MockRepo.return_value.update_detalle_individual.assert_called_once()
        args = MockRepo.return_value.update_detalle_individual.call_args.args
        assert args[0] == "solicitud-1"
        assert args[1]["estado"] == "confirmada"
        assert args[1]["doc_num"] == 70215585
