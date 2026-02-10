"""Endpoint de proceso completo SAP para redistribución."""

import logging
from typing import Dict

from fastapi import FastAPI, Depends, HTTPException, Path, Body, status, Request
from datetime import datetime

from src.database.connection import get_db_connection_context
from src.database.pedido_estados import ESTADO_PEDIDO_CONFIRMADO
from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.services.redistribucion_validator import RedistribucionValidator
from src.security.jwt_auth import verify_jwt_token, require_permission
from src.utils.audit_context import get_audit_context, ORIGEN_WEB
from src.models import (
    RedistribucionConfirmarRequest,
    ProcesoCompletoSAPResponse,
    ProcesoCompletoSAPDetalleODC,
)
from ..utils import get_user_id
from ._helpers import obtener_pedido_o_404, obtener_respuestas_proveedor
from ._converters import convertir_ajustes_a_redistribucion
from ._resumen import calcular_resumen_confirmacion
from ._sap_processing import procesar_pedido_sap_con_homologacion
from ._notifications import notificar_odc_enviada_a_sap

logger = logging.getLogger(__name__)


def register_proceso_completo_endpoints(app: FastAPI):
    """Endpoint de proceso completo SAP."""

    @app.post("/api/pedidos/{numero_pedido}/proceso-completo-sap",
             tags=["Pedidos - Redistribución"])
    async def proceso_completo_sap(
        request: Request,
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: RedistribucionConfirmarRequest = Body(..., description="Datos de redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """Proceso completo: Redistribución + Generar ODC + Enviar a SAP."""
        user_id = get_user_id(user)

        logger.info("=" * 70)
        logger.info(f"🚀 PROCESO COMPLETO SAP iniciado para pedido: {numero_pedido}")
        logger.info(f"   Usuario: {user_id}")
        logger.info("=" * 70)

        resultado_redistribucion = None
        resultado_odc = None
        resultado_envio_sap = None
        resumen = None
        paso_fallido = None
        error_detalle = None
        pedido_id = None

        try:
            with get_db_connection_context() as conn:
                repo_pedido = PedidoRepository(conn)
                repo_dist = DistribucionConfirmadaRepository(conn)

                pedido_data = obtener_pedido_o_404(repo_pedido, numero_pedido, es_numero=True)

                pedido_id = pedido_data["cabecera"]["pedido_id"]

                logger.info("📋 PASO 1/3: Confirmando redistribución...")

                try:
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

                    resumen = calcular_resumen_confirmacion(request_body.ajustes_detalle)
                    total_productos = resumen.total_productos

                    resultado_redistribucion = {
                        "version_confirmada": resultado_crear["version"],
                        "productos_redistribuidos": total_productos,
                        "estado_pedido": "CONFIRMADO REDISTRIBUCION"
                    }

                    logger.info(f"✅ PASO 1/3 completado: Redistribución confirmada (versión {resultado_crear['version']})")

                    try:
                        resultado_sap = await procesar_pedido_sap_con_homologacion(
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
                    paso_fallido = "redistribucion"
                    error_detalle = str(e)
                    logger.error(f"❌ Error en PASO 1 (Redistribución): {e}", exc_info=True)
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail={
                            "error": "redistribucion_error",
                            "message": f"Error al confirmar redistribución: {str(e)}",
                            "paso_fallido": "redistribucion"
                        }
                    )

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
                    paso_fallido = "generar_odc"
                    error_detalle = str(e)
                    logger.error(f"❌ Error en PASO 2 (Generar ODC): {e}", exc_info=True)

                    return ProcesoCompletoSAPResponse(
                        status="partial",
                        message=f"Redistribución exitosa, pero falló la generación de ODC: {str(e)}",
                        pedido_id=pedido_id,
                        numero_pedido=numero_pedido,
                        redistribucion=resultado_redistribucion,
                        odc_generada=None,
                        envio_sap=None,
                        resumen=resumen,
                        fecha_proceso=datetime.now(),
                        paso_fallido="generar_odc",
                        error_detalle=str(e)
                    )

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
                    doc_num = resultado_sap_envio.get("doc_num")
                    error = resultado_sap_envio.get("error")
                    error_code = resultado_sap_envio.get("error_code")

                    resultado_envio_sap = ProcesoCompletoSAPDetalleODC(
                        oc_id=oc_id,
                        proveedor=resultado_odc.get("proveedor"),
                        success=success,
                        doc_entry=doc_entry,
                        doc_num=doc_num,
                        error=error,
                        error_code=error_code
                    )

                    if success:
                        logger.info(f"✅ PASO 3/3 completado: ODC enviada a SAP (DocNum: {doc_num})")

                        try:
                            await notificar_odc_enviada_a_sap(pedido_id, numero_pedido, str(doc_num) if doc_num else None)
                        except Exception as notif_err:
                            logger.warning(f"⚠️ Error al enviar notificación SSE de ODC enviada a SAP: {notif_err}")

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

                        return ProcesoCompletoSAPResponse(
                            status="success",
                            message=f"Proceso completado exitosamente. ODC enviada a SAP con DocNum: {doc_num}",
                            pedido_id=pedido_id,
                            numero_pedido=numero_pedido,
                            redistribucion=resultado_redistribucion,
                            odc_generada=resultado_odc,
                            envio_sap=resultado_envio_sap,
                            resumen=resumen,
                            fecha_proceso=datetime.now(),
                            paso_fallido=None,
                            error_detalle=None
                        )
                    else:
                        logger.error(f"❌ PASO 3/3 fallido: Error al enviar ODC a SAP: {error}")

                        return ProcesoCompletoSAPResponse(
                            status="partial",
                            message=f"Redistribución y ODC generadas, pero falló el envío a SAP: {error}",
                            pedido_id=pedido_id,
                            numero_pedido=numero_pedido,
                            redistribucion=resultado_redistribucion,
                            odc_generada=resultado_odc,
                            envio_sap=resultado_envio_sap,
                            resumen=resumen,
                            fecha_proceso=datetime.now(),
                            paso_fallido="envio_sap",
                            error_detalle=error
                        )

                except Exception as e:
                    paso_fallido = "envio_sap"
                    error_detalle = str(e)
                    logger.error(f"❌ Error en PASO 3 (Enviar a SAP): {e}", exc_info=True)

                    return ProcesoCompletoSAPResponse(
                        status="partial",
                        message=f"Redistribución y ODC generadas, pero falló el envío a SAP: {str(e)}",
                        pedido_id=pedido_id,
                        numero_pedido=numero_pedido,
                        redistribucion=resultado_redistribucion,
                        odc_generada=resultado_odc,
                        envio_sap=None,
                        resumen=resumen,
                        fecha_proceso=datetime.now(),
                        paso_fallido="envio_sap",
                        error_detalle=str(e)
                    )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error general en proceso completo SAP: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno en proceso completo SAP: {str(e)}",
                    "paso_fallido": paso_fallido or "desconocido",
                    "error_detalle": error_detalle or str(e)
                }
            )
