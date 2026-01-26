"""
Clientes para conexiones externas (SAP, Core/Active Directory, etc.)
"""

from .sap_client import SAPClient
from .sap_service_layer_client import SAPServiceLayerClient
from .core_client import CoreAPIClient

__all__ = [
    "SAPClient",
    "SAPServiceLayerClient",
    "CoreAPIClient"
]

