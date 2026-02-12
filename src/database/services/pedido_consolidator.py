"""
Consolidador para normalizar y consolidar datos de pedidos.

Responsabilidad: Normalizar datos parseados y consolidar duplicados.
NO hace parsing, NO persiste en BD.
"""

import logging
import pandas as pd
from typing import Dict, Any, Optional, List
from datetime import date

logger = logging.getLogger(__name__)


class PedidoConsolidator:
    """
    Consolidador para normalizar y consolidar datos de pedidos.
    
    Convierte datos parseados a formato normalizado para BD.
    """
    
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
        
        # Mapeo de campos del Excel a campos de BD
        # Priorizar nombres normalizados, luego buscar variaciones
        if "numero_pedido" in cabecera_parseada:
            cabecera_bd["numero_pedido"] = cabecera_parseada["numero_pedido"]
        elif "CODIGO PEDIDO" in cabecera_parseada:
            cabecera_bd["numero_pedido"] = cabecera_parseada["CODIGO PEDIDO"]
        elif "CÓDIGO PEDIDO" in cabecera_parseada:
            cabecera_bd["numero_pedido"] = cabecera_parseada["CÓDIGO PEDIDO"]
        
        if "fecha_pedido" in cabecera_parseada:
            cabecera_bd["fecha_pedido"] = cabecera_parseada["fecha_pedido"]
        elif "FECHA DE PEDIDO" in cabecera_parseada:
            cabecera_bd["fecha_pedido"] = cabecera_parseada["FECHA DE PEDIDO"]
        elif "FECHA PEDIDO" in cabecera_parseada:
            cabecera_bd["fecha_pedido"] = cabecera_parseada["FECHA PEDIDO"]
        
        if "fecha_entrega" in cabecera_parseada:
            cabecera_bd["fecha_entrega"] = cabecera_parseada["fecha_entrega"]
        elif "FECHA DE ENTREGA" in cabecera_parseada:
            cabecera_bd["fecha_entrega"] = cabecera_parseada["FECHA DE ENTREGA"]
        elif "FECHA ENTREGA" in cabecera_parseada:
            cabecera_bd["fecha_entrega"] = cabecera_parseada["FECHA ENTREGA"]
        
        if "forma_pago" in cabecera_parseada:
            cabecera_bd["forma_pago"] = cabecera_parseada["forma_pago"]
        elif "FORMA PAGO" in cabecera_parseada:
            cabecera_bd["forma_pago"] = cabecera_parseada["FORMA PAGO"]
        elif "FORMA DE PAGO" in cabecera_parseada:
            cabecera_bd["forma_pago"] = cabecera_parseada["FORMA DE PAGO"]
        
        if "mensaje" in cabecera_parseada:
            cabecera_bd["mensaje"] = cabecera_parseada["mensaje"]
        elif "MENSAJE" in cabecera_parseada:
            cabecera_bd["mensaje"] = cabecera_parseada["MENSAJE"]
        
        if "proveedor_nombre" in cabecera_parseada:
            cabecera_bd["proveedor_nombre"] = cabecera_parseada["proveedor_nombre"]
        elif "NOMBRE PROVEEDOR" in cabecera_parseada:
            cabecera_bd["proveedor_nombre"] = cabecera_parseada["NOMBRE PROVEEDOR"]
        
        if "comprador_nombre" in cabecera_parseada:
            cabecera_bd["comprador_nombre"] = cabecera_parseada["comprador_nombre"]
        elif "COMPRADOR NOMBRE" in cabecera_parseada:
            cabecera_bd["comprador_nombre"] = cabecera_parseada["COMPRADOR NOMBRE"]
        
        if "comprador_codigo" in cabecera_parseada:
            cabecera_bd["comprador_codigo"] = cabecera_parseada["comprador_codigo"]
        elif "COD COMPRADOR" in cabecera_parseada:
            cabecera_bd["comprador_codigo"] = cabecera_parseada["COD COMPRADOR"]
        elif "CÓD COMPRADOR" in cabecera_parseada:
            cabecera_bd["comprador_codigo"] = cabecera_parseada["CÓD COMPRADOR"]
        
        if "origen_traslado" in cabecera_parseada:
            cabecera_bd["origen_traslado"] = cabecera_parseada["origen_traslado"]
        elif "ORIGEN TRASLADO" in cabecera_parseada:
            cabecera_bd["origen_traslado"] = cabecera_parseada["ORIGEN TRASLADO"]
        
        if "serie" in cabecera_parseada:
            cabecera_bd["serie"] = cabecera_parseada["serie"]
        elif "SERIE" in cabecera_parseada:
            cabecera_bd["serie"] = cabecera_parseada["SERIE"]
        
        # Convertir fecha_pedido a DATE (manejar Timestamp, datetime, string)
        if cabecera_bd["fecha_pedido"]:
            try:
                import pandas as pd
                from datetime import datetime, date
                
                valor = cabecera_bd["fecha_pedido"]
                
                # Si ya es date, dejar como está
                if isinstance(valor, date) and not isinstance(valor, datetime):
                    pass
                # Si es datetime o Timestamp, convertir a date
                elif isinstance(valor, (datetime, pd.Timestamp)):
                    cabecera_bd["fecha_pedido"] = valor.date()
                # Si es string, parsear
                elif isinstance(valor, str):
                    valor_limpio = valor.strip()
                    if "/" in valor_limpio:
                        cabecera_bd["fecha_pedido"] = pd.to_datetime(valor_limpio, dayfirst=True).date()
                    else:
                        cabecera_bd["fecha_pedido"] = pd.to_datetime(valor_limpio).date()
            except Exception as e:
                logger.warning(f"⚠️ Error al parsear fecha_pedido '{cabecera_bd['fecha_pedido']}': {e}")
                cabecera_bd["fecha_pedido"] = None
        
        # Convertir fecha_entrega a DATE (manejar Timestamp, datetime, string)
        if cabecera_bd["fecha_entrega"]:
            try:
                import pandas as pd
                from datetime import datetime, date
                
                valor = cabecera_bd["fecha_entrega"]
                
                # Si ya es date, dejar como está
                if isinstance(valor, date) and not isinstance(valor, datetime):
                    pass
                # Si es datetime o Timestamp, convertir a date
                elif isinstance(valor, (datetime, pd.Timestamp)):
                    cabecera_bd["fecha_entrega"] = valor.date()
                # Si es string, intentar parsear (pero si dice "INMEDIATO", dejar como está)
                elif isinstance(valor, str):
                    valor_limpio = valor.strip().upper()
                    # Si es "INMEDIATO" u otro texto especial, mantener como string
                    if valor_limpio in ("INMEDIATO", "ASAP", "URGE", ""):
                        cabecera_bd["fecha_entrega"] = valor_limpio.lower() if valor_limpio else None
                    else:
                        # Intentar parsear como fecha
                        try:
                            if "/" in valor_limpio:
                                cabecera_bd["fecha_entrega"] = pd.to_datetime(valor_limpio, dayfirst=True).date()
                            else:
                                cabecera_bd["fecha_entrega"] = pd.to_datetime(valor_limpio).date()
                        except:
                            # Si no es fecha, mantener el string original
                            cabecera_bd["fecha_entrega"] = valor.lower()
            except Exception as e:
                logger.warning(f"⚠️ Error al parsear fecha_entrega '{cabecera_bd['fecha_entrega']}': {e}")
                cabecera_bd["fecha_entrega"] = None
        
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
            cantidad_total = 0
            for dist in distribuciones:
                cantidad = dist.get("cantidad", 0)
                if cantidad and isinstance(cantidad, (int, float)):
                    cantidad_total += int(cantidad)
            
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
                    # Suma todas las cantidades para el producto
                    subtotales[codigo] = subtotales.get(codigo, 0) + cantidad

            return subtotales

