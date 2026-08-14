"""
Endpoints de cancelacion y descarte de pedidos.
"""

import logging
from typing import Dict

from fastapi import FastAPI, Path, Query, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.repositories.pedido.pedido_cabecera_repository import PedidoCabeceraRepository
from src.database.pedido_estados import (
    ESTADO_CANCELADO,
    ESTADO_CANCELADO_POR_EL_RAYO,
    ESTADO_LIMITE_CANCELAR_PEDIDO,
    ESTADO_NUEVO_PEDIDO,
)
from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission
from src.logging_config import log_business_operation
from src.utils.audit_context import get_audit_context, ORIGEN_WEB
from .pedidos_crud_helpers import (
    enrich_pedido_with_ui_flags,
    enrich_pedido_reintento_envio_odc_sap,
    get_estado_id_from_pedido,
)

logger = logging.getLogger(__name__)

# Permisos (evita duplicación de literales)
_PERM_MABEL = 'mabel.view'
_PERM_ODCSAP = 'odcsap.view'
_PERM_PRODUCCION_ELRAYO = 'produccion-elrayo.view'


def _resolver_estado_id(cabecera):
    """Resuelve el estado_id (numérico) de una cabecera, con fallback al estado legacy."""
    estado_id = cabecera.get("estado_id")
    if estado_id is None:
        from src.database.pedido_estados import estado_id_desde_legacy
        estado_id = estado_id_desde_legacy(cabecera.get("estado"))
    try:
        return int(estado_id) if estado_id is not None else None
    except (TypeError, ValueError):
        return None


async def _notificar_realtime(actor_permission, actor_username, title, message, metadata):
    """Envía una notificación en tiempo real (best-effort, nunca falla el flujo)."""
    try:
        from src.utils.notification_manager import notification_manager, NotificationType
        await notification_manager.notify_by_actor(
            actor_permission=actor_permission,
            actor_username=actor_username,
            title=title,
            message=message,
            notification_type=NotificationType.WARNING,
            metadata=metadata,
        )
    except Exception as notif_err:
        logger.warning(f"⚠️ Error al enviar notificacion en tiempo real: {notif_err}")


def _notificar_cancelado_email(pedido_id, numero_pedido, user):
    """Envía el correo de cancelación a EL RAYO (best-effort)."""
    try:
        from src.utils.email_notifier import send_pedido_cancelado_notification
        send_pedido_cancelado_notification(
            pedido_id=pedido_id,
            numero_pedido=numero_pedido,
            usuario_id=user.get("username") or user.get("sub"),
        )
    except Exception as notif_err:
        logger.warning(f"⚠️ No se pudo enviar notificacion de pedido cancelado a EL RAYO: {notif_err}")


async def _notificar_descartado(pedido_id, numero_pedido, estado_id, user):
    """Envía las notificaciones (email + tiempo real) de pedido descartado (best-effort)."""
    try:
        from src.utils.email_notifier import send_pedido_descartado_notification
        send_pedido_descartado_notification(
            pedido_id=pedido_id,
            numero_pedido=numero_pedido,
            usuario_id=user.get("username") or user.get("sub"),
        )
        logger.info(f"📧 Notificacion de pedido descartado enviada a EL RAYO (estado_id={estado_id})")
    except Exception as notif_err:
        logger.warning(f"⚠️ No se pudo enviar notificacion de pedido descartado a EL RAYO: {notif_err}")

    _username = user.get("username") or user.get("sub") or "unknown"
    await _notificar_realtime(
        actor_permission=_PERM_MABEL,
        actor_username=_username,
        title="Pedido descartado por MABEL TRADING",
        message=f"El pedido {numero_pedido or pedido_id} ha sido descartado.",
        metadata={"pedido_id": pedido_id, "numero_pedido": numero_pedido, "accion": "pedido_descartado"},
    )


def _raise_si_no_puede_descartar(ok, error_code, message):
    """Lanza la HTTPException apropiada si el pedido no puede descartarse."""
    if ok:
        return
    if error_code == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": error_code, "message": message}
        )
    if error_code in ("estado_no_borrador", "estado_no_permitido"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": error_code, "message": message}
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": error_code, "message": message}
    )


