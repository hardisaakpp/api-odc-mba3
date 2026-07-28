"""
Endpoints relacionados con integración SAP.
"""

import logging
import uuid
from src.utils.timezone import ahora_naive
from typing import Optional, List
from fastapi import FastAPI, Request, Query as FastAPIQuery, Depends, Query
from fastapi.responses import JSONResponse

from src.utils import get_source_from_headers
from src.database.services.sap_service import SAPService
from src.database.clients.sap_client import SAPClient
from src.database.repositories.orden_compra_repository import OrdenCompraRepository
from src.database.repositories.sap_integration_log_repository import SAPIntegrationLogRepository, SAPLogEntry
from src.database.services.oc_sap_service import OCSAPService
from src.database.connection import get_db_connection, get_db_connection_context
from src.config import ENABLE_SAP_QUERIES, SAP_LINKED_SERVER, ENABLE_SAP_SERVICE_LAYER
from src.security.jwt_auth import verify_jwt_token, require_permission

logger = logging.getLogger(__name__)


def _respuesta_sap_deshabilitado(source):
    logger.warning("⚠️ SAP Service Layer está deshabilitado")
    return JSONResponse(
        status_code=400,
        content={
            "status": "error",
            "message": "SAP Service Layer está deshabilitado",
            "hint": "Configura ENABLE_SAP_SERVICE_LAYER=true en .env"
        },
        headers={"X-Source": source, "X-Endpoint": "INTEGRAR-SAP"}
    )


def _log_safe(log_repo, entry, warning_msg):
    try:
        log_repo.guardar_log(entry)
    except Exception as e:
        logger.warning(f"{warning_msg}: {e}")


def _normalizar_lista(valor):
    if valor and not isinstance(valor, list):
        return [valor]
    return valor


def _resetear_oc_si_error(oc_repo, oc_id_item, estado_actual):
    if estado_actual == "ERROR":
        logger.info(f"🔄 OC {oc_id_item[:8]}... en ERROR, reseteando a PENDIENTE para reintento")
        oc_repo.update_estado(oc_id_item, "PENDIENTE", respuesta_sap=None, error_message=None)


def _resolver_por_uuid(oc_repo, oc_id_list, source):
    oc_ids_a_procesar = []
    logger.info(f"📋 Procesando {len(oc_id_list)} OCs por UUID")
    for oc_id_item in oc_id_list:
        oc_cabecera = oc_repo.get_existing_cabecera(oc_id_item)
        if not oc_cabecera:
            logger.warning(f"⚠️ OC {oc_id_item[:8]}... no encontrada, omitiendo")
            continue
        estado_actual = oc_cabecera.get("estado")
        if estado_actual not in {"PENDIENTE", "ERROR"}:
            logger.warning(f"⚠️ OC {oc_id_item[:8]}... no está en estado procesable (estado: {estado_actual}), omitiendo")
            continue
        _resetear_oc_si_error(oc_repo, oc_id_item, estado_actual)
        oc_ids_a_procesar.append(oc_id_item)
    if not oc_ids_a_procesar:
        return [], [], JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "No se encontraron OCs válidas para procesar",
                "oc_ids_provistos": oc_id_list,
                "enviadas": 0,
                "errores": 0
            },
            headers={"X-Source": source, "X-Endpoint": "INTEGRAR-SAP"}
        )
    return oc_ids_a_procesar, [], None


def _resolver_por_referencia(oc_repo, refs_list, source):
    oc_ids_a_procesar = []
    referencias_usadas = []
    logger.info(f"📋 Procesando OCs por referencia ({len(refs_list)} referencias)")
    for referencia in refs_list:
        oc_encontrada = oc_repo.find_by_referencia_despacho(referencia)
        if not oc_encontrada:
            logger.warning(f"⚠️ No se encontró OC con referencia: {referencia}")
            continue
        oc_id_encontrado = oc_encontrada.get("oc_id")
        if not oc_id_encontrado:
            logger.warning(f"⚠️ OC con referencia {referencia} no tiene oc_id registrado")
            continue
        estado_actual = oc_encontrada.get("estado")
        if estado_actual not in {"PENDIENTE", "ERROR"}:
            logger.warning(f"⚠️ OC con ref {referencia} no está en estado procesable (estado: {estado_actual})")
            continue
        _resetear_oc_si_error(oc_repo, oc_id_encontrado, estado_actual)
        oc_ids_a_procesar.append(oc_id_encontrado)
        referencias_usadas.append(referencia)
    if not oc_ids_a_procesar:
        return [], [], JSONResponse(
            status_code=404,
            content={
                "status": "not_found",
                "message": "No se encontraron OCs válidas con las referencias proporcionadas",
                "referencias_provistas": refs_list,
                "enviadas": 0,
                "errores": 0
            },
            headers={"X-Source": source, "X-Endpoint": "INTEGRAR-SAP"}
        )
    return oc_ids_a_procesar, referencias_usadas, None


