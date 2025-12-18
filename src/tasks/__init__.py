"""
Módulo de tareas programadas en segundo plano.

Nota: Los imports se hacen de forma explícita en lugar de automática
para evitar problemas cuando Celery carga el módulo.
"""

# No importar automáticamente para evitar problemas con Celery
# Los módulos se importan explícitamente donde se necesiten:
# - auto_migrate.py: para el proceso asyncio antiguo (si se necesita)
# - celery_auto_migrate.py: para el proceso Celery (nuevo)

__all__ = []
