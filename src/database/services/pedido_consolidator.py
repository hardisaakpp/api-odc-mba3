"""
Consolidador para normalizar y consolidar datos de pedidos.

Responsabilidad: Normalizar datos parseados y consolidar duplicados.
NO hace parsing, NO persiste en BD.
"""

import logging
import pandas as pd
from typing import Dict, Any, Optional, List
from datetime import date, datetime

logger = logging.getLogger(__name__)


class PedidoConsolidator:
    """
    Consolidador para normalizar y consolidar datos de pedidos.
    
    Convierte datos parseados a formato normalizado para BD.
    """
    
    _CAMPO_ALIASES: Dict[str, list] = {
        "numero_pedido": ["numero_pedido", "CODIGO PEDIDO", "CÓDIGO PEDIDO"],
        "fecha_pedido": ["fecha_pedido", "FECHA DE PEDIDO", "FECHA PEDIDO"],
        "fecha_entrega": ["fecha_entrega", "FECHA DE ENTREGA", "FECHA ENTREGA"],
        "forma_pago": ["forma_pago", "FORMA PAGO", "FORMA DE PAGO"],
        "mensaje": ["mensaje", "MENSAJE"],
        "proveedor_nombre": ["proveedor_nombre", "NOMBRE PROVEEDOR"],
        "comprador_nombre": ["comprador_nombre", "COMPRADOR NOMBRE"],
        "comprador_codigo": ["comprador_codigo", "COD COMPRADOR", "CÓD COMPRADOR"],
        "origen_traslado": ["origen_traslado", "ORIGEN TRASLADO"],
        "serie": ["serie", "SERIE"],
    }

    @staticmethod
    def _parsear_fecha_simple(valor: Any) -> Optional[date]:
        try:
            if isinstance(valor, datetime):
                return valor.date()
            if isinstance(valor, date):
                return valor
            if isinstance(valor, str):
                valor_limpio = valor.strip()
                if "/" in valor_limpio:
                    return pd.to_datetime(valor_limpio, dayfirst=True).date()
                return pd.to_datetime(valor_limpio).date()
            return None
        except Exception as e:
            logger.warning(f"⚠️ Error al parsear fecha '{valor}': {e}")
            return None

    @staticmethod
    def _parsear_fecha_entrega(valor: Any) -> Any:
        try:
            if isinstance(valor, datetime):
                return valor.date()
            if isinstance(valor, date):
                return valor
            if isinstance(valor, str):
                valor_limpio = valor.strip().upper()
                if valor_limpio in ("INMEDIATO", "ASAP", "URGE", ""):
                    return valor_limpio.lower() if valor_limpio else None
                try:
                    if "/" in valor_limpio:
                        return pd.to_datetime(valor_limpio, dayfirst=True).date()
                    return pd.to_datetime(valor_limpio).date()
                except Exception:
                    return valor.lower()
            return None
        except Exception as e:
            logger.warning(f"⚠️ Error al parsear fecha_entrega '{valor}': {e}")
            return None

    def normalizar_cabecera_para_bd(
        self, 
        cabecera_parseada: Dict[str, Any], 
        filename: str, 
        usuario_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Normaliza la cabecera parseada del Excel al formato esperado por la BD.
        
        Convierte los campos del Excel (ej: "CODIGO PEDIDO") a los nombres
        de campos de la BD (ej: "numero_pedido").
        
        Args:
            cabecera_parseada: Diccionario con campos parseados del Excel
            filename: Nombre del archivo
            usuario_id: ID del usuario
            
        Returns:
            Diccionario normalizado para insertar en tabla pedido
        """
        cabecera_bd = {
            "numero_pedido": None,
            "fecha_pedido": None,
            "fecha_entrega": None,
            "forma_pago": None,
            "mensaje": None,
            "proveedor_nombre": None,
            "comprador_nombre": None,
            "comprador_codigo": None,
            "origen_traslado": None,
            "serie": None,
            "archivo_nombre": filename,
            "creado_por": usuario_id,
        }

        for campo_bd, aliases in PedidoConsolidator._CAMPO_ALIASES.items():
            for alias in aliases:
                if alias in cabecera_parseada:
                    cabecera_bd[campo_bd] = cabecera_parseada[alias]
                    break

        if cabecera_bd["fecha_pedido"]:
            cabecera_bd["fecha_pedido"] = PedidoConsolidator._parsear_fecha_simple(
                cabecera_bd["fecha_pedido"]
            )

        if cabecera_bd["fecha_entrega"]:
            cabecera_bd["fecha_entrega"] = PedidoConsolidator._parsear_fecha_entrega(
                cabecera_bd["fecha_entrega"]
            )

        return cabecera_bd
    
    def consolidar_detalles_simple(
        self, 
        data_parseada: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Consolida detalles del formato simple agrupando por CodigoProducto.
        
        Args:
            data_parseada: Lista de items parseados con codigoProducto, idTienda, cantidad
            
        Returns:
            Lista de detalles consolidados con distribuciones
        """
        detalles_consolidados = []
        productos_agrupados = {}
        
        for item in data_parseada:
            codigo_producto = item.get("codigoProducto")
            id_tienda = item.get("idTienda")
            cantidad = item.get("cantidad")
            fila_origen = item.get("filaOrigen")
            es_bodega = item.get("es_bodega", False)  # ⭐ NUEVO: Preservar flag de bodega
            
            if not codigo_producto or not id_tienda or not cantidad:
                continue
            
            if codigo_producto not in productos_agrupados:
                productos_agrupados[codigo_producto] = {
                    "detalle": {
                        "codigo_interno": codigo_producto,
                        "descripcion_sap": None,
                        "marca": None,
                        "codigo_barras": None,
                        "pack": None,
                        "costo_doc_sin_iva": None,
                        "descuento_1": None,
                        "pvp": None,
                        "subtotal": None,
                        "total": None,
                    },
                    "distribuciones": [],
                    "filas_origen": []
                }
            
            # Verificar si ya existe esta tienda para este producto
            tienda_existente = None
            for dist in productos_agrupados[codigo_producto]["distribuciones"]:
                if dist.get("tienda_codigo") == id_tienda.upper():
                    tienda_existente = dist
                    break
            
            if tienda_existente:
                # Sumar cantidades si está duplicado
                tienda_existente["cantidad"] += cantidad
            else:
                # Agregar nueva distribución
                productos_agrupados[codigo_producto]["distribuciones"].append({
                    "tienda_codigo": id_tienda.upper(),
                    "tienda_nombre": id_tienda,
                    "cantidad": cantidad,
                    "fila_origen": fila_origen,
                    "es_bodega": es_bodega  # ⭐ NUEVO: Preservar flag de bodega
                })
            
            productos_agrupados[codigo_producto]["filas_origen"].append(fila_origen)
        
        # Convertir diccionario a lista
        for codigo, data in productos_agrupados.items():
            detalles_consolidados.append({
                "detalle": data["detalle"],
                "distribuciones": data["distribuciones"],
                "filas_origen": data["filas_origen"]
            })
        
        return detalles_consolidados
    
    def consolidar_pedido_por_producto(
        self,
        detalles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Genera pedido consolidado sumando cantidades por producto.
        
        Agrupa todas las distribuciones de un mismo producto y suma
        las cantidades totales (sin importar tienda).
        
        Args:
            detalles: Lista de detalles con estructura:
                [
                    {
                        "detalle": {"codigo_interno": "...", ...},
                        "distribuciones": [
                            {"tienda_codigo": "...", "cantidad": 10, ...},
                            ...
                        ]
                    },
                    ...
                ]
        
        Returns:
            {
                "productos_consolidados": [
                    {
                        "codigo_producto": str,
                        "cantidad_total": int,  # Suma de todas las tiendas
                        "distribuciones": List[Dict],  # Distribuciones originales
                        "detalle": Dict  # Datos del detalle
                    }
                ],
                "resumen": {
                    "total_productos": int,
                    "cantidad_total": int  # Suma total de todas las cantidades
                }
            }
        """
        productos_consolidados = []
        cantidad_total_general = 0
        
        for detalle_data in detalles:
            detalle = detalle_data.get("detalle", {})
            distribuciones = detalle_data.get("distribuciones", [])
            
            codigo_producto = detalle.get("codigo_interno")
            if not codigo_producto:
                continue
            
            # Sumar todas las cantidades de este producto (todas las tiendas)
            cantidad_total = 0.0
            for dist in distribuciones:
                cantidad = dist.get("cantidad", 0)
                if cantidad is not None and isinstance(cantidad, (int, float)):
                    cantidad_total += float(cantidad)
            
            productos_consolidados.append({
                "codigo_producto": codigo_producto,
                "cantidad_total": cantidad_total,
                "distribuciones": distribuciones,
                "detalle": detalle
            })
            
            cantidad_total_general += cantidad_total
        
        return {
            "productos_consolidados": productos_consolidados,
            "resumen": {
                "total_productos": len(productos_consolidados),
                "cantidad_total": cantidad_total_general
            }
        }

    @staticmethod
    def calcular_subtotal_por_producto(distribuciones_movimiento: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Calcula el subtotal (suma de cantidades) para cada producto usando solo Movimiento.

        Args:
            distribuciones_movimiento: Lista de distribuciones, cada una con "codigo_producto" y "cantidad".

        Returns:
            Dict con codigo_producto como clave y la suma total de cantidades como valor.
        """
        subtotales: Dict[str, int] = {}

        for dist in distribuciones_movimiento:
            codigo = dist.get("codigo_producto")
            cantidad = dist.get("cantidad", 0)

            if codigo:
                subtotales[codigo] = subtotales.get(codigo, 0) + cantidad

        return subtotales

