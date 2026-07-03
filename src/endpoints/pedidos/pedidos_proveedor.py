"""
Endpoints de gestión de respuestas de proveedores.
"""

import logging
from typing import Dict
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Path, Body
from fastapi.responses import JSONResponse

from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission
from src.models import (
    FormularioProveedorResponse,
    RespuestaProveedorRequest,
    RespuestaProveedorResponse
)
from .utils import validate_excel_file, get_user_id, MAX_FILE_SIZE

logger = logging.getLogger(__name__)

_DESC_PEDIDO_ID = "UUID del pedido"
_PERM_MABEL_VIEW = 'mabel.view'


async def _handle_cargar_respuesta_proveedor(pedido_id: str, file: UploadFile, user: Dict):
    try:
        validate_excel_file(file)
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"El archivo excede el tamaño máximo permitido de {MAX_FILE_SIZE / 1024 / 1024} MB"
            )
        from src.database.services.pedido_proveedor_service import PedidoProveedorService
        service = PedidoProveedorService()
        usuario_id = get_user_id(user)
        resultado = service.importar_respuesta_proveedor(
            pedido_id=pedido_id,
            file_content=content,
            usuario_id=usuario_id
        )
        status_code = 200
        if resultado["status"] == "validation_error":
            status_code = 400
        return JSONResponse(status_code=status_code, content=resultado)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al cargar respuesta del proveedor: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al procesar respuesta: {str(e)}"
        )


async def _handle_obtener_formulario_proveedor(pedido_id: str, user: Dict):
    try:
        from src.database.services.pedido_proveedor_web_service import PedidoProveedorWebService
        service = PedidoProveedorWebService()
        formulario = service.obtener_formulario_proveedor(pedido_id)
        return JSONResponse(status_code=200, content=formulario)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Error al obtener formulario proveedor: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al obtener formulario: {str(e)}"
        )


async def _handle_enviar_respuesta_proveedor(
    pedido_id: str, respuesta: RespuestaProveedorRequest, user: Dict
):
    try:
        from src.database.services.pedido_proveedor_web_service import PedidoProveedorWebService
        service = PedidoProveedorWebService()
        usuario_id = get_user_id(user)
        productos_dict = [producto.model_dump() for producto in respuesta.productos]
        resultado = service.procesar_respuesta_proveedor_web(
            pedido_id=pedido_id,
            productos=productos_dict,
            observaciones_generales=respuesta.observaciones_generales,
            estado=respuesta.estado,
            usuario_id=usuario_id
        )
        status_code = 200
        if resultado["status"] == "validation_error":
            status_code = 400
        return JSONResponse(status_code=status_code, content=resultado)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Error al enviar respuesta del proveedor: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al procesar respuesta: {str(e)}"
        )


def _leer_estado_antes(pedido_id: str):
    from src.database.connection import get_db_connection_context
    from src.database.repositories.pedido_repository import PedidoRepository
    estado_id_antes = None
    with get_db_connection_context() as conn:
        repo = PedidoRepository(conn)
        pedido_antes = repo.get_pedido_completo(pedido_id)
        if pedido_antes and pedido_antes.get("cabecera"):
            eid = pedido_antes["cabecera"].get("estado_id")
            try:
                estado_id_antes = int(eid) if eid is not None else None
            except (TypeError, ValueError):
                estado_id_antes = None
    return estado_id_antes


