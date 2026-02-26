"""
Endpoints de descarga de pedidos.
"""

import logging
from typing import Dict

from fastapi import FastAPI, Path, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.pedido_estados import ESTADO_REDISTRIBUCION
from src.security.jwt_auth import verify_jwt_token, require_any_permission
from .export_pedido_excel import generate_pedido_excel

logger = logging.getLogger(__name__)


def register_pedidos_descarga_endpoints(app: FastAPI):
    """Registra endpoints de descarga Excel/CSV de pedidos."""

    @app.get("/api/pedidos/{pedido_id}/descargar-csv", tags=["Pedidos"])
    @app.get("/api/pedidos/{pedido_id}/descargar-excel", tags=["Pedidos"])
    async def descargar_pedido_excel(
        pedido_id: str = Path(..., description="UUID del pedido a descargar"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Descargar informacion del pedido en formato Excel (.xlsx).
        
        **Uso:**
        - Interfaz: Detalle del Pedido (`/pedidos/{pedido_id}`)
        - Boton: "Descargar Excel"
        - Estado requerido: **CONFIRMADO (4)** (ESTADO_REDISTRIBUCION)
        
        **Contenido del Excel:**
        - Informacion de cabecera del pedido
        - Detalles de todos los articulos
        - Distribuciones por tienda
        
        **Formato:**
        - Archivo Excel (.xlsx) con 3 hojas:
          - Hoja 1: Informacion de cabecera
          - Hoja 2: Detalles de articulos
          - Hoja 3: Distribucion por tiendas
        
        **Respuestas:**
        - **200**: Archivo Excel descargado correctamente
        - **400**: Pedido no esta en estado CONFIRMADO (4)
        - **404**: Pedido no encontrado
        """
        try:
            with get_db_connection_context() as conn:
                repo = PedidoRepository(conn)
                
                # Obtener pedido completo
                pedido_data = repo.get_pedido_completo(pedido_id)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={"error": "not_found", "message": "Pedido no encontrado"}
                    )
                
                cabecera = pedido_data.get("cabecera", {})
                estado_id = cabecera.get("estado_id")
                
                # Validar que este en estado CONFIRMADO (4)
                if estado_id != ESTADO_REDISTRIBUCION:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "estado_no_permitido",
                            "message": f"El pedido debe estar en estado CONFIRMADO para descargar. Estado actual: {cabecera.get('estado_nombre', 'Desconocido')}"
                        }
                    )
                
                # Generar Excel usando modulo extraido
                username = user.get("username", "UNKNOWN")
                excel_buffer, filename = generate_pedido_excel(conn, pedido_id, pedido_data, username)
                
                # Retornar archivo Excel
                return StreamingResponse(
                    excel_buffer,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}",
                        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    }
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al generar Excel del pedido {pedido_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error al generar Excel del pedido: {str(e)}"
                }
            )
