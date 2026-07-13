"""
Regresión: `_enviar_emails_exito_sap` truncaba `total_cantidad_ajustada` con
`int(...)` antes de mandarlo al correo de confirmación a MABEL Trading,
perdiendo la parte decimal (ej. 12.5 -> "12"). `main` nunca lo truncaba.
"""

from types import SimpleNamespace
from unittest.mock import patch

from src.endpoints.pedidos.redistribucion.endpoints_proceso import _enviar_emails_exito_sap


def test_total_cantidad_ajustada_no_se_trunca():
    resumen = SimpleNamespace(total_productos=3, total_cantidad_ajustada=12.5)

    with patch(
        "src.utils.email_notifier.send_mabel_redistribucion_confirmacion_notification"
    ) as mock_mabel, patch(
        "src.utils.email_notifier.send_oc_ready_for_dispatch_notification",
        return_value=True,
    ):
        _enviar_emails_exito_sap(
            pedido_id="p1",
            numero_pedido="N-1",
            user_id="user1",
            resultado_redistribucion={"version_confirmada": 2},
            resumen=resumen,
            oc_cabecera={},
            doc_num_po=100,
            doc_entry=200,
            solicitudes_para_response=[],
            numero_oc_sap_cabecera=100,
        )

    assert mock_mabel.call_args.kwargs["total_cantidad_ajustada"] == 12.5