def _resolver_primera_pendiente(oc_repo, source):
    logger.info("📋 Procesando primera OC pendiente")
    ocs_pendientes = oc_repo.get_by_estado("PENDIENTE")
    if not ocs_pendientes:
        logger.info("ℹ️ No hay OCs pendientes")
        return [], JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "No hay órdenes de compra pendientes de enviar a SAP",
                "metadata": {
                    "total_pendientes": 0,
                    "enviadas": 0,
                    "errores": 0,
                    "pendientes_restantes": 0,
                    "detalles": []
                }
            },
            headers={"X-Source": source, "X-Endpoint": "INTEGRAR-SAP"}
        )
    oc_id_primera = ocs_pendientes[0].get("oc_id")
    return ([oc_id_primera] if oc_id_primera else []), None


def _resolver_oc_ids(oc_repo, oc_id, referencia_despacho, source):
    if oc_id:
        oc_id_list = [id.strip() for id in oc_id if id and id.strip()]
        return _resolver_por_uuid(oc_repo, oc_id_list, source)
    if referencia_despacho:
        refs_list = [ref.strip() for ref in referencia_despacho if ref and ref.strip()]
        return _resolver_por_referencia(oc_repo, refs_list, source)
    ids, early = _resolver_primera_pendiente(oc_repo, source)
    return ids, [], early


def _warnings_de_st_fallido(resultado_st):
    st_error = resultado_st.get("error", "")
    st_errores_detalle = resultado_st.get("errores_detalle", [])
    st_resultados = resultado_st.get("resultados", [])
    if st_errores_detalle:
        return [e.get("mensaje", str(e)) for e in st_errores_detalle]
    if st_resultados:
        warnings = []
        for r in st_resultados:
            if not r.get("success") and r.get("error"):
                tienda = r.get("tienda_codigo", "N/A")
                warnings.append(f"ST no creada hacia {tienda}: {r['error']}")
        return warnings
    if st_error:
        return [f"Solicitudes de Transferencia: {st_error}"]
    return []


def _construir_warnings_st(resultado_st):
    if not resultado_st.get("success", True):
        return _warnings_de_st_fallido(resultado_st)
    if resultado_st.get("warnings"):
        return list(resultado_st["warnings"])
    return []


def _construir_warnings_itr(resultado_itr):
    warnings = []
    if resultado_itr.get("errors", 0) > 0:
        for r in resultado_itr.get("resultados", []):
            if not r.get("success") and r.get("error"):
                to_wh = r.get("ToWarehouse", "N/A")
                warnings.append(f"ITR no creado hacia {to_wh}: {r['error']}")
    return warnings


def _log_resultado_oc(log_repo, proceso_id, username, source, oc_id_item, proveedor, referencia, resultado):
    success = resultado.get("success", False)
    doc_entry = resultado.get("doc_entry")
    doc_num = resultado.get("doc_num")
    sap_response = resultado.get("sap_response")
    error = resultado.get("error")
    error_code = resultado.get("error_code")
    error_source = resultado.get("error_source")
    sap_error_details = resultado.get("sap_error_details")
    try:
        if success:
            log_repo.guardar_log(SAPLogEntry(
                proceso_id=proceso_id,
                nivel_log="INFO",
                mensaje=f"ODC {oc_id_item[:8]}... enviada exitosamente: DocNum={doc_num}",
                usuario=username,
                fuente=source,
                oc_id=oc_id_item,
                proveedor=proveedor,
                referencia_despacho=referencia,
                doc_entry=doc_entry,
                doc_num=doc_num,
                success=True,
                detalles_adicionales={"sap_response": sap_response} if sap_response else None
            ))
        else:
            log_repo.guardar_log(SAPLogEntry(
                proceso_id=proceso_id,
                nivel_log="ERROR",
                mensaje=f"Error ODC {oc_id_item[:8]}...: {error}",
                usuario=username,
                fuente=source,
                oc_id=oc_id_item,
                proveedor=proveedor,
                referencia_despacho=referencia,
                error_code=error_code,
                error_source=error_source,
                success=False,
                detalles_adicionales={"sap_error_details": sap_error_details} if sap_error_details else None
            ))
    except Exception as e:
        logger.warning(f"No se pudo guardar log de resultado: {e}")


