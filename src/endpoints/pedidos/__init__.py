"""
Módulo de endpoints de pedidos.
Contiene todos los endpoints relacionados con la gestión de pedidos.
"""

from fastapi import FastAPI

from .pedidos_crud import register_crud_endpoints
from .pedidos_exportacion import register_exportacion_endpoints
from .pedidos_proveedor import register_proveedor_endpoints
from .pedidos_edicion import register_edicion_endpoints
from .pedidos_rayo import register_rayo_endpoints
from .pedidos_redistribucion import register_redistribucion_endpoints
from .pedidos_odc import register_odc_endpoints
from .pedidos_sap import register_sap_endpoints


def register_pedidos_endpoints(app: FastAPI):
    """
    Registra todos los endpoints relacionados con pedidos.
    
    Este es el punto de entrada principal para registrar todos los endpoints
    de pedidos en la aplicación FastAPI.
    """
    # Registrar endpoints por categoría
    register_crud_endpoints(app)              # 6 endpoints: listar, estados, obtener, importar, crear, modificar
    register_exportacion_endpoints(app)       # 2 endpoints: exportar para proveedor, exportar plano MBA
    register_proveedor_endpoints(app)         # 4 endpoints: cargar respuesta, formulario, enviar respuesta, crear desde pedido
    register_edicion_endpoints(app)           # 5 endpoints: actualizar costo, total, comentario, guardar/obtener modificaciones
    register_rayo_endpoints(app)              # 2 endpoints: obtener confirmaciones, detalle confirmación
    register_redistribucion_endpoints(app)    # 8 endpoints: distribución, redistribuir, confirmar, reportes, borradores
    register_odc_endpoints(app)               # 1 endpoint: crear orden de compra
    register_sap_endpoints(app)               # 1 endpoint: obtener procesamiento SAP


__all__ = ["register_pedidos_endpoints"]
