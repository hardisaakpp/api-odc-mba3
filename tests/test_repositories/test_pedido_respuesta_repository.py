"""
Tests para PedidoRespuestaRepository.
"""

import pytest  # type: ignore[reportMissingImports]
from unittest.mock import MagicMock, Mock
import uuid
from datetime import datetime

from src.database.repositories.pedido_respuesta_repository import PedidoRespuestaRepository


@pytest.fixture
def mock_connection():
    """Fixture que crea una conexión mockeada."""
    conn = MagicMock()
    conn.cursor.return_value = MagicMock()
    return conn


@pytest.fixture
def repository(mock_connection):
    """Fixture que crea un repositorio con conexión mockeada."""
    return PedidoRespuestaRepository(mock_connection)


class TestPedidoRespuestaRepositoryCrearRespuesta:
    """Tests para crear_respuesta_proveedor."""
    
    def test_crear_respuesta_primera_version(self, repository, mock_connection):
        """Test que crea primera versión (version = 1)."""
        pedido_id = str(uuid.uuid4())
        usuario_id = "user123"
        
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            (None,),  # MAX(version) retorna None (primera vez)
            (str(uuid.uuid4()),)  # NEWID() retorna UUID
        ]
        cursor.rowcount = 1
        mock_connection.cursor.return_value = cursor
        
        respuesta_id = repository.crear_respuesta_proveedor(
            pedido_id=pedido_id,
            usuario_id=usuario_id,
            observaciones_generales="Test"
        )
        
        assert respuesta_id is not None
        assert cursor.execute.call_count == 3  # MAX, NEWID, INSERT
        mock_connection.commit.assert_called_once()
        cursor.close.assert_called_once()
    
    def test_crear_respuesta_segunda_version(self, repository, mock_connection):
        """Test que incrementa versión automáticamente."""
        pedido_id = str(uuid.uuid4())
        
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            (1,),  # MAX(version) retorna 1 (ya existe versión 1)
            (str(uuid.uuid4()),)  # NEWID()
        ]
        mock_connection.cursor.return_value = cursor
        
        respuesta_id = repository.crear_respuesta_proveedor(
            pedido_id=pedido_id,
            usuario_id=None,
            observaciones_generales=None
        )
        
        assert respuesta_id is not None
        # Verificar que se insertó con version = 2
        insert_call = cursor.execute.call_args_list[-1]
        assert insert_call[0][1][2] == 2  # Tercer parámetro es version


class TestPedidoRespuestaRepositoryGuardarDetalles:
    """Tests para guardar_respuesta_detalles."""
    
    def test_guardar_detalles_success(self, repository, mock_connection):
        """Test que guarda detalles exitosamente."""
        respuesta_id = str(uuid.uuid4())
        pedido_detalle_id = str(uuid.uuid4())
        
        respuestas_cantidades = [{
            "pedido_detalle_id": pedido_detalle_id,
            "cantidad_solicitada_total": 100,
            "cantidad_confirmada_total": 80,
            "observaciones": "Stock limitado"
        }]
        respuestas_precios = [{
            "pedido_detalle_id": pedido_detalle_id,
            "costo_doc_sin_iva_ajustado": 95.50,
            "descuento_1_ajustado": 5.0,
            "observaciones_precio": "Precio especial"
        }]
        
        cursor = MagicMock()
        # Mock para obtener precios originales
        cursor.fetchone.return_value = (100.00, 10.0)  # costo, descuento
        cursor.rowcount = 1
        mock_connection.cursor.return_value = cursor
        
        resultado = repository.guardar_respuesta_detalles(
            respuesta_id=respuesta_id,
            respuestas_cantidades=respuestas_cantidades,
            respuestas_precios=respuestas_precios
        )
        
        assert resultado["cantidades_guardadas"] == 1
        assert resultado["precios_guardados"] == 1
        mock_connection.commit.assert_called_once()
        cursor.close.assert_called_once()
    
    def test_guardar_detalles_sin_precios(self, repository, mock_connection):
        """Test que guarda detalles sin precios ajustados."""
        respuesta_id = str(uuid.uuid4())
        pedido_detalle_id = str(uuid.uuid4())
        
        respuestas_cantidades = [{
            "pedido_detalle_id": pedido_detalle_id,
            "cantidad_solicitada_total": 100,
            "cantidad_confirmada_total": 80,
            "observaciones": None
        }]
        respuestas_precios = []
        
        cursor = MagicMock()
        cursor.fetchone.return_value = (100.00, 10.0)
        cursor.rowcount = 1
        mock_connection.cursor.return_value = cursor
        
        resultado = repository.guardar_respuesta_detalles(
            respuesta_id=respuesta_id,
            respuestas_cantidades=respuestas_cantidades,
            respuestas_precios=respuestas_precios
        )
        
        assert resultado["cantidades_guardadas"] == 1
        assert resultado["precios_guardados"] == 0


class TestPedidoRespuestaRepositoryObtenerRespuesta:
    """Tests para obtener_respuesta_activa."""
    
    def test_obtener_respuesta_exists(self, repository, mock_connection):
        """Test que obtiene respuesta cuando existe."""
        pedido_id = str(uuid.uuid4())
        respuesta_id = str(uuid.uuid4())
        pedido_detalle_id = str(uuid.uuid4())
        
        cursor = MagicMock()
        # Mock para cabecera
        fecha_respuesta = datetime.now()
        created_at = datetime.now()
        updated_at = datetime.now()
        cursor.fetchone.side_effect = [
            (respuesta_id, 1, "PENDIENTE_REVISION", fecha_respuesta, None, "user1", None, "Obs", created_at, updated_at),
        ]
        # Mock para detalles
        cursor.fetchall.return_value = [
            (str(uuid.uuid4()), pedido_detalle_id, 100, 80, 100.0, 95.0, 10.0, 5.0, "Obs producto", "PROD001", "Producto Test")
        ]
        mock_connection.cursor.return_value = cursor
        
        resultado = repository.obtener_respuesta_activa(pedido_id)
        
        assert resultado is not None
        assert resultado["cabecera"]["respuesta_id"] == respuesta_id
        assert len(resultado["detalles"]) == 1
        assert resultado["detalles"][0]["cantidad_confirmada_total"] == 80
    
    def test_obtener_respuesta_not_exists(self, repository, mock_connection):
        """Test que retorna None cuando no existe."""
        pedido_id = str(uuid.uuid4())
        
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        mock_connection.cursor.return_value = cursor
        
        resultado = repository.obtener_respuesta_activa(pedido_id)
        
        assert resultado is None

