"""
Tests del arreglo de raíz para el incidente 2026-08-27 (pedido "pedido prueba 130"):
_enviar_itrs_a_sap clasificaba cada tienda en éxito/error binario, así que un
timeout agotando reintentos (SAP pudo haber creado el ITR igual, solo tarde)
se reportaba exactamente igual que un rechazo real de SAP -- de ahí el falso
"0 de 23 creadas exitosamente" pese a que SAP había creado 15.

Cubre la clasificación en 3 estados ('confirmada' / 'error_confirmado' /
'pendiente_confirmacion') y el pase de reconciliación de solo lectura al
cierre del batch (_reconciliar_pendientes_confirmacion), que reutiliza los
mismos mecanismos de verificación contra SAP que ya usaba el botón manual
"Reintentar ST" (_extraer_adopcion_de_job / _buscar_itrs_existentes_en_sap).
"""

from unittest.mock import MagicMock, patch

from src.database.services.stock_transfer_service import StockTransferService


def _service():
    return StockTransferService.__new__(StockTransferService)


def _result_inicial():
    return {
        "success": False,
        "total_tiendas": 1,
        "transferencias_creadas": 0,
        "transferencias_errores": 0,
        "transferencias_encoladas": 0,
        "transferencias_pendientes_confirmacion": 0,
        "resultados": [],
    }


def _enviar(service, result, comentario_exacto="Transferencia desde OC 24715 - Pedido pedido prueba 130"):
    service._enviar_itrs_a_sap(
        stock_transfers_json=[{"ToWarehouse": "TRL-PSM"}],
        distribucion_por_tienda={"tid-1": []},
        bodega_origen="RL-CD",
        mapeo_nombre_tienda={"TRL-PSM": "ROLAND PORTAL SHOPPING MANTA"},
        result=result,
        comentario_exacto=comentario_exacto,
    )


class TestTimeoutAgotandoReintentosQuedaPendienteNoError:
    def test_stopped_early_false_sin_reconciliacion_posible_queda_pendiente(self):
        """Timeout agotando reintentos (stopped_early=False), sin job_id y sin
        match en la búsqueda de SAP: no se puede confirmar -- debe quedar
        'pendiente_confirmacion', NUNCA contarse como error confirmado."""
        service = _service()
        service.sap_client = MagicMock()
        service.sap_client.get_inventory_transfer_requests_by_comment.return_value = []
        result = _result_inicial()
        with patch.object(
            service, "_enviar_itr_con_reintento",
            return_value={
                "success": False,
                "response": None,
                "attempts": 3,
                "error": "Error de conexión: timeout",
                "stopped_early": False,
            },
        ):
            _enviar(service, result)

        assert result["transferencias_errores"] == 0
        assert result["transferencias_pendientes_confirmacion"] == 1
        assert result["transferencias_creadas"] == 0
        resultado_tienda = result["resultados"][0]
        assert resultado_tienda["estado"] == "pendiente_confirmacion"
        assert resultado_tienda["success"] is False

    def test_stopped_early_false_pero_sap_ya_lo_habia_creado_se_confirma_sin_duplicar(self):
        """El caso exacto del incidente: SAP sí creó el ITR (se ve en la búsqueda
        por comentario), pero la confirmación no llegó a tiempo al backend.
        La reconciliación al cierre debe subir el estado a 'confirmada' con el
        DocNum real, SIN volver a llamar a _enviar_itr_con_reintento (cero POST
        nuevo -- eso sería un duplicado)."""
        service = _service()
        service.sap_client = MagicMock()
        service.sap_client.get_inventory_transfer_requests_by_comment.return_value = [
            {
                "comments": "Transferencia desde OC 24715 - Pedido pedido prueba 130",
                "from_warehouse": "RL-CD",
                "to_warehouse": "TRL-PSM",
                "doc_num": 70215585,
                "doc_entry": 400970,
            }
        ]
        result = _result_inicial()
        with patch.object(
            service, "_enviar_itr_con_reintento",
            return_value={
                "success": False,
                "response": None,
                "attempts": 3,
                "error": "Error de conexión: timeout",
                "stopped_early": False,
            },
        ) as mock_enviar:
            _enviar(service, result)

        mock_enviar.assert_called_once()  # un solo intento de creación, no un reintento extra
        assert result["transferencias_errores"] == 0
        assert result["transferencias_pendientes_confirmacion"] == 0
        assert result["transferencias_creadas"] == 1
        resultado_tienda = result["resultados"][0]
        assert resultado_tienda["estado"] == "confirmada"
        assert resultado_tienda["success"] is True
        assert resultado_tienda["doc_num"] == 70215585
        assert resultado_tienda["doc_entry"] == 400970
        assert resultado_tienda["recuperada"] is True

    def test_stopped_early_true_sigue_siendo_error_confirmado(self):
        """SAP rechazó de forma definitiva (should_retry devolvió False): esto
        SÍ debe seguir contando como error real, no como pendiente."""
        service = _service()
        service.sap_client = MagicMock()
        result = _result_inicial()
        with patch.object(
            service, "_enviar_itr_con_reintento",
            return_value={
                "success": False,
                "response": {"success": False, "error": "Artículo no habilitado"},
                "attempts": 1,
                "error": "Artículo no habilitado",
                "stopped_early": True,
            },
        ):
            _enviar(service, result)

        assert result["transferencias_errores"] == 1
        assert result["transferencias_pendientes_confirmacion"] == 0
        assert result["transferencias_creadas"] == 0
        resultado_tienda = result["resultados"][0]
        assert resultado_tienda["estado"] == "error_confirmado"
        # No debe haber intentado buscar en SAP -- ya es un error confirmado.
        service.sap_client.get_inventory_transfer_requests_by_comment.assert_not_called()

    def test_job_encolado_completado_en_reconciliacion_se_confirma(self):
        """202 (job encolado) cuyo job SÍ terminó COMPLETADO al momento de
        cerrar el batch: se adopta por job_id, sin pasar por la búsqueda por
        comentario."""
        service = _service()
        service.sap_client = MagicMock()
        service.sap_client.get_job_status.return_value = {
            "status": "COMPLETADO",
            "result": {"docEntry": 400970, "docNum": 70215585},
        }
        result = _result_inicial()
        with patch.object(
            service, "_enviar_itr_con_reintento",
            return_value={
                "success": False,
                "response": {"success": False, "queued": True, "job_id": "job-abc", "error": "SAP saturado"},
                "attempts": 1,
                "error": "SAP saturado",
                "stopped_early": False,
            },
        ):
            _enviar(service, result)

        service.sap_client.get_inventory_transfer_requests_by_comment.assert_not_called()
        assert result["transferencias_pendientes_confirmacion"] == 0
        assert result["transferencias_creadas"] == 1
        resultado_tienda = result["resultados"][0]
        assert resultado_tienda["estado"] == "confirmada"
        assert resultado_tienda["doc_num"] == 70215585
