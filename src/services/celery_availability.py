"""
Disponibilidad de workers Celery vía heartbeat en Redis.

Reemplaza el chequeo anterior (celery_app.control.inspect().ping(), un broadcast
por el canal de control de Celery a todos los workers) que resultó flaky en
producción: el ping no siempre respeta su propio timeout, y bajo contención de
hilos (pings compitiendo con hilos abandonados de intentos previos) devolvía
falsos negativos con workers sanos. Incidente 2026-08-27: una carga de plantilla
cayó al fallback síncrono por un falso negativo de ese ping (Celery estaba sano y
procesando otras tareas en ese mismo momento), el procesamiento síncrono tardó
117s por saturación de SAP, y el frontend ya había cortado por su timeout de 60s
mostrando "tiempo de espera agotado" mientras el backend seguía trabajando.

El worker Celery escribe un heartbeat en Redis cada CELERY_HEARTBEAT_INTERVALO_SEGUNDOS
(tarea periódica de Celery Beat, ver src/tasks/celery_worker_heartbeat.py, encolada en
la misma cola 'celery' que usan las cargas de plantilla y el proceso completo SAP: si
ningún worker la consume, la clave expira sola). Este módulo solo hace un GET simple y
rápido de esa clave -- sin hilos, sin fan-out/fan-in a workers, sin condiciones de carrera.
"""
import logging

from src.database.services.proceso_estado_service import get_redis_client

logger = logging.getLogger(__name__)

HEARTBEAT_REDIS_KEY = "mba3:celery:worker-heartbeat"

# Escrita por celery_reconciliar_transferencias.reconciliar_transferencias_pendientes
# al completar exitosamente, con TTL = RECONCILIAR_ST_MARGEN_COLCHON_HORAS. Leída por
# el chequeo de abajo (reconciliacion_st_al_dia), invocado en CADA corrida (diaria y
# semanal, ver celery_reconciliar_transferencias._verificar_salud_diaria) -- dentro
# de la MISMA tarea, no en una separada: el problema que vigila no es urgente, y
# corriendo todos los días la latencia de detección queda acotada de todas formas.
RECONCILIAR_ST_LAST_RUN_REDIS_KEY = "mba3:reconciliar-st:last-run"


def celery_worker_available() -> bool:
    """
    True si un worker Celery escribió su heartbeat en los últimos
    CELERY_HEARTBEAT_TTL_SEGUNDOS. False si no hay heartbeat vigente (no hay
    worker sano consumiendo la cola) o si Redis no responde -- ante cualquier
    duda se prioriza el flujo síncrono, igual que el mecanismo anterior.

    Llamada síncrona y bloqueante (redis-py): invocar vía asyncio.to_thread
    desde código async para no congelar el event loop si Redis responde lento.
    """
    try:
        return bool(get_redis_client().exists(HEARTBEAT_REDIS_KEY))
    except Exception as e:
        logger.warning(f"No se pudo verificar heartbeat de Celery en Redis: {e}")
        return False


def reconciliacion_st_al_dia() -> bool:
    """
    True si la reconciliación automática de ST (celery_reconciliar_transferencias.
    reconciliar_transferencias_pendientes) completó exitosamente dentro del margen
    esperado (RECONCILIAR_ST_MARGEN_COLCHON_HORAS). False si el margen venció --
    señal de que la corrida diaria dejó de ejecutarse o de terminar (Celery Beat
    caído, excepción no manejada), NO de que SAP esté fallando -- eso ya se reporta
    aparte, vía el correo de escalamiento a técnicos por OC.

    Ante un error de Redis en el chequeo mismo se asume True: no tiene sentido
    generar una alerta de "la tarea no corrió" por un problema transitorio del
    propio chequeo, no de la tarea que se está verificando.
    """
    try:
        return bool(get_redis_client().exists(RECONCILIAR_ST_LAST_RUN_REDIS_KEY))
    except Exception as e:
        logger.warning(f"No se pudo verificar la última corrida de reconciliación ST: {e}")
        return True