def _procesar_oc_individual(oc_repo, log_repo, oc_sap_service, proceso_id, username, source, oc_id_item, proveedor, referencia):
    _log_safe(log_repo, SAPLogEntry(
        proceso_id=proceso_id,
        nivel_log="INFO",
        mensaje=f"Procesando ODC {oc_id_item[:8]}...",
        usuario=username,
        fuente=source,
        oc_id=oc_id_item,
        proveedor=proveedor,
        referencia_despacho=referencia
    ), "No se pudo guardar log de OC")

    # ⭐ La bodega se determina automáticamente desde el pedido:
    # 1. Si hay distribuciones con es_bodega=True y cantidad > 0, usa la primera bodega encontrada
    # 2. Si no, usa origen_traslado del pedido
    # 3. Si no hay ninguno, se envía sin WarehouseCode (SAP usará su configuración por defecto)
    resultado = oc_sap_service.enviar_oc_a_sap(
        oc_repo=oc_repo,
        oc_id=oc_id_item,
        warehouse_code=None
    )

    _log_resultado_oc(log_repo, proceso_id, username, source, oc_id_item, proveedor, referencia, resultado)

    success = resultado.get("success", False)
    error = resultado.get("error")
    doc_entry = resultado.get("doc_entry")
    doc_num = resultado.get("doc_num")
    sap_request_json = resultado.get("sap_request_json")
    sap_response = resultado.get("sap_response")
    error_code = resultado.get("error_code")
    error_source = resultado.get("error_source")
    sap_error_details = resultado.get("sap_error_details")
    resultado_st = resultado.get("solicitudes_transferencia")
    resultado_itr = resultado.get("inventory_transfer_requests")

    detalle_resultado = {
        "oc_id": oc_id_item,
        "proveedor": proveedor,
        "success": success,
        "doc_entry": doc_entry,
        "doc_num": doc_num,
        "error": error,
        "error_message": error,  # Alias para compatibilidad con frontend
        "error_code": error_code,  # Código de error de SAP (ej: -4013)
        "error_source": error_source,  # Origen: "SAP", "BACKEND", "SAP_CONNECTION", o None si éxito
        "sap_request_json": sap_request_json,  # Payload usado para POST /PurchaseOrders
        "sap_response": sap_response,  # Respuesta completa de SAP (éxito)
        "sap_error_details": sap_error_details,  # Detalles del error de SAP (si aplica)
        "solicitudes_transferencia": resultado_st,  # Resultado de ST por tienda (para evaluación de cierre)
        "inventory_transfer_requests": resultado_itr  # Resultado de ITR por bodega destino
    }

    detalle_warnings = []
    if resultado_st:
        detalle_warnings.extend(_construir_warnings_st(resultado_st))
    if resultado_itr:
        detalle_warnings.extend(_construir_warnings_itr(resultado_itr))
    if detalle_warnings:
        detalle_resultado["warnings"] = detalle_warnings
    if referencia:
        detalle_resultado["referencia_despacho"] = referencia

    return detalle_resultado, success, error


def _procesar_oc_en_lista(
    oc_repo,
    log_repo,
    oc_sap_service,
    proceso_id,
    username,
    source,
    oc_id_item,
    proveedor,
    referencia,
):
    detalle_resultado, success, error = _procesar_oc_individual(
        oc_repo,
        log_repo,
        oc_sap_service,
        proceso_id,
        username,
        source,
        oc_id_item,
        proveedor,
        referencia,
    )
    return detalle_resultado, success, error


def _registrar_error_en_lista(oc_repo, log_repo, proceso_id, username, source, oc_id_item, proveedor_fallback, error):
    try:
        log_repo.guardar_log(SAPLogEntry(
            proceso_id=proceso_id,
            nivel_log="ERROR",
            mensaje=f"Error al procesar ODC {oc_id_item[:8]}...: {str(error)}",
            usuario=username,
            fuente=source,
            oc_id=oc_id_item,
            proveedor=proveedor_fallback,
            error_source="BACKEND",
            success=False
        ))
    except Exception:
        pass


def _detalles_error_en_lista(oc_id_item, proveedor_fallback, error):
    return {
        "oc_id": oc_id_item,
        "proveedor": proveedor_fallback,
        "success": False,
        "doc_entry": None,
        "doc_num": None,
        "error": str(error),
        "error_message": str(error),  # Alias para compatibilidad con frontend
        "error_code": None,
        "error_source": "BACKEND",
        "sap_response": None,
        "sap_error_details": None
    }