async def _notificar_confirmacion_rayo(
    resultado: Dict, transicion_a_confirmado: bool, pedido_id: str, user: Dict
):
    if resultado.get("status") == "success" and transicion_a_confirmado:
        try:
            from src.utils.notification_manager import notification_manager, NotificationType
            from src.database.connection import get_db_connection_context as _get_conn
            from src.database.repositories.pedido_repository import PedidoRepository as _PedidoRepo
            with _get_conn() as _conn:
                _repo = _PedidoRepo(_conn)
                _pedido = _repo.get_pedido_completo(pedido_id)
                _num = (_pedido.get("cabecera") or {}).get("numero_pedido", "") if _pedido else ""
            _username = user.get("username") or user.get("sub") or "unknown"
            await notification_manager.notify_by_actor(
                actor_permission="odcsap.view",
                actor_username=_username,
                title="EL RAYO confirmó tu pedido",
                message=f"El pedido {_num} ha sido confirmado por EL RAYO y está listo para redistribución.",
                notification_type=NotificationType.SUCCESS,
                metadata={"pedido_id": pedido_id, "numero_pedido": _num, "accion": "pedido_confirmado_rayo"},
            )
        except Exception as notif_err:
            logger.warning(f"⚠️ Error al enviar notificación en tiempo real: {notif_err}")


def _obtener_detalles_modificados(conn, pedido_id: str, resultado: Dict) -> int:
    from src.database.repositories.pedido_confirmacion_rayo_repository import PedidoConfirmacionRayoRepository
    detalles_modificados = 0
    try:
        repo_confirmacion = PedidoConfirmacionRayoRepository(conn)
        confirmaciones = repo_confirmacion.obtener_confirmaciones_por_pedido(pedido_id=pedido_id, limit=1)
        if confirmaciones:
            confirmacion_id = confirmaciones[0]["confirmacion_id"]
            confirmacion_completa = repo_confirmacion.obtener_confirmacion(confirmacion_id)
            if confirmacion_completa:
                detalles_modificados = confirmacion_completa.get("total_detalles_modificados", 0)
    except Exception as e:
        logger.warning(f"⚠️ No se pudo obtener detalles modificados de la confirmación: {e}")
        detalles_modificados = resultado.get("cantidades_guardadas", 0) + resultado.get("precios_guardados", 0)
    return detalles_modificados


def _enviar_email_segun_ambiente(pedido_id: str, numero_pedido, usuario_id, detalles_modificados: int):
    from src.utils.email_notifier_pedido import send_rayo_confirmacion_notification
    from src.config import EMAIL_PROVEEDOR_PRUEBAS, ENVIRONMENT
    if ENVIRONMENT == "development":
        email_enviado = send_rayo_confirmacion_notification(
            pedido_id=pedido_id,
            numero_pedido=numero_pedido,
            usuario_rayo=usuario_id,
            detalles_modificados=detalles_modificados,
            email_destino=EMAIL_PROVEEDOR_PRUEBAS,
        )
        destino_log = f"correo de prueba ({EMAIL_PROVEEDOR_PRUEBAS})"
    else:
        email_enviado = send_rayo_confirmacion_notification(
            pedido_id=pedido_id,
            numero_pedido=numero_pedido,
            usuario_rayo=usuario_id,
            detalles_modificados=detalles_modificados,
        )
        destino_log = "destinatarios MABEL_TRADING configurados"
    return email_enviado, destino_log


def _enviar_email_confirmacion_rayo(
    resultado: Dict, transicion_a_confirmado: bool, pedido_id: str, usuario_id
):
    if not (
        resultado.get("status") == "success"
        and resultado.get("confirmacion_registrada", False)
        and transicion_a_confirmado
    ):
        return
    try:
        from src.database.connection import get_db_connection_context
        from src.database.repositories.pedido_repository import PedidoRepository
        with get_db_connection_context() as conn:
            repo_pedido = PedidoRepository(conn)
            pedido_completo = repo_pedido.get_pedido_completo(pedido_id)
            if pedido_completo:
                numero_pedido = pedido_completo["cabecera"].get("numero_pedido", "N/A")
                detalles_modificados = _obtener_detalles_modificados(conn, pedido_id, resultado)
                email_enviado, destino_log = _enviar_email_segun_ambiente(
                    pedido_id, numero_pedido, usuario_id, detalles_modificados
                )
                if email_enviado:
                    logger.info(f"📧 Email de confirmación de El Rayo enviado a {destino_log} (Pedido: {numero_pedido})")
                else:
                    logger.warning("⚠️ No se pudo enviar email de confirmación de El Rayo (no crítico)")
            else:
                logger.warning("⚠️ No se pudo obtener información del pedido para enviar notificación (no crítico)")
    except Exception as e:
        logger.warning(f"⚠️ Error al enviar email de confirmación de El Rayo (no crítico): {e}")


