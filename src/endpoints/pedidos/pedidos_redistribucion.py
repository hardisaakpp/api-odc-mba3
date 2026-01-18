"""
Endpoints de redistribución de pedidos.
"""

import logging
from typing import Dict, Optional
from fastapi import FastAPI, Depends, HTTPException, Path, Query, Body, status
from fastapi.responses import JSONResponse, Response
from datetime import datetime

from src.security.jwt_auth import verify_jwt_token, require_permission
from src.models import (
    DistribucionPedidoResponse,
    RedistribuirPedidoRequest,
    ConfirmarRedistribucionRequest,
    ConfirmarRedistribucionResponse,
    ReporteDiferenciasResponse,
    RedistribucionConfirmarRequest,
    ConfirmarRedistribucionResponseFrontend,
    GuardarBorradorRequest,
    GuardarBorradorResponse,
    BorradorResponse
)
from .utils import get_user_id

logger = logging.getLogger(__name__)


def register_redistribucion_endpoints(app: FastAPI):
    """Registra los endpoints de redistribución de pedidos."""
    
    @app.get("/api/pedidos/{pedido_id}/distribucion", 
             response_model=DistribucionPedidoResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_distribucion(
        pedido_id: str = Path(..., description="UUID del pedido"),
        version: Optional[int] = Query(None, ge=1, description="Versión específica (si no se especifica, obtiene la última)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """Obtiene la distribución confirmada de un pedido."""
        try:
            from src.database.connection import get_db_connection_context
            from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
            from src.database.repositories.pedido_repository import PedidoRepository
            
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)
                
                distribucion_data = repo_dist.get_distribucion_completa(pedido_id, version)
                pedido_data = repo_pedido.get_pedido_completo(pedido_id)
                
                if not pedido_data:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                      detail={"error": "pedido_not_found",
                                             "message": f"No se encontró el pedido con ID: {pedido_id}"})
                
                productos_enriquecidos = []
                for producto_dist in distribucion_data["productos"]:
                    pedido_detalle_id = producto_dist["pedido_detalle_id"]
                    detalle_pedido = next((d for d in pedido_data["detalles"] 
                                         if d["pedido_detalle_id"] == pedido_detalle_id), None)
                    
                    if detalle_pedido:
                        productos_enriquecidos.append({
                            "pedido_detalle_id": pedido_detalle_id,
                            "codigo_interno": detalle_pedido.get("codigo_interno"),
                            "descripcion_sap": detalle_pedido.get("descripcion_sap"),
                            "cantidad_solicitada_total": producto_dist["cantidad_solicitada_total"],
                            "cantidad_confirmada_total": producto_dist["cantidad_confirmada_total"],
                            "cantidad_asignada_total": producto_dist["cantidad_asignada_total"],
                            "distribuciones": producto_dist["distribuciones"]
                        })
                    else:
                        productos_enriquecidos.append(producto_dist)
                
                return DistribucionPedidoResponse(
                    pedido_id=pedido_id,
                    numero_pedido=pedido_data["cabecera"]["numero_pedido"],
                    version_actual=distribucion_data["version_actual"],
                    estado_pedido=pedido_data["cabecera"].get("estado"),
                    productos=productos_enriquecidos
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener distribución: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                              detail={"error": "internal_error",
                                     "message": f"Error interno al obtener distribución: {str(e)}"})
    
    @app.post("/api/pedidos/{pedido_id}/redistribuir", tags=["Pedidos - Redistribución"])
    async def redistribuir_pedido(
        pedido_id: str = Path(..., description="UUID del pedido"),
        request_body: RedistribuirPedidoRequest = Body(..., description="Datos de la redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """Crea una nueva redistribución para un pedido (OBLIGATORIO - Fase 4)."""
        try:
            from src.database.services.redistribucion_service import RedistribucionService
            
            user_id = get_user_id(user)
            service = RedistribucionService()
            
            resultado = service.crear_redistribucion(
                pedido_id=pedido_id,
                productos=request_body.productos,
                observaciones=request_body.observaciones,
                usuario_id=user_id
            )
            
            return JSONResponse(status_code=200, content=resultado)
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"error": "validation_error", "message": str(e)})
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al redistribuir pedido: {e}", exc_info=True)
            raise HTTPException(status_code=500, 
                              detail={"error": "internal_error", "message": f"Error interno: {str(e)}"})
    
    @app.post("/api/pedidos/{pedido_id}/confirmar-redistribucion",
              response_model=ConfirmarRedistribucionResponse,
              tags=["Pedidos - Redistribución"])
    async def confirmar_redistribucion(
        pedido_id: str = Path(..., description="UUID del pedido"),
        request_body: ConfirmarRedistribucionRequest = Body(...),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """Confirma la redistribución actual del pedido."""
        try:
            from src.database.services.redistribucion_service import RedistribucionService
            
            user_id = get_user_id(user)
            service = RedistribucionService()
            
            resultado = service.confirmar_redistribucion(
                pedido_id=pedido_id,
                version=request_body.version,
                usuario_id=user_id
            )
            
            return ConfirmarRedistribucionResponse(**resultado)
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al confirmar redistribución: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
    
    @app.get("/api/pedidos/{pedido_id}/reporte-diferencias",
             response_model=ReporteDiferenciasResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_reporte_diferencias(
        pedido_id: str = Path(..., description="UUID del pedido"),
        version: Optional[int] = Query(None, ge=1, description="Versión específica (si no se especifica, analiza la última)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """Obtiene el reporte de diferencias de una redistribución."""
        try:
            import re
            from src.database.connection import get_db_connection_context
            from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
            from src.database.repositories.pedido_repository import PedidoRepository
            
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
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                      detail={"error": "pedido_not_found",
                                             "message": f"No se encontró el pedido: {pedido_id}"})
                
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
                    productos=diferencias["productos"]
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener reporte de diferencias: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
    
    @app.get("/api/pedidos/{pedido_id}/reporte-diferencias/excel", tags=["Pedidos - Redistribución"])
    async def descargar_reporte_diferencias_excel(
        pedido_id: str = Path(..., description="UUID del pedido"),
        version: Optional[int] = Query(None, ge=1, description="Versión específica"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """Descarga el reporte de diferencias en formato Excel."""
        try:
            from src.database.services.redistribucion_export_service import RedistribucionExportService
            
            service = RedistribucionExportService()
            excel_bytes = service.exportar_reporte_diferencias(pedido_id, version)
            
            return Response(
                content=excel_bytes,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="reporte_diferencias_{pedido_id}_{datetime.now().strftime("%Y%m%d")}.xlsx"'}
            )
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"❌ Error al exportar reporte: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
    
    @app.post("/api/pedidos/{numero_pedido}/redistribucion/borrador",
              response_model=GuardarBorradorResponse,
              tags=["Pedidos - Redistribución"])
    async def guardar_borrador_redistribucion(
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: GuardarBorradorRequest = Body(...),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """Guarda un borrador de redistribución."""
        try:
            from src.database.services.redistribucion_borrador_service import RedistribucionBorradorService
            
            user_id = get_user_id(user)
            service = RedistribucionBorradorService()
            
            resultado = service.guardar_borrador(
                numero_pedido=numero_pedido,
                ajustes_detalle=request_body.ajustes_detalle,
                usuario_id=user_id
            )
            
            return GuardarBorradorResponse(**resultado)
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"❌ Error al guardar borrador: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
    
    @app.get("/api/pedidos/{numero_pedido}/redistribucion/borrador",
             response_model=BorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_borrador_redistribucion(
        numero_pedido: str = Path(..., description="Número del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """Obtiene el borrador de redistribución guardado."""
        try:
            from src.database.services.redistribucion_borrador_service import RedistribucionBorradorService
            
            service = RedistribucionBorradorService()
            resultado = service.obtener_borrador(numero_pedido)
            
            return BorradorResponse(**resultado)
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"❌ Error al obtener borrador: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
    
    @app.get("/api/pedidos/{numero_pedido}/redistribucion/inicial", tags=["Pedidos - Redistribución"])
    async def obtener_redistribucion_inicial(
        numero_pedido: str = Path(..., description="Número del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.facturas.view'))
    ):
        """Obtiene la redistribución inicial (desde respuesta del proveedor)."""
        try:
            from src.database.services.redistribucion_inicial_service import RedistribucionInicialService
            
            service = RedistribucionInicialService()
            resultado = service.obtener_redistribucion_inicial(numero_pedido)
            
            return JSONResponse(status_code=200, content=resultado)
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"❌ Error al obtener redistribución inicial: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
    
    @app.post("/api/pedidos/{numero_pedido}/redistribucion/confirmar",
              response_model=ConfirmarRedistribucionResponseFrontend,
              tags=["Pedidos - Redistribución"])
    async def confirmar_redistribucion_frontend(
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: RedistribucionConfirmarRequest = Body(...),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mba3-consultas.proceso.execute'))
    ):
        """Confirma la redistribución desde el frontend."""
        try:
            from src.database.services.redistribucion_frontend_service import RedistribucionFrontendService
            
            user_id = get_user_id(user)
            service = RedistribucionFrontendService()
            
            resultado = service.confirmar_redistribucion_frontend(
                numero_pedido=numero_pedido,
                ajustes_detalle=request_body.ajustes_detalle,
                usuario_id=user_id
            )
            
            return ConfirmarRedistribucionResponseFrontend(**resultado)
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al confirmar redistribución: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
