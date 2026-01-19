"""
Repositorio para operaciones de pedido en SQL Server.
Modelo: Pedido → PedidoDetalle → PedidoDetalleTienda
ENFOQUE: Solo ingesta y persistencia, sin cálculos ni validaciones de negocio
"""

import logging
import pyodbc
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class PedidoRepository:
    """Repositorio para operaciones de pedido."""
    
    def __init__(self, conn: pyodbc.Connection):
        """
        Inicializa el repositorio con una conexión a SQL Server.
        
        Args:
            conn: Conexión a SQL Server
        """
        self.conn = conn
    
    def insert_cabecera(self, datos_cabecera: Dict[str, Any]) -> str:
        """
        Inserta un registro en pedido.
        
        Args:
            datos_cabecera: Diccionario con datos de cabecera (sin pedido_id)
            
        Returns:
            pedido_id (UUID) generado
            
        Raises:
            Exception: Si falla la inserción
        """
        # Normalizar fechas: convertir date/datetime/Timestamp a string ISO
        from datetime import date
        import pandas as pd
        
        datos_cabecera_normalizado = dict(datos_cabecera)
        
        if "fecha_pedido" in datos_cabecera_normalizado:
            fp = datos_cabecera_normalizado["fecha_pedido"]
            if fp is not None:
                if isinstance(fp, date):
                    datos_cabecera_normalizado["fecha_pedido"] = fp.isoformat() if hasattr(fp, 'isoformat') else str(fp)
                elif isinstance(fp, pd.Timestamp):
                    datos_cabecera_normalizado["fecha_pedido"] = fp.date().isoformat()
        
        if "fecha_entrega" in datos_cabecera_normalizado:
            fe = datos_cabecera_normalizado["fecha_entrega"]
            if fe is not None and not isinstance(fe, str):
                if isinstance(fe, date):
                    datos_cabecera_normalizado["fecha_entrega"] = fe.isoformat() if hasattr(fe, 'isoformat') else str(fe)
                elif isinstance(fe, pd.Timestamp):
                    datos_cabecera_normalizado["fecha_entrega"] = fe.date().isoformat()
        
        cursor = self.conn.cursor()
        
        try:
            # Generar UUID para pedido_id
            cursor.execute("SELECT NEWID()")
            uuid_result = cursor.fetchone()
            if uuid_result is None:
                raise ValueError("No se pudo generar UUID para pedido_id")
            pedido_id = str(uuid_result[0])
            
            # Verificar si existe columna estado (para compatibilidad)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido' 
                AND COLUMN_NAME = 'estado'
            """)
            row = cursor.fetchone()
            tiene_estado = (row[0] if row else 0) > 0
            
            if tiene_estado:
                sql = """
                INSERT INTO pedido (
                    pedido_id,
                    numero_pedido,
                    fecha_pedido,
                    fecha_entrega,
                    forma_pago,
                    odc,
                    proveedor_nombre,
                    comprador_nombre,
                    comprador_codigo,
                    origen_traslado,
                    serie,
                    archivo_nombre,
                    creado_por,
                    estado,
                    creado_en
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
                """
                estado = datos_cabecera_normalizado.get("estado", "PENDIENTE_CONFIRMACION_PROVEEDOR")
                values = (
                    pedido_id,
                    datos_cabecera_normalizado.get("numero_pedido"),
                    datos_cabecera_normalizado.get("fecha_pedido"),
                    datos_cabecera_normalizado.get("fecha_entrega"),
                    datos_cabecera_normalizado.get("forma_pago"),
                    datos_cabecera_normalizado.get("odc"),
                    datos_cabecera_normalizado.get("proveedor_nombre"),
                    datos_cabecera_normalizado.get("comprador_nombre"),
                    datos_cabecera_normalizado.get("comprador_codigo"),
                    datos_cabecera_normalizado.get("origen_traslado"),
                    datos_cabecera_normalizado.get("serie"),
                    datos_cabecera_normalizado.get("archivo_nombre"),
                    datos_cabecera_normalizado.get("creado_por"),
                    estado,
                )
            else:
                sql = """
                INSERT INTO pedido (
                    pedido_id,
                    numero_pedido,
                    fecha_pedido,
                    fecha_entrega,
                    forma_pago,
                    odc,
                    proveedor_nombre,
                    comprador_nombre,
                    comprador_codigo,
                    origen_traslado,
                    serie,
                    archivo_nombre,
                    creado_por,
                    creado_en
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
                """
                values = (
                    pedido_id,
                    datos_cabecera_normalizado.get("numero_pedido"),
                    datos_cabecera_normalizado.get("fecha_pedido"),
                    datos_cabecera_normalizado.get("fecha_entrega"),
                    datos_cabecera_normalizado.get("forma_pago"),
                    datos_cabecera_normalizado.get("odc"),
                    datos_cabecera_normalizado.get("proveedor_nombre"),
                    datos_cabecera_normalizado.get("comprador_nombre"),
                    datos_cabecera_normalizado.get("comprador_codigo"),
                    datos_cabecera_normalizado.get("origen_traslado"),
                    datos_cabecera_normalizado.get("serie"),
                    datos_cabecera_normalizado.get("archivo_nombre"),
                    datos_cabecera_normalizado.get("creado_por"),
                )
            
            cursor.execute(sql, values)
            self.conn.commit()
            
            logger.debug(f"✅ Pedido cabecera insertada: {pedido_id} - Pedido: {datos_cabecera_normalizado.get('numero_pedido')}")
            return pedido_id
            
        except pyodbc.IntegrityError as e:
            self.conn.rollback()
            if "UQ_pedido_numero_pedido" in str(e):
                numero_pedido = datos_cabecera.get('numero_pedido')
                raise ValueError(
                    f"El número de pedido '{numero_pedido}' ya existe en el sistema. "
                    f"No es posible cargar un pedido con un número de pedido duplicado. "
                    f"Por favor, verifica el número de pedido e intenta con un número diferente."
                )
            raise
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar pedido: {e}")
            logger.error(f"   Número pedido: {datos_cabecera.get('numero_pedido')}")
            raise
        finally:
            cursor.close()
    
    def insert_detalle(self, pedido_id: str, datos_detalle: Dict[str, Any]) -> str:
        """
        Inserta un registro en pedido_detalle (artículo).
        
        ENFOQUE: Solo persiste lo que viene, sin recalcular totales.
        
        Args:
            pedido_id: UUID del pedido
            datos_detalle: Diccionario con datos del detalle (sin pedido_detalle_id)
            
        Returns:
            pedido_detalle_id (UUID) generado
        """
        cursor = self.conn.cursor()
        
        try:
            # Generar UUID para pedido_detalle_id
            cursor.execute("SELECT NEWID()")
            uuid_result = cursor.fetchone()
            if uuid_result is None:
                raise ValueError("No se pudo generar UUID para pedido_detalle_id")
            pedido_detalle_id = str(uuid_result[0])
            
            # Verificar si existe la columna comentario antes de incluirla en el INSERT
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido_detalle' 
                AND COLUMN_NAME = 'comentario'
            """)
            result = cursor.fetchone()
            tiene_comentario = result[0] > 0 if result else False
            
            if tiene_comentario:
                sql = """
                INSERT INTO pedido_detalle (
                    pedido_detalle_id,
                    pedido_id,
                    codigo_interno,
                    descripcion_sap,
                    marca,
                    codigo_barras,
                    pack,
                    costo_doc_sin_iva,
                    descuento_1,
                    pvp,
                    subtotal,
                    total,
                    bodega,
                    comentario,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
                """
                
                values = (
                    pedido_detalle_id,
                    pedido_id,
                    datos_detalle.get("codigo_interno"),
                    datos_detalle.get("descripcion_sap"),
                    datos_detalle.get("marca"),
                    datos_detalle.get("codigo_barras"),
                    datos_detalle.get("pack"),
                    datos_detalle.get("costo_doc_sin_iva"),
                    datos_detalle.get("descuento_1"),
                    datos_detalle.get("pvp"),
                    datos_detalle.get("subtotal"),  # Calculado al guardar
                    datos_detalle.get("total"),     # Tal cual viene del Excel
                    datos_detalle.get("bodega"),    # Bodega/almacén del producto
                    datos_detalle.get("comentario"),  # Comentario del artículo
                )
            else:
                # Si no existe la columna comentario, usar el INSERT sin ella (compatibilidad con BD antiguas)
                sql = """
                INSERT INTO pedido_detalle (
                    pedido_detalle_id,
                    pedido_id,
                    codigo_interno,
                    descripcion_sap,
                    marca,
                    codigo_barras,
                    pack,
                    costo_doc_sin_iva,
                    descuento_1,
                    pvp,
                    subtotal,
                    total,
                    bodega,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
                """
                
                values = (
                    pedido_detalle_id,
                    pedido_id,
                    datos_detalle.get("codigo_interno"),
                    datos_detalle.get("descripcion_sap"),
                    datos_detalle.get("marca"),
                    datos_detalle.get("codigo_barras"),
                    datos_detalle.get("pack"),
                    datos_detalle.get("costo_doc_sin_iva"),
                    datos_detalle.get("descuento_1"),
                    datos_detalle.get("pvp"),
                    datos_detalle.get("subtotal"),  # Calculado al guardar
                    datos_detalle.get("total"),     # Tal cual viene del Excel
                    datos_detalle.get("bodega"),    # Bodega/almacén del producto
                )
            
            cursor.execute(sql, values)
            self.conn.commit()
            
            logger.debug(f"✅ Pedido detalle insertado: {pedido_detalle_id}")
            return pedido_detalle_id
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar pedido_detalle: {e}")
            raise
        finally:
            cursor.close()
    
    def insert_detalle_tiendas(
        self,
        pedido_detalle_id: str,
        distribuciones: List[Dict[str, Any]]  # [{"tienda_id": "...", "cantidad": 10, "fila_origen": 2}, ...]
    ) -> int:
        """
        Inserta distribuciones de un detalle por tiendas.
        
        Args:
            pedido_detalle_id: UUID del detalle
            distribuciones: Lista de dicts con tienda_id, cantidad y opcionalmente fila_origen
            
        Returns:
            Número de distribuciones insertadas
        """
        if not distribuciones:
            return 0
        
        cursor = self.conn.cursor()
        inserted_count = 0
        
        try:
            # Verificar si existe columna fila_origen (para compatibilidad)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido_detalle_tienda' 
                AND COLUMN_NAME = 'fila_origen'
            """)
            row = cursor.fetchone()
            tiene_fila_origen = (row[0] if row else 0) > 0
            
            if tiene_fila_origen:
                sql = """
                INSERT INTO pedido_detalle_tienda (
                    id,
                    pedido_detalle_id,
                    tienda_id,
                    cantidad,
                    fila_origen,
                    created_at
                ) VALUES (NEWID(), ?, ?, ?, ?, GETDATE())
                """
            else:
                sql = """
                INSERT INTO pedido_detalle_tienda (
                    id,
                    pedido_detalle_id,
                    tienda_id,
                    cantidad,
                    created_at
                ) VALUES (NEWID(), ?, ?, ?, GETDATE())
                """
            
            for dist in distribuciones:
                try:
                    tienda_id = dist.get("tienda_id")
                    cantidad = dist.get("cantidad")
                    fila_origen = dist.get("fila_origen")
                    
                    if not tienda_id or not cantidad or cantidad <= 0:
                        continue
                    
                    if tiene_fila_origen:
                        cursor.execute(sql, (pedido_detalle_id, tienda_id, cantidad, fila_origen))
                    else:
                        cursor.execute(sql, (pedido_detalle_id, tienda_id, cantidad))
                    inserted_count += 1
                    
                except pyodbc.IntegrityError:
                    # Ya existe la relación, continuar
                    logger.debug(f"⚠️ Relación detalle-tienda ya existe: {pedido_detalle_id} - {dist.get('tienda_id')}")
                    continue
                except Exception as e:
                    logger.warning(f"⚠️ Error al insertar distribución: {e}")
                    continue
            
            self.conn.commit()
            logger.debug(f"✅ {inserted_count} distribuciones insertadas para detalle {pedido_detalle_id}")
            return inserted_count
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al insertar distribuciones: {e}")
            raise
        finally:
            cursor.close()
    
    def get_or_create_tienda(self, codigo: str, nombre: Optional[str] = None) -> str:
        """
        Obtiene el ID de una tienda existente o la crea si no existe.
        
        Args:
            codigo: Código de la tienda
            nombre: Nombre de la tienda (opcional)
            
        Returns:
            tienda_id (UUID)
        """
        cursor = self.conn.cursor()
        
        try:
            # Intentar obtener tienda existente
            cursor.execute("SELECT tienda_id FROM tienda WHERE codigo = ?", (codigo,))
            row = cursor.fetchone()
            
            if row:
                tienda_id = str(row[0])
                logger.debug(f"✅ Tienda existente encontrada: {codigo} ({tienda_id})")
                return tienda_id
            
            # Crear nueva tienda
            cursor.execute("SELECT NEWID()")
            uuid_result = cursor.fetchone()
            if uuid_result is None:
                raise ValueError("No se pudo generar UUID para tienda_id")
            tienda_id = str(uuid_result[0])
            
            sql = """
            INSERT INTO tienda (
                tienda_id,
                codigo,
                nombre,
                activa,
                created_at
            ) VALUES (?, ?, ?, 1, GETDATE())
            """
            
            cursor.execute(sql, (tienda_id, codigo, nombre))
            self.conn.commit()
            
            logger.debug(f"✅ Nueva tienda creada: {codigo} ({tienda_id})")
            return tienda_id
            
        except pyodbc.IntegrityError as e:
            self.conn.rollback()
            # Si falla por unique constraint, intentar obtener de nuevo (race condition)
            cursor.execute("SELECT tienda_id FROM tienda WHERE codigo = ?", (codigo,))
            row = cursor.fetchone()
            if row:
                return str(row[0])
            raise
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al crear/obtener tienda {codigo}: {e}")
            raise
        finally:
            cursor.close()
    
    def get_pedido_completo(self, pedido_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un pedido completo con cabecera, detalles, tiendas y distribuciones.
        
        Args:
            pedido_id: UUID del pedido
            
        Returns:
            Dict con cabecera, detalles (con sus tiendas), o None si no existe
        """
        cursor = self.conn.cursor()
        
        try:
            # Verificar si existe columna estado
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido' 
                AND COLUMN_NAME = 'estado'
            """)
            row_check = cursor.fetchone()
            tiene_estado = (row_check[0] if row_check else 0) > 0
            
            # Obtener cabecera
            if tiene_estado:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, estado, creado_en
                    FROM pedido
                    WHERE pedido_id = ?
                """, (pedido_id,))
            else:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, creado_en
                    FROM pedido
                    WHERE pedido_id = ?
                """, (pedido_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            # Construir cabecera
            if tiene_estado:
                cabecera = {
                    "pedido_id": str(row[0]),
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "odc": row[5],
                    "proveedor_nombre": row[6],
                    "comprador_nombre": row[7],
                    "comprador_codigo": row[8],
                    "origen_traslado": row[9],
                    "serie": row[10],
                    "archivo_nombre": row[11],
                    "creado_por": row[12],
                    "estado": row[13],
                    "creado_en": row[14].isoformat() if row[14] else None,
                }
            else:
                cabecera = {
                    "pedido_id": str(row[0]),
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "odc": row[5],
                    "proveedor_nombre": row[6],
                    "comprador_nombre": row[7],
                    "comprador_codigo": row[8],
                    "origen_traslado": row[9],
                    "serie": row[10],
                    "archivo_nombre": row[11],
                    "creado_por": row[12],
                    "creado_en": row[13].isoformat() if row[13] else None,
                }
            
            # Obtener detalles con sus distribuciones
            # Nota: comentario y campos de modificación manual pueden no existir en BD antigua, se maneja con try/except
            try:
                cursor.execute("""
                    SELECT 
                        pd.pedido_detalle_id,
                        pd.codigo_interno, pd.descripcion_sap, pd.marca, pd.codigo_barras,
                        pd.pack, pd.costo_doc_sin_iva, pd.descuento_1, pd.pvp,
                        pd.subtotal, pd.total, pd.bodega, pd.comentario,
                        ISNULL(pd.costo_modificado_manual, 0) AS costo_modificado_manual,
                        ISNULL(pd.total_modificado_manual, 0) AS total_modificado_manual,
                        ISNULL(pd.comentario_modificado_manual, 0) AS comentario_modificado_manual
                    FROM pedido_detalle pd
                    WHERE pd.pedido_id = ?
                    ORDER BY pd.created_at
                """, (pedido_id,))
                tiene_comentario = True
                tiene_campos_modificados = True
            except Exception as e:
                # Si algún campo no existe, intentar sin ellos
                try:
                    cursor.execute("""
                        SELECT 
                            pd.pedido_detalle_id,
                            pd.codigo_interno, pd.descripcion_sap, pd.marca, pd.codigo_barras,
                            pd.pack, pd.costo_doc_sin_iva, pd.descuento_1, pd.pvp,
                            pd.subtotal, pd.total, pd.bodega, pd.comentario
                        FROM pedido_detalle pd
                        WHERE pd.pedido_id = ?
                        ORDER BY pd.created_at
                    """, (pedido_id,))
                    tiene_comentario = True
                    tiene_campos_modificados = False
                except Exception:
                    # Si el campo comentario no existe, usar consulta sin él
                    cursor.execute("""
                        SELECT 
                            pd.pedido_detalle_id,
                            pd.codigo_interno, pd.descripcion_sap, pd.marca, pd.codigo_barras,
                            pd.pack, pd.costo_doc_sin_iva, pd.descuento_1, pd.pvp,
                            pd.subtotal, pd.total, pd.bodega
                        FROM pedido_detalle pd
                        WHERE pd.pedido_id = ?
                        ORDER BY pd.created_at
                    """, (pedido_id,))
                    tiene_comentario = False
                    tiene_campos_modificados = False
            
            detalles = []
            for row in cursor.fetchall():
                pedido_detalle_id = str(row[0])
                
                # Obtener distribuciones por tienda para este detalle
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
                    tiendas_distribucion.append({
                        "tienda_id": str(dist_row[1]),
                        "codigo": dist_row[2],
                        "nombre": dist_row[3],
                        "cantidad": dist_row[0],
                    })
                
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
                    "subtotal": float(row[9]) if row[9] else None,  # Tal cual se guardó
                    "total": float(row[10]) if row[10] else None,   # Tal cual se guardó
                    "bodega": int(row[11]) if row[11] else None,    # Bodega/almacén
                    "tiendas": tiendas_distribucion,
                }
                
                # Agregar comentario si existe en la consulta
                if tiene_comentario and len(row) > 12:
                    detalle_dict["comentario"] = row[12] if row[12] else None
                else:
                    detalle_dict["comentario"] = None
                
                # Agregar campos de modificación manual si existen en la consulta
                if tiene_campos_modificados and len(row) > 15:
                    detalle_dict["costo_modificado_manual"] = bool(row[13])
                    detalle_dict["total_modificado_manual"] = bool(row[14])
                    detalle_dict["comentario_modificado_manual"] = bool(row[15])
                else:
                    # Si los campos no existen en BD antigua, devolver False por defecto
                    detalle_dict["costo_modificado_manual"] = False
                    detalle_dict["total_modificado_manual"] = False
                    detalle_dict["comentario_modificado_manual"] = False
                
                detalles.append(detalle_dict)
            
            return {
                "cabecera": cabecera,
                "detalles": detalles
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener pedido completo: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_pedido_completo_por_numero(self, numero_pedido: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un pedido completo con cabecera, detalles, tiendas y distribuciones por número de pedido.
        
        Args:
            numero_pedido: Número de pedido (business key)
            
        Returns:
            Dict con cabecera, detalles (con sus tiendas), o None si no existe
        """
        cursor = self.conn.cursor()
        
        try:
            # Verificar si existe columna estado
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido' 
                AND COLUMN_NAME = 'estado'
            """)
            row_check = cursor.fetchone()
            tiene_estado = (row_check[0] if row_check else 0) > 0
            
            # Obtener cabecera por numero_pedido
            if tiene_estado:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, estado, creado_en
                    FROM pedido
                    WHERE numero_pedido = ?
                """, (numero_pedido,))
            else:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, creado_en
                    FROM pedido
                    WHERE numero_pedido = ?
                """, (numero_pedido,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            pedido_id = str(row[0])
            
            # Construir cabecera
            if tiene_estado:
                cabecera = {
                    "pedido_id": pedido_id,
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "odc": row[5],
                    "proveedor_nombre": row[6],
                    "comprador_nombre": row[7],
                    "comprador_codigo": row[8],
                    "origen_traslado": row[9],
                    "serie": row[10],
                    "archivo_nombre": row[11],
                    "creado_por": row[12],
                    "estado": row[13],
                    "creado_en": row[14].isoformat() if row[14] else None,
                }
            else:
                cabecera = {
                    "pedido_id": pedido_id,
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "odc": row[5],
                    "proveedor_nombre": row[6],
                    "comprador_nombre": row[7],
                    "comprador_codigo": row[8],
                    "origen_traslado": row[9],
                    "serie": row[10],
                    "archivo_nombre": row[11],
                    "creado_por": row[12],
                    "creado_en": row[13].isoformat() if row[13] else None,
                }
            
            # Obtener detalles con sus distribuciones (usando pedido_id obtenido)
            # Nota: comentario y campos de modificación manual pueden no existir en BD antigua, se maneja con try/except
            try:
                cursor.execute("""
                    SELECT 
                        pd.pedido_detalle_id,
                        pd.codigo_interno, pd.descripcion_sap, pd.marca, pd.codigo_barras,
                        pd.pack, pd.costo_doc_sin_iva, pd.descuento_1, pd.pvp,
                        pd.subtotal, pd.total, pd.bodega, pd.comentario,
                        ISNULL(pd.costo_modificado_manual, 0) AS costo_modificado_manual,
                        ISNULL(pd.total_modificado_manual, 0) AS total_modificado_manual,
                        ISNULL(pd.comentario_modificado_manual, 0) AS comentario_modificado_manual
                    FROM pedido_detalle pd
                    WHERE pd.pedido_id = ?
                    ORDER BY pd.created_at
                """, (pedido_id,))
                tiene_comentario = True
                tiene_campos_modificados = True
            except Exception as e:
                # Si algún campo no existe, intentar sin ellos
                try:
                    cursor.execute("""
                        SELECT 
                            pd.pedido_detalle_id,
                            pd.codigo_interno, pd.descripcion_sap, pd.marca, pd.codigo_barras,
                            pd.pack, pd.costo_doc_sin_iva, pd.descuento_1, pd.pvp,
                            pd.subtotal, pd.total, pd.bodega, pd.comentario
                        FROM pedido_detalle pd
                        WHERE pd.pedido_id = ?
                        ORDER BY pd.created_at
                    """, (pedido_id,))
                    tiene_comentario = True
                    tiene_campos_modificados = False
                except Exception:
                    # Si el campo comentario no existe, usar consulta sin él
                    cursor.execute("""
                        SELECT 
                            pd.pedido_detalle_id,
                            pd.codigo_interno, pd.descripcion_sap, pd.marca, pd.codigo_barras,
                            pd.pack, pd.costo_doc_sin_iva, pd.descuento_1, pd.pvp,
                            pd.subtotal, pd.total, pd.bodega
                        FROM pedido_detalle pd
                        WHERE pd.pedido_id = ?
                        ORDER BY pd.created_at
                    """, (pedido_id,))
                    tiene_comentario = False
                    tiene_campos_modificados = False
            
            detalles = []
            for row in cursor.fetchall():
                pedido_detalle_id = str(row[0])
                
                # Obtener distribuciones por tienda para este detalle
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
                    tiendas_distribucion.append({
                        "tienda_id": str(dist_row[1]),
                        "codigo": dist_row[2],
                        "nombre": dist_row[3],
                        "cantidad": dist_row[0],
                    })
                
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
                    "subtotal": float(row[9]) if row[9] else None,  # Tal cual se guardó
                    "total": float(row[10]) if row[10] else None,   # Tal cual se guardó
                    "bodega": int(row[11]) if row[11] else None,    # Bodega/almacén
                    "tiendas": tiendas_distribucion,
                }
                
                # Agregar comentario si existe en la consulta
                # IMPORTANTE: Verificar que el campo existe y tiene valor
                if tiene_comentario:
                    if len(row) > 12:
                        detalle_dict["comentario"] = row[12] if row[12] else None
                    else:
                        detalle_dict["comentario"] = None
                else:
                    detalle_dict["comentario"] = None
                
                # Agregar campos de modificación manual si existen en la consulta
                if tiene_campos_modificados and len(row) > 15:
                    detalle_dict["costo_modificado_manual"] = bool(row[13])
                    detalle_dict["total_modificado_manual"] = bool(row[14])
                    detalle_dict["comentario_modificado_manual"] = bool(row[15])
                else:
                    # Si los campos no existen en BD antigua, devolver False por defecto
                    detalle_dict["costo_modificado_manual"] = False
                    detalle_dict["total_modificado_manual"] = False
                    detalle_dict["comentario_modificado_manual"] = False
                
                detalles.append(detalle_dict)
            
            return {
                "cabecera": cabecera,
                "detalles": detalles
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener pedido completo por número: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def update_estado(self, pedido_id: str, estado: str) -> bool:
        """
        Actualiza el estado de un pedido.
        
        Args:
            pedido_id: UUID del pedido
            estado: Nuevo estado (ej: 'PENDIENTE_CONFIRMACION_PROVEEDOR', 'CONFIRMADO_PROVEEDOR', etc.)
            
        Returns:
            True si se actualizó correctamente, False si no existe el pedido o no hay columna estado
        """
        cursor = self.conn.cursor()
        
        try:
            # Verificar si existe columna estado
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido' 
                AND COLUMN_NAME = 'estado'
            """)
            row = cursor.fetchone()
            tiene_estado = (row[0] if row else 0) > 0
            
            if not tiene_estado:
                logger.warning("⚠️ Columna 'estado' no existe en tabla pedido. Ejecute el script add_estado_pedido.sql")
                return False
            
            cursor.execute("""
                UPDATE pedido 
                SET estado = ?
                WHERE pedido_id = ?
            """, (estado, pedido_id))
            
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.debug(f"✅ Estado actualizado para pedido {pedido_id}: {estado}")
                return True
            else:
                logger.warning(f"⚠️ No se encontró pedido con ID: {pedido_id}")
                return False
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar estado del pedido: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def update_cabecera(self, pedido_id: str, datos_cabecera: Dict[str, Any]) -> bool:
        """
        Actualiza la cabecera de un pedido.
        
        Si algún campo en datos_cabecera es None, se preserva el valor existente.
        No se puede modificar: pedido_id, numero_pedido (business key), creado_por, creado_en.
        
        Args:
            pedido_id: UUID del pedido
            datos_cabecera: Diccionario con datos actualizados (sin pedido_id)
            
        Returns:
            True si se actualizó correctamente, False si no existe el pedido
            
        Raises:
            Exception: Si falla la actualización
        """
        cursor = self.conn.cursor()
        
        try:
            # Verificar si existe columna estado
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido' 
                AND COLUMN_NAME = 'estado'
            """)
            row = cursor.fetchone()
            tiene_estado = (row[0] if row else 0) > 0
            
            # Obtener valores existentes
            if tiene_estado:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, estado
                    FROM pedido
                    WHERE pedido_id = ?
                """, (pedido_id,))
            else:
                cursor.execute("""
                    SELECT 
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por
                    FROM pedido
                    WHERE pedido_id = ?
                """, (pedido_id,))
            
            row = cursor.fetchone()
            if not row:
                logger.warning(f"⚠️ No se encontró pedido para actualizar: {pedido_id}")
                return False
            
            # Construir diccionario con valores existentes
            existing = {
                "fecha_pedido": row[2].isoformat() if row[2] else None,
                "fecha_entrega": row[3],
                "forma_pago": row[4],
                "odc": row[5],
                "proveedor_nombre": row[6],
                "comprador_nombre": row[7],
                "comprador_codigo": row[8],
                "origen_traslado": row[9],
                "serie": row[10],
                "archivo_nombre": row[11],
            }
            if tiene_estado:
                existing["estado"] = row[13]
            
            # Fusionar datos: usar nuevo valor si existe y no es None, sino usar existente
            merged = {}
            for key in existing.keys():
                new_value = datos_cabecera.get(key)
                if new_value is not None:
                    merged[key] = new_value
                else:
                    merged[key] = existing[key]
            
            # Normalizar fechas
            from datetime import date
            if "fecha_pedido" in merged and merged["fecha_pedido"] is not None:
                fp = merged["fecha_pedido"]
                if isinstance(fp, date):
                    merged["fecha_pedido"] = fp.isoformat()
                elif isinstance(fp, str):
                    # Ya es string ISO, mantenerlo
                    pass
            
            # SQL para actualizar
            if tiene_estado:
                sql = """
                UPDATE pedido SET
                    fecha_pedido = ?,
                    fecha_entrega = ?,
                    forma_pago = ?,
                    odc = ?,
                    proveedor_nombre = ?,
                    comprador_nombre = ?,
                    comprador_codigo = ?,
                    origen_traslado = ?,
                    serie = ?,
                    estado = ?
                WHERE pedido_id = ?
                """
                values = (
                    merged.get("fecha_pedido"),
                    merged.get("fecha_entrega"),
                    merged.get("forma_pago"),
                    merged.get("odc"),
                    merged.get("proveedor_nombre"),
                    merged.get("comprador_nombre"),
                    merged.get("comprador_codigo"),
                    merged.get("origen_traslado"),
                    merged.get("serie"),
                    merged.get("estado"),
                    pedido_id,
                )
            else:
                sql = """
                UPDATE pedido SET
                    fecha_pedido = ?,
                    fecha_entrega = ?,
                    forma_pago = ?,
                    odc = ?,
                    proveedor_nombre = ?,
                    comprador_nombre = ?,
                    comprador_codigo = ?,
                    origen_traslado = ?,
                    serie = ?
                WHERE pedido_id = ?
                """
                values = (
                    merged.get("fecha_pedido"),
                    merged.get("fecha_entrega"),
                    merged.get("forma_pago"),
                    merged.get("odc"),
                    merged.get("proveedor_nombre"),
                    merged.get("comprador_nombre"),
                    merged.get("comprador_codigo"),
                    merged.get("origen_traslado"),
                    merged.get("serie"),
                    pedido_id,
                )
            
            cursor.execute(sql, values)
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.debug(f"✅ Pedido cabecera actualizada: {pedido_id}")
                return True
            else:
                logger.warning(f"⚠️ No se encontró pedido para actualizar: {pedido_id}")
                return False
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar cabecera del pedido: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def update_costo_detalle(
        self,
        pedido_detalle_id: str,
        nuevo_costo: float,
        modificado_por: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Actualiza el costo unitario de un detalle de pedido.
        
        Args:
            pedido_detalle_id: UUID del detalle del pedido
            nuevo_costo: Nuevo valor del costo unitario (DECIMAL)
            
        Returns:
            Dict con información de la actualización:
            {
                "success": bool,
                "pedido_detalle_id": str,
                "costo_anterior": float | None,
                "costo_nuevo": float,
                "total_actualizado": float | None,
                "mensaje": str
            }
            
        Raises:
            Exception: Si falla la actualización
        """
        cursor = self.conn.cursor()
        
        try:
            # 1. Obtener el costo anterior
            cursor.execute("""
                SELECT costo_doc_sin_iva, pedido_id
                FROM pedido_detalle
                WHERE pedido_detalle_id = ?
            """, (pedido_detalle_id,))
            
            row = cursor.fetchone()
            if not row:
                return {
                    "success": False,
                    "pedido_detalle_id": pedido_detalle_id,
                    "costo_anterior": None,
                    "costo_nuevo": float(nuevo_costo),
                    "mensaje": f"No se encontró el detalle del pedido con ID: {pedido_detalle_id}"
                }
            
            costo_anterior = row[0]
            pedido_id = row[1]
            
            # Convertir valores Decimal a float para serialización JSON
            costo_anterior_float = float(costo_anterior) if costo_anterior is not None else None
            
            # 2. Actualizar el costo con campos de auditoría y marcar como modificado manualmente
            set_clauses = [
                "costo_doc_sin_iva = ?",
                "updated_at = GETDATE()",
                "costo_modificado_manual = 1"  # Marcar que fue modificado manualmente
            ]
            values: List[Any] = [nuevo_costo]
            
            if modificado_por:
                set_clauses.append("modificado_por = ?")
                values.append(modificado_por)
            
            values.append(pedido_detalle_id)
            
            cursor.execute(f"""
                UPDATE pedido_detalle
                SET {', '.join(set_clauses)}
                WHERE pedido_detalle_id = ?
            """, values)
            
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                # IMPORTANTE: El COSTO UNIT. es completamente independiente
                # NO se calcula ni modifica SUBTOTAL, TOTAL ni ninguna otra columna
                # Solo se guarda el valor modificado del costo
                
                logger.info(f"✅ Costo actualizado para pedido_detalle {pedido_detalle_id}")
                logger.info(f"   - Costo anterior: {costo_anterior_float}")
                logger.info(f"   - Costo nuevo: {nuevo_costo}")
                logger.info(f"   - NOTA: SUBTOTAL y TOTAL no se modifican (COSTO UNIT. es independiente)")
                
                return {
                    "success": True,
                    "pedido_detalle_id": pedido_detalle_id,
                    "costo_anterior": costo_anterior_float,
                    "costo_nuevo": float(nuevo_costo),
                    "mensaje": f"Costo actualizado correctamente"
                }
            else:
                return {
                    "success": False,
                    "pedido_detalle_id": pedido_detalle_id,
                    "costo_anterior": costo_anterior_float,
                    "costo_nuevo": float(nuevo_costo),
                    "mensaje": "No se pudo actualizar el costo (0 filas afectadas)"
                }
                
        except Exception as e:
            logger.error(f"❌ Error al actualizar costo de pedido_detalle: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def update_total_detalle(
        self,
        pedido_detalle_id: str,
        nuevo_total: float,
        modificado_por: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Actualiza el total de un detalle de pedido y recalcula el costo unitario.
        
        Args:
            pedido_detalle_id: UUID del detalle del pedido
            nuevo_total: Nuevo valor del total (DECIMAL)
            
        Returns:
            Dict con información de la actualización:
            {
                "success": bool,
                "pedido_detalle_id": str,
                "total_anterior": float | None,
                "total_nuevo": float,
                "costo_actualizado": float | None,
                "mensaje": str
            }
            
        Raises:
            Exception: Si falla la actualización
        """
        cursor = self.conn.cursor()
        
        try:
            # 1. Obtener el total anterior, costo actual y cantidad
            cursor.execute("""
                SELECT total, costo_doc_sin_iva, pedido_id
                FROM pedido_detalle
                WHERE pedido_detalle_id = ?
            """, (pedido_detalle_id,))
            
            row = cursor.fetchone()
            if not row:
                return {
                    "success": False,
                    "pedido_detalle_id": pedido_detalle_id,
                    "total_anterior": None,
                    "total_nuevo": nuevo_total,
                    "costo_actualizado": None,
                    "mensaje": f"No se encontró el detalle del pedido con ID: {pedido_detalle_id}"
                }
            
            total_anterior = row[0]
            costo_anterior = row[1]
            pedido_id = row[2]
            
            # Convertir valores Decimal a float para serialización JSON
            total_anterior_float = float(total_anterior) if total_anterior is not None else None
            costo_anterior_float = float(costo_anterior) if costo_anterior is not None else None
            
            # 2. Actualizar SOLO el total (NO recalcular el costo ni el subtotal)
            # NOTA: El costo y subtotal NO se modifican, solo el total
            set_clauses = [
                "total = ?",
                "updated_at = GETDATE()",
                "total_modificado_manual = 1"  # Marcar que fue modificado manualmente
            ]
            values: List[Any] = [nuevo_total]
            
            if modificado_por:
                set_clauses.append("modificado_por = ?")
                values.append(modificado_por)
            
            values.append(pedido_detalle_id)
            
            cursor.execute(f"""
                UPDATE pedido_detalle
                SET {', '.join(set_clauses)}
                WHERE pedido_detalle_id = ?
            """, values)
            
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.info(f"✅ Total actualizado para pedido_detalle {pedido_detalle_id}")
                logger.info(f"   - Total anterior: {total_anterior_float}")
                logger.info(f"   - Total nuevo: {nuevo_total}")
                logger.info(f"   - Costo (sin cambios): {costo_anterior_float}")
                
                return {
                    "success": True,
                    "pedido_detalle_id": pedido_detalle_id,
                    "total_anterior": total_anterior_float,
                    "total_nuevo": float(nuevo_total),
                    "costo_actualizado": costo_anterior_float,  # El costo NO cambia
                    "mensaje": f"Total actualizado correctamente"
                }
            else:
                return {
                    "success": False,
                    "pedido_detalle_id": pedido_detalle_id,
                    "total_anterior": total_anterior_float,
                    "total_nuevo": float(nuevo_total),
                    "costo_actualizado": costo_anterior_float,
                    "mensaje": "No se pudo actualizar el total (0 filas afectadas)"
                }
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar total de pedido_detalle: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def update_comentario_detalle(
        self,
        pedido_detalle_id: str,
        nuevo_comentario: Optional[str],
        modificado_por: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Actualiza el comentario de un detalle de pedido.
        
        Args:
            pedido_detalle_id: UUID del detalle del pedido
            nuevo_comentario: Nuevo comentario (puede ser None para limpiar)
            
        Returns:
            Dict con información de la actualización:
            {
                "success": bool,
                "pedido_detalle_id": str,
                "comentario_anterior": str | None,
                "comentario_nuevo": str | None,
                "mensaje": str
            }
            
        Raises:
            Exception: Si falla la actualización
        """
        cursor = self.conn.cursor()
        
        try:
            # 1. Obtener el comentario anterior
            cursor.execute("""
                SELECT comentario
                FROM pedido_detalle
                WHERE pedido_detalle_id = ?
            """, (pedido_detalle_id,))
            
            row = cursor.fetchone()
            if not row:
                return {
                    "success": False,
                    "pedido_detalle_id": pedido_detalle_id,
                    "comentario_anterior": None,
                    "comentario_nuevo": nuevo_comentario,
                    "mensaje": f"No se encontró el detalle del pedido con ID: {pedido_detalle_id}"
                }
            
            comentario_anterior = row[0]
            
            # Normalizar: convertir None a None explícitamente, y strings vacíos a None
            comentario_anterior_str = comentario_anterior if comentario_anterior else None
            nuevo_comentario_str = nuevo_comentario.strip() if nuevo_comentario and nuevo_comentario.strip() else None
            
            # 2. Actualizar el comentario en la base de datos con campos de auditoría
            # Marcar como modificado manualmente solo si el comentario no es None o vacío
            set_clauses = ["comentario = ?", "updated_at = GETDATE()"]
            if nuevo_comentario_str:
                set_clauses.append("comentario_modificado_manual = 1")  # Marcar que fue modificado manualmente
            else:
                # Si se limpia el comentario, mantener el flag como está (no resetearlo)
                # Esto permite rastrear que alguna vez fue modificado
                pass
            
            values = [nuevo_comentario_str]
            
            if modificado_por:
                set_clauses.append("modificado_por = ?")
                values.append(modificado_por)
            
            values.append(pedido_detalle_id)
            
            cursor.execute(f"""
                UPDATE pedido_detalle
                SET {', '.join(set_clauses)}
                WHERE pedido_detalle_id = ?
            """, values)
            
            rows_affected = cursor.rowcount
            self.conn.commit()
            
            if rows_affected > 0:
                logger.info(f"✅ Comentario actualizado para pedido_detalle {pedido_detalle_id}")
                logger.info(f"   - Comentario anterior: {comentario_anterior_str}")
                logger.info(f"   - Comentario nuevo: {nuevo_comentario_str}")
                
                return {
                    "success": True,
                    "pedido_detalle_id": pedido_detalle_id,
                    "comentario_anterior": comentario_anterior_str,
                    "comentario_nuevo": nuevo_comentario_str,
                    "mensaje": "Comentario actualizado correctamente"
                }
            else:
                return {
                    "success": False,
                    "pedido_detalle_id": pedido_detalle_id,
                    "comentario_anterior": comentario_anterior_str,
                    "comentario_nuevo": nuevo_comentario_str,
                    "mensaje": "No se pudo actualizar el comentario (0 filas afectadas)"
                }
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al actualizar comentario de pedido_detalle: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def validar_tiendas_existen(
        self,
        codigos_tiendas: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Valida si las tiendas existen y están activas.
        
        Args:
            codigos_tiendas: Lista de códigos de tiendas a validar
            
        Returns:
            Dict con formato:
            {
                "codigo_tienda": {
                    "existe": bool,
                    "activa": bool,
                    "tienda_id": str (si existe)
                }
            }
        """
        if not codigos_tiendas:
            return {}
        
        cursor = self.conn.cursor()
        resultado = {}
        
        try:
            # Buscar todas las tiendas de una vez
            placeholders = ','.join('?' * len(codigos_tiendas))
            cursor.execute(f"""
                SELECT tienda_id, codigo, activa
                FROM tienda
                WHERE codigo IN ({placeholders})
            """, codigos_tiendas)
            
            # Inicializar todas como no encontradas
            for codigo in codigos_tiendas:
                resultado[codigo.upper()] = {
                    "existe": False,
                    "activa": False,
                    "tienda_id": None
                }
            
            # Marcar las encontradas
            for row in cursor.fetchall():
                tienda_id = str(row[0])
                codigo = str(row[1]).upper()
                activa = bool(row[2])
                
                if codigo in resultado:
                    resultado[codigo] = {
                        "existe": True,
                        "activa": activa,
                        "tienda_id": tienda_id
                    }
            
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error al validar tiendas: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_by_estado(self, estado: str) -> List[Dict[str, Any]]:
        """
        Obtiene todos los pedidos con un estado específico.
        
        Args:
            estado: Estado a filtrar
            
        Returns:
            Lista de diccionarios con datos de pedidos
        """
        cursor = self.conn.cursor()
        
        try:
            # Verificar si existe columna estado
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido' 
                AND COLUMN_NAME = 'estado'
            """)
            row = cursor.fetchone()
            tiene_estado = (row[0] if row else 0) > 0
            
            if not tiene_estado:
                logger.warning("⚠️ Columna 'estado' no existe en tabla pedido")
                return []
            
            cursor.execute("""
                SELECT 
                    pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                    forma_pago, odc, proveedor_nombre, comprador_nombre,
                    comprador_codigo, origen_traslado, serie, archivo_nombre,
                    creado_por, estado, creado_en
                FROM pedido
                WHERE estado = ?
                ORDER BY creado_en DESC
            """, (estado,))
            
            pedidos = []
            for row in cursor.fetchall():
                pedidos.append({
                    "pedido_id": str(row[0]),
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "odc": row[5],
                    "proveedor_nombre": row[6],
                    "comprador_nombre": row[7],
                    "comprador_codigo": row[8],
                    "origen_traslado": row[9],
                    "serie": row[10],
                    "archivo_nombre": row[11],
                    "creado_por": row[12],
                    "estado": row[13],
                    "creado_en": row[14].isoformat() if row[14] else None,
                })
            
            return pedidos
            
        except Exception as e:
            logger.error(f"❌ Error al obtener pedidos por estado: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_pedidos_con_filtros(
        self,
        estado: Optional[str] = None,
        fecha_desde: Optional[str] = None,
        fecha_hasta: Optional[str] = None,
        proveedor_nombre: Optional[str] = None,
        numero_pedido: Optional[str] = None,
        creado_por: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Obtiene pedidos con filtros y paginación.
        
        Args:
            estado: Estado del pedido (ej: "PENDIENTE_CONFIRMACION_PROVEEDOR")
            fecha_desde: Fecha desde (YYYY-MM-DD)
            fecha_hasta: Fecha hasta (YYYY-MM-DD)
            proveedor_nombre: Nombre del proveedor (búsqueda parcial)
            numero_pedido: Número de pedido (búsqueda exacta o parcial)
            creado_por: Usuario que creó el pedido
            limit: Límite de registros
            offset: Offset para paginación
        
        Returns:
            Dict con lista de pedidos y metadata:
            {
                "data": [...],
                "total": 150,
                "limit": 50,
                "offset": 0,
                "has_more": true
            }
        """
        cursor = self.conn.cursor()
        
        try:
            # Verificar si existe columna estado
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido' 
                AND COLUMN_NAME = 'estado'
            """)
            row = cursor.fetchone()
            tiene_estado = (row[0] if row else 0) > 0
            
            # Construir WHERE conditions
            where_conditions = []
            params = []
            
            if tiene_estado and estado:
                where_conditions.append("p.estado = ?")
                params.append(estado)
            
            if fecha_desde:
                where_conditions.append("CAST(p.fecha_pedido AS DATE) >= CAST(? AS DATE)")
                params.append(fecha_desde)
            
            if fecha_hasta:
                where_conditions.append("CAST(p.fecha_pedido AS DATE) <= CAST(? AS DATE)")
                params.append(fecha_hasta)
            
            if proveedor_nombre:
                where_conditions.append("p.proveedor_nombre LIKE ?")
                params.append(f"%{proveedor_nombre}%")
            
            if numero_pedido:
                where_conditions.append("p.numero_pedido LIKE ?")
                params.append(f"%{numero_pedido}%")
            
            if creado_por:
                where_conditions.append("p.creado_por = ?")
                params.append(creado_por)
            
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            
            # Query para obtener total
            count_query = f"SELECT COUNT(*) FROM pedido p WHERE {where_clause}"
            cursor.execute(count_query, params)
            result = cursor.fetchone()
            total = result[0] if result else 0
            
            # Query para obtener datos con paginación
            select_fields = """
                p.pedido_id, p.numero_pedido, p.fecha_pedido, p.fecha_entrega,
                p.forma_pago, p.odc, p.proveedor_nombre, p.comprador_nombre,
                p.comprador_codigo, p.origen_traslado, p.serie, p.archivo_nombre,
                p.creado_por, p.creado_en
            """
            
            if tiene_estado:
                select_fields += ", p.estado"
            
            data_query = f"""
                SELECT {select_fields}
                FROM pedido p
                WHERE {where_clause}
                ORDER BY p.creado_en DESC
            """
            
            if limit is not None:
                data_query += f" OFFSET {offset or 0} ROWS FETCH NEXT {limit} ROWS ONLY"
            
            cursor.execute(data_query, params)
            
            pedidos = []
            for row in cursor.fetchall():
                idx = 0
                pedido = {
                    "pedido_id": str(row[idx]),
                    "numero_pedido": row[idx + 1],
                    "fecha_pedido": row[idx + 2].isoformat() if row[idx + 2] else None,
                    "fecha_entrega": row[idx + 3],
                    "forma_pago": row[idx + 4],
                    "odc": row[idx + 5],
                    "proveedor_nombre": row[idx + 6],
                    "comprador_nombre": row[idx + 7],
                    "comprador_codigo": row[idx + 8],
                    "origen_traslado": row[idx + 9],
                    "serie": row[idx + 10],
                    "archivo_nombre": row[idx + 11],
                    "creado_por": row[idx + 12],
                    "creado_en": row[idx + 13].isoformat() if row[idx + 13] else None,
                }
                
                if tiene_estado:
                    pedido["estado"] = row[idx + 14]
                else:
                    pedido["estado"] = None
                
                pedidos.append(pedido)
            
            has_more = (offset or 0) + len(pedidos) < total if limit else False
            
            return {
                "data": pedidos,
                "total": total,
                "limit": limit,
                "offset": offset or 0,
                "has_more": has_more
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener pedidos con filtros: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def existe_numero_pedido(self, numero_pedido: str) -> bool:
        """
        Verifica si un número de pedido ya existe en el sistema.
        
        Args:
            numero_pedido: Número del pedido a verificar
            
        Returns:
            True si el número de pedido ya existe, False si no existe
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM pedido 
                WHERE numero_pedido = ?
            """, (numero_pedido,))
            
            row = cursor.fetchone()
            count = row[0] if row else 0
            
            existe = count > 0
            if existe:
                logger.debug(f"✓ Número de pedido '{numero_pedido}' YA EXISTE en el sistema")
            else:
                logger.debug(f"✓ Número de pedido '{numero_pedido}' disponible (no existe)")
            
            return existe
            
        except Exception as e:
            logger.error(f"❌ Error al verificar existencia de número de pedido '{numero_pedido}': {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def get_ultimo_pedido(self, usuario_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el último pedido cargado por un usuario específico.
        
        Args:
            usuario_id: ID del usuario autenticado (creado_por)
        
        Returns:
            Dict con datos básicos del último pedido del usuario
            o None si el usuario no tiene pedidos
        """
        cursor = self.conn.cursor()
        
        try:
            # Verificar si existe columna estado
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pedido' 
                AND COLUMN_NAME = 'estado'
            """)
            row_check = cursor.fetchone()
            tiene_estado = (row_check[0] if row_check else 0) > 0
            
            # Obtener el último pedido DEL USUARIO
            if tiene_estado:
                cursor.execute("""
                    SELECT TOP 1
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, estado, creado_en
                    FROM pedido
                    WHERE creado_por = ?
                    ORDER BY creado_en DESC
                """, (usuario_id,))
            else:
                cursor.execute("""
                    SELECT TOP 1
                        pedido_id, numero_pedido, fecha_pedido, fecha_entrega,
                        forma_pago, odc, proveedor_nombre, comprador_nombre,
                        comprador_codigo, origen_traslado, serie, archivo_nombre,
                        creado_por, creado_en
                    FROM pedido
                    WHERE creado_por = ?
                    ORDER BY creado_en DESC
                """, (usuario_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            if tiene_estado:
                return {
                    "pedido_id": str(row[0]),
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "odc": row[5],
                    "proveedor_nombre": row[6],
                    "comprador_nombre": row[7],
                    "comprador_codigo": row[8],
                    "origen_traslado": row[9],
                    "serie": row[10],
                    "archivo_nombre": row[11],
                    "creado_por": row[12],
                    "estado": row[13],
                    "creado_en": row[14].isoformat() if row[14] else None,
                }
            else:
                return {
                    "pedido_id": str(row[0]),
                    "numero_pedido": row[1],
                    "fecha_pedido": row[2].isoformat() if row[2] else None,
                    "fecha_entrega": row[3],
                    "forma_pago": row[4],
                    "odc": row[5],
                    "proveedor_nombre": row[6],
                    "comprador_nombre": row[7],
                    "comprador_codigo": row[8],
                    "origen_traslado": row[9],
                    "serie": row[10],
                    "archivo_nombre": row[11],
                    "creado_por": row[12],
                    "creado_en": row[13].isoformat() if row[13] else None,
                }
                
        except Exception as e:
            logger.error(f"❌ Error al obtener último pedido del usuario {usuario_id}: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def guardar_modificaciones_columnas(
        self,
        numero_pedido: str,
        modificaciones: List[Dict[str, str]],
        modificado_por: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Guarda o actualiza modificaciones de columnas para un pedido.
        
        Args:
            numero_pedido: Número del pedido
            modificaciones: Lista de diccionarios con formato:
                [
                    {"pedido_detalle_id": "uuid", "columna_key": "costo_doc_sin_iva"},
                    ...
                ]
            modificado_por: ID del usuario que realiza la modificación (opcional)
        
        Returns:
            Dict con formato:
            {
                "success": bool,
                "numero_pedido": str,
                "modificaciones_guardadas": int,
                "mensaje": str
            }
        """
        cursor = self.conn.cursor()
        
        try:
            # Validar que el pedido existe y obtener su pedido_id
            cursor.execute("""
                SELECT pedido_id
                FROM pedido
                WHERE numero_pedido = ?
            """, (numero_pedido,))
            
            row = cursor.fetchone()
            if not row:
                return {
                    "success": False,
                    "numero_pedido": numero_pedido,
                    "modificaciones_guardadas": 0,
                    "mensaje": f"No se encontró el pedido con número: {numero_pedido}"
                }
            
            pedido_id = str(row[0])
            
            # Validar que las columnas son válidas
            columnas_validas = {'costo_doc_sin_iva', 'total', 'comentario'}
            modificaciones_count = 0
            errores = []
            
            for mod in modificaciones:
                pedido_detalle_id = mod.get('pedido_detalle_id')
                columna_key = mod.get('columna_key')
                
                if not pedido_detalle_id or not columna_key:
                    errores.append(f"Modificación inválida: {mod}")
                    continue
                
                if columna_key not in columnas_validas:
                    errores.append(f"Columna inválida '{columna_key}' para detalle {pedido_detalle_id}")
                    continue
                
                # Verificar que el detalle pertenece al pedido
                cursor.execute("""
                    SELECT pedido_detalle_id
                    FROM pedido_detalle
                    WHERE pedido_detalle_id = ?
                    AND pedido_id = ?
                """, (pedido_detalle_id, pedido_id))
                
                detalle_row = cursor.fetchone()
                if not detalle_row:
                    errores.append(f"Detalle {pedido_detalle_id} no pertenece al pedido {numero_pedido}")
                    continue
                
                # Usar MERGE (UPSERT) para insertar o actualizar
                # Si ya existe una modificación para este detalle+columna, la actualizamos
                # Si no existe, la creamos
                cursor.execute("""
                    MERGE pedido_detalle_modificacion_columna AS target
                    USING (SELECT ? AS pedido_detalle_id, ? AS columna_key, ? AS modificado_por) AS source
                    ON target.pedido_detalle_id = source.pedido_detalle_id 
                    AND target.columna_key = source.columna_key
                    WHEN MATCHED THEN
                        UPDATE SET 
                            modificado_por = source.modificado_por,
                            fecha_modificacion = GETDATE()
                    WHEN NOT MATCHED THEN
                        INSERT (pedido_detalle_id, columna_key, modificado_por, fecha_modificacion)
                        VALUES (source.pedido_detalle_id, source.columna_key, source.modificado_por, GETDATE());
                """, (pedido_detalle_id, columna_key, modificado_por))
                
                modificaciones_count += 1
            
            self.conn.commit()
            
            mensaje = f"Se guardaron {modificaciones_count} modificaciones correctamente"
            if errores:
                mensaje += f". Errores: {len(errores)}"
                logger.warning(f"⚠️ Errores al guardar modificaciones: {errores}")
            
            logger.info(f"✅ Guardadas {modificaciones_count} modificaciones para pedido {numero_pedido}")
            
            return {
                "success": True,
                "numero_pedido": numero_pedido,
                "modificaciones_guardadas": modificaciones_count,
                "mensaje": mensaje,
                "errores": errores if errores else None
            }
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al guardar modificaciones de columnas: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    def obtener_modificaciones_columnas(
        self,
        numero_pedido: str
    ) -> Dict[str, Any]:
        """
        Obtiene las modificaciones de columnas para un pedido.
        
        Args:
            numero_pedido: Número del pedido
        
        Returns:
            Dict con formato:
            {
                "success": bool,
                "numero_pedido": str,
                "modificaciones": [
                    {
                        "pedido_detalle_id": "uuid",
                        "columna_key": "costo_doc_sin_iva",
                        "modificado_por": "usuario@ejemplo.com",
                        "fecha_modificacion": "2025-01-15T10:30:00Z"
                    },
                    ...
                ],
                "mensaje": str
            }
        """
        cursor = self.conn.cursor()
        
        try:
            # Validar que el pedido existe y obtener su pedido_id
            cursor.execute("""
                SELECT pedido_id
                FROM pedido
                WHERE numero_pedido = ?
            """, (numero_pedido,))
            
            row = cursor.fetchone()
            if not row:
                return {
                    "success": False,
                    "numero_pedido": numero_pedido,
                    "modificaciones": [],
                    "mensaje": f"No se encontró el pedido con número: {numero_pedido}"
                }
            
            pedido_id = str(row[0])
            
            # Obtener modificaciones usando JOIN para filtrar por pedido
            cursor.execute("""
                SELECT 
                    m.pedido_detalle_id,
                    m.columna_key,
                    m.modificado_por,
                    m.fecha_modificacion
                FROM pedido_detalle_modificacion_columna m
                INNER JOIN pedido_detalle d ON m.pedido_detalle_id = d.pedido_detalle_id
                WHERE d.pedido_id = ?
                ORDER BY m.fecha_modificacion DESC
            """, (pedido_id,))
            
            rows = cursor.fetchall()
            modificaciones = []
            
            for row in rows:
                fecha_mod = row[3]
                fecha_mod_iso = fecha_mod.isoformat() if fecha_mod else None
                
                modificaciones.append({
                    "pedido_detalle_id": str(row[0]),
                    "columna_key": row[1],
                    "modificado_por": row[2] if row[2] else None,
                    "fecha_modificacion": fecha_mod_iso
                })
            
            logger.info(f"✅ Obtenidas {len(modificaciones)} modificaciones para pedido {numero_pedido}")
            
            return {
                "success": True,
                "numero_pedido": numero_pedido,
                "modificaciones": modificaciones,
                "mensaje": f"Se encontraron {len(modificaciones)} modificaciones"
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener modificaciones de columnas: {e}", exc_info=True)
            raise
        finally:
            cursor.close()


