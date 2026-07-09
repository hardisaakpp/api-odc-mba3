"""
M?dulo de endpoints FastAPI para la API de consultas MBA3.

Esta es la versi?n refactorizada que organiza los endpoints en m?dulos separados.
Mantiene compatibilidad con la funci?n create_endpoints() original.
"""

from fastapi import FastAPI
from .health import register_health_endpoints
from .auth import register_auth_endpoints
from .despachos import register_despachos_endpoints
from .sap import register_sap_endpoints
from .ordenes_compra import register_ordenes_compra_endpoints
from .pruebas import register_pruebas_endpoints
from .user_preferences import register_user_preferences_endpoints
from .remisiones import register_remisiones_endpoints
from .homologaciones_sku import register_homologaciones_sku_endpoints
from .cruce_productos import register_cruce_productos_endpoints
from .plantillas import register_plantillas_endpoints
from .pedidos import register_pedidos_endpoints
from .notificaciones import register_notificaciones_endpoints


def create_endpoints(app: FastAPI):
    """
    Registra todos los endpoints en la aplicaci?n FastAPI.
    
    Esta funci?n mantiene la compatibilidad con el c?digo existente.
    Los endpoints se registran desde m?dulos separados para mejor organizaci?n.
    
    Args:
        app: Instancia de FastAPI
    """
    # Registrar endpoints de health check (migrado)
    register_health_endpoints(app)
    
    # Registrar endpoints de autenticación
    register_auth_endpoints(app)
    
    # Registrar endpoints de despachos (migrado)
    register_despachos_endpoints(app)
    
    # Registrar endpoints de SAP (migrado)
    register_sap_endpoints(app)
    
    # Registrar endpoints de ?rdenes de compra (migrado)
    register_ordenes_compra_endpoints(app)
    
    # Registrar endpoints de pruebas (migrado)
    register_pruebas_endpoints(app)
    
    # Registrar endpoints de preferencias de usuario
    register_user_preferences_endpoints(app)
    
    # Registrar endpoints de remisiones
    register_remisiones_endpoints(app)
    
    # Registrar endpoints de homologaciones SKU
    register_homologaciones_sku_endpoints(app)
    
    # Registrar endpoints de cruce de productos
    register_cruce_productos_endpoints(app)
    
    # Registrar endpoints de plantillas Excel
    register_plantillas_endpoints(app)
    
    # Registrar endpoints de pedidos (refactorizado - 29 endpoints)
    register_pedidos_endpoints(app)
    
    # Registrar endpoints de notificaciones en tiempo real (SSE)
    register_notificaciones_endpoints(app)