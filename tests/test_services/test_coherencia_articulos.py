"""
Tests para validación de coherencia de artículos entre hojas.

REGLA ARQUITECTÓNICA: Movimiento depende de Detalle Articulos, no al revés.
Validación de coherencia interna del pedido, no de existencia en SAP.
"""

import pytest
from src.database.services.pedido_validator import PedidoValidator


class TestCoherenciaArticulos:
    """Suite de tests para validación de coherencia entre hojas."""
    
    @pytest.fixture
    def validator(self):
        """Instancia del validador."""
        return PedidoValidator()
    
    def test_coherencia_ok_todos_codigos_declarados(self, validator):
        """
        ✅ TEST 1: Todos los códigos en Movimiento están en Detalle
        
        DADO:
          - Detalle: {PROD-001, PROD-002, PROD-003}
          - Movimiento: {PROD-001, PROD-002}
        
        CUANDO:
          se valida coherencia
        
        ENTONCES:
          debe retornar OK con coherente=True
        """
        # Arrange
        codigos_detalle = {"PROD-001", "PROD-002", "PROD-003"}
        codigos_movimiento = {"PROD-001", "PROD-002"}
        
        # Act
        resultado = validator.validar_coherencia_articulos(
            codigos_detalle=codigos_detalle,
            codigos_movimiento=codigos_movimiento
        )
        
        # Assert
        assert resultado["coherente"] is True
        assert len(resultado["codigos_invalidos"]) == 0
        assert len(resultado["errores"]) == 0
        assert "OK" in resultado["resumen"]
    
    def test_codigo_en_movimiento_no_en_detalle(self, validator):
        """
        ✅ TEST 2: Código en Movimiento que NO está en Detalle
        
        DADO:
          - Detalle: {PROD-001, PROD-002}
          - Movimiento: {PROD-001, PROD-999}
        
        CUANDO:
          se valida coherencia
        
        ENTONCES:
          debe retornar ERROR con PROD-999 como inválido
        """
        # Arrange
        codigos_detalle = {"PROD-001", "PROD-002"}
        codigos_movimiento = {"PROD-001", "PROD-999"}
        
        # Act
        resultado = validator.validar_coherencia_articulos(
            codigos_detalle=codigos_detalle,
            codigos_movimiento=codigos_movimiento
        )
        
        # Assert
        assert resultado["coherente"] is False
        assert "PROD-999" in resultado["codigos_invalidos"]
        assert len(resultado["errores"]) == 1
        
        # Verificar estructura del error
        error = resultado["errores"][0]
        assert error["codigo"] == "PROD-999"
        assert error["tipo"] == "ERROR"
        assert error["severity"] == "CRITICO"
        assert "PROD-999" in error["mensaje"]
        assert "Detalle Articulos" in error["mensaje"]
        assert "accion_recomendada" in error
    
    def test_multiples_codigos_invalidos(self, validator):
        """
        ✅ TEST 3: Múltiples códigos inválidos
        
        DADO:
          - Detalle: {PROD-001}
          - Movimiento: {PROD-001, PROD-888, PROD-999}
        
        CUANDO:
          se valida coherencia
        
        ENTONCES:
          debe detectar ambos códigos inválidos (solo una entrada cada uno)
        """
        # Arrange
        codigos_detalle = {"PROD-001"}
        codigos_movimiento = {"PROD-001", "PROD-888", "PROD-999"}
        
        # Act
        resultado = validator.validar_coherencia_articulos(
            codigos_detalle=codigos_detalle,
            codigos_movimiento=codigos_movimiento
        )
        
        # Assert
        assert resultado["coherente"] is False
        assert len(resultado["codigos_invalidos"]) == 2
        assert "PROD-888" in resultado["codigos_invalidos"]
        assert "PROD-999" in resultado["codigos_invalidos"]
        assert len(resultado["errores"]) == 2  # Una entrada por código
        
        # Verificar que no hay duplicación de errores
        codigos_en_errores = {e["codigo"] for e in resultado["errores"]}
        assert codigos_en_errores == {"PROD-888", "PROD-999"}
    
    def test_normalizacion_espacios_mayusculas(self, validator):
        """
        ✅ TEST 4: Normalización de espacios y mayúsculas
        
        DADO:
          - Detalle: {"PROD-001"} (limpio)
          - Movimiento: {"  prod-001  ", "  PROD-001  "} (con espacios y casos)
        
        CUANDO:
          se valida coherencia
        
        ENTONCES:
          debe coincidir sin falsos errores (normalización dentro del validador)
        """
        # Arrange
        codigos_detalle = {"PROD-001"}
        codigos_movimiento = {"  prod-001  ", "  PROD-001  "}
        
        # Act
        resultado = validator.validar_coherencia_articulos(
            codigos_detalle=codigos_detalle,
            codigos_movimiento=codigos_movimiento
        )
        
        # Assert
        assert resultado["coherente"] is True
        assert len(resultado["codigos_invalidos"]) == 0
        assert len(resultado["errores"]) == 0
    
    def test_movimiento_vacio_es_valido(self, validator):
        """
        ✅ TEST 5: Movimiento vacío es válido
        
        DADO:
          - Detalle: {PROD-001, PROD-002}
          - Movimiento: {} (vacío)
        
        CUANDO:
          se valida coherencia
        
        ENTONCES:
          debe retornar OK (no hay códigos para validar)
        """
        # Arrange
        codigos_detalle = {"PROD-001", "PROD-002"}
        codigos_movimiento = set()
        
        # Act
        resultado = validator.validar_coherencia_articulos(
            codigos_detalle=codigos_detalle,
            codigos_movimiento=codigos_movimiento
        )
        
        # Assert
        assert resultado["coherente"] is True
        assert len(resultado["codigos_invalidos"]) == 0
    
    def test_detalle_vacio_movimiento_con_codigos(self, validator):
        """
        ✅ TEST 6: Detalle vacío pero Movimiento tiene códigos
        
        DADO:
          - Detalle: {} (vacío)
          - Movimiento: {PROD-001}
        
        CUANDO:
          se valida coherencia
        
        ENTONCES:
          debe retornar ERROR (movimiento sin detalle base)
        """
        # Arrange
        codigos_detalle = set()
        codigos_movimiento = {"PROD-001"}
        
        # Act
        resultado = validator.validar_coherencia_articulos(
            codigos_detalle=codigos_detalle,
            codigos_movimiento=codigos_movimiento
        )
        
        # Assert
        assert resultado["coherente"] is False
        assert "PROD-001" in resultado["codigos_invalidos"]
        assert len(resultado["errores"]) == 1
    
    def test_mapeo_a_filas_se_incluye(self, validator):
        """
        ✅ TEST 7: Mapeo de códigos a números de fila
        
        DADO:
          - Detalle: {PROD-001}
          - Movimiento: {PROD-999}
          - mapear_a_filas: {"PROD-999": [5, 10, 15]}
        
        CUANDO:
          se valida con mapeo
        
        ENTONCES:
          debe incluir filas en el error (sin duplicación)
        """
        # Arrange
        codigos_detalle = {"PROD-001"}
        codigos_movimiento = {"PROD-999"}
        mapear_a_filas = {"PROD-999": [5, 10, 15]}
        
        # Act
        resultado = validator.validar_coherencia_articulos(
            codigos_detalle=codigos_detalle,
            codigos_movimiento=codigos_movimiento,
            mapear_a_filas=mapear_a_filas
        )
        
        # Assert
        assert resultado["coherente"] is False
        assert len(resultado["errores"]) == 1  # Una entrada por código
        
        # Verificar que incluye filas
        error = resultado["errores"][0]
        assert "filas" in error
        assert error["filas"] == [5, 10, 15]
    
    def test_mapeo_normalizado_aunque_inputs_sin_normalizar(self, validator):
        """
        ✅ TEST 8: Mapeo se normaliza incluso si entrada sin normalizar
        
        DADO:
          - Detalle: {PROD-001}
          - Movimiento: {  prod-999  }
          - mapear_a_filas: {"  PROD-999  ": [5]}
        
        CUANDO:
          se valida con mapeo sin normalizar
        
        ENTONCES:
          debe normalizar mapeo internamente y coincidir
        """
        # Arrange
        codigos_detalle = {"PROD-001"}
        codigos_movimiento = {"  prod-999  "}
        mapear_a_filas = {"  PROD-999  ": [5]}  # Sin normalizar
        
        # Act
        resultado = validator.validar_coherencia_articulos(
            codigos_detalle=codigos_detalle,
            codigos_movimiento=codigos_movimiento,
            mapear_a_filas=mapear_a_filas
        )
        
        # Assert
        assert resultado["coherente"] is False
        assert len(resultado["errores"]) == 1
        
        # Verificar que el mapeo fue normalizado correctamente
        error = resultado["errores"][0]
        assert "filas" in error
        assert error["filas"] == [5]
    
    def test_ambas_hojas_None_es_valido(self, validator):
        """
        ✅ TEST 9: Si ambas hojas vienen None (caso edge)
        
        DADO:
          - Detalle: None
          - Movimiento: None
        
        CUANDO:
          se valida coherencia
        
        ENTONCES:
          debe retornar OK (tratadas como vacías)
        """
        # Act
        resultado = validator.validar_coherencia_articulos(
            codigos_detalle=None,
            codigos_movimiento=None
        )
        
        # Assert
        assert resultado["coherente"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
