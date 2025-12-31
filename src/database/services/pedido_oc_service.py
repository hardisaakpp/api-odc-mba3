"""
Servicio para crear órdenes de compra desde pedidos confirmados.
FASE 5: Generación de ODC desde cantidades confirmadas del proveedor.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..connection import get_db_connection_context
from ..repositories.pedido_repository import PedidoRepository
from ..repositories.pedido_respuesta_repository import PedidoRespuestaRepository
from ..repositories.orden_compra_repository import OrdenCompraRepository
from ..repositories.producto_sap_repository import ProductoSAPRepository
from .sap_service import SAPService

logger = logging.getLogger(__name__)


class PedidoOCService:
    """Servicio para crear órdenes de compra desde pedidos confirmados."""
    
    def __init__(self):
        """Inicializa el servicio."""
        self.sap_service = SAPService()
    
    def obtener_cantidades_confirmadas(
        self,
        conn,
        pedido_id: str
    ) -> List[Dict[str, Any]]:
        """
        Obtiene cantidades confirmadas del proveedor para un pedido.
        
        Usa el query de QUERY_CANTIDADES_CONFIRMADAS.md.
        Solo incluye productos con cantidad_confirmada_total > 0.
        Solo incluye respuestas en estado APROBADA.
        
        Args:
            conn: Conexión a BD
            pedido_id: UUID del pedido
            
        Returns:
            Lista de productos con cantidades confirmadas
        """
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT 
                    r.respuesta_id,
                    pd.pedido_detalle_id,
                    pd.codigo_interno,
                    pd.descripcion_sap,
                    pd.pack AS pack_sap,
                    rd.cantidad_confirmada_total,
                    COALESCE(rd.costo_doc_sin_iva_ajustado, rd.costo_doc_sin_iva_original) AS costo_unitario,
                    COALESCE(rd.descuento_1_ajustado, rd.descuento_1_original) AS descuento,
                    p.proveedor_nombre,
                    p.fecha_pedido
                FROM pedido_respuesta_proveedor r
                INNER JOIN pedido_respuesta_proveedor_detalle rd ON r.respuesta_id = rd.respuesta_id
                INNER JOIN pedido_detalle pd ON rd.pedido_detalle_id = pd.pedido_detalle_id
                INNER JOIN pedido p ON r.pedido_id = p.pedido_id
                WHERE 
                    r.pedido_id = ?
                    AND r.estado = 'APROBADA'
                    AND rd.cantidad_confirmada_total > 0
                ORDER BY pd.codigo_interno
            """, (pedido_id,))
            
            resultados = []
            for row in cursor.fetchall():
                resultados.append({
                    "respuesta_id": str(row[0]),
                    "pedido_detalle_id": str(row[1]),
                    "codigo_interno": row[2],
                    "descripcion_sap": row[3],
                    "pack_sap": row[4],
                    "cantidad_confirmada_total": int(row[5]),
                    "costo_unitario": float(row[6]) if row[6] else None,
                    "descuento": float(row[7]) if row[7] else None,
                    "proveedor_nombre": row[8],
                    "fecha_pedido": row[9].isoformat() if row[9] else None,
                })
            
            return resultados
        finally:
            cursor.close()
    
    def obtener_sku_sap_y_conversion(
        self,
        conn,
        codigo_interno: str,
        pack_sap: Optional[str]
    ) -> Dict[str, Any]:
        """
        Obtiene SKU SAP y unidad de conversión para un producto.
        
        Intenta obtener desde:
        1. producto_sap_cache (cache de SAP)
        2. pack_conversion (si solo tenemos pack_sap)
        
        Args:
            conn: Conexión a BD
            codigo_interno: SKU MBA3
            pack_sap: Pack SAP (X1, X2, X3, etc.)
            
        Returns:
            Dict con sku_sap, unidad_conversion, unidad_sap
        """
        # Intentar obtener desde SAPService (usa cache)
        sap_info = self.sap_service.get_or_fetch_producto_info(codigo_interno)
        
        if sap_info and not sap_info.get("_error"):
            return {
                "sku_sap": sap_info.get("item_code") or codigo_interno,
                "unidad_conversion": sap_info.get("unidad_conversion"),
                "unidad_sap": sap_info.get("pack_sap") or pack_sap,
                "pack_sap": sap_info.get("pack_sap") or pack_sap
            }
        
        # Fallback: obtener unidad_conversion desde pack_conversion
        producto_repo = ProductoSAPRepository(conn)
        unidad_conversion = None
        
        if pack_sap:
            unidad_conversion = producto_repo.get_unidad_conversion_by_pack(pack_sap)
        
        return {
            "sku_sap": codigo_interno,  # Usar codigo_interno como fallback
            "unidad_conversion": unidad_conversion,
            "unidad_sap": pack_sap,
            "pack_sap": pack_sap
        }
    
    def crear_oc_desde_pedido_confirmado(
        self,
        pedido_id: str,
        usuario_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Crea una orden de compra desde un pedido confirmado.
        
        Flujo:
        1. Valida que el pedido tenga respuesta aprobada
        2. Obtiene cantidades confirmadas (cantidad_confirmada_total > 0)
        3. Convierte unidades (docenas → packs SAP)
        4. Obtiene SKU SAP desde homologación/cache
        5. Crea OC con pedido_id asociado
        6. Estado inicial: PENDIENTE
        
        Args:
            pedido_id: UUID del pedido
            usuario_id: User ID del usuario que crea la OC
            
        Returns:
            Dict con resultado de la creación
        """
        with get_db_connection_context() as conn:
            pedido_repo = PedidoRepository(conn)
            respuesta_repo = PedidoRespuestaRepository(conn)
            oc_repo = OrdenCompraRepository(conn)
            
            # 1. Validar que el pedido existe
            pedido = pedido_repo.get_pedido_completo(pedido_id)
            if not pedido:
                raise ValueError(f"Pedido no encontrado: {pedido_id}")
            
            # 2. Validar que tiene respuesta aprobada
            respuesta = respuesta_repo.obtener_respuesta_activa(pedido_id)
            if not respuesta:
                raise ValueError(f"El pedido {pedido_id} no tiene respuesta del proveedor")
            
            if respuesta["cabecera"]["estado"] != "APROBADA":
                raise ValueError(
                    f"La respuesta del proveedor no está aprobada. "
                    f"Estado actual: {respuesta['cabecera']['estado']}"
                )
            
            # 3. Obtener cantidades confirmadas
            cantidades_confirmadas = self.obtener_cantidades_confirmadas(conn, pedido_id)
            
            if not cantidades_confirmadas:
                raise ValueError(
                    f"No hay productos con cantidad confirmada > 0 para el pedido {pedido_id}"
                )
            
            # 4. Preparar detalles de OC
            oc_detalles = []
            errores = []
            warnings = []
            
            for item in cantidades_confirmadas:
                codigo_interno = item["codigo_interno"]
                cantidad_confirmada = item["cantidad_confirmada_total"]
                pack_sap = item["pack_sap"]
                
                # Obtener SKU SAP y conversión
                try:
                    sap_info = self.obtener_sku_sap_y_conversion(conn, codigo_interno, pack_sap)
                    sku_sap = sap_info["sku_sap"]
                    unidad_conversion = sap_info["unidad_conversion"]
                    unidad_sap = sap_info["unidad_sap"] or pack_sap
                    
                    if not unidad_conversion:
                        errores.append(
                            f"Producto {codigo_interno}: No se encontró unidad de conversión para pack {pack_sap}"
                        )
                        continue
                    
                    # Convertir cantidad (docenas → packs)
                    cantidad_sap = cantidad_confirmada * unidad_conversion
                    
                    # Calcular precios
                    costo_unitario = item["costo_unitario"] or 0.0
                    descuento = item["descuento"] or 0.0
                    
                    # Precio unitario en packs (si el costo viene en docenas)
                    precio_unitario_sap = costo_unitario / unidad_conversion if unidad_conversion > 0 else costo_unitario
                    
                    # Calcular total con descuento
                    subtotal = cantidad_sap * precio_unitario_sap
                    total_linea = subtotal * (1 - descuento / 100) if descuento else subtotal
                    
                    oc_detalles.append({
                        "sku_sap": sku_sap,
                        "cantidad_sap": cantidad_sap,
                        "unidad_sap": unidad_sap,
                        "referencia_detalle": item["pedido_detalle_id"],
                        "precio_unitario": precio_unitario_sap,
                        "total_linea": total_linea,
                        "cantidad_origen": cantidad_confirmada  # Guardar cantidad original en docenas
                    })
                    
                except Exception as e:
                    errores.append(f"Producto {codigo_interno}: {str(e)}")
                    logger.warning(f"⚠️ Error al procesar producto {codigo_interno}: {e}")
                    continue
            
            if errores:
                raise ValueError(
                    f"Errores al procesar productos:\n" + "\n".join(errores)
                )
            
            if not oc_detalles:
                raise ValueError("No se pudo crear ninguna línea de detalle para la OC")
            
            # 5. Obtener proveedor (CardCode)
            proveedor_nombre = cantidades_confirmadas[0]["proveedor_nombre"]
            proveedor = oc_repo.get_proveedor_from_cliente(proveedor_nombre)
            
            if not proveedor:
                raise ValueError(f"No se pudo determinar el proveedor (CardCode) para: {proveedor_nombre}")
            
            # 6. Crear cabecera de OC
            fecha_pedido = cantidades_confirmadas[0]["fecha_pedido"]
            fecha_generacion = datetime.fromisoformat(fecha_pedido) if fecha_pedido else datetime.now()
            
            datos_cabecera = {
                "despacho_id": None,  # No viene de despacho
                "pedido_id": pedido_id,  # ⭐ Asociar con pedido
                "proveedor": proveedor,
                "fecha_generacion": fecha_generacion,
                "referencia_despacho": None,  # No hay referencia de despacho
                "estado": "PENDIENTE"
            }
            
            oc_id = oc_repo.insert_cabecera(datos_cabecera)
            
            # 7. Crear detalles de OC
            detalles_insertados = oc_repo.insert_detalles(oc_id, oc_detalles)
            
            logger.info(
                f"✅ OC creada desde pedido {pedido_id}: "
                f"OC ID={oc_id}, {detalles_insertados} líneas"
            )
            
            return {
                "oc_id": oc_id,
                "pedido_id": pedido_id,
                "proveedor": proveedor,
                "estado": "PENDIENTE",
                "detalles_insertados": detalles_insertados,
                "total_lineas": len(oc_detalles),
                "warnings": warnings
            }
