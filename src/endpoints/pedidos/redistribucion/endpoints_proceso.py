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
import concurrent.futures
import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, Depends, HTTPException, Path, Body, Query, status, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.utils.timezone import ahora_naive
from src.database.connection import get_db_connection_context
from src.database.pedido_estados import (
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_CONFIRMADO_ENVIADO,
    ESTADO_ERROR_ENVIO_SAP_REINTENTO,
)
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
import src.celery_app as celery_app_module

logger = logging.getLogger(__name__)

# Timeout para comprobar si hay workers Celery (evitar 202 sin worker y polling colgado)
# Configurable via .env (mismo patrón que EMAIL_SMTP_TIMEOUT en src/config.py); default
# subido de 2.5s a 5.0s tras incidente 2026-08 de falso negativo con worker vivo (más
# margen sobre la latencia típica de ping() sin penalizar demasiado el camino caído).
CELERY_WORKER_PING_TIMEOUT = float(os.getenv("CELERY_WORKER_PING_TIMEOUT", "5.0"))

# Margen extra sobre CELERY_WORKER_PING_TIMEOUT para el join() externo (ver más abajo
# por qué es necesario: inspect().ping() no corta exactamente en su propio timeout).
CELERY_WORKER_PING_JOIN_BUFFER = float(os.getenv("CELERY_WORKER_PING_JOIN_BUFFER", "2.0"))

# TTL del cache de disponibilidad de workers Celery (ver docstring de
# _celery_workers_available para el porqué: evita que llamadas repetidas en
# ráfaga disparen un nuevo hilo de ping cada vez).
CELERY_WORKER_AVAILABILITY_CACHE_TTL = float(os.getenv("CELERY_WORKER_AVAILABILITY_CACHE_TTL", "4.0"))

_PERM_MABEL_VIEW = 'mabel.view'

# Estado del cache single-flight de disponibilidad de workers Celery (ver
# _celery_workers_available). Módulo-privado.
_disponibilidad_lock = threading.Lock()
_disponibilidad_cache = {"resultado": False, "timestamp": 0.0, "verificando": False}


def _celery_workers_available() -> bool:
    """
    Comprueba si hay al menos un worker Celery disponible.
    Si no hay workers o hay error/timeout, retorna False (priorizar flujo síncrono).

    inspect().ping() no siempre respeta su propio parámetro `timeout` (el canal
    de control de Celery puede quedarse colgado bastante más tiempo); por eso
    se ejecuta en un hilo daemon con un límite externo real, para no arrastrar
    ese cuelgue a la petición HTTP que espera este chequeo.

    Cache single-flight con TTL corto (CELERY_WORKER_AVAILABILITY_CACHE_TTL):
    se verificó en vivo que cuando el join() externo se rinde, el hilo daemon
    abandonado sigue corriendo en segundo plano intentando obtener su pong, y
    ese hilo huérfano CONTIENDE con el hilo de ping de la siguiente llamada
    (aparentemente por un pool de conexiones Kombu/Celery compartido y
    limitado): pings aislados resolvían en ~5.4s, pero pings que competían
    con un hilo abandonado tardaban 9.6-14s. El resultado era que llamadas
    repetidas/rápidas a esta función seguían devolviendo falsos negativos,
    porque chocaban con sus propios rezagados, incluso después del fix del
    margen de join() (CELERY_WORKER_PING_JOIN_BUFFER) de la ronda anterior.

    Este cache soluciona eso de tres formas:
      (a) llamadas repetidas dentro del TTL reutilizan la última respuesta en
          vez de lanzar un hilo de ping nuevo cada vez;
      (b) si ya hay un ping en curso, los llamadores nuevos reutilizan el
          último valor conocido en vez de lanzar un hilo de ping COMPETIDOR
          (esto es lo que elimina la acumulación/contención de hilos);
      (c) si un hilo de ping abandonado/lento finalmente recibe su pong
          (incluso después de que su propio llamador se haya rendido),
          igual actualiza el cache compartido para que el SIGUIENTE llamador
          se beneficie de inmediato en vez de disparar otro ping lento.
    """
    ahora = time.time()
    with _disponibilidad_lock:
        edad = ahora - _disponibilidad_cache["timestamp"]
        if edad < CELERY_WORKER_AVAILABILITY_CACHE_TTL:
            return _disponibilidad_cache["resultado"]
        if _disponibilidad_cache["verificando"]:
            return _disponibilidad_cache["resultado"]
        _disponibilidad_cache["verificando"] = True

    resultado: Dict[str, Any] = {}

    def _ping():
        try:
            inspect = celery_app_module.celery_app.control.inspect(timeout=CELERY_WORKER_PING_TIMEOUT)
            resultado["ping"] = inspect.ping()
        except Exception as e:
            resultado["error"] = e
        finally:
            disponible = bool(resultado.get("ping"))
            with _disponibilidad_lock:
                _disponibilidad_cache["resultado"] = disponible
                _disponibilidad_cache["timestamp"] = time.time()
                _disponibilidad_cache["verificando"] = False

    hilo = threading.Thread(target=_ping, daemon=True)
    hilo.start()
    # inspect(timeout=X).ping() no respeta X con precisión: se confirmó en vivo que
    # excede el timeout pedido por ~0.3-0.4s incluso con un worker sano; sin este
    # margen el join externo pierde esa carrera casi siempre y devuelve falso negativo.
    hilo.join(timeout=CELERY_WORKER_PING_TIMEOUT + CELERY_WORKER_PING_JOIN_BUFFER)

    if hilo.is_alive():
        logger.debug(
            "Comprobación de workers Celery excedió el timeout (%.1fs); "
            "el hilo sigue en curso y actualizará el cache al terminar",
            CELERY_WORKER_PING_TIMEOUT + CELERY_WORKER_PING_JOIN_BUFFER,
        )
        return False
    if "error" in resultado:
        logger.debug("Comprobación de workers Celery fallida: %s", resultado["error"])
        return False

    available = bool(resultado.get("ping"))
    if not available:
        logger.debug("No hay workers Celery disponibles (ping sin respuesta)")
    return available


