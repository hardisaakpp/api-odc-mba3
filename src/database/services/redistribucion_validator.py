"""
Servicio de validación para redistribución (FASE 4).
Implementa las reglas de negocio estrictas para la redistribución.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal

from src.database.pedido_estados import ESTADO_REDISTRIBUCION, estado_id_desde_legacy

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
        
        # Validación 1: No valores negativos y deben ser enteros
        for producto in productos_redistribucion:
            pedido_detalle_id = producto["pedido_detalle_id"]
            for distribucion in producto["distribuciones"]:
                cantidad_asignada = distribucion["cantidad_asignada"]
                
                # Validar que no sea negativo
                if cantidad_asignada < 0:
                    errores.append(
                        f"Producto {pedido_detalle_id}: cantidad_asignada no puede ser negativa "
                        f"(tienda {distribucion['tienda_id']}: {cantidad_asignada})"
                    )
                
                # Validar que sea un número entero (no decimal)
                if isinstance(cantidad_asignada, float) and cantidad_asignada % 1 != 0:
                    errores.append(
                        f"Producto {pedido_detalle_id}: cantidad_asignada debe ser un número entero "
                        f"(tienda {distribucion['tienda_id']}: {cantidad_asignada})"
                    )
                
                # Validar rango razonable (máximo 1,000,000 unidades por tienda)
                if cantidad_asignada > 1000000:
                    errores.append(
                        f"Producto {pedido_detalle_id}: cantidad_asignada excede el límite máximo "
                        f"(tienda {distribucion['tienda_id']}: {cantidad_asignada}). Máximo permitido: 1,000,000"
                    )
        
        # Validación 2: La suma de cantidades asignadas debe ser igual a la cantidad confirmada por el proveedor
        # Esta validación garantiza consistencia entre backend y frontend (el botón Confirmar Redistribución
        # solo se habilita cuando la diferencia es 0 para cada producto).
        for producto in productos_redistribucion:
            pedido_detalle_id = producto["pedido_detalle_id"]
            cantidad_asignada_total = sum(
                d["cantidad_asignada"] for d in producto["distribuciones"]
            )
            
            respuesta = respuestas_proveedor.get(pedido_detalle_id, {})
            cantidad_confirmada_total = respuesta.get("cantidad_confirmada_total", 0)
            
            # Validar que la suma total sea un entero
            if isinstance(cantidad_asignada_total, float) and cantidad_asignada_total % 1 != 0:
                errores.append(
                    f"Producto {pedido_detalle_id}: La suma total de cantidades asignadas debe ser un número entero "
                    f"(suma actual: {cantidad_asignada_total})"
                )
            
            # Validar que la suma de cantidades asignadas sea igual a la cantidad confirmada
            if cantidad_asignada_total != cantidad_confirmada_total:
                diferencia = cantidad_confirmada_total - cantidad_asignada_total
                errores.append(
                    f"Producto {pedido_detalle_id}: La suma de cantidades asignadas ({cantidad_asignada_total}) "
                    f"no coincide con la cantidad confirmada por el proveedor ({cantidad_confirmada_total}). "
                    f"Diferencia: {diferencia}"
                )
            
            # Validar que la cantidad confirmada sea válida
            if cantidad_confirmada_total < 0:
                errores.append(
                    f"Producto {pedido_detalle_id}: La cantidad confirmada no puede ser negativa "
                    f"({cantidad_confirmada_total})"
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
        
        # Validación 4: No duplicados de tienda por producto y validar formato de tienda_id
        for producto in productos_redistribucion:
            pedido_detalle_id = producto["pedido_detalle_id"]
            tiendas_vistas = set()
            for distribucion in producto["distribuciones"]:
                tienda_id = distribucion["tienda_id"]
                
                # Validar formato de tienda_id (debe ser UUID válido o string no vacío)
                if not tienda_id or not isinstance(tienda_id, str) or len(tienda_id.strip()) == 0:
                    errores.append(
                        f"Producto {pedido_detalle_id}: Tienda ID inválido o vacío en la redistribución"
                    )
                    continue
                
                # Validar duplicados
                if tienda_id in tiendas_vistas:
                    errores.append(
                        f"Producto {pedido_detalle_id}: Tienda {tienda_id} duplicada en la redistribución"
                    )
                tiendas_vistas.add(tienda_id)
        
        # Validación 5: Solo el estado REDISTRIBUCION (CONFIRMADO POR EL RAYO) permite confirmar redistribución
        # Nota: Si el pedido está en este estado, la respuesta del proveedor ya existe (validación implícita)
        cabecera = pedido_data.get("cabecera", {})
        estado_id = cabecera.get("estado_id")
        if estado_id is None:
            estado_id = estado_id_desde_legacy(cabecera.get("estado"))
        estado_nombre = cabecera.get("estado_nombre") or cabecera.get("estado") or "N/A"
        if estado_id != ESTADO_REDISTRIBUCION:
            errores.append(
                f"El estado del pedido ({estado_nombre}) no permite confirmar redistribución. "
                "Solo se permite en estado CONFIRMADO POR EL RAYO."
            )
        
        # Validación 6: Validar bodegas - las bodegas no pueden quedar negativas
        # Cuando se redistribuye desde bodega a tiendas, la bodega debe tener suficiente inventario
        # Para esto necesitamos obtener información de bodegas del pedido original
        for detalle in pedido_data.get("detalles", []):
            pedido_detalle_id = detalle.get("pedido_detalle_id")
            
            # Buscar si este producto tiene redistribución
            producto_redistribucion = next(
                (p for p in productos_redistribucion if p["pedido_detalle_id"] == pedido_detalle_id),
                None
            )
            
            if producto_redistribucion:
                # Obtener bodegas originales de este producto
                bodegas_originales = {}
                for tienda in detalle.get("tiendas", []):
                    if tienda.get("es_bodega", False):
                        bodegas_originales[tienda["tienda_id"]] = tienda.get("cantidad", 0)
                
                # Verificar que las bodegas en la redistribución no queden negativas
                for distribucion in producto_redistribucion["distribuciones"]:
                    tienda_id = distribucion["tienda_id"]
                    
                    # Si esta tienda es una bodega, verificar que la cantidad no sea negativa
                    if tienda_id in bodegas_originales:
                        cantidad_asignada = distribucion["cantidad_asignada"]
                        # Ya validamos que no sea negativa en la validación 1,
                        # pero aquí podemos dar un mensaje más específico si es bodega
                        if cantidad_asignada < 0:
                            errores.append(
                                f"Producto {pedido_detalle_id}: La bodega {tienda_id} no puede tener cantidad negativa "
                                f"(cantidad asignada: {cantidad_asignada})"
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
