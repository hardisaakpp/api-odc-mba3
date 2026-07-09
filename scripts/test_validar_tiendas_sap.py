"""
Script de prueba para validar tiendas contra SAP
"""

import sys
import logging
from typing import List, Dict, Any

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Agregar ruta del proyecto
sys.path.insert(0, 'c:\\Users\\cortiz\\PycharmProjects\\mba3-consultas')

from src.database.services.pedido_validator import PedidoValidator

def test_validar_tiendas_contra_sap():
    """
    Test básico para validar tiendas contra SAP OWHS
    """
    logger.info("=" * 80)
    logger.info("TEST: Validar Tiendas contra SAP")
    logger.info("=" * 80)
    
    validator = PedidoValidator()
    
    # TEST 1: Tiendas válidas
    logger.info("\n📋 TEST 1: Validar tiendas VÁLIDAS")
    logger.info("-" * 80)
    
    tiendas_validas = ["ROL01", "ROL02", "ROL03"]
    resultado = validator.validar_tiendas_existen_en_sap(
        codigos_tiendas=tiendas_validas,
        sap_obligatorio=True
    )
    
    logger.info(f"Tiendas a validar: {tiendas_validas}")
    logger.info(f"Resultado:")
    logger.info(f"  - Válidas: {len(resultado['validas'])} - {resultado['validas']}")
    logger.info(f"  - No encontradas: {len(resultado['no_encontradas'])} - {resultado['no_encontradas']}")
    logger.info(f"  - Errores: {len(resultado['errores'])} - {resultado['errores']}")
    logger.info(f"  - Todas válidas: {resultado['todas_validas']}")
    
    assert resultado['todas_validas'] == True, "Las tiendas válidas deben pasar"
    assert len(resultado['validas']) == 3, "Deben haber 3 tiendas válidas"
    assert len(resultado['no_encontradas']) == 0, "No debe haber no encontradas"
    logger.info("✅ TEST 1 PASÓ\n")
    
    # TEST 2: Tiendas inválidas
    logger.info("📋 TEST 2: Validar tiendas INVÁLIDAS")
    logger.info("-" * 80)
    
    tiendas_invalidas = ["ROL99", "ROL98"]
    resultado = validator.validar_tiendas_existen_en_sap(
        codigos_tiendas=tiendas_invalidas,
        sap_obligatorio=True
    )
    
    logger.info(f"Tiendas a validar: {tiendas_invalidas}")
    logger.info(f"Resultado:")
    logger.info(f"  - Válidas: {len(resultado['validas'])} - {resultado['validas']}")
    logger.info(f"  - No encontradas: {len(resultado['no_encontradas'])} - {resultado['no_encontradas']}")
    logger.info(f"  - Errores: {len(resultado['errores'])} - {resultado['errores']}")
    logger.info(f"  - Todas válidas: {resultado['todas_validas']}")
    
    assert resultado['todas_validas'] == False, "Las tiendas inválidas deben fallar"
    assert len(resultado['no_encontradas']) == 2, "Deben haber 2 no encontradas"
    logger.info("✅ TEST 2 PASÓ\n")
    
    # TEST 3: Mezcla de válidas e inválidas
    logger.info("📋 TEST 3: Validar MEZCLA de válidas e inválidas")
    logger.info("-" * 80)
    
    tiendas_mixtas = ["ROL01", "ROL99", "ROL02", "ROL98"]
    resultado = validator.validar_tiendas_existen_en_sap(
        codigos_tiendas=tiendas_mixtas,
        sap_obligatorio=True
    )
    
    logger.info(f"Tiendas a validar: {tiendas_mixtas}")
    logger.info(f"Resultado:")
    logger.info(f"  - Válidas: {len(resultado['validas'])} - {resultado['validas']}")
    logger.info(f"  - No encontradas: {len(resultado['no_encontradas'])} - {resultado['no_encontradas']}")
    logger.info(f"  - Errores: {len(resultado['errores'])} - {resultado['errores']}")
    logger.info(f"  - Todas válidas: {resultado['todas_validas']}")
    
    assert resultado['todas_validas'] == False, "Debe fallar si hay alguna inválida"
    assert len(resultado['validas']) == 2, "Deben haber 2 válidas"
    assert len(resultado['no_encontradas']) == 2, "Deben haber 2 no encontradas"
    logger.info("✅ TEST 3 PASÓ\n")
    
    # TEST 4: Normalización de mayúsculas
    logger.info("📋 TEST 4: Validar NORMALIZACIÓN de mayúsculas")
    logger.info("-" * 80)
    
    tiendas_minusculas = ["rol01", "rol02", "rol03"]
    resultado = validator.validar_tiendas_existen_en_sap(
        codigos_tiendas=tiendas_minusculas,
        sap_obligatorio=True
    )
    
    logger.info(f"Tiendas a validar (minúsculas): {tiendas_minusculas}")
    logger.info(f"Resultado:")
    logger.info(f"  - Válidas: {len(resultado['validas'])} - {resultado['validas']}")
    logger.info(f"  - Todas válidas: {resultado['todas_validas']}")
    
    assert resultado['todas_validas'] == True, "Debe normalizar y encontrar tiendas"
    assert len(resultado['validas']) == 3, "Debe encontrar 3 tiendas después de normalizar"
    logger.info("✅ TEST 4 PASÓ\n")
    
    # TEST 5: Estructura detallada
    logger.info("📋 TEST 5: Validar ESTRUCTURA detallada de respuesta")
    logger.info("-" * 80)
    
    tiendas = ["ROL01"]
    resultado = validator.validar_tiendas_existen_en_sap(
        codigos_tiendas=tiendas,
        sap_obligatorio=True
    )
    
    logger.info("Estructura del resultado:")
    logger.info(f"  - detalle['ROL01']: {resultado['detalle'].get('ROL01', {})}")
    
    detalle_rol01 = resultado['detalle'].get('ROL01', {})
    assert 'existe' in detalle_rol01, "Debe tener campo 'existe'"
    assert 'info' in detalle_rol01, "Debe tener campo 'info'"
    assert 'severity' in detalle_rol01, "Debe tener campo 'severity'"
    
    if detalle_rol01.get('existe'):
        info = detalle_rol01.get('info', {})
        assert 'codigo' in info, "Info debe tener 'codigo'"
        assert 'nombre' in info, "Info debe tener 'nombre'"
        logger.info(f"    ✓ Tienda: {info.get('codigo')} - {info.get('nombre')}")
    
    logger.info("✅ TEST 5 PASÓ\n")
    
    logger.info("=" * 80)
    logger.info("✅ TODOS LOS TESTS PASARON EXITOSAMENTE")
    logger.info("=" * 80)

if __name__ == "__main__":
    try:
        test_validar_tiendas_contra_sap()
    except AssertionError as e:
        logger.error(f"❌ TEST FALLÓ: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ ERROR: {e}", exc_info=True)
        sys.exit(1)
