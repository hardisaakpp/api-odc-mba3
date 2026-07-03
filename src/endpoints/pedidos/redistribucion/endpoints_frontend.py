"""Endpoints compatibles con frontend (por numero_pedido)."""

import logging
import re
from typing import Dict, Optional

from fastapi import FastAPI, Depends, HTTPException, Path, Query, Body, status, Request
from fastapi.responses import StreamingResponse

from src.utils.timezone import ahora_naive

from src.database.connection import get_db_connection_context
from src.database.pedido_estados import ESTADO_PEDIDO_CONFIRMADO
from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.services.redistribucion_validator import RedistribucionValidator
from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission
from src.utils.audit_context import get_audit_context, ORIGEN_WEB
from src.models import (
    RedistribucionConfirmarRequest,
    ConfirmarRedistribucionResponseFrontend,
    BorradorResponse,
    AjusteDetalle,
)
from ..utils import get_user_id
from ._helpers import obtener_pedido_o_404, obtener_respuestas_proveedor, enriquecer_productos_con_pedido
from ._converters import convertir_ajustes_a_redistribucion
from ._resumen import calcular_resumen_confirmacion
from ._sap_processing import procesar_pedido_sap_con_homologacion
from ._notifications import notificar_redistribucion_confirmada, enviar_email_confirmacion_redistribucion
from ._excel_generators import generar_excel_distribucion

logger = logging.getLogger(__name__)

_PERM_MABEL = 'mabel.view'
_PERM_ODCSAP = 'odcsap.view'


async def _confirmar_redistribucion_handler(
    request: Request, numero_pedido: str, request_body: RedistribucionConfirmarRequest, user: Dict
) -> ConfirmarRedistribucionResponseFrontend:
    try:
        user_id = get_user_id(user)

        with get_db_connection_context() as conn:
            repo_pedido = PedidoRepository(conn)
            repo_dist = DistribucionConfirmadaRepository(conn)

            pedido_data = obtener_pedido_o_404(repo_pedido, numero_pedido, es_numero=True)

            pedido_id = pedido_data["cabecera"]["pedido_id"]

            productos_redistribucion = convertir_ajustes_a_redistribucion(
                request_body.ajustes_detalle,
                pedido_data,
                repo_pedido.tienda_repo,
            )

            respuestas_proveedor = obtener_respuestas_proveedor(repo_pedido, pedido_id)

            validator = RedistribucionValidator()
            es_valido, errores = validator.validar_redistribucion(
                pedido_data,
                productos_redistribucion,
                respuestas_proveedor
            )

            if not es_valido:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "validation_error",
                        "message": "La redistribución no cumple con las reglas de negocio",
                        "errores": errores
                    }
                )

            audit = get_audit_context(request, user, origen=ORIGEN_WEB)

            resultado = repo_dist.crear_redistribucion(
                pedido_id=pedido_id,
                productos_redistribucion=productos_redistribucion,
                usuario=user_id,
                audit_context=audit
            )

            repo_dist.confirmar_redistribucion(
                pedido_id=pedido_id,
                version=resultado["version"],
                usuario=user_id,
                audit_context=audit
            )

            repo_pedido.update_estado(pedido_id, ESTADO_PEDIDO_CONFIRMADO, audit_context=audit)

            resumen = calcular_resumen_confirmacion(request_body.ajustes_detalle)
            total_productos = resumen.total_productos

            logger.info(f"✅ Redistribución confirmada para pedido {numero_pedido} por usuario {user_id}")

            try:
                await notificar_redistribucion_confirmada(pedido_id, numero_pedido)
            except Exception as notif_err:
                logger.warning(f"⚠️ Error al enviar notificación en tiempo real: {notif_err}")

            logger.info("=" * 70)
            logger.info("🔄 PROCESANDO: Consultando SAP y procesando productos del pedido...")
            logger.info("=" * 70)

            try:
                await procesar_pedido_sap_con_homologacion(
                    pedido_id=pedido_id,
                    user_id=user_id,
                    conn=conn,
                    logger=logger,
                )
            except Exception as sap_error:
                logger.error(f"❌ Error al procesar pedido con SAP: {sap_error}", exc_info=True)
                logger.warning("⚠️ La redistribución fue confirmada pero el procesamiento SAP falló")

            logger.info("=" * 70)

            try:
                email_enviado = enviar_email_confirmacion_redistribucion(
                    pedido_id=pedido_id,
                    numero_pedido=numero_pedido,
                    user_id=user_id,
                    version=resultado.get("version", 0),
                    resumen=resumen,
                )
                if email_enviado:
                    logger.info(f"📧 Email de confirmación de redistribución enviado a El Rayo (Pedido: {numero_pedido})")
                else:
                    logger.warning("⚠️ No se pudo enviar email de confirmación de redistribución (no crítico)")
            except Exception as e:
                logger.warning(f"⚠️ Error al enviar email de confirmación de redistribución (no crítico): {e}")

            return ConfirmarRedistribucionResponseFrontend(
                pedido_id=pedido_id,
                numero_pedido=numero_pedido,
                redistribucion_id=str(resultado["version"]),
                fecha_confirmacion=ahora_naive(),
                resumen=resumen,
                ajustes_aplicados=total_productos,
                message="Redistribución confirmada exitosamente"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al confirmar redistribución: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": f"Error interno al confirmar redistribución: {str(e)}"
            }
        )