def _procesar_lista_ocs(oc_repo, log_repo, oc_sap_service, proceso_id, username, source, oc_ids_a_procesar):
    detalles = []
    enviadas = 0
    errores = 0
    for oc_id_item in oc_ids_a_procesar:
        try:
            oc_info = oc_repo.get_existing_cabecera(oc_id_item)
            proveedor = oc_info.get("proveedor") if oc_info else "UNKNOWN"
            referencia = oc_info.get("referencia_despacho") if oc_info else None

            detalle_resultado, success, error = _procesar_oc_en_lista(
                oc_repo,
                log_repo,
                oc_sap_service,
                proceso_id,
                username,
                source,
                oc_id_item,
                proveedor,
                referencia,
            )
            detalles.append(detalle_resultado)
            if success:
                enviadas += 1
            else:
                errores += 1
                logger.error(f"❌ Error ODC {oc_id_item[:8]}...: {error}")
        except Exception as e:
            errores += 1
            logger.error(f"❌ Error al procesar ODC {oc_id_item[:8]}...: {e}", exc_info=True)
            proveedor_fallback = proveedor if 'proveedor' in locals() else "UNKNOWN"
            _registrar_error_en_lista(
                oc_repo,
                log_repo,
                proceso_id,
                username,
                source,
                oc_id_item,
                proveedor_fallback,
                e,
            )
            detalles.append(_detalles_error_en_lista(oc_id_item, proveedor_fallback, e))
    return detalles, enviadas, errores


def _combinar_st(st_existente, resultado_st):
    return {
        "success": st_existente.get("success", False) and resultado_st.get("success", False),
        "transferencias_creadas": (st_existente.get("transferencias_creadas", 0) +
                                   resultado_st.get("transferencias_creadas", 0)),
        "transferencias_errores": (st_existente.get("transferencias_errores", 0) +
                                   resultado_st.get("transferencias_errores", 0)),
        "total_tiendas": max(st_existente.get("total_tiendas", 0),
                             resultado_st.get("total_tiendas", 0))
    }


def _procesar_detalle_acumulado(detalle, pedidos_procesados):
    try:
        with get_db_connection_context() as conn_temp:
            oc_repo_temp = OrdenCompraRepository(conn_temp)
            oc_info = oc_repo_temp.get_existing_cabecera(detalle["oc_id"])
            if not (oc_info and oc_info.get("pedido_id")):
                return
            pedido_id = oc_info["pedido_id"]
            resultado_st = detalle.get("solicitudes_transferencia")
            if pedido_id in pedidos_procesados:
                st_existente = pedidos_procesados[pedido_id].get("resultado_st")
                if st_existente and resultado_st:
                    pedidos_procesados[pedido_id]["resultado_st"] = _combinar_st(st_existente, resultado_st)
                elif resultado_st:
                    pedidos_procesados[pedido_id]["resultado_st"] = resultado_st
            else:
                pedidos_procesados[pedido_id] = {
                    "oc_id": detalle["oc_id"],
                    "resultado_st": resultado_st
                }
    except Exception:
        pass


def _acumular_pedidos_procesados(detalles):
    pedidos_procesados = {}
    for detalle in detalles:
        if not detalle.get("success"):
            continue
        _procesar_detalle_acumulado(detalle, pedidos_procesados)
    return pedidos_procesados


def _cerrar_pedidos(pedidos_procesados, resumen_cierre):
    if not pedidos_procesados:
        return
    try:
        from src.database.repositories.pedido_repository import PedidoRepository
        from src.database.services.pedido_cierre_service import PedidoCierreService

        with get_db_connection_context() as conn_temp:
            oc_repo_temp = OrdenCompraRepository(conn_temp)
            pedido_repo_temp = PedidoRepository(conn_temp)
            cierre_service = PedidoCierreService()

            for pedido_id, info_pedido in pedidos_procesados.items():
                resultado_st = info_pedido.get("resultado_st")
                resultado = cierre_service.cerrar_pedido_si_corresponde(
                    pedido_id=pedido_id,
                    oc_repo=oc_repo_temp,
                    pedido_repo=pedido_repo_temp,
                    resultado_st=resultado_st
                )
                entrada_cierre = {
                    "pedido_id": pedido_id,
                    "estado_anterior": resultado["estado_anterior"],
                    "estado_nuevo": resultado["estado_nuevo"],
                    "evaluacion": resultado["evaluacion"]
                }
                if resultado.get("cerrado"):
                    resumen_cierre["pedidos_cerrados"].append(entrada_cierre)
                elif resultado.get("estado_nuevo"):
                    entrada_cierre["razon_estado"] = resultado.get("razon_estado")
                    resumen_cierre["pedidos_cerrados"].append(entrada_cierre)
    except Exception as e:
        logger.warning(f"⚠️ Error al generar resumen de cierre (no crítico): {e}")


