"""
Endpoints para transiciones de estado de pedidos.

Este módulo agrupa todos los endpoints relacionados con cambios de estado
de pedidos: gestionar, confirmar para redistribución, despachar y facturar, finalizar.
"""

import logging
from typing import Dict
from fastapi import FastAPI, Path, Depends, HTTPException, Request, status

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.pedido_estados import (
    ESTADO_NUEVO_PEDIDO,
    ESTADO_GESTIONAR_PEDIDO,
    ESTADO_REDISTRIBUCION,
    ESTADO_CONFIRMADO_ENVIADO,
    ESTADO_DESPACHAR_Y_FACTURAR,
    ESTADO_FINALIZADO,
)
from src.security.jwt_auth import verify_jwt_token, require_any_permission
from src.utils.audit_context import get_audit_context, ORIGEN_WEB
from .pedidos_crud_helpers import (
    enrich_pedido_with_ui_flags,
    enrich_pedido_reintento_envio_odc_sap,
    get_estado_id_from_pedido,
)

logger = logging.getLogger(__name__)


DESC_UUID_PEDIDO = "UUID del pedido"
PERM_MABEL_VIEW = "mabel.view"
PERM_ODCSAP_VIEW = "odcsap.view"
MSG_ERROR_NO_ENCONTRADO = "No se encontró el pedido."


def _obtener_pedido_completo_o_404(repo: PedidoRepository, pedido_id: str) -> Dict:
    pedido = repo.get_pedido_completo(pedido_id)
    if not pedido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": MSG_ERROR_NO_ENCONTRADO}
        )
    return pedido

async def _logic_marcar_pedido_gestionar(pedido_id: str, request: Request, user: Dict):
    audit = get_audit_context(request, user, origen=ORIGEN_WEB)
    try:
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = _obtener_pedido_completo_o_404(repo, pedido_id)
            estado_id = get_estado_id_from_pedido(pedido)
            
            if estado_id == ESTADO_NUEVO_PEDIDO:
                repo.update_estado(pedido_id, ESTADO_GESTIONAR_PEDIDO, audit_context=audit)
                pedido = _obtener_pedido_completo_o_404(repo, pedido_id)
            
            enrich_pedido_with_ui_flags(pedido)
            enrich_pedido_reintento_envio_odc_sap(pedido, conn)
            
            # 📢 Notificación SSE: mismo permiso (otros EL RAYO) + MABEL cuando EL RAYO abre el pedido
            if estado_id == ESTADO_NUEVO_PEDIDO:
                try:
                    from src.utils.notification_manager import notification_manager, NotificationType
                    numero_pedido = pedido.get("cabecera", {}).get("numero_pedido", "")
                    _username = user.get("username") or user.get("sub") or "unknown"
                    await notification_manager.notify_by_actor(
                        actor_permission=PERM_ODCSAP_VIEW,
                        actor_username=_username,
                        title="EL RAYO está gestionando tu pedido",
                        message=f"El pedido {numero_pedido} está siendo revisado por EL RAYO.",
                        notification_type=NotificationType.INFO,
                        metadata={"pedido_id": pedido_id, "numero_pedido": numero_pedido, "accion": "pedido_en_gestion"},
                    )
                except Exception as notif_err:
                    logger.warning(f"⚠️ Error al enviar notificación en tiempo real: {notif_err}")
            
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=200, content=pedido)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al marcar pedido como gestionar: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

async def _logic_confirmar_para_redistribucion(pedido_id: str, request: Request, user: Dict):
    audit = get_audit_context(request, user, origen=ORIGEN_WEB)
    try:
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = _obtener_pedido_completo_o_404(repo, pedido_id)
            estado_id = get_estado_id_from_pedido(pedido)
            
            if estado_id != ESTADO_GESTIONAR_PEDIDO:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "estado_no_gestionar",
                        "message": "Solo se puede confirmar para redistribución cuando el pedido está en estado GESTIONAR PEDIDO."
                    }
                )
            repo.update_estado(pedido_id, ESTADO_REDISTRIBUCION, audit_context=audit)
            pedido = _obtener_pedido_completo_o_404(repo, pedido_id)
            
            numero_pedido = pedido.get("cabecera", {}).get("numero_pedido", "")
            enrich_pedido_with_ui_flags(pedido)
            enrich_pedido_reintento_envio_odc_sap(pedido, conn)
            
            # 📢 Notificación: otros EL RAYO + MABEL (excl. autor)
            try:
                from src.utils.notification_manager import notification_manager, NotificationType
                _username = user.get("username") or user.get("sub") or "unknown"
                await notification_manager.notify_by_actor(
                    actor_permission=PERM_ODCSAP_VIEW,
                    actor_username=_username,
                    title="Pedido confirmado para redistribución",
                    message=f"El pedido {numero_pedido} ha sido confirmado por EL RAYO. Ya puedes descargarlo.",
                    notification_type=NotificationType.SUCCESS,
                    metadata={"pedido_id": pedido_id, "numero_pedido": numero_pedido, "accion": "confirmar_redistribucion"},
                )
            except Exception as notif_err:
                logger.warning(f"⚠️ Error al enviar notificación: {notif_err}")
            
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=200, content=pedido)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al confirmar pedido para redistribución: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

