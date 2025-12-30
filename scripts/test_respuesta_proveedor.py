"""
Script de prueba manual para PedidoRespuestaRepository.
Ejecutar después de crear las tablas SQL.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.repositories.pedido_respuesta_repository import PedidoRespuestaRepository


def test_repositorio_basico():
    """Prueba básica del repositorio."""
    print("=" * 70)
    print("🧪 PRUEBA: PedidoRespuestaRepository")
    print("=" * 70)
    
    with get_db_connection_context() as conn:
        # 1. Buscar un pedido existente
        pedido_repo = PedidoRepository(conn)
        pedidos = pedido_repo.get_by_estado("PENDIENTE_CONFIRMACION_PROVEEDOR")
        
        if not pedidos:
            print("⚠️ No hay pedidos en estado PENDIENTE_CONFIRMACION_PROVEEDOR")
            print("   Crear un pedido primero para probar")
            return False
        
        pedido_id = pedidos[0]["pedido_id"]
        print(f"✅ Pedido encontrado: {pedido_id}")
        
        # 2. Obtener pedido completo
        pedido = pedido_repo.get_pedido_completo(pedido_id)
        if not pedido:
            print("❌ No se pudo obtener pedido completo")
            return False
        
        print(f"✅ Pedido tiene {len(pedido['detalles'])} productos")
        
        # 3. Crear respuesta del proveedor
        respuesta_repo = PedidoRespuestaRepository(conn)
        
        print("\n📝 Creando respuesta del proveedor...")
        respuesta_id = respuesta_repo.crear_respuesta_proveedor(
            pedido_id=pedido_id,
            usuario_id="test_user",
            observaciones_generales="Prueba manual"
        )
        print(f"✅ Respuesta creada: {respuesta_id}")
        
        # 4. Preparar respuestas mock
        respuestas_cantidades = []
        for detalle in pedido["detalles"][:3]:  # Solo primeros 3 productos
            total_solicitado = sum(t["cantidad"] for t in detalle["tiendas"])
            respuestas_cantidades.append({
                "pedido_detalle_id": detalle["pedido_detalle_id"],
                "codigo_producto": detalle["codigo_interno"],
                "cantidad_solicitada_total": total_solicitado,
                "cantidad_confirmada_total": max(1, int(total_solicitado * 0.8)),  # 80%
                "observaciones": f"Confirmado {int(total_solicitado * 0.8)} unidades"
            })
        
        respuestas_precios = []  # Sin ajustes de precio por ahora
        
        # 5. Guardar detalles
        print("\n💾 Guardando detalles...")
        resultado = respuesta_repo.guardar_respuesta_detalles(
            respuesta_id=respuesta_id,
            respuestas_cantidades=respuestas_cantidades,
            respuestas_precios=respuestas_precios
        )
        print(f"✅ Detalles guardados: {resultado}")
        
        # 6. Obtener respuesta
        print("\n🔍 Obteniendo respuesta guardada...")
        respuesta_obtenida = respuesta_repo.obtener_respuesta_activa(pedido_id)
        
        if respuesta_obtenida:
            print(f"✅ Respuesta obtenida (versión {respuesta_obtenida['cabecera']['version']})")
            print(f"   Estado: {respuesta_obtenida['cabecera']['estado']}")
            print(f"   Productos: {len(respuesta_obtenida['detalles'])}")
            return True
        else:
            print("❌ No se pudo obtener respuesta")
            return False


if __name__ == "__main__":
    try:
        success = test_repositorio_basico()
        if success:
            print("\n" + "=" * 70)
            print("✅ TODAS LAS PRUEBAS PASARON")
            print("=" * 70)
        else:
            print("\n" + "=" * 70)
            print("❌ ALGUNAS PRUEBAS FALLARON")
            print("=" * 70)
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

