"""
Tests del cliente de middleware SAP: bodegas (warehouses) e ítem extendido.

Usa mocks de requests para no depender del middleware real.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.database.clients.sap_service_layer_client import _MiddlewareSAPServiceLayerClient


def _client():
    # Se instancia la implementación middleware directamente (no vía la factory
    # SAPServiceLayerClient()) para que estos tests prueben siempre el cliente
    # middleware, sin depender del flag SAP_USE_MIDDLEWARE del .env cargado.
    return _MiddlewareSAPServiceLayerClient()


def _mock_response(status_code, json_data):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


class _FakeRedis:
    """Redis mínimo en memoria: solo get/setex/delete, para no depender del Redis real."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture(autouse=True)
def _sin_redis_por_defecto():
    """
    Por defecto ningún test de este archivo depende de un Redis real (aunque haya
    uno corriendo en el entorno de desarrollo): sin caché de job en curso, igual que
    si Redis no estuviera disponible. Los tests de TestJobEnCursoRedis reemplazan
    este patch con un _FakeRedis explícito para probar ese camino.
    """
    with patch("src.database.clients.sap_service_layer_client._get_redis_client_para_jobs", return_value=None):
        yield


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

    def test_mapea_pvp_y_codigo_barras(self):
        """El middleware resuelve 'pvp' (Precio Minorista, PriceList 1) y 'codeBars'
        directamente; antes de esto ningún campo de precio venía en la respuesta y la
        validación de Pack/PVP (RN-02) nunca podía comparar contra el valor real de SAP."""
        client = _client()
        data = {
            "itemCode": "A1", "itemName": "Producto", "purchaseItem": True,
            "salesItem": True, "inventoryItem": True, "valid": True, "frozen": False,
            "itemType": "itItems", "packCode": "X1", "groupCode": 103,
            "preferredVendorCode": "P123", "pvp": 6.99, "codeBars": "7861215678025",
        }
        with patch.object(client, "_get", return_value=_mock_response(200, data)):
            item = client.get_item("A1")
        assert item is not None
        assert item["Price"] == 6.99
        assert item["CodeBars"] == "7861215678025"

    def test_sin_pvp_ni_codigo_barras_quedan_none(self):
        client = _client()
        data = {
            "itemCode": "A1", "itemName": "Producto", "purchaseItem": True,
            "salesItem": True, "inventoryItem": True, "valid": True, "frozen": False,
            "itemType": "itItems", "packCode": None, "groupCode": None,
            "preferredVendorCode": None,
        }
        with patch.object(client, "_get", return_value=_mock_response(200, data)):
            item = client.get_item("A1")
        assert item is not None
        assert item["Price"] is None
        assert item["CodeBars"] is None


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

    def test_mapea_pvp_y_codigo_barras_por_item(self):
        client = _client()
        item_con_precio = {**self._item("A1"), "pvp": 6.99, "codeBars": "7861215678025"}
        data = {"items": [item_con_precio], "notFound": []}
        with patch.object(client, "_post", return_value=_mock_response(200, data)):
            result = client.get_items_batch(["A1"])
        assert result["A1"]["Price"] == 6.99
        assert result["A1"]["CodeBars"] == "7861215678025"

    def test_particiona_en_chunks_de_100(self):
        client = _client()
        codigos = [f"I{i:03d}" for i in range(150)]  # 2 chunks: 100, 50
        with patch.object(client, "_get_items_batch_chunk", return_value=None) as mock_chunk:
            client.get_items_batch(codigos)
        assert mock_chunk.call_count == 2
        tamanos = [len(call.args[0]) for call in mock_chunk.call_args_list]
        assert tamanos == [100, 50]

    def test_chunk_no_disponible_202_no_aparece_en_resultado(self):
        """202 (encolado, SAP lento/saturado): _post_lectura reintenta acotado y, si sigue
        saturado, el chunk queda igual sin resolverse (mismo contrato que cualquier no-200)."""
        client = _client()
        response = _mock_response(202, {"jobId": "abc", "status": "ENCOLADO"})
        with patch.object(client, "_post", return_value=response), \
                patch("src.database.clients.sap_service_layer_client.time.sleep"):
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


