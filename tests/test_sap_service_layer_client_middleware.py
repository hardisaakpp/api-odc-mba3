"""
Tests del cliente de middleware SAP: bodegas (warehouses) e ítem extendido.

Usa mocks de requests para no depender del middleware real.
"""

from unittest.mock import MagicMock, patch

from src.database.clients.sap_service_layer_client import _MiddlewareSAPServiceLayerClient


def _client():
    # Se instancia la implementación middleware directamente (no vía la factory
    # SAPServiceLayerClient()) para que estos tests prueben siempre el cliente
    # middleware, sin depender del flag SAP_USE_MIDDLEWARE del .env cargado.
    client = _MiddlewareSAPServiceLayerClient()
    client.enabled = True
    return client


def _mock_response(status_code, json_data):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


class TestGetItemExtendido:
    """Campos nuevos (packCode, groupCode, preferredVendorCode) en GET /items/{code}."""

    def test_mapea_campos_nuevos(self):
        client = _client()
        data = {
            "itemCode": "A1", "itemName": "Producto", "purchaseItem": True,
            "salesItem": True, "inventoryItem": True, "valid": True, "frozen": False,
            "itemType": "itItems", "packCode": "X1", "groupCode": 103,
            "preferredVendorCode": "P123",
        }
        with patch.object(client, "_get", return_value=_mock_response(200, data)):
            item = client.get_item("A1")
        assert item is not None
        assert item["U_IXX_PACK"] == "X1"
        assert item["ItmsGrpCod"] == 103
        assert item["CardCode"] == "P123"

    def test_proveedor_preferido_vacio_es_none(self):
        client = _client()
        data = {
            "itemCode": "A1", "itemName": "Producto", "purchaseItem": True,
            "salesItem": True, "inventoryItem": True, "valid": True, "frozen": False,
            "itemType": "itItems", "packCode": None, "groupCode": None,
            "preferredVendorCode": "",
        }
        with patch.object(client, "_get", return_value=_mock_response(200, data)):
            item = client.get_item("A1")
        assert item is not None
        assert item["CardCode"] is None
        assert item["U_IXX_PACK"] is None


class TestGetAllWarehouses:
    def test_mapea_lista_a_whscode_whsname(self):
        client = _client()
        data = {"warehouses": [{"whsCode": "RL-CD", "whsName": "ROLAND CD"}]}
        with patch.object(client, "_get", return_value=_mock_response(200, data)):
            result = client.get_all_warehouses()
        assert result == [{"WhsCode": "RL-CD", "WhsName": "ROLAND CD"}]

    def test_sin_conexion_retorna_none(self):
        client = _client()
        with patch.object(client, "_get", return_value=None):
            assert client.get_all_warehouses() is None

    def test_deshabilitado_retorna_none(self):
        client = _client()
        client.enabled = False
        assert client.get_all_warehouses() is None


class TestValidateWarehousesBatch:
    def test_lista_vacia_no_llama_http(self):
        client = _client()
        with patch.object(client, "_post") as mock_post:
            result = client.validate_warehouses_batch([])
        assert result == {"warehouses": []}
        mock_post.assert_not_called()

    def test_un_solo_chunk_bajo_200(self):
        client = _client()
        data = {"warehouses": [{"whsCode": "RL-CD", "exists": True, "whsName": "ROLAND CD"}]}
        with patch.object(client, "_post", return_value=_mock_response(200, data)) as mock_post:
            result = client.validate_warehouses_batch(["RL-CD"])
        assert result == data
        mock_post.assert_called_once()

    def test_particiona_en_chunks_de_200(self):
        client = _client()
        codigos = [f"W{i:03d}" for i in range(450)]  # 3 chunks: 200, 200, 50
        with patch.object(client, "_validate_warehouses_chunk", return_value=[]) as mock_chunk:
            client.validate_warehouses_batch(codigos)
        assert mock_chunk.call_count == 3
        tamanos = [len(call.args[0]) for call in mock_chunk.call_args_list]
        assert tamanos == [200, 200, 50]

    def test_chunk_fallido_se_marca_connection_error_y_continua(self):
        client = _client()
        codigos = [f"W{i:03d}" for i in range(250)]  # 2 chunks: 200 falla, 50 ok
        respuestas = [None, [{"whsCode": "W200", "exists": True, "whsName": "X"}]]
        with patch.object(client, "_validate_warehouses_chunk", side_effect=respuestas):
            result = client.validate_warehouses_batch(codigos)
        assert result is not None
        errores = [w for w in result["warehouses"] if w.get("errorType") == "connection_error"]
        assert len(errores) == 200
        assert any(w.get("whsCode") == "W200" for w in result["warehouses"])

    def test_todos_los_chunks_fallan_retorna_none(self):
        client = _client()
        with patch.object(client, "_validate_warehouses_chunk", return_value=None):
            result = client.validate_warehouses_batch(["A", "B"])
        assert result is None

    def test_deshabilitado_retorna_none(self):
        client = _client()
        client.enabled = False
        assert client.validate_warehouses_batch(["RL-CD"]) is None


