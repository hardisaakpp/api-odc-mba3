"""
Tarea Celery periódica: heartbeat de disponibilidad de workers.

Cada vez que un worker sano CONSUME y ejecuta esta tarea, escribe un timestamp
en Redis con TTL corto (CELERY_HEARTBEAT_TTL_SEGUNDOS). Si ningún worker está
consumiendo la cola 'celery' (la misma que usan las cargas de plantilla y el
proceso completo SAP), la clave expira sola y
src.services.celery_availability.celery_worker_available() lo detecta como "no
disponible" -- sin necesidad de un ping de broadcast al canal de control (ver
ese módulo para el porqué del cambio).
"""
import logging
import time

from src.celery_app import celery_app
from src.config import CELERY_HEARTBEAT_TTL_SEGUNDOS
from src.database.services.proceso_estado_service import get_redis_client
from src.services.celery_availability import HEARTBEAT_REDIS_KEY

logger = logging.getLogger(__name__)


@celery_app.task(
    name="src.tasks.celery_worker_heartbeat.emitir_heartbeat",
    time_limit=10,
    soft_time_limit=5,
    # Nadie consulta el resultado de esta tarea (a diferencia del resto de tareas
    # del proyecto, que sí lo hacen vía AsyncResult/polling); sin esto, cada
    # ejecución -- una cada CELERY_HEARTBEAT_INTERVALO_SEGUNDOS, para siempre --
    # persistiría una entrada más en el result backend de Redis (result_expires=3600)
    # sin que nada la lea nunca.
    ignore_result=True,
)
def emitir_heartbeat() -> None:
    redis_client = get_redis_client()
    redis_client.setex(HEARTBEAT_REDIS_KEY, CELERY_HEARTBEAT_TTL_SEGUNDOS, str(time.time()))