async def _handle_crear_respuesta_desde_pedido(pedido_id: str, user: Dict):
    try:
        from src.database.services.pedido_proveedor_web_service import PedidoProveedorWebService
        from src.database.pedido_estados import ESTADO_REDISTRIBUCION

        usuario_id = get_user_id(user)
        estado_id_antes = _leer_estado_antes(pedido_id)

        logger.info(f"Guardando cambios y creando respuesta para pedido {pedido_id} (usuario: {usuario_id})")

        web_service = PedidoProveedorWebService()
        resultado = web_service.crear_respuesta_desde_pedido(
            pedido_id=pedido_id,
            usuario_id=usuario_id,
            observaciones_generales=None
        )

        logger.info(f"✅ Cambios guardados y respuesta creada para pedido {pedido_id}. Estado: CONFIRMADO")

        transicion_a_confirmado = estado_id_antes is not None and estado_id_antes != ESTADO_REDISTRIBUCION

        await _notificar_confirmacion_rayo(resultado, transicion_a_confirmado, pedido_id, user)
        _enviar_email_confirmacion_rayo(resultado, transicion_a_confirmado, pedido_id, usuario_id)

        return JSONResponse(status_code=200, content=resultado)
    except ValueError as e:
        error_msg = str(e)
        logger.error(f"❌ Error de validación al guardar cambios: {e}")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        logger.error(f"❌ Error al guardar cambios del pedido: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al guardar cambios del pedido: {str(e)}"
        )


def register_proveedor_endpoints(app: FastAPI):
    """Registra los endpoints de gestión de proveedores."""

    @app.post("/api/pedidos/{pedido_id}/cargar-respuesta-proveedor", tags=["Pedidos - Proveedor"])
    async def cargar_respuesta_proveedor(
        pedido_id: str = Path(..., description=_DESC_PEDIDO_ID),
        file: UploadFile = File(..., description="Archivo Excel con respuesta del proveedor"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL_VIEW))
    ):
        """Carga la respuesta del proveedor desde un archivo Excel."""
        return await _handle_cargar_respuesta_proveedor(pedido_id, file, user)

    @app.get("/api/pedidos/{pedido_id}/formulario-proveedor",
             response_model=FormularioProveedorResponse,
             tags=["Pedidos - Proveedor"])
    async def obtener_formulario_proveedor(
        pedido_id: str = Path(..., description=_DESC_PEDIDO_ID),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL_VIEW))
    ):
        """Obtiene los datos del pedido formateados para el formulario web del proveedor."""
        return await _handle_obtener_formulario_proveedor(pedido_id, user)

    @app.post("/api/pedidos/{pedido_id}/enviar-respuesta-proveedor",
              response_model=RespuestaProveedorResponse,
              tags=["Pedidos - Proveedor"])
    async def enviar_respuesta_proveedor(
        pedido_id: str = Path(..., description=_DESC_PEDIDO_ID),
        respuesta: RespuestaProveedorRequest = Body(...),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL_VIEW))
    ):
        """Recibe la respuesta del proveedor desde el formulario web."""
        return await _handle_enviar_respuesta_proveedor(pedido_id, respuesta, user)

    @app.post("/api/pedidos/{pedido_id}/crear-respuesta-desde-pedido",
              response_model=RespuestaProveedorResponse,
              tags=["Pedidos - Proveedor"])
    async def crear_respuesta_desde_pedido(
        pedido_id: str = Path(..., description=_DESC_PEDIDO_ID),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', _PERM_MABEL_VIEW]))
    ):
        """Guarda los cambios de EL RAYO, crea la respuesta del proveedor y deja el pedido en estado CONFIRMADO (confirmar = ir a redistribución)."""
        return await _handle_crear_respuesta_desde_pedido(pedido_id, user)
