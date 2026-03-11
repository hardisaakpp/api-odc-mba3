"""Endpoint de proceso completo SAP para redistribución.

NOTA DE RENDIMIENTO:
    Toda la lógica síncrona pesada (BD, SAP Service Layer, email SMTP)
    se ejecuta en un thread separado via asyncio.to_thread() para NO
    bloquear el event loop de asyncio. Esto permite que SSE heartbeats,
    polling y otras peticiones se procesen normalmente mientras este
    endpoint trabaja (~40 segundos de operaciones síncronas).

    Para ejecución en segundo plano (Celery), usar POST .../proceso-completo-sap-async
    y consultar GET .../proceso-sap/resultado/{process_id} o .../proceso-sap/stream/{process_id}.
"""

import asyncio
import json
import logging
from typing import Dict, List

from fastapi import FastAPI, Depends, HTTPException, Path, Body, Query, status, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.utils.timezone import ahora_naive
from src.database.connection import get_db_connection_context
from src.database.pedido_estados import ESTADO_PEDIDO_CONFIRMADO, ESTADO_CONFIRMADO_ENVIADO
from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.services.proceso_estado_service import ProcesoEstadoService
from src.database.services.redistribucion_validator import RedistribucionValidator
from src.security.jwt_auth import verify_jwt_token, require_permission
from src.utils.audit_context import AuditContext, get_audit_context, ORIGEN_WEB
from src.models import (
    RedistribucionConfirmarRequest,
    ProcesoCompletoSAPResponse,
    ProcesoCompletoSAPDetalleODC,
)
from ..utils import get_user_id
from ._helpers import obtener_pedido_o_404, obtener_respuestas_proveedor
from ._converters import convertir_ajustes_a_redistribucion
from ._resumen import calcular_resumen_confirmacion
from ._sap_processing import procesar_pedido_sap_con_homologacion_sync
from ._notifications import notificar_odc_enviada_a_sap

logger = logging.getLogger(__name__)

# Timeout para comprobar si hay workers Celery (evitar 202 sin worker y polling colgado)
CELERY_WORKER_PING_TIMEOUT = 2.5


def _celery_workers_available() -> bool:
    """
    Comprueba si hay al menos un worker Celery disponible.
    Si no hay workers o hay error/timeout, retorna False (priorizar flujo síncrono).
    """
    try:
        from src.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=CELERY_WORKER_PING_TIMEOUT)
        result = inspect.ping()
        available = bool(result and len(result) > 0)
        if not available:
            logger.debug("No hay workers Celery disponibles (ping sin respuesta)")
        return available
    except Exception as e:
        logger.debug("Comprobación de workers Celery fallida: %s", e)
        return False


