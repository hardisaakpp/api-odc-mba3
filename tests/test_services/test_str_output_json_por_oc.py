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
