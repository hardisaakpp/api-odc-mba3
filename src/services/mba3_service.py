"""
Servicio para ejecutar consultas contra MBA3.

Maneja la comunicación con MBA3 y el guardado en SQL Server.
"""

import logging
from typing import Dict, Any, Optional

from query_handler import get_mba3_client
from utils import validate_query
from exceptions import QueryValidationError, MBA3QueryError

logger = logging.getLogger(__name__)


class MBA3Service:
    """Servicio para ejecutar consultas contra MBA3."""
    
    @staticmethod
    def execute_query(query_text: str) -> Dict[str, Any]:
        """
        Ejecuta una consulta SQL contra MBA3.
        
        Args:
            query_text: Consulta SQL a ejecutar
            
        Returns:
            Resultado de la consulta como diccionario
            
        Raises:
            ValueError: Si la consulta no es válida
            RuntimeError: Si hay error al ejecutar la consulta
        """
        # Validar consulta
        is_valid, validation_message = validate_query(query_text)
        if not is_valid:
            raise QueryValidationError(validation_message)
        
        # Log de la consulta
        logger.info("=" * 70)
        logger.info(f"Ejecutando consulta contra MBA3: {query_text}")
        logger.info("=" * 70)
        
        # Obtener cliente MBA3
        client = get_mba3_client()
        
        # Ejecutar consulta
        try:
            result = client.execute_query(query_text, require_jwt=True)
            
            if result is None:
                raise MBA3QueryError(
                    "La consulta no retornó resultados. "
                    "Verifica la consulta SQL y la conexión con MBA3."
                )
            
            # Log de éxito
            logger.info("=" * 70)
            logger.info("✅ Consulta ejecutada exitosamente contra MBA3")
            if isinstance(result, list):
                logger.info(f"Total de registros: {len(result)}")
            elif isinstance(result, dict):
                logger.info(f"Resultado tipo: diccionario")
            logger.info("=" * 70)
            
            return result
            
        except MBA3QueryError:
            raise
        except QueryValidationError:
            raise
        except Exception as e:
            logger.error(f"Error al ejecutar consulta contra MBA3: {e}", exc_info=True)
            raise MBA3QueryError(f"Error al ejecutar consulta contra MBA3: {str(e)}")
    
    @staticmethod
    def save_to_database(result: Dict[str, Any], upsert: bool = False) -> Optional[Dict[str, Any]]:
        """
        Guarda el resultado de MBA3 en SQL Server.
        
        Args:
            result: Resultado de la consulta MBA3
            upsert: Si True, actualiza si existe; si False, inserta siempre
            
        Returns:
            Dict con estadísticas del guardado, o None si está deshabilitado
        """
        try:
            from database import save_mba3_data_to_sql_server
            
            logger.info("💾 Guardando datos en SQL Server...")
            save_status = save_mba3_data_to_sql_server(
                result,
                upsert=upsert,
                continue_on_error=True
            )
            
            if save_status.get("status") == "success":
                logger.info(f"✅ Datos guardados exitosamente en SQL Server")
                logger.info(f"   Facturas guardadas: {save_status.get('facturas_guardadas', 0)}")
                logger.info(f"   Total detalles: {save_status.get('total_detalles', 0)}")
            elif save_status.get("status") == "partial":
                logger.warning(f"⚠️ Datos guardados parcialmente en SQL Server")
                logger.warning(f"   Guardadas: {save_status.get('facturas_guardadas', 0)}")
                logger.warning(f"   Errores: {save_status.get('facturas_error', 0)}")
            elif save_status.get("status") == "disabled":
                logger.info("⏭️ Guardado en SQL Server deshabilitado")
                return None
            
            return save_status
            
        except ImportError:
            logger.warning("⚠️ Módulo database no disponible. Saltando guardado en SQL Server.")
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado al guardar en SQL Server: {e}", exc_info=True)
            return None

