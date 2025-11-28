"""
Servicio para ejecutar consultas contra MBA3.

Maneja la comunicación con MBA3 y el guardado en SQL Server.
"""

import logging
from typing import Dict, Any, Optional

from query_handler import get_mba3_client
from utils import validate_query
from exceptions import QueryValidationError, MBA3QueryError, MBA3ConnectionError

logger = logging.getLogger(__name__)


class MBA3Service:
    """Servicio para ejecutar consultas contra MBA3."""
    
    # Query base para facturas (integrada en el backend)
    BASE_FACTURAS_QUERY = """
        SELECT 
            CODIGO_FACTURA,
            ANULADA,
            NUMERO_PEDIDO_SISTEMA,
            NUMERO_ORDEN,
            NUMERO_FACTURA,
            CODIGO_DESPACHO,
            EMPRESA,
            CODIGO_CLIENTE,
            FECHA_FACTURA,
            TIPO_DOCUMENTO,
            ObjDatosFactura,
            ORDEN_COMPRA,
            ORDEN_COMPRA_CLIENTE,
            Remision_Facturada,
            NumIDFacturaRelacionada,
            CONFIRMADO,
            CODIGO_BODEGA
        FROM CLNT_FACTURA_PRINCIPAL
    """
    
    @staticmethod
    def build_facturas_query(
        anulada: Optional[bool] = False,
        confirmado: Optional[bool] = True,
        remision_facturada: Optional[bool] = False,
        include_obj_datos: bool = True
    ) -> str:
        """
        Construye la query SQL para obtener facturas con filtros opcionales.
        
        Esta query está integrada en el backend para que el frontend
        no necesite enviar SQL directamente.
        
        Args:
            anulada: Si es True, solo facturas anuladas; si False, solo no anuladas; None = todas
            confirmado: Si es True, solo facturas confirmadas; si False, solo no confirmadas; None = todas
            remision_facturada: Si es True, solo facturas con remisión facturada; si False, solo sin remisión; None = todas
            include_obj_datos: Si es True, filtra solo facturas con ObjDatosFactura no nulo
            
        Returns:
            Query SQL completa como string
        """
        where_clauses = []
        
        # Agregar filtros según parámetros
        if anulada is not None:
            where_clauses.append(f"ANULADA='{'true' if anulada else 'false'}'")
        
        if confirmado is not None:
            where_clauses.append(f"CONFIRMADO='{'true' if confirmado else 'false'}'")
        
        if remision_facturada is not None:
            where_clauses.append(f"Remision_Facturada='{'true' if remision_facturada else 'false'}'")
        
        if include_obj_datos:
            where_clauses.append("ObjDatosFactura IS NOT NULL")
        
        # Construir query completa
        query = MBA3Service.BASE_FACTURAS_QUERY.strip()
        if where_clauses:
            query += "\n        WHERE " + " AND ".join(where_clauses)
        
        return query
    
    @staticmethod
    def get_facturas(
        anulada: Optional[bool] = False,
        confirmado: Optional[bool] = True,
        remision_facturada: Optional[bool] = False,
        include_obj_datos: bool = True,
        save_to_db: bool = True,
        upsert: bool = True
    ) -> Dict[str, Any]:
        """
        Obtiene facturas de MBA3 usando la query integrada en el backend.
        
        Este método construye la query automáticamente y la ejecuta,
        eliminando la necesidad de que el frontend envíe SQL.
        
        Args:
            anulada: Filtrar por facturas anuladas (False = no anuladas, True = anuladas, None = todas)
            confirmado: Filtrar por facturas confirmadas (True = confirmadas, False = no confirmadas, None = todas)
            remision_facturada: Filtrar por remisión facturada (False = sin remisión, True = con remisión, None = todas)
            include_obj_datos: Si es True, solo incluye facturas con ObjDatosFactura no nulo
            save_to_db: Si es True, guarda los resultados en SQL Server
            upsert: Si es True, actualiza si existe; si False, inserta siempre (solo si save_to_db=True)
            
        Returns:
            Dict con los resultados y metadata
        """
        # Construir query
        query = MBA3Service.build_facturas_query(
            anulada=anulada,
            confirmado=confirmado,
            remision_facturada=remision_facturada,
            include_obj_datos=include_obj_datos
        )
        
        # Log de la query que se va a ejecutar
        logger.info("=" * 70)
        logger.info(f"🔍 Query que se ejecutará en get_facturas:")
        logger.info(query)
        logger.info("=" * 70)
        
        # Ejecutar query
        result = MBA3Service.execute_query(query)
        
        # Log detallado del resultado
        logger.info("=" * 70)
        logger.info(f"📦 Resultado de execute_query:")
        logger.info(f"   Tipo: {type(result)}")
        if isinstance(result, list) and len(result) > 0:
            logger.info(f"   Total elementos: {len(result)}")
            # Type narrowing: result es una lista no vacía aquí
            first = result[0]  # type: ignore[reportArgumentType]
            logger.info(f"   Tipo primer elemento: {type(first)}")
            if isinstance(first, dict):
                campos = list(first.keys())
                logger.info(f"   Campos en primera factura: {campos}")
                logger.info(f"   Total campos: {len(campos)}")
                if len(campos) == 1:
                    logger.error(f"   ⚠️ PROBLEMA: Solo hay 1 campo: {campos}")
                # Mostrar algunos valores
                for campo in campos[:5]:
                    logger.info(f"   {campo}: {first.get(campo)}")
        logger.info("=" * 70)
        
        # Guardar en base de datos si está habilitado
        # Capturar cualquier error para que no afecte la respuesta de las facturas
        save_status = None
        if save_to_db:
            try:
                save_status = MBA3Service.save_to_database(result, upsert=upsert)
            except Exception as save_error:
                # Si hay un error al guardar, registrarlo pero no afectar la respuesta
                logger.error(f"❌ Error al intentar guardar en SQL Server (no afecta la respuesta): {save_error}")
                save_status = {
                    "status": "error",
                    "message": f"Error al guardar en SQL Server: {str(save_error)}",
                    "facturas_guardadas": 0,
                    "facturas_actualizadas": 0,
                    "total_detalles": 0,
                    "errors": [str(save_error)]
                }
        
        # Retornar resultado con metadata
        return {
            "data": result,
            "query": query,
            "filters": {
                "anulada": anulada,
                "confirmado": confirmado,
                "remision_facturada": remision_facturada,
                "include_obj_datos": include_obj_datos
            },
            "save_status": save_status,
            "count": len(result) if isinstance(result, list) else (1 if result else 0)
        }
    
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
            
            # Log detallado del resultado de MBA3
            logger.info("=" * 70)
            logger.info("✅ Consulta ejecutada exitosamente contra MBA3")
            logger.info(f"   Tipo de resultado: {type(result)}")
            if isinstance(result, list):
                logger.info(f"   Total de registros: {len(result)}")
                if len(result) > 0:
                    first = result[0]
                    logger.info(f"   Tipo primer elemento: {type(first)}")
                    if isinstance(first, dict):
                        campos = list(first.keys())
                        logger.info(f"   Campos devueltos por MBA3: {campos}")
                        logger.info(f"   Total campos: {len(campos)}")
                        if len(campos) == 1:
                            logger.error(f"   ⚠️ PROBLEMA: MBA3 solo devolvió 1 campo: {campos}")
                            logger.error(f"   ⚠️ Datos completos: {first}")
                        else:
                            # Mostrar primeros 5 campos como ejemplo
                            for campo in campos[:5]:
                                logger.info(f"   {campo}: {first.get(campo)}")
            elif isinstance(result, dict):
                logger.info(f"   Resultado tipo: diccionario")
                campos = list(result.keys())
                logger.info(f"   Campos: {campos}")
            logger.info("=" * 70)
            
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
    def save_to_database(result: Dict[str, Any], upsert: bool = False) -> Optional[Dict[str, Any]]:
        """
        Guarda el resultado de MBA3 en SQL Server.
        
        Este método captura todos los errores y no los propaga para que no afecten
        la respuesta principal de las facturas.
        
        Args:
            result: Resultado de la consulta MBA3
            upsert: Si True, actualiza si existe; si False, inserta siempre
            
        Returns:
            Dict con estadísticas del guardado, o None si está deshabilitado o hay error
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

