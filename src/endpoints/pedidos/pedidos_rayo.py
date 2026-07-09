"""
Endpoints de confirmaciones de El Rayo.
"""

import logging
from typing import Dict, Optional
from fastapi import FastAPI, Depends, HTTPException, Path, Query

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_confirmacion_rayo_repository import PedidoConfirmacionRayoRepository
from src.database.repositories.pedido_repository import PedidoRepository
from src.security.jwt_auth import verify_jwt_token, require_permission
from src.models import (
    ConfirmacionRayoListResponse,
    ConfirmacionRayoDetailResponse,
    ConfirmacionRayoItem
)

logger = logging.getLogger(__name__)

_DESC_PEDIDO_ID = "UUID del pedido"
_PERM_ODCSAP_VIEW = 'odcsap.view'


async def _handle_obtener_confirmaciones_rayo(pedido_id: str, limit: Optional[int]):
    try:
        with get_db_connection_context() as conn:
            repo_pedido = PedidoRepository(conn)
            pedido = repo_pedido.get_pedido_completo(pedido_id)

            if not pedido:
                raise HTTPException(status_code=404, detail=f"Pedido no encontrado: {pedido_id}")

            repo_confirmacion = PedidoConfirmacionRayoRepository(conn)
            confirmaciones_data = repo_confirmacion.obtener_confirmaciones_por_pedido(
                pedido_id=pedido_id, limit=limit)

            confirmaciones = []
            for conf_data in confirmaciones_data:
                confirmacion_completa = repo_confirmacion.obtener_confirmacion(conf_data["confirmacion_id"])
                if confirmacion_completa:
                    confirmaciones.append(ConfirmacionRayoItem(**confirmacion_completa))

            return ConfirmacionRayoListResponse(
                pedido_id=pedido_id,
                numero_pedido=pedido["cabecera"].get("numero_pedido"),
                total_confirmaciones=len(confirmaciones),
                confirmaciones=confirmaciones
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al obtener confirmaciones de EL RAYO: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al obtener confirmaciones: {str(e)}")


async def _handle_obtener_detalle_confirmacion_rayo(pedido_id: str, confirmacion_id: str):
    try:
        with get_db_connection_context() as conn:
            repo_pedido = PedidoRepository(conn)
            pedido = repo_pedido.get_pedido_completo(pedido_id)

            if not pedido:
                raise HTTPException(status_code=404, detail=f"Pedido no encontrado: {pedido_id}")

            repo_confirmacion = PedidoConfirmacionRayoRepository(conn)
            confirmacion_data = repo_confirmacion.obtener_confirmacion(confirmacion_id)

            if not confirmacion_data:
                raise HTTPException(status_code=404, detail=f"Confirmación no encontrada: {confirmacion_id}")

            if confirmacion_data["pedido_id"] != pedido_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"La confirmación {confirmacion_id} no pertenece al pedido {pedido_id}"
                )

            return ConfirmacionRayoDetailResponse(confirmacion=ConfirmacionRayoItem(**confirmacion_data))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al obtener detalle de confirmación: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al obtener detalle de confirmación: {str(e)}")


def register_rayo_endpoints(app: FastAPI):
    """Registra los endpoints de confirmaciones de El Rayo."""

    @app.get("/api/pedidos/{pedido_id}/confirmaciones-rayo",
             response_model=ConfirmacionRayoListResponse,
             tags=["Pedidos - Confirmaciones"])
    async def obtener_confirmaciones_rayo(
        pedido_id: str = Path(..., description=_DESC_PEDIDO_ID),
        limit: Optional[int] = Query(None, ge=1, le=100, description="Número máximo de confirmaciones a retornar (opcional)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_ODCSAP_VIEW))
    ):
        """Obtiene el historial de confirmaciones realizadas por EL RAYO para un pedido."""
        return await _handle_obtener_confirmaciones_rayo(pedido_id, limit)

    @app.get("/api/pedidos/{pedido_id}/confirmaciones-rayo/{confirmacion_id}",
             response_model=ConfirmacionRayoDetailResponse,
             tags=["Pedidos - Confirmaciones"])
    async def obtener_detalle_confirmacion_rayo(
        pedido_id: str = Path(..., description=_DESC_PEDIDO_ID),
        confirmacion_id: str = Path(..., description="UUID de la confirmación"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_ODCSAP_VIEW))
    ):
        """Obtiene el detalle completo de una confirmación específica de EL RAYO."""
        return await _handle_obtener_detalle_confirmacion_rayo(pedido_id, confirmacion_id)
