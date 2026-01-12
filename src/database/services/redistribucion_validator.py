"""
Servicio de validación para redistribución (FASE 4).
Implementa las reglas de negocio estrictas para la redistribución.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)


class RedistribucionValidator:
    """Validador de redistribución con reglas de negocio estrictas."""
    
    @staticmethod
    def validar_redistribucion(
        pedido_data: Dict[str, Any],
        productos_redistribucion: List[Dict[str, Any]],
        respuestas_proveedor: Dict[str, Dict[str, Any]]
    ) -> Tuple[bool, List[str]]:
        """
        Valida una redistribución completa según las reglas de negocio.
        
        Args:
            pedido_data: Datos completos del pedido (con detalles y tiendas)
            productos_redistribucion: Lista de productos con redistribuciones
            respuestas_proveedor: Diccionario con respuestas del proveedor por pedido_detalle_id
                Formato: {
                    "pedido_detalle_id": {
                        "cantidad_solicitada_total": 100,
                        "cantidad_confirmada_total": 80
                    }
                }
        
        Returns:
            Tuple (es_valido, lista_errores)
        """
        errores = []
        
        # Validación 1: No valores negativos
        for producto in productos_redistribucion:
            pedido_detalle_id = producto["pedido_detalle_id"]
            for distribucion in producto["distribuciones"]:
                cantidad_asignada = distribucion["cantidad_asignada"]
                if cantidad_asignada < 0:
                    errores.append(
                        f"Producto {pedido_detalle_id}: cantidad_asignada no puede ser negativa "
                        f"(tienda {distribucion['tienda_id']}: {cantidad_asignada})"
                    )
        
        # Validación 2: La suma por producto <= cantidad confirmada
        for producto in productos_redistribucion:
            pedido_detalle_id = producto["pedido_detalle_id"]
            cantidad_asignada_total = sum(
                d["cantidad_asignada"] for d in producto["distribuciones"]
            )
            
            respuesta = respuestas_proveedor.get(pedido_detalle_id, {})
            cantidad_confirmada_total = respuesta.get("cantidad_confirmada_total", 0)
            
            if cantidad_asignada_total > cantidad_confirmada_total:
                errores.append(
                    f"Producto {pedido_detalle_id}: La suma de cantidades asignadas ({cantidad_asignada_total}) "
                    f"excede la cantidad confirmada por el proveedor ({cantidad_confirmada_total})"
                )
        
        # Validación 3: Todas las tiendas pertenecen al pedido
        # Obtener tiendas válidas del pedido
        tiendas_validas = set()
        for detalle in pedido_data.get("detalles", []):
            for tienda in detalle.get("tiendas", []):
                tiendas_validas.add(tienda["tienda_id"])
        
        for producto in productos_redistribucion:
            pedido_detalle_id = producto["pedido_detalle_id"]
            
            # Verificar que el producto existe en el pedido
            producto_existe = any(
                d["pedido_detalle_id"] == pedido_detalle_id 
                for d in pedido_data.get("detalles", [])
            )
            
            if not producto_existe:
                errores.append(
                    f"Producto {pedido_detalle_id}: No existe en el pedido"
                )
                continue
            
            # Verificar que todas las tiendas de la redistribución pertenecen al pedido
            for distribucion in producto["distribuciones"]:
                tienda_id = distribucion["tienda_id"]
                if tienda_id not in tiendas_validas:
                    errores.append(
                        f"Producto {pedido_detalle_id}: Tienda {tienda_id} no pertenece al pedido"
                    )
        
        # Validación 4: No duplicados de tienda por producto
        for producto in productos_redistribucion:
            pedido_detalle_id = producto["pedido_detalle_id"]
            tiendas_vistas = set()
            for distribucion in producto["distribuciones"]:
                tienda_id = distribucion["tienda_id"]
                if tienda_id in tiendas_vistas:
                    errores.append(
                        f"Producto {pedido_detalle_id}: Tienda {tienda_id} duplicada en la redistribución"
                    )
                tiendas_vistas.add(tienda_id)
        
        # Validación 5: El pedido debe tener respuesta del proveedor
        if not respuestas_proveedor:
            errores.append(
                "El pedido no tiene respuesta del proveedor. Debe existir una confirmación antes de redistribuir."
            )
        
        # Validación 6: Estado del pedido debe permitir redistribución
        estado_pedido = pedido_data.get("cabecera", {}).get("estado", "")
        estados_permitidos = [
            "RESPUESTA_PROVEEDOR_CARGADA",  # Estado después de que EL RAYO confirma (Fase 3)
            "CONFIRMADO_PROVEEDOR",
            "EN_AJUSTE_MABEL",
            "PENDIENTE_CONFIRMACION_PROVEEDOR"  # Por si acaso
        ]
        
        if estado_pedido and estado_pedido not in estados_permitidos:
            errores.append(
                f"El estado del pedido ({estado_pedido}) no permite redistribución. "
                f"Estados permitidos: {', '.join(estados_permitidos)}"
            )
        
        es_valido = len(errores) == 0
        
        if not es_valido:
            logger.warning(f"⚠️ Validación de redistribución falló: {len(errores)} errores")
            for error in errores:
                logger.warning(f"  - {error}")
        
        return es_valido, errores
    
    @staticmethod
    def validar_confirmacion_redistribucion(
        pedido_id: str,
        version: int,
        distribucion_data: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Valida que una redistribución puede ser confirmada.
        
        Args:
            pedido_id: UUID del pedido
            version: Versión a confirmar
            distribucion_data: Datos de la distribución a confirmar
        
        Returns:
            Tuple (es_valido, lista_errores)
        """
        errores = []
        
        # Validación 1: La versión debe existir
        if version == 0:
            errores.append("No existe ninguna redistribución para confirmar")
        
        # Validación 2: Debe haber al menos una distribución
        productos = distribucion_data.get("productos", [])
        if not productos:
            errores.append("No hay productos en la redistribución para confirmar")
        
        # Validación 3: Todas las distribuciones deben tener estado PENDIENTE
        for producto in productos:
            for distribucion in producto.get("distribuciones", []):
                estado = distribucion.get("estado", "")
                if estado != "PENDIENTE":
                    errores.append(
                        f"Producto {producto.get('pedido_detalle_id')}: "
                        f"La redistribución ya está en estado {estado} (debe estar PENDIENTE)"
                    )
        
        es_valido = len(errores) == 0
        
        if not es_valido:
            logger.warning(f"⚠️ Validación de confirmación falló: {len(errores)} errores")
        
        return es_valido, errores
