"""
Endpoints de gestión de respuestas de proveedores.
"""

import asyncio
import logging
from typing import Dict, List, Optional
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Path, Body, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission
from src.models import (
    FormularioProveedorResponse,
    RespuestaProveedorRequest,
    RespuestaProveedorResponse
)
from .utils import validate_excel_file, get_user_id, MAX_FILE_SIZE
from .pedidos_crud_helpers import calcular_diferencia_produccion, get_estado_id_from_pedido

logger = logging.getLogger(__name__)

_DESC_PEDIDO_ID = "UUID del pedido"
_PERM_MABEL_VIEW = 'mabel.view'
_PERM_ODCSAP_VIEW = 'odcsap.view'


class DetalleAsignadoHijo(BaseModel):
    """Cantidad de una línea de la diferencia asignada a un pedido hijo específico."""
    pedido_detalle_id: str
    cantidad: float = Field(..., ge=0)


class HijoDiferenciaRequest(BaseModel):
    """Un pedido hijo a generar: su fecha de entrega y la porción de cada línea que se le asigna."""
    fecha_entrega: str
    detalles: List[DetalleAsignadoHijo]


class ConfirmarConDiferenciaRequest(BaseModel):
    """Req. 1.2 (+ N hijos): body de POST confirmar-con-diferencia. La diferencia de
    cada línea se reparte entre uno o más pedidos hijo, cada uno con su propia fecha
    de entrega; el reparto debe cubrir exactamente el 100% de cada línea (se valida
    en _handle_confirmar_con_diferencia)."""
    hijos: List[HijoDiferenciaRequest] = Field(..., min_length=1)


