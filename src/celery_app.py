"""
Configuración de Celery para proceso automático AISLADO.

Este proceso corre en paralelo a FastAPI sin compartir recursos.
Usa Celery Beat para ejecutar la migración automática periódicamente.

Características:
- Proceso separado del servidor FastAPI
- No compite por recursos con el proceso manual
- Reintentos automáticos en caso de error
- Monitoreable con Flower

Comandos de ejecución:
- Worker: celery -A src.celery_app worker --loglevel=info --pool=solo
- Beat:   celery -A src.celery_app beat --loglevel=info
- Flower: celery -A src.celery_app flower (opcional, para monitoreo)
"""

import logging
from celery import Celery
from celery.schedules import crontab
from kombu import Queue
from celery.signals import worker_process_init, worker_process_shutdown, beat_init, worker_ready

# Importar configuración centralizada desde config.py
# Toda la configuración se maneja en un solo lugar: src/config.py
from src.config import (
    REDIS_URL,
    ENABLE_AUTO_MIGRATE,
    AUTO_MIGRATE_INTERVAL_MINUTES,
    ENABLE_SYNC_PRODUCTOS_AUTOMATICA,
    SYNC_PRODUCTOS_HOUR,
    SYNC_PRODUCTOS_MINUTE,
    ENABLE_RECONCILIACION_ST_AUTOMATICA,
    RECONCILIAR_ST_INTERVALO_MINUTOS,
)

logger = logging.getLogger(__name__)

# Crear app Celery
celery_app = Celery(
    'mba3_auto_migrate',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        'src.tasks.celery_auto_migrate',
        'src.tasks.celery_sync_productos',
        'src.tasks.celery_cruce_productos',
        'src.tasks.celery_plantilla_upload',
        'src.tasks.celery_proceso_sap',
        'src.tasks.celery_reconciliar_transferencias',
    ]
)

# Configuración de Celery
celery_app.conf.update(
    # Zona horaria
    timezone='America/Bogota',
    enable_utc=True,
    
    # Serialización (usar JSON para compatibilidad)
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    
    # Programación de tareas (Celery Beat). Auto-migrate solo si ENABLE_AUTO_MIGRATE=true (legacy)
    beat_schedule={
        **({
            'auto-migrate-periodic': {
                'task': 'src.tasks.celery_auto_migrate.execute_auto_migration',
                'schedule': float(AUTO_MIGRATE_INTERVAL_MINUTES * 60),
                'options': {'expires': 60.0, 'queue': 'maintenance'},
            }
        } if ENABLE_AUTO_MIGRATE else {}),
        # Sync nocturna de maestros deshabilitada por defecto (2026-07): la
        # homologacion masiva concluyo y el cruce de productos se sincroniza
        # manualmente desde la UI. Reactivar con ENABLE_SYNC_PRODUCTOS_AUTOMATICA=true
        # (ver src/config.py y docs/INTEGRACION_SAP.md). La tarea y sus endpoints
        # manuales siguen operativos; solo se quita la programacion de Beat.
        **({
            'sync-productos-maestro': {
                'task': 'src.tasks.celery_sync_productos.sync_productos_maestro',
                'schedule': crontab(hour=SYNC_PRODUCTOS_HOUR, minute=SYNC_PRODUCTOS_MINUTE),  # type: ignore[arg-type] # Diario a las 3:00 AM - crontab acepta enteros aunque los stubs indiquen str
                'options': {
                    'queue': 'maintenance',
                    'expires': 300.0,  # Expira si no se ejecuta en 5 minutos
                }
            }
        } if ENABLE_SYNC_PRODUCTOS_AUTOMATICA else {}),
        **({
            'reconciliar-transferencias-pendientes': {
                'task': 'src.tasks.celery_reconciliar_transferencias.reconciliar_transferencias_pendientes',
                'schedule': float(RECONCILIAR_ST_INTERVALO_MINUTOS * 60),
                'options': {'queue': 'maintenance', 'expires': 240.0},
            }
        } if ENABLE_RECONCILIACION_ST_AUTOMATICA else {}),
    },

    # Mantener cargas interactivas en la cola por defecto y mover tareas
    # programadas/largas a maintenance para que no bloqueen plantillas.
    task_default_queue='celery',
    # Declarar ambas colas para que el worker las consuma aunque se lance sin -Q
    # (deploy sin Docker, systemd, celery a mano). Sin esto, un worker sin -Q solo
    # consume la cola por defecto y las tareas de Beat quedan huerfanas en Redis
    # (incidente prod 2026-07: 5,318 tareas acumuladas en 'maintenance').
    # El -Q del CLI, si se pasa, tiene prioridad sobre esta lista.
    task_queues=(
        Queue('celery'),
        Queue('maintenance'),
    ),
    task_routes={
        'src.tasks.celery_auto_migrate.execute_auto_migration': {'queue': 'maintenance'},
        'src.tasks.celery_sync_productos.sync_productos_maestro': {'queue': 'maintenance'},
        'src.tasks.celery_reconciliar_transferencias.reconciliar_transferencias_pendientes': {'queue': 'maintenance'},
    },
    
    # CRÍTICO: Configuración de workers para prevenir acumulación de recursos
    worker_prefetch_multiplier=1,  # Solo tomar 1 tarea a la vez
    worker_max_tasks_per_child=20,  # Reiniciar worker después de 20 tareas (previene memory leaks)
    # Tareas I/O-bound contra SAP/SQL Server: el default (1 hijo por nucleo, ej. 8)
    # sobra y ademas presiona a SAP en paralelo. Pico realista: 2 interactivas
    # (plantillas/cruce/redistribucion) + 1 programada. El --concurrency del CLI,
    # si se pasa, tiene prioridad. Con --pool=solo (Windows dev) se ignora.
    worker_concurrency=3,
    
    # Pool: usar 'solo' en Windows, 'prefork' en Linux
    # En Windows, el pool por defecto puede causar problemas
    # Se configura en el comando: --pool=solo
    
    # Timeouts
    task_time_limit=600,  # 10 minutos máximo por tarea
    task_soft_time_limit=540,  # Aviso después de 9 minutos
    
    # Confirmación de tareas
    task_acks_late=True,  # Confirmar solo después de completar (si falla, se puede reintentar)
    task_reject_on_worker_lost=True,  # Reintentar si el worker se cae
    
    # Resultados
    result_expires=3600,  # Mantener resultados 1 hora
    result_persistent=True,  # Persistir resultados en Redis
    
    # Tracking
    task_track_started=True,  # Registrar cuando inicia una tarea
    task_send_sent_event=True,  # Enviar eventos de tareas
    
    # Configuración adicional para prevenir problemas
    worker_disable_rate_limits=False,
    task_ignore_result=False,  # Guardar resultados para poder consultarlos
)