def _paso1_confirmar_redistribucion(
    conn,
    repo_pedido,
    repo_dist,
    pedido_id: str,
    ajustes_detalle,
    pedido_data,
    user_id: str,
    audit,
):
    """PASO 1/3: Confirma redistribución y ejecuta homologación SAP."""
    try:
        productos_redistribucion = convertir_ajustes_a_redistribucion(
            ajustes_detalle,
            pedido_data,
            repo_pedido.tienda_repo,
        )
        respuestas_proveedor = obtener_respuestas_proveedor(repo_pedido, pedido_id)
        validator = RedistribucionValidator()
        es_valido, errores = validator.validar_redistribucion(
            pedido_data, productos_redistribucion, respuestas_proveedor
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
        return resultado_redistribucion, resumen
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


def _paso2_generar_odc(
    pedido_id: str,
    numero_pedido: str,
    resultado_redistribucion,
    resumen,
):
    """PASO 2/3: Genera la(s) ODC desde el pedido confirmado.

    La mayoría de los pedidos generan 1 ODC. Un pedido que mezcla tiendas de más
    de una marca (origen_traslado_detectado, Fase 1 de PYTD002) genera 2 -- ver
    PedidoOCService.crear_ocs_desde_pedido_confirmado.

    Returns:
        (odcs, None) en éxito, con odcs = [{"oc_id", "resultado_odc"}, ...] (1 o 2 elementos)
        (None, error_dict) en fallo
    """
    try:
        from src.database.services.pedido_oc_service import PedidoOCService
        service = PedidoOCService()
        resultados_oc = service.crear_ocs_desde_pedido_confirmado(pedido_id=pedido_id)
        odcs = []
        for resultado_oc in resultados_oc:
            oc_id = resultado_oc.get("oc_id")
            if not oc_id:
                raise ValueError("El servicio no retornó un oc_id válido")
            odcs.append({
                "oc_id": oc_id,
                "resultado_odc": {
                    "oc_id": oc_id,
                    "proveedor": resultado_oc.get("proveedor"),
                    "codigo_bodega": resultado_oc.get("codigo_bodega"),
                    "detalles_insertados": resultado_oc.get("detalles_insertados", 0),
                    "estado": "PENDIENTE"
                },
                "tiendas_bodega": resultado_oc.get("tiendas_bodega"),
            })
        if len(odcs) > 1:
            logger.info(
                f"✅ PASO 2/3 completado: {len(odcs)} ODC generadas (pedido mixto): "
                f"{[o['resultado_odc'].get('codigo_bodega') for o in odcs]}"
            )
        else:
            logger.info(f"✅ PASO 2/3 completado: ODC generada (ID: {odcs[0]['oc_id'][:8]}...)")
        return odcs, None
    except Exception as e:
        logger.error(f"❌ Error en PASO 2 (Generar ODC): {e}", exc_info=True)
        return None, {
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
                solicitudes_transferencia=None,
                resumen=resumen,
                fecha_proceso=ahora_naive(),
                paso_fallido="generar_odc",
                error_detalle=str(e)
            )
        }


def _actualizar_estado_reintento(repo_pedido, pedido_id: str, audit):
    """Intenta actualizar el pedido a estado ERROR_ENVIO_SAP_REINTENTO; falla en silencio."""
    try:
        repo_pedido.update_estado(pedido_id, ESTADO_ERROR_ENVIO_SAP_REINTENTO, audit_context=audit)
    except Exception:
        logger.debug("No se pudo actualizar pedido a ERROR ENVIO SAP REINTENTO", exc_info=True)


def _resolver_doc_num_y_solicitudes(resultado_sap_envio):
    """Extrae doc_num ITR y construye el dict de solicitudes para la respuesta."""
    doc_num_po = resultado_sap_envio.get("doc_num")
    doc_num = doc_num_po
    st = resultado_sap_envio.get("solicitudes_transferencia") or {}
    resultados_st = st.get("resultados") or []
    if resultados_st and resultados_st[0].get("doc_num") is not None:
        doc_num = resultados_st[0]["doc_num"]
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
    return doc_num_po, doc_num, solicitudes_para_response


