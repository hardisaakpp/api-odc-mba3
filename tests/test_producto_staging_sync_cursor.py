"""
Regresión: el refactor de reducción de Complejidad Cognitiva descartaba el
cursor calculado por _determinar_estrategia_sync al llamar a
_bucle_paginacion_mba3 (siempre arrancaba con last_product_id=None), por lo
que el sync "incremental" de MBA3 en realidad reprocesaba todo el catálogo
en cada corrida. `sync_sap_products`, en el mismo archivo, sí pasaba el
cursor (initial_cursor) correctamente.
"""

from unittest.mock import MagicMock, patch

from src.database.services.producto_staging_sync_service import ProductoStagingSyncService


def _service_con_mba3_mock(queries_capturadas):
    service = ProductoStagingSyncService()
    service.mba3_service = MagicMock()

    def execute_query(query):
        queries_capturadas.append(query)
        return []  # sin productos -> el bucle termina en la primera iteración

    service.mba3_service.execute_query.side_effect = execute_query
    return service


class TestBuclePaginacionMba3Cursor:
    def test_usa_initial_cursor_como_punto_de_partida(self):
        queries = []
        service = _service_con_mba3_mock(queries)
        repo = MagicMock()

        service._bucle_paginacion_mba3(
            repo, "SELECT * FROM X WHERE 1=1", 1000, False, initial_cursor="ABC123"
        )

        assert len(queries) == 1
        assert "ABC123" in queries[0]

    def test_sin_initial_cursor_arranca_desde_el_inicio(self):
        queries = []
        service = _service_con_mba3_mock(queries)
        repo = MagicMock()

        service._bucle_paginacion_mba3(repo, "SELECT * FROM X WHERE 1=1", 1000, False)

        assert len(queries) == 1
        assert "PRODUCT_ID" not in queries[0].split("WHERE")[-1] or "LIMIT" in queries[0]
        assert "ABC123" not in queries[0]

    def test_sync_mba3_products_propaga_cursor_calculado(self):
        service = ProductoStagingSyncService()
        service._determinar_estrategia_sync = MagicMock(return_value=("incremental", "CURSOR-XYZ"))

        capturado = {}

        def fake_bucle(mba3_staging_repo, query_base, batch_size, force_full_sync, initial_cursor=None):
            capturado["initial_cursor"] = initial_cursor
            return {
                "total_insertados": 0, "total_actualizados": 0, "total_errores": 0,
                "total_procesados": 0, "productos_encontrados": set(), "batch_number": 0,
            }

        service._bucle_paginacion_mba3 = fake_bucle
        service._limpiar_obsoletos_mba3 = MagicMock(return_value=0)

        with patch(
            "src.database.services.producto_staging_sync_service.get_db_connection",
            return_value=MagicMock(),
        ), patch(
            "src.database.services.producto_staging_sync_service.ProductoMBA3StagingRepository",
            return_value=MagicMock(),
        ), patch(
            "src.database.services.producto_staging_sync_service.SyncControlRepository",
            return_value=MagicMock(),
        ):
            service.sync_mba3_products()

        assert capturado["initial_cursor"] == "CURSOR-XYZ"
