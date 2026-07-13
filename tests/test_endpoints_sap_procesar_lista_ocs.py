"""
Regresión: al extraer _procesar_oc_individual/_procesar_lista_ocs del endpoint
masivo de envío de OCs (endpoints/sap.py), el proveedor resuelto para el log
se perdía cuando la excepción escapaba después de haberlo resuelto -- el
except hardcodeaba "proveedor": "UNKNOWN" siempre, en vez del proveedor real
ya conocido (como hacía `main` con `proveedor if 'proveedor' in locals()
else "UNKNOWN"`).
"""

from unittest.mock import MagicMock

from src.endpoints.sap import _procesar_lista_ocs


def test_proveedor_real_se_preserva_si_falla_despues_de_resolverlo():
    oc_repo = MagicMock()
    oc_repo.get_existing_cabecera.return_value = {
        "proveedor": "PROVEEDOR REAL SA",
        "referencia_despacho": "REF-1",
    }
    log_repo = MagicMock()
    oc_sap_service = MagicMock()
    oc_sap_service.enviar_oc_a_sap.side_effect = RuntimeError("fallo inesperado enviando a SAP")

    detalles, enviadas, errores = _procesar_lista_ocs(
        oc_repo, log_repo, oc_sap_service, "proceso-1", "user1", "TEST", ["oc-1"]
    )

    assert errores == 1
    assert enviadas == 0
    assert detalles[0]["proveedor"] == "PROVEEDOR REAL SA"

    log_entry = log_repo.guardar_log.call_args.args[0]
    assert log_entry.proveedor == "PROVEEDOR REAL SA"


def test_proveedor_desconocido_si_falla_antes_de_resolverlo():
    oc_repo = MagicMock()
    oc_repo.get_existing_cabecera.side_effect = RuntimeError("no se pudo leer cabecera")
    log_repo = MagicMock()
    oc_sap_service = MagicMock()

    detalles, enviadas, errores = _procesar_lista_ocs(
        oc_repo, log_repo, oc_sap_service, "proceso-1", "user1", "TEST", ["oc-1"]
    )

    assert errores == 1
    assert detalles[0]["proveedor"] == "UNKNOWN"
    oc_sap_service.enviar_oc_a_sap.assert_not_called()
