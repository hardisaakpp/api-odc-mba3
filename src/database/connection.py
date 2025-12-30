"""
Gestión de conexiones a SQL Server.
"""

import logging
import pyodbc
from typing import Optional
from contextlib import contextmanager

from src.config import (
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
        
        # CRÍTICO: Configurar autocommit = False para usar transacciones explícitas
        # Esto asegura que los commits explícitos (conn.commit()) funcionen correctamente
        conn.autocommit = False
        
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


@contextmanager
def get_db_connection_context():
    """
    Context manager para conexiones SQL Server que GARANTIZA el cierre de conexión.
    
    Este context manager es CRÍTICO para prevenir:
    - Conexiones huérfanas que bloquean la base de datos
    - Agotamiento del pool de conexiones
    - Transacciones pendientes que causan deadlocks
    - Problemas cuando se usa con Celery workers
    
    Uso:
        with get_db_connection_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tabla")
            # La conexión se cierra automáticamente al salir
    
    Características:
    - Commit automático si todo sale bien
    - Rollback automático si hay excepciones
    - Cierre GARANTIZADO de conexión (incluso si hay errores)
    - Timeouts configurados para prevenir bloqueos eternos
    
    Returns:
        Generator que yield una conexión pyodbc
    """
    conn = None
    try:
        # Construir cadena de conexión con timeouts para prevenir bloqueos
        if SQL_SERVER_UID and SQL_SERVER_PWD:
            connection_string = (
                f"DRIVER={SQL_SERVER_DRIVER};"
                f"SERVER={SQL_SERVER_SERVER};"
                f"DATABASE={SQL_SERVER_DATABASE};"
                f"UID={SQL_SERVER_UID};"
                f"PWD={SQL_SERVER_PWD};"
                # CRÍTICO: Configuraciones para evitar bloqueos
                f"MARS_Connection=yes;"  # Múltiples result sets activos
                f"Connection Timeout=10;"  # Timeout de conexión (10 segundos)
                f"Command Timeout=30;"  # Timeout de comandos (30 segundos)
            )
        else:
            connection_string = (
                f"DRIVER={SQL_SERVER_DRIVER};"
                f"SERVER={SQL_SERVER_SERVER};"
                f"DATABASE={SQL_SERVER_DATABASE};"
                f"Trusted_Connection=yes;"
                f"MARS_Connection=yes;"
                f"Connection Timeout=10;"
                f"Command Timeout=30;"
            )
        
        logger.debug(f"[Context Manager] Creando conexión a {SQL_SERVER_SERVER}/{SQL_SERVER_DATABASE}")
        conn = pyodbc.connect(connection_string, timeout=10)
        
        # Configurar para usar transacciones explícitas
        # READ COMMITTED permite lecturas concurrentes (no bloquea SELECTs de otros procesos)
        conn.autocommit = False
        
        logger.debug("[Context Manager] Conexión creada exitosamente")
        
        # Yield la conexión para que el código que usa el context manager pueda trabajar con ella
        yield conn
        
        # Si llegamos aquí sin excepciones, confirmar transacción
        if conn and not conn.closed:
            conn.commit()
            logger.debug("[Context Manager] Transacción confirmada (commit)")
            
    except Exception as e:
        # Si hay error, revertir transacción
        if conn and not conn.closed:
            try:
                conn.rollback()
                logger.debug("[Context Manager] Transacción revertida (rollback) por error")
            except Exception as rollback_error:
                logger.error(f"[Context Manager] Error al hacer rollback: {rollback_error}")
        
        # Re-raise la excepción original para que el código llamador la maneje
        raise
        
    finally:
        # CRÍTICO: SIEMPRE cerrar la conexión, sin importar qué pasó
        if conn and not conn.closed:
            try:
                conn.close()
                logger.debug("[Context Manager] ✅ Conexión cerrada correctamente")
            except Exception as close_error:
                logger.error(f"[Context Manager] ❌ Error al cerrar conexión: {close_error}")


@contextmanager
def get_sap_db_connection_context():
    """
    Context manager para conexiones SQL Server SAP que GARANTIZA el cierre.
    
    Similar a get_db_connection_context() pero para el servidor SAP.
    
    Returns:
        Generator que yield una conexión pyodbc al servidor SAP
    """
    conn = None
    try:
        if SQL_SERVER_SAP_UID and SQL_SERVER_SAP_PWD:
            connection_string = (
                f"DRIVER={SQL_SERVER_SAP_DRIVER};"
                f"SERVER={SQL_SERVER_SAP_SERVER};"
                f"DATABASE={SQL_SERVER_SAP_DATABASE};"
                f"UID={SQL_SERVER_SAP_UID};"
                f"PWD={SQL_SERVER_SAP_PWD};"
                f"MARS_Connection=yes;"
                f"Connection Timeout=10;"
                f"Command Timeout=30;"
            )
        else:
            connection_string = (
                f"DRIVER={SQL_SERVER_SAP_DRIVER};"
                f"SERVER={SQL_SERVER_SAP_SERVER};"
                f"DATABASE={SQL_SERVER_SAP_DATABASE};"
                f"Trusted_Connection=yes;"
                f"MARS_Connection=yes;"
                f"Connection Timeout=10;"
                f"Command Timeout=30;"
            )
        
        logger.debug(f"[Context Manager SAP] Creando conexión a {SQL_SERVER_SAP_SERVER}/{SQL_SERVER_SAP_DATABASE}")
        conn = pyodbc.connect(connection_string, timeout=10)
        conn.autocommit = False
        
        logger.debug("[Context Manager SAP] Conexión creada exitosamente")
        yield conn
        
        if conn and not conn.closed:
            conn.commit()
            logger.debug("[Context Manager SAP] Transacción confirmada")
            
    except Exception as e:
        if conn and not conn.closed:
            try:
                conn.rollback()
                logger.debug("[Context Manager SAP] Transacción revertida por error")
            except Exception as rollback_error:
                logger.error(f"[Context Manager SAP] Error al hacer rollback: {rollback_error}")
        raise
        
    finally:
        if conn and not conn.closed:
            try:
                conn.close()
                logger.debug("[Context Manager SAP] ✅ Conexión cerrada correctamente")
            except Exception as close_error:
                logger.error(f"[Context Manager SAP] ❌ Error al cerrar conexión: {close_error}")


