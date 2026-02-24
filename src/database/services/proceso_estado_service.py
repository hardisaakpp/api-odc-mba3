"""
Servicio para gestionar estado de procesos largos usando Redis.
Implementa patrón singleton para el cliente Redis.
"""
import json
import uuid
import logging
import os
from typing import Dict, Any, Optional, cast
from datetime import datetime

from src.utils.timezone import ahora_naive
import redis

logger = logging.getLogger(__name__)

# Singleton para Redis client
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """
    Obtiene o crea el cliente Redis singleton.
    
    Returns:
        Cliente Redis configurado
        
    Raises:
        redis.ConnectionError: Si no se puede conectar a Redis
    """
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        try:
            _redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Test conexión
            _redis_client.ping()
            logger.info("✅ Cliente Redis singleton inicializado")
        except Exception as e:
            logger.error(f"❌ Error conectando a Redis: {e}")
            raise redis.ConnectionError(f"No se pudo conectar a Redis: {e}")
    return _redis_client


class ProcesoEstadoService:
    """
    Gestiona estado de procesos en Redis.
    
    **Política de TTL y validez:**
    
    - **TTL del proceso**: 24 horas (configurable con PROCESO_ESTADO_TTL_HORAS)
    - **TTL del puntero "último completado"**: 15 minutos
    - **Validez para sugerencias**: 15 minutos desde completado
    
    **Invalidación automática:**
    - Un nuevo cruce invalida automáticamente el anterior (nuevo puntero)
    - El puntero expira después de 15 minutos (TTL)
    - Si se sincronizan maestros (MBA3/SAP), se recomienda ejecutar nuevo cruce
    
    **Razón del TTL de 15 minutos:**
    - Balance entre frescura de datos y rendimiento
    - Evita ejecutar cruces innecesarios
    - Los datos de productos cambian lentamente (sincronización diaria)
    """
    
    # TTL configurable (horas)
    TTL_HORAS = int(os.getenv('PROCESO_ESTADO_TTL_HORAS', '24'))
    # TTL del puntero al último completado (15 minutos)
    TTL_ULTIMO_COMPLETADO_SEGUNDOS = 900  # 15 minutos
    
    def __init__(self):
        """Inicializa el servicio con cliente Redis singleton."""
        self.redis_client = get_redis_client()
    
    def _key(self, process_id: str) -> str:
        """
        Devuelve la clave Redis según el tipo de proceso (cruce vs plantilla vs proceso-sap).
        """
        if process_id.startswith("plantilla-"):
            return f"proceso:plantilla:{process_id}"
        if process_id.startswith("proceso-sap-"):
            return f"proceso:sap:{process_id}"
        return f"proceso:cruce:{process_id}"

    def crear_proceso(self, user_id: Optional[str] = None) -> str:
        """
        Crea un nuevo proceso y devuelve su ID.
        
        Args:
            user_id: ID del usuario que inicia el proceso (para auditoría)
            
        Returns:
            ID del proceso creado (formato: cruce-{uuid})
        """
        process_id = f"cruce-{uuid.uuid4().hex[:12]}"
        estado_inicial = {
            "process_id": process_id,
            "status": "processing",  # Estado inicial: "processing" no "iniciando"
            "step": "iniciando",
            "progress": 0,
            "message": "Iniciando cruce de productos...",
            "user_id": user_id,  # Auditoría: quién inició el proceso
            "created_at": ahora_naive().isoformat(),
            "updated_at": ahora_naive().isoformat(),
            "version": 1  # Versión para comparación segura
        }
        self._guardar_estado(process_id, estado_inicial)
        logger.info(f"📝 Proceso creado: {process_id} (usuario: {user_id})")
        return process_id

    def crear_proceso_plantilla(self, user_id: Optional[str] = None) -> str:
        """
        Crea un nuevo proceso de carga de plantilla Excel y devuelve su ID.
        
        Args:
            user_id: ID del usuario que inicia el proceso (para auditoría)
            
        Returns:
            ID del proceso creado (formato: plantilla-{uuid})
        """
        process_id = f"plantilla-{uuid.uuid4().hex[:12]}"
        estado_inicial = {
            "process_id": process_id,
            "status": "processing",
            "step": "iniciando",
            "progress": 0,
            "message": "Plantilla recibida. Procesando en segundo plano...",
            "user_id": user_id,
            "created_at": ahora_naive().isoformat(),
            "updated_at": ahora_naive().isoformat(),
            "version": 1
        }
        self._guardar_estado(process_id, estado_inicial)
        logger.info(f"📝 Proceso plantilla creado: {process_id} (usuario: {user_id})")
        return process_id

    def crear_proceso_sap(self, user_id: Optional[str] = None, numero_pedido: Optional[str] = None) -> str:
        """
        Crea un nuevo proceso de envío ODC a SAP (proceso completo en segundo plano).

        Args:
            user_id: ID del usuario que inicia el proceso (para auditoría)
            numero_pedido: Número de pedido (opcional, para mostrar en estado)

        Returns:
            ID del proceso creado (formato: proceso-sap-{uuid})
        """
        process_id = f"proceso-sap-{uuid.uuid4().hex[:12]}"
        estado_inicial = {
            "process_id": process_id,
            "status": "processing",
            "step": "iniciando",
            "progress": 0,
            "message": "Enviando ODC a SAP en segundo plano...",
            "user_id": user_id,
            "numero_pedido": numero_pedido,
            "created_at": ahora_naive().isoformat(),
            "updated_at": ahora_naive().isoformat(),
            "version": 1,
        }
        self._guardar_estado(process_id, estado_inicial)
        logger.info(f"📝 Proceso SAP creado: {process_id} (usuario: {user_id}, pedido: {numero_pedido})")
        return process_id
    
    def actualizar_progreso(
        self,
        process_id: str,
        step: str,
        progress: int,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        total_items: Optional[int] = None
    ):
        """
        Actualiza el progreso del proceso.
        
        Args:
            process_id: ID del proceso
            step: Paso actual del proceso
            progress: Porcentaje de progreso (0-100)
            message: Mensaje descriptivo
            data: Datos adicionales opcionales
            total_items: Total de items para calcular barra de progreso real
        """
        estado = self._obtener_estado(process_id)
        if not estado:
            logger.warning(f"⚠️ Proceso {process_id} no encontrado al actualizar progreso")
            return
        
        # No resetear progress en error (mantener último progreso)
        nuevo_progress = max(estado.get("progress", 0), progress)
        
        estado.update({
            "step": step,
            "progress": nuevo_progress,
            "message": message,
            "updated_at": ahora_naive().isoformat(),
            "version": estado.get("version", 0) + 1  # Incrementar versión
        })
        
        if data:
            estado["data"] = data
        
        if total_items:
            estado["total_items"] = total_items
        
        self._guardar_estado(process_id, estado)
    
    def completar_proceso(
        self,
        process_id: str,
        resultado: Dict[str, Any]
    ):
        """
        Marca el proceso como completado.
        
        Args:
            process_id: ID del proceso
            resultado: Resultado completo del cruce
        """
        estado = self._obtener_estado(process_id)
        if not estado:
            logger.warning(f"⚠️ Proceso {process_id} no encontrado al completar")
            return
        
        default_message = "Cruce completado exitosamente"
        if process_id.startswith("plantilla-"):
            default_message = "Plantilla procesada exitosamente"
        elif process_id.startswith("proceso-sap-"):
            default_message = "Proceso SAP completado. ODC enviada."
        
        estado.update({
            "status": "completed",
            "step": "completado",
            "progress": 100,
            "message": default_message,
            "resultado": resultado,
            "completed_at": ahora_naive().isoformat(),
            "updated_at": ahora_naive().isoformat(),
            "version": estado.get("version", 0) + 1
        })
        self._guardar_estado(process_id, estado)
        
        # Solo para cruce: guardar puntero al último completado (sugerencias)
        if process_id.startswith("cruce-"):
            try:
                self.redis_client.setex(
                    "proceso:cruce:ultimo_completado",
                    self.TTL_ULTIMO_COMPLETADO_SEGUNDOS,
                    process_id
                )
                logger.debug(f"📌 Puntero actualizado: último_completado → {process_id}")
            except Exception as e:
                logger.warning(f"⚠️ Error guardando puntero último completado: {e}")
        
        logger.info(f"✅ Proceso completado: {process_id}")
    
    def marcar_error(
        self,
        process_id: str,
        error: str,
        error_data: Optional[Dict[str, Any]] = None
    ):
        """
        Marca el proceso como error.

        Args:
            process_id: ID del proceso
            error: Mensaje de error
            error_data: Datos estructurados para el frontend (ej. validacion_sap, sugerencias).
                       Se devuelve en GET resultado para permitir UI de corrección de códigos.
        """
        estado = self._obtener_estado(process_id)
        if not estado:
            logger.warning(f"⚠️ Proceso {process_id} no encontrado al marcar error")
            return

        update: Dict[str, Any] = {
            "status": "error",
            "step": "error",
            "progress": estado.get("progress", 0),  # NO resetear progress
            "message": f"Error: {error}",
            "error": error,
            "error_at": ahora_naive().isoformat(),
            "updated_at": ahora_naive().isoformat(),
            "version": estado.get("version", 0) + 1
        }
        if error_data is not None:
            update["error_data"] = error_data
        estado.update(update)
        self._guardar_estado(process_id, estado)
        logger.error(f"❌ Proceso con error: {process_id} - {error}")
    
    def obtener_estado(self, process_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el estado actual del proceso.
        
        Args:
            process_id: ID del proceso
            
        Returns:
            Estado del proceso o None si no existe
        """
        return self._obtener_estado(process_id)
    
    def obtener_ultimo_completado(self, max_age_minutes: int = 15) -> Optional[Dict[str, Any]]:
        """
        Obtiene el último proceso completado exitosamente.
        
        ✅ AJUSTE 1: Usa puntero O(1) en lugar de keys() O(N)
        
        Busca el proceso más reciente con status="completed"
        y que no sea más antiguo que max_age_minutes.
        
        Args:
            max_age_minutes: Edad máxima del cruce en minutos (default: 15)
                            ⚠️ Debe coincidir con TTL del puntero
        
        Returns:
            Estado del último proceso completado o None si no existe o es muy antiguo
        
        Nota:
            - El puntero tiene TTL de 15 minutos
            - Si el proceso fue completado hace más de 15 min, el puntero expira
            - Un nuevo cruce invalida automáticamente el anterior (nuevo puntero)
        """
        try:
            # ✅ O(1): Leer puntero directamente
            # Con decode_responses=True, get() devuelve str | None
            process_id = cast(Optional[str], self.redis_client.get("proceso:cruce:ultimo_completado"))
            
            if not process_id:
                logger.debug("No hay puntero a último completado")
                return None
            
            # Obtener estado del proceso
            estado = self._obtener_estado(process_id)
            
            if not estado:
                logger.warning(f"⚠️ Proceso {process_id} del puntero no existe")
                return None
            
            # Validar que esté completado
            if estado.get("status") != "completed":
                logger.warning(f"⚠️ Proceso {process_id} no está completado")
                return None
            
            # Validar que tenga resultado
            if "resultado" not in estado:
                logger.warning(f"⚠️ Proceso {process_id} no tiene resultado")
                return None
            
            # Validar edad máxima (doble validación por si acaso)
            completed_at_str = estado.get("completed_at")
            if completed_at_str:
                completed_at = datetime.fromisoformat(completed_at_str)
                edad_minutos = (ahora_naive() - completed_at).total_seconds() / 60
                
                if edad_minutos > max_age_minutes:
                    logger.debug(f"Proceso {process_id} es muy antiguo ({edad_minutos:.1f} min)")
                    return None
            
            return estado
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo último completado: {e}")
            return None
    
    def _obtener_estado(self, process_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene estado desde Redis.
        
        Args:
            process_id: ID del proceso
            
        Returns:
            Estado del proceso o None si no existe
        """
        key = self._key(process_id)
        try:
            # Con decode_responses=True, get() devuelve str | None
            data = cast(Optional[str], self.redis_client.get(key))
            if not data:
                return None
            return json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(f"❌ Error decodificando estado {process_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error obteniendo estado {process_id}: {e}")
            return None
    
    def _guardar_estado(self, process_id: str, estado: Dict[str, Any]):
        """
        Guarda estado en Redis con TTL configurable.
        
        Args:
            process_id: ID del proceso
            estado: Estado a guardar
            
        Raises:
            redis.RedisError: Si hay error guardando en Redis
        """
        key = self._key(process_id)
        ttl_seconds = self.TTL_HORAS * 3600
        try:
            self.redis_client.setex(
                key,
                ttl_seconds,
                json.dumps(estado, default=str)
            )
        except Exception as e:
            logger.error(f"❌ Error guardando estado {process_id}: {e}")
            raise