def _log_final_consolidado(proceso_id, username, source, enviadas, errores, resumen_cierre):
    try:
        with get_db_connection_context() as conn_final:
            log_repo_final = SAPIntegrationLogRepository(conn_final)
            log_repo_final.guardar_log(SAPLogEntry(
                proceso_id=proceso_id,
                nivel_log="INFO",
                mensaje=f"INTEGRAR-SAP completado: {enviadas} enviadas, {errores} errores. "
                        f"Pedidos cerrados: {len(resumen_cierre['pedidos_cerrados'])}",
                usuario=username,
                fuente=source,
                success=enviadas > 0 and errores == 0,
                detalles_adicionales=resumen_cierre
            ))
    except Exception as e:
        logger.warning(f"⚠️ No se pudo guardar log final consolidado: {e}")


def _construir_mensaje(oc_ids_a_procesar, enviadas, errores, detalles, all_warnings):
    if len(oc_ids_a_procesar) == 1:
        if enviadas > 0:
            mensaje = "ODC enviada exitosamente a SAP"
            if detalles[0].get("doc_num"):
                mensaje += f" (DocNum: {detalles[0].get('doc_num')})"
            if all_warnings:
                mensaje += f". ADVERTENCIA: {len(all_warnings)} Solicitud(es) de Transferencia con problemas"
        else:
            mensaje = f"Error al enviar ODC a SAP: {detalles[0].get('error', 'Error desconocido')}"
    else:
        mensaje = f"Proceso completado: {enviadas} ODC(s) enviada(s), {errores} error(es) de {len(oc_ids_a_procesar)} procesada(s)"
        if all_warnings:
            mensaje += f". ADVERTENCIA: {len(all_warnings)} Solicitud(es) de Transferencia con problemas"
    return mensaje


def _construir_respuesta(source, enviadas, errores, detalles, oc_ids_a_procesar, referencias_usadas, oc_id, referencia_despacho):
    status_general = "success" if errores == 0 else "partial"
    if enviadas == 0:
        status_general = "error"

    all_warnings = []
    for detalle in detalles:
        detalle_warnings_list = detalle.get("warnings", [])
        if detalle_warnings_list:
            all_warnings.extend(detalle_warnings_list)

    mensaje = _construir_mensaje(oc_ids_a_procesar, enviadas, errores, detalles, all_warnings)

    headers = {
        "X-Source": source,
        "X-Endpoint": "INTEGRAR-SAP",
        "X-OC-Status": status_general,
        "X-Enviadas": str(enviadas),
        "X-Errores": str(errores),
        "X-Total-Procesadas": str(len(oc_ids_a_procesar))
    }

    metadata = {
        "enviadas": enviadas,
        "errores": errores,
        "total_procesadas": len(oc_ids_a_procesar),
        "detalles": detalles
    }

    if referencias_usadas:
        metadata["referencias_usadas"] = referencias_usadas

    if not oc_id and not referencia_despacho:
        with get_db_connection_context() as conn_check:
            oc_repo_temp = OrdenCompraRepository(conn_check)
            ocs_pendientes_restantes = oc_repo_temp.get_by_estado("PENDIENTE")
            total_pendientes = len(ocs_pendientes_restantes)
        metadata["total_pendientes"] = total_pendientes
        metadata["pendientes_restantes"] = total_pendientes
        headers["X-Total-Pendientes"] = str(total_pendientes)
        headers["X-Pendientes-Restantes"] = str(total_pendientes)

    response_content = {
        "status": status_general,
        "message": mensaje,
        "metadata": metadata
    }

    if all_warnings:
        response_content["warnings"] = all_warnings

    return JSONResponse(
        status_code=200,
        content=response_content,
        headers=headers
    )