def _raise_si_no_puede_cancelar_por_rayo(ok, error_code, message):
    """Lanza la HTTPException apropiada si el pedido no puede cancelarse por EL RAYO."""
    if ok:
        return
    if error_code == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": error_code, "message": message}
        )
    if error_code == "estado_no_permitido":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": error_code, "message": message}
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": error_code, "message": message}
    )


async def _cancelar_pedido_handler(request, pedido_id, user):
    """Lógica del endpoint 'cancelar pedido' (MABEL, desde Redistribución)."""
    # Crear contexto de auditoria (Buenas Practicas - Seccion 3)
    audit = get_audit_context(request, user, origen=ORIGEN_WEB)

    try:
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = repo.get_pedido_completo(pedido_id)

            if not pedido:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "not_found",
                        "message": f"No se encontro el pedido con ID: {pedido_id}"
                    }
                )

            # Validar estado: solo permitir cancelar si estado_id < ESTADO_LIMITE_CANCELAR_PEDIDO (10)
            cabecera = pedido.get("cabecera", {})
            estado_id = _resolver_estado_id(cabecera)

            if estado_id is None or estado_id >= ESTADO_LIMITE_CANCELAR_PEDIDO:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "estado_no_permitido",
                        "message": "El pedido no puede cancelarse porque esta en estado Confirmado redistribucion o posterior."
                    }
                )

            # Cambiar estado a CANCELADO (con campos de auditoria)
            repo.update_estado(pedido_id, ESTADO_CANCELADO, audit_context=audit)

            # Obtener pedido actualizado
            pedido_actualizado = repo.get_pedido_completo(pedido_id)
            if pedido_actualizado is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found", "message": "No se encontro el pedido."})
            numero_pedido = (pedido_actualizado.get("cabecera") or {}).get("numero_pedido")

            # Notificar a EL RAYO (email)
            _notificar_cancelado_email(pedido_id, numero_pedido, user)

            # 📢 Notificacion: otros MABEL + EL RAYO (excl. autor)
            _username = user.get("username") or user.get("sub") or "unknown"
            await _notificar_realtime(
                actor_permission=_PERM_MABEL,
                actor_username=_username,
                title="Pedido cancelado por MABEL TRADING",
                message=f"El pedido {numero_pedido} ha sido cancelado.",
                metadata={"pedido_id": pedido_id, "numero_pedido": numero_pedido, "accion": "pedido_cancelado"},
            )

            # Calcular flags de UI
            enrich_pedido_with_ui_flags(pedido_actualizado)
            enrich_pedido_reintento_envio_odc_sap(pedido_actualizado, conn)

            # Log funcional estandarizado (Buenas Practicas - Seccion 5)
            log_business_operation(
                operation="cancelar_pedido",
                id_usuario=user.get('username', 'UNKNOWN'),
                id_transaccion=pedido_id,
                id_tienda=cabecera.get("codigo_tienda"),
                success=True,
                detalles={
                    "numero_pedido": numero_pedido,
                    "estado_anterior": estado_id,
                    "estado_nuevo": ESTADO_CANCELADO
                }
            )

            return JSONResponse(status_code=200, content=pedido_actualizado)

    except HTTPException:
        raise
    except Exception as e:
        # Log funcional de error
        log_business_operation(
            operation="cancelar_pedido",
            id_usuario=user.get('username', 'UNKNOWN'),
            id_transaccion=pedido_id,
            success=False,
            detalles={"error": str(e)}
        )
        logger.error(f"❌ Error al cancelar pedido {pedido_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": f"Error interno al cancelar el pedido: {str(e)}"
            }
        )