class TestCreateStockTransfer202:
    """HTTP 202 del middleware (job encolado) NO es un error definitivo."""

    def test_202_retorna_queued_con_job_id_no_como_error_terminal(self):
        client = _client()
        response = _mock_response(202, {"jobId": "job-123", "status": "ENCOLADO"})
        with patch.object(client, "_post", return_value=response):
            resultado = client.create_stock_transfer({
                "FromWarehouse": "RL-CD",
                "ToWarehouse": "TRL-PSC",
                "StockTransferLines": [],
            })
        assert resultado["success"] is False
        assert resultado["queued"] is True
        assert resultado["job_id"] == "job-123"
        assert resultado["status_code"] == 202

    def test_200_sigue_retornando_success_normal(self):
        client = _client()
        response = _mock_response(200, {"docEntry": 1, "docNum": 2})
        with patch.object(client, "_post", return_value=response):
            resultado = client.create_stock_transfer({
                "FromWarehouse": "RL-CD",
                "ToWarehouse": "TRL-PSC",
                "StockTransferLines": [],
            })
        assert resultado["success"] is True
        assert "queued" not in resultado


class TestCreatePurchaseOrder202:
    """HTTP 202 del middleware (job encolado) NO es un error definitivo.

    Antes de esto, create_purchase_order no distinguía el 202 de un error real de
    SAP: caía al bloque de error genérico y devolvía "HTTP 202" como si la ODC
    hubiera fallado. Eso hacía que la app marcara la ODC como "ERROR" (perdiendo
    el jobId) y ofreciera el botón de reintento -- si el job encolado terminaba
    completándose en SAP en segundo plano, el reintento creaba una ODC duplicada.
    """

    def test_202_retorna_queued_con_job_id_no_como_error_terminal(self):
        client = _client()
        response = _mock_response(202, {"jobId": "job-456", "status": "ENCOLADO"})
        with patch.object(client, "_post", return_value=response):
            resultado = client.create_purchase_order({
                "CardCode": "PFAKE",
                "DocumentLines": [],
            })
        assert resultado["success"] is False
        assert resultado["queued"] is True
        assert resultado["job_id"] == "job-456"
        assert resultado["status_code"] == 202

    def test_200_sigue_retornando_success_normal(self):
        client = _client()
        response = _mock_response(200, {"docEntry": 1, "docNum": 2})
        with patch.object(client, "_post", return_value=response):
            resultado = client.create_purchase_order({
                "CardCode": "PFAKE",
                "DocumentLines": [],
            })
        assert resultado["success"] is True
        assert "queued" not in resultado


class TestReintento202Lecturas:
    """
    HTTP 202 en lecturas/validaciones (GET, o POST de validación sin efecto
    secundario en SAP) se reintenta acotado dentro de la misma llamada: a
    diferencia de crear una ITR/OC, estas son idempotentes, así que no hay
    riesgo de duplicar nada en SAP al reintentarlas directamente.
    """

    def test_get_recupera_tras_202_sin_agotar_reintentos(self):
        client = _client()
        respuestas = [
            _mock_response(202, {"jobId": "j1", "status": "ENCOLADO"}),
            _mock_response(200, {"ok": True}),
        ]
        with patch("src.database.clients.sap_service_layer_client.requests.get", side_effect=respuestas) as mock_get, \
                patch("src.database.clients.sap_service_layer_client.time.sleep") as mock_sleep:
            response = client._get("/api/v1/items/A1")
        assert response.status_code == 200
        assert mock_get.call_count == 2
        mock_sleep.assert_called_once()

    def test_get_agota_reintentos_y_retorna_el_202_final(self):
        client = _client()
        respuesta_202 = _mock_response(202, {"jobId": "j1", "status": "ENCOLADO"})
        with patch("src.database.clients.sap_service_layer_client.requests.get", return_value=respuesta_202) as mock_get, \
                patch("src.database.clients.sap_service_layer_client.time.sleep") as mock_sleep:
            response = client._get("/api/v1/items/A1")
        assert response.status_code == 202
        assert mock_get.call_count == client._LECTURA_202_MAX_INTENTOS
        assert mock_sleep.call_count == client._LECTURA_202_MAX_INTENTOS - 1

    def test_post_lectura_recupera_tras_202(self):
        client = _client()
        respuestas = [
            _mock_response(202, {"jobId": "j1", "status": "ENCOLADO"}),
            _mock_response(200, {"warehouses": []}),
        ]
        with patch.object(client, "_post", side_effect=respuestas) as mock_post, \
                patch("src.database.clients.sap_service_layer_client.time.sleep"):
            response = client._post_lectura("/api/v1/warehouses/validate", {"warehouseCodes": []})
        assert response.status_code == 200
        assert mock_post.call_count == 2

    def test_get_item_202_persistente_se_distingue_de_error_generico(self):
        """Tras agotar reintentos, el error debe ser reconocible como 'saturado', no un HTTP 202 crudo."""
        client = _client()
        with patch.object(
            client, "_get", return_value=_mock_response(202, {"jobId": "j1", "status": "ENCOLADO"})
        ):
            item = client.get_item("A1")
        assert item["_error"] is True
        assert item["_error_type"] == "saturado"
        assert "HTTP 202" not in item["_error_message"]
        assert "saturado" in item["_error_message"].lower()

    def test_get_business_partner_202_persistente_se_distingue_de_error_generico(self):
        client = _client()
        with patch.object(
            client, "_get", return_value=_mock_response(202, {"jobId": "j1", "status": "ENCOLADO"})
        ):
            bp = client.get_business_partner("P123")
        assert bp["_error"] is True
        assert bp["_error_type"] == "saturado"
        assert "HTTP 202" not in bp["_error_message"]


