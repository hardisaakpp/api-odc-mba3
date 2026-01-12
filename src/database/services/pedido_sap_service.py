"""
Servicio para procesar pedidos con SAP.
Similar a factura_service pero para pedidos (sin vínculo con MBA3).
Se ejecuta cuando MT confirma la redistribución.
"""

import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal

from ..connection import get_db_connection_context
from ..repositories.pedido_repository import PedidoRepository
from ..repositories.pedido_sap_procesamiento_repository import PedidoSAPProcesamientoRepository
from ..repositories.distribucion_confirmada_repository import DistribucionConfirmadaRepository
from ..services.sap_service import SAPService
from ..services.homologacion_service import HomologacionService

logger = logging.getLogger(__name__)


def procesar_pedido_con_sap(
    pedido_id: str,
    usuario_id: Optional[str] = None,
    homologacion_service: Optional[HomologacionService] = None,
    continue_on_error: bool = True
) -> Dict[str, Any]:
    """
    Procesa un pedido consultando SAP para cada producto.
    
    Similar a save_mba3_factura pero para pedidos:
    1. Obtiene productos del pedido desde pedido_detalle
    2. Para cada producto, suma cantidades de distribucion_confirmada (todas las tiendas)
    3. Consulta información SAP (ItemCode, Pack, conversiones)
    4. Calcula cantidades y precios en unidades SAP
    5. Detecta productos no homologados
    6. Guarda en pedido_sap_procesamiento
    
    Args:
        pedido_id: UUID del pedido
        usuario_id: User ID que procesa (opcional)
        homologacion_service: Servicio de homologación para detectar productos no homologados
        continue_on_error: Si True, continúa procesando aunque falle un producto
        
    Returns:
        Dict con estadísticas de la operación:
        {
            "status": "success" | "partial" | "error",
            "total_productos": 5,
            "productos_procesados": 4,
            "productos_error": 1,
            "productos_no_homologados": 2,
            "errors": []
        }
    """
    stats = {
        "status": "success",
        "total_productos": 0,
        "productos_procesados": 0,
        "productos_error": 0,
        "productos_no_homologados": 0,
        "errors": []
    }
    
    try:
        # Usar context manager para garantizar cierre de conexión
        with get_db_connection_context() as conn:
            pedido_repo = PedidoRepository(conn)
            sap_proc_repo = PedidoSAPProcesamientoRepository(conn)
            dist_repo = DistribucionConfirmadaRepository(conn)
            sap_service = SAPService()
            
            # Inicializar servicio de homologación si no se proporciona
            if homologacion_service is None:
                homologacion_service = HomologacionService()
            
            # Obtener pedido completo
            pedido_data = pedido_repo.get_pedido_completo(pedido_id)
            if not pedido_data:
                raise ValueError(f"No se encontró el pedido con ID: {pedido_id}")
            
            detalles = pedido_data.get("detalles", [])
            stats["total_productos"] = len(detalles)
            
            logger.info(f"📦 Procesando {stats['total_productos']} producto(s) del pedido {pedido_id}...")
            
            # Obtener distribución confirmada (última versión)
            version_actual = dist_repo.get_version_actual(pedido_id)
            if version_actual == 0:
                logger.warning(f"⚠️ No hay distribución confirmada para el pedido {pedido_id}")
                return {
                    "status": "error",
                    "message": "No hay distribución confirmada para procesar",
                    **stats
                }
            
            distribucion_data = dist_repo.get_distribucion_completa(pedido_id, version_actual)
            productos_distribucion = {p["pedido_detalle_id"]: p for p in distribucion_data.get("productos", [])}
            
            # Procesar cada producto
            for idx, detalle in enumerate(detalles, 1):
                try:
                    pedido_detalle_id = detalle.get("pedido_detalle_id")
                    codigo_interno = detalle.get("codigo_interno")
                    descripcion_producto = detalle.get("descripcion_sap")  # Descripción del producto
                    
                    if not codigo_interno:
                        logger.warning(f"⚠️ Producto {idx} sin código interno, omitiendo...")
                        continue
                    
                    logger.info(f"[{idx}/{stats['total_productos']}] Procesando producto: {codigo_interno}")
                    
                    # Obtener cantidad total desde distribución confirmada
                    producto_dist = productos_distribucion.get(pedido_detalle_id, {})
                    cantidad_total = producto_dist.get("cantidad_asignada_total", 0)
                    
                    if cantidad_total == 0:
                        logger.warning(f"   ⚠️ Producto {codigo_interno} tiene cantidad 0, omitiendo...")
                        continue
                    
                    # Obtener precio desde pedido_detalle
                    precio_unitario_original = detalle.get("costo_doc_sin_iva")
                    if precio_unitario_original is None:
                        logger.warning(f"   ⚠️ Producto {codigo_interno} sin precio, usando 0")
                        precio_unitario_original = 0.0
                    
                    # Calcular total original
                    total_linea_original = float(cantidad_total) * float(precio_unitario_original)
                    
                    # Consultar información SAP
                    sap_info = None
                    producto_homologado = True
                    tipo_problema = None
                    item_code_sap_encontrado = None
                    mensaje_error = None
                    
                    try:
                        sap_info = sap_service.get_or_fetch_producto_info(codigo_interno)
                        
                        if sap_info:
                            # Verificar si es un error
                            if sap_info.get("_error"):
                                producto_homologado = False
                                tipo_problema = sap_info.get("_error_type", "no_existe")
                                item_code_sap_encontrado = sap_info.get("_item_code_sap")
                                
                                # Detectar como no homologado
                                if homologacion_service:
                                    info_adicional = {}
                                    if item_code_sap_encontrado:
                                        info_adicional["item_code_sap"] = item_code_sap_encontrado
                                    
                                    homologacion_service.detectar_producto_no_homologado(
                                        codigo_interno,
                                        tipo_problema=tipo_problema,
                                        info_adicional=info_adicional if info_adicional else None
                                    )
                                
                                if tipo_problema == "mismatch":
                                    mensaje_error = f"SKU MBA3='{codigo_interno}' no coincide con ItemCode SAP='{item_code_sap_encontrado}'"
                                    logger.warning(f"   ⚠️ MISMATCH: {mensaje_error}")
                                elif tipo_problema == "no_existe":
                                    mensaje_error = f"Producto no encontrado en SAP: {codigo_interno}"
                                    logger.warning(f"   ⚠️ {mensaje_error}")
                                else:
                                    mensaje_error = f"Error al consultar SAP para {codigo_interno}"
                                    logger.warning(f"   ⚠️ {mensaje_error}")
                                
                                # Establecer sap_info a None para que no se usen conversiones
                                sap_info = None
                            else:
                                # Producto encontrado y válido
                                logger.debug(
                                    f"   ✅ SAP info: Pack={sap_info.get('pack_sap')}, "
                                    f"Unidad={sap_info.get('unidad_conversion')}"
                                )
                        else:
                            # Producto no encontrado en SAP
                            producto_homologado = False
                            tipo_problema = "no_existe"
                            mensaje_error = f"Producto no encontrado en SAP: {codigo_interno}"
                            
                            if homologacion_service:
                                homologacion_service.detectar_producto_no_homologado(
                                    codigo_interno,
                                    tipo_problema="no_existe"
                                )
                            
                            logger.warning(f"   ⚠️ {mensaje_error}")
                            
                    except Exception as sap_error:
                        # Error al consultar SAP
                        producto_homologado = False
                        tipo_problema = "error"
                        mensaje_error = f"Error al consultar SAP: {str(sap_error)}"
                        
                        if homologacion_service:
                            homologacion_service.detectar_producto_no_homologado(
                                codigo_interno,
                                tipo_problema="error",
                                info_adicional={"error_message": str(sap_error)}
                            )
                        
                        logger.warning(f"   ⚠️ {mensaje_error}")
                    
                    # Calcular conversiones si hay información SAP válida
                    cantidad_sap = None
                    precio_unitario_sap = None
                    total_linea_sap = None
                    item_code_sap = None
                    pack_sap = None
                    unidad_conversion = None
                    unidad_sap = None
                    
                    if sap_info and not sap_info.get("_error"):
                        # Información SAP válida
                        item_code_sap = sap_info.get("item_code") or codigo_interno
                        pack_sap = sap_info.get("pack_sap")
                        unidad_conversion = sap_info.get("unidad_conversion")
                        unidad_sap = sap_info.get("pack_sap")
                        
                        # Convertir cantidad (igual que despacho_detalle: docenas × unidad_conversion = packs)
                        if unidad_conversion and unidad_conversion > 0:
                            cantidad_sap = float(cantidad_total) * float(unidad_conversion)
                            logger.info(
                                f"   ✅ Conversión: {cantidad_total} docenas × {unidad_conversion} = {cantidad_sap:.2f} packs "
                                f"({unidad_sap})"
                            )
                        else:
                            cantidad_sap = float(cantidad_total)
                            logger.warning(f"   ⚠️ Sin conversión disponible, usando cantidad original")
                        
                        # Convertir precio (igual que despacho_detalle: precio_unitario_original / unidad_conversion)
                        if unidad_conversion and unidad_conversion > 0:
                            precio_unitario_sap = float(precio_unitario_original) / float(unidad_conversion)
                        else:
                            precio_unitario_sap = float(precio_unitario_original)
                        
                        # Calcular total en unidades SAP
                        total_linea_sap = cantidad_sap * precio_unitario_sap
                    else:
                        # Sin información SAP, usar valores originales
                        cantidad_sap = float(cantidad_total)
                        precio_unitario_sap = float(precio_unitario_original)
                        # Calcular total_linea_sap siempre (no copiar de total_linea_original)
                        total_linea_sap = cantidad_sap * precio_unitario_sap
                    
                    # Preparar datos para guardar
                    datos_procesamiento = {
                        "pedido_id": pedido_id,
                        "pedido_detalle_id": pedido_detalle_id,
                        "descripcion_producto": descripcion_producto,  # Descripción del producto
                        "item_code_sap": item_code_sap,
                        "pack_sap": pack_sap,
                        "unidad_conversion": unidad_conversion,
                        "unidad_sap": unidad_sap,
                        "cantidad_original": float(cantidad_total),
                        "cantidad_sap": cantidad_sap,
                        "precio_unitario_original": float(precio_unitario_original),
                        "precio_unitario_sap": precio_unitario_sap,
                        "total_linea_original": total_linea_original,
                        "total_linea_sap": total_linea_sap,
                        "producto_homologado": producto_homologado,
                        "tipo_problema": tipo_problema,
                        "item_code_sap_encontrado": item_code_sap_encontrado,
                        "mensaje_error": mensaje_error,
                        "procesado_por": usuario_id
                    }
                    
                    # Guardar procesamiento (UPSERT)
                    sap_proc_repo.upsert_procesamiento(datos_procesamiento)
                    
                    stats["productos_procesados"] += 1
                    if not producto_homologado:
                        stats["productos_no_homologados"] += 1
                    
                    logger.info(
                        f"   ✅ Producto procesado: {codigo_interno} "
                        f"(homologado: {producto_homologado})"
                    )
                    
                except Exception as e:
                    error_msg = f"Error al procesar producto {idx} ({detalle.get('codigo_interno', 'sin_codigo')}): {str(e)}"
                    logger.error(f"❌ {error_msg}")
                    stats["productos_error"] += 1
                    stats["errors"].append(error_msg)
                    
                    if not continue_on_error:
                        raise
            
            # Determinar estado final
            if stats["productos_error"] == 0:
                stats["status"] = "success"
            elif stats["productos_procesados"] > 0:
                stats["status"] = "partial"
            else:
                stats["status"] = "error"
            
            logger.info("=" * 70)
            logger.info(f"✅ Proceso completado: {stats['productos_procesados']} procesados, "
                       f"{stats['productos_error']} errores, "
                       f"{stats['productos_no_homologados']} no homologados "
                       f"de {stats['total_productos']} totales")
            logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"❌ Error crítico al procesar pedido con SAP: {e}", exc_info=True)
        stats["status"] = "error"
        stats["errors"].append(f"Error crítico: {str(e)}")
        return {
            "status": "error",
            "message": f"Error al procesar pedido con SAP: {str(e)}",
            **stats
        }
    
    return stats
