"""
Servicio de validación para redistribución (FASE 4).
Implementa las reglas de negocio estrictas para la redistribución.
"""

import logging
from typing import Dict, Any, List, Tuple

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
        errores: List[str] = []
        errores.extend(RedistribucionValidator._validar_cantidades_distribuciones(productos_redistribucion))
        errores.extend(RedistribucionValidator._validar_totales_vs_confirmados(productos_redistribucion, respuestas_proveedor))
        errores.extend(RedistribucionValidator._validar_tiendas_pertenecen_al_pedido(pedido_data, productos_redistribucion))
        errores.extend(RedistribucionValidator._validar_sin_duplicados_tiendas(productos_redistribucion))
        errores.extend(RedistribucionValidator._validar_estado_pedido(pedido_data))
        errores.extend(RedistribucionValidator._validar_bodegas_no_negativas(pedido_data, productos_redistribucion))

        es_valido = len(errores) == 0
        if not es_valido:
            logger.warning(f"⚠️ Validación de redistribución falló: {len(errores)} errores")
            for error in errores:
                logger.warning(f"  - {error}")
        return es_valido, errores

    @staticmethod
    def _validar_cantidades_distribuciones(
        productos_redistribucion: List[Dict[str, Any]]
    ) -> List[str]:
        """Validación 1: cantidades no negativas y dentro del rango permitido (acepta decimales)."""
        errores: List[str] = []
        for producto in productos_redistribucion:
            pedido_detalle_id = producto["pedido_detalle_id"]
            for distribucion in producto["distribuciones"]:
                cantidad_asignada = distribucion["cantidad_asignada"]
                tienda_id = distribucion["tienda_id"]
                if cantidad_asignada < 0:
                    errores.append(
                        f"Producto {pedido_detalle_id}: cantidad_asignada no puede ser negativa "
                        f"(tienda {tienda_id}: {cantidad_asignada})"
                    )
                # Acepta decimales (ej. 0.5, 1.25); alineado con frontend y AjusteDetalle/DistribucionTiendaFrontend (float).
                if cantidad_asignada > 1000000:
                    errores.append(
                        f"Producto {pedido_detalle_id}: cantidad_asignada excede el límite máximo "
                        f"(tienda {tienda_id}: {cantidad_asignada}). Máximo permitido: 1,000,000"
                    )
        return errores

    @staticmethod
    def _validar_totales_vs_confirmados(
        productos_redistribucion: List[Dict[str, Any]],
        respuestas_proveedor: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """Validación 2: suma de cantidades asignadas == cantidad confirmada por proveedor."""
        _tol = 1e-6
        errores: List[str] = []
        for producto in productos_redistribucion:
            pedido_detalle_id = producto["pedido_detalle_id"]
            cantidad_asignada_total = sum(d["cantidad_asignada"] for d in producto["distribuciones"])
            respuesta = respuestas_proveedor.get(pedido_detalle_id, {})
            cantidad_confirmada_total = respuesta.get("cantidad_confirmada_total", 0)
            if abs(float(cantidad_asignada_total) - float(cantidad_confirmada_total)) > _tol:
                diferencia = cantidad_confirmada_total - cantidad_asignada_total
                errores.append(
                    f"Producto {pedido_detalle_id}: La suma de cantidades asignadas ({cantidad_asignada_total}) "
                    f"no coincide con la cantidad confirmada por el proveedor ({cantidad_confirmada_total}). "
                    f"Diferencia: {diferencia}"
                )
            if cantidad_confirmada_total < 0:
                errores.append(
                    f"Producto {pedido_detalle_id}: La cantidad confirmada no puede ser negativa "
                    f"({cantidad_confirmada_total})"
                )
        return errores

    @staticmethod
    def _validar_tiendas_pertenecen_al_pedido(
        pedido_data: Dict[str, Any],
        productos_redistribucion: List[Dict[str, Any]]
    ) -> List[str]:
        """Validación 3: todos los productos existen en el pedido y sus tiendas pertenecen a él."""
        errores: List[str] = []
        tiendas_validas: set = set()
        for detalle in pedido_data.get("detalles", []):
            for tienda in detalle.get("tiendas", []):
                tiendas_validas.add(tienda["tienda_id"])

        for producto in productos_redistribucion:
            pedido_detalle_id = producto["pedido_detalle_id"]
            producto_existe = any(
                d["pedido_detalle_id"] == pedido_detalle_id
                for d in pedido_data.get("detalles", [])
            )
            if not producto_existe:
                errores.append(f"Producto {pedido_detalle_id}: No existe en el pedido")
                continue
            for distribucion in producto["distribuciones"]:
                tienda_id = distribucion["tienda_id"]
                if tienda_id not in tiendas_validas:
                    errores.append(
                        f"Producto {pedido_detalle_id}: Tienda {tienda_id} no pertenece al pedido"
                    )
        return errores

    @staticmethod
    def _validar_sin_duplicados_tiendas(
        productos_redistribucion: List[Dict[str, Any]]
    ) -> List[str]:
        """Validación 4: tienda_id no vacío y sin duplicados por producto."""
        errores: List[str] = []
        for producto in productos_redistribucion:
            pedido_detalle_id = producto["pedido_detalle_id"]
            tiendas_vistas: set = set()
            for distribucion in producto["distribuciones"]:
                tienda_id = distribucion["tienda_id"]
                if not tienda_id or not isinstance(tienda_id, str) or len(tienda_id.strip()) == 0:
                    errores.append(
                        f"Producto {pedido_detalle_id}: Tienda ID inválido o vacío en la redistribución"
                    )
                    continue
                if tienda_id in tiendas_vistas:
                    errores.append(
                        f"Producto {pedido_detalle_id}: Tienda {tienda_id} duplicada en la redistribución"
                    )
                tiendas_vistas.add(tienda_id)
        return errores

    @staticmethod
    def _validar_estado_pedido(pedido_data: Dict[str, Any]) -> List[str]:
        """Validación 5: el pedido debe estar en estado REDISTRIBUCION (CONFIRMADO POR EL RAYO)."""
        cabecera = pedido_data.get("cabecera", {})
        estado_id = cabecera.get("estado_id")
        if estado_id is None:
            estado_id = estado_id_desde_legacy(cabecera.get("estado"))
        estado_nombre = cabecera.get("estado_nombre") or cabecera.get("estado") or "N/A"
        if estado_id != ESTADO_REDISTRIBUCION:
            return [
                f"El estado del pedido ({estado_nombre}) no permite confirmar redistribución. "
                "Solo se permite en estado CONFIRMADO POR EL RAYO."
            ]
        return []

    @staticmethod
    def _bodegas_de_detalle(detalle: Dict[str, Any]) -> Dict[str, Any]:
        """Retorna mapa {tienda_id: cantidad} de las tiendas marcadas como bodega en un detalle."""
        return {
            tienda["tienda_id"]: tienda.get("cantidad", 0)
            for tienda in detalle.get("tiendas", [])
            if tienda.get("es_bodega", False)
        }

    @staticmethod
    def _validar_bodegas_producto(
        pedido_detalle_id: str,
        bodegas_originales: Dict[str, Any],
        producto_redistribucion: Dict[str, Any]
    ) -> List[str]:
        """Valida que ninguna bodega quede con cantidad negativa para un producto."""
        errores: List[str] = []
        for distribucion in producto_redistribucion["distribuciones"]:
            tienda_id = distribucion["tienda_id"]
            if tienda_id in bodegas_originales:
                cantidad_asignada = distribucion["cantidad_asignada"]
                # La validación 1 ya cubre negativos en general; aquí damos mensaje específico de bodega.
                if cantidad_asignada < 0:
                    errores.append(
                        f"Producto {pedido_detalle_id}: La bodega {tienda_id} no puede tener cantidad negativa "
                        f"(cantidad asignada: {cantidad_asignada})"
                    )
        return errores

    @staticmethod
    def _validar_bodegas_no_negativas(
        pedido_data: Dict[str, Any],
        productos_redistribucion: List[Dict[str, Any]]
    ) -> List[str]:
        """Validación 6: las bodegas no pueden quedar con cantidad negativa tras la redistribución."""
        errores: List[str] = []
        for detalle in pedido_data.get("detalles", []):
            pedido_detalle_id = detalle.get("pedido_detalle_id")
            producto_redistribucion = next(
                (p for p in productos_redistribucion if p["pedido_detalle_id"] == pedido_detalle_id),
                None
            )
            if producto_redistribucion:
                bodegas_originales = RedistribucionValidator._bodegas_de_detalle(detalle)
                errores.extend(RedistribucionValidator._validar_bodegas_producto(
                    pedido_detalle_id, bodegas_originales, producto_redistribucion
                ))
        return errores
    
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
