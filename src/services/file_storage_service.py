"""
Servicio para almacenamiento de archivos en MinIO/S3.

Este servicio permite guardar y recuperar archivos Excel de plantillas
en un storage centralizado compatible con S3 (MinIO, AWS S3, etc.).

Uso:
    from src.services.file_storage_service import FileStorageService
    
    storage = FileStorageService()
    
    # Guardar archivo
    storage_path = storage.guardar_archivo(
        contenido=file_bytes,
        pedido_id=123,
        nombre_original="plantilla.xlsx",
        usuario_id="cortiz"
    )
    
    # Descargar archivo
    contenido, metadata = storage.descargar_archivo(storage_path)
    
    # Verificar si existe
    existe = storage.archivo_existe(storage_path)
"""

import logging
import io
from datetime import datetime

from src.utils.timezone import ahora_naive
from typing import Optional, Tuple, Dict, Any
from pathlib import PurePosixPath

from src.config import (
    ENABLE_FILE_STORAGE,
    FILE_STORAGE_ENDPOINT,
    FILE_STORAGE_ACCESS_KEY,
    FILE_STORAGE_SECRET_KEY,
    FILE_STORAGE_BUCKET,
    FILE_STORAGE_REGION,
)

logger = logging.getLogger(__name__)


class FileStorageError(Exception):
    """Excepción para errores de storage de archivos."""
    pass