def _ejecutar_integrar_sap(request, oc_id, referencia_despacho, user):
    source = get_source_from_headers(request)
    username = user.get('username', 'unknown') if user else 'unknown'
    logger.info(f"🚀 INTEGRAR-SAP iniciado (usuario: {username}, fuente: {source})")

    try:
        if not ENABLE_SAP_SERVICE_LAYER:
            return _respuesta_sap_deshabilitado(source)

        proceso_id = str(uuid.uuid4())
        conn = get_db_connection()
        oc_repo = OrdenCompraRepository(conn)
        log_repo = SAPIntegrationLogRepository(conn)
        oc_sap_service = OCSAPService()

        _log_safe(log_repo, SAPLogEntry(
            proceso_id=proceso_id,
            nivel_log="INFO",
            mensaje=f"INTEGRAR-SAP iniciado (usuario: {username}, fuente: {source})",
            usuario=username,
            fuente=source
        ), "No se pudo guardar log de inicio")

        _log_safe(log_repo, SAPLogEntry(
            proceso_id=proceso_id,
            nivel_log="INFO",
            mensaje="Conexión a SQL Server establecida",
            usuario=username,
            fuente=source
        ), "No se pudo guardar log de conexión")

        oc_id = _normalizar_lista(oc_id)
        referencia_despacho = _normalizar_lista(referencia_despacho)

        oc_ids_a_procesar, referencias_usadas, early_response = _resolver_oc_ids(
            oc_repo, oc_id, referencia_despacho, source
        )
        if early_response is not None:
            conn.close()
            return early_response

        logger.info(f"📦 Procesando {len(oc_ids_a_procesar)} OCs...")
        _log_safe(log_repo, SAPLogEntry(
            proceso_id=proceso_id,
            nivel_log="INFO",
            mensaje=f"Procesando {len(oc_ids_a_procesar)} OCs...",
            usuario=username,
            fuente=source
        ), "No se pudo guardar log de procesamiento")

        detalles, enviadas, errores = _procesar_lista_ocs(
            oc_repo, log_repo, oc_sap_service, proceso_id, username, source, oc_ids_a_procesar
        )
        conn.close()

        resumen_cierre = {
            "proceso_id": proceso_id,
            "timestamp": ahora_naive().isoformat(),
            "usuario": username,
            "fuente": source,
            "total_procesadas": len(oc_ids_a_procesar),
            "enviadas": enviadas,
            "errores": errores,
            "detalles_por_oc": detalles,
            "pedidos_cerrados": []
        }

        pedidos_procesados = _acumular_pedidos_procesados(detalles)
        _cerrar_pedidos(pedidos_procesados, resumen_cierre)
        _log_final_consolidado(proceso_id, username, source, enviadas, errores, resumen_cierre)

        logger.info(f"✅ INTEGRAR-SAP completado: {enviadas} enviadas, {errores} errores de {len(oc_ids_a_procesar)} procesadas")
        _log_safe(log_repo, SAPLogEntry(
            proceso_id=proceso_id,
            nivel_log="INFO",
            mensaje=f"INTEGRAR-SAP completado: {enviadas} enviadas, {errores} errores de {len(oc_ids_a_procesar)} procesadas",
            usuario=username,
            fuente=source
        ), "No se pudo guardar log de finalización")

        return _construir_respuesta(source, enviadas, errores, detalles, oc_ids_a_procesar, referencias_usadas, oc_id, referencia_despacho)

    except Exception as e:
        logger.error(f"❌ Error al integrar con SAP: {e}", exc_info=True)
        try:
            if 'conn' in locals() and conn:
                conn.close()
        except Exception:
            pass
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Error al integrar con SAP: {str(e)}"
            },
            headers={
                "X-Source": source,
                "X-Endpoint": "INTEGRAR-SAP"
            }
        )