async def _logic_marcar_despachar_y_facturar(pedido_id: str, request: Request, user: Dict):
    audit = get_audit_context(request, user, origen=ORIGEN_WEB)
    try:
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = _obtener_pedido_completo_o_404(repo, pedido_id)
            estado_id = get_estado_id_from_pedido(pedido)
            
            if estado_id != ESTADO_CONFIRMADO_ENVIADO:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "estado_no_confirmado_enviado",
                        "message": "Solo se puede marcar como Despachar y Facturar cuando el pedido está en estado Confirmado y Enviado (ODC enviada a SAP)."
                    }
                )
            repo.update_estado(pedido_id, ESTADO_DESPACHAR_Y_FACTURAR, audit_context=audit)
            pedido = _obtener_pedido_completo_o_404(repo, pedido_id)
            
            numero_pedido = pedido.get("cabecera", {}).get("numero_pedido", "")
            enrich_pedido_with_ui_flags(pedido)
            enrich_pedido_reintento_envio_odc_sap(pedido, conn)
            
            # 📢 Notificación a ambos roles (mismo permiso excl. autor)
            try:
                from src.utils.notification_manager import notification_manager, NotificationType
                _username = user.get("username") or user.get("sub") or "unknown"
                await notification_manager.notify_by_actor(
                    actor_permission=PERM_ODCSAP_VIEW,
                    actor_username=_username,
                    title="Pedido marcado para Despachar y Facturar",
                    message=f"El pedido {numero_pedido} está listo para ser despachado y facturado.",
                    notification_type=NotificationType.INFO,
                    metadata={"pedido_id": pedido_id, "numero_pedido": numero_pedido, "accion": "despachar_y_facturar"},
                )
            except Exception as notif_err:
                logger.warning(f"⚠️ Error al enviar notificación: {notif_err}")

            # 📧 Email a MABEL TRADING (best-effort)
            try:
                from src.utils.email_notifier_pedido import send_despachar_y_facturar_notification

                usuario_rayo = user.get("username") or user.get("sub") or "unknown"
                email_enviado = send_despachar_y_facturar_notification(
                    pedido_id=pedido_id,
                    numero_pedido=numero_pedido,
                    usuario_rayo=usuario_rayo,
                )
                if email_enviado:
                    logger.info(
                        f"📧 Email 'Despachar y Facturar' enviado a MABEL_TRADING (Pedido: {numero_pedido})"
                    )
                else:
                    logger.warning(
                        f"⚠️ No se pudo enviar email 'Despachar y Facturar' a MABEL_TRADING (Pedido: {numero_pedido})"
                    )
            except Exception as e:
                logger.warning(
                    f"⚠️ Error al enviar email 'Despachar y Facturar' (no crítico): {e}",
                    exc_info=True,
                )
            
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=200, content=pedido)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al marcar pedido para despachar y facturar: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

