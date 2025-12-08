"""
Endpoints FastAPI para la API de consultas MBA3.

Esta versión usa servicios y helpers para separar la lógica de negocio.

⚠️ ESTE ARCHIVO ES SOLO PARA REFERENCIA/RESPALDO
Todos los endpoints han sido migrados a módulos separados en endpoints/
Este archivo ya no se ejecuta y se mantiene solo como respaldo histórico
"""

import logging
import uuid
from datetime import datetime

from fastapi import Request, Query as FastAPIQuery, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List

from models import HealthResponse
from services.mba3_service import MBA3Service
from utils import get_source_from_headers
from database.services.sap_service import SAPService
from database.clients.sap_client import SAPClient
from database.repositories.despacho_repository import DespachoRepository
from database.repositories.orden_compra_repository import OrdenCompraRepository
from database.repositories.sap_integration_log_repository import SAPIntegrationLogRepository
from database.services.orden_compra_service import copy_despacho_to_orden_compra
from database.services.oc_sap_service import OCSAPService
from database.connection import get_db_connection
from config import ENABLE_SAP_QUERIES, SAP_LINKED_SERVER, ENABLE_SAP_SERVICE_LAYER
from security.auth import optional_auth
from security.jwt_auth import verify_jwt_token, require_permission
from fastapi import Depends, Query
from exceptions import MBA3ConnectionError, MBA3QueryError

logger = logging.getLogger(__name__)


# ⚠️ ESTE ARCHIVO ES SOLO PARA REFERENCIA/RESPALDO
# Todos los endpoints han sido migrados a módulos separados en endpoints/
# Este archivo ya no se ejecuta y se mantiene solo como respaldo histórico

def create_endpoints(app):
    """
    Registra todos los endpoints en la aplicación FastAPI.
    
    ⚠️ NOTA: Esta función ya no se usa. Todos los endpoints han sido migrados.
    Se mantiene solo como referencia histórica.
    
    Args:
        app: Instancia de FastAPI
    """
    # Función vacía - todos los endpoints están migrados
    # Este archivo se mantiene solo como referencia histórica
    pass
    
    # ⚠️ NOTA: Todo el código original de los endpoints ha sido eliminado
    # porque todos han sido migrados a módulos separados en endpoints/
    # Si necesitas ver el código original, está disponible en el historial de Git