def _ejecutar_test_sap_query(request, sku):
    source = get_source_from_headers(request)

    logger.info("=" * 70)
    logger.info(f"Prueba de consulta SAP recibida a las {ahora_naive().isoformat()}")
    logger.info(f"Fuente: {source}")
    logger.info(f"SKU: {sku}")
    logger.info("=" * 70)

    try:
        if not ENABLE_SAP_QUERIES:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Consultas SAP están deshabilitadas",
                    "hint": "Configura ENABLE_SAP_QUERIES=true en .env"
                }
            )

        sap_service = SAPService()
        producto_info = sap_service.get_or_fetch_producto_info(sku)

        if producto_info:
            response_data = {
                "status": "success",
                "sku": sku,
                "sap_info": {
                    "item_code": producto_info.get("item_code"),
                    "item_name": producto_info.get("item_name"),
                    "pack_sap": producto_info.get("pack_sap"),
                    "pack_id": producto_info.get("pack_id"),
                    "unidad_conversion": producto_info.get("unidad_conversion"),
                },
                "config": {
                    "sap_linked_server": SAP_LINKED_SERVER,
                    "sap_enabled": ENABLE_SAP_QUERIES,
                },
                "message": "Producto encontrado en SAP",
                "timestamp": ahora_naive().isoformat()
            }

            unidad = producto_info.get("unidad_conversion")
            if unidad:
                response_data["conversion_info"] = {
                    "unidad_conversion": unidad,
                    "formula": "1 docena = {unidad} packs".format(unidad=unidad),
                    "ejemplo": {
                        "docenas": 456,
                        "packs": 456 * unidad,
                        "formula_ejemplo": f"456 docenas × {unidad} = {456 * unidad} packs"
                    }
                }

            logger.info(f"✅ Consulta SAP exitosa para SKU: {sku}")
            logger.info(f"   Pack: {producto_info.get('pack_sap')}, Unidad: {producto_info.get('unidad_conversion')}")

            return JSONResponse(
                status_code=200,
                content=response_data,
                headers={
                    "X-Source": source,
                    "X-SKU": sku,
                    "X-Pack-SAP": producto_info.get("pack_sap") or "N/A"
                }
            )
        else:
            logger.warning(f"⚠️ Producto no encontrado en SAP: {sku}")
            return JSONResponse(
                status_code=404,
                content={
                    "status": "not_found",
                    "message": f"Producto no encontrado en SAP para SKU: {sku}",
                    "sku": sku,
                    "hint": "Verifica que el SKU exista en SAP y que el servidor vinculado esté configurado correctamente",
                    "timestamp": ahora_naive().isoformat()
                }
            )

    except Exception as e:
        logger.error(f"❌ Error al consultar SAP: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Error al consultar SAP: {str(e)}",
                "sku": sku,
                "timestamp": ahora_naive().isoformat()
            }
        )


def _ejecutar_test_sap_direct(request, sku):
    source = get_source_from_headers(request)

    logger.info("=" * 70)
    logger.info(f"Prueba de consulta SAP directa recibida a las {ahora_naive().isoformat()}")
    logger.info(f"SKU: {sku}")
    logger.info("=" * 70)

    try:
        if not ENABLE_SAP_QUERIES:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Consultas SAP están deshabilitadas"
                }
            )

        client = SAPClient()
        resultado = client.get_producto_info(sku)

        if resultado:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "sku": sku,
                    "sap_direct_result": resultado,
                    "message": "Consulta directa a SAP exitosa",
                    "timestamp": ahora_naive().isoformat()
                },
                headers={
                    "X-Source": source,
                    "X-SKU": sku
                }
            )
        else:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "not_found",
                    "message": f"Producto no encontrado en SAP: {sku}",
                    "sku": sku
                }
            )

    except Exception as e:
        logger.error(f"❌ Error en consulta directa SAP: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Error al consultar SAP: {str(e)}",
                "sku": sku
            }
        )


