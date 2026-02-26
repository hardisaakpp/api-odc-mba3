"""
Endpoint de detalle de pedidos.
"""

import logging
import re
from typing import Dict

from fastapi import FastAPI, Path, Query, Depends, HTTPException
from fastapi.responses import JSONResponse

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.repositories.pedido_respuesta_repository import PedidoRespuestaRepository
from src.security.jwt_auth import verify_jwt_token, require_any_permission
from .pedidos_crud_helpers import enrich_pedido_with_ui_flags

logger = logging.getLogger(__name__)


def register_pedidos_detalle_endpoints(app: FastAPI):
    """Registra endpoint de detalle de pedido (por número o UUID)."""

    @app.get("/api/plantillas/{identificador}", tags=["Plantillas"])
    async def get_pedido(
        identificador: str = Path(..., description="Número de pedido (ej: 'P-12.48 - 12 - 2025') o UUID del pedido (para compatibilidad)"),
        incluir_respuesta: bool = Query(False, description="Incluir respuesta del proveedor si existe"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Obtiene un pedido completo con cabecera, detalles y distribuciones por tienda.
        Acepta número de pedido (recomendado) o UUID (para compatibilidad).
        Opcionalmente incluye la respuesta del proveedor.
        
        **Path Parameters:**
        - `identificador` (string, requerido) - Puede ser:
          - Número de pedido (business key, ej: 'P-12.48 - 12 - 2025') ⭐ RECOMENDADO
          - UUID del pedido (ej: 'AEDEC52D-D007-416F-8A09-9F0D31282EEE') ⚠️ Compatibilidad
        
        **Query Parameters:**
        - `incluir_respuesta` (bool, default: false): Si true, incluye respuesta del proveedor si existe
        
        **Respuesta exitosa:**
        ```json
        {
            "cabecera": {
                "pedido_id": "...",
                "numero_pedido": "...",
                "fecha_pedido": "...",
                ...
            },
            "detalles": [
                {
                    "pedido_detalle_id": "...",
                    "codigo_interno": "...",
                    "descripcion_sap": "...",
                    "tiendas": [
                        {
                            "tienda_id": "...",
                            "codigo": "RECREO",
                            "nombre": "...",
                            "cantidad": 10
                        }
                    ]
                }
            ],
            "respuesta_proveedor": {
                "cabecera": {...},
                "detalles": [...]
            }
        }
        ```
        
        Returns:
            JSON con pedido completo
        """
        try:
            # Detectar si es UUID (formato: 8-4-4-4-12 caracteres hexadecimales)
            uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
            es_uuid = uuid_pattern.match(identificador.strip()) is not None
            
            with get_db_connection_context() as conn:
                repository = PedidoRepository(conn)
                
                # Usar método apropiado según el formato detectado
                if es_uuid:
                    logger.info(f"🔍 Detectado UUID: {identificador}, usando get_pedido_completo")
                    pedido = repository.get_pedido_completo(identificador)
                    if not pedido:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Pedido no encontrado con UUID: {identificador}"
                        )
                else:
                    logger.info(f"🔍 Detectado numero_pedido: {identificador}, usando get_pedido_completo_por_numero")
                    pedido = repository.get_pedido_completo_por_numero(identificador)
                    if not pedido:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Pedido no encontrado con número: {identificador}"
                        )
                
                # Agregar respuesta si se solicita y existe (usando pedido_id de la cabecera)
                if incluir_respuesta:
                    respuesta_repo = PedidoRespuestaRepository(conn)
                    pedido_id = pedido["cabecera"]["pedido_id"]
                    respuesta = respuesta_repo.obtener_respuesta_activa(pedido_id)
                    if respuesta:
                        pedido["respuesta_proveedor"] = respuesta

                # Descartar (Cargar Plantilla): solo Borrador o Nuevo Pedido. Cancelar Pedido (Redistribución): deshabilitar desde Confirmado redistribución (10) en adelante.
                enrich_pedido_with_ui_flags(pedido)

                return JSONResponse(status_code=200, content=pedido)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al obtener pedido: {str(e)}"
            )
