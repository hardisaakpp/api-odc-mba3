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
from src.database.repositories.common.serialization import make_json_serializable
from src.database.pedido_estados import ESTADOS_PRODUCCION_EL_RAYO_IDS
from src.security.jwt_auth import verify_jwt_token, require_any_permission
from .pedidos_crud_helpers import (
    enrich_pedido_with_ui_flags,
    enrich_pedido_reintento_envio_odc_sap,
    calcular_totales_detalles,
    get_estado_id_from_pedido,
    ocultar_costos_para_produccion_el_rayo,
)

logger = logging.getLogger(__name__)

_PERM_ODCSAP = 'odcsap.view'
_PERM_PRODUCCION_ELRAYO = 'produccion-elrayo.view'


def _validar_acceso_produccion_el_rayo(pedido: Dict, user: Dict) -> None:
    """Rechaza (403) el acceso al detalle si el pedido está en NUEVO_PEDIDO o
    GESTIONAR_PEDIDO y el usuario tiene odcsap.view pero NO produccion-elrayo.view
    (req. 1.8 segunda fase: esos 2 estados son exclusivos de Producción El Rayo;
    si el usuario tiene ambos permisos, produccion-elrayo.view nunca pierde acceso)."""
    permissions = user.get("permissions") or []
    if _PERM_ODCSAP not in permissions or _PERM_PRODUCCION_ELRAYO in permissions:
        return
    estado_id = get_estado_id_from_pedido(pedido)
    if estado_id in ESTADOS_PRODUCCION_EL_RAYO_IDS:
        raise HTTPException(
            status_code=403,
            detail="Este pedido está en un estado exclusivo de Producción El Rayo; ya no es accesible desde este perfil.",
        )


def _validar_acceso_estados_permitidos_produccion_el_rayo(pedido: Dict, user: Dict) -> None:
    """Rechaza (403) el acceso al detalle si el pedido NO está en NUEVO_PEDIDO ni
    GESTIONAR_PEDIDO y el usuario tiene produccion-elrayo.view pero NO odcsap.view
    (req. 1.8: Producción El Rayo solo puede acceder a esos 2 estados; si el
    usuario tiene ambos permisos, odcsap.view nunca pierde acceso)."""
    permissions = user.get("permissions") or []
    if _PERM_PRODUCCION_ELRAYO not in permissions or _PERM_ODCSAP in permissions:
        return
    estado_id = get_estado_id_from_pedido(pedido)
    if estado_id not in ESTADOS_PRODUCCION_EL_RAYO_IDS:
        raise HTTPException(
            status_code=403,
            detail="Producción El Rayo solo puede acceder a pedidos en Nuevo Pedido o Gestionar Pedido.",
        )


def _obtener_y_enriquecer_pedido(identificador: str, incluir_respuesta: bool, conn) -> Dict:
    """Extrae la lógica de obtención y enriquecimiento del pedido para reducir complejidad."""
    # Detectar si es UUID (formato: 8-4-4-4-12 caracteres hexadecimales)
    uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
    es_uuid = uuid_pattern.match(identificador.strip()) is not None
    
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
    enrich_pedido_reintento_envio_odc_sap(pedido, conn)

    # Totales calculados en backend (no persistidos): suma de COSTO UNIT., SUBTOTAL y TOTAL por detalle
    pedido["totales"] = calcular_totales_detalles(pedido.get("detalles", []))
    
    return pedido


def register_pedidos_detalle_endpoints(app: FastAPI):
    """Registra endpoint de detalle de pedido (por número o UUID)."""

    @app.get("/api/plantillas/{identificador}", tags=["Plantillas"])
    async def get_pedido(
        identificador: str = Path(..., description="Número de pedido (ej: 'P-12.48 - 12 - 2025') o UUID del pedido (para compatibilidad)"),
        incluir_respuesta: bool = Query(False, description="Incluir respuesta del proveedor si existe"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view', _PERM_PRODUCCION_ELRAYO]))
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
            "cabecera": {...},
            "detalles": [...],
            "totales": {
                "total_costo_unitario": 1234.56,
                "total_subtotal": 1234.56,
                "total_total": 1500.00
            },
            "respuesta_proveedor": {...}
        }
        ```
        Los totales se calculan en backend (no se persisten en BD) para que todos los usuarios vean la misma suma.
        
        Returns:
            JSON con pedido completo
        """
        try:
            with get_db_connection_context() as conn:
                pedido = _obtener_y_enriquecer_pedido(identificador, incluir_respuesta, conn)
                _validar_acceso_produccion_el_rayo(pedido, user)
                _validar_acceso_estados_permitidos_produccion_el_rayo(pedido, user)

                # RN-03: Producción El Rayo no debe recibir costos/precios/márgenes, ni
                # siquiera en el JSON crudo (antes solo se ocultaban en el frontend).
                ocultar_costos_para_produccion_el_rayo(user, pedido.get("detalles"), pedido.get("totales"))

                # Asegurar que Decimal (p. ej. cantidad_solicitada_total, cantidad_confirmada_total, total, cantidad) sea JSON serializable
                content = make_json_serializable(pedido)
                return JSONResponse(status_code=200, content=content)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al obtener pedido: {str(e)}"
            )