def _obtener_cabecera_oc(oc_repo, oc_id: str, doc_num_po):
    """Lee la cabecera de la OC en BD y resuelve numero_oc_sap con fallback a doc_num_po."""
    numero_oc_sap_cabecera = None
    oc_cabecera = None
    try:
        oc_cabecera = oc_repo.get_existing_cabecera(oc_id)
        if oc_cabecera and oc_cabecera.get("numero_oc_sap") is not None:
            numero_oc_sap_cabecera = str(oc_cabecera["numero_oc_sap"])
    except Exception:
        pass
    if numero_oc_sap_cabecera is None and doc_num_po is not None:
        numero_oc_sap_cabecera = str(doc_num_po)
    return oc_cabecera, numero_oc_sap_cabecera


def _enviar_email_despacho_odc(
    numero_pedido: str,
    oc_cabecera,
    doc_num_po,
    doc_entry,
    solicitudes_para_response,
    numero_oc_sap_cabecera,
) -> None:
    """Envía el email de ODC/ST lista para despacho de UNA ODC puntual.

    En un pedido mixto (2 ODC, una por bodega) se llama una vez por ODC -- ver
    _paso3_enviar_odc_sap -- cada una con su propio doc_num/DocEntry/ST; antes solo se
    enviaba para la primera ODC ("primera") y la segunda quedaba sin correo. No reenvía
    la confirmación de redistribución (esa es a nivel de pedido, ver
    _enviar_emails_exito_sap).
    """
    try:
        from src.utils.email_notifier import send_oc_ready_for_dispatch_notification
        email_despacho_enviado = send_oc_ready_for_dispatch_notification(
            oc_cabecera=oc_cabecera or {},
            doc_num=doc_num_po,
            doc_entry=doc_entry,
            solicitudes_transferencia=solicitudes_para_response,
            pedido_numero=numero_pedido,
        )
        if email_despacho_enviado:
            logger.info(
                "📧 Notificación de ODC/ST lista para despacho enviada "
                f"(Pedido: {numero_pedido}, OC: {numero_oc_sap_cabecera or doc_num_po})"
            )
        else:
            logger.warning(
                "⚠️ No se pudo enviar notificación de ODC/ST lista para despacho "
                f"(Pedido: {numero_pedido}, OC: {numero_oc_sap_cabecera or doc_num_po})"
            )
    except Exception as email_error:
        logger.warning(
            "⚠️ Error al enviar notificación de ODC/ST lista para despacho "
            f"(no crítico): {email_error}"
        )


def _enviar_emails_exito_sap(
    pedido_id: str,
    numero_pedido: str,
    user_id: str,
    resultado_redistribucion,
    resumen,
    oc_cabecera,
    doc_num_po,
    doc_entry,
    solicitudes_para_response,
    numero_oc_sap_cabecera,
):
    """Envía los dos emails de confirmación tras un envío exitoso de ODC a SAP: la
    confirmación de redistribución (a nivel de pedido) y el despacho de la primera ODC.
    Para las ODC adicionales de un pedido mixto ver _enviar_email_despacho_odc."""
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
    _enviar_email_despacho_odc(
        numero_pedido, oc_cabecera, doc_num_po, doc_entry, solicitudes_para_response, numero_oc_sap_cabecera
    )


def _enviar_una_odc_a_sap(oc_sap_service, oc_repo, odc: Dict[str, Any]) -> Dict[str, Any]:
    """Envía una ODC a SAP y arma su ProcesoCompletoSAPDetalleODC. Función pura por
    ODC, usada tanto para el caso normal (1 ODC) como para cada bodega de un pedido
    mixto (2 ODC) en _paso3_enviar_odc_sap."""
    oc_id = odc["oc_id"]
    resultado_odc = odc["resultado_odc"]
    resultado_sap_envio = oc_sap_service.enviar_oc_a_sap(
        oc_repo=oc_repo,
        oc_id=oc_id,
        warehouse_code=None,
        tiendas_destino_filtro=odc.get("tiendas_bodega"),
    )
    success = resultado_sap_envio.get("success", False)
    queued = resultado_sap_envio.get("queued", False)
    doc_entry = resultado_sap_envio.get("doc_entry")
    error = resultado_sap_envio.get("error")
    error_code = resultado_sap_envio.get("error_code")
    doc_num_po, doc_num, solicitudes_para_response = _resolver_doc_num_y_solicitudes(resultado_sap_envio)
    oc_cabecera, numero_oc_sap_cabecera = _obtener_cabecera_oc(oc_repo, oc_id, doc_num_po)
    detalle = ProcesoCompletoSAPDetalleODC(
        oc_id=oc_id,
        proveedor=resultado_odc.get("proveedor"),
        success=success,
        numero_oc_sap=numero_oc_sap_cabecera,
        doc_entry=doc_entry,
        doc_num=doc_num,
        error=error,
        error_code=error_code,
        solicitudes_transferencia=solicitudes_para_response,
        retry_recommended=resultado_sap_envio.get("retry_recommended"),
        queued=queued,
    )
    return {
        "success": success,
        "queued": queued,
        "detalle": detalle,
        "oc_cabecera": oc_cabecera,
        "doc_num_po": doc_num_po,
        "doc_num": doc_num,
        "doc_entry": doc_entry,
        "solicitudes_transferencia": solicitudes_para_response,
        "codigo_bodega": resultado_odc.get("codigo_bodega"),
        "error": error,
    }


