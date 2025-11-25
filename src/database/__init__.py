"""
Módulo de base de datos para persistencia en SQL Server.

Estructura:
- connection: Gestión de conexiones
- repositories: Operaciones CRUD por entidad
- mappers: Transformación de datos MBA3 → SQL Server
- services: Lógica de negocio de persistencia
"""

from .connection import get_db_connection
from .services.factura_service import save_mba3_data_to_sql_server

__all__ = [
    "get_db_connection",
    "save_mba3_data_to_sql_server"
]





