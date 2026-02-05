"""
Endpoints de redistribución de pedidos.
"""

import logging
import json
from typing import Dict, Optional, Any
from fastapi import FastAPI, Depends, HTTPException, Path, Query, Body, status
from fastapi.responses import JSONResponse, StreamingResponse
from datetime import datetime
import pandas as pd
from io import BytesIO

from src.database.connection import get_db_connection_context
from src.database.pedido_estados import (
    ESTADO_REDISTRIBUCION,
    ESTADO_REDISTRIBUIDO,
    ESTADO_PEDIDO_CONFIRMADO,
    ESTADO_LIMITE_CANCELAR_PEDIDO,
    estado_id_desde_legacy,
)
from src.database.repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
from src.database.repositories.pedido_repository import PedidoRepository
from src.database.services.redistribucion_validator import RedistribucionValidator
from src.security.jwt_auth import verify_jwt_token, require_permission, require_any_permission
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
    BorradorResponse,
    AjusteDetalle,
    DistribucionTiendaFrontend,
    ResumenConfirmacion
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
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Obtiene la distribución confirmada de un pedido.
        
        **Funcionalidad:**
        - Obtiene la redistribución realizada por MABEL TRADING
        - Incluye cantidades solicitadas, confirmadas y asignadas
        - Muestra costos originales y ajustados
        - Permite especificar una versión específica o obtener la última
        
        **Query Parameters:**
        - `version` (int, opcional): Versión específica a obtener. Si no se especifica, obtiene la última versión.
        
        **Response:**
        ```json
        {
            "pedido_id": "...",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "version_actual": 1,
            "estado_pedido": "CONFIRMADO",
            "productos": [
                {
                    "pedido_detalle_id": "...",
                    "codigo_interno": "R225.1012.BCO",
                    "descripcion_sap": "...",
                    "cantidad_solicitada_total": 100,
                    "cantidad_confirmada_total": 80,
                    "cantidad_asignada_total": 75,
                    "distribuciones": [...]
                }
            ]
        }
        ```
        """
        try:
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)
                
                # Obtener distribución
                distribucion_data = repo_dist.get_distribucion_completa(pedido_id, version)
                
                # Obtener datos del pedido para completar información
                pedido_data = repo_pedido.get_pedido_completo(pedido_id)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con ID: {pedido_id}"
                        }
                    )
                
                # Enriquecer productos con información del pedido
                productos_enriquecidos = []
                for producto_dist in distribucion_data["productos"]:
                    pedido_detalle_id = producto_dist["pedido_detalle_id"]
                    
                    # Buscar detalle en el pedido
                    detalle_pedido = next(
                        (d for d in pedido_data["detalles"] if d["pedido_detalle_id"] == pedido_detalle_id),
                        None
                    )
                    
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
                
                cabecera = pedido_data["cabecera"]
                _eid = cabecera.get("estado_id")
                if _eid is None and cabecera.get("estado"):
                    _eid = estado_id_desde_legacy(cabecera.get("estado"))
                try:
                    _eid = int(_eid) if _eid is not None else None
                except (TypeError, ValueError):
                    _eid = None
                # Deshabilitar "Cancelar Pedido" desde Confirmado redistribución (estado 10) en adelante
                puede_descartar = _eid is not None and _eid < ESTADO_LIMITE_CANCELAR_PEDIDO
                
                return DistribucionPedidoResponse(
                    pedido_id=pedido_id,
                    numero_pedido=cabecera["numero_pedido"],
                    version_actual=distribucion_data["version_actual"],
                    estado_pedido=cabecera.get("estado"),
                    puede_descartar=puede_descartar,
                    productos=productos_enriquecidos
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
        pedido_id: str = Path(..., description="UUID del pedido"),
        request_body: RedistribuirPedidoRequest = Body(..., description="Datos de la redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Crea una nueva redistribución para un pedido (OBLIGATORIO - Fase 4).
        
        **FASE 4: Redistribución por MABEL TRADING (OBLIGATORIA)**
        
        Este endpoint es OBLIGATORIO después de que EL RAYO confirma los cambios (Fase 3).
        MABEL TRADING debe redistribuir manualmente las cantidades por tienda desde el total confirmado.
        
        **Funcionalidad:**
        - Crea una nueva versión de redistribución
        - Valida reglas de negocio estrictas
        - Permite a MABEL TRADING redistribuir manualmente desde el total confirmado
        - Los costos unitarios NO se recalculan (permanecen como los guardó EL RAYO)
        - Versiona automáticamente la redistribución
        
        **Características importantes:**
        - ✅ Los costos unitarios permanecen tal como los guardó EL RAYO
        - ❌ NO se recalculan costos
        - ❌ NO se genera reporte de diferencias
        - ✅ La redistribución es OBLIGATORIA (no opcional)
        
        **Validaciones:**
        - No valores negativos
        - ⭐ Las bodegas y tiendas son independientes: pueden modificarse libremente sin afectarse mutuamente
        - Todas las tiendas pertenecen al pedido
        - No duplicados de tienda por producto
        - El pedido debe tener respuesta del proveedor
        - Estado del pedido debe ser CONFIRMADO (solo este estado permite confirmar redistribución)
        
        **Request:**
        ```json
        {
            "productos": [
                {
                    "pedido_detalle_id": "...",
                    "distribuciones": [
                        {"tienda_id": "...", "cantidad_asignada": 50},
                        {"tienda_id": "...", "cantidad_asignada": 30}
                    ]
                }
            ],
            "observaciones": "Ajuste por disponibilidad de stock"
        }
        ```
        
        **Response:**
        ```json
        {
            "status": "success",
            "message": "Redistribución creada exitosamente (versión 1)",
            "data": {
                "pedido_id": "...",
                "version": 1,
                "distribuciones_insertadas": 2
            }
        }
        ```
        """
        try:
            user_id = get_user_id(user)
            
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)
                
                # Obtener datos completos del pedido
                pedido_data = repo_pedido.get_pedido_completo(pedido_id)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con ID: {pedido_id}"
                        }
                    )
                
                # Obtener respuestas del proveedor
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        rpd.pedido_detalle_id,
                        rpd.cantidad_solicitada_total,
                        rpd.cantidad_confirmada_total
                    FROM pedido_respuesta_proveedor_detalle rpd
                    INNER JOIN pedido_respuesta_proveedor rp ON rpd.respuesta_id = rp.respuesta_id
                    WHERE rp.pedido_id = ?
                    ORDER BY rp.version DESC, rp.fecha_respuesta DESC
                """, (pedido_id,))
                
                respuestas_proveedor = {}
                for row in cursor.fetchall():
                    respuestas_proveedor[str(row[0])] = {
                        "cantidad_solicitada_total": row[1],
                        "cantidad_confirmada_total": row[2]
                    }
                
                # Preparar datos para validación
                productos_redistribucion = []
                for producto in request_body.productos:
                    productos_redistribucion.append({
                        "pedido_detalle_id": producto.pedido_detalle_id,
                        "distribuciones": [
                            {
                                "tienda_id": d.tienda_id,
                                "cantidad_asignada": d.cantidad_asignada
                            }
                            for d in producto.distribuciones
                        ]
                    })
                
                # Validar redistribución
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
                
                # Crear redistribución
                resultado = repo_dist.crear_redistribucion(
                    pedido_id=pedido_id,
                    productos_redistribucion=productos_redistribucion,
                    usuario=user_id
                )
                
                # Actualizar estado del pedido a CONFIRMADO (solo este estado permite Confirmar Redistribución)
                repo_pedido.update_estado(pedido_id, ESTADO_REDISTRIBUCION)
                
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
        pedido_id: str = Path(..., description="UUID del pedido"),
        request_body: ConfirmarRedistribucionRequest = Body(..., description="Datos de confirmación"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Confirma una redistribución, cambiando su estado a 'CONFIRMADO'.
        
        **Funcionalidad:**
        - Cambia el estado de todas las distribuciones a 'CONFIRMADO'
        - Actualiza el estado del pedido a 'REDISTRIBUIDO' (endpoint interno)
        - Registra auditoría de la confirmación
        
        **Request:**
        ```json
        {
            "version": 1,
            "observaciones": "Redistribución validada y confirmada"
        }
        ```
        
        **Response:**
        ```json
        {
            "pedido_id": "...",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "version_confirmada": 1,
            "estado_anterior": "CONFIRMADO",
            "estado_nuevo": "REDISTRIBUIDO",
            "fecha_confirmacion": "2025-01-15T10:30:00Z",
            "mensaje": "Redistribución versión 1 confirmada exitosamente"
        }
        ```
        """
        try:
            user_id = get_user_id(user)
            
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)
                
                # Obtener estado actual del pedido
                pedido_data = repo_pedido.get_pedido_completo(pedido_id)
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con ID: {pedido_id}"
                        }
                    )
                
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
                
                # Confirmar redistribución
                resultado = repo_dist.confirmar_redistribucion(
                    pedido_id=pedido_id,
                    version=request_body.version,
                    usuario=user_id
                )
                
                # Actualizar estado del pedido a 'REDISTRIBUIDO' (endpoint interno)
                repo_pedido.update_estado(pedido_id, ESTADO_REDISTRIBUIDO)
                estado_nuevo = "REDISTRIBUIDO"
                
                logger.info(f"✅ Redistribución confirmada para pedido {pedido_id} por usuario {user_id}")
                
                # NUEVO: Procesar pedido con SAP (similar a MIGRAR pero para pedidos)
                logger.info("=" * 70)
                logger.info("🔄 PROCESANDO: Consultando SAP y procesando productos del pedido...")
                logger.info("=" * 70)
                
                try:
                    from src.database.services.pedido_sap_service import procesar_pedido_con_sap
                    from src.database.services.homologacion_service import HomologacionService
                    from src.utils.email_notifier import send_homologacion_notification
                    
                    homologacion_service = HomologacionService()
                    
                    # Procesar pedido con SAP
                    resultado_sap = procesar_pedido_con_sap(
                        pedido_id=pedido_id,
                        usuario_id=user_id,
                        homologacion_service=homologacion_service,
                        continue_on_error=True
                    )
                    
                    logger.info(f"✅ Procesamiento SAP completado: {resultado_sap.get('productos_procesados', 0)} productos procesados")
                    
                    # Actualizar estado a CONFIRMADO REDISTRIBUCION si el procesamiento fue exitoso
                    if resultado_sap.get("status") in ["success", "partial"]:
                        repo_pedido.update_estado(pedido_id, ESTADO_PEDIDO_CONFIRMADO)
                        estado_nuevo = "CONFIRMADO REDISTRIBUCION"
                        logger.info(f"✅ Estado del pedido {pedido_id} actualizado a CONFIRMADO REDISTRIBUCION")
                    
                    # Verificar productos no homologados y notificar
                    if resultado_sap.get("productos_no_homologados", 0) > 0:
                        logger.info("🔍 Verificando productos no homologados...")
                        
                        try:
                            from src.database.repositories.homologacion_repository import HomologacionRepository
                            
                            # Obtener TODOS los productos no homologados con estadísticas
                            todos_productos = homologacion_service.get_todos_productos_no_homologados()
                            productos_no_homologados = todos_productos.get("productos", [])
                            estadisticas = todos_productos.get("estadisticas", {})
                            
                            if productos_no_homologados and len(productos_no_homologados) > 0:
                                logger.info(f"⚠️ Se detectaron {len(productos_no_homologados)} productos no homologados")
                                
                                # Crear repository para filtrar productos ya notificados
                                repository = HomologacionRepository(conn)
                                
                                # Enviar notificación FILTRANDO productos ya notificados
                                email_enviado = send_homologacion_notification(
                                    productos_no_homologados=productos_no_homologados,
                                    estadisticas=estadisticas,
                                    fecha_ejecucion=datetime.now(),
                                    filtrar_ya_notificados=True,  # Filtrar ya notificados
                                    homologacion_repository=repository
                                )
                                
                                if email_enviado:
                                    logger.info("✅ Notificación de homologación enviada (solo productos nuevos)")
                                else:
                                    logger.info("⏭️ No se envió notificación (todos ya fueron notificados)")
                            else:
                                logger.info("✅ No hay productos no homologados nuevos para notificar")
                                
                        except Exception as homolog_error:
                            logger.warning(f"⚠️ Error al verificar homologaciones: {homolog_error}")
                            # No afectar la respuesta principal
                    
                except Exception as sap_error:
                    logger.error(f"❌ Error al procesar pedido con SAP: {sap_error}", exc_info=True)
                    # No afectar la confirmación de redistribución, solo loguear el error
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
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Obtiene el reporte de diferencias de una redistribución.
        
        **Funcionalidad:**
        - Calcula diferencias entre cantidades solicitadas, confirmadas y asignadas
        - Muestra diferencias por producto y por tienda
        - Calcula diferencias de costos
        - Genera totales consolidados
        
        **Query Parameters:**
        - `version` (int, opcional): Versión específica a analizar. Si no se especifica, analiza la última versión.
        
        **Response:**
        ```json
        {
            "pedido_id": "...",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "version": 1,
            "fecha_generacion": "2025-01-15T10:30:00Z",
            "total_productos": 5,
            "total_cantidad_solicitada": 500,
            "total_cantidad_confirmada": 400,
            "total_cantidad_asignada": 380,
            "total_diferencia_cantidad": -20,
            "total_costo_original": 10000.00,
            "total_costo_ajustado": 9500.00,
            "total_diferencia_costo": -500.00,
            "diferencias_productos": [...],
            "diferencias_tiendas": [...]
        }
        ```
        """
        try:
            import re
            # Detectar si es UUID o numero_pedido
            uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
            es_uuid = uuid_pattern.match(pedido_id.strip()) is not None
            
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)
                
                # Obtener datos del pedido (detectar si es UUID o numero_pedido)
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
                
                # Calcular diferencias usando el pedido_id real (UUID)
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
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Exporta el reporte de diferencias a Excel.
        
        **Funcionalidad:**
        - Genera un archivo Excel con el reporte completo de diferencias
        - Incluye hojas para diferencias por producto y por tienda
        - Incluye resumen con totales
        
        **Query Parameters:**
        - `version` (int, opcional): Versión específica a analizar. Si no se especifica, analiza la última versión.
        
        **Response:**
        - Archivo Excel descargable (.xlsx)
        """
        try:
            from fastapi.responses import StreamingResponse
            
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)
                
                # Obtener datos del pedido
                pedido_data = repo_pedido.get_pedido_completo(pedido_id)
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con ID: {pedido_id}"
                        }
                    )
                
                # Calcular diferencias
                diferencias = repo_dist.calcular_diferencias(pedido_id, version)
                
                # Crear Excel
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    # Hoja 1: Resumen
                    resumen_data = {
                        "Concepto": [
                            "Total Productos",
                            "Total Cantidad Solicitada",
                            "Total Cantidad Confirmada",
                            "Total Cantidad Asignada",
                            "Total Diferencia Cantidad",
                            "Total Costo Original",
                            "Total Costo Ajustado",
                            "Total Diferencia Costo"
                        ],
                        "Valor": [
                            diferencias["total_productos"],
                            diferencias["total_cantidad_solicitada"],
                            diferencias["total_cantidad_confirmada"],
                            diferencias["total_cantidad_asignada"],
                            diferencias["total_diferencia_cantidad"],
                            diferencias["total_costo_original"] or 0,
                            diferencias["total_costo_ajustado"] or 0,
                            diferencias["total_diferencia_costo"] or 0
                        ]
                    }
                    pd.DataFrame(resumen_data).to_excel(writer, sheet_name="Resumen", index=False)
                    
                    # Hoja 2: Diferencias por Producto
                    if diferencias["diferencias_productos"]:
                        df_productos = pd.DataFrame(diferencias["diferencias_productos"])
                        df_productos.to_excel(writer, sheet_name="Diferencias por Producto", index=False)
                    
                    # Hoja 3: Diferencias por Tienda
                    if diferencias["diferencias_tiendas"]:
                        df_tiendas = pd.DataFrame(diferencias["diferencias_tiendas"])
                        df_tiendas.to_excel(writer, sheet_name="Diferencias por Tienda", index=False)
                
                output.seek(0)
                
                numero_pedido = pedido_data["cabecera"]["numero_pedido"]
                filename = f"reporte_diferencias_{numero_pedido.replace(' ', '_')}_v{diferencias['version']}.xlsx"
                
                return StreamingResponse(
                    BytesIO(output.read()),
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
    
    # ============================================================================
    # ENDPOINTS FASE 4: Compatibles con Frontend (usando numero_pedido y AjusteDetalle)
    # ============================================================================
    
    @app.post("/api/pedidos/{numero_pedido}/redistribucion/borrador",
             response_model=GuardarBorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def guardar_borrador_redistribucion(
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: GuardarBorradorRequest = Body(..., description="Datos del borrador de redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Guarda un borrador de redistribución.
        
        **Funcionalidad:**
        - Guarda la redistribución como borrador (no la confirma)
        - Permite recuperar el borrador más tarde
        - Pasa el pedido a estado CONFIRMADO para permitir luego Confirmar Redistribución
        
        **Request:**
        ```json
        {
            "ajustes_detalle": [
                {
                    "codigo_producto": "R225.1012.BCO",
                    "descripcion": "Producto ejemplo",
                    "cantidad_solicitada": 100,
                    "cantidad_confirmada": 80,
                    "cantidad_ajustada": 75,
                    "distribucion_tiendas": [
                        {"tienda_codigo": "T001", "tienda_nombre": "Tienda 1", "cantidad": 50},
                        {"tienda_codigo": "T002", "tienda_nombre": "Tienda 2", "cantidad": 25}
                    ],
                    "costo_original": 25.50,
                    "costo_ajustado": 25.50,
                    "cambio_precio": false
                }
            ]
        }
        ```
        
        **Response:**
        ```json
        {
            "status": "success",
            "message": "Borrador guardado exitosamente",
            "pedido_id": "...",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "fecha_guardado": "2025-01-15T10:30:00Z"
        }
        ```
        """
        try:
            user_id = get_user_id(user)
            
            with get_db_connection_context() as conn:
                repo_pedido = PedidoRepository(conn)
                
                # Obtener pedido por número
                pedido_data = repo_pedido.get_pedido_completo_por_numero(numero_pedido)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con número: {numero_pedido}"
                        }
                    )
                
                pedido_id = pedido_data["cabecera"]["pedido_id"]
                
                # Guardar borrador en una tabla temporal o en JSON
                # Por ahora, guardamos en una tabla de borradores (crear si no existe)
                cursor = conn.cursor()
                
                # Verificar si existe tabla de borradores
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_NAME = 'redistribucion_borrador'
                """)
                result = cursor.fetchone()
                existe_tabla = result[0] > 0 if result else False
                
                if not existe_tabla:
                    # Crear tabla de borradores
                    cursor.execute("""
                        CREATE TABLE redistribucion_borrador (
                            id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
                            pedido_id UNIQUEIDENTIFIER NOT NULL,
                            numero_pedido NVARCHAR(50) NOT NULL,
                            ajustes_detalle NVARCHAR(MAX) NOT NULL,
                            creado_por NVARCHAR(450) NULL,
                            fecha_guardado DATETIME DEFAULT GETDATE(),
                            CONSTRAINT FK_borrador_pedido 
                                FOREIGN KEY (pedido_id) 
                                REFERENCES pedido(pedido_id) 
                                ON DELETE CASCADE
                        )
                    """)
                    cursor.execute("""
                        CREATE INDEX idx_borrador_pedido_id ON redistribucion_borrador(pedido_id)
                    """)
                    cursor.execute("""
                        CREATE INDEX idx_borrador_numero_pedido ON redistribucion_borrador(numero_pedido)
                    """)
                
                # Guardar o actualizar borrador
                ajustes_json = json.dumps([ajuste.dict() for ajuste in request_body.ajustes_detalle])
                
                cursor.execute("""
                    IF EXISTS (SELECT 1 FROM redistribucion_borrador WHERE pedido_id = ?)
                        UPDATE redistribucion_borrador
                        SET ajustes_detalle = ?,
                            fecha_guardado = GETDATE(),
                            creado_por = ?
                        WHERE pedido_id = ?
                    ELSE
                        INSERT INTO redistribucion_borrador (pedido_id, numero_pedido, ajustes_detalle, creado_por)
                        VALUES (?, ?, ?, ?)
                """, (pedido_id, ajustes_json, user_id, pedido_id, pedido_id, numero_pedido, ajustes_json, user_id))
                
                conn.commit()

                # Pasar a CONFIRMADO para que el usuario pueda luego Confirmar Redistribución
                repo_pedido.update_estado(pedido_id, ESTADO_REDISTRIBUCION)
                
                logger.info(f"✅ Borrador guardado para pedido {numero_pedido} por usuario {user_id}")
                
                return GuardarBorradorResponse(
                    pedido_id=pedido_id,
                    numero_pedido=numero_pedido,
                    fecha_guardado=datetime.now(),
                    message="Borrador guardado exitosamente"
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al guardar borrador: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al guardar borrador: {str(e)}"
                }
            )
    
    @app.get("/api/pedidos/{numero_pedido}/redistribucion/borrador",
             response_model=BorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_borrador_redistribucion(
        numero_pedido: str = Path(..., description="Número del pedido"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Obtiene el borrador de redistribución guardado.
        
        **Funcionalidad:**
        - Recupera el borrador guardado previamente
        - Permite continuar editando desde donde se dejó
        
        **Response:**
        ```json
        {
            "status": "success",
            "ajustes_detalle": [...],
            "fecha_guardado": "2025-01-15T10:30:00Z"
        }
        ```
        """
        try:
            with get_db_connection_context() as conn:
                repo_pedido = PedidoRepository(conn)
                
                # Obtener pedido por número
                pedido_data = repo_pedido.get_pedido_completo_por_numero(numero_pedido)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con número: {numero_pedido}"
                        }
                    )
                
                pedido_id = pedido_data["cabecera"]["pedido_id"]
                
                # Obtener borrador
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT ajustes_detalle, fecha_guardado
                    FROM redistribucion_borrador
                    WHERE pedido_id = ?
                """, (pedido_id,))
                
                row = cursor.fetchone()
                
                if not row:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "borrador_not_found",
                            "message": "No se encontró un borrador guardado para este pedido"
                        }
                    )
                
                ajustes_json = row[0]
                fecha_guardado = row[1]
                
                # Parsear JSON
                ajustes_list = json.loads(ajustes_json)
                
                # Sincronizar costos y totales con los valores actuales del pedido
                detalles_pedido_map = {
                    detalle.get("codigo_interno"): detalle 
                    for detalle in pedido_data.get("detalles", [])
                }
                
                ajustes_detalle_sincronizados = []
                for ajuste_dict in ajustes_list:
                    codigo_producto = ajuste_dict.get("codigo_producto")
                    detalle_pedido = detalles_pedido_map.get(codigo_producto)
                    
                    if detalle_pedido:
                        # Sincronizar costo unitario con el valor actual del pedido
                        costo_actual = detalle_pedido.get("costo_doc_sin_iva")
                        if costo_actual is not None:
                            ajuste_dict["costo_original"] = costo_actual
                            ajuste_dict["costo_ajustado"] = costo_actual
                        
                        # Sincronizar total (cantidad confirmada) con el valor actual del pedido
                        total_actual = detalle_pedido.get("total")
                        if total_actual is not None:
                            try:
                                cantidad_confirmada_actual = int(float(total_actual))
                                ajuste_dict["cantidad_confirmada"] = cantidad_confirmada_actual
                                # Si cantidad_ajustada es mayor que confirmada, mantenerla, sino usar confirmada
                                if ajuste_dict.get("cantidad_ajustada", 0) > cantidad_confirmada_actual:
                                    ajuste_dict["cantidad_ajustada"] = cantidad_confirmada_actual
                            except (ValueError, TypeError):
                                pass
                    
                    ajustes_detalle_sincronizados.append(AjusteDetalle(**ajuste_dict))
                
                return BorradorResponse(
                    ajustes_detalle=ajustes_detalle_sincronizados,
                    fecha_guardado=fecha_guardado
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener borrador: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al obtener borrador: {str(e)}"
                }
            )
    
    @app.get("/api/pedidos/{numero_pedido}/redistribucion/inicial",
             response_model=BorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def obtener_datos_iniciales_redistribucion(
        numero_pedido: str = Path(..., description="Número del pedido"),
        solo_lectura: Optional[str] = Query(None, description="Si es '1' o 'true', devuelve la última redistribución confirmada (para vista solo lectura)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Obtiene los datos iniciales para la redistribución sincronizados con el pedido actualizado.
        
        **Query params:**
        - `solo_lectura`: Si es `1` o `true` y el pedido tiene redistribución confirmada (estado
          CONFIRMADO REDISTRIBUCION o posterior), devuelve la **última redistribución guardada**
          en formato ajustes_detalle, para que la interfaz de solo lectura muestre siempre lo confirmado.
        
        **Funcionalidad (sin solo_lectura):**
        - Genera los datos iniciales de redistribución basándose en el pedido actualizado
        - Sincroniza costos unitarios y totales con los valores actuales del pedido (EL RAYO)
        - Obtiene cantidades confirmadas desde la respuesta del proveedor
        - Usa los costos y totales actualizados del pedido (no valores antiguos)
        - Incluye información de campos modificados manualmente para resaltado visual
        
        **Response:**
        ```json
        {
            "status": "success",
            "ajustes_detalle": [
                {
                    "codigo_producto": "R225.1012.BCO",
                    "descripcion": "Producto ejemplo",
                    "cantidad_solicitada": 100,
                    "cantidad_confirmada": 80,
                    "cantidad_ajustada": 80,
                    "distribucion_tiendas": [...],
                    "costo_original": 25.50,  // ⭐ Sincronizado con pedido actualizado
                    "costo_ajustado": 25.50,  // ⭐ Sincronizado con pedido actualizado
                    "cambio_precio": false,
                    "pedido_detalle_id": "uuid-123",  // ⭐ Para identificar la fila
                    "costo_modificado_manual": true,   // ⭐ Indica si el costo fue modificado
                    "total_modificado_manual": true    // ⭐ Indica si el total fue modificado
                }
            ],
            "fecha_guardado": "2025-01-15T10:30:00Z"
        }
        ```
        """
        try:
            with get_db_connection_context() as conn:
                repo_pedido = PedidoRepository(conn)
                
                # Obtener pedido por número
                pedido_data = repo_pedido.get_pedido_completo_por_numero(numero_pedido)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con número: {numero_pedido}"
                        }
                    )
                
                pedido_id = pedido_data["cabecera"]["pedido_id"]
                
                # Solo lectura: si hay redistribución confirmada, devolver la última guardada
                if str(solo_lectura or "").lower() in ("1", "true"):
                    repo_dist = DistribucionConfirmadaRepository(conn)
                    version_actual = repo_dist.get_version_actual(pedido_id)
                    if version_actual >= 1:
                        distribucion_data = repo_dist.get_distribucion_completa(pedido_id)
                        detalles_by_id = {d.get("pedido_detalle_id"): d for d in pedido_data.get("detalles", []) if d.get("pedido_detalle_id")}
                        ajustes_detalle_confirmada = []
                        for p in distribucion_data.get("productos", []):
                            pedido_detalle_id = p.get("pedido_detalle_id")
                            detalle = detalles_by_id.get(pedido_detalle_id, {})
                            codigo = detalle.get("codigo_interno") or ""
                            descripcion = detalle.get("descripcion_sap") or ""
                            if not codigo:
                                continue
                            dist_tiendas = [
                                DistribucionTiendaFrontend(
                                    tienda_codigo=d.get("tienda_codigo") or "",
                                    tienda_nombre=d.get("tienda_nombre") or "",
                                    cantidad=int(d.get("cantidad_asignada", 0)),
                                    es_bodega=bool(d.get("es_bodega", False)),
                                )
                                for d in p.get("distribuciones", [])
                            ]
                            if not dist_tiendas:
                                continue
                            primer_d = p.get("distribuciones", [{}])[0]
                            costo = None
                            if primer_d.get("costo_unitario_ajustado") is not None:
                                costo = float(primer_d["costo_unitario_ajustado"])
                            elif primer_d.get("costo_unitario_original") is not None:
                                costo = float(primer_d["costo_unitario_original"])
                            ajustes_detalle_confirmada.append(
                                AjusteDetalle(
                                    codigo_producto=codigo,
                                    descripcion=descripcion,
                                    cantidad_solicitada=int(p.get("cantidad_solicitada_total", 0)),
                                    cantidad_confirmada=int(p.get("cantidad_confirmada_total", 0)),
                                    cantidad_ajustada=int(p.get("cantidad_asignada_total", 0)),
                                    distribucion_tiendas=dist_tiendas,
                                    costo_original=costo,
                                    costo_ajustado=costo,
                                    cambio_precio=False,
                                    pedido_detalle_id=pedido_detalle_id,
                                    costo_modificado_manual=bool(detalle.get("costo_modificado_manual", False)),
                                    total_modificado_manual=bool(detalle.get("total_modificado_manual", False)),
                                )
                            )
                        return BorradorResponse(
                            ajustes_detalle=ajustes_detalle_confirmada,
                            fecha_guardado=datetime.now(),
                        )
                
                # Obtener cantidades confirmadas desde la respuesta del proveedor
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT TOP 1
                        rpd.pedido_detalle_id,
                        rpd.cantidad_solicitada_total,
                        rpd.cantidad_confirmada_total
                    FROM pedido_respuesta_proveedor_detalle rpd
                    INNER JOIN pedido_respuesta_proveedor rp ON rpd.respuesta_id = rp.respuesta_id
                    WHERE rp.pedido_id = ?
                    ORDER BY rp.version DESC, rp.fecha_respuesta DESC
                """, (pedido_id,))
                
                respuestas_map = {}
                for row in cursor.fetchall():
                    respuestas_map[str(row[0])] = {
                        "cantidad_solicitada_total": row[1],
                        "cantidad_confirmada_total": row[2]
                    }
                
                # Generar ajustes_detalle sincronizados con el pedido actualizado
                ajustes_detalle = []
                for detalle in pedido_data.get("detalles", []):
                    pedido_detalle_id = detalle.get("pedido_detalle_id")
                    codigo_producto = detalle.get("codigo_interno")
                    
                    if not codigo_producto:
                        continue
                    
                    # Obtener respuesta del proveedor para este producto
                    respuesta = respuestas_map.get(pedido_detalle_id, {})
                    cantidad_solicitada = respuesta.get("cantidad_solicitada_total", 0)
                    cantidad_confirmada = respuesta.get("cantidad_confirmada_total", 0)
                    
                    # Si no hay respuesta del proveedor, usar valores del pedido
                    if cantidad_solicitada == 0:
                        cantidad_solicitada = sum(t.get("cantidad", 0) for t in detalle.get("tiendas", []))
                    
                    if cantidad_confirmada == 0:
                        # Usar el campo "total" del detalle como cantidad confirmada (EL RAYO)
                        total_value = detalle.get("total")
                        if total_value is not None:
                            try:
                                cantidad_confirmada = int(float(total_value))
                            except (ValueError, TypeError):
                                cantidad_confirmada = cantidad_solicitada
                        else:
                            cantidad_confirmada = cantidad_solicitada
                    
                    # Obtener costos actualizados del pedido (EL RAYO)
                    costo_actual = detalle.get("costo_doc_sin_iva")
                    
                    # ⭐ NUEVO: Calcular distribución inicial proporcional basada en total confirmado
                    # Esto incluye bodegas y permite redistribución desde bodega
                    distribucion_tiendas = []
                    tiendas_del_detalle = detalle.get("tiendas", [])
                    
                    # Calcular cantidad total original (solicitada)
                    cantidad_total_original = sum(t.get("cantidad", 0) for t in tiendas_del_detalle)
                    
                    # Si hay cantidad confirmada, calcular distribución proporcional
                    if cantidad_confirmada > 0 and cantidad_total_original > 0:
                        # Calcular factor de proporción
                        factor_proporcion = cantidad_confirmada / cantidad_total_original
                        
                        # Redistribuir proporcionalmente, acumulando para redondeo
                        cantidad_asignada_total = 0
                        distribuciones_calculadas = []
                        
                        for i, tienda in enumerate(tiendas_del_detalle):
                            cantidad_original = tienda.get("cantidad", 0)
                            
                            # Calcular cantidad proporcional
                            if i == len(tiendas_del_detalle) - 1:
                                # Última tienda: asignar el resto para que sume exactamente
                                cantidad_calculada = cantidad_confirmada - cantidad_asignada_total
                            else:
                                # Calcular proporción y redondear
                                cantidad_calculada = round(cantidad_original * factor_proporcion)
                                cantidad_asignada_total += cantidad_calculada
                            
                            # Asegurar que no sea negativa
                            cantidad_calculada = max(0, cantidad_calculada)
                            
                            distribuciones_calculadas.append({
                                "tienda_codigo": tienda.get("codigo", ""),
                                "tienda_nombre": tienda.get("nombre", ""),
                                "cantidad": cantidad_calculada,
                                "es_bodega": tienda.get("es_bodega", False)  # ⭐ Incluir flag de bodega
                            })
                        
                        distribucion_tiendas = distribuciones_calculadas
                    else:
                        # Si no hay datos para calcular, inicializar en 0
                        for tienda in tiendas_del_detalle:
                            distribucion_tiendas.append({
                                "tienda_codigo": tienda.get("codigo", ""),
                                "tienda_nombre": tienda.get("nombre", ""),
                                "cantidad": 0,
                                "es_bodega": tienda.get("es_bodega", False)  # ⭐ Incluir flag de bodega
                            })
                    
                    # Obtener flags de modificación manual del detalle
                    costo_modificado = detalle.get("costo_modificado_manual", False)
                    total_modificado = detalle.get("total_modificado_manual", False)
                    
                    # Crear ajuste detalle sincronizado
                    ajuste = AjusteDetalle(
                        codigo_producto=codigo_producto,
                        descripcion=detalle.get("descripcion_sap", ""),
                        cantidad_solicitada=cantidad_solicitada,
                        cantidad_confirmada=cantidad_confirmada,
                        cantidad_ajustada=cantidad_confirmada,  # Inicialmente igual a confirmada
                        distribucion_tiendas=distribucion_tiendas,
                        costo_original=costo_actual,  # ⭐ Sincronizado con pedido actualizado
                        costo_ajustado=costo_actual,  # ⭐ Sincronizado con pedido actualizado
                        cambio_precio=False,
                        pedido_detalle_id=pedido_detalle_id,  # ⭐ Para identificar la fila en el frontend
                        costo_modificado_manual=costo_modificado,  # ⭐ Flag de modificación de costo
                        total_modificado_manual=total_modificado  # ⭐ Flag de modificación de total
                    )
                    
                    ajustes_detalle.append(ajuste)
                
                return BorradorResponse(
                    ajustes_detalle=ajustes_detalle,
                    fecha_guardado=datetime.now()
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al obtener datos iniciales de redistribución: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al obtener datos iniciales: {str(e)}"
                }
            )
    
    @app.post("/api/pedidos/{numero_pedido}/redistribucion/confirmar",
             response_model=ConfirmarRedistribucionResponseFrontend,
             tags=["Pedidos - Redistribución"])
    async def confirmar_redistribucion_frontend(
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: RedistribucionConfirmarRequest = Body(..., description="Datos de confirmación de redistribución"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Confirma una redistribución (compatible con frontend).
        
        **Funcionalidad:**
        - Confirma la redistribución usando la estructura AjusteDetalle del frontend
        - Convierte automáticamente códigos de tienda a UUIDs
        - Calcula resumen de confirmación
        - Actualiza estado del pedido a 'CONFIRMADO REDISTRIBUCION' cuando se confirma desde el frontend
        
        **Request:**
        ```json
        {
            "ajustes_detalle": [
                {
                    "codigo_producto": "R225.1012.BCO",
                    "descripcion": "Producto ejemplo",
                    "cantidad_solicitada": 100,
                    "cantidad_confirmada": 80,
                    "cantidad_ajustada": 75,
                    "distribucion_tiendas": [
                        {"tienda_codigo": "T001", "tienda_nombre": "Tienda 1", "cantidad": 50},
                        {"tienda_codigo": "T002", "tienda_nombre": "Tienda 2", "cantidad": 25}
                    ],
                    "costo_original": 25.50,
                    "costo_ajustado": 25.50,
                    "cambio_precio": false
                }
            ]
        }
        ```
        
        **Response:**
        ```json
        {
            "status": "success",
            "message": "Redistribución confirmada exitosamente",
            "pedido_id": "...",
            "numero_pedido": "P-12.48 - 12 - 2025",
            "redistribucion_id": "...",
            "fecha_confirmacion": "2025-01-15T10:30:00Z",
            "resumen": {
                "total_productos": 1,
                "total_cantidad_solicitada": 100,
                "total_cantidad_confirmada": 80,
                "total_cantidad_ajustada": 75,
                "total_costo_original": 2550.00,
                "total_costo_ajustado": 1912.50,
                "diferencia_cantidad": -5,
                "diferencia_costo": -637.50
            },
            "ajustes_aplicados": 1
        }
        ```
        """
        try:
            user_id = get_user_id(user)
            
            with get_db_connection_context() as conn:
                repo_pedido = PedidoRepository(conn)
                repo_dist = DistribucionConfirmadaRepository(conn)
                
                # Obtener pedido por número
                pedido_data = repo_pedido.get_pedido_completo_por_numero(numero_pedido)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con número: {numero_pedido}"
                        }
                    )
                
                pedido_id = pedido_data["cabecera"]["pedido_id"]
                
                # Convertir AjusteDetalle a estructura interna
                # Necesitamos mapear codigo_producto -> pedido_detalle_id y tienda_codigo -> tienda_id
                # IMPORTANTE: Sincronizar costos y totales con los valores actuales del pedido
                productos_redistribucion = []
                
                for ajuste in request_body.ajustes_detalle:
                    # Buscar pedido_detalle_id por codigo_producto
                    detalle_pedido = next(
                        (d for d in pedido_data["detalles"] 
                         if d.get("codigo_interno") == ajuste.codigo_producto),
                        None
                    )
                    
                    if not detalle_pedido:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={
                                "error": "producto_not_found",
                                "message": f"No se encontró el producto con código: {ajuste.codigo_producto}"
                            }
                        )
                    
                    # Sincronizar costos con los valores actuales del pedido
                    costo_actual = detalle_pedido.get("costo_doc_sin_iva")
                    if costo_actual is not None:
                        # Usar el costo actual del pedido, no el del request
                        ajuste.costo_original = costo_actual
                        ajuste.costo_ajustado = costo_actual
                    
                    # Sincronizar cantidad confirmada con el total actual del pedido (si existe)
                    total_actual = detalle_pedido.get("total")
                    if total_actual is not None:
                        try:
                            cantidad_confirmada_actual = int(float(total_actual))
                            ajuste.cantidad_confirmada = cantidad_confirmada_actual
                        except (ValueError, TypeError):
                            pass
                    
                    # Convertir distribuciones de tienda
                    distribuciones = []
                    for dist_tienda in ajuste.distribucion_tiendas:
                        # Buscar tienda_id por codigo
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT tienda_id FROM tienda WHERE codigo = ?
                        """, (dist_tienda.tienda_codigo,))
                        row = cursor.fetchone()
                        
                        if not row:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail={
                                    "error": "tienda_not_found",
                                    "message": f"No se encontró la tienda con código: {dist_tienda.tienda_codigo}"
                                }
                            )
                        
                        distribuciones.append({
                            "tienda_id": str(row[0]),
                            "cantidad_asignada": dist_tienda.cantidad
                        })
                    
                    productos_redistribucion.append({
                        "pedido_detalle_id": detalle_pedido["pedido_detalle_id"],
                        "distribuciones": distribuciones
                    })
                
                # Obtener respuestas del proveedor para validación
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        rpd.pedido_detalle_id,
                        rpd.cantidad_solicitada_total,
                        rpd.cantidad_confirmada_total
                    FROM pedido_respuesta_proveedor_detalle rpd
                    INNER JOIN pedido_respuesta_proveedor rp ON rpd.respuesta_id = rp.respuesta_id
                    WHERE rp.pedido_id = ?
                    ORDER BY rp.version DESC, rp.fecha_respuesta DESC
                """, (pedido_id,))
                
                respuestas_proveedor = {}
                for row in cursor.fetchall():
                    respuestas_proveedor[str(row[0])] = {
                        "cantidad_solicitada_total": row[1],
                        "cantidad_confirmada_total": row[2]
                    }
                
                # Validar redistribución
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
                
                # Crear redistribución
                resultado = repo_dist.crear_redistribucion(
                    pedido_id=pedido_id,
                    productos_redistribucion=productos_redistribucion,
                    usuario=user_id
                )
                
                # Confirmar redistribución
                resultado_confirmacion = repo_dist.confirmar_redistribucion(
                    pedido_id=pedido_id,
                    version=resultado["version"],
                    usuario=user_id
                )
                
                # Actualizar estado del pedido a "CONFIRMADO REDISTRIBUCION" (específico para confirmación desde frontend)
                repo_pedido.update_estado(pedido_id, ESTADO_PEDIDO_CONFIRMADO)
                
                # Calcular resumen
                total_productos = len(request_body.ajustes_detalle)
                total_cantidad_solicitada = sum(a.cantidad_solicitada for a in request_body.ajustes_detalle)
                total_cantidad_confirmada = sum(a.cantidad_confirmada for a in request_body.ajustes_detalle)
                total_cantidad_ajustada = sum(a.cantidad_ajustada for a in request_body.ajustes_detalle)
                diferencia_cantidad = total_cantidad_ajustada - total_cantidad_confirmada
                
                total_costo_original = sum(
                    (a.cantidad_solicitada * (a.costo_original or 0)) 
                    for a in request_body.ajustes_detalle
                ) or None
                
                total_costo_ajustado = sum(
                    (a.cantidad_ajustada * (a.costo_ajustado or 0)) 
                    for a in request_body.ajustes_detalle
                ) or None
                
                diferencia_costo = (
                    total_costo_ajustado - total_costo_original 
                    if total_costo_ajustado is not None and total_costo_original is not None 
                    else None
                )
                
                resumen = ResumenConfirmacion(
                    total_productos=total_productos,
                    total_cantidad_solicitada=total_cantidad_solicitada,
                    total_cantidad_confirmada=total_cantidad_confirmada,
                    total_cantidad_ajustada=total_cantidad_ajustada,
                    total_costo_original=total_costo_original,
                    total_costo_ajustado=total_costo_ajustado,
                    diferencia_cantidad=diferencia_cantidad,
                    diferencia_costo=diferencia_costo
                )
                
                logger.info(f"✅ Redistribución confirmada para pedido {numero_pedido} por usuario {user_id}")
                
                # NUEVO: Procesar pedido con SAP (similar a MIGRAR pero para pedidos)
                logger.info("=" * 70)
                logger.info("🔄 PROCESANDO: Consultando SAP y procesando productos del pedido...")
                logger.info("=" * 70)
                
                try:
                    from src.database.services.pedido_sap_service import procesar_pedido_con_sap
                    from src.database.services.homologacion_service import HomologacionService
                    from src.utils.email_notifier import send_homologacion_notification
                    
                    homologacion_service = HomologacionService()
                    
                    # Procesar pedido con SAP
                    resultado_sap = procesar_pedido_con_sap(
                        pedido_id=pedido_id,
                        usuario_id=user_id,
                        homologacion_service=homologacion_service,
                        continue_on_error=True
                    )
                    
                    logger.info(f"✅ Procesamiento SAP completado: {resultado_sap.get('productos_procesados', 0)} productos procesados")
                    
                    # Verificar productos no homologados y notificar
                    if resultado_sap.get("productos_no_homologados", 0) > 0:
                        logger.info("🔍 Verificando productos no homologados...")
                        
                        try:
                            from src.database.repositories.homologacion_repository import HomologacionRepository
                            
                            # Obtener TODOS los productos no homologados con estadísticas
                            todos_productos = homologacion_service.get_todos_productos_no_homologados()
                            productos_no_homologados = todos_productos.get("productos", [])
                            estadisticas = todos_productos.get("estadisticas", {})
                            
                            if productos_no_homologados and len(productos_no_homologados) > 0:
                                logger.info(f"⚠️ Se detectaron {len(productos_no_homologados)} productos no homologados")
                                
                                # Crear repository para filtrar productos ya notificados
                                repository = HomologacionRepository(conn)
                                
                                # Enviar notificación FILTRANDO productos ya notificados
                                email_enviado = send_homologacion_notification(
                                    productos_no_homologados=productos_no_homologados,
                                    estadisticas=estadisticas,
                                    fecha_ejecucion=datetime.now(),
                                    filtrar_ya_notificados=True,
                                    homologacion_repository=repository
                                )
                                
                                if email_enviado:
                                    logger.info("✅ Notificación de homologación enviada (solo productos nuevos)")
                                else:
                                    logger.info("⏭️ No se envió notificación (todos ya fueron notificados)")
                            else:
                                logger.info("✅ No hay productos no homologados nuevos para notificar")
                                
                        except Exception as homolog_error:
                            logger.warning(f"⚠️ Error al verificar homologaciones: {homolog_error}")
                            # No afectar la respuesta principal
                    
                except Exception as sap_error:
                    logger.error(f"❌ Error al procesar pedido con SAP: {sap_error}", exc_info=True)
                    # No afectar la confirmación de redistribución, solo loguear el error
                    logger.warning("⚠️ La redistribución fue confirmada pero el procesamiento SAP falló")
                
                logger.info("=" * 70)
                
                # Enviar notificación por correo electrónico a El Rayo cuando MABEL TRADING confirma la redistribución
                try:
                    from src.utils.email_notifier import send_mabel_redistribucion_confirmacion_notification
                    
                    email_enviado = send_mabel_redistribucion_confirmacion_notification(
                        pedido_id=pedido_id,
                        numero_pedido=numero_pedido,
                        usuario_mabel=user_id,
                        version_confirmada=resultado.get("version"),
                        total_productos=total_productos,
                        total_cantidad_ajustada=resumen.total_cantidad_ajustada if resumen else 0
                    )
                    if email_enviado:
                        logger.info(f"📧 Email de confirmación de redistribución enviado a El Rayo (Pedido: {numero_pedido})")
                    else:
                        logger.warning(f"⚠️ No se pudo enviar email de confirmación de redistribución (no crítico)")
                except Exception as e:
                    # NO fallar el proceso si el email falla
                    logger.warning(f"⚠️ Error al enviar email de confirmación de redistribución (no crítico): {e}")
                
                return ConfirmarRedistribucionResponseFrontend(
                    pedido_id=pedido_id,
                    numero_pedido=numero_pedido,
                    redistribucion_id=str(resultado["version"]),  # Usar version como ID
                    fecha_confirmacion=datetime.now(),
                    resumen=resumen,
                    ajustes_aplicados=total_productos,
                    message="Redistribución confirmada exitosamente"
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
    
    @app.post("/api/pedidos/{numero_pedido}/redistribucion/ajustar-bodegas",
             response_model=BorradorResponse,
             tags=["Pedidos - Redistribución"])
    async def ajustar_bodegas_automaticamente(
        numero_pedido: str = Path(..., description="Número del pedido"),
        request_body: RedistribucionConfirmarRequest = Body(..., description="Datos de redistribución para ajustar"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_permission('mabel.view'))
    ):
        """
        Retorna los datos de redistribución sin ajustar automáticamente las bodegas.
        
        **Funcionalidad:**
        - Retorna los datos tal como se envían, sin modificar las bodegas
        - Las bodegas mantienen sus valores originales cuando se redistribuye a tiendas
        - No se resta automáticamente de las bodegas cuando se aumenta la cantidad en tiendas
        
        **Nota:**
        Esta funcionalidad fue modificada para NO restar automáticamente de las bodegas
        cuando se redistribuye a las tiendas. Las bodegas permanecen con sus valores originales.
        """
        try:
            with get_db_connection_context() as conn:
                repo_pedido = PedidoRepository(conn)
                
                # Obtener pedido por número
                pedido_data = repo_pedido.get_pedido_completo_por_numero(numero_pedido)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "pedido_not_found",
                            "message": f"No se encontró el pedido con número: {numero_pedido}"
                        }
                    )
                
                # Retornar los datos tal como se envían, sin ajustar bodegas
                # Las bodegas mantienen sus valores originales
                ajustes_ajustados = []
                
                for ajuste in request_body.ajustes_detalle:
                    # Calcular cantidad_ajustada como la suma de todas las distribuciones (tiendas + bodegas)
                    suma_total = sum(d.cantidad for d in ajuste.distribucion_tiendas)
                    
                    # Crear ajuste sin modificar las bodegas
                    ajuste_ajustado = AjusteDetalle(
                        codigo_producto=ajuste.codigo_producto,
                        descripcion=ajuste.descripcion,
                        cantidad_solicitada=ajuste.cantidad_solicitada,
                        cantidad_confirmada=ajuste.cantidad_confirmada,
                        cantidad_ajustada=suma_total,
                        distribucion_tiendas=ajuste.distribucion_tiendas,  # Mantener distribución original sin cambios
                        costo_original=ajuste.costo_original,
                        costo_ajustado=ajuste.costo_ajustado,
                        cambio_precio=ajuste.cambio_precio,
                        pedido_detalle_id=ajuste.pedido_detalle_id,
                        costo_modificado_manual=ajuste.costo_modificado_manual,
                        total_modificado_manual=ajuste.total_modificado_manual
                    )
                    
                    ajustes_ajustados.append(ajuste_ajustado)
                
                return BorradorResponse(
                    ajustes_detalle=ajustes_ajustados,
                    fecha_guardado=datetime.now()
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al procesar redistribución: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error interno al procesar redistribución: {str(e)}"
                }
            )
    
    @app.get("/api/pedidos/{pedido_id}/distribucion/descargar-excel", tags=["Pedidos - Redistribución"])
    async def descargar_distribucion_excel(
        pedido_id: str = Path(..., description="UUID del pedido"),
        version: Optional[int] = Query(None, ge=1, description="Versión específica (si no se especifica, obtiene la última)"),
        user: Dict = Depends(verify_jwt_token),
        _: None = Depends(require_any_permission(['odcsap.view', 'mabel.view']))
    ):
        """
        Descargar distribución confirmada del pedido en formato Excel (.xlsx).
        
        **Uso:**
        - Interfaz: Pantalla de Redistribución (`/pedidos/{numero_pedido}/redistribucion`)
        - Botón: "Descargar Distribución Excel"
        
        **Contenido del Excel:**
        - Hoja 1: Información del pedido (cabecera)
        - Hoja 2: Resumen de productos (cantidades solicitadas, confirmadas, asignadas)
        - Hoja 3: Distribución detallada por tienda con costos
        
        **Query Parameters:**
        - `version` (int, opcional): Versión específica a descargar. Si no se especifica, descarga la última versión.
        
        **Respuestas:**
        - **200**: Archivo Excel descargado correctamente
        - **404**: Pedido no encontrado o no tiene distribución confirmada
        - **500**: Error interno
        """
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            import re
            
            with get_db_connection_context() as conn:
                repo_dist = DistribucionConfirmadaRepository(conn)
                repo_pedido = PedidoRepository(conn)
                
                # Obtener distribución confirmada
                distribucion_data = repo_dist.get_distribucion_completa(pedido_id, version)
                
                if not distribucion_data or not distribucion_data.get("productos"):
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "not_found",
                            "message": "No se encontró distribución confirmada para este pedido"
                        }
                    )
                
                # Obtener datos del pedido
                pedido_data = repo_pedido.get_pedido_completo(pedido_id)
                
                if not pedido_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={"error": "not_found", "message": "Pedido no encontrado"}
                    )
                
                cabecera = pedido_data.get("cabecera", {})
                
                # Crear libro de Excel
                wb = Workbook()
                wb.remove(wb.active)  # Eliminar la hoja por defecto
                
                # Estilos
                header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                header_font = Font(bold=True, color="FFFFFF", size=12)
                title_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
                title_font = Font(bold=True, size=14)
                border = Border(
                    left=Side(style='thin'),
                    right=Side(style='thin'),
                    top=Side(style='thin'),
                    bottom=Side(style='thin')
                )
                
                # === HOJA 1: INFORMACIÓN DEL PEDIDO ===
                ws_cabecera = wb.create_sheet("Información del Pedido")
                
                # Título
                ws_cabecera['A1'] = "INFORMACIÓN DEL PEDIDO - DISTRIBUCIÓN CONFIRMADA"
                ws_cabecera['A1'].font = title_font
                ws_cabecera['A1'].fill = title_fill
                ws_cabecera.merge_cells('A1:B1')
                
                # Datos de cabecera
                row = 3
                info_fields = [
                    ("Número de Pedido", cabecera.get("numero_pedido", "N/A")),
                    ("Pedido ID", pedido_id),
                    ("Versión Redistribución", distribucion_data.get("version_actual", "N/A")),
                    ("Estado", cabecera.get("estado_nombre", "N/A")),
                    ("Fecha Pedido", cabecera.get("fecha_pedido", "N/A")),
                    ("Fecha Entrega", cabecera.get("fecha_entrega", "N/A")),
                    ("Proveedor", cabecera.get("proveedor_nombre", "N/A")),
                    ("Comprador", cabecera.get("comprador_nombre", "N/A")),
                    ("Forma de Pago", cabecera.get("forma_pago", "N/A")),
                    ("ODC", cabecera.get("odc", "N/A")),
                    ("Creado Por", cabecera.get("creado_por", "N/A")),
                ]
                
                for field, value in info_fields:
                    ws_cabecera[f'A{row}'] = field
                    ws_cabecera[f'A{row}'].font = Font(bold=True)
                    ws_cabecera[f'B{row}'] = value
                    row += 1
                
                # Ajustar anchos de columna
                ws_cabecera.column_dimensions['A'].width = 25
                ws_cabecera.column_dimensions['B'].width = 50
                
                # === HOJA 2: RESUMEN DE PRODUCTOS ===
                ws_resumen = wb.create_sheet("Resumen de Productos")
                
                # Título
                ws_resumen['A1'] = "RESUMEN DE PRODUCTOS - CANTIDADES"
                ws_resumen['A1'].font = title_font
                ws_resumen['A1'].fill = title_fill
                ws_resumen.merge_cells('A1:F1')
                
                # Encabezados
                headers_resumen = [
                    "Código Interno",
                    "Descripción",
                    "Cantidad Solicitada",
                    "Cantidad Confirmada",
                    "Cantidad Asignada",
                    "Diferencia"
                ]
                
                for col_num, header in enumerate(headers_resumen, 1):
                    cell = ws_resumen.cell(row=3, column=col_num)
                    cell.value = header
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    cell.border = border
                
                row = 4
                total_solicitada = 0
                total_confirmada = 0
                total_asignada = 0
                
                # Enriquecer productos con información del pedido
                productos_enriquecidos = []
                for producto_dist in distribucion_data["productos"]:
                    pedido_detalle_id = producto_dist["pedido_detalle_id"]
                    
                    # Buscar detalle en el pedido
                    detalle_pedido = next(
                        (d for d in pedido_data["detalles"] if d["pedido_detalle_id"] == pedido_detalle_id),
                        None
                    )
                    
                    if detalle_pedido:
                        productos_enriquecidos.append({
                            **producto_dist,
                            "codigo_interno": detalle_pedido.get("codigo_interno"),
                            "descripcion_sap": detalle_pedido.get("descripcion_sap"),
                        })
                    else:
                        productos_enriquecidos.append(producto_dist)
                
                for producto in productos_enriquecidos:
                    codigo_interno = producto.get("codigo_interno", "")
                    descripcion = producto.get("descripcion_sap", "")
                    cantidad_solicitada = producto.get("cantidad_solicitada_total", 0)
                    cantidad_confirmada = producto.get("cantidad_confirmada_total", 0)
                    cantidad_asignada = producto.get("cantidad_asignada_total", 0)
                    diferencia = cantidad_confirmada - cantidad_asignada
                    
                    total_solicitada += cantidad_solicitada
                    total_confirmada += cantidad_confirmada
                    total_asignada += cantidad_asignada
                    
                    ws_resumen.cell(row=row, column=1, value=codigo_interno)
                    ws_resumen.cell(row=row, column=2, value=descripcion)
                    ws_resumen.cell(row=row, column=3, value=cantidad_solicitada)
                    ws_resumen.cell(row=row, column=4, value=cantidad_confirmada)
                    ws_resumen.cell(row=row, column=5, value=cantidad_asignada)
                    ws_resumen.cell(row=row, column=6, value=diferencia)
                    
                    row += 1
                
                # Totales
                row += 1
                ws_resumen.cell(row=row, column=1, value="TOTALES").font = Font(bold=True)
                ws_resumen.cell(row=row, column=3, value=total_solicitada).font = Font(bold=True)
                ws_resumen.cell(row=row, column=4, value=total_confirmada).font = Font(bold=True)
                ws_resumen.cell(row=row, column=5, value=total_asignada).font = Font(bold=True)
                ws_resumen.cell(row=row, column=6, value=total_confirmada - total_asignada).font = Font(bold=True)
                
                # Ajustar anchos de columna
                ws_resumen.column_dimensions['A'].width = 20
                ws_resumen.column_dimensions['B'].width = 45
                ws_resumen.column_dimensions['C'].width = 18
                ws_resumen.column_dimensions['D'].width = 18
                ws_resumen.column_dimensions['E'].width = 18
                ws_resumen.column_dimensions['F'].width = 15
                
                # === HOJA 3: DISTRIBUCIÓN DETALLADA POR TIENDA ===
                ws_detalle = wb.create_sheet("Distribución por Tienda")
                
                # Título
                ws_detalle['A1'] = "DISTRIBUCIÓN DETALLADA POR TIENDA"
                ws_detalle['A1'].font = title_font
                ws_detalle['A1'].fill = title_fill
                ws_detalle.merge_cells('A1:G1')
                
                # Encabezados
                headers_detalle = [
                    "Código Interno",
                    "Descripción",
                    "Código Tienda",
                    "Nombre Tienda",
                    "Cantidad Asignada",
                    "Costo Unitario",
                    "Observaciones"
                ]
                
                for col_num, header in enumerate(headers_detalle, 1):
                    cell = ws_detalle.cell(row=3, column=col_num)
                    cell.value = header
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    cell.border = border
                
                row = 4
                
                # Escribir distribuciones detalladas
                for producto in productos_enriquecidos:
                    codigo_interno = producto.get("codigo_interno", "")
                    descripcion = producto.get("descripcion_sap", "")
                    distribuciones = producto.get("distribuciones", [])
                    
                    if distribuciones:
                        for dist in distribuciones:
                            ws_detalle.cell(row=row, column=1, value=codigo_interno)
                            ws_detalle.cell(row=row, column=2, value=descripcion)
                            ws_detalle.cell(row=row, column=3, value=dist.get("tienda_codigo", ""))
                            ws_detalle.cell(row=row, column=4, value=dist.get("tienda_nombre", ""))
                            ws_detalle.cell(row=row, column=5, value=dist.get("cantidad_asignada", 0))
                            ws_detalle.cell(row=row, column=6, value=float(dist.get("costo_unitario_ajustado", 0.0)))
                            ws_detalle.cell(row=row, column=7, value=dist.get("observaciones", ""))
                            
                            # Formato numérico
                            ws_detalle.cell(row=row, column=6).number_format = '#,##0.00'
                            
                            row += 1
                    else:
                        # Sin distribución
                        ws_detalle.cell(row=row, column=1, value=codigo_interno)
                        ws_detalle.cell(row=row, column=2, value=descripcion)
                        ws_detalle.cell(row=row, column=3, value="Sin distribución")
                        row += 1
                
                # Ajustar anchos de columna
                ws_detalle.column_dimensions['A'].width = 20
                ws_detalle.column_dimensions['B'].width = 45
                ws_detalle.column_dimensions['C'].width = 15
                ws_detalle.column_dimensions['D'].width = 30
                ws_detalle.column_dimensions['E'].width = 18
                ws_detalle.column_dimensions['F'].width = 15
                ws_detalle.column_dimensions['G'].width = 30
                
                # Agregar información de descarga
                row = ws_cabecera.max_row + 2
                ws_cabecera[f'A{row}'] = "Descargado por:"
                ws_cabecera[f'A{row}'].font = Font(bold=True)
                ws_cabecera[f'B{row}'] = user.get("username", "Desconocido")
                
                row += 1
                ws_cabecera[f'A{row}'] = "Fecha de descarga:"
                ws_cabecera[f'A{row}'].font = Font(bold=True)
                ws_cabecera[f'B{row}'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Guardar el libro de Excel en memoria
                from io import BytesIO
                excel_buffer = BytesIO()
                wb.save(excel_buffer)
                excel_buffer.seek(0)
                
                # Nombre del archivo
                numero_pedido = cabecera.get("numero_pedido", pedido_id)
                # Limpiar nombre para evitar caracteres inválidos en nombre de archivo
                numero_pedido_safe = re.sub(r'[^\w\-_\. ]', '_', numero_pedido)
                version_str = f"_v{distribucion_data.get('version_actual', 1)}"
                filename = f"distribucion_{numero_pedido_safe}{version_str}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                
                logger.info(f"✅ Excel de distribución generado para pedido {pedido_id} ({numero_pedido}) por usuario {user.get('username', 'UNKNOWN')}")
                
                # Retornar archivo Excel
                return StreamingResponse(
                    excel_buffer,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}",
                        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    }
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error al generar Excel de distribución para pedido {pedido_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "internal_error",
                    "message": f"Error al generar Excel de distribución: {str(e)}"
                }
            )
    