"""
Tests para PedidoCierreService.evaluar_cierre_pedido con ODC en estado "ENCOLADA".

Antes de agregar este estado, una ODC encolada (HTTP 202 del middleware, aún sin
resolver) no caía en ningún branch de evaluar_cierre_pedido (solo contaba
ENVIADA/PENDIENTE/ERROR) -- el pedido igual quedaba sin cerrar (odc_enviadas <
total_odc lo impedía), pero razon_no_cierre decía genéricamente "Solo N/total ODC
enviadas" sin explicar que en realidad se está esperando la confirmación de SAP.
"""

from unittest.mock import MagicMock

from src.database.services.pedido_cierre_service import PedidoCierreService


def _oc_repo_con(ocs):
    oc_repo = MagicMock()
    oc_repo.get_by_pedido_id.return_value = ocs
    return oc_repo


class TestEvaluarCierrePedidoConEncolada:
    def test_una_odc_encolada_impide_el_cierre_con_razon_especifica(self):
        ocs = [
            {"estado": "ENVIADA", "doc_entry": 111},
            {"estado": "ENCOLADA", "doc_entry": None},
        ]
        oc_repo = _oc_repo_con(ocs)

        resultado = PedidoCierreService().evaluar_cierre_pedido("pedido-1", oc_repo)

        assert resultado["puede_cerrar"] is False
        assert resultado["odc_encoladas"] == 1
        assert resultado["odc_con_error"] == 0
        assert resultado["odc_pendientes"] == 0
        assert "esperando confirmación de SAP" in resultado["razon_no_cierre"]

    def test_todas_enviadas_sin_encoladas_permite_cerrar(self):
        ocs = [
            {"estado": "ENVIADA", "doc_entry": 111},
            {"estado": "ENVIADA", "doc_entry": 222},
        ]
        oc_repo = _oc_repo_con(ocs)

        resultado = PedidoCierreService().evaluar_cierre_pedido("pedido-1", oc_repo)

        assert resultado["puede_cerrar"] is True
        assert resultado["odc_encoladas"] == 0
        assert resultado["razon_no_cierre"] is None
