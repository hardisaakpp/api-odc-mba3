"""
Script de prueba para verificar las conversiones de unidades.

Este script simula el proceso de conversión que ocurre al guardar facturas.
"""

import sys
from pathlib import Path

# Agregar src al path para importar módulos
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

import logging
from database.services.sap_service import SAPService
from database.mappers.factura_mapper import FacturaMapper

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_conversion(sku: str = "5-0012.9", cantidad: float = 456, total_linea: float = 2120.4):
    """
    Prueba la conversión de unidades para un SKU.
    
    Args:
        sku: SKU del producto
        cantidad: Cantidad en docenas (de El Rayo)
        total_linea: Total de la línea
    """
    print()
    print("=" * 70)
    print("🔍 PRUEBA DE CONVERSIÓN DE UNIDADES")
    print("=" * 70)
    print()
    
    print(f"📋 Datos de entrada:")
    print(f"   SKU: {sku}")
    print(f"   Cantidad (docenas): {cantidad}")
    print(f"   Total línea: {total_linea}")
    print()
    
    # Paso 1: Obtener información SAP
    print("🔍 Paso 1: Consultando información SAP...")
    sap_service = SAPService()
    sap_info = sap_service.get_or_fetch_producto_info(sku)
    
    if not sap_info:
        print("❌ No se pudo obtener información SAP")
        return False
    
    print("✅ Información SAP obtenida:")
    print(f"   Pack SAP: {sap_info.get('pack_sap')}")
    print(f"   Unidad de conversión: {sap_info.get('unidad_conversion')}")
    print()
    
    # Paso 2: Simular línea de factura
    print("🔍 Paso 2: Simulando línea de factura MBA3...")
    linea_mba3 = {
        "Codigo": sku,
        "Cantidad": cantidad,
        "TotalLinea": total_linea,
        "PrecioUnitario": total_linea / cantidad if cantidad > 0 else 0,
        "Nombre": "Producto de prueba",
        "Descuento": 0,
        "Impuesto": None,
        "RegNum": None
    }
    
    print("✅ Línea MBA3 simulada:")
    print(f"   Código: {linea_mba3['Codigo']}")
    print(f"   Cantidad: {linea_mba3['Cantidad']} docenas")
    print(f"   Precio unitario: {linea_mba3['PrecioUnitario']:.4f} (por docena)")
    print(f"   Total línea: {linea_mba3['TotalLinea']:.2f}")
    print()
    
    # Paso 3: Convertir usando el mapper
    print("🔍 Paso 3: Aplicando conversión...")
    detalle_convertido = FacturaMapper.to_despacho_detalle(
        linea_mba3, 
        tipo_linea="GrabarLineasProd",
        sap_info=sap_info
    )
    
    if not detalle_convertido:
        print("❌ No se pudo convertir la línea")
        return False
    
    print("✅ Conversión completada!")
    print()
    
    # Paso 4: Mostrar resultados
    print("=" * 70)
    print("📊 RESULTADOS DE LA CONVERSIÓN")
    print("=" * 70)
    print()
    
    print("📦 Datos Originales (El Rayo - Docenas):")
    print(f"   Cantidad: {detalle_convertido['cantidad']} docenas")
    print(f"   Precio unitario: {detalle_convertido['precio_unitario']:.4f} por docena")
    print(f"   Total línea: {detalle_convertido['total_linea']:.2f}")
    print()
    
    if detalle_convertido.get('cantidad_sap'):
        print("📦 Datos Convertidos (Mabel - Packs):")
        print(f"   Cantidad: {detalle_convertido['cantidad_sap']:.2f} packs")
        print(f"   Unidad SAP: {detalle_convertido['unidad_sap']}")
        print(f"   Precio unitario: {detalle_convertido['precio_unitario_sap']:.4f} por pack")
        print()
        
        # Verificar cálculos
        print("🔍 Verificación de Cálculos:")
        unidad_conversion = sap_info.get('unidad_conversion')
        if unidad_conversion is None:
            print("   ⚠️ No se pudo obtener unidad_conversion, saltando verificación de cálculos")
            return
        
        cantidad_esperada = cantidad * unidad_conversion
        precio_esperado = total_linea / cantidad_esperada if cantidad_esperada > 0 else 0
        
        print(f"   Cantidad SAP esperada: {cantidad} × {unidad_conversion} = {cantidad_esperada:.2f}")
        print(f"   Cantidad SAP obtenida: {detalle_convertido['cantidad_sap']:.2f}")
        print(f"   ✅ {'CORRECTO' if abs(detalle_convertido['cantidad_sap'] - cantidad_esperada) < 0.01 else 'ERROR'}")
        print()
        
        print(f"   Precio unitario SAP esperado: {total_linea:.2f} / {cantidad_esperada:.2f} = {precio_esperado:.4f}")
        print(f"   Precio unitario SAP obtenido: {detalle_convertido['precio_unitario_sap']:.4f}")
        print(f"   ✅ {'CORRECTO' if abs(detalle_convertido['precio_unitario_sap'] - precio_esperado) < 0.0001 else 'ERROR'}")
        print()
        
        return True
    else:
        print("⚠️ No se realizó conversión (no hay información SAP o cantidad es 0)")
        return False


def main():
    """Función principal."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Prueba conversión de unidades")
    parser.add_argument(
        "--sku",
        type=str,
        default="5-0012.9",
        help="SKU del producto a probar (default: 5-0012.9)"
    )
    parser.add_argument(
        "--cantidad",
        type=float,
        default=456.0,
        help="Cantidad en docenas (default: 456.0)"
    )
    parser.add_argument(
        "--total",
        type=float,
        default=2120.4,
        help="Total de la línea (default: 2120.4)"
    )
    
    args = parser.parse_args()
    
    print()
    print("🚀 INICIANDO PRUEBA DE CONVERSIÓN")
    print("=" * 70)
    
    resultado = test_conversion(
        sku=args.sku,
        cantidad=args.cantidad,
        total_linea=args.total
    )
    
    print("=" * 70)
    if resultado:
        print("✅ Prueba de conversión completada exitosamente!")
    else:
        print("❌ La prueba de conversión falló")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()