def _ejecutar_proceso_completo_sync(
    numero_pedido: str,
    ajustes_detalle: List,
    user_id: str,
    audit: AuditContext,
) -> dict:
    """
    Ejecuta toda la lógica síncrona del proceso completo SAP.

    Se ejecuta en un thread separado (asyncio.to_thread) para NO bloquear
    el event loop de asyncio durante:
      - Consultas a BD (pyodbc sync)
      - Llamadas HTTP a SAP Service Layer (requests sync)
      - Envío de emails SMTP (smtplib sync)

    Returns:
        dict con:
          - 'response': ProcesoCompletoSAPResponse listo para retornar
          - '_notify_sap': bool indicando si enviar notificación SSE
          - '_notify_data': dict con datos para la notificación SSE

    Raises:
        HTTPException: errores de validación o internos que se propagan al cliente.
    """
    import threading
    _worker_thread = threading.current_thread().name
    logger.info(f"🧵 Ejecutando en thread: {_worker_thread} (NO es el event loop)")

    resultado_redistribucion = None
    resultado_odc = None
    resumen = None
    pedido_id = None

    with get_db_connection_context() as conn:
        repo_pedido = PedidoRepository(conn)
        repo_dist = DistribucionConfirmadaRepository(conn)

        pedido_data = obtener_pedido_o_404(repo_pedido, numero_pedido, es_numero=True)
        pedido_id = pedido_data["cabecera"]["pedido_id"]

        # ── PASO 1/3: Confirmando redistribución ──────────────────────
        logger.info("📋 PASO 1/3: Confirmando redistribución...")

        try:
            productos_redistribucion = convertir_ajustes_a_redistribucion(
                ajustes_detalle,
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

            resultado_crear = repo_dist.crear_redistribucion(
                pedido_id=pedido_id,
                productos_redistribucion=productos_redistribucion,
                usuario=user_id,
                audit_context=audit
            )

            repo_dist.confirmar_redistribucion(
                pedido_id=pedido_id,
                version=resultado_crear["version"],
                usuario=user_id,
                audit_context=audit
            )

            repo_pedido.update_estado(pedido_id, ESTADO_PEDIDO_CONFIRMADO, audit_context=audit)

            resumen = calcular_resumen_confirmacion(ajustes_detalle)
            total_productos = resumen.total_productos

            resultado_redistribucion = {
                "version_confirmada": resultado_crear["version"],
                "productos_redistribuidos": total_productos,
                "estado_pedido": "CONFIRMADO REDISTRIBUCION"
            }

            logger.info(f"✅ PASO 1/3 completado: Redistribución confirmada (versión {resultado_crear['version']})")

            # Procesamiento SAP (homologación) - síncrono, OK porque estamos en thread
            try:
                resultado_sap = procesar_pedido_sap_con_homologacion_sync(
                    pedido_id=pedido_id,
                    user_id=user_id,
                    conn=conn,
                    logger=logger,
                )
                logger.info(
                    "   Procesamiento SAP: %s productos procesados",
                    resultado_sap.get("productos_procesados", 0),
                )
            except Exception as sap_error:
                logger.warning(f"⚠️ Error en procesamiento SAP (no crítico): {sap_error}")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error en PASO 1 (Redistribución): {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "redistribucion_error",
                    "message": f"Error al confirmar redistribución: {str(e)}",
                    "paso_fallido": "redistribucion"
                }
            )

        # ── PASO 2/3: Generando ODC ──────────────────────────────────
        logger.info("📦 PASO 2/3: Generando ODC...")

        try:
            from src.database.services.pedido_oc_service import PedidoOCService

            service = PedidoOCService()
            resultado_oc = service.crear_oc_desde_pedido_confirmado(
                pedido_id=pedido_id,
                usuario_id=user_id
            )

            oc_id = resultado_oc.get("oc_id")
            if not oc_id:
                raise ValueError("El servicio no retornó un oc_id válido")

            resultado_odc = {
                "oc_id": oc_id,
                "proveedor": resultado_oc.get("proveedor"),
                "detalles_insertados": resultado_oc.get("detalles_insertados", 0),
                "estado": "PENDIENTE"
            }

            logger.info(f"✅ PASO 2/3 completado: ODC generada (ID: {oc_id[:8]}...)")

        except Exception as e:
            logger.error(f"❌ Error en PASO 2 (Generar ODC): {e}", exc_info=True)
            return {
                "_notify_sap": False,
                "_notify_data": {},
                "response": ProcesoCompletoSAPResponse(
                    status="partial",
                    message=f"Redistribución exitosa, pero falló la generación de ODC: {str(e)}",
                    pedido_id=pedido_id,
                    numero_pedido=numero_pedido,
                    redistribucion=resultado_redistribucion,
                    odc_generada=None,
                    envio_sap=None,
                    resumen=resumen,
                    fecha_proceso=ahora_naive(),
                    paso_fallido="generar_odc",
                    error_detalle=str(e)
                )
            }

        # ── PASO 3/3: Enviando ODC a SAP ─────────────────────────────
        logger.info("🚀 PASO 3/3: Enviando ODC a SAP...")

        try:
            from src.database.services.oc_sap_service import OCSAPService
            from src.database.repositories.orden_compra_repository import OrdenCompraRepository

            oc_repo = OrdenCompraRepository(conn)
            oc_sap_service = OCSAPService()

            resultado_sap_envio = oc_sap_service.enviar_oc_a_sap(
                oc_repo=oc_repo,
                oc_id=oc_id,
                warehouse_code=None
            )

            success = resultado_sap_envio.get("success", False)
            doc_entry = resultado_sap_envio.get("doc_entry")
            doc_num_po = resultado_sap_envio.get("doc_num")  # DocNum de la PO en SAP
            error = resultado_sap_envio.get("error")
            error_code = resultado_sap_envio.get("error_code")

            # DocNum a mostrar en UI: preferir el de la Solicitud de Transferencia (ITR), ej. 70214643
            doc_num = doc_num_po
            st = resultado_sap_envio.get("solicitudes_transferencia") or {}
            resultados_st = st.get("resultados") or []
            if resultados_st and resultados_st[0].get("doc_num") is not None:
                doc_num = resultados_st[0]["doc_num"]

            # Para el modal: lista solo doc_num + tienda_codigo (como en el correo), una fila por ITR
            st_raw = resultado_sap_envio.get("solicitudes_transferencia") or {}
            solicitudes_para_response = dict(st_raw) if st_raw else None
            if solicitudes_para_response and solicitudes_para_response.get("resultados"):
                solicitudes_para_response["itrs_por_tienda"] = [
                    {
                        "doc_num": r.get("doc_num"),
                        "tienda_codigo": (r.get("tienda_codigo") or ""),
                    }
                    for r in solicitudes_para_response["resultados"]
                ]

            # Num ODC para el modal: valor de orden_compra_cabecera.numero_oc_sap (PO en SAP, ej. 22530)
            # DocNum en el modal: número de documento ITR (ej. 70214734) — no confundir con numero_oc_sap
            numero_oc_sap_cabecera = None
            try:
                oc_cabecera = oc_repo.get_existing_cabecera(oc_id)
                if oc_cabecera and oc_cabecera.get("numero_oc_sap") is not None:
                    numero_oc_sap_cabecera = str(oc_cabecera["numero_oc_sap"])
            except Exception:
                pass
            # Fallback: si la cabecera no trae numero_oc_sap, usar el DocNum de la PO que devolvió SAP
            if numero_oc_sap_cabecera is None and doc_num_po is not None:
                numero_oc_sap_cabecera = str(doc_num_po)

            resultado_envio_sap = ProcesoCompletoSAPDetalleODC(
                oc_id=oc_id,
                proveedor=resultado_odc.get("proveedor"),
                success=success,
                numero_oc_sap=numero_oc_sap_cabecera,
                doc_entry=doc_entry,
                doc_num=doc_num,
                error=error,
                error_code=error_code,
                solicitudes_transferencia=solicitudes_para_response,
            )

            if success:
                logger.info(f"✅ PASO 3/3 completado: ODC enviada a SAP (DocNum: {doc_num})")

                # Actualizar pedido a "Confirmado y enviado" (ODC enviada a SAP correctamente)
                repo_pedido.update_estado(pedido_id, ESTADO_CONFIRMADO_ENVIADO, audit_context=audit)
                logger.debug(f"✅ Estado actualizado para pedido {pedido_id}: estado_id={ESTADO_CONFIRMADO_ENVIADO} (Confirmado y enviado)")

                # Enviar email de confirmación (síncrono - OK, estamos en thread)
                try:
                    from src.utils.email_notifier import send_mabel_redistribucion_confirmacion_notification
                    send_mabel_redistribucion_confirmacion_notification(
                        pedido_id=pedido_id,
                        numero_pedido=numero_pedido,
                        usuario_mabel=user_id,
                        version_confirmada=resultado_redistribucion.get("version_confirmada"),
                        total_productos=resumen.total_productos if resumen else 0,
                        total_cantidad_ajustada=resumen.total_cantidad_ajustada if resumen else 0
                    )
                except Exception:
                    pass

                num_itr = (solicitudes_para_response or {}).get("transferencias_creadas") or 0
                if num_itr == 1:
                    message_success = f"Proceso completado exitosamente. ODC enviada a SAP con DocNum: {doc_num}"
                else:
                    message_success = "Proceso completado exitosamente. ODC y solicitudes de transferencia enviadas a SAP"

                return {
                    "_notify_sap": True,
                    "_notify_data": {
                        "pedido_id": pedido_id,
                        "numero_pedido": numero_pedido,
                        "doc_num": str(doc_num) if doc_num else None,
                    },
                    "response": ProcesoCompletoSAPResponse(
                        status="success",
                        message=message_success,
                        pedido_id=pedido_id,
                        numero_pedido=numero_pedido,
                        redistribucion=resultado_redistribucion,
                        odc_generada=resultado_odc,
                        envio_sap=resultado_envio_sap,
                        solicitudes_transferencia=solicitudes_para_response,
                        resumen=resumen,
                        fecha_proceso=ahora_naive(),
                        paso_fallido=None,
                        error_detalle=None
                    )
                }
            else:
                logger.error(f"❌ PASO 3/3 fallido: Error al enviar ODC a SAP: {error}")

                return {
                    "_notify_sap": False,
                    "_notify_data": {},
                    "response": ProcesoCompletoSAPResponse(
                        status="partial",
                        message=f"Redistribución y ODC generadas, pero falló el envío a SAP: {error}",
                        pedido_id=pedido_id,
                        numero_pedido=numero_pedido,
                        redistribucion=resultado_redistribucion,
                        odc_generada=resultado_odc,
                        envio_sap=resultado_envio_sap,
                        solicitudes_transferencia=solicitudes_para_response,
                        resumen=resumen,
                        fecha_proceso=ahora_naive(),
                        paso_fallido="envio_sap",
                        error_detalle=error
                    )
                }

        except Exception as e:
            logger.error(f"❌ Error en PASO 3 (Enviar a SAP): {e}", exc_info=True)

            return {
                "_notify_sap": False,
                "_notify_data": {},
                "response": ProcesoCompletoSAPResponse(
                    status="partial",
                    message=f"Redistribución y ODC generadas, pero falló el envío a SAP: {str(e)}",
                    pedido_id=pedido_id,
                    numero_pedido=numero_pedido,
                    redistribucion=resultado_redistribucion,
                    odc_generada=resultado_odc,
                    envio_sap=None,
                    resumen=resumen,
                    fecha_proceso=ahora_naive(),
                    paso_fallido="envio_sap",
                    error_detalle=str(e)
                )
            }


