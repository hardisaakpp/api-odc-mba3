"""
Endpoint para realizar cruce de productos entre MBA3 y SAP.
"""

import logging
from fastapi import FastAPI, HTTPException, Depends

from src.database.services.cruce_productos_service import CruceProductosService
from src.security.jwt_auth import verify_jwt_token, require_permission

logger = logging.getLogger(__name__)


def register_cruce_productos_endpoints(app: FastAPI):
    """
    Registra los endpoints de cruce de productos en la aplicación FastAPI.
    
    Args:
        app: Instancia de FastAPI
    """
    
    @app.get("/cruce-productos/realizar-cruce", tags=["Cruce de Productos"])
    async def realizar_cruce_productos(
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """
        Realiza un cruce completo entre productos de MBA3 y SAP.
        
        Identifica:
        - Homologados exactos: PRODUCT_ID === ItemCode
        - Homologables: normalizar(PRODUCT_ID) === normalizar(ItemCode) pero códigos diferentes
        - Solo en MBA3: productos que no tienen match en SAP
        - Solo en SAP: productos que no tienen match en MBA3
        
        Returns:
            Resultado del cruce con estadísticas y listas de productos
        """
        try:
            logger.info("🔍 Iniciando cruce de productos MBA3 vs SAP...")
            service = CruceProductosService()
            resultado = service.realizar_cruce()
            
            return {
                "status": "success",
                "data": resultado,
                "message": "Cruce de productos completado exitosamente"
            }
        except Exception as e:
            logger.error(f"❌ Error al realizar cruce de productos: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error al realizar cruce: {str(e)}")