class ConfirmarRespuestaRequest(BaseModel):
    """Req. 1.2 (endurecimiento 2026-08-17): body opcional de POST crear-respuesta-desde-pedido.
    diferencia_reconocida=true indica que el cliente ya mostró el modal de diferencia de
    producción y el usuario decidió confirmar sin generar pedido hijo ('Diferencia no será
    entregada'). Sin este campo (o en false), el endpoint rechaza la confirmación si detecta
    una diferencia -- ver _handle_crear_respuesta_desde_pedido."""
    diferencia_reconocida: bool = Field(False, description="True si el usuario ya reconoció la diferencia de producción mostrada en el modal")


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
        resultado = await asyncio.to_thread(
            service.importar_respuesta_proveedor,
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


async def _handle_obtener_formulario_proveedor(pedido_id: str):
    try:
        from src.database.services.pedido_proveedor_web_service import PedidoProveedorWebService
        service = PedidoProveedorWebService()
        formulario = await asyncio.to_thread(service.obtener_formulario_proveedor, pedido_id)
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
        resultado = await asyncio.to_thread(
            service.procesar_respuesta_proveedor_web,
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


def _db_numero_pedido_para_notificacion(pedido_id: str) -> str:
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    from src.database.connection import get_db_connection_context as _get_conn
    from src.database.repositories.pedido_repository import PedidoRepository as _PedidoRepo
    with _get_conn() as _conn:
        _repo = _PedidoRepo(_conn)
        _pedido = _repo.get_pedido_completo(pedido_id)
        return (_pedido.get("cabecera") or {}).get("numero_pedido", "") if _pedido else ""


async def _notificar_confirmacion_rayo(
    resultado: Dict, transicion_a_confirmado: bool, pedido_id: str, user: Dict,
    numeros_pedido_hijo: Optional[List[str]] = None,
):
    """Notificación SSE de 'EL RAYO confirmó tu pedido'. Un solo tipo de mensaje cuando el
    pedido se confirma solo, y otro cuando la confirmación generó pedido(s) hijo por
    diferencia de producción (ver _handle_confirmar_con_diferencia) -- misma notificación
    del padre, mencionando al/los hijo(s) en vez de una notificación separada por cada uno."""
    if resultado.get("status") == "success" and transicion_a_confirmado:
        try:
            from src.utils.notification_manager import notification_manager, NotificationType
            _num = await asyncio.to_thread(_db_numero_pedido_para_notificacion, pedido_id)
            _username = user.get("username") or user.get("sub") or "unknown"
            if numeros_pedido_hijo:
                _sufijo = "s" if len(numeros_pedido_hijo) != 1 else ""
                mensaje = (
                    f"El pedido {_num} ha sido confirmado por EL RAYO y está listo para "
                    f"redistribución. Se generó {len(numeros_pedido_hijo)} pedido{_sufijo} con "
                    f"la diferencia: {', '.join(numeros_pedido_hijo)}."
                )
            else:
                mensaje = f"El pedido {_num} ha sido confirmado por EL RAYO y está listo para redistribución."
            await notification_manager.notify_by_actor(
                actor_permission="odcsap.view",
                actor_username=_username,
                title="EL RAYO confirmó tu pedido",
                message=mensaje,
                notification_type=NotificationType.SUCCESS,
                metadata={
                    "pedido_id": pedido_id,
                    "numero_pedido": _num,
                    "accion": "pedido_confirmado_rayo",
                    "numeros_pedido_hijo": numeros_pedido_hijo or [],
                },
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


def _enviar_email_segun_ambiente(
    pedido_id: str, numero_pedido, usuario_id, detalles_modificados: int,
    numeros_pedido_hijo: Optional[List[str]] = None,
):
    from src.utils.email_notifier_pedido import send_rayo_confirmacion_notification
    from src.config import EMAIL_PROVEEDOR_PRUEBAS, ENVIRONMENT
    if ENVIRONMENT == "development":
        email_enviado = send_rayo_confirmacion_notification(
            pedido_id=pedido_id,
            numero_pedido=numero_pedido,
            usuario_rayo=usuario_id,
            detalles_modificados=detalles_modificados,
            email_destino=EMAIL_PROVEEDOR_PRUEBAS,
            numeros_pedido_hijo=numeros_pedido_hijo,
        )
        destino_log = f"correo de prueba ({EMAIL_PROVEEDOR_PRUEBAS})"
    else:
        email_enviado = send_rayo_confirmacion_notification(
            pedido_id=pedido_id,
            numero_pedido=numero_pedido,
            usuario_rayo=usuario_id,
            detalles_modificados=detalles_modificados,
            numeros_pedido_hijo=numeros_pedido_hijo,
        )
        destino_log = "destinatarios MABEL_TRADING configurados"
    return email_enviado, destino_log


def _enviar_email_confirmacion_rayo(
    resultado: Dict, transicion_a_confirmado: bool, pedido_id: str, usuario_id,
    numeros_pedido_hijo: Optional[List[str]] = None,
):
    """numeros_pedido_hijo: números de los pedidos "hijo" generados con la diferencia
    (solo lo pasa _handle_confirmar_con_diferencia); agrega la sección "Acción
    Requerida" al correo guiando a MABEL TRADING a revisarlos en Cargar Plantilla."""
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
                    pedido_id, numero_pedido, usuario_id, detalles_modificados,
                    numeros_pedido_hijo=numeros_pedido_hijo,
                )
                if email_enviado:
                    logger.info(f"📧 Email de confirmación de El Rayo enviado a {destino_log} (Pedido: {numero_pedido})")
                else:
                    logger.warning("⚠️ No se pudo enviar email de confirmación de El Rayo (no crítico)")
            else:
                logger.warning("⚠️ No se pudo obtener información del pedido para enviar notificación (no crítico)")
    except Exception as e:
        logger.warning(f"⚠️ Error al enviar email de confirmación de El Rayo (no crítico): {e}")


async def _handle_crear_respuesta_desde_pedido(pedido_id: str, user: Dict, diferencia_reconocida: bool = False):
    try:
        from src.database.services.pedido_proveedor_web_service import PedidoProveedorWebService
        from src.database.pedido_estados import ESTADO_REDISTRIBUCION

        usuario_id = get_user_id(user)
        estado_id_antes = await asyncio.to_thread(_leer_estado_antes, pedido_id)

        # Req. 1.2 (endurecimiento): antes esta regla solo vivía como gate de UI (el
        # frontend consultaba GET /diferencia-produccion y decidía si mostrar el modal
        # antes de llamar aquí). Cualquier llamada directa a este endpoint -- otro
        # cliente, un bug futuro del frontend, o simplemente una migración de BD
        # pendiente que dejaba cantidad_solicitada_original en NULL -- se saltaba el
        # control por completo. Se repite la misma verificación aquí, del lado del
        # servidor, para que no dependa de que el llamador haya preguntado antes.
        pedido_actual = await asyncio.to_thread(_db_obtener_pedido_completo, pedido_id)
        if pedido_actual:
            diferencia = calcular_diferencia_produccion(pedido_actual.get("detalles", []))
            if diferencia["tiene_diferencia"] and not diferencia_reconocida:
                raise HTTPException(status_code=400, detail={
                    "error": "diferencia_produccion_no_reconocida",
                    "message": "El pedido tiene productos con Total por debajo de la cantidad solicitada originalmente. Usa el flujo de diferencia de producción (modal) para confirmar.",
                    "detalles": diferencia["detalles"],
                })

        logger.info(f"Guardando cambios y creando respuesta para pedido {pedido_id} (usuario: {usuario_id})")

        web_service = PedidoProveedorWebService()
        resultado = await asyncio.to_thread(
            web_service.crear_respuesta_desde_pedido,
            pedido_id=pedido_id,
            usuario_id=usuario_id,
            observaciones_generales=None
        )

        logger.info(f"✅ Cambios guardados y respuesta creada para pedido {pedido_id}. Estado: CONFIRMADO")

        transicion_a_confirmado = estado_id_antes is not None and estado_id_antes != ESTADO_REDISTRIBUCION

        await _notificar_confirmacion_rayo(resultado, transicion_a_confirmado, pedido_id, user)
        await asyncio.to_thread(
            _enviar_email_confirmacion_rayo, resultado, transicion_a_confirmado, pedido_id, usuario_id
        )

        return JSONResponse(status_code=200, content=resultado)
    except HTTPException:
        raise
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


def _db_obtener_pedido_completo(pedido_id: str):
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    from src.database.connection import get_db_connection_context
    from src.database.repositories.pedido_repository import PedidoRepository
    with get_db_connection_context() as conn:
        repo = PedidoRepository(conn)
        return repo.get_pedido_completo(pedido_id)


async def _handle_obtener_diferencia_produccion(pedido_id: str):
    """Req. 1.2: GET de solo lectura que el frontend consulta justo al hacer clic en
    'Confirmar', antes de decidir si mostrar el modal de diferencia de producción."""
    pedido = await asyncio.to_thread(_db_obtener_pedido_completo, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail={"error": "pedido_not_found", "message": f"No se encontró el pedido: {pedido_id}"})
    resultado = calcular_diferencia_produccion(pedido.get("detalles", []))
    return JSONResponse(status_code=200, content=resultado)


def _db_crear_pedido_hijo_diferencia(pedido_padre, detalles_con_diferencia, nueva_fecha_entrega, usuario_id, audit):
    """Consulta bloqueante (pyodbc); se ejecuta vía asyncio.to_thread."""
    from src.database.services.pedido_service import PedidoService
    service = PedidoService()
    return service.crear_pedido_hijo_diferencia(
        pedido_padre=pedido_padre,
        detalles_con_diferencia=detalles_con_diferencia,
        nueva_fecha_entrega=nueva_fecha_entrega,
        usuario_id=usuario_id,
        audit_context=audit,
    )


_TOLERANCIA_REPARTO = 0.001


def _validar_reparto_diferencia(diferencia_detalles: List[Dict], hijos: List["HijoDiferenciaRequest"]) -> None:
    """Cada línea de la diferencia debe quedar cubierta exactamente (ni de más ni de
    menos) por la suma de lo asignado a todos los hijos. Las cantidades son unidades
    de producto: no se aceptan valores fraccionados."""
    asignado_por_detalle: Dict[str, float] = {}
    for hijo in hijos:
        for d in hijo.detalles:
            if not float(d.cantidad).is_integer():
                raise HTTPException(status_code=400, detail={
                    "error": "cantidad_fraccionada",
                    "message": f"La cantidad asignada ({d.cantidad}) no puede ser fraccionada; debe ser un número entero."
                })
            asignado_por_detalle[d.pedido_detalle_id] = asignado_por_detalle.get(d.pedido_detalle_id, 0.0) + d.cantidad

    for detalle in diferencia_detalles:
        pedido_detalle_id = detalle["pedido_detalle_id"]
        esperado = detalle["diferencia"]
        asignado = asignado_por_detalle.get(pedido_detalle_id, 0.0)
        if abs(asignado - esperado) > _TOLERANCIA_REPARTO:
            raise HTTPException(status_code=400, detail={
                "error": "reparto_invalido",
                "message": (
                    f"El reparto de '{detalle.get('codigo_interno') or pedido_detalle_id}' debe sumar "
                    f"{esperado} entre todos los pedidos hijo (suma actual: {asignado})."
                )
            })


def _construir_detalles_para_hijo(hijo_req, diferencia_por_detalle_id: Dict) -> List[Dict]:
    """Arma la lista de detalles (pedido_detalle_id, cantidad_solicitada_original,
    diferencia) para un pedido hijo, ignorando asignaciones con cantidad <= 0 o sin
    diferencia registrada para esa línea. Usado por `_handle_confirmar_con_diferencia`."""
    detalles_para_hijo = []
    for asignado in hijo_req.detalles:
        if asignado.cantidad <= 0:
            continue
        detalle_diferencia = diferencia_por_detalle_id.get(asignado.pedido_detalle_id)
        if not detalle_diferencia:
            continue
        detalles_para_hijo.append({
            "pedido_detalle_id": asignado.pedido_detalle_id,
            "cantidad_solicitada_original": detalle_diferencia["cantidad_solicitada_original"],
            "diferencia": asignado.cantidad,
        })
    return detalles_para_hijo


async def _handle_confirmar_con_diferencia(pedido_id: str, body: ConfirmarConDiferenciaRequest, request, user: Dict):
    """Req. 1.2 (+ N hijos): opción 'Confirmar pedido, generar nuevo pedido con la
    diferencia' del modal de diferencia de producción. El pedido padre sigue el flujo
    normal de confirmación (igual que 'Diferencia no será entregada'/
    crear-respuesta-desde-pedido, una sola vez) y además se crea un pedido hijo por
    cada elemento de body.hijos, cada uno en estado PRODUCCION POSPUESTA con la
    porción de la diferencia y la fecha de entrega que le correspondan.

    La notificación de confirmación reutiliza el mismo correo "Pedido Confirmado por
    El Rayo" (_enviar_email_confirmacion_rayo) que usan los otros dos casos de
    confirmación, una sola vez para el pedido padre -- en vez de un correo "Diferencia
    en Pedido" separado por cada hijo generado."""
    from src.database.services.pedido_proveedor_web_service import PedidoProveedorWebService
    from src.database.pedido_estados import ESTADO_REDISTRIBUCION
    from src.utils.audit_context import get_audit_context, ORIGEN_WEB

    usuario_id = get_user_id(user)
    audit = get_audit_context(request, user, origen=ORIGEN_WEB)

    pedido_padre = await asyncio.to_thread(_db_obtener_pedido_completo, pedido_id)
    if not pedido_padre:
        raise HTTPException(status_code=404, detail={"error": "pedido_not_found", "message": f"No se encontró el pedido: {pedido_id}"})

    diferencia = calcular_diferencia_produccion(pedido_padre.get("detalles", []))
    if not diferencia["tiene_diferencia"]:
        raise HTTPException(status_code=400, detail={
            "error": "sin_diferencia",
            "message": "El pedido no tiene productos con total por debajo de la cantidad solicitada original."
        })

    _validar_reparto_diferencia(diferencia["detalles"], body.hijos)

    estado_id_antes = get_estado_id_from_pedido(pedido_padre)
    transicion_a_confirmado = estado_id_antes is not None and estado_id_antes != ESTADO_REDISTRIBUCION

    try:
        web_service = PedidoProveedorWebService()
        resultado_confirmacion = await asyncio.to_thread(
            web_service.crear_respuesta_desde_pedido,
            pedido_id=pedido_id,
            usuario_id=usuario_id,
            observaciones_generales=None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    diferencia_por_detalle_id = {d["pedido_detalle_id"]: d for d in diferencia["detalles"]}
    resultados_hijos: List[Dict] = []

    for hijo_req in body.hijos:
        detalles_para_hijo = _construir_detalles_para_hijo(hijo_req, diferencia_por_detalle_id)

        if not detalles_para_hijo:
            logger.warning(f"⚠️ Pedido hijo sin líneas asignadas al confirmar diferencia de {pedido_id}; se omite")
            continue

        resultado_hijo = await asyncio.to_thread(
            _db_crear_pedido_hijo_diferencia,
            pedido_padre, detalles_para_hijo, hijo_req.fecha_entrega, usuario_id, audit,
        )
        resultados_hijos.append(resultado_hijo)

    _numeros_hijo = [r["numero_pedido"] for r in resultados_hijos] or None
    await _notificar_confirmacion_rayo(
        resultado_confirmacion, transicion_a_confirmado, pedido_id, user,
        numeros_pedido_hijo=_numeros_hijo,
    )
    await asyncio.to_thread(
        _enviar_email_confirmacion_rayo, resultado_confirmacion, transicion_a_confirmado, pedido_id, usuario_id,
        numeros_pedido_hijo=_numeros_hijo,
    )

    logger.info(
        f"✅ Pedido {pedido_id} confirmado con diferencia por usuario {user.get('username', 'UNKNOWN')}; "
        f"{len(resultados_hijos)} pedido(s) hijo creado(s): "
        f"{', '.join(r['numero_pedido'] for r in resultados_hijos)}"
    )

    return JSONResponse(status_code=200, content={
        "status": "success",
        "confirmacion": resultado_confirmacion,
        "pedidos_hijos": resultados_hijos,
    })


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
        return await _handle_obtener_formulario_proveedor(pedido_id)

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
        body: Optional[ConfirmarRespuestaRequest] = Body(default=None),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', _PERM_MABEL_VIEW]))
    ):
        """Guarda los cambios de EL RAYO, crea la respuesta del proveedor y deja el pedido en
        estado CONFIRMADO (confirmar = ir a redistribución).

        Req. 1.2 (endurecimiento 2026-08-17): rechaza (400, error
        'diferencia_produccion_no_reconocida') si el pedido tiene productos con Total por
        debajo de cantidad_solicitada_original y el body no envía diferencia_reconocida=true.
        Antes esta regla vivía solo como gate de UI -- ver
        docs/requeriments/PYTD002_ODC-MABEL-RAYO_SEGUIMIENTO.md.
        """
        diferencia_reconocida = body.diferencia_reconocida if body else False
        return await _handle_crear_respuesta_desde_pedido(pedido_id, user, diferencia_reconocida)

    @app.get("/api/pedidos/{pedido_id}/diferencia-produccion", tags=["Pedidos - Proveedor"])
    async def obtener_diferencia_produccion(
        pedido_id: str = Path(..., description=_DESC_PEDIDO_ID),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_ODCSAP_VIEW, _PERM_MABEL_VIEW]))
    ):
        """
        Req. 1.2 (pedidos parciales): indica si algún producto del pedido tiene un
        Total actual por debajo de la cantidad_solicitada_original (plantilla Excel).
        El frontend lo consulta al hacer clic en "Confirmar" para decidir si mostrar
        el modal de diferencia de producción.
        """
        return await _handle_obtener_diferencia_produccion(pedido_id)

    @app.post("/api/pedidos/{pedido_id}/confirmar-con-diferencia", tags=["Pedidos - Proveedor"])
    async def confirmar_con_diferencia(
        request: Request,
        pedido_id: str = Path(..., description=_DESC_PEDIDO_ID),
        body: ConfirmarConDiferenciaRequest = Body(...),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission([_PERM_ODCSAP_VIEW, _PERM_MABEL_VIEW]))
    ):
        """
        Req. 1.2 (pedidos parciales, + N hijos): opción "Confirmar pedido, generar
        nuevo pedido con la diferencia" del modal de diferencia de producción. Confirma
        el pedido padre una sola vez (mismo flujo que crear-respuesta-desde-pedido,
        notificando por correo a MABEL_TRADING con "Pedido Confirmado por El Rayo",
        igual que los otros dos casos de confirmación) y crea uno o más pedidos hijo
        (numero_pedido = "<padre>.NN"), cada uno con la porción de la diferencia y la
        fecha de entrega indicadas en body.hijos, en estado PRODUCCION POSPUESTA. El
        reparto entre hijos debe cubrir exactamente el 100% de cada línea con
        diferencia (400 "reparto_invalido" si no cuadra). A diferencia de los otros dos
        casos, este correo incluye además una sección "Acción Requerida" con un enlace
        por cada pedido hijo generado, guiando a MABEL TRADING a revisarlos en Cargar
        Plantilla y decidir Aceptar/Rechazar.
        """
        return await _handle_confirmar_con_diferencia(pedido_id, body, request, user)
