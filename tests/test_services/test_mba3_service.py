"""
Tests para MBA3Service.
"""

import pytest  # type: ignore[reportMissingImports]
from unittest.mock import patch, MagicMock

from src.services.mba3_service import MBA3Service
from src.exceptions import QueryValidationError, MBA3QueryError


class TestMBA3ServiceBuildFacturasQuery:
    """Tests para build_facturas_query."""
    
    def test_build_query_without_filters(self):
        """Test que construye query base sin filtros."""
        query = MBA3Service.build_facturas_query()
        
        assert "SELECT" in query
        assert "CLNT_FACTURA_PRINCIPAL" in query
        assert "WHERE" not in query
    
    def test_build_query_with_anulada_filter(self):
        """Test que agrega filtro de anulada."""
        query = MBA3Service.build_facturas_query(anulada=True)
        
        assert "WHERE" in query
        assert "ANULADA='true'" in query
    
    def test_build_query_with_confirmado_filter(self):
        """Test que agrega filtro de confirmado."""
        query = MBA3Service.build_facturas_query(confirmado=False)
        
        assert "WHERE" in query
        assert "CONFIRMADO='false'" in query
    
    def test_build_query_with_multiple_filters(self):
        """Test que agrega múltiples filtros."""
        query = MBA3Service.build_facturas_query(
            anulada=False,
            confirmado=True,
            remision_facturada=True
        )
        
        assert "WHERE" in query
        assert "ANULADA='false'" in query
        assert "CONFIRMADO='true'" in query
        assert "Remision_Facturada='true'" in query
        assert query.count("AND") == 2  # Dos AND para tres filtros
    
    def test_build_query_with_obj_datos_filter(self):
        """Test que agrega filtro de ObjDatosFactura."""
        query = MBA3Service.build_facturas_query(include_obj_datos=True)
        
        assert "WHERE" in query
        assert "ObjDatosFactura IS NOT NULL" in query
    
    def test_build_query_without_obj_datos_filter(self):
        """Test que no agrega filtro de ObjDatosFactura cuando es False."""
        query = MBA3Service.build_facturas_query(include_obj_datos=False)
        
        assert "WHERE" not in query or "ObjDatosFactura" not in query


class TestMBA3ServiceExecuteQuery:
    """Tests para execute_query."""
    
    @patch('src.services.mba3_service.get_mba3_client')
    @patch('src.services.mba3_service.validate_query')
    def test_execute_query_success(self, mock_validate, mock_get_client):
        """Test que ejecuta query exitosamente."""
        mock_validate.return_value = (True, "Valid")
        mock_client = MagicMock()
        mock_client.execute_query.return_value = [{"id": 1, "name": "Test"}]
        mock_get_client.return_value = mock_client
        
        result = MBA3Service.execute_query("SELECT * FROM tabla")
        
        assert result == [{"id": 1, "name": "Test"}]
        mock_client.execute_query.assert_called_once_with("SELECT * FROM tabla", require_jwt=True)
    
    @patch('src.services.mba3_service.validate_query')
    def test_execute_query_invalid_raises_error(self, mock_validate):
        """Test que lanza error para query inválida."""
        mock_validate.return_value = (False, "Only SELECT allowed")
        
        with pytest.raises(QueryValidationError):
            MBA3Service.execute_query("INSERT INTO tabla VALUES (1)")
    
    @patch('src.services.mba3_service.get_mba3_client')
    @patch('src.services.mba3_service.validate_query')
    def test_execute_query_none_result_raises_error(self, mock_validate, mock_get_client):
        """Test que lanza error cuando el resultado es None."""
        mock_validate.return_value = (True, "Valid")
        mock_client = MagicMock()
        mock_client.execute_query.return_value = None
        mock_get_client.return_value = mock_client
        
        with pytest.raises(MBA3QueryError, match="no retornó resultados"):
            MBA3Service.execute_query("SELECT * FROM tabla")
    
    @patch('src.services.mba3_service.get_mba3_client')
    @patch('src.services.mba3_service.validate_query')
    def test_execute_query_exception_raises_error(self, mock_validate, mock_get_client):
        """Test que lanza MBA3QueryError cuando hay excepción."""
        mock_validate.return_value = (True, "Valid")
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = Exception("Connection error")
        mock_get_client.return_value = mock_client
        
        with pytest.raises(MBA3QueryError, match="Error al ejecutar consulta"):
            MBA3Service.execute_query("SELECT * FROM tabla")


class TestMBA3ServiceGetFacturas:
    """Tests para get_facturas."""
    
    @patch('src.services.mba3_service.MBA3Service.save_to_database')
    @patch('src.services.mba3_service.MBA3Service.execute_query')
    def test_get_facturas_success(self, mock_execute, mock_save):
        """Test que obtiene facturas exitosamente."""
        mock_data = [{"CODIGO_FACTURA": "FE-123-TEST"}]
        mock_execute.return_value = mock_data
        mock_save.return_value = {"status": "success", "facturas_guardadas": 1}
        
        result = MBA3Service.get_facturas()
        
        assert result["data"] == mock_data
        assert result["count"] == 1
        assert "query" in result
        assert "filters" in result
        assert "save_status" in result
    
    @patch('src.services.mba3_service.MBA3Service.save_to_database')
    @patch('src.services.mba3_service.MBA3Service.execute_query')
    def test_get_facturas_with_filters(self, mock_execute, mock_save):
        """Test que aplica filtros correctamente."""
        mock_execute.return_value = []
        mock_save.return_value = None
        
        result = MBA3Service.get_facturas(
            anulada=False,
            confirmado=True,
            remision_facturada=False
        )
        
        # Verificar que se construyó la query con filtros
        query = result["query"]
        assert "ANULADA='false'" in query
        assert "CONFIRMADO='true'" in query
        assert "Remision_Facturada='false'" in query
        
        # Verificar que los filtros están en la respuesta
        assert result["filters"]["anulada"] is False
        assert result["filters"]["confirmado"] is True
        assert result["filters"]["remision_facturada"] is False
    
    @patch('src.services.mba3_service.MBA3Service.save_to_database')
    @patch('src.services.mba3_service.MBA3Service.execute_query')
    def test_get_facturas_without_save(self, mock_execute, mock_save):
        """Test que no guarda cuando save_to_db=False."""
        mock_execute.return_value = []
        
        result = MBA3Service.get_facturas(save_to_db=False)
        
        assert result["save_status"] is None
        mock_save.assert_not_called()
    
    @patch('src.services.mba3_service.MBA3Service.save_to_database')
    @patch('src.services.mba3_service.MBA3Service.execute_query')
    def test_get_facturas_save_error_does_not_fail(self, mock_execute, mock_save):
        """Test que no falla cuando hay error al guardar."""
        mock_execute.return_value = [{"CODIGO_FACTURA": "FE-123"}]
        mock_save.side_effect = Exception("DB Error")
        
        # No debe lanzar excepción
        result = MBA3Service.get_facturas(save_to_db=True)
        
        assert result["data"] == [{"CODIGO_FACTURA": "FE-123"}]
        assert result["save_status"]["status"] == "error"

