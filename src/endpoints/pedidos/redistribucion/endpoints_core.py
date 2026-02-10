"""Endpoints core de redistribución (por UUID)."""

import logging
from typing import Dict, Optional

from fastapi import FastAPI, Depends, HTTPException, Path, Query, Body, status, Request
from fastapi.responses import JSONResponse, StreamingResponse
from datetime import datetime

from src.database.connection import get_db_connection_context
from src.database.pedido_estados import ESTADO_REDISTRIBUIDO, ESTADO_PEDIDO_CONFIRMADO
from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.services.redistribucion_validator import RedistribucionValidator
from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission
from src.utils.audit_context import get_audit_context, ORIGEN_WEB
from src.models import (
    DistribucionPedidoResponse,
    DistribucionProductoResponse,
    RedistribuirPedidoRequest,
    ConfirmarRedistribucionRequest,
    ConfirmarRedistribucionResponse,
    ReporteDiferenciasResponse,
)
from ..utils import get_user_id
from ._helpers import (
    obtener_pedido_o_404,
    obtener_respuestas_proveedor,
    enriquecer_productos_con_pedido,
    calcular_estado_puede_descartar,
)
from ._sap_processing import procesar_pedido_sap_con_homologacion
from ._notifications import notificar_redistribucion_confirmada
from ._excel_generators import generar_excel_reporte_diferencias

logger = logging.getLogger(__name__)


