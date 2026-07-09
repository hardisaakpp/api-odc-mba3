"""
Repositorios para operaciones CRUD en SQL Server.

CHANGELOG:
- 2026-01-08: Agregadas utilidades de serialización compartidas
- 2026-01-08: Agregados repositorios especializados de despacho
"""

# Repositorios principales (facades)
from .despacho_repository import DespachoRepository
from .producto_sap_repository import ProductoSAPRepository
from .orden_compra_repository import OrdenCompraRepository
from .pedido_respuesta_repository import PedidoRespuestaRepository

# Utilidades compartidas
from .common.serialization import serialize_date, serialize_decimal

# Repositorios especializados (disponibles para uso directo si se necesita)
from .despacho import (
    DespachoCabeceraRepository,
    DespachoDetalleRepository,
    DespachoQueryRepository
)

__all__ = [
    # Repositorios principales
    "DespachoRepository",
    "ProductoSAPRepository",
    "OrdenCompraRepository",
    "PedidoRespuestaRepository",
    # Utilidades
    "serialize_date",
    "serialize_decimal",
    # Repositorios especializados
    "DespachoCabeceraRepository",
    "DespachoDetalleRepository",
    "DespachoQueryRepository"
]
