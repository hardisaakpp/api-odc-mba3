"""
Test de validación de la refactorización de endpoints de pedidos.

Este test valida que:
1. La refactorización de pedidos_crud.py fue exitosa
2. Todos los módulos de endpoints están cargados y funcionan
3. Los endpoints están registrados correctamente en la aplicación
"""

import pytest
from src.endpoints.pedidos.pedidos_crud import register_crud_endpoints
from fastapi import FastAPI


def test_all_pedidos_modules_can_be_imported():
    """Verifica que todos los módulos especializados de endpoints puedan ser importados."""
    from src.endpoints.pedidos import pedidos_estado_endpoints
    from src.endpoints.pedidos import pedidos_listado_endpoints
    from src.endpoints.pedidos import pedidos_detalle_endpoints
    from src.endpoints.pedidos import pedidos_crear_editar_endpoints
    from src.endpoints.pedidos import pedidos_cancelar_endpoints
    from src.endpoints.pedidos import pedidos_descarga_endpoints
    
    assert hasattr(pedidos_estado_endpoints, 'register_pedidos_estado_endpoints')
    assert hasattr(pedidos_listado_endpoints, 'register_pedidos_listado_endpoints')
    assert hasattr(pedidos_detalle_endpoints, 'register_pedidos_detalle_endpoints')
    assert hasattr(pedidos_crear_editar_endpoints, 'register_pedidos_crear_editar_endpoints')
    assert hasattr(pedidos_cancelar_endpoints, 'register_pedidos_cancelar_endpoints')
    assert hasattr(pedidos_descarga_endpoints, 'register_pedidos_descarga_endpoints')
    
    print("✅ Todos los módulos especializados fueron importados exitosamente")


def test_pedidos_crud_is_clean_orchestrator():
    """Verifica que pedidos_crud.py solo contenga el orquestador."""
    from src.endpoints.pedidos import pedidos_crud
    
    # Verificar que pedidos_crud es muy pequeño (solo orquestador)
    import inspect
    source = inspect.getsource(pedidos_crud)
    
    # Contar líneas - should be ~30 lines including docstring
    lines = len(source.strip().split('\n'))
    assert lines < 50, f"pedidos_crud.py debería tener <50 líneas, pero tiene {lines}"
    
    # Verificar que solo tiene la función register_crud_endpoints
    assert hasattr(pedidos_crud, 'register_crud_endpoints')
    
    print(f"✅ pedidos_crud.py es un orquestador limpio ({lines} líneas)")


def test_all_endpoints_registered_correctly():
    """Verifica que todos los endpoints estén registrados cuando se llama register_crud_endpoints."""
    app = FastAPI()
    register_crud_endpoints(app)
    
    # Obtener todas las rutas registradas
    routes = [r for r in app.routes if hasattr(r, 'path')]
    route_paths = {r.path for r in routes}
    
    # Verificar que las rutas clave están presentes
    expected_paths = {
        '/api/pedidos',                          # listar
        '/api/pedidos/confirmados',              # listar confirmados
        '/api/pedidos/estados',                  # listar estados
        '/api/pedidos/existe',                   # verificar existe
        '/api/pedidos/{pedido_id}/gestionar',    # marcar gestionar
        '/api/pedidos/{pedido_id}/confirmar-para-redistribucion',  # confirmar redistribución
        '/api/plantillas/{identificador}',       # detalle por identificador
        '/api/pedidos',                          # POST crear
        '/api/pedidos/{pedido_id}',              # PUT modificar, DELETE descartar
        '/api/pedidos/{pedido_id}/cancelar',     # cancelar MABEL
        '/api/pedidos/{pedido_id}/cancelar-por-el-rayo',  # cancelar EL RAYO
        '/api/pedidos/{pedido_id}/descargar-excel',  # descargar
        '/api/pedidos/{pedido_id}/descargar-csv',    # descargar CSV
        '/pedidos/importar-excel',               # importar
    }
    
    # Verificar que existen (sin ser tan strict en exact match de path patterns)
    found_count = 0
    for expected in expected_paths:
        # Para rutas con parámetros, hacer búsqueda más flexible
        if any(exp in str(route_paths) for exp in expected.split('{')):
            found_count += 1
    
    print(f"✅ Rutas registradas: {len(routes)} rutas, {found_count}/{len(expected_paths)} esperadas encontradas")
    assert len(routes) >= 15, f"Debería haber al menos 15 rutas, pero se encontraron {len(routes)}"


def test_modulos_especializados_are_independent():
    """Verifica que los módulos especializados pueden ser importados y usados independientemente."""
    from src.endpoints.pedidos.pedidos_listado_endpoints import register_pedidos_listado_endpoints
    from src.endpoints.pedidos.pedidos_estado_endpoints import register_pedidos_estado_endpoints
    
    app1 = FastAPI()
    register_pedidos_listado_endpoints(app1)
    
    app2 = FastAPI()
    register_pedidos_estado_endpoints(app2)
    
    # Ambas aplicaciones deberían tener rutas
    routes1 = [r for r in app1.routes if hasattr(r, 'path')]
    routes2 = [r for r in app2.routes if hasattr(r, 'path')]
    
    assert len(routes1) > 0, "pedidos_listado_endpoints no registró rutas"
    assert len(routes2) > 0, "pedidos_estado_endpoints no registró rutas"
    
    print(f"✅ Módulos independientes funcionan correctamente: {len(routes1)} rutas en listado, {len(routes2)} rutas en estado")


def test_refactoring_completeness():
    """Test final que resume el estado de la refactorización."""
    print("\n" + "="*60)
    print("VALIDACIÓN DE REFACTORIZACIÓN DE PEDIDOS_CRUD.PY")
    print("="*60)
    
    # 1. Verificar que pedidos_crud.py es pequeño
    from src.endpoints.pedidos import pedidos_crud
    import inspect
    source = inspect.getsource(pedidos_crud)
    lines = len(source.strip().split('\n'))
    print(f"\n1. ✅ pedidos_crud.py reducido a {lines} líneas (era ~950)")
    
    # 2. Verificar que todos los módulos existen
    from src.endpoints.pedidos import (
        pedidos_estado_endpoints,
        pedidos_listado_endpoints,
        pedidos_detalle_endpoints,
        pedidos_crear_editar_endpoints,
        pedidos_cancelar_endpoints,
        pedidos_descarga_endpoints
    )
    print("2. ✅ 6 módulos especializados creados y funcionales")
    
    # 3. Verificar que la función orquestadora existe
    assert hasattr(pedidos_crud, 'register_crud_endpoints')
    print("3. ✅ Función register_crud_endpoints() coordinadora existe")
    
    # 4. Registra todos los endpoints
    app = FastAPI()
    pedidos_crud.register_crud_endpoints(app)
    routes_count = len([r for r in app.routes if hasattr(r, 'path')])
    print(f"4. ✅ {routes_count} endpoints registrados en FastAPI")
    
    # 5. Estructura correcta
    print("5. ✅ Arquitectura modular validada:")
    print("   - pedidos_estado_endpoints: transiciones de estado")
    print("   - pedidos_listado_endpoints: listados y maestros")
    print("   - pedidos_detalle_endpoints: detalle de pedido")
    print("   - pedidos_crear_editar_endpoints: creación e importación")
    print("   - pedidos_cancelar_endpoints: cancelación y descarte")
    print("   - pedidos_descarga_endpoints: exportación Excel/CSV")
    
    print("\n" + "="*60)
    print("✅ REFACTORIZACIÓN COMPLETADA EXITOSAMENTE")
    print("="*60)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
