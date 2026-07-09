"""
Capa de servicios para la lógica de negocio.

Separa la lógica de negocio de los endpoints HTTP.

Nota: Los imports se hacen de forma explícita en lugar de automática
para evitar problemas cuando Celery carga el módulo.
"""

# No importar automáticamente para evitar problemas con Celery
# Los módulos se importan explícitamente donde se necesiten:
# - mba3_service.py: para ejecutar consultas MBA3
# - query_service.py: para validación de queries

__all__ = []