class FileStorageService:
    """
    Servicio para almacenamiento de archivos en MinIO/S3.
    
    Características:
    - Compatible con S3 y MinIO
    - Organiza archivos por pedido_id
    - Almacena metadatos del archivo
    - Soporta URLs firmadas para descarga segura
    """
    
    def __init__(self):
        """Inicializa el cliente de storage."""
        self._client = None
        self._bucket = FILE_STORAGE_BUCKET
        self._initialized = False
        
    def _get_client(self):
        """
        Obtiene el cliente de S3/MinIO (lazy initialization).
        
        Returns:
            Cliente boto3 S3
            
        Raises:
            FileStorageError: Si no se puede inicializar el cliente
        """
        if self._client is not None:
            return self._client
            
        if not ENABLE_FILE_STORAGE:
            raise FileStorageError(
                "El almacenamiento de archivos está deshabilitado. "
                "Configura ENABLE_FILE_STORAGE=true en .env"
            )
        
        try:
            import boto3
            from botocore.config import Config
            from botocore.exceptions import ClientError
            
            # Configuración para MinIO (path style)
            config = Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'}
            )
            
            self._client = boto3.client(
                's3',
                endpoint_url=FILE_STORAGE_ENDPOINT,
                aws_access_key_id=FILE_STORAGE_ACCESS_KEY,
                aws_secret_access_key=FILE_STORAGE_SECRET_KEY,
                region_name=FILE_STORAGE_REGION,
                config=config
            )
            
            # Verificar/crear bucket si no existe
            self._ensure_bucket_exists()
            self._initialized = True
            
            logger.info(f"✅ FileStorageService inicializado - Endpoint: {FILE_STORAGE_ENDPOINT}, Bucket: {self._bucket}")
            return self._client
            
        except ImportError:
            raise FileStorageError(
                "La librería boto3 no está instalada. "
                "Ejecuta: pip install boto3"
            )
        except Exception as e:
            logger.error(f"❌ Error al inicializar FileStorageService: {e}")
            raise FileStorageError(f"No se pudo conectar al storage: {str(e)}")
    
    def _ensure_bucket_exists(self):
        """Crea el bucket si no existe."""
        assert self._client is not None, "El cliente S3 no está inicializado"
        try:
            self._client.head_bucket(Bucket=self._bucket)
            logger.debug(f"Bucket '{self._bucket}' existe")
        except Exception:
            try:
                self._client.create_bucket(Bucket=self._bucket)
                logger.info(f"✅ Bucket '{self._bucket}' creado exitosamente")
            except Exception as e:
                # Si el error es porque ya existe, ignorar
                if "BucketAlreadyOwnedByYou" not in str(e) and "BucketAlreadyExists" not in str(e):
                    logger.warning(f"⚠️ No se pudo crear bucket '{self._bucket}': {e}")
    
    def _generar_storage_path(
        self,
        pedido_id: str,  # UNIQUEIDENTIFIER (GUID)
        nombre_original: str,
        timestamp: Optional[datetime] = None
    ) -> str:
        """
        Genera la ruta de almacenamiento para un archivo.
        
        Estructura: plantillas/{año}/{mes}/{pedido_id}/{timestamp}_{nombre_original}
        
        Args:
            pedido_id: ID del pedido
            nombre_original: Nombre original del archivo
            timestamp: Timestamp opcional (default: ahora)
            
        Returns:
            Ruta de almacenamiento en el bucket
        """
        if timestamp is None:
            timestamp = ahora_naive()
        
        # Sanitizar nombre del archivo
        nombre_seguro = "".join(
            c if c.isalnum() or c in ".-_" else "_"
            for c in nombre_original
        )
        
        # Estructura de carpetas
        año = timestamp.strftime("%Y")
        mes = timestamp.strftime("%m")
        ts = timestamp.strftime("%Y%m%d_%H%M%S")
        
        path = f"plantillas/{año}/{mes}/{pedido_id}/{ts}_{nombre_seguro}"
        return path

    def _generar_storage_path_temporal(
        self,
        process_id: str,
        nombre_original: str,
        timestamp: Optional[datetime] = None
    ) -> str:
        """
        Genera la ruta de almacenamiento temporal para procesamiento async de plantilla.
        Estructura: temp/plantilla-upload/{process_id}/{timestamp}_{nombre_original}
        """
        if timestamp is None:
            timestamp = ahora_naive()
        nombre_seguro = "".join(
            c if c.isalnum() or c in ".-_" else "_"
            for c in nombre_original
        )
        ts = timestamp.strftime("%Y%m%d_%H%M%S")
        return f"temp/plantilla-upload/{process_id}/{ts}_{nombre_seguro}"
    
    def guardar_archivo(
        self,
        contenido: bytes,
        pedido_id: str,  # UNIQUEIDENTIFIER (GUID)
        nombre_original: str,
        usuario_id: str,
        content_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ) -> str:
        """
        Guarda un archivo en el storage.
        
        Args:
            contenido: Contenido del archivo en bytes
            pedido_id: ID del pedido asociado
            nombre_original: Nombre original del archivo
            usuario_id: ID del usuario que sube el archivo
            content_type: Tipo MIME del archivo
            
        Returns:
            Ruta del archivo en el storage (storage_path)
            
        Raises:
            FileStorageError: Si no se puede guardar el archivo
        """
        client = self._get_client()
        
        timestamp = ahora_naive()
        storage_path = self._generar_storage_path(pedido_id, nombre_original, timestamp)
        
        # Metadatos del archivo (solo caracteres ASCII permitidos en S3)
        metadata = {
            "pedido-id": str(pedido_id),
            "nombre-original": nombre_original.encode('ascii', 'replace').decode('ascii'),
            "usuario-id": usuario_id,
            "fecha-subida": timestamp.isoformat(),
            "tamano-bytes": str(len(contenido))  # Sin tilde - S3 solo acepta ASCII
        }
        
        try:
            client.put_object(
                Bucket=self._bucket,
                Key=storage_path,
                Body=contenido,
                ContentType=content_type,
                Metadata=metadata
            )
            
            logger.info(
                f"✅ Archivo guardado en storage: {storage_path} "
                f"(pedido_id={pedido_id}, tamaño={len(contenido)/1024:.1f}KB, usuario={usuario_id})"
            )
            
            return storage_path
            
        except Exception as e:
            logger.error(f"❌ Error al guardar archivo en storage: {e}")
            raise FileStorageError(f"No se pudo guardar el archivo: {str(e)}")

    def guardar_archivo_temporal(
        self,
        contenido: bytes,
        process_id: str,
        nombre_original: str,
        content_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ) -> str:
        """
        Guarda un archivo en storage temporal para procesamiento async (Celery).
        La ruta debe usarse en la tarea Celery; después del procesamiento
        debe eliminarse con eliminar_archivo(storage_path).
        
        Args:
            contenido: Contenido del archivo en bytes
            process_id: ID del proceso (ej. plantilla-abc123)
            nombre_original: Nombre original del archivo
            
        Returns:
            Ruta del archivo en el storage (storage_path)
        """
        client = self._get_client()
        timestamp = ahora_naive()
        storage_path = self._generar_storage_path_temporal(process_id, nombre_original, timestamp)
        metadata = {
            "process-id": str(process_id),
            "nombre-original": nombre_original.encode('ascii', 'replace').decode('ascii'),
            "fecha-subida": timestamp.isoformat(),
            "tamano-bytes": str(len(contenido))
        }
        try:
            client.put_object(
                Bucket=self._bucket,
                Key=storage_path,
                Body=contenido,
                ContentType=content_type,
                Metadata=metadata
            )
            logger.info(
                f"✅ Archivo temporal guardado: {storage_path} "
                f"(process_id={process_id}, tamaño={len(contenido)/1024:.1f}KB)"
            )
            return storage_path
        except Exception as e:
            logger.error(f"❌ Error al guardar archivo temporal en storage: {e}")
            raise FileStorageError(f"No se pudo guardar el archivo temporal: {str(e)}")
    
    def descargar_archivo(self, storage_path: str) -> Tuple[bytes, Dict[str, Any]]:
        """
        Descarga un archivo del storage.
        
        Args:
            storage_path: Ruta del archivo en el storage
            
        Returns:
            Tupla (contenido_bytes, metadatos)
            
        Raises:
            FileStorageError: Si no se puede descargar el archivo
        """
        client = self._get_client()
        
        try:
            response = client.get_object(
                Bucket=self._bucket,
                Key=storage_path
            )
            
            contenido = response['Body'].read()
            metadata = response.get('Metadata', {})
            
            # Agregar información adicional
            metadata['content_type'] = response.get('ContentType', 'application/octet-stream')
            metadata['content_length'] = response.get('ContentLength', len(contenido))
            metadata['last_modified'] = response.get('LastModified')
            
            logger.info(f"✅ Archivo descargado del storage: {storage_path}")
            
            return contenido, metadata
            
        except client.exceptions.NoSuchKey:
            logger.warning(f"⚠️ Archivo no encontrado en storage: {storage_path}")
            raise FileStorageError(f"Archivo no encontrado: {storage_path}")
        except Exception as e:
            logger.error(f"❌ Error al descargar archivo del storage: {e}")
            raise FileStorageError(f"No se pudo descargar el archivo: {str(e)}")
    
    def archivo_existe(self, storage_path: str) -> bool:
        """
        Verifica si un archivo existe en el storage.
        
        Args:
            storage_path: Ruta del archivo en el storage
            
        Returns:
            True si el archivo existe, False en caso contrario
        """
        client = self._get_client()
        
        try:
            client.head_object(
                Bucket=self._bucket,
                Key=storage_path
            )
            return True
        except Exception:
            return False
    
    def eliminar_archivo(self, storage_path: str) -> bool:
        """
        Elimina un archivo del storage.
        
        Args:
            storage_path: Ruta del archivo en el storage
            
        Returns:
            True si se eliminó correctamente
            
        Raises:
            FileStorageError: Si no se puede eliminar el archivo
        """
        client = self._get_client()
        
        try:
            client.delete_object(
                Bucket=self._bucket,
                Key=storage_path
            )
            
            logger.info(f"✅ Archivo eliminado del storage: {storage_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error al eliminar archivo del storage: {e}")
            raise FileStorageError(f"No se pudo eliminar el archivo: {str(e)}")
    
    def generar_url_descarga(
        self,
        storage_path: str,
        expiracion_segundos: int = 3600,
        nombre_descarga: Optional[str] = None
    ) -> str:
        """
        Genera una URL firmada para descarga directa (opcional).
        
        Útil si se quiere permitir descarga directa sin pasar por el backend.
        
        Args:
            storage_path: Ruta del archivo en el storage
            expiracion_segundos: Tiempo de validez de la URL (default: 1 hora)
            nombre_descarga: Nombre sugerido para la descarga
            
        Returns:
            URL firmada para descarga
            
        Raises:
            FileStorageError: Si no se puede generar la URL
        """
        client = self._get_client()
        
        try:
            params = {
                'Bucket': self._bucket,
                'Key': storage_path,
            }
            
            if nombre_descarga:
                params['ResponseContentDisposition'] = f'attachment; filename="{nombre_descarga}"'
            
            url = client.generate_presigned_url(
                'get_object',
                Params=params,
                ExpiresIn=expiracion_segundos
            )
            
            logger.debug(f"URL de descarga generada para: {storage_path} (expira en {expiracion_segundos}s)")
            return url
            
        except Exception as e:
            logger.error(f"❌ Error al generar URL de descarga: {e}")
            raise FileStorageError(f"No se pudo generar la URL de descarga: {str(e)}")
    
    def obtener_metadatos(self, storage_path: str) -> Dict[str, Any]:
        """
        Obtiene los metadatos de un archivo sin descargarlo.
        
        Args:
            storage_path: Ruta del archivo en el storage
            
        Returns:
            Diccionario con metadatos del archivo
            
        Raises:
            FileStorageError: Si no se puede obtener los metadatos
        """
        client = self._get_client()
        
        try:
            response = client.head_object(
                Bucket=self._bucket,
                Key=storage_path
            )
            
            metadata = response.get('Metadata', {})
            metadata['content_type'] = response.get('ContentType', 'application/octet-stream')
            metadata['content_length'] = response.get('ContentLength', 0)
            metadata['last_modified'] = response.get('LastModified')
            metadata['storage_path'] = storage_path
            
            return metadata
            
        except client.exceptions.NoSuchKey:
            raise FileStorageError(f"Archivo no encontrado: {storage_path}")
        except Exception as e:
            logger.error(f"❌ Error al obtener metadatos: {e}")
            raise FileStorageError(f"No se pudo obtener los metadatos: {str(e)}")
    
    def is_enabled(self) -> bool:
        """
        Verifica si el storage está habilitado.
        
        Returns:
            True si ENABLE_FILE_STORAGE=true
        """
        return ENABLE_FILE_STORAGE
    
    def health_check(self) -> Dict[str, Any]:
        """
        Verifica el estado del servicio de storage.
        
        Returns:
            Dict con información del estado
        """
        if not ENABLE_FILE_STORAGE:
            return {
                "status": "disabled",
                "message": "File storage está deshabilitado"
            }
        
        try:
            client = self._get_client()
            
            # Verificar conexión listando buckets
            client.head_bucket(Bucket=self._bucket)
            
            return {
                "status": "healthy",
                "endpoint": FILE_STORAGE_ENDPOINT,
                "bucket": self._bucket,
                "message": "Conexión exitosa"
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "endpoint": FILE_STORAGE_ENDPOINT,
                "bucket": self._bucket,
                "error": str(e)
            }


# Instancia singleton para uso global (opcional)
_storage_instance: Optional[FileStorageService] = None


def get_file_storage() -> FileStorageService:
    """
    Obtiene la instancia del servicio de storage (singleton).
    
    Returns:
        Instancia de FileStorageService
    """
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = FileStorageService()
    return _storage_instance
