"""
Tests para _paso3_enviar_odc_sap: con 1 sola ODC (caso normal) el envio sigue siendo
secuencial, sin cambios de comportamiento. Con 2 ODC (pedido mixto ROLAND+REGIONS,
Fase 2 de PYTD002) se envian en paralelo via ThreadPoolExecutor -- cada hilo abre su
propia conexion a BD y su propio OCSAPService (ver _enviar_una_odc_a_sap_en_thread),
ya que una conexion pyodbc y la sesion SAP no son seguras para compartir entre hilos.
"""

from unittest.mock import MagicMock, patch

from src.endpoints.pedidos.redistribucion.endpoints_proceso import _paso3_enviar_odc_sap
from src.models import ProcesoCompletoSAPDetalleODC


def _envio_ok(oc_id: str, codigo_bodega: str, doc_num: int):
    return {
        "success": True,
        "detalle": ProcesoCompletoSAPDetalleODC(
            oc_id=oc_id, success=True, numero_oc_sap=f"OC-{oc_id}", doc_num=doc_num,
        ),
        "oc_cabecera": {"oc_id": oc_id},
        "doc_num_po": 100,
        "doc_num": doc_num,
        "doc_entry": 1,
        "solicitudes_transferencia": {"transferencias_creadas": 1},
        "codigo_bodega": codigo_bodega,
        "error": None,
    }


def _odc(oc_id: str, codigo_bodega: str):
    return {
        "oc_id": oc_id,
        "resultado_odc": {"proveedor": "P", "codigo_bodega": codigo_bodega},
        "tiendas_bodega": [],
    }


def _envio_encolado(oc_id: str, codigo_bodega: str, job_id: str = "job-1"):
    """ODC que recibió HTTP 202 del middleware (SAP saturado): no es un error real,
    solo no se pudo confirmar todavía."""
    return {
        "success": False,
        "queued": True,
        "detalle": ProcesoCompletoSAPDetalleODC(
            oc_id=oc_id, success=False, queued=True,
            error=f"SAP saturado: la solicitud fue encolada por el middleware (jobId={job_id})",
        ),
        "oc_cabecera": {"oc_id": oc_id},
        "doc_num_po": None,
        "doc_num": None,
        "doc_entry": None,
        "solicitudes_transferencia": None,
        "codigo_bodega": codigo_bodega,
        "error": f"SAP saturado: la solicitud fue encolada por el middleware (jobId={job_id})",
    }


def _envio_error_real(oc_id: str, codigo_bodega: str):
    return {
        "success": False,
        "queued": False,
        "detalle": ProcesoCompletoSAPDetalleODC(
            oc_id=oc_id, success=False, error="SKU no existe en SAP",
        ),
        "oc_cabecera": {"oc_id": oc_id},
        "doc_num_po": None,
        "doc_num": None,
        "doc_entry": None,
        "solicitudes_transferencia": None,
        "codigo_bodega": codigo_bodega,
        "error": "SKU no existe en SAP",
    }


def _args_comunes():
    return dict(
        pedido_id="pedido-1",
        numero_pedido="pedido prueba 1",
        resultado_redistribucion=None,
        resumen=None,
        repo_pedido=MagicMock(),
        audit=MagicMock(),
        user_id="user-1",
    )


def test_un_odc_no_usa_thread_pool():
    oc_repo = MagicMock()
    oc_sap_service = MagicMock()
    odcs = [_odc("oc-A", "RL-CD")]

    with patch(
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_una_odc_a_sap",
        return_value=_envio_ok("oc-A", "RL-CD", 1001),
    ) as mock_secuencial, patch(
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_una_odc_a_sap_en_thread"
    ) as mock_paralelo, patch(
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_emails_exito_sap"
    ):
        resultado = _paso3_enviar_odc_sap(oc_repo, oc_sap_service, odcs, **_args_comunes())

    mock_secuencial.assert_called_once_with(oc_sap_service, oc_repo, odcs[0], process_id=None, lock=None)
    mock_paralelo.assert_not_called()
    assert resultado["response"].status == "success"


def test_dos_odcs_usa_thread_pool_y_preserva_orden():
    oc_repo = MagicMock()
    oc_sap_service = MagicMock()
    odcs = [_odc("oc-RL", "RL-CD"), _odc("oc-RG", "RG-CD")]

    def fake_en_thread(odc, process_id=None, lock=None):
        doc_num = 1001 if odc["oc_id"] == "oc-RL" else 1002
        return _envio_ok(odc["oc_id"], odc["resultado_odc"]["codigo_bodega"], doc_num)

    with patch(
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_una_odc_a_sap"
    ) as mock_secuencial, patch(
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_una_odc_a_sap_en_thread",
        side_effect=fake_en_thread,
    ) as mock_paralelo, patch(
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_emails_exito_sap"
    ), patch(
        # Sin este mock, el correo de despacho de la 2da ODC (envios[1:], ver
        # _notificar_exito_sap) no queda cubierto por el mock de
        # _enviar_emails_exito_sap (que solo cubre la "primera") y dispara un
        # envío SMTP real cada vez que corre este test.
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_email_despacho_odc"
    ) as mock_despacho_adicional:
        resultado = _paso3_enviar_odc_sap(oc_repo, oc_sap_service, odcs, **_args_comunes())

    mock_secuencial.assert_not_called()
    assert mock_paralelo.call_count == 2
    mock_despacho_adicional.assert_called_once()
    assert resultado["response"].status == "success"
    envios_sap = resultado["response"].envios_sap
    assert [d.numero_oc_sap for d in envios_sap] == ["OC-oc-RL", "OC-oc-RG"]