class TestExtraerErrorSapEmbebido:
    """
    El middleware reenvía el error nativo de SAP B1 embebido como texto dentro
    de `detail` (ej. "SAP Service Layer returned HTTP 404: {\"error\": {...}}").
    Sin extraerlo, retry_utils pierde la política de reintento por código B1
    (ej. -2038 fuerza reintento aunque llegue como 400).
    """

    _DETAIL_CON_ERROR_SAP = (
        'SAP Service Layer returned HTTP 404: {\n'
        '   "error" : {\n'
        '      "code" : -2028,\n'
        '      "message" : {\n'
        '         "lang" : "en-us",\n'
        '         "value" : "In \\"BP Code\\", enter vendor code "\n'
        '      }\n'
        '   }\n'
        '}\n'
    )

    def test_extrae_codigo_y_detalle_de_error_embebido(self):
        client = _client()
        response = _mock_response(
            404,
            {"title": "Resource not found in SAP", "status": 404, "detail": self._DETAIL_CON_ERROR_SAP},
        )
        resultado = client._extraer_error_sap_embebido(response)
        assert resultado["error_code"] == -2028
        assert resultado["sap_error_details"]["error"]["code"] == -2028

    def test_detail_sin_json_embebido_retorna_none(self):
        client = _client()
        response = _mock_response(400, {"title": "Bad request", "status": 400, "detail": "Sin JSON aquí"})
        resultado = client._extraer_error_sap_embebido(response)
        assert resultado == {"error_code": None, "sap_error_details": None}

    def test_body_no_json_retorna_none(self):
        client = _client()
        response = MagicMock()
        response.json.side_effect = ValueError("not json")
        resultado = client._extraer_error_sap_embebido(response)
        assert resultado == {"error_code": None, "sap_error_details": None}

    def test_create_purchase_order_propaga_error_code(self):
        client = _client()
        response = _mock_response(
            404,
            {"title": "Resource not found in SAP", "status": 404, "detail": self._DETAIL_CON_ERROR_SAP},
        )
        with patch.object(client, "_post", return_value=response):
            resultado = client.create_purchase_order({
                "CardCode": "PFAKE",
                "DocumentLines": [],
            })
        assert resultado is not None
        assert resultado["success"] is False
        assert resultado["error_code"] == -2028
        assert resultado["sap_error_details"]["error"]["code"] == -2028

    def test_create_stock_transfer_propaga_error_code(self):
        client = _client()
        response = _mock_response(
            404,
            {"title": "Resource not found in SAP", "status": 404, "detail": self._DETAIL_CON_ERROR_SAP},
        )
        with patch.object(client, "_post", return_value=response):
            resultado = client.create_stock_transfer({
                "FromWarehouse": "ZZZ",
                "ToWarehouse": "ZZZ2",
                "StockTransferLines": [],
            })
        assert resultado is not None
        assert resultado["success"] is False
        assert resultado["error_code"] == -2028


class TestGetItemsBatch:
    """POST /api/v1/items/batch: un solo intento por chunk, sin polling."""

    @staticmethod
    def _item(code, name="Producto", group_name="R-MEDIAS"):
        return {
            "itemCode": code, "itemName": name, "purchaseItem": True,
            "salesItem": True, "inventoryItem": True, "valid": True, "frozen": False,
            "itemType": "itItems", "packCode": "X3", "groupCode": 103,
            "groupName": group_name, "preferredVendorCode": None,
        }

    def test_lista_vacia_no_llama_http(self):
        client = _client()
        with patch.object(client, "_post") as mock_post:
            result = client.get_items_batch([])
        assert result == {}
        mock_post.assert_not_called()

    def test_mixto_encontrados_y_no_encontrados(self):
        client = _client()
        data = {"items": [self._item("A1"), self._item("B2")], "notFound": ["C3"]}
        with patch.object(client, "_post", return_value=_mock_response(200, data)):
            result = client.get_items_batch(["A1", "B2", "C3"])
        assert result["A1"]["ItemName"] == "Producto"
        assert result["A1"]["ItmsGrpNam"] == "R-MEDIAS"
        assert result["B2"]["ItemCode"] == "B2"
        assert result["C3"] == {
            "_error": True, "_error_type": "no_existe",
            "_error_message": "Item 'C3' no existe en SAP",
        }

    def test_particiona_en_chunks_de_100(self):
        client = _client()
        codigos = [f"I{i:03d}" for i in range(150)]  # 2 chunks: 100, 50
        with patch.object(client, "_get_items_batch_chunk", return_value=None) as mock_chunk:
            client.get_items_batch(codigos)
        assert mock_chunk.call_count == 2
        tamanos = [len(call.args[0]) for call in mock_chunk.call_args_list]
        assert tamanos == [100, 50]

    def test_chunk_no_disponible_202_no_aparece_en_resultado(self):
        """202 (encolado, SAP lento/saturado): mismo tratamiento que cualquier no-200, un solo intento."""
        client = _client()
        response = _mock_response(202, {"jobId": "abc", "status": "ENCOLADO"})
        with patch.object(client, "_post", return_value=response):
            result = client.get_items_batch(["A1"])
        assert result is None  # único chunk, y no se resolvió

    def test_un_chunk_falla_otro_ok_solo_los_resueltos_aparecen(self):
        client = _client()
        codigos = [f"I{i:03d}" for i in range(150)]  # 2 chunks: 100, 50
        respuestas = [
            None,  # primer chunk (100 codigos) no disponible
            {"items": [self._item("I100")], "notFound": []},  # segundo chunk (50 codigos) ok
        ]
        with patch.object(client, "_get_items_batch_chunk", side_effect=respuestas):
            result = client.get_items_batch(codigos)
        assert result is not None
        assert "I100" in result
        assert "I000" not in result  # del chunk que fallo, ausente (no un error explicito)

    def test_todos_los_chunks_fallan_retorna_none(self):
        client = _client()
        with patch.object(client, "_get_items_batch_chunk", return_value=None):
            result = client.get_items_batch(["A1", "B2"])
        assert result is None

    def test_deshabilitado_retorna_none(self):
        client = _client()
        client.enabled = False
        assert client.get_items_batch(["A1"]) is None
