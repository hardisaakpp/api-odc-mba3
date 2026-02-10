"""
Repositorio para gestionar la tabla archivo_plantilla.

Esta tabla almacena referencias a archivos Excel originales guardados
en el storage centralizado (MinIO/S3).
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ArchivoPlantillaRepository:
    """
    Repositorio para operaciones CRUD sobre la tabla archivo_plantilla.
    
    Métodos principales:
    - crear: Registra una nueva referencia de archivo
    - obtener_por_pedido_id: Obtiene el archivo asociado a un pedido
    - obtener_por_storage_path: Obtiene archivo por su ruta en storage
    - registrar_descarga: Actualiza contador y fecha de descarga
    - eliminar: Marca el archivo como inactivo (soft delete)
    """
    
    def __init__(self, connection):
        """
        Inicializa el repositorio con una conexión a la base de datos.
        
        Args:
            connection: Conexión pyodbc a SQL Server
        """
        self.conn = connection
    
    def crear(
        self,
        pedido_id: str,  # UNIQUEIDENTIFIER (GUID) como string
        nombre_original: str,
        storage_path: str,
        tamaño_bytes: int,
        subido_por: str,
        content_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ) -> int:
        """
        Registra una nueva referencia de archivo en la base de datos.
        
        Args:
            pedido_id: ID del pedido asociado
            nombre_original: Nombre original del archivo
            storage_path: Ruta del archivo en el storage (MinIO/S3)
            tamaño_bytes: Tamaño del archivo en bytes
            subido_por: ID/nombre del usuario que subió el archivo
            content_type: Tipo MIME del archivo
            
        Returns:
            ID del registro creado (archivo_id)
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO archivo_plantilla (
                    pedido_id,
                    nombre_original,
                    storage_path,
                    content_type,
                    tamaño_bytes,
                    subido_por,
                    fecha_subida,
                    activo
                )
                OUTPUT INSERTED.archivo_id
                VALUES (?, ?, ?, ?, ?, ?, GETDATE(), 1)
            """, (
                pedido_id,
                nombre_original,
                storage_path,
                content_type,
                tamaño_bytes,
                subido_por
            ))
            
            row = cursor.fetchone()
            if not row:
                raise Exception("No se obtuvo el ID del archivo registrado")
            archivo_id: int = row[0]
            
            self.conn.commit()
            
            logger.info(
                f"✅ Archivo registrado en BD: archivo_id={archivo_id}, "
                f"pedido_id={pedido_id}, storage_path={storage_path}"
            )
            
            return archivo_id
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al registrar archivo: {e}")
            raise
    
    def obtener_por_pedido_id(self, pedido_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el archivo activo asociado a un pedido.
        
        Si hay múltiples archivos para el mismo pedido, retorna el más reciente.
        
        Args:
            pedido_id: ID del pedido
            
        Returns:
            Dict con información del archivo o None si no existe
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT TOP 1
                archivo_id,
                pedido_id,
                nombre_original,
                storage_path,
                content_type,
                tamaño_bytes,
                subido_por,
                fecha_subida,
                activo,
                descargas,
                ultima_descarga,
                ultimo_descargador
            FROM archivo_plantilla
            WHERE pedido_id = ? AND activo = 1
            ORDER BY fecha_subida DESC
        """, (pedido_id,))
        
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return {
            "archivo_id": row[0],
            "pedido_id": row[1],
            "nombre_original": row[2],
            "storage_path": row[3],
            "content_type": row[4],
            "tamaño_bytes": row[5],
            "subido_por": row[6],
            "fecha_subida": row[7].isoformat() if row[7] else None,
            "activo": row[8],
            "descargas": row[9],
            "ultima_descarga": row[10].isoformat() if row[10] else None,
            "ultimo_descargador": row[11]
        }
    
    def obtener_por_storage_path(self, storage_path: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un archivo por su ruta en el storage.
        
        Args:
            storage_path: Ruta del archivo en MinIO/S3
            
        Returns:
            Dict con información del archivo o None si no existe
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT
                archivo_id,
                pedido_id,
                nombre_original,
                storage_path,
                content_type,
                tamaño_bytes,
                subido_por,
                fecha_subida,
                activo,
                descargas,
                ultima_descarga,
                ultimo_descargador
            FROM archivo_plantilla
            WHERE storage_path = ?
        """, (storage_path,))
        
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return {
            "archivo_id": row[0],
            "pedido_id": row[1],
            "nombre_original": row[2],
            "storage_path": row[3],
            "content_type": row[4],
            "tamaño_bytes": row[5],
            "subido_por": row[6],
            "fecha_subida": row[7].isoformat() if row[7] else None,
            "activo": row[8],
            "descargas": row[9],
            "ultima_descarga": row[10].isoformat() if row[10] else None,
            "ultimo_descargador": row[11]
        }
    
    def registrar_descarga(
        self,
        archivo_id: int,
        descargado_por: str
    ) -> bool:
        """
        Registra una descarga del archivo.
        
        Incrementa el contador de descargas y actualiza la fecha/usuario
        de última descarga.
        
        Args:
            archivo_id: ID del archivo
            descargado_por: ID/nombre del usuario que descarga
            
        Returns:
            True si se actualizó correctamente
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE archivo_plantilla
                SET 
                    descargas = descargas + 1,
                    ultima_descarga = GETDATE(),
                    ultimo_descargador = ?
                WHERE archivo_id = ?
            """, (descargado_por, archivo_id))
            
            self.conn.commit()
            
            logger.info(f"✅ Descarga registrada: archivo_id={archivo_id}, usuario={descargado_por}")
            return True
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al registrar descarga: {e}")
            raise
    
    def eliminar(self, archivo_id: int) -> bool:
        """
        Marca un archivo como inactivo (soft delete).
        
        No elimina el registro de la BD, solo marca activo=0.
        
        Args:
            archivo_id: ID del archivo
            
        Returns:
            True si se marcó correctamente
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE archivo_plantilla
                SET activo = 0
                WHERE archivo_id = ?
            """, (archivo_id,))
            
            self.conn.commit()
            
            logger.info(f"✅ Archivo marcado como inactivo: archivo_id={archivo_id}")
            return True
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"❌ Error al eliminar archivo: {e}")
            raise
    
    def listar_por_usuario(
        self,
        usuario_id: str,
        limit: int = 50,
        solo_activos: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Lista los archivos subidos por un usuario.
        
        Args:
            usuario_id: ID/nombre del usuario
            limit: Cantidad máxima de resultados
            solo_activos: Si True, solo retorna archivos activos
            
        Returns:
            Lista de diccionarios con información de archivos
        """
        cursor = self.conn.cursor()
        
        query = """
            SELECT TOP (?)
                a.archivo_id,
                a.pedido_id,
                a.nombre_original,
                a.storage_path,
                a.content_type,
                a.tamaño_bytes,
                a.subido_por,
                a.fecha_subida,
                a.activo,
                a.descargas,
                a.ultima_descarga,
                a.ultimo_descargador,
                p.numero_pedido
            FROM archivo_plantilla a
            LEFT JOIN pedido p ON a.pedido_id = p.pedido_id
            WHERE a.subido_por = ?
        """
        
        params = [limit, usuario_id]
        
        if solo_activos:
            query += " AND a.activo = 1"
        
        query += " ORDER BY a.fecha_subida DESC"
        
        cursor.execute(query, params)
        
        archivos = []
        for row in cursor.fetchall():
            archivos.append({
                "archivo_id": row[0],
                "pedido_id": row[1],
                "nombre_original": row[2],
                "storage_path": row[3],
                "content_type": row[4],
                "tamaño_bytes": row[5],
                "subido_por": row[6],
                "fecha_subida": row[7].isoformat() if row[7] else None,
                "activo": row[8],
                "descargas": row[9],
                "ultima_descarga": row[10].isoformat() if row[10] else None,
                "ultimo_descargador": row[11],
                "numero_pedido": row[12]
            })
        
        return archivos
    
    def listar_todos(
        self,
        limit: int = 50,
        solo_activos: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Lista todos los archivos subidos (sin filtrar por usuario).
        
        Usado por usuarios con permiso odcsap.view que necesitan ver
        los archivos subidos por otros usuarios (ej: Mabel Trading).
        
        Args:
            limit: Cantidad máxima de resultados
            solo_activos: Si True, solo retorna archivos activos
            
        Returns:
            Lista de diccionarios con información de archivos
        """
        cursor = self.conn.cursor()
        
        query = """
            SELECT TOP (?)
                a.archivo_id,
                a.pedido_id,
                a.nombre_original,
                a.storage_path,
                a.content_type,
                a.tamaño_bytes,
                a.subido_por,
                a.fecha_subida,
                a.activo,
                a.descargas,
                a.ultima_descarga,
                a.ultimo_descargador,
                p.numero_pedido
            FROM archivo_plantilla a
            LEFT JOIN pedido p ON a.pedido_id = p.pedido_id
            WHERE 1=1
        """
        
        params = [limit]
        
        if solo_activos:
            query += " AND a.activo = 1"
        
        query += " ORDER BY a.fecha_subida DESC"
        
        cursor.execute(query, params)
        
        archivos = []
        for row in cursor.fetchall():
            archivos.append({
                "archivo_id": row[0],
                "pedido_id": row[1],
                "nombre_original": row[2],
                "storage_path": row[3],
                "content_type": row[4],
                "tamaño_bytes": row[5],
                "subido_por": row[6],
                "fecha_subida": row[7].isoformat() if row[7] else None,
                "activo": row[8],
                "descargas": row[9],
                "ultima_descarga": row[10].isoformat() if row[10] else None,
                "ultimo_descargador": row[11],
                "numero_pedido": row[12]
            })
        
        return archivos

    def existe_para_pedido(self, pedido_id: str) -> bool:
        """
        Verifica si existe un archivo activo para un pedido.
        
        Args:
            pedido_id: ID del pedido
            
        Returns:
            True si existe al menos un archivo activo
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*)
            FROM archivo_plantilla
            WHERE pedido_id = ? AND activo = 1
        """, (pedido_id,))
        
        count = cursor.fetchone()[0]
        return count > 0