class TestJobEnCursoRedis:
    """
    El middleware no deduplica peticiones concurrentes para el mismo recurso
    (JobExecutionCoordinator.cs crea un Guid.NewGuid() incondicional). Antes de
    crear un job nuevo por un 202, se consulta si ya había uno guardado en Redis
    para el mismo recurso, para no multiplicar la carga contra SAP.
    """

    _REDIS_PATH = "src.database.clients.sap_service_layer_client._get_redis_client_para_jobs"

    @pytest.fixture(autouse=True)
    def _sin_redis_por_defecto(self):
        """
        Sobreescribe el fixture autouse del módulo (que siempre patchea
        _get_redis_client_para_jobs -> None): esta clase prueba ese mismo caché, y
        cada test parchea explícitamente lo que necesita en su propio cuerpo.
        """
        yield

    @staticmethod
    def _item_data(code="A1"):
        return {
            "itemCode": code, "itemName": "Producto", "purchaseItem": True,
            "salesItem": True, "inventoryItem": True, "valid": True, "frozen": False,
            "itemType": "itItems", "packCode": None, "groupCode": None, "preferredVendorCode": None,
        }

    def test_get_item_202_guarda_job_id_en_redis(self):
        client = _client()
        fake_redis = _FakeRedis()
        response = _mock_response(202, {"jobId": "job-abc", "status": "ENCOLADO"})
        with patch(self._REDIS_PATH, return_value=fake_redis), \
                patch.object(client, "_get", return_value=response):
            item = client.get_item("A1")
        assert item["_error_type"] == "saturado"
        assert fake_redis.store["sap:job_en_curso:item:A1"] == "job-abc"

    def test_get_item_reutiliza_job_completado_sin_nueva_consulta(self):
        client = _client()
        fake_redis = _FakeRedis()
        fake_redis.store["sap:job_en_curso:item:A1"] = "job-abc"
        job_status = {"jobId": "job-abc", "status": "COMPLETADO", "result": self._item_data()}
        with patch(self._REDIS_PATH, return_value=fake_redis), \
                patch.object(client, "get_job_status", return_value=job_status), \
                patch.object(client, "_get") as mock_get:
            item = client.get_item("A1")
        assert item["ItemCode"] == "A1"
        assert item["PurchaseItem"] == "tYES"
        mock_get.assert_not_called()  # no se creó una consulta/job nuevo
        assert "sap:job_en_curso:item:A1" not in fake_redis.store  # se limpió

    def test_get_item_con_job_encolado_retorna_saturado_sin_crear_uno_nuevo(self):
        client = _client()
        fake_redis = _FakeRedis()
        fake_redis.store["sap:job_en_curso:item:A1"] = "job-abc"
        job_status = {"jobId": "job-abc", "status": "ENCOLADO"}
        with patch(self._REDIS_PATH, return_value=fake_redis), \
                patch.object(client, "get_job_status", return_value=job_status), \
                patch.object(client, "_get") as mock_get:
            item = client.get_item("A1")
        assert item["_error_type"] == "saturado"
        mock_get.assert_not_called()
        assert fake_redis.store["sap:job_en_curso:item:A1"] == "job-abc"  # sigue guardado

    def test_get_item_con_job_en_error_limpia_y_consulta_de_nuevo(self):
        client = _client()
        fake_redis = _FakeRedis()
        fake_redis.store["sap:job_en_curso:item:A1"] = "job-abc"
        job_status = {"jobId": "job-abc", "status": "ERROR", "error": "no se pudo resolver"}
        fresh_response = _mock_response(200, self._item_data())
        with patch(self._REDIS_PATH, return_value=fake_redis), \
                patch.object(client, "get_job_status", return_value=job_status), \
                patch.object(client, "_get", return_value=fresh_response) as mock_get:
            item = client.get_item("A1")
        assert item["ItemCode"] == "A1"
        mock_get.assert_called_once()
        assert "sap:job_en_curso:item:A1" not in fake_redis.store

    def test_get_business_partner_reutiliza_job_completado_sin_nueva_consulta(self):
        client = _client()
        fake_redis = _FakeRedis()
        fake_redis.store["sap:job_en_curso:bp:P123"] = "job-xyz"
        bp_data = {"cardCode": "P123", "cardName": "X", "cardType": "cSupplier", "valid": True, "frozen": False}
        job_status = {"jobId": "job-xyz", "status": "COMPLETADO", "result": bp_data}
        with patch(self._REDIS_PATH, return_value=fake_redis), \
                patch.object(client, "get_job_status", return_value=job_status), \
                patch.object(client, "_get") as mock_get:
            bp = client.get_business_partner("P123")
        assert bp["CardCode"] == "P123"
        assert bp["Valid"] == "tYES"
        mock_get.assert_not_called()

    def test_sin_redis_disponible_no_rompe_el_flujo_normal(self):
        client = _client()
        response = _mock_response(200, self._item_data())
        with patch(self._REDIS_PATH, return_value=None), \
                patch.object(client, "_get", return_value=response):
            item = client.get_item("A1")
        assert item["ItemCode"] == "A1"

    def test_get_redis_client_para_jobs_no_cachea_conexion_fallida(self):
        """Si ping() falla, la próxima llamada debe reintentar conectar (no quedar pegada)."""
        import src.database.clients.sap_service_layer_client as mod

        mod._redis_client_jobs = None
        cliente_roto = MagicMock()
        cliente_roto.ping.side_effect = Exception("conexión rechazada")
        try:
            with patch("src.database.clients.sap_service_layer_client.redis.from_url", return_value=cliente_roto) as mock_from_url:
                assert mod._get_redis_client_para_jobs() is None
                assert mod._get_redis_client_para_jobs() is None
            assert mock_from_url.call_count == 2
        finally:
            mod._redis_client_jobs = None


class TestGetJobStatus:
    def test_200_retorna_el_json_del_job(self):
        client = _client()
        data = {"jobId": "job-123", "status": "COMPLETADO", "result": {"docEntry": 1, "docNum": 2}}
        with patch.object(client, "_get", return_value=_mock_response(200, data)):
            resultado = client.get_job_status("job-123")
        assert resultado == data

    def test_sin_conexion_retorna_none(self):
        client = _client()
        with patch.object(client, "_get", return_value=None):
            assert client.get_job_status("job-123") is None

    def test_status_no_200_retorna_none(self):
        client = _client()
        with patch.object(client, "_get", return_value=_mock_response(404, {"title": "not found"})):
            assert client.get_job_status("job-123") is None

    def test_sin_job_id_retorna_none_sin_llamar_http(self):
        client = _client()
        with patch.object(client, "_get") as mock_get:
            assert client.get_job_status("") is None
        mock_get.assert_not_called()
