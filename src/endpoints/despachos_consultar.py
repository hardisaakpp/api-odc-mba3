"""
Endpoint para consultar despachos desde MBA3 (solo lectura).
"""

import logging
from datetime import datetime

from src.utils.timezone import ahora_naive
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse

from src.services.mba3_service import MBA3Service
from src.utils import get_source_from_headers
from src.security.jwt_auth import verify_jwt_token, require_permission
from src.exceptions import MBA3ConnectionError, MBA3QueryError
from src.config import MBA3_QUERY_PREDEFINIDA

logger = logging.getLogger(__name__)


def _log_respuesta_mba3(result) -> None:
    """Registra información detallada de la respuesta de MBA3 (solo debugging)."""
    logger.info("=" * 70)
    logger.info("📊 RESPUESTA DE MBA3:")
    if isinstance(result, list):
        logger.info(f"   Tipo: Lista con {len(result)} elementos")
        if len(result) > 0:
            first_item = result[0]  # type: ignore[reportArgumentType]
            if isinstance(first_item, dict):
                campos = list(first_item.keys())
                logger.info(f"   Campos en primera factura: {campos}")
                logger.info(f"   Total de campos: {len(campos)}")
                # Mostrar algunos valores de ejemplo
                for campo in campos[:5]:  # Primeros 5 campos
                    logger.info(f"   {campo}: {first_item.get(campo)}")
            else:
                logger.warning(f"   ⚠️ Primer elemento no es dict: {type(first_item)}")
    elif isinstance(result, dict):
        logger.info("   Tipo: Diccionario")
        campos = list(result.keys())
        logger.info(f"   Campos: {campos}")
    else:
        logger.warning(f"   ⚠️ Tipo inesperado: {type(result)}")
    logger.info("=" * 70)


def register_consultar_endpoint(app: FastAPI):
    """
    Registra el endpoint /consultar en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    @app.get("/consultar", tags=["Consultas MBA3"])
    async def consultar_despachos(
        request: Request,
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Endpoint CONSULTAR: Ejecuta consulta predefinida y muestra resultados.
        
        **Responsabilidad:** Solo consulta, NO guarda en base de datos.
        Usa la query predefinida configurada en el backend.
        
        **Características:**
        - ✅ Query predefinida integrada en el backend
        - ✅ Solo consulta datos desde MBA3
        - ✅ NO guarda en SQL Server
        - ✅ Retorna resultados para visualización en Swagger/Postman
        
        **Ejemplo de uso:**
        ```
        GET /consultar
        ```
        
        **Query predefinida:**
        ```sql
        SELECT CODIGO_FACTURA,ANULADA,NUMERO_PEDIDO_SISTEMA,NUMERO_ORDEN,NUMERO_FACTURA,CODIGO_DESPACHO,EMPRESA,CODIGO_CLIENTE,FECHA_FACTURA,TIPO_DOCUMENTO,ObjDatosFactura,ORDEN_COMPRA,ORDEN_COMPRA_CLIENTE,Remision_Facturada,NumIDFacturaRelacionada,CONFIRMADO,CODIGO_BODEGA FROM CLNT_FACTURA_PRINCIPAL WHERE TIPO_DOCUMENTO='REM' AND ANULADA='false' AND CONFIRMADO='true' AND Remision_Facturada='false' AND CODIGO_DESPACHO=0 AND NUMERO_FACTURA > 0 AND ObjDatosFactura IS NOT NULL
        ```
        
        **Nota:** Este endpoint es solo para consultar y visualizar datos.
        Para guardar en despacho, usar endpoint MIGRAR.
        Para proceso completo (consulta + guarda + copia a ODC), usar GET /consulta/predefinida.
        
        Returns:
            JSON con los datos consultados de MBA3 (sin guardar)
        """
        # Usar query predefinida desde configuración
        query_predefinida = MBA3_QUERY_PREDEFINIDA
        
        # Determinar fuente
        source = get_source_from_headers(request)
        
        # Log de usuario autenticado
        username = user.get('username', 'unknown') if user else 'unknown'
        logger.info(f"👤 Usuario autenticado: {username}")
        
        # Log de la consulta
        logger.info("=" * 70)
        logger.info(f"🔍 CONSULTAR: Consulta ejecutada a las {ahora_naive().isoformat()}")
        logger.info(f"Fuente: {source}")
        logger.info(f"Query predefinida: {query_predefinida}")
        logger.info("Ejecutando consulta contra MBA3 (SOLO CONSULTA, NO GUARDA)...")
        logger.info("=" * 70)
        
        try:
            # Ejecutar consulta usando el servicio (SOLO consulta, NO guarda)
            result = MBA3Service.execute_query(query_predefinida)

            # Log detallado de la respuesta para debugging
            _log_respuesta_mba3(result)

            # Preparar headers de respuesta
            headers = {
                "X-Query": query_predefinida[:100],  # Primeros 100 caracteres de la query
                "X-Source": source,
                "X-Method": "GET",
                "X-Endpoint": "CONSULTAR",
                "X-Saved-To-DB": "false"  # Indica que NO se guardó
            }
            
            # Retornar resultado JSON de MBA3 directamente (solo para visualización)
            return JSONResponse(
                status_code=200,
                content=result,
                headers=headers
            )
            
        except MBA3ConnectionError as e:
            logger.error(f"❌ Error de conexión con MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "message": "No se pudo conectar al servidor MBA3",
                    "detail": str(e),
                    "type": "connection_error",
                    "hint": "Verifica que el servidor MBA3 esté disponible y accesible. Revisa la configuración de MBA3_BASE_URL en tu archivo .env"
                }
            )
        except MBA3QueryError as e:
            logger.error(f"❌ Error al ejecutar consulta en MBA3: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": "Error al ejecutar consulta en MBA3",
                    "detail": str(e),
                    "type": "query_error"
                }
            )
        except Exception as e:
            logger.error(f"❌ Error al ejecutar consulta: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error al ejecutar consulta: {str(e)}"
                }
            )

