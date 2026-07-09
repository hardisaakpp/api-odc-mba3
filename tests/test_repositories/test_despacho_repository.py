"""
Tests para DespachoRepository.
"""

import pytest  # type: ignore[reportMissingImports]
from unittest.mock import MagicMock, Mock
import uuid

from src.database.repositories.despacho_repository import DespachoRepository


@pytest.fixture
def mock_connection():
    """Fixture que crea una conexión mockeada."""
    conn = MagicMock()
    conn.cursor.return_value = MagicMock()
    return conn


@pytest.fixture
def repository(mock_connection):
    """Fixture que crea un repositorio con conexión mockeada."""
    return DespachoRepository(mock_connection)


class TestDespachoRepositoryFindByCodigoFactura:
    """Tests para find_by_codigo_factura."""
    
    def test_find_by_codigo_factura_exists(self, repository, mock_connection):
        """Test que encuentra despacho cuando existe."""
        codigo_factura = "FE-123-TRAYO"
        despacho_id = str(uuid.uuid4())
        
        cursor = MagicMock()
        cursor.fetchone.return_value = (despacho_id,)
        mock_connection.cursor.return_value = cursor
        
        result = repository.find_by_codigo_factura(codigo_factura)
        
        assert result == despacho_id
        cursor.execute.assert_called_once()
        cursor.close.assert_called_once()
    
    def test_find_by_codigo_factura_not_exists(self, repository, mock_connection):
        """Test que retorna None cuando no existe."""
        codigo_factura = "FE-999-NOTEXISTS"
        
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        mock_connection.cursor.return_value = cursor
        
        result = repository.find_by_codigo_factura(codigo_factura)
        
        assert result is None
        cursor.close.assert_called_once()


class TestDespachoRepositoryGetExistingCabecera:
    """Tests para get_existing_cabecera."""
    
    def test_get_existing_cabecera_exists(self, repository, mock_connection):
        """Test que obtiene cabecera cuando existe."""
        despacho_id = str(uuid.uuid4())
        
        cursor = MagicMock()
        cursor.fetchone.return_value = (
            "TRAYO", "CLI001", "2025-01-21", "FE-123-TRAYO",
            0, "176120", 129165, 900125351, "FE", "OC001",
            "OC_CLI001", 1, 123, "2025-01-21", 456, "BOD001", 1
        )
        mock_connection.cursor.return_value = cursor
        
        result = repository.get_existing_cabecera(despacho_id)
        
        assert result is not None
        assert result["empresa"] == "TRAYO"
        assert result["codigo_cliente"] == "CLI001"
        assert result["codigo_factura"] == "FE-123-TRAYO"
        assert result["anulada"] == 0
        assert result["confirmado"] == 1
        cursor.close.assert_called_once()
    
    def test_get_existing_cabecera_not_exists(self, repository, mock_connection):
        """Test que retorna None cuando no existe."""
        despacho_id = str(uuid.uuid4())
        
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        mock_connection.cursor.return_value = cursor
        
        result = repository.get_existing_cabecera(despacho_id)
        
        assert result is None
        cursor.close.assert_called_once()


class TestDespachoRepositoryInsertCabecera:
    """Tests para insert_cabecera."""
    
    def test_insert_cabecera_success(self, repository, mock_connection):
        """Test que inserta cabecera exitosamente."""
        datos_cabecera = {
            "empresa": "TRAYO",
            "codigo_cliente": "CLI001",
            "fecha_despacho": "2025-01-21",
            "codigo_factura": "FE-123-TRAYO",
            "anulada": 0,
            "numero_pedido_sistema": "176120",
            "numero_orden": 129165,
            "numero_factura": 900125351,
            "tipo_documento": "FE",
            "orden_compra": "OC001",
            "orden_compra_cliente": "OC_CLI001",
            "remision_facturada": 1,
            "num_id_factura_relacionada": 123,
            "codigo_despacho": 456,
            "codigo_bodega": "BOD001",
            "fecha_factura": "2025-01-21",
            "confirmado": 1
        }
        
        cursor = MagicMock()
        cursor.execute.return_value.fetchone.return_value = (str(uuid.uuid4()),)
        mock_connection.cursor.return_value = cursor
        
        result = repository.insert_cabecera(datos_cabecera)
        
        assert result is not None
        assert isinstance(result, str)
        cursor.execute.assert_called()
        mock_connection.commit.assert_called_once()
        cursor.close.assert_called_once()
    
    def test_insert_cabecera_missing_codigo_factura(self, repository):
        """Test que lanza ValueError cuando falta codigo_factura."""
        datos_cabecera = {
            "empresa": "TRAYO",
            "codigo_cliente": "CLI001"
        }
        
        with pytest.raises(ValueError, match="codigo_factura"):
            repository.insert_cabecera(datos_cabecera)
    
    def test_insert_cabecera_missing_required_fields(self, repository):
        """Test que lanza ValueError cuando faltan campos requeridos."""
        datos_cabecera = {
            "codigo_factura": "FE-123-TRAYO"
            # Faltan empresa, codigo_cliente, etc.
        }
        
        with pytest.raises(ValueError, match="requeridos"):
            repository.insert_cabecera(datos_cabecera)


class TestDespachoRepositoryDeleteDetalles:
    """Tests para delete_detalles."""
    
    def test_delete_detalles_success(self, repository, mock_connection):
        """Test que elimina detalles exitosamente."""
        despacho_id = str(uuid.uuid4())
        
        cursor = MagicMock()
        cursor.rowcount = 5
        mock_connection.cursor.return_value = cursor
        
        result = repository.delete_detalles(despacho_id)
        
        assert result == 5
        cursor.execute.assert_called_once()
        mock_connection.commit.assert_called_once()
        cursor.close.assert_called_once()
    
    def test_delete_detalles_none_deleted(self, repository, mock_connection):
        """Test que retorna 0 cuando no hay detalles."""
        despacho_id = str(uuid.uuid4())
        
        cursor = MagicMock()
        cursor.rowcount = 0
        mock_connection.cursor.return_value = cursor
        
        result = repository.delete_detalles(despacho_id)
        
        assert result == 0
    
    def test_delete_detalles_error_rollback(self, repository, mock_connection):
        """Test que hace rollback cuando hay error."""
        despacho_id = str(uuid.uuid4())
        
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB Error")
        mock_connection.cursor.return_value = cursor
        
        with pytest.raises(Exception, match="DB Error"):
            repository.delete_detalles(despacho_id)
        
        mock_connection.rollback.assert_called_once()
        cursor.close.assert_called_once()

