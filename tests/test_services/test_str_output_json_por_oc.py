"""
Test de regresion: un pedido con 2 ODC (una por bodega/marca, Fase 2 de PYTD002)
llama a _persistir_y_guardar_json_solicitudes_transferencia una vez por ODC. El
archivo de diagnostico output/str_{pedido_id}.json se nombraba solo por pedido_id,
asi que la segunda ODC pisaba el archivo que habia dejado la primera (ver caso real:
pedido E5D5568D, RG-CD 1/1 se perdio al sobrescribirlo RL-CD 3/3, aunque ambas
Solicitudes de Transferencia se crearon correctamente en SAP segun la BD).
"""

from unittest.mock import MagicMock, patch

from src.database.services.stock_transfer_service import StockTransferService


def test_dos_odcs_del_mismo_pedido_generan_archivos_str_distintos(tmp_path):
    with patch("src.database.services.stock_transfer_service.PROJECT_ROOT", tmp_path), \
         patch("src.database.services.stock_transfer_service.SolicitudTransferenciaRepository"):
        service = StockTransferService()

        service._persistir_y_guardar_json_solicitudes_transferencia(
            conn=MagicMock(),
            result={"success": True, "total_tiendas": 1, "transferencias_creadas": 1},
            payloads_sap=[],
            oc_id="oc-RG-CD",
            pedido_id="pedido-1",
            bodega_origen="RG-CD",
            oc_doc_num=24671,
        )
        service._persistir_y_guardar_json_solicitudes_transferencia(
            conn=MagicMock(),
            result={"success": True, "total_tiendas": 3, "transferencias_creadas": 3},
            payloads_sap=[],
            oc_id="oc-RL-CD",
            pedido_id="pedido-1",
            bodega_origen="RL-CD",
            oc_doc_num=24672,
        )

    archivos = sorted(p.name for p in (tmp_path / "output").glob("str_pedido-1*.json"))
    assert archivos == ["str_pedido-1_oc-RG-CD.json", "str_pedido-1_oc-RL-CD.json"]


def test_cerrar_resumen_actualiza_encabezado_existente_en_vez_de_insertar_uno_nuevo(tmp_path):
    """Persistencia por tienda (2026-08-28): el encabezado ya se creó ANTES del
    envío a SAP (para poder guardar cada tienda de inmediato); al cierre solo se
    actualizan sus contadores finales -- nunca se vuelve a insertar ni se toca
    solicitud_transferencia_detalle de nuevo."""
    with patch("src.database.services.stock_transfer_service.PROJECT_ROOT", tmp_path), \
         patch("src.database.services.stock_transfer_service.SolicitudTransferenciaRepository") as MockRepo:
        service = StockTransferService()

        service._cerrar_resumen_y_guardar_json_solicitudes_transferencia(
            conn=MagicMock(),
            solicitud_transferencia_id="solicitud-1",
            result={"success": True, "total_tiendas": 1, "transferencias_creadas": 1, "resultados": []},
            payloads_sap=[],
            oc_id="oc-1",
            pedido_id="pedido-1",
            bodega_origen="RL-CD",
            oc_doc_num=24672,
        )

    # update_resumen recibe la MISMA referencia que luego se le agrega
    # solicitud_transferencia_id (para el caller) -- se valida el arg posicional
    # y el contenido relevante, no una igualdad exacta del dict post-mutación.
    MockRepo.return_value.update_resumen.assert_called_once()
    call_args = MockRepo.return_value.update_resumen.call_args.args
    assert call_args[0] == "solicitud-1"
    assert call_args[1]["transferencias_creadas"] == 1
    MockRepo.return_value.insert.assert_not_called()
    MockRepo.return_value.insert_detalle.assert_not_called()
    archivos = list((tmp_path / "output").glob("str_pedido-1*.json"))
    assert len(archivos) == 1
