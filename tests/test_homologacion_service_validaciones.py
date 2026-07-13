"""
Tests de las validaciones de create/update_homologacion_sku.

Cubre una discrepancia real detectada en una auditoría contra `main`: al
deduplicar create/update en un solo helper (_validar_campos_homologacion),
update_homologacion_sku empezó a validar precio_unitario_mba3 y
cantidad_docena_mba3 (que en main nunca validaba), y create_homologacion_sku
empezó a validar estado (que en main tampoco validaba). Se revirtió a dos
validaciones de alcance exacto por método; estos tests fijan ese alcance.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from src.database.services.homologacion_service import HomologacionService


@contextmanager
def _mock_conn_context(repo):
    with patch(
        "src.database.services.homologacion_service.get_db_connection",
        return_value=MagicMock(),
    ), patch(
        "src.database.services.homologacion_service.HomologacionRepository",
        return_value=repo,
    ):
        yield


class TestCreateHomologacionSkuValidacion:
    def test_rechaza_precio_unitario_mba3_negativo(self):
        service = HomologacionService()
        repo = MagicMock()
        with _mock_conn_context(repo):
            resultado = service.create_homologacion_sku(
                {"sku_mba3": "SKU1", "precio_unitario_mba3": -1}
            )
        assert resultado["status"] == "error"
        assert resultado["error_code"] == "VALIDATION_ERROR"
        repo.create_homologacion_sku.assert_not_called()

    def test_rechaza_cantidad_docena_mba3_negativa(self):
        service = HomologacionService()
        repo = MagicMock()
        with _mock_conn_context(repo):
            resultado = service.create_homologacion_sku(
                {"sku_mba3": "SKU1", "cantidad_docena_mba3": -1}
            )
        assert resultado["status"] == "error"
        repo.create_homologacion_sku.assert_not_called()

    def test_no_valida_estado_igual_que_main(self):
        """main nunca validó 'estado' en create; un valor inválido no debe bloquear."""
        service = HomologacionService()
        repo = MagicMock()
        repo.create_homologacion_sku.return_value = {"id": "x"}
        with _mock_conn_context(repo):
            resultado = service.create_homologacion_sku(
                {"sku_mba3": "SKU1", "estado": "NO_ES_UN_ESTADO_VALIDO"}
            )
        assert resultado["status"] == "success"
        repo.create_homologacion_sku.assert_called_once()


class TestUpdateHomologacionSkuValidacion:
    def test_no_rechaza_precio_unitario_mba3_negativo(self):
        """Regresión: update no debe validar este campo (main tampoco lo hacía)."""
        service = HomologacionService()
        repo = MagicMock()
        repo.update_homologacion_sku.return_value = True
        repo.get_homologacion_by_id.return_value = {"id": "x"}
        with _mock_conn_context(repo):
            resultado = service.update_homologacion_sku("id-1", {"precio_unitario_mba3": -5})
        assert resultado["status"] == "success"
        repo.update_homologacion_sku.assert_called_once()

    def test_no_rechaza_cantidad_docena_mba3_negativa(self):
        service = HomologacionService()
        repo = MagicMock()
        repo.update_homologacion_sku.return_value = True
        repo.get_homologacion_by_id.return_value = {"id": "x"}
        with _mock_conn_context(repo):
            resultado = service.update_homologacion_sku("id-1", {"cantidad_docena_mba3": -5})
        assert resultado["status"] == "success"
        repo.update_homologacion_sku.assert_called_once()

    def test_rechaza_precio_unitario_sap_negativo(self):
        service = HomologacionService()
        repo = MagicMock()
        with _mock_conn_context(repo):
            resultado = service.update_homologacion_sku("id-1", {"precio_unitario_sap": -5})
        assert resultado["status"] == "error"
        repo.update_homologacion_sku.assert_not_called()

    def test_rechaza_cantidad_pack_sap_negativa(self):
        service = HomologacionService()
        repo = MagicMock()
        with _mock_conn_context(repo):
            resultado = service.update_homologacion_sku("id-1", {"cantidad_pack_sap": -5})
        assert resultado["status"] == "error"
        repo.update_homologacion_sku.assert_not_called()

    def test_rechaza_estado_invalido(self):
        service = HomologacionService()
        repo = MagicMock()
        with _mock_conn_context(repo):
            resultado = service.update_homologacion_sku("id-1", {"estado": "INVALIDO"})
        assert resultado["status"] == "error"
        repo.update_homologacion_sku.assert_not_called()

    def test_acepta_estado_valido(self):
        service = HomologacionService()
        repo = MagicMock()
        repo.update_homologacion_sku.return_value = True
        repo.get_homologacion_by_id.return_value = {"id": "x"}
        with _mock_conn_context(repo):
            resultado = service.update_homologacion_sku("id-1", {"estado": "HOMOLOGADO"})
        assert resultado["status"] == "success"
