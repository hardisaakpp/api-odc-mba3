"""
Endpoint de procesamiento SAP.
"""

import logging
import re
from typing import Dict
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Path, status

from src.database.connection import get_db_connection_context
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.repositories.pedido_sap_procesamiento_repository import PedidoSAPProcesamientoRepository
from src.security.jwt_auth import verify_jwt_token, require_permission
from src.models import ProcesamientoSAPResponse, ProductoSAPProcesamientoItem, EstadisticasProcesamientoSAP

logger = logging.getLogger(__name__)


def register_sap_endpoints(app: FastAPI):
    """Registra el endpoint de procesamiento SAP."""
    
    @app.get("/api/pedidos/{pedido_id}/procesamiento-sap",
             response_model=ProcesamientoSAPResponse,
             tags=["Pedidos - SAP"])
    async def obtener_procesamiento_sap(
        pedido_id: str = Path(..., description="UUID del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """Obtiene información de procesamiento SAP de un pedido."""
        try:
            uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
            es_uuid = uuid_pattern.match(pedido_id.strip()) is not None
            
            with get_db_connection_context() as conn:
                pedido_repo = PedidoRepository(conn)
                sap_proc_repo = PedidoSAPProcesamientoRepository(conn)
                
                if es_uuid:
                    logger.info(f"🔍 Detectado UUID: {pedido_id}, usando get_pedido_completo")
                    pedido_data = pedido_repo.get_pedido_completo(pedido_id)
                    if pedido_data:
                        pedido_id_real = pedido_data["cabecera"]["pedido_id"]
                    else:
                        pedido_id_real = None
                else:
                    logger.info(f"🔍 Detectado numero_pedido: {pedido_id}, usando get_pedido_completo_por_numero")
                    pedido_data = pedido_repo.get_pedido_completo_por_numero(pedido_id)
                    if pedido_data:
                        pedido_id_real = pedido_data["cabecera"]["pedido_id"]
                    else:
                        pedido_id_real = None
                
                if not pedido_data or pedido_id_real is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con {'ID' if es_uuid else 'número'}: {pedido_id}"
                        }
                    )
                
                numero_pedido = pedido_data["cabecera"].get("numero_pedido")
                procesamientos = sap_proc_repo.get_procesamientos_por_pedido(pedido_id_real)
                
                productos = []
                total_productos = len(procesamientos)
                productos_homologados = productos_no_homologados = productos_con_error = 0
                total_cantidad_original = total_cantidad_sap = total_precio_original = total_precio_sap = 0.0
                fecha_procesamiento_max = None
                
                for proc in procesamientos:
                    fecha_proc = None
                    if proc.get("fecha_procesamiento"):
                        if isinstance(proc["fecha_procesamiento"], str):
                            try:
                                fecha_proc = datetime.fromisoformat(proc["fecha_procesamiento"].replace('Z', '+00:00'))
                            except:
                                fecha_proc = None
                        elif isinstance(proc["fecha_procesamiento"], datetime):
                            fecha_proc = proc["fecha_procesamiento"]
                    
                    if fecha_proc and (fecha_procesamiento_max is None or fecha_proc > fecha_procesamiento_max):
                        fecha_procesamiento_max = fecha_proc
                    
                    if proc.get("producto_homologado", True):
                        productos_homologados += 1
                    else:
                        productos_no_homologados += 1
                    
                    if proc.get("tipo_problema") == "error" or proc.get("mensaje_error"):
                        productos_con_error += 1
                    
                    if proc.get("cantidad_original"):
                        total_cantidad_original += float(proc["cantidad_original"])
                    if proc.get("cantidad_sap"):
                        total_cantidad_sap += float(proc["cantidad_sap"])
                    if proc.get("total_linea_original"):
                        total_precio_original += float(proc["total_linea_original"])
                    if proc.get("total_linea_sap"):
                        total_precio_sap += float(proc["total_linea_sap"])
                    
                    productos.append(ProductoSAPProcesamientoItem(
                        procesamiento_detalle_id=proc["procesamiento_detalle_id"],
                        pedido_detalle_id=proc["pedido_detalle_id"],
                        codigo_interno=proc["codigo_interno"],
                        descripcion_producto=proc.get("descripcion_producto"),
                        item_code_sap=proc.get("item_code_sap"),
                        pack_sap=proc.get("pack_sap"),
                        unidad_conversion=proc.get("unidad_conversion"),
                        unidad_original=proc.get("unidad_original"),
                        unidad_sap=proc.get("unidad_sap"),
                        cantidad_original=proc.get("cantidad_original"),
                        cantidad_sap=proc.get("cantidad_sap"),
                        precio_unitario_original=proc.get("precio_unitario_original"),
                        precio_unitario_sap=proc.get("precio_unitario_sap"),
                        total_linea_original=proc.get("total_linea_original"),
                        total_linea_sap=proc.get("total_linea_sap"),
                        producto_homologado=proc.get("producto_homologado", True),
                        tipo_problema=proc.get("tipo_problema"),
                        item_code_sap_encontrado=proc.get("item_code_sap_encontrado"),
                        mensaje_error=proc.get("mensaje_error"),
                        fecha_procesamiento=fecha_proc,
                        procesado_por=proc.get("procesado_por")
                    ))
                
                estadisticas = EstadisticasProcesamientoSAP(
                    total_productos=total_productos,
                    productos_homologados=productos_homologados,
                    productos_no_homologados=productos_no_homologados,
                    productos_con_error=productos_con_error,
                    total_cantidad_original=total_cantidad_original if total_cantidad_original > 0 else None,
                    total_cantidad_sap=total_cantidad_sap if total_cantidad_sap > 0 else None,
                    total_precio_original=total_precio_original if total_precio_original > 0 else None,
                    total_precio_sap=total_precio_sap if total_precio_sap > 0 else None
                )
                
                return ProcesamientoSAPResponse(
                    status="success",
                    pedido_id=pedido_id_real,
                    numero_pedido=numero_pedido,
                    productos=productos,
                    estadisticas=estadisticas,
                    fecha_procesamiento=fecha_procesamiento_max
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener procesamiento SAP: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error interno al obtener procesamiento SAP: {str(e)}"
            )
