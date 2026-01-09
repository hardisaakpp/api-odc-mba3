"""
Paquete de repositorios especializados para despachos.

CHANGELOG:
- 2026-01-08: Creado para organizar repositorios de despacho
"""

from .despacho_cabecera_repository import DespachoCabeceraRepository
from .despacho_detalle_repository import DespachoDetalleRepository
from .despacho_query_repository import DespachoQueryRepository

__all__ = [
    'DespachoCabeceraRepository',
    'DespachoDetalleRepository',
    'DespachoQueryRepository',
]
