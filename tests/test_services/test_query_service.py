"""
Tests para QueryService.
"""

import pytest  # type: ignore[reportMissingImports]
from datetime import datetime
from unittest.mock import patch, MagicMock

from src.services.query_service import QueryService
from src.exceptions import QueryValidationError
from src.models import QueryResponse


class TestQueryService:
    """Tests para QueryService."""
    
    def test_process_query_valid_select(self):
        """Test que procesa una query SELECT válida correctamente."""
        query_text = "SELECT * FROM tabla WHERE id = 1"
        source = "Test"
        
        with patch('src.services.query_service.validate_query', return_value=(True, "Valid")):
            with patch('src.services.query_service.parse_query', return_value=(
                {"select": "*", "from": "tabla", "where": "id = 1"},
                "PARSE_OK"
            )):
                with patch('src.services.query_service.save_query_to_file'):
                    result = QueryService.process_query(query_text, source)
                    
                    assert isinstance(result, QueryResponse)
                    assert result.original == query_text
                    assert result.source == source
                    assert result.parsed["select"] == "*"
                    assert result.parsed["from"] == "tabla"
                    assert result.note == "PARSE_OK"
                    # received_at debe ser un timestamp ISO válido (no vacío)
                    assert result.received_at is not None
                    assert len(result.received_at) > 0
    
    def test_process_query_invalid_raises_error(self):
        """Test que lanza QueryValidationError para queries inválidas."""
        query_text = "INSERT INTO tabla VALUES (1)"
        source = "Test"
        
        with patch('src.services.query_service.validate_query', return_value=(False, "Only SELECT allowed")):
            with pytest.raises(QueryValidationError, match="Only SELECT allowed"):
                QueryService.process_query(query_text, source)
    
    def test_process_query_with_custom_timestamp(self):
        """Test que acepta un timestamp personalizado."""
        query_text = "SELECT * FROM tabla"
        source = "Test"
        custom_timestamp = "2025-01-21T12:00:00"
        
        with patch('src.services.query_service.validate_query', return_value=(True, "Valid")):
            with patch('src.services.query_service.parse_query', return_value=(
                {"select": "*", "from": "tabla"},
                "PARSE_OK"
            )):
                with patch('src.services.query_service.save_query_to_file'):
                    result = QueryService.process_query(query_text, source, received_at=custom_timestamp)
                    
                    assert result.received_at == custom_timestamp
    
    def test_process_query_saves_to_file(self):
        """Test que guarda la query en archivo."""
        query_text = "SELECT * FROM tabla"
        source = "Test"
        
        with patch('src.services.query_service.validate_query', return_value=(True, "Valid")):
            with patch('src.services.query_service.parse_query', return_value=(
                {"select": "*", "from": "tabla"},
                "PARSE_OK"
            )):
                with patch('src.services.query_service.save_query_to_file') as mock_save:
                    QueryService.process_query(query_text, source)
                    
                    # Verificar que se llamó save_query_to_file
                    assert mock_save.called
                    call_args = mock_save.call_args[0][0]
                    assert call_args["original"] == query_text
                    assert call_args["source"] == source