def register_core_endpoints(app: FastAPI):
    """Endpoints core de redistribución (por UUID)."""

    @app.get("/api/pedidos/{pedido_id}/distribucion",
             response_model=DistribucionPedidoResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_distribucion(
        pedido_id: str = Path(..., description="UUID del pedido"),
        version: Optional[int] = Query(None, ge=1, description="Versión específica (si no se especifica, obtiene la última)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Obtiene la distribución confirmada de un pedido.
        """
        try:
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)

                # Obtener distribución
                distribucion_data = repo_dist.get_distribucion_completa(pedido_id, version)

                # Obtener datos del pedido para completar información
                pedido_data = obtener_pedido_o_404(repo_pedido, pedido_id)

                productos_enriquecidos = enriquecer_productos_con_pedido(
                    distribucion_data.get("productos", []),
                    pedido_data.get("detalles", []),
                )

                cabecera = pedido_data["cabecera"]
                puede_descartar = calcular_estado_puede_descartar(cabecera)

                return DistribucionPedidoResponse(
                    pedido_id=pedido_id,
                    numero_pedido=cabecera["numero_pedido"],
                    version_actual=distribucion_data["version_actual"],
                    estado_pedido=cabecera.get("estado"),
                    puede_descartar=puede_descartar,
                    productos=[DistribucionProductoResponse(**p) for p in productos_enriquecidos]
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener distribución: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al obtener distribución: {str(e)}"
                }
            )

    @app.post("/api/pedidos/{pedido_id}/redistribuir", tags=["Pedidos - Redistribución"])
    async def redistribuir_pedido(
        request: Request,
        pedido_id: str = Path(..., description="UUID del pedido"),
        request_body: RedistribuirPedidoRequest = Body(..., description="Datos de la redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """Crea una nueva redistribución para un pedido."""
        try:
            user_id = get_user_id(user)

            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)

                # Obtener datos completos del pedido
                pedido_data = obtener_pedido_o_404(repo_pedido, pedido_id)

                # Obtener respuestas del proveedor
                respuestas_proveedor = obtener_respuestas_proveedor(repo_pedido, pedido_id)

                # Validar redistribución
                validator = RedistribucionValidator()
                productos_dict = [p.model_dump() for p in request_body.productos]
                es_valido, errores = validator.validar_redistribucion(
                    pedido_data,
                    productos_dict,
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

                # Crear contexto de auditoría (Buenas Prácticas - Sección 3)
                audit = get_audit_context(request, user, origen=ORIGEN_WEB)

                # Crear redistribución
                resultado = repo_dist.crear_redistribucion(
                    pedido_id=pedido_id,
                    productos_redistribucion=productos_dict,
                    usuario=user_id,
                    audit_context=audit
                )

                # Actualizar estado del pedido
                repo_pedido.update_estado(pedido_id, ESTADO_REDISTRIBUIDO, audit_context=audit)

                logger.info(f"✅ Redistribución creada para pedido {pedido_id} por usuario {user_id}")

                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "status": "success",
                        "message": resultado["mensaje"],
                        "data": {
                            "pedido_id": resultado["pedido_id"],
                            "version": resultado["version"],
                            "distribuciones_insertadas": resultado["distribuciones_insertadas"]
                        }
                    }
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al redistribuir pedido: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al redistribuir pedido: {str(e)}"
                }
            )

    @app.post("/api/pedidos/{pedido_id}/confirmar-redistribucion",
             response_model=ConfirmarRedistribucionResponse,
             tags=["Pedidos - Redistribución"])
    async def confirmar_redistribucion(
        request: Request,
        pedido_id: str = Path(..., description="UUID del pedido"),
        request_body: ConfirmarRedistribucionRequest = Body(..., description="Datos de confirmación"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """Confirma una redistribución, cambiando su estado a 'CONFIRMADO'."""
        try:
            user_id = get_user_id(user)

            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)

                # Obtener estado actual del pedido
                pedido_data = obtener_pedido_o_404(repo_pedido, pedido_id)
                estado_anterior = pedido_data["cabecera"].get("estado", "PENDIENTE")

                # Obtener distribución para validar
                distribucion_data = repo_dist.get_distribucion_completa(
                    pedido_id,
                    request_body.version
                )

                # Validar confirmación
                validator = RedistribucionValidator()
                es_valido, errores = validator.validar_confirmacion_redistribucion(
                    pedido_id,
                    request_body.version or distribucion_data["version_actual"],
                    distribucion_data
                )

                if not es_valido:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "validation_error",
                            "message": "La redistribución no puede ser confirmada",
                            "errores": errores
                        }
                    )

                # Crear contexto de auditoría (Buenas Prácticas - Sección 3)
                audit = get_audit_context(request, user, origen=ORIGEN_WEB)

                # Confirmar redistribución
                resultado = repo_dist.confirmar_redistribucion(
                    pedido_id=pedido_id,
                    version=request_body.version,
                    usuario=user_id,
                    audit_context=audit
                )

                # Actualizar estado del pedido a 'REDISTRIBUIDO'
                repo_pedido.update_estado(pedido_id, ESTADO_REDISTRIBUIDO, audit_context=audit)
                estado_nuevo = "REDISTRIBUIDO"

                logger.info(f"✅ Redistribución confirmada para pedido {pedido_id} por usuario {user_id}")

                # 📢 Notificación en tiempo real a EL RAYO
                try:
                    _numero_pedido = pedido_data["cabecera"].get("numero_pedido", "")
                    await notificar_redistribucion_confirmada(pedido_id, _numero_pedido)
                except Exception as notif_err:
                    logger.warning(f"⚠️ Error al enviar notificación en tiempo real: {notif_err}")

                # NUEVO: Procesar pedido con SAP
                logger.info("=" * 70)
                logger.info("🔄 PROCESANDO: Consultando SAP y procesando productos del pedido...")
                logger.info("=" * 70)

                try:
                    resultado_sap = await procesar_pedido_sap_con_homologacion(
                        pedido_id=pedido_id,
                        user_id=user_id,
                        conn=conn,
                        logger=logger,
                    )

                    # Actualizar estado a CONFIRMADO REDISTRIBUCION si el procesamiento fue exitoso
                    if resultado_sap.get("status") in ["success", "partial"]:
                        repo_pedido.update_estado(pedido_id, ESTADO_PEDIDO_CONFIRMADO)
                        estado_nuevo = "CONFIRMADO REDISTRIBUCION"
                        logger.info(f"✅ Estado del pedido {pedido_id} actualizado a CONFIRMADO REDISTRIBUCION")

                except Exception as sap_error:
                    logger.error(f"❌ Error al procesar pedido con SAP: {sap_error}", exc_info=True)
                    logger.warning("⚠️ La redistribución fue confirmada pero el procesamiento SAP falló")

                logger.info("=" * 70)

                return ConfirmarRedistribucionResponse(
                    pedido_id=pedido_id,
                    numero_pedido=pedido_data["cabecera"]["numero_pedido"],
                    version_confirmada=resultado["version_confirmada"],
                    estado_anterior=estado_anterior,
                    estado_nuevo=estado_nuevo,
                    fecha_confirmacion=datetime.now(),
                    mensaje=resultado["mensaje"]
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

    @app.get("/api/pedidos/{pedido_id}/reporte-diferencias",
             response_model=ReporteDiferenciasResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_reporte_diferencias(
        pedido_id: str = Path(..., description="UUID del pedido"),
        version: Optional[int] = Query(None, ge=1, description="Versión específica (si no se especifica, analiza la última)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['mabel.view', 'odcsap.view']))
    ):
        """Obtiene el reporte de diferencias de una redistribución."""
        try:
            import re
            uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
            es_uuid = uuid_pattern.match(pedido_id.strip()) is not None

            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)

                if es_uuid:
                    logger.info(f"🔍 Detectado UUID: {pedido_id}, usando get_pedido_completo")
                    pedido_data = repo_pedido.get_pedido_completo(pedido_id)
                    pedido_id_real = pedido_id
                else:
                    logger.info(f"🔍 Detectado numero_pedido: {pedido_id}, usando get_pedido_completo_por_numero")
                    pedido_data = repo_pedido.get_pedido_completo_por_numero(pedido_id)
                    if pedido_data:
                        pedido_id_real = pedido_data["cabecera"]["pedido_id"]
                    else:
                        pedido_id_real = None

                if not pedido_data or pedido_id_real is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido: {pedido_id}"
                        }
                    )

                diferencias = repo_dist.calcular_diferencias(pedido_id_real, version)

                return ReporteDiferenciasResponse(
                    pedido_id=pedido_id_real,
                    numero_pedido=pedido_data["cabecera"]["numero_pedido"],
                    version=diferencias["version"],
                    fecha_generacion=datetime.now(),
                    total_productos=diferencias["total_productos"],
                    total_cantidad_solicitada=diferencias["total_cantidad_solicitada"],
                    total_cantidad_confirmada=diferencias["total_cantidad_confirmada"],
                    total_cantidad_asignada=diferencias["total_cantidad_asignada"],
                    total_diferencia_cantidad=diferencias["total_diferencia_cantidad"],
                    total_costo_original=diferencias["total_costo_original"],
                    total_costo_ajustado=diferencias["total_costo_ajustado"],
                    total_diferencia_costo=diferencias["total_diferencia_costo"],
                    diferencias_productos=diferencias["diferencias_productos"],
                    diferencias_tiendas=diferencias["diferencias_tiendas"]
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener reporte de diferencias: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al obtener reporte de diferencias: {str(e)}"
                }
            )

    @app.get("/api/pedidos/{pedido_id}/reporte-diferencias/excel", tags=["Pedidos - Redistribución"])
    async def exportar_reporte_diferencias_excel(
        pedido_id: str = Path(..., description="UUID del pedido"),
        version: Optional[int] = Query(None, ge=1, description="Versión específica (si no se especifica, analiza la última)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['mabel.view', 'odcsap.view']))
    ):
        """Exporta el reporte de diferencias a Excel."""
        try:
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)

                pedido_data = obtener_pedido_o_404(repo_pedido, pedido_id)

                diferencias = repo_dist.calcular_diferencias(pedido_id, version)

                output = generar_excel_reporte_diferencias(diferencias, pedido_data)

                numero_pedido = pedido_data["cabecera"]["numero_pedido"]
                filename = f"reporte_diferencias_{numero_pedido.replace(' ', '_')}_v{diferencias['version']}.xlsx"

                return StreamingResponse(
                    output,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al exportar reporte de diferencias: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al exportar reporte: {str(e)}"
                }
            )