async def _descartar_o_cancelar_pedido_handler(request, pedido_id, notificar_el_rayo, user):
    """Lógica del endpoint 'descartar o cancelar pedido' (Cargar Plantilla / Redistribución)."""
    try:
        # Crear contexto de auditoria (Buenas Practicas - Seccion 3)
        audit = get_audit_context(request, user, origen=ORIGEN_WEB)

        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            ok, error_code, message = repo.validar_puede_descartar(
                pedido_id, es_cancelar_pedido=notificar_el_rayo
            )
            _raise_si_no_puede_descartar(ok, error_code, message)

            # Obtener estado_id y numero_pedido antes de eliminar
            pedido_data = repo.get_pedido_completo(pedido_id)
            numero_pedido = (pedido_data.get("cabecera") or {}).get("numero_pedido") if pedido_data else None
            estado_id = get_estado_id_from_pedido(pedido_data) if pedido_data else None

            # Eliminar el pedido con audit_context
            repo.delete_pedido(pedido_id, audit_context=audit)

            # Determinar si se debe enviar notificacion a EL RAYO:
            # - Caso 1: "Cancelar Pedido" desde Redistribucion -> siempre notificar
            # - Caso 2: "Descartar" desde Cargar Plantilla en estado NUEVO PEDIDO (2) -> notificar
            # - Caso 3: "Descartar" en estado BORRADOR (1) o GESTIONAR PEDIDO (3) -> NO notificar
            enviar_notificacion = notificar_el_rayo or estado_id == ESTADO_NUEVO_PEDIDO

            if enviar_notificacion:
                await _notificar_descartado(pedido_id, numero_pedido, estado_id, user)
            else:
                logger.info(f"⏭️ No se envia notificacion (estado={estado_id}, notificar_el_rayo={notificar_el_rayo})")

        logger.info(f"✅ Pedido {pedido_id} eliminado por usuario {user.get('username', 'UNKNOWN')} (notificar_el_rayo={notificar_el_rayo}, estado_id={estado_id})")
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al descartar pedido {pedido_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": f"Error al descartar el pedido: {str(e)}"
            }
        )


async def _cancelar_pedido_por_el_rayo_handler(request, pedido_id, user):
    """Lógica del endpoint 'cancelar pedido por EL RAYO' (desde Detalle del Pedido)."""
    # Crear contexto de auditoria (Buenas Practicas - Seccion 3)
    audit = get_audit_context(request, user, origen=ORIGEN_WEB)

    try:
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)

            # Validar que se puede cancelar (solo estado GESTIONAR PEDIDO)
            ok, error_code, message = repo.validar_puede_eliminar(pedido_id)
            _raise_si_no_puede_cancelar_por_rayo(ok, error_code, message)

            # Obtener datos del pedido
            pedido_data = repo.get_pedido_completo(pedido_id)
            numero_pedido = (pedido_data.get("cabecera") or {}).get("numero_pedido") if pedido_data else None

            # Cambiar estado a CANCELADO POR EL RAYO (20) en vez de eliminar
            cab_repo = PedidoCabeceraRepository(conn)
            cab_repo.update_estado(
                pedido_id,
                ESTADO_CANCELADO_POR_EL_RAYO,
                audit_context=audit,
            )

            # 📢 Notificacion: otros EL RAYO + MABEL (excl. autor)
            _username = user.get("username") or user.get("sub") or "unknown"
            await _notificar_realtime(
                actor_permission=_PERM_ODCSAP,
                actor_username=_username,
                title="Pedido cancelado por EL RAYO",
                message=f"El pedido {numero_pedido or pedido_id} ha sido cancelado por EL RAYO.",
                metadata={"pedido_id": pedido_id, "numero_pedido": numero_pedido, "accion": "pedido_cancelado_por_el_rayo"},
            )

            logger.info(
                f"✅ Pedido {pedido_id} cancelado por EL RAYO (boton Cancelar Pedido) "
                f"por usuario {user.get('username', 'UNKNOWN')} (numero_pedido={numero_pedido})"
            )

            return {
                "success": True,
                "message": f"Pedido {numero_pedido or pedido_id} cancelado correctamente",
                "pedido_id": pedido_id,
                "numero_pedido": numero_pedido,
                "estado": "CANCELADO POR EL RAYO",
                "estado_id": ESTADO_CANCELADO_POR_EL_RAYO,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al cancelar pedido {pedido_id} por EL RAYO: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": f"Error al cancelar el pedido: {str(e)}"
            }
        )


