"""
Repositorio para gestionar la tabla archivo_plantilla.

Esta tabla almacena referencias a archivos Excel originales guardados
en el storage centralizado (MinIO/S3).
"""

import logging
from typing import Optional, Dict, Any, List

from src.utils.timezone import ahora_naive

logger = logging.getLogger(__name__)

_CAMPO_TAMANO_BYTES = "tamaño_bytes"


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
        tamano_bytes: int,
        subido_por: str,
        content_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ) -> int:
        """
        Registra una nueva referencia de archivo en la base de datos.

        Args:
            pedido_id: ID del pedido asociado
            nombre_original: Nombre original del archivo
            storage_path: Ruta del archivo en el storage (MinIO/S3)
            tamano_bytes: Tamaño del archivo en bytes
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
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                pedido_id,
                nombre_original,
                storage_path,
                content_type,
                tamano_bytes,
                subido_por,
                ahora_naive(),
            ))
            
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("No se obtuvo el ID del archivo registrado")
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
            _CAMPO_TAMANO_BYTES: row[5],
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
            _CAMPO_TAMANO_BYTES: row[5],
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
                    descargas = COALESCE(descargas, 0) + 1,
                    ultima_descarga = ?,
                    ultimo_descargador = ?
                WHERE archivo_id = ? AND activo = 1
            """, (ahora_naive(), descargado_por, archivo_id))

            if cursor.rowcount == 0:
                logger.warning(
                    "⚠️ No se registró descarga: archivo_id=%s no existe o está inactivo",
                    archivo_id
                )
                self.conn.rollback()
                return False
            
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
    
    @staticmethod
    def _mapear_fila_archivo(row) -> Dict[str, Any]:
        """Mapea una fila de archivo_plantilla (+ numero_pedido de pedido) a dict --
        mismo shape para listar_por_usuario y listar_todos."""
        return {
            "archivo_id": row[0],
            "pedido_id": row[1],
            "nombre_original": row[2],
            "storage_path": row[3],
            "content_type": row[4],
            _CAMPO_TAMANO_BYTES: row[5],
            "subido_por": row[6],
            "fecha_subida": row[7].isoformat() if row[7] else None,
            "activo": row[8],
            "descargas": row[9],
            "ultima_descarga": row[10].isoformat() if row[10] else None,
            "ultimo_descargador": row[11],
            "numero_pedido": row[12]
        }

    def _listar_paginado(
        self,
        where_clause: str,
        params_where: List[Any],
        limit: int,
        offset: int
    ) -> Dict[str, Any]:
        """Ejecuta el COUNT + SELECT paginado (OFFSET/FETCH) compartido por listar_por_usuario
        y listar_todos, y arma {"data": [...], "total": N} -- N es el total real de filas que
        cumplen where_clause, no la cantidad devuelta en esta página.

        El COUNT incluye el mismo LEFT JOIN a pedido que el SELECT: where_clause puede filtrar por
        p.numero_pedido (búsqueda), y sin el join ese filtro rompería el COUNT."""
        cursor = self.conn.cursor()

        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM archivo_plantilla a
            LEFT JOIN pedido p ON a.pedido_id = p.pedido_id
            {where_clause}
            """,
            params_where
        )
        total = cursor.fetchone()[0]

        query = f"""
            SELECT
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
            {where_clause}
            ORDER BY a.fecha_subida DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        cursor.execute(query, params_where + [offset, limit])

        archivos = [self._mapear_fila_archivo(row) for row in cursor.fetchall()]

        return {"data": archivos, "total": total}

    @staticmethod
    def _clausula_busqueda(busqueda: Optional[str]) -> tuple[str, List[Any]]:
        """Fragmento SQL + params para filtrar por número de pedido o nombre de archivo --
        compartido por listar_por_usuario y listar_todos. Devuelve ("", []) si no hay texto de
        búsqueda (el caller simplemente no lo agrega). Sobre p.numero_pedido (requiere el LEFT JOIN
        a pedido, ya presente en _listar_paginado) y a.nombre_original; SQL Server usa collation
        case-insensitive por defecto, así que LIKE ya no distingue mayúsculas."""
        texto = (busqueda or "").strip()
        if not texto:
            return "", []
        patron = f"%{texto}%"
        return " AND (p.numero_pedido LIKE ? OR a.nombre_original LIKE ?)", [patron, patron]

    def listar_por_usuario(
        self,
        usuario_id: str,
        limit: int = 50,
        offset: int = 0,
        solo_activos: bool = True,
        busqueda: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Lista los archivos subidos por un usuario, paginado.

        Args:
            usuario_id: ID/nombre del usuario
            limit: Cantidad máxima de resultados de esta página
            offset: Cantidad de filas a saltar (paginación)
            solo_activos: Si True, solo retorna archivos activos
            busqueda: Filtra por número de pedido o nombre de archivo (substring, sin distinguir
                mayúsculas), aplicado en la base de datos -- no solo en la página actual.

        Returns:
            {"data": [...], "total": N} -- N es el total real (todas las páginas), no len(data).
        """
        where_clause = "WHERE a.subido_por = ?"
        params_where: List[Any] = [usuario_id]
        if solo_activos:
            where_clause += " AND a.activo = 1"
        clausula_busqueda, params_busqueda = self._clausula_busqueda(busqueda)
        where_clause += clausula_busqueda
        params_where += params_busqueda

        return self._listar_paginado(where_clause, params_where, limit, offset)

    def listar_todos(
        self,
        limit: int = 50,
        offset: int = 0,
        solo_activos: bool = True,
        busqueda: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Lista todos los archivos subidos (sin filtrar por usuario), paginado.

        Usado por usuarios con permiso odcsap.view que necesitan ver
        los archivos subidos por otros usuarios (ej: Mabel Trading).

        Args:
            limit: Cantidad máxima de resultados de esta página
            offset: Cantidad de filas a saltar (paginación)
            solo_activos: Si True, solo retorna archivos activos
            busqueda: Filtra por número de pedido o nombre de archivo (substring, sin distinguir
                mayúsculas), aplicado en la base de datos -- no solo en la página actual.

        Returns:
            {"data": [...], "total": N} -- N es el total real (todas las páginas), no len(data).
        """
        where_clause = "WHERE 1=1"
        params_where: List[Any] = []
        if solo_activos:
            where_clause += " AND a.activo = 1"
        clausula_busqueda, params_busqueda = self._clausula_busqueda(busqueda)
        where_clause += clausula_busqueda
        params_where += params_busqueda

        return self._listar_paginado(where_clause, params_where, limit, offset)

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