def test_dos_odcs_envia_email_despacho_para_cada_una():
    """Regresión: solo se enviaba el correo de ODC/ST lista para despacho de la primera
    ODC (_enviar_emails_exito_sap); la segunda ODC del pedido mixto no generaba correo."""
    oc_repo = MagicMock()
    oc_sap_service = MagicMock()
    odcs = [_odc("oc-RL", "RL-CD"), _odc("oc-RG", "RG-CD")]

    def fake_en_thread(odc, process_id=None, lock=None):
        doc_num = 1001 if odc["oc_id"] == "oc-RL" else 1002
        return _envio_ok(odc["oc_id"], odc["resultado_odc"]["codigo_bodega"], doc_num)

    with patch(
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_una_odc_a_sap_en_thread",
        side_effect=fake_en_thread,
    ), patch(
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_emails_exito_sap"
    ) as mock_email_primera, patch(
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_email_despacho_odc"
    ) as mock_email_adicional:
        _paso3_enviar_odc_sap(oc_repo, oc_sap_service, odcs, **_args_comunes())

    # La primera ODC va por el flujo de siempre (confirmación redistribución + despacho)
    mock_email_primera.assert_called_once()
    assert mock_email_primera.call_args.args[-1] == "OC-oc-RL"

    # La segunda ODC solo necesita el correo de despacho, con SU PROPIO doc_num/numero_oc_sap
    mock_email_adicional.assert_called_once()
    assert mock_email_adicional.call_args.args[0] == "pedido prueba 1"
    assert mock_email_adicional.call_args.args[-1] == "OC-oc-RG"


def test_odc_exitosa_recibe_correo_aunque_la_hermana_quede_encolada():
    """Bug real que corrige: antes, cualquier ODC no-exitosa (incluida una que solo
    quedó encolada por HTTP 202, no un error real) hacía que NINGUNA ODC del pedido
    recibiera su correo de despacho -- ni siquiera la que sí tuvo éxito."""
    oc_repo = MagicMock()
    oc_sap_service = MagicMock()
    odcs = [_odc("oc-RL", "RL-CD"), _odc("oc-RG", "RG-CD")]

    def fake_en_thread(odc, process_id=None, lock=None):
        if odc["oc_id"] == "oc-RL":
            return _envio_ok("oc-RL", "RL-CD", 1001)
        return _envio_encolado("oc-RG", "RG-CD")

    with patch(
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_una_odc_a_sap_en_thread",
        side_effect=fake_en_thread,
    ), patch(
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_email_despacho_odc"
    ) as mock_despacho:
        resultado = _paso3_enviar_odc_sap(oc_repo, oc_sap_service, odcs, **_args_comunes())

    # Solo la ODC exitosa (RL) recibe correo de despacho; la encolada (RG) no tiene
    # nada que despachar todavía.
    mock_despacho.assert_called_once()
    assert mock_despacho.call_args.args[1] == {"oc_id": "oc-RL"}

    assert resultado["response"].status == "partial"
    assert "confirmará automáticamente" in resultado["response"].message
    assert "falló" not in resultado["response"].message


def test_odc_exitosa_recibe_correo_aunque_la_hermana_falle_con_error_real():
    """La ODC exitosa siempre recibe su correo, sin importar si la hermana quedó
    encolada o falló con un error real de SAP."""
    oc_repo = MagicMock()
    oc_sap_service = MagicMock()
    odcs = [_odc("oc-RL", "RL-CD"), _odc("oc-RG", "RG-CD")]

    def fake_en_thread(odc, process_id=None, lock=None):
        if odc["oc_id"] == "oc-RL":
            return _envio_ok("oc-RL", "RL-CD", 1001)
        return _envio_error_real("oc-RG", "RG-CD")

    with patch(
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_una_odc_a_sap_en_thread",
        side_effect=fake_en_thread,
    ), patch(
        "src.endpoints.pedidos.redistribucion.endpoints_proceso._enviar_email_despacho_odc"
    ) as mock_despacho:
        resultado = _paso3_enviar_odc_sap(oc_repo, oc_sap_service, odcs, **_args_comunes())

    mock_despacho.assert_called_once()
    assert mock_despacho.call_args.args[1] == {"oc_id": "oc-RL"}
    assert resultado["response"].status == "partial"
    assert "SKU no existe en SAP" in resultado["response"].message