@worker_process_init.connect
def init_worker(**kwargs):
    """
    Se ejecuta cuando inicia un worker de Celery.
    
    Útil para inicializar recursos específicos del worker.
    """
    import os
    # Mismo formato/archivos que FastAPI (api.log, errors.log) para diagnóstico en producción.
    from src.logging_config import setup_logging
    setup_logging()
    logger.info("=" * 70)
    logger.info("🔧 Iniciando worker Celery")
    logger.info(f"   PID: {os.getpid()}")
    if ENABLE_AUTO_MIGRATE:
        logger.info(f"   Intervalo de migración automática: cada {AUTO_MIGRATE_INTERVAL_MINUTES} minutos")
    else:
        logger.info("   Migración automática: DESHABILITADA (ENABLE_AUTO_MIGRATE=false)")
    logger.info("   ⚠️ Este proceso está AISLADO de FastAPI")
    logger.info("   ⚠️ No compite por recursos con el proceso manual")
    logger.info("=" * 70)


@worker_process_shutdown.connect
def shutdown_worker(**kwargs):
    """
    Se ejecuta cuando termina un worker de Celery.
    
    Útil para limpiar recursos antes de cerrar.
    """
    logger.info("=" * 70)
    logger.info("🛑 Cerrando worker Celery")
    logger.info("   Limpiando recursos...")
    logger.info("=" * 70)


@beat_init.connect
def init_beat(**kwargs):
    """
    Se ejecuta cuando inicia Celery Beat.
    
    Celery Beat es el scheduler que programa las tareas periódicas.
    """
    logger.info("=" * 70)
    logger.info("⏰ Iniciando Celery Beat (scheduler)")
    if ENABLE_AUTO_MIGRATE:
        logger.info(f"   Programación: migración automática cada {AUTO_MIGRATE_INTERVAL_MINUTES} minutos")
    else:
        logger.info("   Migración automática: DESHABILITADA (legacy)")
    logger.info("   Las tareas se encolarán en Redis y serán ejecutadas por los workers")
    logger.info("=" * 70)


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    """
    Se ejecuta cuando el worker está listo. Solo ejecuta migración automática inicial si ENABLE_AUTO_MIGRATE=true.
    """
    import os
    logger.info("=" * 70)
    logger.info("🚀 Worker listo")
    logger.info(f"   PID: {os.getpid()}")
    if ENABLE_AUTO_MIGRATE:
        logger.info("   Migración automática inicial programada (iniciará en 3 segundos)")
        logger.info(f"   Próxima ejecución: cada {AUTO_MIGRATE_INTERVAL_MINUTES} minutos")
        from src.tasks.celery_auto_migrate import execute_auto_migration
        execute_auto_migration.apply_async(countdown=3)
    else:
        logger.info("   Migración automática: DESHABILITADA (legacy)")
    logger.info("=" * 70)


# Log de inicialización
logger.info("✅ Celery configurado correctamente")
logger.info(f"   Broker: {REDIS_URL}")
logger.info(f"   Backend: {REDIS_URL}")
logger.info(f"   Auto-migrate: {'cada ' + str(AUTO_MIGRATE_INTERVAL_MINUTES) + ' min' if ENABLE_AUTO_MIGRATE else 'deshabilitado (legacy)'}")
