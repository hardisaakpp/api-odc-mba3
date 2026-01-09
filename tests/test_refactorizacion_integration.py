"""
Test rápido de integración para verificar la refactorización de pedido_validator.py
"""
import sys
sys.path.insert(0, '.')

from src.database.services.pedido_validator import PedidoValidator, ValidationIssue, ValidationSeverity

def test_basico():
    """Test básico de funcionalidad."""
    print("\n🧪 Ejecutando test de integración básico...")

    # Crear validador
    validator = PedidoValidator(
        tiendas_permitidas=['T001', 'T002'],
        validar_precios=True,
        iva_porcentaje=15.0
    )

    # Test 1: Validar cabecera válida
    print("\n[1/4] Test validar_cabecera con datos válidos...")
    cabecera_valida = {
        "numero_pedido": "PED-001",
        "fecha_pedido": "2026-01-08",
        "fecha_entrega": "2026-01-15"
    }
    issues = validator.validar_cabecera(cabecera_valida, row_number=1)
    assert len(issues) == 0, f"No debería haber issues, pero se encontraron: {issues}"
    print("   ✅ PASS - Cabecera válida sin issues")

    # Test 2: Validar cabecera inválida (sin número de pedido)
    print("\n[2/4] Test validar_cabecera con datos inválidos...")
    cabecera_invalida = {
        "numero_pedido": "",
        "fecha_pedido": "2026-01-08"
    }
    issues = validator.validar_cabecera(cabecera_invalida, row_number=1)
    assert len(issues) > 0, "Debería haber issues por número de pedido vacío"
    assert any(i.field == "numero_pedido" for i in issues), "Debería haber issue en numero_pedido"
    assert any(i.severity == ValidationSeverity.ERROR for i in issues), "Debería haber un ERROR"
    print(f"   ✅ PASS - Detectó {len(issues)} issue(s) correctamente")

    # Test 3: Validar detalle con precios
    print("\n[3/4] Test validar_detalle con precios...")
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
    issues = validator.validar_detalle(detalle, distribuciones, row_number=2)
    # Puede haber warnings pero no debería haber errores críticos
    errores = [i for i in issues if i.severity == ValidationSeverity.ERROR]
    assert len(errores) == 0, f"No debería haber errores, pero se encontraron: {errores}"
    print(f"   ✅ PASS - Detalle validado correctamente ({len(issues)} issue(s) total)")

    # Test 4: Validar que ValidationIssue funciona
    print("\n[4/4] Test crear ValidationIssue manualmente...")
    issue = ValidationIssue(
        row_number=1,
        field="test_field",
        severity=ValidationSeverity.WARNING,
        message="Test message",
        value="test_value"
    )
    assert issue.row_number == 1
    assert issue.field == "test_field"
    assert issue.severity == ValidationSeverity.WARNING
    assert issue.message == "Test message"
    assert issue.value == "test_value"
    print("   ✅ PASS - ValidationIssue funciona correctamente")

    print("\n" + "="*70)
    print("✅ TODOS LOS TESTS PASARON")
    print("="*70)
    print("\n🎉 La refactorización está funcionando correctamente!")
    return True

if __name__ == "__main__":
    try:
        success = test_basico()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST FALLÓ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

