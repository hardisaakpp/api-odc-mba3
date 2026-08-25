"""Endpoint de búsqueda del catálogo maestro de tiendas (para 'agregar tienda' en redistribución)."""

import logging
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query, status

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido.pedido_tienda_repository import PedidoTiendaRepository
from src.security.jwt_auth import verify_jwt_token, require_permission
from src.models import TiendaCatalogoItem

logger = logging.getLogger(__name__)

_PERM_MABEL = 'mabel.view'


async def _buscar_tiendas_handler(q: Optional[str], limit: int) -> List[TiendaCatalogoItem]:
    try:
        with get_db_connection_context() as conn:
            repo = PedidoTiendaRepository(conn)
            resultados = repo.buscar_tiendas(q, limit)
            return [TiendaCatalogoItem(**r) for r in resultados]
    except Exception as e:
        logger.error(f"❌ Error al buscar tiendas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": f"Error interno al buscar tiendas: {str(e)}"}
        )


def register_tiendas_endpoints(app: FastAPI):
    """Endpoint de búsqueda del catálogo maestro de tiendas."""

    @app.get("/api/pedidos/tiendas/buscar",
             response_model=List[TiendaCatalogoItem],
             tags=["Pedidos - Redistribución"])
    async def buscar_tiendas(
        q: Optional[str] = Query(None, description="Texto a buscar en código o nombre de tienda (búsqueda parcial)"),
        limit: int = Query(20, ge=1, le=100, description="Límite de resultados"),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """Busca tiendas activas del catálogo maestro por nombre o código."""
        return await _buscar_tiendas_handler(q, limit)