async def _logic_marcar_finalizado(pedido_id: str, request: Request, user: Dict):
    audit = get_audit_context(request, user, origen=ORIGEN_WEB)
    try:
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = _obtener_pedido_completo_o_404(repo, pedido_id)
            estado_id = get_estado_id_from_pedido(pedido)
            
            if estado_id != ESTADO_DESPACHAR_Y_FACTURAR:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "estado_no_despachar_y_facturar",
                        "message": "Solo se puede marcar como Finalizado cuando el pedido está en estado Despachar y Facturar."
                    }
                )
            repo.update_estado(pedido_id, ESTADO_FINALIZADO, audit_context=audit)
            pedido = _obtener_pedido_completo_o_404(repo, pedido_id)
            
            numero_pedido = pedido.get("cabecera", {}).get("numero_pedido", "")
            enrich_pedido_with_ui_flags(pedido)
            enrich_pedido_reintento_envio_odc_sap(pedido, conn)
            
            # 📢 Notificación a ambos roles (mismo permiso excl. autor)
            try:
                from src.utils.notification_manager import notification_manager, NotificationType
                _username = user.get("username") or user.get("sub") or "unknown"
                await notification_manager.notify_by_actor(
                    actor_permission=PERM_ODCSAP_VIEW,
                    actor_username=_username,
                    title="Pedido finalizado",
                    message=f"El pedido {numero_pedido} ha sido marcado como FINALIZADO.",
                    notification_type=NotificationType.SUCCESS,
                    metadata={"pedido_id": pedido_id, "numero_pedido": numero_pedido, "accion": "finalizar"},
                )
            except Exception as notif_err:
                logger.warning(f"⚠️ Error al enviar notificación: {notif_err}")

            # 📧 Email a EL RAYO (best-effort)
            try:
                from src.utils.email_notifier_pedido import send_finalizar_pedido_notification

                usuario_mabel = user.get("username") or user.get("sub") or "unknown"
                email_enviado = send_finalizar_pedido_notification(
                    pedido_id=pedido_id,
                    numero_pedido=numero_pedido,
                    usuario_mabel=usuario_mabel,
                )
                if email_enviado:
                    logger.info(
                        f"📧 Email 'Pedido finalizado' enviado a OPERACIONES (EL RAYO) (Pedido: {numero_pedido})"
                    )
                else:
                    logger.warning(
                        f"⚠️ No se pudo enviar email 'Pedido finalizado' a OPERACIONES (EL RAYO) (Pedido: {numero_pedido})"
                    )
            except Exception as e:
                logger.warning(
                    f"⚠️ Error al enviar email 'Pedido finalizado' (no crítico): {e}",
                    exc_info=True,
                )

            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=200, content=pedido)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al marcar pedido como finalizado: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


def register_pedidos_estado_endpoints(app: FastAPI):
    """Registra endpoints de transiciones de estado de pedidos."""
    
    @app.post("/api/pedidos/{pedido_id}/gestionar", tags=["Pedidos"])
    async def marcar_pedido_gestionar(
        request: Request,
        pedido_id: str = Path(..., description=DESC_UUID_PEDIDO),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([PERM_ODCSAP_VIEW, PERM_MABEL_VIEW]))
    ):
        """
        Marca el pedido como GESTIONAR PEDIDO (al hacer clic en "Ver Detalle" desde la tabla Pedidos).
        Si el pedido está en estado NUEVO PEDIDO, actualiza a GESTIONAR PEDIDO y devuelve el pedido completo.
        Si ya está en otro estado, solo devuelve el pedido sin cambiar estado.
        """
        return await _logic_marcar_pedido_gestionar(pedido_id, request, user)
    
    @app.post("/api/pedidos/{pedido_id}/confirmar-para-redistribucion", tags=["Pedidos"])
    async def confirmar_para_redistribucion(
        request: Request,
        pedido_id: str = Path(..., description=DESC_UUID_PEDIDO),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([PERM_ODCSAP_VIEW, PERM_MABEL_VIEW]))
    ):
        """Confirmar pedido para redistribución (ESTADO_REDISTRIBUCION)."""
        return await _logic_confirmar_para_redistribucion(pedido_id, request, user)
    
    @app.post("/api/pedidos/{pedido_id}/marcar-despachar-y-facturar", tags=["Pedidos"])
    async def marcar_despachar_y_facturar(
        request: Request,
        pedido_id: str = Path(..., description=DESC_UUID_PEDIDO),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([PERM_ODCSAP_VIEW, PERM_MABEL_VIEW]))
    ):
        """
        Marca el pedido como Despachar y Facturar.

        - Actualiza el estado a DESPACHAR_Y_FACTURAR.
        - Envía notificación en tiempo real a otros EL RAYO.
        - Envía correo a MABEL TRADING informando que el pedido fue marcado como
          "Despachar y Facturar" (best-effort; si falla el email no se rompe el flujo).
        """
        return await _logic_marcar_despachar_y_facturar(pedido_id, request, user)
    
    @app.post("/api/pedidos/{pedido_id}/marcar-finalizado", tags=["Pedidos"])
    async def marcar_finalizado(
        request: Request,
        pedido_id: str = Path(..., description=DESC_UUID_PEDIDO),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([PERM_ODCSAP_VIEW, PERM_MABEL_VIEW]))
    ):
        """
        Marca el pedido como FINALIZADO.

        - Actualiza el estado a FINALIZADO.
        - Envía notificación en tiempo real a otros EL RAYO.
        - Envía correo a EL RAYO (OPERACIONES) notificando que MABEL TRADING
          finalizó el pedido (best-effort; si falla el email no se rompe el flujo).
        """
        return await _logic_marcar_finalizado(pedido_id, request, user)
