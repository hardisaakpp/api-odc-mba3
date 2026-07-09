"""
Clientes para conexiones externas (SAP Service Layer, etc.)
"""

from .sap_client import SAPClient
from .sap_service_layer_client import SAPServiceLayerClient

__all__ = [
    "SAPClient",
    "SAPServiceLayerClient",
]

