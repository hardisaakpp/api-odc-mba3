"""
Servicio para ejecutar consultas contra MBA3.

Maneja la comunicación con MBA3 y el guardado en SQL Server.
"""

import logging
from typing import Dict, Any, Optional, Union, List

from query_handler import get_mba3_client
from utils import validate_query
from exceptions import QueryValidationError, MBA3QueryError, MBA3ConnectionError

logger = logging.getLogger(__name__)


class MBA3Service:
    """Servicio para ejecutar consultas contra MBA3."""
    
    @staticmethod
    def execute_query(query_text: str) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Ejecuta una consulta SQL contra MBA3.
        
        Args:
            query_text: Consulta SQL a ejecutar
            
        Returns:
            Resultado de la consulta como lista de diccionarios o diccionario
            
        Raises:
            ValueError: Si la consulta no es válida
            RuntimeError: Si hay error al ejecutar la consulta
        """
        # Validar consulta
        is_valid, validation_message = validate_query(query_text)
        if not is_valid:
            raise QueryValidationError(validation_message)
        
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
            
            # Log resumido del resultado
            if isinstance(result, list):
                logger.info(f"✅ Consulta MBA3 exitosa: {len(result)} registros")
                if len(result) > 0 and isinstance(result[0], dict):
                    campos = list(result[0].keys())
                    if len(campos) == 1:
                        logger.error(f"⚠️ PROBLEMA: MBA3 solo devolvió 1 campo: {campos}")
            elif isinstance(result, dict):
                logger.info(f"✅ Consulta MBA3 exitosa: resultado tipo diccionario ({len(result)} campos)")
            else:
                logger.info(f"✅ Consulta MBA3 exitosa: resultado tipo {type(result)}")
            
            return result
            
        except MBA3ConnectionError:
            # Re-lanzar errores de conexión sin modificar
            raise
        except MBA3QueryError:
            raise
        except QueryValidationError:
            raise
        except Exception as e:
            logger.error(f"Error al ejecutar consulta contra MBA3: {e}", exc_info=True)
            raise MBA3QueryError(f"Error al ejecutar consulta contra MBA3: {str(e)}")
    
    @staticmethod
    def save_to_database(result: Any, upsert: bool = False, homologacion_service: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """
        Guarda el resultado de MBA3 en SQL Server.
        
        Este método captura todos los errores y no los propaga para que no afecten
        la respuesta principal de las facturas.
        
        Args:
            result: Resultado de la consulta MBA3 (puede ser list o dict)
            upsert: Si True, actualiza si existe; si False, inserta siempre
            homologacion_service: Servicio de homologación para detectar productos no homologados (opcional)
            
        Returns:
            Dict con estadísticas del guardado, o None si está deshabilitado o hay error
        """
        try:
            from database import save_mba3_data_to_sql_server
            
            save_status = save_mba3_data_to_sql_server(
                result,
                upsert=upsert,
                continue_on_error=True,
                homologacion_service=homologacion_service
            )
            
            if save_status.get("status") == "success":
                logger.info(f"✅ Datos guardados en SQL Server: {save_status.get('facturas_guardadas', 0)} facturas, {save_status.get('total_detalles', 0)} detalles")
            elif save_status.get("status") == "partial":
                logger.warning(f"⚠️ Guardado parcial: {save_status.get('facturas_guardadas', 0)} guardadas, {save_status.get('facturas_error', 0)} errores")
            elif save_status.get("status") == "disabled":
                logger.debug("⏭️ Guardado en SQL Server deshabilitado")
                return None
            elif save_status.get("status") == "error":
                logger.error(f"❌ Error al guardar en SQL Server: {save_status.get('errors', [])}")
                # Retornar el status de error para que el frontend lo vea, pero no lanzar excepción
                return {
                    "status": "error",
                    "message": "Error al guardar en SQL Server",
                    "errors": save_status.get("errors", []),
                    "facturas_guardadas": 0,
                    "facturas_actualizadas": 0,
                    "total_detalles": 0
                }
            
            return save_status
            
        except ImportError as e:
            logger.warning(f"⚠️ Módulo database no disponible. Saltando guardado en SQL Server: {e}")
            return {
                "status": "disabled",
                "message": "Módulo database no disponible",
                "facturas_guardadas": 0,
                "facturas_actualizadas": 0,
                "total_detalles": 0
            }
        except Exception as e:
            # Capturar cualquier error y no propagarlo para que no afecte la respuesta
            logger.error(f"❌ Error inesperado al guardar en SQL Server: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Error al guardar en SQL Server: {str(e)}",
                "errors": [str(e)],
                "facturas_guardadas": 0,
                "facturas_actualizadas": 0,
                "total_detalles": 0
            }
    
    @staticmethod
    def save_remisiones_to_database(result: Any, upsert: bool = False) -> Optional[Dict[str, Any]]:
        """
        Guarda el resultado de remisiones de MBA3 en SQL Server.
        
        Este método guarda remisiones en la tabla remision_cabecera (sin detalles).
        
        Args:
            result: Resultado de la consulta MBA3 (puede ser list o dict)
            upsert: Si True, actualiza si existe; si False, inserta siempre
            
        Returns:
            Dict con estadísticas del guardado, o None si está deshabilitado o hay error
        """
        try:
            from database.services.remision_service import save_mba3_remisiones_to_sql_server
            
            save_status = save_mba3_remisiones_to_sql_server(
                result,
                upsert=upsert,
                continue_on_error=True
            )
            
            if save_status.get("status") == "success":
                logger.info(
                    f"✅ Remisiones guardadas en SQL Server: "
                    f"{save_status.get('remisiones_guardadas', 0)} guardadas, "
                    f"{save_status.get('remisiones_actualizadas', 0)} actualizadas"
                )
            elif save_status.get("status") == "disabled":
                logger.debug("⏭️ Guardado en SQL Server deshabilitado")
                return None
            elif save_status.get("status") == "error":
                logger.error(f"❌ Error al guardar remisiones en SQL Server: {save_status.get('errors', [])}")
                return {
                    "status": "error",
                    "message": "Error al guardar remisiones en SQL Server",
                    "errors": save_status.get("errors", []),
                    "remisiones_guardadas": 0,
                    "remisiones_actualizadas": 0
                }
            
            # Adaptar formato de respuesta para compatibilidad con el frontend
            return {
                "status": save_status.get("status", "success"),
                "facturas_guardadas": save_status.get("remisiones_guardadas", 0),
                "facturas_actualizadas": save_status.get("remisiones_actualizadas", 0),
                "total_detalles": 0,  # Las remisiones no tienen detalles
                "errors": save_status.get("errors", [])
            }
            
        except ImportError as e:
            logger.warning(f"⚠️ Módulo database no disponible. Saltando guardado en SQL Server: {e}")
            return {
                "status": "disabled",
                "message": "Módulo database no disponible",
                "remisiones_guardadas": 0,
                "remisiones_actualizadas": 0,
                "total_detalles": 0
            }
        except Exception as e:
            # Capturar cualquier error y no propagarlo para que no afecte la respuesta
            logger.error(f"❌ Error inesperado al guardar remisiones en SQL Server: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Error al guardar remisiones en SQL Server: {str(e)}",
                "errors": [str(e)],
                "remisiones_guardadas": 0,
                "remisiones_actualizadas": 0,
                "total_detalles": 0
            }

