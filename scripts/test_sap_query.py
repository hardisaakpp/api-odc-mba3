"""
Script de prueba para verificar la consulta a SAP.

Este script prueba la conexión y consulta a SAP usando OPENQUERY.

Uso:
    python scripts/test_sap_query.py
    python scripts/test_sap_query.py --sku "5-0012.9"
"""

import sys
import os
from pathlib import Path

# Agregar src al path para importar módulos
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

import logging
from database.clients.sap_client import SAPClient
from database.services.sap_service import SAPService
from database.repositories.producto_sap_repository import ProductoSAPRepository
from database.connection import get_db_connection
from config import ENABLE_SAP_QUERIES, SAP_LINKED_SERVER

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_sap_client_direct(sku: str = "5-0012.9"):
    """
    Prueba directa del cliente SAP.
    
    Args:
        sku: SKU del producto a consultar
    """
    print("=" * 70)
    print("🔍 PRUEBA 1: Cliente SAP Directo")
    print("=" * 70)
    
    if not ENABLE_SAP_QUERIES:
        print("❌ ERROR: Consultas SAP están deshabilitadas")
        print("   Configura ENABLE_SAP_QUERIES=true en .env")
        return False
    
    print(f"📋 Configuración:")
    print(f"   Servidor vinculado: {SAP_LINKED_SERVER}")
    print(f"   SKU a consultar: {sku}")
    print()
    
    try:
        client = SAPClient()
        print("✅ Cliente SAP inicializado")
        print()
        
        print(f"🔍 Consultando SAP para SKU: {sku}...")
        resultado = client.get_producto_info(sku)
        
        if resultado:
            print("✅ Consulta exitosa!")
            print()
            print("📊 Resultado:")
            print(f"   ItemCode: {resultado.get('ItemCode')}")
            print(f"   ItemName: {resultado.get('ItemName')}")
            print(f"   U_IXX_PACK: {resultado.get('U_IXX_PACK')}")
            return True
        else:
            print("⚠️ No se encontró información en SAP para este SKU")
            return False
            
    except Exception as e:
        print(f"❌ Error al consultar SAP: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sap_service_with_cache(sku: str = "5-0012.9"):
    """
    Prueba del servicio SAP con cache.
    
    Args:
        sku: SKU del producto a consultar
    """
    print()
    print("=" * 70)
    print("🔍 PRUEBA 2: Servicio SAP con Cache")
    print("=" * 70)
    
    if not ENABLE_SAP_QUERIES:
        print("❌ ERROR: Consultas SAP están deshabilitadas")
        return False
    
    try:
        service = SAPService()
        print("✅ Servicio SAP inicializado")
        print()
        
        print(f"🔍 Obteniendo información para SKU: {sku}...")
        print("   (Consultará SAP o usará cache si está disponible)")
        print()
        
        producto_info = service.get_or_fetch_producto_info(sku)
        
        if producto_info:
            print("✅ Información obtenida exitosamente!")
            print()
            print("📊 Resultado completo:")
            for key, value in producto_info.items():
                print(f"   {key}: {value}")
            
            # Verificar unidad de conversión
            unidad = producto_info.get("unidad_conversion")
            if unidad:
                print()
                print(f"✅ Unidad de conversión: {unidad}")
                print(f"   Esto significa: 1 docena = {unidad} packs")
            else:
                print()
                print("⚠️ No se pudo obtener unidad de conversión")
                print("   Verifica que el pack_sap exista en pack_conversion")
            
            return True
        else:
            print("⚠️ No se pudo obtener información del producto")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cache_repository(sku: str = "5-0012.9"):
    """
    Prueba del repositorio de cache.
    
    Args:
        sku: SKU del producto a consultar
    """
    print()
    print("=" * 70)
    print("🔍 PRUEBA 3: Repositorio de Cache")
    print("=" * 70)
    
    try:
        conn = get_db_connection()
        repository = ProductoSAPRepository(conn)
        print("✅ Repositorio inicializado")
        print()
        
        # Buscar en cache
        print(f"🔍 Buscando en cache para SKU: {sku}...")
        producto = repository.find_by_sku(sku)
        
        if producto:
            print("✅ Producto encontrado en cache!")
            print()
            print("📊 Información en cache:")
            for key, value in producto.items():
                print(f"   {key}: {value}")
            
            # Verificar validez del cache
            is_valid = repository.is_cache_valid(sku)
            print()
            if is_valid:
                print("✅ Cache es válido")
            else:
                print("⚠️ Cache ha expirado")
        else:
            print("⚠️ Producto no encontrado en cache")
            print("   Esto es normal si es la primera vez que se consulta")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Función principal."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Prueba consulta a SAP")
    parser.add_argument(
        "--sku",
        type=str,
        default="5-0012.9",
        help="SKU del producto a consultar (default: 5-0012.9)"
    )
    parser.add_argument(
        "--test",
        type=str,
        choices=["client", "service", "cache", "all"],
        default="all",
        help="Qué prueba ejecutar (default: all)"
    )
    
    args = parser.parse_args()
    sku = args.sku
    
    print()
    print("🚀 INICIANDO PRUEBAS DE CONSULTA SAP")
    print("=" * 70)
    print()
    
    resultados = []
    
    # Ejecutar pruebas según selección
    if args.test in ["client", "all"]:
        resultados.append(("Cliente SAP", test_sap_client_direct(sku)))
    
    if args.test in ["service", "all"]:
        resultados.append(("Servicio SAP", test_sap_service_with_cache(sku)))
    
    if args.test in ["cache", "all"]:
        resultados.append(("Repositorio Cache", test_cache_repository(sku)))
    
    # Resumen
    print()
    print("=" * 70)
    print("📊 RESUMEN DE PRUEBAS")
    print("=" * 70)
    for nombre, resultado in resultados:
        status = "✅ PASÓ" if resultado else "❌ FALLÓ"
        print(f"   {nombre}: {status}")
    
    print()
    todos_pasaron = all(r[1] for r in resultados)
    if todos_pasaron:
        print("✅ Todas las pruebas pasaron exitosamente!")
    else:
        print("⚠️ Algunas pruebas fallaron. Revisa los errores arriba.")
    
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()

