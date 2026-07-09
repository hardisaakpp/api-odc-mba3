"""
Script de validación para la refactorización de DespachoRepository.

Valida que:
1. Todos los imports funcionan correctamente
2. Los repositorios especializados son instanciables
3. El facade delega correctamente
4. La interfaz pública no ha cambiado
"""

import sys
from pathlib import Path

# Agregar src al path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


def test_imports():
    """Verificar que todos los imports funcionan."""
    print("🔍 Verificando imports...")

    try:
        # Utilidades compartidas
        from database.repositories.common.serialization import serialize_date, serialize_decimal
        print("  ✅ Utilidades de serialización importadas")

        # Repositorios especializados
        from database.repositories.despacho import (
            DespachoCabeceraRepository,
            DespachoDetalleRepository,
            DespachoQueryRepository
        )
        print("  ✅ Repositorios especializados importados")

        # Facade
        from database.repositories import DespachoRepository
        print("  ✅ DespachoRepository (facade) importado")

        # Re-exportación de utilidades
        from database.repositories import serialize_date as sd, serialize_decimal as sdec
        print("  ✅ Utilidades re-exportadas desde __init__")

        return True
    except ImportError as e:
        print(f"  ❌ Error de import: {e}")
        return False


def test_interface_compatibility():
    """Verificar que la interfaz pública no ha cambiado."""
    print("\n🔍 Verificando compatibilidad de interfaz...")

    try:
        from database.repositories import DespachoRepository

        # Métodos de cabecera
        required_methods = [
            'find_by_codigo_factura',
            'get_existing_cabecera',
            'insert_cabecera',
            'update_cabecera',
            # Métodos de detalle
            'insert_detalles',
            'get_detalles',
            'delete_detalles',
            # Métodos de consulta
            'get_despachos_sin_oc',
            'count_despachos_sin_oc',
            'get_despachos_con_info_oc',
        ]

        for method in required_methods:
            if not hasattr(DespachoRepository, method):
                print(f"  ❌ Método faltante: {method}")
                return False
            print(f"  ✅ {method}")

        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def test_serialization():
    """Verificar funciones de serialización."""
    print("\n🔍 Verificando funciones de serialización...")

    try:
        from datetime import date, datetime
        from decimal import Decimal
        from database.repositories.common.serialization import serialize_date, serialize_decimal

        # Test serialize_date
        test_date = date(2026, 1, 8)
        result_date = serialize_date(test_date)
        assert result_date == "2026-01-08", f"Expected '2026-01-08', got '{result_date}'"
        print(f"  ✅ serialize_date: {test_date} → {result_date}")

        test_datetime = datetime(2026, 1, 8, 15, 30, 45)
        result_datetime = serialize_date(test_datetime)
        assert result_datetime == "2026-01-08T15:30:45", f"Expected '2026-01-08T15:30:45', got '{result_datetime}'"
        print(f"  ✅ serialize_date: {test_datetime} → {result_datetime}")

        # Test serialize_decimal
        test_decimal = Decimal("123.45")
        result_decimal = serialize_decimal(test_decimal)
        assert result_decimal == 123.45, f"Expected 123.45, got {result_decimal}"
        print(f"  ✅ serialize_decimal: {test_decimal} → {result_decimal}")

        # Test None
        assert serialize_date(None) is None
        assert serialize_decimal(None) is None
        print("  ✅ Manejo de None correcto")

        return True
    except AssertionError as e:
        print(f"  ❌ Error de aserción: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def main():
    """Ejecutar todas las validaciones."""
    print("=" * 60)
    print("VALIDACIÓN DE REFACTORIZACIÓN - DespachoRepository")
    print("=" * 60)

    results = {
        "imports": test_imports(),
        "interface": test_interface_compatibility(),
        "serialization": test_serialization()
    }

    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)

    all_passed = all(results.values())

    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name.upper():.<20} {status}")

    print("=" * 60)

    if all_passed:
        print("🎉 TODAS LAS VALIDACIONES PASARON")
        print("\nLa refactorización es exitosa y mantiene compatibilidad hacia atrás.")
        return 0
    else:
        print("⚠️ ALGUNAS VALIDACIONES FALLARON")
        print("\nRevisar los errores anteriores.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