def register_pedidos_cancelar_endpoints(app: FastAPI):
    """Registra endpoints de cancelacion y descarte de pedidos."""

    @app.post("/api/pedidos/{pedido_id}/cancelar", tags=["Pedidos"])
    async def cancelar_pedido(
        request: Request,
        pedido_id: str = Path(..., description="UUID del pedido a cancelar"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL))
    ):
        """
        Cancelar un pedido (cambiar estado a CANCELADO y notificar a EL RAYO).

        **Usado desde:** Vista Redistribucion, boton "Cancelar Pedido".

        **Comportamiento:**
        - Cambia el estado del pedido a CANCELADO (estado_id = 19).
        - Envia correo a EL RAYO notificando la cancelacion.
        - **No elimina** el pedido de la base de datos.

        **Restricciones:**
        - Solo permitido en estados anteriores a Confirmado redistribucion (estado_id < 10).
        - El boton debe estar deshabilitado desde Confirmado redistribucion en adelante.

        **Respuestas:**
        - **200**: Pedido cancelado correctamente, devuelve el pedido actualizado.
        - **404**: Pedido no encontrado.
        - **400**: Pedido no esta en estado permitido para cancelar.
        - **500**: Error interno.
        """
        return await _cancelar_pedido_handler(request, pedido_id, user)

    @app.delete("/api/pedidos/{pedido_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Pedidos"])
    async def descartar_o_cancelar_pedido(
        request: Request,
        pedido_id: str = Path(..., description="UUID del pedido a eliminar"),
        notificar_el_rayo: bool = Query(
            False,
            description="Si True, envia correo a EL RAYO notificando la cancelacion (usar solo desde 'Cancelar Pedido' en Redistribucion). Si False, determina automaticamente si notificar segun el estado del pedido.",
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_ODCSAP, _PERM_MABEL]))
    ):
        """
        Eliminar un pedido (Descartar o Cancelar Pedido).

        **Dos flujos en el frontend:**

        1. **Descartar (Cargar Plantilla)**: llamar sin `notificar_el_rayo` o con `notificar_el_rayo=false`.
           - Interfaz: `/cargar-plantilla/{numero_pedido}`
           - Estados permitidos: **BORRADOR (1)** y **NUEVO PEDIDO (2)**
           - Si el estado es **BORRADOR (1)**: NO envia email (solo elimina).
           - Si el estado es **NUEVO PEDIDO (2)**: envia email a EL RAYO notificando el descarte.

        2. **Cancelar Pedido (Redistribucion)**: llamar con `notificar_el_rayo=true`.
           - Interfaz: `/redistribucion`
           - Borra el pedido **y** envia correo a EL RAYO.
           - Permitido solo en estados **anteriores** a Confirmado redistribucion (estado_id < 10).

        **Nota:** Para eliminar desde **Detalle del Pedido** (estado GESTIONAR PEDIDO),
        usar el endpoint `/api/pedidos/{pedido_id}/eliminar` en su lugar.

        **Restricciones:**
        - No se permite si el pedido tiene respuesta de proveedor, redistribucion confirmada u orden de compra

        **Respuestas:**
        - **204**: Pedido eliminado correctamente
        - **400**: Pedido no esta en estado permitido
        - **404**: Pedido no encontrado
        - **409**: Pedido tiene informacion asociada
        """
        return await _descartar_o_cancelar_pedido_handler(request, pedido_id, notificar_el_rayo, user)

    @app.post("/api/pedidos/{pedido_id}/cancelar-por-el-rayo", tags=["Pedidos"])
    async def cancelar_pedido_por_el_rayo(
        request: Request,
        pedido_id: str = Path(..., description="UUID del pedido a cancelar"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_ODCSAP, _PERM_MABEL, _PERM_PRODUCCION_ELRAYO]))
    ):
        """
        Cancelar un pedido desde la interfaz de Detalle del Pedido (boton "Cancelar Pedido").

        **Uso exclusivo:**
        - Interfaz: **Detalle del Pedido** (`/pedidos/{pedido_id}`)
        - Estado permitido: **GESTIONAR PEDIDO (3)** unicamente
        - Comportamiento: Cambia estado a CANCELADO POR EL RAYO (20) y notifica a MABEL TRADING

        **Notificaciones:**
        - ✅ Se envia notificacion en tiempo real a MABEL TRADING

        **Diferencia con "Cancelar Pedido" de MABEL:**
        - "Cancelar Pedido" (MABEL): Desde Redistribucion, estados < 10, cambia a CANCELADO (19)
        - "Cancelar Pedido" (EL RAYO): Desde Detalle, estado 3 solamente, cambia a CANCELADO POR EL RAYO (20)

        **Respuestas:**
        - **200**: Pedido cancelado correctamente
        - **400**: Pedido no esta en estado GESTIONAR PEDIDO (3)
        - **404**: Pedido no encontrado
        """
        return await _cancelar_pedido_por_el_rayo_handler(request, pedido_id, user)
