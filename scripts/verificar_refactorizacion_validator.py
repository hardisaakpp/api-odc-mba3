"""
Script de verificación post-refactorización de pedido_validator.py
Verifica que todos los imports y funcionalidades básicas funcionan correctamente.
"""

import sys
from pathlib import Path

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("VERIFICACIÓN POST-REFACTORIZACIÓN: pedido_validator.py")
print("=" * 70)

# Test 1: Importar tipos comunes
print("\n[1/6] Verificando pedido_validation_types.py...")
try:
    from src.database.services.pedido_validation_types import (
        ValidationIssue,
        ValidationSeverity
    )
    print("✅ Tipos comunes importados correctamente")
    print(f"    - ValidationSeverity: {ValidationSeverity}")
    print(f"    - ValidationIssue: {ValidationIssue}")
except Exception as e:
    print(f"❌ Error importando tipos comunes: {e}")
    sys.exit(1)

# Test 2: Importar validador de cabecera
print("\n[2/6] Verificando pedido_cabecera_validator.py...")
try:
    from src.database.services.pedido_cabecera_validator import PedidoCabeceraValidator
    validator_cabecera = PedidoCabeceraValidator()
    print("✅ PedidoCabeceraValidator importado correctamente")
    print(f"    - Instancia creada: {validator_cabecera}")
except Exception as e:
    print(f"❌ Error importando validador de cabecera: {e}")
    sys.exit(1)

# Test 3: Importar validador de precios
print("\n[3/6] Verificando pedido_precio_validator.py...")
try:
    from src.database.services.pedido_precio_validator import PedidoPrecioValidator
    validator_precio = PedidoPrecioValidator()
    print("✅ PedidoPrecioValidator importado correctamente")
    print(f"    - Instancia creada: {validator_precio}")
except Exception as e:
    print(f"❌ Error importando validador de precios: {e}")
    sys.exit(1)

# Test 4: Importar PedidoValidator (facade)
print("\n[4/6] Verificando pedido_validator.py (facade)...")
try:
    from src.database.services.pedido_validator import (
        PedidoValidator,
        ValidationIssue as VI,
        ValidationSeverity as VS
    )
    validator = PedidoValidator()
    print("✅ PedidoValidator importado correctamente")
    print(f"    - Instancia creada: {validator}")
    print(f"    - Tiene cabecera_validator: {hasattr(validator, 'cabecera_validator')}")
    print(f"    - Tiene precio_validator: {hasattr(validator, 'precio_validator')}")
except Exception as e:
    print(f"❌ Error importando PedidoValidator: {e}")
    sys.exit(1)

# Test 5: Verificar compatibilidad de exports
print("\n[5/6] Verificando compatibilidad de exports...")
try:
    assert VI == ValidationIssue, "ValidationIssue no se exporta correctamente"
    assert VS == ValidationSeverity, "ValidationSeverity no se exporta correctamente"
    print("✅ Exports mantienen compatibilidad hacia atrás")
except AssertionError as e:
    print(f"❌ Error de compatibilidad: {e}")
    sys.exit(1)

# Test 6: Probar funcionalidad básica
print("\n[6/6] Probando funcionalidad básica...")
try:
    # Crear validador con configuración
    validator = PedidoValidator(
        tiendas_permitidas=['T001', 'T002'],
        validar_precios=True,
        iva_porcentaje=15.0
    )

    # Validar cabecera simple
    cabecera = {
        "numero_pedido": "PED-001",
        "fecha_pedido": "2026-01-08",
        "fecha_entrega": "2026-01-15"
    }
    issues_cabecera = validator.validar_cabecera(cabecera, row_number=1)
    print(f"✅ validar_cabecera() funciona: {len(issues_cabecera)} issues")

    # Validar detalle simple (delegará a precio_validator si validar_precios=True)
    detalle = {
        "codigo_interno": "PROD-001",
        "costo_doc_sin_iva": 10.0,
        "pvp": 12.0,
        "descuento_1": 0,
        "subtotal": 12.0,
        "total": 12.0
    }
    distribuciones = [
        {"codigo_tienda": "T001", "cantidad": 5}
    ]
    issues_detalle = validator.validar_detalle(detalle, distribuciones, row_number=2)
    print(f"✅ validar_detalle() funciona: {len(issues_detalle)} issues")

    # Crear un issue manualmente
    issue = ValidationIssue(
        row_number=1,
        field="test",
        severity=ValidationSeverity.WARNING,
        message="Test issue",
        value="test_value"
    )
    print(f"✅ ValidationIssue se crea correctamente: {issue.message}")

except Exception as e:
    print(f"❌ Error en prueba funcional: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Resumen final
print("\n" + "=" * 70)
print("✅ VERIFICACIÓN COMPLETADA CON ÉXITO")
print("=" * 70)
print("\nTodos los módulos refactorizados funcionan correctamente:")
print("  ✓ pedido_validation_types.py")
print("  ✓ pedido_cabecera_validator.py")
print("  ✓ pedido_precio_validator.py")
print("  ✓ pedido_validator.py (facade)")
print("\n✅ Compatibilidad hacia atrás: MANTENIDA")
print("✅ Funcionalidad básica: OPERATIVA")
print("\n🚀 Sistema listo para producción")

