"""
Manejo del cliente MBA3 para ejecución de consultas.
"""

import logging
from typing import Optional

from mba3_query_client import MBA3APIClient
from config import (
    MBA3_BASE_URL,
    MBA3_SERVICE_CODE,
    MBA3_SERVICE_PASSWORD,
    MBA3_DIGEST_USERNAME,
    MBA3_DIGEST_PASSWORD
)

logger = logging.getLogger(__name__)

# Instancia global del cliente MBA3 (se inicializa lazy)
_mba3_client: Optional[MBA3APIClient] = None


def get_mba3_client() -> MBA3APIClient:
    """
    Obtiene o crea la instancia del cliente MBA3.
    Usa singleton pattern para reutilizar la misma instancia y mantener el JWT.
    
    Returns:
        Instancia de MBA3APIClient configurada con las credenciales
    """
    global _mba3_client
    if _mba3_client is None:
        logger.info("Inicializando cliente MBA3 para consultas dinámicas...")
        _mba3_client = MBA3APIClient(
            base_url=MBA3_BASE_URL,
            service_code=MBA3_SERVICE_CODE,
            service_password=MBA3_SERVICE_PASSWORD,
            digest_username=MBA3_DIGEST_USERNAME,
            digest_password=MBA3_DIGEST_PASSWORD
        )
        logger.info(f"Cliente MBA3 inicializado con URL: {MBA3_BASE_URL}")
    return _mba3_client

