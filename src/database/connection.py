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
    SQL_SERVER_PWD,
    SQL_SERVER_SAP_DRIVER,
    SQL_SERVER_SAP_SERVER,
    SQL_SERVER_SAP_DATABASE,
    SQL_SERVER_SAP_UID,
    SQL_SERVER_SAP_PWD
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
        
        # Verificar base de datos actual
        cursor = conn.cursor()
        cursor.execute("SELECT DB_NAME()")
        db_result = cursor.fetchone()
        cursor.close()
        
        if db_result is None:
            raise ValueError("No se pudo obtener el nombre de la base de datos actual")
        current_db = db_result[0]
        
        logger.info(f"✅ Conexión a SQL Server establecida")
        logger.info(f"   Servidor: {SQL_SERVER_SERVER}")
        logger.info(f"   Base de datos configurada: {SQL_SERVER_DATABASE}")
        logger.info(f"   Base de datos actual: {current_db}")
        
        if current_db.lower() != SQL_SERVER_DATABASE.lower():
            logger.warning(
                f"⚠️ ADVERTENCIA: Base de datos actual ({current_db}) "
                f"no coincide con la configurada ({SQL_SERVER_DATABASE})"
            )
        
        return conn
        
    except Exception as e:
        logger.error(f"❌ Error al conectar a SQL Server: {e}")
        raise


def get_sap_db_connection() -> pyodbc.Connection:
    """
    Crea y retorna una conexión al servidor SQL Server SAP.
    
    Este servidor se usa SOLO para ejecutar consultas OPENQUERY a SAP.
    Debe tener el servidor vinculado [MYHANADB] configurado.
    
    Returns:
        Conexión al servidor SQL Server SAP
        
    Raises:
        Exception: Si no se puede conectar a la base de datos
    """
    try:
        # Construir cadena de conexión para servidor SAP
        if SQL_SERVER_SAP_UID and SQL_SERVER_SAP_PWD:
            # Autenticación con usuario y contraseña
            connection_string = (
                f"DRIVER={SQL_SERVER_SAP_DRIVER};"
                f"SERVER={SQL_SERVER_SAP_SERVER};"
                f"DATABASE={SQL_SERVER_SAP_DATABASE};"
                f"UID={SQL_SERVER_SAP_UID};"
                f"PWD={SQL_SERVER_SAP_PWD}"
            )
        else:
            # Autenticación Windows (Trusted Connection)
            connection_string = (
                f"DRIVER={SQL_SERVER_SAP_DRIVER};"
                f"SERVER={SQL_SERVER_SAP_SERVER};"
                f"DATABASE={SQL_SERVER_SAP_DATABASE};"
                f"Trusted_Connection=yes;"
            )
        
        logger.debug(f"Conectando a SQL Server SAP: {SQL_SERVER_SAP_SERVER}/{SQL_SERVER_SAP_DATABASE}")
        conn = pyodbc.connect(connection_string, timeout=10)
        
        # Verificar base de datos actual
        cursor = conn.cursor()
        cursor.execute("SELECT DB_NAME()")
        db_result = cursor.fetchone()
        cursor.close()
        
        if db_result is None:
            raise ValueError("No se pudo obtener el nombre de la base de datos actual")
        current_db = db_result[0]
        
        logger.info(f"✅ Conexión a SQL Server SAP establecida")
        logger.info(f"   Servidor: {SQL_SERVER_SAP_SERVER}")
        logger.info(f"   Base de datos configurada: {SQL_SERVER_SAP_DATABASE}")
        logger.info(f"   Base de datos actual: {current_db}")
        
        return conn
        
    except Exception as e:
        logger.error(f"❌ Error al conectar a SQL Server SAP: {e}")
        raise






