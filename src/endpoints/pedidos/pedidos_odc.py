"""
Endpoint de creación de órdenes de compra.
"""

import logging
import re
from typing import Dict
from fastapi import FastAPI, Depends, HTTPException, Path, status

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.security.jwt_auth import verify_jwt_token, require_any_permission

logger = logging.getLogger(__name__)


def register_odc_endpoints(app: FastAPI):
    """Registra el endpoint de creación de órdenes de compra."""
    
    @app.post("/api/pedidos/{identificador}/crear-orden-compra", tags=["Pedidos - ODC"])
    async def crear_orden_compra_desde_pedido(
        identificador: str = Path(..., description="UUID del pedido o número de pedido (ej: 'P-12.55 - 12 - 2025')"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """Crea una orden de compra desde un pedido confirmado."""
        try:
            from src.database.services.pedido_oc_service import PedidoOCService
            
            user_id = user.get("sub") or user.get("user_id")
            
            # Detectar si es UUID o numero_pedido
            uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
            es_uuid = uuid_pattern.match(identificador.strip()) is not None
            
            # Obtener pedido_id real
            with get_db_connection_context() as conn:
                pedido_repo = PedidoRepository(conn)
                
                if es_uuid:
                    logger.info(f"🔍 Detectado UUID: {identificador}")
                    pedido = pedido_repo.get_pedido_completo(identificador)
                    if not pedido:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": "pedido_not_found",
                                   "message": f"Pedido no encontrado con UUID: {identificador}"})
                    pedido_id_real = identificador
                else:
                    logger.info(f"🔍 Detectado numero_pedido: {identificador}")
                    pedido = pedido_repo.get_pedido_completo_por_numero(identificador)
                    if not pedido:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": "pedido_not_found",
                                   "message": f"Pedido no encontrado con número: {identificador}"})
                    pedido_id_real = pedido["cabecera"]["pedido_id"]
            
            # Crear OC usando el pedido_id real
            service = PedidoOCService()
            resultado = service.crear_oc_desde_pedido_confirmado(
                pedido_id=pedido_id_real, usuario_id=user_id)
            
            return {"status": "success", "message": "Orden de compra creada exitosamente", **resultado}
            
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                              detail={"error": "validation_error", "message": str(e)})
        except Exception as e:
            logger.error(f"❌ Error al crear orden de compra: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                              detail={"error": "internal_error",
                                     "message": f"Error interno al crear orden de compra: {str(e)}"})
