"""
Gestión de conexiones a SQL Server.
"""

import logging
import pyodbc
from typing import Optional

from config import (
    SQL_SERVER_DRIVER,
    SQL_SERVER_SERVER,
    SQL_SERVER_DATABASE,
    SQL_SERVER_UID,
    SQL_SERVER_PWD
)

logger = logging.getLogger(__name__)


def get_db_connection() -> pyodbc.Connection:
    """
    Crea y retorna una conexión a SQL Server.
    
    Returns:
        Conexión a SQL Server
        
    Raises:
        Exception: Si no se puede conectar a la base de datos
    """
    try:
        # Construir cadena de conexión
        if SQL_SERVER_UID and SQL_SERVER_PWD:
            # Autenticación con usuario y contraseña
            connection_string = (
                f"DRIVER={SQL_SERVER_DRIVER};"
                f"SERVER={SQL_SERVER_SERVER};"
                f"DATABASE={SQL_SERVER_DATABASE};"
                f"UID={SQL_SERVER_UID};"
                f"PWD={SQL_SERVER_PWD}"
            )
        else:
            # Autenticación Windows (Trusted Connection)
            connection_string = (
                f"DRIVER={SQL_SERVER_DRIVER};"
                f"SERVER={SQL_SERVER_SERVER};"
                f"DATABASE={SQL_SERVER_DATABASE};"
                f"Trusted_Connection=yes;"
            )
        
        logger.debug(f"Conectando a SQL Server: {SQL_SERVER_SERVER}/{SQL_SERVER_DATABASE}")
        conn = pyodbc.connect(connection_string, timeout=10)
        logger.info("✅ Conexión a SQL Server establecida")
        return conn
        
    except Exception as e:
        logger.error(f"❌ Error al conectar a SQL Server: {e}")
        raise