def _enviar_una_odc_a_sap_en_thread(odc: Dict[str, Any]) -> Dict[str, Any]:
    """Como _enviar_una_odc_a_sap, pero abre su propia conexión a BD y su propio
    OCSAPService en vez de recibirlos del caller. Se usa para enviar en paralelo las
    2 ODC de un pedido mixto (ver _paso3_enviar_odc_sap): una conexión pyodbc no es
    segura para compartir entre threads, y OCSAPService (en modo conexión directa a
    SAP, sin middleware) guarda su propia sesión SAP como estado de instancia -- cada
    thread necesita las suyas, no las del caller."""
    from src.database.services.oc_sap_service import OCSAPService
    from src.database.repositories.orden_compra_repository import OrdenCompraRepository

    with get_db_connection_context() as conn:
        oc_repo_local = OrdenCompraRepository(conn)
        oc_sap_service_local = OCSAPService()
        return _enviar_una_odc_a_sap(oc_sap_service_local, oc_repo_local, odc)


def _procesar_envios_sap(oc_repo, oc_sap_service, odcs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Envía las ODC a SAP: en paralelo si son 2+ (pedido mixto), secuencial si es 1.
    Usado por `_paso3_enviar_odc_sap`; puede propagar cualquier excepción que
    levanten los envíos individuales."""
    if len(odcs) > 1:
        # Pedido mixto: enviar las ODC en paralelo (cada una es una llamada HTTP
        # independiente a SAP) en vez de una tras otra, para no duplicar el
        # tiempo total de espera. executor.map conserva el orden de odcs en los
        # resultados sin importar cuál termine primero.
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(odcs)) as executor:
            return list(executor.map(_enviar_una_odc_a_sap_en_thread, odcs))
    return [_enviar_una_odc_a_sap(oc_sap_service, oc_repo, odc) for odc in odcs]


def _notificar_exito_sap(
    pedido_id: str, numero_pedido: str, user_id: str, resultado_redistribucion, resumen,
    envios: List[Dict[str, Any]], primera: Dict[str, Any],
) -> None:
    """Envía los correos de confirmación/despacho tras un envío a SAP exitoso.
    Un solo correo de confirmación de redistribución (a nivel de pedido) + un
    correo de despacho por cada ODC adicional (pedido mixto). Usado por
    `_respuesta_exito_sap`."""
    _enviar_emails_exito_sap(
        pedido_id, numero_pedido, user_id, resultado_redistribucion, resumen,
        primera["oc_cabecera"], primera["doc_num_po"], primera["doc_entry"],
        primera["solicitudes_transferencia"], primera["detalle"].numero_oc_sap
    )
    # Pedido mixto: la confirmación de redistribución ya se envió arriba (es a nivel
    # de pedido, no por ODC); cada ODC adicional necesita su propio correo de
    # despacho con su propio doc_num/ST -- antes solo se enviaba el de "primera".
    for envio_adicional in envios[1:]:
        _enviar_email_despacho_odc(
            numero_pedido, envio_adicional["oc_cabecera"], envio_adicional["doc_num_po"],
            envio_adicional["doc_entry"], envio_adicional["solicitudes_transferencia"],
            envio_adicional["detalle"].numero_oc_sap
        )


def _mensaje_exito_sap(envios: List[Dict[str, Any]], primera: Dict[str, Any], doc_nums: List[str]) -> str:
    """Mensaje de éxito de PASO 3/3, distinto según sea pedido mixto (2+ ODC) o
    normal (1 ODC, con o sin ITR). Usado por `_respuesta_exito_sap`."""
    if len(envios) > 1:
        return (
            f"Proceso completado exitosamente. Pedido mixto: {len(envios)} ODC enviadas a SAP "
            f"(DocNum: {', '.join(doc_nums)})"
        )
    num_itr = (primera["solicitudes_transferencia"] or {}).get("transferencias_creadas") or 0
    if num_itr == 1:
        return f"Proceso completado exitosamente. ODC enviada a SAP con DocNum: {primera['doc_num']}"
    return "Proceso completado exitosamente. ODC y solicitudes de transferencia enviadas a SAP"


def _respuesta_exito_sap(
    pedido_id: str, numero_pedido: str, user_id: str,
    resultado_redistribucion, resumen, odcs_generadas: List[Any],
    envios: List[Dict[str, Any]], detalles: List[Any],
    repo_pedido, audit,
) -> Dict[str, Any]:
    """Respuesta de PASO 3/3 cuando todas las ODC se enviaron correctamente:
    actualiza el estado del pedido, envía los correos y arma el
    ProcesoCompletoSAPResponse. Usado por `_paso3_enviar_odc_sap`."""
    primera = envios[0]
    doc_nums = [str(e["doc_num"]) for e in envios if e.get("doc_num")]
    logger.info(f"✅ PASO 3/3 completado: {len(envios)} ODC enviadas a SAP (DocNum: {', '.join(doc_nums)})")
    repo_pedido.update_estado(pedido_id, ESTADO_CONFIRMADO_ENVIADO, audit_context=audit)
    logger.debug(f"✅ Estado actualizado para pedido {pedido_id}: estado_id={ESTADO_CONFIRMADO_ENVIADO} (Confirmado y enviado)")
    _notificar_exito_sap(pedido_id, numero_pedido, user_id, resultado_redistribucion, resumen, envios, primera)

    return {
        "_notify_sap": True,
        "_notify_data": {
            "pedido_id": pedido_id,
            "numero_pedido": numero_pedido,
            "doc_num": primera["doc_num_po"] and str(primera["doc_num_po"]) or None,
        },
        "response": ProcesoCompletoSAPResponse(
            status="success",
            message=_mensaje_exito_sap(envios, primera, doc_nums),
            pedido_id=pedido_id,
            numero_pedido=numero_pedido,
            redistribucion=resultado_redistribucion,
            odc_generada=odcs_generadas[0] if odcs_generadas else None,
            envio_sap=detalles[0],
            envios_sap=detalles,
            solicitudes_transferencia=primera["solicitudes_transferencia"],
            resumen=resumen,
            fecha_proceso=ahora_naive(),
            paso_fallido=None,
            error_detalle=None
        )
    }


def _mensaje_fallo_sap(
    envios: List[Dict[str, Any]], primera: Dict[str, Any],
    fallidas_reales: List[str], encoladas: List[str], error_resumen: str,
) -> str:
    """Mensaje de fallo/parcial de PASO 3/3, distinto según sea pedido mixto (2+ ODC,
    puede fallar/encolarse solo alguna) o normal (1 ODC). Usado por `_respuesta_fallo_sap`.
    Una ODC encolada (HTTP 202, SAP saturado) no es un error -- se distingue del
    resto para no decirle al usuario que "falló" algo que en realidad SAP todavía
    está procesando."""
    if len(envios) > 1:
        partes = []
        if fallidas_reales:
            partes.append(f"falló el envío a SAP de {len(fallidas_reales)}/{len(envios)} ODC: {error_resumen}")
        if encoladas:
            partes.append(
                f"{len(encoladas)}/{len(envios)} ODC del pedido mixto está siendo procesada por SAP "
                "(saturación temporal) y se confirmará automáticamente"
            )
        return "Redistribución y ODC generadas, pero " + "; además, ".join(partes)
    if not primera["success"] and primera.get("queued"):
        return "Redistribución y ODC generada. SAP está procesando la ODC (saturación temporal); se confirmará automáticamente."
    return f"Redistribución y ODC generadas, pero falló el envío a SAP: {primera['error']}"


def _respuesta_fallo_sap(
    pedido_id: str, numero_pedido: str,
    resultado_redistribucion, resumen, odcs_generadas: List[Any],
    envios: List[Dict[str, Any]], detalles: List[Any],
    repo_pedido, audit,
) -> Dict[str, Any]:
    """Respuesta de PASO 3/3 cuando alguna ODC no se envió con éxito: marca el
    pedido para reintento manual y arma el ProcesoCompletoSAPResponse. Usado por
    `_paso3_enviar_odc_sap`.

    Una ODC encolada (HTTP 202 del middleware) no es un fallo real -- no debe
    impedir el correo de despacho de una ODC hermana que sí tuvo éxito (antes,
    cualquier ODC no-exitosa, incluida una simplemente encolada, hacía que
    ninguna ODC del pedido recibiera su correo de despacho)."""
    primera = envios[0]
    fallidas_reales = [
        f"{e.get('codigo_bodega') or e['detalle'].oc_id}: {e['error']}"
        for e in envios if not e["success"] and not e.get("queued")
    ]
    encoladas = [
        e.get("codigo_bodega") or e["detalle"].oc_id
        for e in envios if not e["success"] and e.get("queued")
    ]
    error_resumen = "; ".join(fallidas_reales)
    logger.error(
        "❌ PASO 3/3 con incidencias pedido=%s: fallidas=[%s] encoladas=[%s]",
        numero_pedido,
        error_resumen,
        ", ".join(encoladas),
    )
    # Cualquier ODC que sí tuvo éxito recibe su correo de despacho, aunque otra
    # ODC hermana haya fallado o quedado encolada.
    for envio in envios:
        if envio["success"]:
            _enviar_email_despacho_odc(
                numero_pedido, envio["oc_cabecera"], envio["doc_num_po"], envio["doc_entry"],
                envio["solicitudes_transferencia"], envio["detalle"].numero_oc_sap,
            )
    # Cualquier fallo/encolado de envío ODC habilita reintento manual en UI (para
    # una ODC encolada, reintentar es seguro: enviar_oc_a_sap resuelve primero el
    # job pendiente antes de considerar un reenvío, ver _resolver_job_encolado_previo).
    _actualizar_estado_reintento(repo_pedido, pedido_id, audit)

    return {
        "_notify_sap": False,
        "_notify_data": {},
        "response": ProcesoCompletoSAPResponse(
            status="partial",
            message=_mensaje_fallo_sap(envios, primera, fallidas_reales, encoladas, error_resumen),
            pedido_id=pedido_id,
            numero_pedido=numero_pedido,
            redistribucion=resultado_redistribucion,
            odc_generada=odcs_generadas[0] if odcs_generadas else None,
            envio_sap=detalles[0],
            envios_sap=detalles,
            solicitudes_transferencia=primera["solicitudes_transferencia"],
            resumen=resumen,
            fecha_proceso=ahora_naive(),
            paso_fallido="envio_sap",
            error_detalle=error_resumen or "; ".join(encoladas)
        )
    }


def _paso3_enviar_odc_sap(
    oc_repo,
    oc_sap_service,
    odcs: List[Dict[str, Any]],
    pedido_id: str,
    numero_pedido: str,
    resultado_redistribucion,
    resumen,
    repo_pedido,
    audit,
    user_id: str,
):
    """PASO 3/3: Envía la(s) ODC a SAP y construye la respuesta final.

    odcs: lista de {"oc_id", "resultado_odc", "tiendas_bodega"} (1 o 2 elementos,
    ver _paso2_generar_odc). El estado del pedido y el correo de confirmación se
    disparan una sola vez, y solo si TODAS las ODC se enviaron con éxito -- si
    alguna falla, el pedido queda en reintento y el reintento manual solo debe
    reenviar la(s) que fallaron (evita reenviar la que sí funcionó).
    """
    odcs_generadas = [odc["resultado_odc"] for odc in odcs]
    try:
        envios = _procesar_envios_sap(oc_repo, oc_sap_service, odcs)
    except Exception as e:
        logger.error(f"❌ Error en PASO 3 (Enviar a SAP): {e}", exc_info=True)
        _actualizar_estado_reintento(repo_pedido, pedido_id, audit)
        return {
            "_notify_sap": False,
            "_notify_data": {},
            "response": ProcesoCompletoSAPResponse(
                status="partial",
                message=f"Redistribución y ODC generadas, pero falló el envío a SAP: {str(e)}",
                pedido_id=pedido_id,
                numero_pedido=numero_pedido,
                redistribucion=resultado_redistribucion,
                odc_generada=odcs_generadas[0] if odcs_generadas else None,
                envio_sap=None,
                envios_sap=None,
                solicitudes_transferencia=None,
                resumen=resumen,
                fecha_proceso=ahora_naive(),
                paso_fallido="envio_sap",
                error_detalle=str(e)
            )
        }

    detalles = [e["detalle"] for e in envios]
    todas_exitosas = all(e["success"] for e in envios)

    if todas_exitosas:
        return _respuesta_exito_sap(
            pedido_id, numero_pedido, user_id, resultado_redistribucion, resumen,
            odcs_generadas, envios, detalles, repo_pedido, audit,
        )
    return _respuesta_fallo_sap(
        pedido_id, numero_pedido, resultado_redistribucion, resumen,
        odcs_generadas, envios, detalles, repo_pedido, audit,
    )


def _ejecutar_proceso_completo_sync(
    numero_pedido: str,
    ajustes_detalle: List,
    user_id: str,
    audit: AuditContext,
    on_progress: Optional[Callable[[str, int, str], None]] = None,
) -> dict:
    """
    Ejecuta toda la lógica síncrona del proceso completo SAP.

    Se ejecuta en un thread separado (asyncio.to_thread) para NO bloquear
    el event loop de asyncio durante:
      - Consultas a BD (pyodbc sync)
      - Llamadas HTTP a SAP Service Layer (requests sync)
      - Envío de emails SMTP (smtplib sync)

    Args:
        on_progress: Callback opcional (step, progress 0-100, message) invocado tras
            cada uno de los 3 pasos reales (redistribución, generar ODC, enviar SAP).
            Solo lo usa el task de Celery (ver celery_proceso_sap.py); los callers
            síncronos no lo pasan.

    Returns:
        dict con:
          - 'response': ProcesoCompletoSAPResponse listo para retornar
          - '_notify_sap': bool indicando si enviar notificación SSE
          - '_notify_data': dict con datos para la notificación SSE

    Raises:
        HTTPException: errores de validación o internos que se propagan al cliente.
    """
    def _reportar(step: str, progress: int, message: str) -> None:
        if on_progress is None:
            return
        try:
            on_progress(step, progress, message)
        except Exception as e:
            logger.warning(f"⚠️ on_progress falló para step={step}: {e}")

    import threading
    _worker_thread = threading.current_thread().name
    logger.info(f"🧵 Ejecutando en thread: {_worker_thread} (NO es el event loop)")

    with get_db_connection_context() as conn:
        repo_pedido = PedidoRepository(conn)
        repo_dist = DistribucionConfirmadaRepository(conn)

        pedido_data = obtener_pedido_o_404(repo_pedido, numero_pedido, es_numero=True)
        pedido_id = pedido_data["cabecera"]["pedido_id"]

        logger.info("📋 PASO 1/3: Confirmando redistribución...")
        resultado_redistribucion, resumen = _paso1_confirmar_redistribucion(
            conn, repo_pedido, repo_dist, pedido_id, ajustes_detalle, pedido_data, user_id, audit
        )
        _reportar("redistribucion", 40, "Redistribución confirmada, generando orden de compra...")

        logger.info("📦 PASO 2/3: Generando ODC...")
        odcs, partial_response = _paso2_generar_odc(
            pedido_id, numero_pedido, resultado_redistribucion, resumen
        )
        if partial_response is not None:
            return partial_response
        assert odcs
        if len(odcs) > 1:
            _reportar("generando", 70, f"{len(odcs)} ODC generadas (pedido mixto), enviando a SAP en paralelo...")
        else:
            _reportar("generando", 70, "Orden de compra generada, enviando a SAP...")

        logger.info("🚀 PASO 3/3: Enviando ODC a SAP...")
        from src.database.services.oc_sap_service import OCSAPService
        from src.database.repositories.orden_compra_repository import OrdenCompraRepository
        oc_repo = OrdenCompraRepository(conn)
        oc_sap_service = OCSAPService()
        return _paso3_enviar_odc_sap(
            oc_repo, oc_sap_service, odcs, pedido_id, numero_pedido,
            resultado_redistribucion, resumen, repo_pedido, audit, user_id
        )


async def _handle_proceso_completo_sap(request, numero_pedido: str, request_body, user: Dict):
    user_id = get_user_id(user)
    logger.info("=" * 70)
    logger.info(f"🚀 PROCESO COMPLETO SAP iniciado para pedido: {numero_pedido}")
    logger.info(f"   Usuario: {user_id}")
    logger.info("=" * 70)
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


def _serializar_response(response):
    """Serializa ProcesoCompletoSAPResponse a dict JSON-safe."""
    if hasattr(response, "model_dump"):
        try:
            return response.model_dump(mode="json")
        except TypeError:
            out = response.model_dump()
            if "fecha_proceso" in out and hasattr(out.get("fecha_proceso"), "isoformat"):
                out["fecha_proceso"] = out["fecha_proceso"].isoformat()
            return out
    else:
        out = dict(response) if response is not None else {}
        if "fecha_proceso" in out and hasattr(out.get("fecha_proceso"), "isoformat"):
            out["fecha_proceso"] = out["fecha_proceso"].isoformat()
        return out


async def _handle_proceso_sap_sync_fallback(request, numero_pedido: str, request_body, user: Dict):
    """Ejecuta el proceso SAP en primer plano y devuelve JSONResponse con metadatos de fallback."""
    user_id = get_user_id(user)
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
    out = _serializar_response(resultado["response"])
    out["fallback"] = "sync"
    out["process_id"] = None
    out["async"] = False
    return JSONResponse(status_code=200, content=out)


def _encolar_proceso_sap(numero_pedido: str, request_body, user_id: str) -> JSONResponse:
    """
    Crea el registro de proceso y encola la tarea en Celery.

    Bloqueante (SQL Server + Redis): debe invocarse via asyncio.to_thread para
    no congelar el event loop si alguno de los dos responde lento.
    """
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


async def _handle_proceso_completo_sap_async(
    request, numero_pedido: str, request_body, force_sync: bool, user: Dict
):
    """Handler para proceso completo SAP con Celery y fallback síncrono."""
    user_id = get_user_id(user)
    run_async = not force_sync
    # to_thread: el ping de inspeccion habla con Redis de forma sincrona y
    # bloqueante. En el event loop, un Redis lento congela TODA la API.
    if run_async and not await asyncio.to_thread(_celery_workers_available):
        logger.info(
            "No hay workers Celery disponibles. Ejecutando proceso SAP en primer plano (fallback sync)."
        )
        run_async = False
    if run_async:
        try:
            return await asyncio.to_thread(
                _encolar_proceso_sap, numero_pedido, request_body, user_id
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
        return await _handle_proceso_sap_sync_fallback(request, numero_pedido, request_body, user)


def _procesar_estado_completado(estado):
    """Procesa un proceso SAP en estado 'completed' y retorna el resultado enriquecido."""
    resultado = estado.get("resultado") or {}
    if not isinstance(resultado, dict):
        resultado = {}
    resultado["process_status"] = "completed"
    resultado["progress"] = 100
    proc_status = resultado.get("status")
    if proc_status == "partial":
        envio = resultado.get("envio_sap") or {}
        err = (
            resultado.get("error_detalle")
            or resultado.get("error")
            or (envio.get("error") if isinstance(envio, dict) else None)
        )
        logger.error(
            "⚠️ GET proceso-sap/resultado %s: proceso parcial pedido=%s paso=%s error=%s",
            estado.get("process_id"),
            estado.get("numero_pedido") or resultado.get("numero_pedido"),
            resultado.get("paso_fallido"),
            err,
        )
    return resultado


async def _handle_obtener_resultado_proceso_sap(process_id: str, user: Dict):
    if not process_id.startswith("proceso-sap-"):
        raise HTTPException(status_code=400, detail="process_id debe ser de tipo proceso-sap (proceso-sap-xxx)")
    estado_service = ProcesoEstadoService()
    # obtener_estado() consulta Redis de forma sincrona y bloqueante (redis-py);
    # se ejecuta via asyncio.to_thread para no congelar el event loop si Redis
    # responde lento (mismo criterio que _celery_workers_available/_encolar_proceso_sap).
    estado = await asyncio.to_thread(estado_service.obtener_estado, process_id)
    if not estado:
        raise HTTPException(status_code=404, detail="Proceso no encontrado")
    user_id = get_user_id(user)
    if estado.get("user_id") and estado["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a este proceso")
    if estado["status"] == "completed":
        return _procesar_estado_completado(estado)
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
        logger.error(
            "❌ GET proceso-sap/resultado %s: pedido=%s error=%s error_data=%s",
            process_id,
            estado.get("numero_pedido"),
            content.get("error"),
            error_data,
        )
        return JSONResponse(status_code=400, content=content)
    return {
        "status": estado["status"],
        "step": estado.get("step"),
        "progress": estado.get("progress", 0),
        "message": estado.get("message"),
        "process_id": process_id,
        "numero_pedido": estado.get("numero_pedido"),
    }


def _construir_payload_stream(estado_actual):
    """Construye el payload SSE para un tick del stream de progreso."""
    payload = {
        "process_id": estado_actual["process_id"],
        "status": estado_actual["status"],
        "step": estado_actual["step"],
        "progress": estado_actual["progress"],
        "message": estado_actual["message"],
        "updated_at": estado_actual.get("updated_at"),
        "version": estado_actual.get("version", 0),
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
    return payload


async def _event_stream_proceso_sap(estado_service, process_id: str, request):
    """Generador SSE para el stream de progreso del proceso SAP."""
    ultimo_updated_at = None
    ultima_version = None
    while True:
        if await request.is_disconnected():
            break
        # obtener_estado() consulta Redis de forma sincrona y bloqueante (redis-py);
        # se ejecuta via asyncio.to_thread para no congelar el event loop en cada
        # tick del stream si Redis responde lento.
        estado_actual = await asyncio.to_thread(estado_service.obtener_estado, process_id)
        if not estado_actual:
            yield f"data: {json.dumps({'error': 'Proceso no encontrado'})}\n\n"
            break
        updated_at = estado_actual.get("updated_at")
        version = estado_actual.get("version", 0)
        if updated_at != ultimo_updated_at or version != ultima_version:
            payload = _construir_payload_stream(estado_actual)
            yield f"data: {json.dumps(payload)}\n\n"
            ultimo_updated_at = updated_at
            ultima_version = version
        if estado_actual["status"] in ("completed", "error"):
            break
        await asyncio.sleep(1)


async def _handle_stream_progreso_proceso_sap(process_id: str, request, user: Dict):
    if not process_id.startswith("proceso-sap-"):
        raise HTTPException(status_code=400, detail="process_id debe ser de tipo proceso-sap (proceso-sap-xxx)")
    estado_service = ProcesoEstadoService()
    # obtener_estado() consulta Redis de forma sincrona y bloqueante (redis-py);
    # se ejecuta via asyncio.to_thread para no congelar el event loop si Redis
    # responde lento (mismo criterio que _celery_workers_available/_encolar_proceso_sap).
    estado = await asyncio.to_thread(estado_service.obtener_estado, process_id)
    if not estado:
        raise HTTPException(status_code=404, detail="Proceso no encontrado")
    user_id = get_user_id(user)
    if estado.get("user_id") and estado["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a este proceso")
    return StreamingResponse(
        _event_stream_proceso_sap(estado_service, process_id, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def register_proceso_completo_endpoints(app: FastAPI):
    """Endpoint de proceso completo SAP (síncrono en thread y asíncrono con Celery)."""

    @app.post("/api/pedidos/{numero_pedido}/proceso-completo-sap",
             tags=["Pedidos - Redistribución"])
    async def proceso_completo_sap(
        request: Request,
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: RedistribucionConfirmarRequest = Body(..., description="Datos de redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL_VIEW))
    ):
        """Proceso completo: Redistribución + Generar ODC + Enviar a SAP.

        La lógica pesada (BD, SAP, email) se ejecuta en un thread separado
        para no bloquear el event loop de asyncio (~40s de operaciones síncronas).
        Para ejecución en segundo plano con Celery, usar POST .../proceso-completo-sap-async.
        """
        return await _handle_proceso_completo_sap(request, numero_pedido, request_body, user)

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
        _: None = Depends(require_permission(_PERM_MABEL_VIEW))
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
        return await _handle_proceso_completo_sap_async(request, numero_pedido, request_body, force_sync, user)

    @app.get("/api/pedidos/proceso-sap/resultado/{process_id}", tags=["Pedidos - Redistribución"])
    async def obtener_resultado_proceso_sap(
        process_id: str,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL_VIEW))
    ):
        """
        Obtiene el resultado del proceso completo SAP ejecutado en segundo plano.
        Usar el process_id devuelto por POST .../proceso-completo-sap-async.
        """
        return await _handle_obtener_resultado_proceso_sap(process_id, user)

    @app.get("/api/pedidos/proceso-sap/stream/{process_id}", tags=["Pedidos - Redistribución"])
    async def stream_progreso_proceso_sap(
        process_id: str,
        request: Request,
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission(_PERM_MABEL_VIEW))
    ):
        """
        Stream SSE del progreso del proceso completo SAP.
        Mismo formato que plantillas/stream y cruce-productos/stream.
        """
        return await _handle_stream_progreso_proceso_sap(process_id, request, user)
