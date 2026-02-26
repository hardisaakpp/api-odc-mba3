"""
Endpoints CRUD para gestión de pedidos (orquestador).

Este módulo coordina el registro de todos los endpoints de pedidos
desde sus módulos especializados:
- pedidos_estado_endpoints: Transiciones de estado
- pedidos_listado_endpoints: Listados y maestros
- pedidos_detalle_endpoints: Detalle de pedido
- pedidos_crear_editar_endpoints: Creación, edición, importar Excel
- pedidos_cancelar_endpoints: Cancelación y descarte
- pedidos_descarga_endpoints: Exportación (Excel/CSV)
"""

from fastapi import FastAPI


def register_crud_endpoints(app: FastAPI):
    """Registra los endpoints CRUD de pedidos."""
    from .pedidos_cancelar_endpoints import register_pedidos_cancelar_endpoints
    from .pedidos_crear_editar_endpoints import register_pedidos_crear_editar_endpoints
    from .pedidos_descarga_endpoints import register_pedidos_descarga_endpoints
    from .pedidos_detalle_endpoints import register_pedidos_detalle_endpoints
    from .pedidos_estado_endpoints import register_pedidos_estado_endpoints
    from .pedidos_listado_endpoints import register_pedidos_listado_endpoints

    register_pedidos_estado_endpoints(app)
    register_pedidos_listado_endpoints(app)
    register_pedidos_detalle_endpoints(app)
    register_pedidos_crear_editar_endpoints(app)
    register_pedidos_cancelar_endpoints(app)
    register_pedidos_descarga_endpoints(app)
