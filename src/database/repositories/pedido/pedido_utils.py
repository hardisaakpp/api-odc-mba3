"""
Utilidades compartidas para repositorios de pedido.

CHANGELOG:
- 2026-01-23: Extraído de pedido_repository.py
"""

import logging
import pyodbc
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date

from src.constants.pedido_fields import MAX_PEDIDO_MENSAJE_LENGTH

logger = logging.getLogger(__name__)

_MENSAJE_TABLAS: Tuple[str, ...] = ("pedido", "pedido_original")


def clamp_pedido_mensaje(value: Any, *, max_length: Optional[int] = None) -> Any:
    """Trunca mensaje al máximo efectivo (columna SQL o techo de app). Evita error 2628."""
    cap = max_length if max_length is not None else MAX_PEDIDO_MENSAJE_LENGTH
    if cap <= 0:
        cap = MAX_PEDIDO_MENSAJE_LENGTH
    cap = min(cap, MAX_PEDIDO_MENSAJE_LENGTH)
    if value is None:
        return None
    s = value if isinstance(value, str) else str(value)
    if len(s) <= cap:
        return s
    logger.warning(
        "pedido.mensaje truncado de %d a %d caracteres (límite efectivo)",
        len(s),
        cap,
    )
    return s[:cap]


class PedidoUtils:
    """Utilidades compartidas para repositorios de pedido."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa las utilidades con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
        # Cache para verificación de columnas
        self._tiene_estado_cache: Optional[bool] = None
        self._tiene_estado_id_cache: Optional[bool] = None
        self._tiene_es_bodega_cache: Optional[bool] = None
        self._mensaje_col_max_cache: Dict[str, int] = {}

    def get_mensaje_column_max_len(self, cursor: pyodbc.Cursor, table_name: str) -> int:
        """CHARACTER_MAXIMUM_LENGTH de dbo.<tabla>.mensaje (-1 MAX → techo app)."""
        if table_name not in _MENSAJE_TABLAS:
            return MAX_PEDIDO_MENSAJE_LENGTH
        if table_name in self._mensaje_col_max_cache:
            return self._mensaje_col_max_cache[table_name]
        cursor.execute(
            """
            SELECT CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = ? AND COLUMN_NAME = 'mensaje'
            """,
            (table_name,),
        )
        row = cursor.fetchone()
        raw = row[0] if row else None
        if raw is None or raw == -1:
            effective = MAX_PEDIDO_MENSAJE_LENGTH
        else:
            effective = min(int(raw), MAX_PEDIDO_MENSAJE_LENGTH)
        self._mensaje_col_max_cache[table_name] = effective
        return effective

    def tiene_columna_estado_id(self, cursor: pyodbc.Cursor) -> bool:
        """
        Verifica si la tabla pedido tiene la columna estado_id (FK a pedido_estado).
        """
        cached = self._tiene_estado_id_cache
        if cached is not None:
            return cached
        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'pedido'
            AND COLUMN_NAME = 'estado_id'
        """)
        row = cursor.fetchone()
        resultado = (row[0] if row else 0) > 0
        self._tiene_estado_id_cache = resultado
        return resultado
    
    def tiene_columna_estado(self, cursor: pyodbc.Cursor) -> bool:
        """
        Verifica si la tabla pedido tiene la columna estado.
        
        Args:
            cursor: Cursor de la base de datos
            
        Returns:
            True si existe la columna estado, False en caso contrario
        """
        cached = self._tiene_estado_cache
        if cached is not None:
            return cached

        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'pedido' 
            AND COLUMN_NAME = 'estado'
        """)
        row = cursor.fetchone()
        resultado = (row[0] if row else 0) > 0
        self._tiene_estado_cache = resultado
        return resultado
    
    def tiene_columna_es_bodega(self, cursor: pyodbc.Cursor) -> bool:
        """
        Verifica si la tabla pedido_detalle_tienda tiene la columna es_bodega.
        
        Args:
            cursor: Cursor de la base de datos
            
        Returns:
            True si existe la columna es_bodega, False en caso contrario
        """
        cached = self._tiene_es_bodega_cache
        if cached is not None:
            return cached

        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'pedido_detalle_tienda' 
            AND COLUMN_NAME = 'es_bodega'
        """)
        row = cursor.fetchone()
        resultado = (row[0] if row else 0) > 0
        self._tiene_es_bodega_cache = resultado
        return resultado
    
    def normalizar_fecha(self, fecha: Any) -> Optional[str]:
        """
        Normaliza una fecha a string ISO format.
        
        Args:
            fecha: Fecha en cualquier formato (date, datetime, Timestamp, str)
            
        Returns:
            Fecha en formato ISO string o None
        """
        if fecha is None:
            return None
        
        import pandas as pd
        
        if isinstance(fecha, str):
            return fecha
        elif isinstance(fecha, date):
            return fecha.isoformat() if hasattr(fecha, 'isoformat') else str(fecha)
        elif isinstance(fecha, pd.Timestamp):
            return fecha.date().isoformat()
        elif isinstance(fecha, datetime):
            return fecha.date().isoformat() if hasattr(fecha, 'date') else fecha.isoformat()
        
        return str(fecha)
    
    def construir_cabecera_desde_row(
        self, row: Any, tiene_estado: bool, tiene_estado_id: bool = False
    ) -> Dict[str, Any]:
        """
        Construye un diccionario de cabecera desde una fila de resultado SQL.

        Cuando tiene_estado_id=True, la fila debe incluir estado_id y estado_nombre
        (ej. FROM pedido p LEFT JOIN pedido_estado pe ON pe.id = p.estado_id).
        Se devuelve estado_id, estado_nombre y estado=estado_nombre (compat).
        """
        base = {
            "pedido_id": str(row[0]),
            "numero_pedido": row[1],
            "fecha_pedido": row[2].isoformat() if row[2] else None,
            "fecha_entrega": row[3],
            "forma_pago": row[4],
            "mensaje": row[5],
            "proveedor_nombre": row[6],
            "comprador_nombre": row[7],
            "comprador_codigo": row[8],
            "origen_traslado": row[9],
            "serie": row[10],
            "archivo_nombre": row[11],
            "creado_por": row[12],
        }
        if tiene_estado_id:
            # row: ..., creado_por, estado_id, estado_nombre, creado_en, modificado_por
            base["estado_id"] = row[13] if row[13] is not None else None
            base["estado_nombre"] = row[14] if row[14] is not None else None
            base["estado"] = base["estado_nombre"]  # compat
            base["creado_en"] = row[15].isoformat() if row[15] else None
            base["modificado_por"] = row[16] if len(row) > 16 else None
        elif tiene_estado:
            base["estado"] = row[13]
            base["creado_en"] = row[14].isoformat() if row[14] else None
            base["modificado_por"] = row[15] if len(row) > 15 else None
        else:
            base["creado_en"] = row[13].isoformat() if row[13] else None
            base["modificado_por"] = row[14] if len(row) > 14 else None
        return base
    
    def obtener_distribuciones_tienda(
        self, 
        cursor: pyodbc.Cursor, 
        pedido_detalle_id: str
    ) -> List[Dict[str, Any]]:
        """
        Obtiene las distribuciones por tienda para un detalle de pedido.
        
        Args:
            cursor: Cursor de la base de datos
            pedido_detalle_id: ID del detalle de pedido
            
        Returns:
            Lista de diccionarios con información de tiendas y cantidades
        """
        tiene_es_bodega = self.tiene_columna_es_bodega(cursor)
        
        if tiene_es_bodega:
            cursor.execute("""
                SELECT 
                    pdt.cantidad,
                    t.tienda_id, t.codigo, t.nombre,
                    pdt.es_bodega
                FROM pedido_detalle_tienda pdt
                INNER JOIN tienda t ON pdt.tienda_id = t.tienda_id
                WHERE pdt.pedido_detalle_id = ?
            """, (pedido_detalle_id,))
        else:
            cursor.execute("""
                SELECT 
                    pdt.cantidad,
                    t.tienda_id, t.codigo, t.nombre
                FROM pedido_detalle_tienda pdt
                INNER JOIN tienda t ON pdt.tienda_id = t.tienda_id
                WHERE pdt.pedido_detalle_id = ?
            """, (pedido_detalle_id,))
        
        tiendas_distribucion = []
        for dist_row in cursor.fetchall():
            # cantidad puede ser Decimal o float (columna DECIMAL(18,4)); normalizar a float
            cantidad_val = dist_row[0]
            cantidad_float = float(cantidad_val) if cantidad_val is not None else 0.0
            dist_item = {
                "tienda_id": str(dist_row[1]),
                "codigo": dist_row[2],
                "nombre": dist_row[3],
                "cantidad": cantidad_float,
            }
            if tiene_es_bodega:
                # Convertir SQL Server bit (0 o 1) a Python bool
                dist_item["es_bodega"] = bool(dist_row[4])
            else:
                dist_item["es_bodega"] = False  # Valor por defecto si no existe el campo
            tiendas_distribucion.append(dist_item)
        
        return tiendas_distribucion
    
    def construir_detalle_desde_row(
        self,
        row: Any,
        tiene_comentario: bool,
        tiene_campos_modificados: bool,
        tiendas_distribucion: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Construye un diccionario de detalle desde una fila de resultado SQL.
        
        Args:
            row: Tupla con los valores de la fila
            tiene_comentario: Si True, incluye el campo comentario
            tiene_campos_modificados: Si True, incluye campos de modificación manual
            tiendas_distribucion: Lista de distribuciones por tienda
            
        Returns:
            Diccionario con los datos del detalle
        """
        pedido_detalle_id = str(row[0])
        
        detalle_dict = {
            "pedido_detalle_id": pedido_detalle_id,
            "codigo_interno": row[1],
            "descripcion_sap": row[2],
            "marca": row[3],
            "codigo_barras": row[4],
            "pack": row[5],
            "costo_doc_sin_iva": float(row[6]) if row[6] else None,
            "descuento_1": float(row[7]) if row[7] else None,
            "pvp": float(row[8]) if row[8] else None,
            "subtotal": float(row[9]) if row[9] else None,
            "total": float(row[10]) if row[10] else None,
            "tiendas": tiendas_distribucion,
        }
        
        # Agregar comentario si existe en la consulta
        if tiene_comentario and len(row) > 11:
            detalle_dict["comentario"] = row[11] if row[11] else None
        else:
            detalle_dict["comentario"] = None
        
        # Agregar campos de modificación manual si existen en la consulta
        if tiene_campos_modificados and len(row) > 14:
            detalle_dict["costo_modificado_manual"] = bool(row[12])
            detalle_dict["total_modificado_manual"] = bool(row[13])
            detalle_dict["comentario_modificado_manual"] = bool(row[14])
        else:
            # Si los campos no existen en BD antigua, devolver False por defecto
            detalle_dict["costo_modificado_manual"] = False
            detalle_dict["total_modificado_manual"] = False
            detalle_dict["comentario_modificado_manual"] = False
        
        return detalle_dict
    
    def obtener_detalles_pedido(
        self,
        cursor: pyodbc.Cursor,
        pedido_id: str
    ) -> List[Dict[str, Any]]:
        """
        Obtiene todos los detalles de un pedido con sus distribuciones.
        
        Args:
            cursor: Cursor de la base de datos
            pedido_id: ID del pedido
            
        Returns:
            Lista de diccionarios con los detalles del pedido
        """
        # Orden alfabético por Referencia del Producto (codigo_interno); mismo orden en UI y Excel
        try:
            cursor.execute("""
                SELECT 
                    pd.pedido_detalle_id,
                    pd.codigo_interno, pd.descripcion_sap, pd.marca, pd.codigo_barras,
                    pd.pack, pd.costo_doc_sin_iva, pd.descuento_1, pd.pvp,
                    pd.subtotal, pd.total, pd.comentario,
                    ISNULL(pd.costo_modificado_manual, 0) AS costo_modificado_manual,
                    ISNULL(pd.total_modificado_manual, 0) AS total_modificado_manual,
                    ISNULL(pd.comentario_modificado_manual, 0) AS comentario_modificado_manual
                FROM pedido_detalle pd
                WHERE pd.pedido_id = ?
                ORDER BY pd.codigo_interno, pd.pedido_detalle_id
            """, (pedido_id,))
            tiene_comentario = True
            tiene_campos_modificados = True
        except Exception:
            # Si falla la query anterior (ej. columna inexistente), intentar sin campos opcionales
            try:
                cursor.execute("""
                    SELECT 
                        pd.pedido_detalle_id,
                        pd.codigo_interno, pd.descripcion_sap, pd.marca, pd.codigo_barras,
                        pd.pack, pd.costo_doc_sin_iva, pd.descuento_1, pd.pvp,
                        pd.subtotal, pd.total, pd.comentario,
                        ISNULL(pd.costo_modificado_manual, 0) AS costo_modificado_manual,
                        ISNULL(pd.total_modificado_manual, 0) AS total_modificado_manual,
                        ISNULL(pd.comentario_modificado_manual, 0) AS comentario_modificado_manual
                    FROM pedido_detalle pd
                    WHERE pd.pedido_id = ?
                    ORDER BY pd.codigo_interno, pd.pedido_detalle_id
                """, (pedido_id,))
                tiene_comentario = True
                tiene_campos_modificados = True
            except Exception:
                try:
                    cursor.execute("""
                        SELECT 
                            pd.pedido_detalle_id,
                            pd.codigo_interno, pd.descripcion_sap, pd.marca, pd.codigo_barras,
                            pd.pack, pd.costo_doc_sin_iva, pd.descuento_1, pd.pvp,
                            pd.subtotal, pd.total, pd.comentario
                        FROM pedido_detalle pd
                        WHERE pd.pedido_id = ?
                        ORDER BY pd.codigo_interno, pd.pedido_detalle_id
                    """, (pedido_id,))
                    tiene_comentario = True
                    tiene_campos_modificados = False
                except Exception:
                    cursor.execute("""
                        SELECT 
                            pd.pedido_detalle_id,
                            pd.codigo_interno, pd.descripcion_sap, pd.marca, pd.codigo_barras,
                            pd.pack, pd.costo_doc_sin_iva, pd.descuento_1, pd.pvp,
                            pd.subtotal, pd.total
                        FROM pedido_detalle pd
                        WHERE pd.pedido_id = ?
                        ORDER BY pd.codigo_interno, pd.pedido_detalle_id
                    """, (pedido_id,))
                    tiene_comentario = False
                    tiene_campos_modificados = False
        
        detalles = []
        for row in cursor.fetchall():
            pedido_detalle_id = str(row[0])
            
            # Obtener distribuciones por tienda para este detalle
            tiendas_distribucion = self.obtener_distribuciones_tienda(cursor, pedido_detalle_id)
            
            # Construir detalle
            detalle_dict = self.construir_detalle_desde_row(
                row, tiene_comentario, tiene_campos_modificados, tiendas_distribucion
            )
            
            detalles.append(detalle_dict)
        
        return detalles
