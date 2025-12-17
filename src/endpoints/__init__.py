"""
Módulo de endpoints FastAPI para la API de consultas MBA3.

Esta es la versión refactorizada que organiza los endpoints en módulos separados.
Mantiene compatibilidad con la función create_endpoints() original.
"""

from fastapi import FastAPI
from .health import register_health_endpoints
from .despachos import register_despachos_endpoints
from .sap import register_sap_endpoints
from .ordenes_compra import register_ordenes_compra_endpoints
from .pruebas import register_pruebas_endpoints
from .user_preferences import register_user_preferences_endpoints
from .remisiones import register_remisiones_endpoints
from .homologaciones_sku import register_homologaciones_sku_endpoints


def create_endpoints(app: FastAPI):
    """
    Registra todos los endpoints en la aplicación FastAPI.
    
    Esta función mantiene la compatibilidad con el código existente.
    Los endpoints se registran desde módulos separados para mejor organización.
    
    Args:
        app: Instancia de FastAPI
    """
    # Registrar endpoints de health check (migrado)
    register_health_endpoints(app)
    
    # Registrar endpoints de despachos (migrado)
    register_despachos_endpoints(app)
    
    # Registrar endpoints de SAP (migrado)
    register_sap_endpoints(app)
    
    # Registrar endpoints de órdenes de compra (migrado)
    register_ordenes_compra_endpoints(app)
    
    # Registrar endpoints de pruebas (migrado)
    register_pruebas_endpoints(app)
    
    # Registrar endpoints de preferencias de usuario
    register_user_preferences_endpoints(app)
    
    # Registrar endpoints de remisiones
    register_remisiones_endpoints(app)
    
    # Registrar endpoints de homologaciones SKU
    register_homologaciones_sku_endpoints(app)
    
    # ✅ TODOS LOS ENDPOINTS HAN SIDO MIGRADOS
    # Ya no es necesario importar el módulo legacy
    # El archivo _endpoints_legacy.py puede mantenerse como respaldo o eliminarse
    # si se confirma que todo funciona correctamente

