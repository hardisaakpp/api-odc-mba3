"""
Endpoints relacionados con consulta, migración y procesamiento de despachos.

Este módulo actúa como punto de entrada que registra todos los endpoints
de despachos desde módulos separados para mejor organización.
"""

from fastapi import FastAPI
from .despachos_consultar import register_consultar_endpoint
from .despachos_migrar import register_migrar_endpoint
from .despachos_procesar import register_procesar_endpoint
from .despachos_info import register_info_endpoints


def register_despachos_endpoints(app: FastAPI):
    """
    Registra todos los endpoints de despachos en la aplicación FastAPI.
    
    Esta función mantiene la compatibilidad con el código existente.
    Los endpoints se registran desde módulos separados para mejor organización.
    
    Args:
        app: Instancia de FastAPI
    """
    # Registrar endpoint de consulta (solo lectura)
    register_consultar_endpoint(app)
    
    # Registrar endpoint de migración (consulta + guarda)
    register_migrar_endpoint(app)
    
    # Registrar endpoint de procesamiento (copia a OC)
    register_procesar_endpoint(app)
    
    # Registrar endpoints de información (solo lectura)
    register_info_endpoints(app)
