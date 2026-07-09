"""
Tests para MBA3Service.
"""

import pytest  # type: ignore[reportMissingImports]
from unittest.mock import patch, MagicMock

from src.services.mba3_service import MBA3Service
from src.exceptions import QueryValidationError, MBA3QueryError


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