def register_sap_endpoints(app: FastAPI):
    """
    Registra los endpoints de SAP en la aplicación FastAPI.

    Args:
        app: Instancia de FastAPI
    """

    @app.post("/integrar-sap", tags=["Integración SAP"])
    async def integrar_sap(
        request: Request,
        oc_id: Optional[List[str]] = Query(None, description="UUID(s) de la(s) orden(es) de compra a enviar. Puede especificarse múltiples veces (ej: ?oc_id=xxx&oc_id=yyy)."),
        referencia_despacho: Optional[List[str]] = Query(None, description="Referencia(s) del despacho (número de factura) para buscar OC(s) específica(s). Puede especificarse múltiples veces (ej: ?referencia_despacho=xxx&referencia_despacho=yyy). Si no se proporciona oc_id ni referencia_despacho, se procesa la primera OC pendiente."),
        user: dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Endpoint INTEGRAR-SAP: Envía órdenes de compra a SAP Service Layer.

        **Responsabilidad:** INTEGRAR (endpoint #4 de los 4 requeridos)

        Este endpoint realiza:
        1. ❌ NO consulta (ya lo hizo CONSULTAR)
        2. ❌ NO guarda en despacho (ya lo hizo MIGRAR)
        3. ❌ NO copia a OC (ya lo hizo PROCESAR)
        4. ✅ Envía ODCs con estado "PENDIENTE" a SAP Service Layer
        5. ✅ Actualiza estado a "ENVIADA" o "ERROR" según resultado

        **Características:**
        - ✅ Puede enviar 1 o varios ODC en una sola llamada
        - ✅ Si se proporciona `oc_id`: envía las ODC(s) especificada(s) por UUID
        - ✅ Si se proporciona `referencia_despacho`: busca y envía las ODC(s) por referencia
        - ✅ Si NO se proporciona ningún parámetro: busca y envía la primera ODC pendiente
        - ✅ Convierte cada ODC a formato JSON de SAP Service Layer
        - ✅ Envía cada ODC directamente a SAP Service Layer (sin middleware)
        - ✅ Actualiza estado a "ENVIADA" o "ERROR" según resultado
        - ✅ Retorna información detallada de cada ODC procesada

        **Query Parameters:**
        - `oc_id` (opcional, múltiple): UUID de la orden de compra. Puede especificarse múltiples veces.
        - `referencia_despacho` (opcional, múltiple): Número de factura/despacho. Puede especificarse múltiples veces.

        **Ejemplos de uso:**
        ```
        # Enviar una OC específica por UUID
        POST /integrar-sap?oc_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325

        # Enviar múltiples OC por UUID
        POST /integrar-sap?oc_id=DD7D7A51-9E57-44D4-9A8F-4A05427A8325&oc_id=ABC123-DEF456-GHI789

        # Buscar OC específica por referencia
        POST /integrar-sap?referencia_despacho=900125353

        # Buscar múltiples OC por referencia
        POST /integrar-sap?referencia_despacho=900125353&referencia_despacho=900125354

        # Procesar primera OC pendiente (comportamiento por defecto)
        POST /integrar-sap
        ```

        **Nota:** Este endpoint asume que las ODCs ya están creadas con estado "PENDIENTE".
        Para proceso completo (consulta + guarda + copia + integración), usar los 4 endpoints en secuencia.

        **Flujo recomendado:**
        1. GET /consultar - Solo consulta
        2. GET /migrar - Consulta + Guarda en despacho
        3. GET /procesar-oc - Copia despachos a ODC (estado: PENDIENTE)
        4. POST /integrar-sap - Envía ODC a SAP Service Layer

        **Estados de ODC:**
        - `PENDIENTE`: Creada pero no enviada a SAP (estado inicial)
        - `ENVIADA`: Enviada exitosamente a SAP (se actualiza aquí)
        - `ERROR`: Error al enviar a SAP (se actualiza aquí)

        **Configuración requerida:**
        - Variables de entorno en `.env`:
          - `SAP_SERVICE_LAYER_URL`
          - `SAP_SERVICE_LAYER_USERNAME`
          - `SAP_SERVICE_LAYER_PASSWORD`
          - `SAP_SERVICE_LAYER_DATABASE`
          - `ENABLE_SAP_SERVICE_LAYER=true`

        Returns:
            JSON con metadata del proceso de envío a SAP
        """
        return _ejecutar_integrar_sap(request, oc_id, referencia_despacho, user)

    @app.get("/sap/test", tags=["Integración SAP"])
    async def test_sap_query(
        request: Request,
        sku: str = FastAPIQuery(..., description="SKU del producto a consultar en SAP (ej: 5-0012.9)")
    ):
        """
        Endpoint de prueba para consultar información de un producto desde SAP.

        Este endpoint permite probar la integración con SAP sin necesidad de procesar
        una factura completa. Consulta información del producto y muestra el resultado.

        **Parámetros:**
        - `sku`: SKU del producto a consultar (requerido)

        **Ejemplo de uso:**
        ```
        GET /sap/test?sku=5-0012.9
        ```

        **Respuesta:**
        - Información del producto desde SAP (ItemCode, ItemName, U_IXX_PACK)
        - Información del cache si está disponible
        - Unidad de conversión calculada

        Returns:
            JSON con información del producto desde SAP o error si falla
        """
        return _ejecutar_test_sap_query(request, sku)

    @app.get("/sap/test/direct", tags=["Integración SAP"])
    async def test_sap_direct(
        request: Request,
        sku: str = FastAPIQuery(..., description="SKU del producto a consultar directamente en SAP")
    ):
        """
        Endpoint de prueba para consulta directa a SAP (sin usar cache).

        Este endpoint consulta directamente a SAP sin verificar el cache primero.
        Útil para forzar una consulta nueva y verificar que la conexión funciona.

        **Parámetros:**
        - `sku`: SKU del producto a consultar (requerido)

        **Ejemplo de uso:**
        ```
        GET /sap/test/direct?sku=5-0012.9
        ```

        Returns:
            JSON con información del producto desde SAP (sin cache)
        """
        return _ejecutar_test_sap_direct(request, sku)