def register_proceso_completo_endpoints(app: FastAPI):
    """Endpoint de proceso completo SAP (síncrono en thread y asíncrono con Celery)."""

    @app.post("/api/pedidos/{numero_pedido}/proceso-completo-sap",
             tags=["Pedidos - Redistribución"])
    async def proceso_completo_sap(
        request: Request,
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: RedistribucionConfirmarRequest = Body(..., description="Datos de redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """Proceso completo: Redistribución + Generar ODC + Enviar a SAP.

        La lógica pesada (BD, SAP, email) se ejecuta en un thread separado
        para no bloquear el event loop de asyncio (~40s de operaciones síncronas).
        Para ejecución en segundo plano con Celery, usar POST .../proceso-completo-sap-async.
        """
        user_id = get_user_id(user)

        logger.info("=" * 70)
        logger.info(f"🚀 PROCESO COMPLETO SAP iniciado para pedido: {numero_pedido}")
        logger.info(f"   Usuario: {user_id}")
        logger.info("=" * 70)

        # Construir contexto de auditoría ANTES de entrar al thread
        # (el objeto Request no es thread-safe)
        audit = get_audit_context(request, user, origen=ORIGEN_WEB)

        try:
            # ╔══════════════════════════════════════════════════════════════╗
            # ║ Ejecutar lógica pesada en thread separado para NO bloquear ║
            # ║ el event loop de asyncio (~40s de operaciones síncronas).  ║
            # ║ Esto permite que SSE heartbeats, polling y otras           ║
            # ║ peticiones HTTP sigan funcionando mientras se procesa.     ║
            # ╚══════════════════════════════════════════════════════════════╝
            import threading
            import time as _time

            _t0 = _time.monotonic()
            _main_thread = threading.current_thread().name
            logger.info(
                f"🧵 Delegando proceso pesado a thread separado "
                f"(event loop libre para SSE/heartbeats). Main thread: {_main_thread}"
            )

            resultado = await asyncio.to_thread(
                _ejecutar_proceso_completo_sync,
                numero_pedido,
                request_body.ajustes_detalle,
                user_id,
                audit,
            )

            _elapsed = _time.monotonic() - _t0
            logger.info(
                f"🧵 Thread completado en {_elapsed:.1f}s. "
                f"Event loop estuvo LIBRE durante ese tiempo."
            )

            # Enviar notificación SSE asíncrona si corresponde
            # (SSE usa asyncio.Queue, debe ejecutarse en el event loop)
            if resultado.get("_notify_sap"):
                try:
                    nd = resultado["_notify_data"]
                    await notificar_odc_enviada_a_sap(
                        nd["pedido_id"], nd["numero_pedido"], nd.get("doc_num")
                    )
                except Exception as notif_err:
                    logger.warning(f"⚠️ Error al enviar notificación SSE de ODC enviada a SAP: {notif_err}")

            return resultado["response"]

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error general en proceso completo SAP: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno en proceso completo SAP: {str(e)}",
                    "paso_fallido": "desconocido",
                    "error_detalle": str(e)
                }
            )

    # -------------------------------------------------------------------------
    # Proceso completo SAP en segundo plano (Celery) - mismo patrón que plantillas
    # -------------------------------------------------------------------------
    @app.post("/api/pedidos/{numero_pedido}/proceso-completo-sap-async",
              tags=["Pedidos - Redistribución"])
    async def proceso_completo_sap_async(
        request: Request,
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: RedistribucionConfirmarRequest = Body(..., description="Datos de redistribución"),
        force_sync: bool = Query(
            False,
            description="Si True, ejecuta en primer plano y devuelve 200 con el resultado (útil si el worker no está disponible)"
        ),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Encola el proceso completo SAP (Redistribución + ODC + Envío a SAP) en Celery.

        Responde de inmediato con 202 y process_id. El resultado se consulta con
        GET /api/pedidos/proceso-sap/resultado/{process_id} o
        GET /api/pedidos/proceso-sap/stream/{process_id}.

        Si Redis/Celery no están disponibles o no hay workers, se ejecuta automáticamente
        en primer plano y se devuelve 200 con el resultado ("fallback": "sync",
        process_id: null, async: false). Con force_sync=true se ejecuta siempre en
        primer plano (200 + resultado, misma forma que sync).
        """
        user_id = get_user_id(user)
        run_async = not force_sync

        # Si no hay workers Celery, usar flujo síncrono (evitar 202 y polling colgado)
        if run_async and not _celery_workers_available():
            logger.info(
                "No hay workers Celery disponibles. Ejecutando proceso SAP en primer plano (fallback sync)."
            )
            run_async = False

        if run_async:
            try:
                estado_service = ProcesoEstadoService()
                process_id = estado_service.crear_proceso_sap(user_id=user_id, numero_pedido=numero_pedido)
                ajustes_serialized = [
                    a.model_dump() if hasattr(a, "model_dump") else a.dict()
                    for a in request_body.ajustes_detalle
                ]
                from src.tasks.celery_proceso_sap import ejecutar_proceso_completo_sap
                ejecutar_proceso_completo_sap.delay(
                    process_id=process_id,
                    numero_pedido=numero_pedido,
                    user_id=user_id,
                    ajustes_detalle=ajustes_serialized,
                )
                logger.info(f"📤 Proceso SAP encolado: {process_id} (pedido: {numero_pedido}, usuario: {user_id})")
                return JSONResponse(
                    status_code=202,
                    content={
                        "status": "accepted",
                        "process_id": process_id,
                        "message": "Proceso en segundo plano. Consulta el resultado con resultado_url o stream_url.",
                        "resultado_url": f"/api/pedidos/proceso-sap/resultado/{process_id}",
                        "stream_url": f"/api/pedidos/proceso-sap/stream/{process_id}",
                    },
                )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(
                    "Proceso en segundo plano no disponible (%s). Ejecutando en primer plano (fallback sync).",
                    e,
                )
                run_async = False

        if not run_async:
            audit = get_audit_context(request, user, origen=ORIGEN_WEB)
            resultado = await asyncio.to_thread(
                _ejecutar_proceso_completo_sync,
                numero_pedido,
                request_body.ajustes_detalle,
                user_id,
                audit,
            )
            if resultado.get("_notify_sap"):
                try:
                    nd = resultado["_notify_data"]
                    await notificar_odc_enviada_a_sap(
                        nd["pedido_id"], nd["numero_pedido"], nd.get("doc_num")
                    )
                except Exception as notif_err:
                    logger.warning(f"⚠️ Error al enviar notificación SSE de ODC enviada a SAP: {notif_err}")
            response = resultado["response"]
            if hasattr(response, "model_dump"):
                # mode='json' serializa datetime a string (evita TypeError en JSONResponse)
                try:
                    out = response.model_dump(mode="json")
                except TypeError:
                    out = response.model_dump()
                    if "fecha_proceso" in out and hasattr(out.get("fecha_proceso"), "isoformat"):
                        out["fecha_proceso"] = out["fecha_proceso"].isoformat()
            else:
                out = dict(response) if response is not None else {}
                if "fecha_proceso" in out and hasattr(out.get("fecha_proceso"), "isoformat"):
                    out["fecha_proceso"] = out["fecha_proceso"].isoformat()
            out["fallback"] = "sync"
            out["process_id"] = None
            out["async"] = False
            return JSONResponse(status_code=200, content=out)

    @app.get("/api/pedidos/proceso-sap/resultado/{process_id}", tags=["Pedidos - Redistribución"])
    async def obtener_resultado_proceso_sap(
        process_id: str,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Obtiene el resultado del proceso completo SAP ejecutado en segundo plano.
        Usar el process_id devuelto por POST .../proceso-completo-sap-async.
        """
        if not process_id.startswith("proceso-sap-"):
            raise HTTPException(status_code=400, detail="process_id debe ser de tipo proceso-sap (proceso-sap-xxx)")
        estado_service = ProcesoEstadoService()
        estado = estado_service.obtener_estado(process_id)
        if not estado:
            raise HTTPException(status_code=404, detail="Proceso no encontrado")
        user_id = get_user_id(user)
        if estado.get("user_id") and estado["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="No tienes acceso a este proceso")

        if estado["status"] == "completed":
            resultado = estado.get("resultado") or {}
            if not isinstance(resultado, dict):
                resultado = {}
            # Incluir process_status y progress para que el frontend cierre el modal y muestre 100%
            resultado["process_status"] = "completed"
            resultado["progress"] = 100
            return resultado
        if estado["status"] == "error":
            content = {
                "status": "error",
                "message": estado.get("message", estado.get("error", "Error desconocido")),
                "error": estado.get("error"),
            }
            error_data = estado.get("error_data")
            if error_data:
                content["paso_fallido"] = error_data.get("paso_fallido")
                content["error_detalle"] = error_data.get("error_detalle")
            return JSONResponse(status_code=400, content=content)
        return {
            "status": estado["status"],
            "step": estado.get("step"),
            "progress": estado.get("progress", 0),
            "message": estado.get("message"),
            "process_id": process_id,
            "numero_pedido": estado.get("numero_pedido"),
        }

    @app.get("/api/pedidos/proceso-sap/stream/{process_id}", tags=["Pedidos - Redistribución"])
    async def stream_progreso_proceso_sap(
        process_id: str,
        request: Request,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Stream SSE del progreso del proceso completo SAP.
        Mismo formato que plantillas/stream y cruce-productos/stream.
        """
        if not process_id.startswith("proceso-sap-"):
            raise HTTPException(status_code=400, detail="process_id debe ser de tipo proceso-sap (proceso-sap-xxx)")
        estado_service = ProcesoEstadoService()
        estado = estado_service.obtener_estado(process_id)
        if not estado:
            raise HTTPException(status_code=404, detail="Proceso no encontrado")
        user_id = get_user_id(user)
        if estado.get("user_id") and estado["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="No tienes acceso a este proceso")

        async def event_stream():
            ultimo_updated_at = None
            ultima_version = None
            while True:
                if await request.is_disconnected():
                    break
                estado_actual = estado_service.obtener_estado(process_id)
                if not estado_actual:
                    yield f"data: {json.dumps({'error': 'Proceso no encontrado'})}\n\n"
                    break
                updated_at = estado_actual.get("updated_at")
                version = estado_actual.get("version", 0)
                if updated_at != ultimo_updated_at or version != ultima_version:
                    payload = {
                        "process_id": estado_actual["process_id"],
                        "status": estado_actual["status"],
                        "step": estado_actual["step"],
                        "progress": estado_actual["progress"],
                        "message": estado_actual["message"],
                        "updated_at": updated_at,
                        "version": version,
                        "numero_pedido": estado_actual.get("numero_pedido"),
                    }
                    if "data" in estado_actual:
                        payload["data"] = estado_actual["data"]
                    if estado_actual["status"] == "completed":
                        res = estado_actual.get("resultado") or {}
                        if isinstance(res, dict):
                            res = {**res, "process_status": "completed", "progress": 100}
                        payload["resultado"] = res
                    if estado_actual["status"] == "error":
                        payload["error"] = estado_actual.get("error")
                        payload["error_data"] = estado_actual.get("error_data")
                    yield f"data: {json.dumps(payload)}\n\n"
                    ultimo_updated_at = updated_at
                    ultima_version = version
                if estado_actual["status"] in ("completed", "error"):
                    break
                await asyncio.sleep(1)
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