async def _ajustar_bodegas_handler(
    numero_pedido: str, request_body: RedistribucionConfirmarRequest
) -> BorradorResponse:
    try:
        with get_db_connection_context() as conn:
            repo_pedido = PedidoRepository(conn)

            obtener_pedido_o_404(repo_pedido, numero_pedido, es_numero=True)

            ajustes_ajustados = []

            for ajuste in request_body.ajustes_detalle:
                suma_total = sum(d.cantidad for d in ajuste.distribucion_tiendas)

                ajuste_ajustado = AjusteDetalle(
                    codigo_producto=ajuste.codigo_producto,
                    descripcion=ajuste.descripcion,
                    cantidad_solicitada=ajuste.cantidad_solicitada,
                    cantidad_confirmada=ajuste.cantidad_confirmada,
                    cantidad_ajustada=suma_total,
                    distribucion_tiendas=ajuste.distribucion_tiendas,
                    costo_original=ajuste.costo_original,
                    costo_ajustado=ajuste.costo_ajustado,
                    cambio_precio=ajuste.cambio_precio,
                    pedido_detalle_id=ajuste.pedido_detalle_id,
                    costo_modificado_manual=ajuste.costo_modificado_manual,
                    total_modificado_manual=ajuste.total_modificado_manual
                )

                ajustes_ajustados.append(ajuste_ajustado)

            return BorradorResponse(
                ajustes_detalle=ajustes_ajustados,
                fecha_guardado=ahora_naive()
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al procesar redistribución: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": f"Error interno al procesar redistribución: {str(e)}"
            }
        )


async def _descargar_excel_handler(
    pedido_id: str, version: Optional[int], user: Dict
) -> StreamingResponse:
    try:
        with get_db_connection_context() as conn:
            repo_dist = DistribucionConfirmadaRepository(conn)
            repo_pedido = PedidoRepository(conn)

            distribucion_data = repo_dist.get_distribucion_completa(pedido_id, version)

            if not distribucion_data or not distribucion_data.get("productos"):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "not_found",
                        "message": "No se encontró distribución confirmada para este pedido"
                    }
                )

            pedido_data = obtener_pedido_o_404(repo_pedido, pedido_id)
            cabecera = pedido_data.get("cabecera", {})

            productos_enriquecidos = enriquecer_productos_con_pedido(
                distribucion_data.get("productos", []),
                pedido_data.get("detalles", []),
            )

            itr_por_tienda: Dict[str, int] = {}
            numero_pedido_buscar = cabecera.get("numero_pedido", "")
            if numero_pedido_buscar:
                try:
                    from src.database.clients.sap_service_layer_client import SAPServiceLayerClient
                    sap_client = SAPServiceLayerClient()
                    itrs = sap_client.get_inventory_transfer_requests_by_comment(
                        f"Pedido {numero_pedido_buscar}"
                    )
                    for itr in itrs:
                        to_wh = itr.get("to_warehouse")
                        doc_num = itr.get("doc_num")
                        if to_wh and doc_num:
                            itr_por_tienda[to_wh] = doc_num
                    if itr_por_tienda:
                        logger.info(
                            f"📋 ITR DocNums obtenidos para {len(itr_por_tienda)} tienda(s) "
                            f"del pedido {numero_pedido_buscar}"
                        )
                except Exception as e_itr:
                    logger.warning(f"⚠️ No se pudieron obtener ITR DocNums (no crítico): {e_itr}")

            excel_buffer = generar_excel_distribucion(
                pedido_id=pedido_id,
                pedido_data=pedido_data,
                distribucion_data=distribucion_data,
                productos_enriquecidos=productos_enriquecidos,
                user=user,
                itr_por_tienda=itr_por_tienda,
            )

            numero_pedido = cabecera.get("numero_pedido", pedido_id)
            numero_pedido_safe = re.sub(r'[^\w\-\. ]', '_', numero_pedido)
            version_str = f"_v{distribucion_data.get('version_actual', 1)}"
            filename = f"distribucion_{numero_pedido_safe}{version_str}_{ahora_naive().strftime('%Y%m%d_%H%M%S')}.xlsx"

            logger.info(f"✅ Excel de distribución generado para pedido {pedido_id} ({numero_pedido}) por usuario {user.get('username', 'UNKNOWN')}")

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
        logger.error(f"❌ Error al generar Excel de distribución para pedido {pedido_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": f"Error al generar Excel de distribución: {str(e)}"
            }
        )


def register_frontend_endpoints(app: FastAPI):
    """Endpoints compatibles con frontend (por numero_pedido)."""

    @app.post("/api/pedidos/{numero_pedido}/redistribucion/confirmar",
             response_model=ConfirmarRedistribucionResponseFrontend,
             tags=["Pedidos - Redistribución"])
    async def confirmar_redistribucion_frontend(
        request: Request,
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: RedistribucionConfirmarRequest = Body(..., description="Datos de confirmación de redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """Confirma una redistribución (compatible con frontend)."""
        return await _confirmar_redistribucion_handler(request, numero_pedido, request_body, user)

    @app.post("/api/pedidos/{numero_pedido}/redistribucion/ajustar-bodegas",
             response_model=BorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def ajustar_bodegas_automaticamente(
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: RedistribucionConfirmarRequest = Body(..., description="Datos de redistribución para ajustar"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """Retorna los datos de redistribución sin ajustar automáticamente las bodegas."""
        return await _ajustar_bodegas_handler(numero_pedido, request_body)

    @app.get("/api/pedidos/{pedido_id}/distribucion/descargar-excel", tags=["Pedidos - Redistribución"])
    async def descargar_distribucion_excel(
        pedido_id: str = Path(..., description="UUID del pedido"),
        version: Optional[int] = Query(None, ge=1, description="Versión específica (si no se especifica, obtiene la última)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_ODCSAP, _PERM_MABEL]))
    ):
        """Descargar distribución confirmada del pedido en formato Excel (.xlsx)."""
        return await _descargar_excel_handler(pedido_id, version, user)
