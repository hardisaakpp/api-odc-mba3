"""
Tests para validación de tiendas contra maestro.

FASE 1: Validación de tiendas (NUEVO)
- TEST 1: Tienda no declarada en catálogo
- TEST 2: Tienda inactiva no puede usarse
- TEST 3: Normalización de espacios y mayúsculas
"""

import pytest
import logging
from io import BytesIO

from src.database.services.pedido_parser import PedidoParser
from src.database.services.pedido_validator import PedidoValidator

logger = logging.getLogger(__name__)


class TestValidacionTiendas:
    """Tests para validación de tiendas contra maestro."""
    
    @pytest.fixture
    def parser(self):
        """Instancia del parser."""
        return PedidoParser()
    
    @pytest.fixture
    def validator(self):
        """Instancia del validador."""
        return PedidoValidator()
    
    def test_tienda_no_declarada_genera_error(self, validator):
        """
        ✅ TEST 1: Tienda no declarada en catálogo
        
        DADO:
          - Hoja Tiendas: [TRL-QSN, TRL-CCI]
          - Movimiento usa: TRL-NUEVO (no declarada)
        
        CUANDO:
          se valida contra catálogo
        
        ENTONCES:
          debe retornar ERROR con mensaje claro
        """
        # Arrange
        catalogo_tiendas = {
            "TRL-QSN": {
                "codigo": "TRL-QSN",
                "nombre": "ROLAND QUICENTRO NORTE",
                "activa": True,
                "codigo_original": "TRL-QSN",
                "fila_origen": 2
            },
            "TRL-CCI": {
                "codigo": "TRL-CCI",
                "nombre": "ROLAND CCI",
                "activa": True,
                "codigo_original": "TRL-CCI",
                "fila_origen": 3
            }
        }
        
        tiendas_movimiento = ["TRL-QSN", "TRL-NUEVO"]
        
        # Act
        resultado = validator.validar_tiendas_contra_catalogo(
            tiendas_movimiento=tiendas_movimiento,
            catalogo_tiendas=catalogo_tiendas
        )
        
        # Assert
        assert resultado["valido"] is False, "Validación debe fallar"
        assert "TRL-NUEVO" in resultado["tiendas_no_encontradas"], "Debe detectar tienda no encontrada"
        assert len(resultado["errores"]) > 0, "Debe haber errores"
        assert "TRL-QSN" in resultado["tiendas_validas"], "TRL-QSN debe ser válida"
        
        # Verificar mensaje de error
        error = resultado["errores"][0]
        assert error["tipo"] == "ERROR"
        assert "TRL-NUEVO" in error["mensaje"]
        assert "no está declarada" in error["mensaje"].lower()
        assert "accion_recomendada" in error
        
        logger.info("✅ TEST 1 PASÓ: Tienda no declarada genera error correcto")
    
    def test_tienda_inactiva_genera_error(self, validator):
        """
        ✅ TEST 2: Tienda inactiva no puede usarse
        
        DADO:
          - Hoja Tiendas: TRL-OLD (Activa=NO)
          - Movimiento usa: TRL-OLD
        
        CUANDO:
          se valida contra catálogo
        
        ENTONCES:
          debe retornar ERROR "Tienda inactiva"
        """
        # Arrange
        catalogo_tiendas = {
            "TRL-QSN": {
                "codigo": "TRL-QSN",
                "nombre": "ROLAND QUICENTRO NORTE",
                "activa": True,
                "codigo_original": "TRL-QSN",
                "fila_origen": 2
            },
            "TRL-OLD": {
                "codigo": "TRL-OLD",
                "nombre": "ROLAND OLD (CERRADA)",
                "activa": False,  # ⚠️ INACTIVA
                "codigo_original": "TRL-OLD",
                "fila_origen": 3
            }
        }
        
        tiendas_movimiento = ["TRL-QSN", "TRL-OLD"]
        
        # Act
        resultado = validator.validar_tiendas_contra_catalogo(
            tiendas_movimiento=tiendas_movimiento,
            catalogo_tiendas=catalogo_tiendas
        )
        
        # Assert
        assert resultado["valido"] is False, "Validación debe fallar"
        assert "TRL-OLD" in resultado["tiendas_inactivas"], "Debe detectar tienda inactiva"
        assert "TRL-QSN" in resultado["tiendas_validas"], "TRL-QSN debe ser válida"
        assert len(resultado["errores"]) > 0, "Debe haber errores"
        
        # Verificar mensaje de error
        error = [e for e in resultado["errores"] if e["valor"] == "TRL-OLD"][0]
        assert error["tipo"] == "ERROR"
        assert "inactiva" in error["mensaje"].lower()
        assert "accion_recomendada" in error
        
        logger.info("✅ TEST 2 PASÓ: Tienda inactiva genera error correcto")
    
    def test_normalizacion_espacios_y_mayusculas(self, validator):
        """
        ✅ TEST 3: Normalización de espacios y mayúsculas (CRÍTICO)
        
        DADO:
          - Catálogo: "TRL-QSN"
          - Movimiento: "  trl-qsn  " (con espacios y minúsculas)
        
        CUANDO:
          se valida
        
        ENTONCES:
          debe coincidir (sin falsos errores)
        """
        # Arrange
        catalogo_tiendas = {
            "TRL-QSN": {
                "codigo": "TRL-QSN",
                "nombre": "ROLAND QUICENTRO",
                "activa": True,
                "codigo_original": "TRL-QSN",
                "fila_origen": 2
            }
        }
        
        # Input SIN normalizar (como vendría del Excel)
        tiendas_movimiento = ["  TRL-qsn  ", "trl-qsn"]
        
        # Act
        resultado = validator.validar_tiendas_contra_catalogo(
            tiendas_movimiento=tiendas_movimiento,
            catalogo_tiendas=catalogo_tiendas
        )
        
        # Assert
        assert resultado["valido"] is True, "Debe pasar (sin falsos errores de espacios/mayúsculas)"
        assert "TRL-QSN" in resultado["tiendas_validas"]
        assert len(resultado["tiendas_no_encontradas"]) == 0, "No debe haber tiendas no encontradas"
        assert len(resultado["tiendas_inactivas"]) == 0, "No debe haber tiendas inactivas"
        
        logger.info("✅ TEST 3 PASÓ: Normalización funciona correctamente")
    
    def test_mapeo_a_filas_tiendas_invalidas(self, validator):
        """
        ✅ TEST 4: Mapeo de errores a números de fila
        
        DADO:
          - Tienda TRL-NUEVO usada en filas 5 y 7
          - Tienda TRL-OLD (inactiva) usada en filas 6 y 8
        
        CUANDO:
          se valida con mapeo de filas
        
        ENTONCES:
          los errores deben incluir número de fila
        """
        # Arrange
        catalogo_tiendas = {
            "TRL-QSN": {
                "codigo": "TRL-QSN",
                "nombre": "ROLAND QUICENTRO",
                "activa": True,
                "codigo_original": "TRL-QSN",
                "fila_origen": 2
            },
            "TRL-OLD": {
                "codigo": "TRL-OLD",
                "nombre": "ROLAND OLD",
                "activa": False,
                "codigo_original": "TRL-OLD",
                "fila_origen": 3
            }
        }
        
        tiendas_movimiento = ["TRL-NUEVO", "TRL-OLD"]
        
        # Mapeo de tiendas a filas donde aparecen
        mapear_a_filas = {
            "TRL-NUEVO": [5, 7],
            "TRL-OLD": [6, 8]
        }
        
        # Act
        resultado = validator.validar_tiendas_contra_catalogo(
            tiendas_movimiento=tiendas_movimiento,
            catalogo_tiendas=catalogo_tiendas,
            mapear_a_filas=mapear_a_filas
        )
        
        # Assert
        assert resultado["valido"] is False
        assert len(resultado["errores"]) == 4, "Debe haber 4 errores (2 de TRL-NUEVO + 2 de TRL-OLD)"
        
        # Verificar que los errores tienen número de fila
        filas_errores = [e.get("fila") for e in resultado["errores"]]
        assert 5 in filas_errores, "Debe haber error en fila 5"
        assert 7 in filas_errores, "Debe haber error en fila 7"
        assert 6 in filas_errores, "Debe haber error en fila 6"
        assert 8 in filas_errores, "Debe haber error en fila 8"
        
        logger.info("✅ TEST 4 PASÓ: Mapeo a filas funciona correctamente")
    
    def test_todas_tiendas_validas(self, validator):
        """
        ✅ TEST 5: Caso exitoso - todas las tiendas son válidas
        
        DADO:
          - Catálogo: [TRL-QSN, TRL-CCI]
          - Movimiento usa: [TRL-QSN, TRL-CCI]
        
        CUANDO:
          se valida
        
        ENTONCES:
          debe retornar valido=true
        """
        # Arrange
        catalogo_tiendas = {
            "TRL-QSN": {
                "codigo": "TRL-QSN",
                "nombre": "ROLAND QUICENTRO NORTE",
                "activa": True,
                "codigo_original": "TRL-QSN",
                "fila_origen": 2
            },
            "TRL-CCI": {
                "codigo": "TRL-CCI",
                "nombre": "ROLAND CCI",
                "activa": True,
                "codigo_original": "TRL-CCI",
                "fila_origen": 3
            }
        }
        
        tiendas_movimiento = ["TRL-QSN", "TRL-CCI", "TRL-QSN"]  # Incluso con repetidas
        
        # Act
        resultado = validator.validar_tiendas_contra_catalogo(
            tiendas_movimiento=tiendas_movimiento,
            catalogo_tiendas=catalogo_tiendas
        )
        
        # Assert
        assert resultado["valido"] is True, "Validación debe pasar"
        assert len(resultado["tiendas_validas"]) == 2, "Debe reconocer 2 tiendas únicas"
        assert len(resultado["tiendas_no_encontradas"]) == 0
        assert len(resultado["tiendas_inactivas"]) == 0
        assert len(resultado["errores"]) == 0
        
        logger.info("✅ TEST 5 PASÓ: Validación exitosa para tiendas válidas")
    
    def test_catalogo_vacio(self, validator):
        """
        ✅ TEST 6: Catálogo vacío - rechaza todas las tiendas
        
        DADO:
          - Catálogo: {} (vacío)
          - Movimiento usa: [TRL-QSN]
        
        CUANDO:
          se valida
        
        ENTONCES:
          debe rechazar todas las tiendas
        """
        # Arrange
        catalogo_tiendas = {}
        tiendas_movimiento = ["TRL-QSN"]
        
        # Act
        resultado = validator.validar_tiendas_contra_catalogo(
            tiendas_movimiento=tiendas_movimiento,
            catalogo_tiendas=catalogo_tiendas
        )
        
        # Assert
        assert resultado["valido"] is False
        assert "TRL-QSN" in resultado["tiendas_no_encontradas"]
        assert len(resultado["errores"]) > 0
        
        logger.info("✅ TEST 6 PASÓ: Catálogo vacío rechaza tiendas correctamente")
    
    def test_tiendas_vacio(self, validator):
        """
        ✅ TEST 7: Movimiento sin tiendas (válido)
        
        DADO:
          - Catálogo: [TRL-QSN]
          - Movimiento usa: [] (vacío)
        
        CUANDO:
          se valida
        
        ENTONCES:
          debe retornar valido=true (sin tiendas a validar)
        """
        # Arrange
        catalogo_tiendas = {
            "TRL-QSN": {
                "codigo": "TRL-QSN",
                "nombre": "ROLAND QUICENTRO",
                "activa": True,
                "codigo_original": "TRL-QSN",
                "fila_origen": 2
            }
        }
        tiendas_movimiento = []
        
        # Act
        resultado = validator.validar_tiendas_contra_catalogo(
            tiendas_movimiento=tiendas_movimiento,
            catalogo_tiendas=catalogo_tiendas
        )
        
        # Assert
        assert resultado["valido"] is True, "Debe ser válido sin tiendas a validar"
        assert len(resultado["tiendas_validas"]) == 0
        assert len(resultado["errores"]) == 0
        
        logger.info("✅ TEST 7 PASÓ: Movimiento sin tiendas es válido")


if __name__ == "__main__":
    # Ejecutar tests con pytest
    pytest.main([__file__, "-v"])
