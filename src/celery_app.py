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
    RECONCILIAR_ST_HORA,
    RECONCILIAR_ST_MINUTO,
    RECONCILIAR_ST_VENTANA_DIAS,
    RECONCILIAR_ST_VENTANA_DIAS_DOMINGO,
    RECONCILIAR_OC_INTERVALO_MINUTOS,
    CELERY_HEARTBEAT_INTERVALO_SEGUNDOS,
    CELERY_HEARTBEAT_TTL_SEGUNDOS,
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
        'src.tasks.celery_reconciliar_ordenes_compra',
        'src.tasks.celery_worker_heartbeat',
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

    # Timeouts de red contra Redis. Sin esto, redis-py espera INDEFINIDAMENTE:
    # si la conexion TCP muere en silencio (caso tipico: port-forward de Docker
    # Desktop/WSL2 que descarta conexiones ociosas), cualquier llamada al broker
    # -- incluido el .delay() que hace la API al encolar -- se cuelga para siempre
    # sin lanzar excepcion. Incidente dev 2026-08-06: la API entera quedo
    # congelada dos veces al subir una plantilla, sin un solo error en el log.
    #   - socket_connect_timeout: corta un connect que no responde.
    #   - socket_timeout: corta una lectura colgada. Debe quedar MUY por encima
    #     del brpop_timeout de kombu (1s) o el worker cortaria su propio bucle
    #     de consumo en cada poll sin tareas.
    #   - socket_keepalive + health_check_interval: redis-py valida la conexion
    #     ociosa antes de reutilizarla, en vez de escribir en un socket muerto.
    broker_transport_options={
        'socket_connect_timeout': 10.0,
        'socket_timeout': 30.0,
        'socket_keepalive': True,
        'health_check_interval': 30,
        'retry_on_timeout': True,
    },
    result_backend_transport_options={
        'socket_connect_timeout': 10.0,
        'socket_timeout': 30.0,
        'socket_keepalive': True,
        'health_check_interval': 30,
        'retry_on_timeout': True,
    },
    # Acota el reintento de publicacion: sin esto un .delay() contra un broker
    # degradado reintenta con backoff mucho mas de lo que el usuario espera.
    task_publish_retry=True,
    task_publish_retry_policy={
        'max_retries': 2,
        'interval_start': 0,
        'interval_step': 0.5,
        'interval_max': 2,
    },
    broker_connection_retry_on_startup=True,

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
            # Lunes a sábado: barrido corto (RECONCILIAR_ST_VENTANA_DIAS, default 2
            # días) -- solo ODCs enviadas recientemente. No mira nada más viejo a
            # propósito (ver conversación 2026-08-28): lo que no se resuelve solo ya
            # escaló a técnicos vía reconciliar_transferencias_pendientes (2 corridas
            # consecutivas), así que no hace falta reintentar indefinidamente.
            'reconciliar-transferencias-pendientes-diaria': {
                'task': 'src.tasks.celery_reconciliar_transferencias.reconciliar_transferencias_pendientes',
                'schedule': crontab(  # type: ignore[arg-type]
                    hour=RECONCILIAR_ST_HORA, minute=RECONCILIAR_ST_MINUTO, day_of_week='mon-sat'
                ),
                'kwargs': {'dias_ventana': RECONCILIAR_ST_VENTANA_DIAS},
                'options': {'queue': 'maintenance', 'expires': 3600.0},
            },
            # Domingo: barrido semanal más amplio (RECONCILIAR_ST_VENTANA_DIAS_DOMINGO,
            # default 7 días) -- alcanza cualquier OC que se le haya "escapado" a los
            # barridos cortos de la semana. También hace de colchón de seguridad: en
            # vez de una tarea aparte corriendo cada hora, esta misma corrida revisa si
            # la reconciliación diaria completó al menos una vez recientemente y avisa
            # por correo si no (ver verificar_salud_diaria en la tarea).
            'reconciliar-transferencias-pendientes-semanal': {
                'task': 'src.tasks.celery_reconciliar_transferencias.reconciliar_transferencias_pendientes',
                'schedule': crontab(  # type: ignore[arg-type]
                    hour=RECONCILIAR_ST_HORA, minute=RECONCILIAR_ST_MINUTO, day_of_week='sun'
                ),
                'kwargs': {'dias_ventana': RECONCILIAR_ST_VENTANA_DIAS_DOMINGO, 'verificar_salud_diaria': True},
                'options': {'queue': 'maintenance', 'expires': 3600.0},
            },
        } if ENABLE_RECONCILIACION_ST_AUTOMATICA else {}),
        # Reconciliación de ODC ENCOLADAS: a diferencia de la de ST, no depende de un
        # flag de encendido/apagado -- es parte de la lógica normal del envío a SAP
        # (cierra el mismo loop que _resolver_job_encolado_previo abre), no una
        # función opcional que un ambiente pueda dejar apagada por descuido.
        'reconciliar-ordenes-compra-pendientes': {
            'task': 'src.tasks.celery_reconciliar_ordenes_compra.reconciliar_ordenes_compra_pendientes',
            'schedule': float(RECONCILIAR_OC_INTERVALO_MINUTOS * 60),
            'options': {'queue': 'maintenance', 'expires': 240.0},
        },
        # Heartbeat de disponibilidad de workers (ver src/services/celery_availability.py).
        # SIEMPRE activo, en la cola 'celery' (la misma que usan las cargas de plantilla y
        # el proceso completo SAP): si ningún worker la consume, el heartbeat expira y
        # celery_worker_available() lo detecta como "no disponible".
        'celery-worker-heartbeat': {
            'task': 'src.tasks.celery_worker_heartbeat.emitir_heartbeat',
            'schedule': float(CELERY_HEARTBEAT_INTERVALO_SEGUNDOS),
            'options': {'queue': 'celery', 'expires': CELERY_HEARTBEAT_TTL_SEGUNDOS},
        },
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


class _SilenciarHeartbeatFilter(logging.Filter):
    """Silencia el ruido de ciclo de vida ('received'/'succeeded'/'Sending due
    task') de la tarea de heartbeat de disponibilidad de workers (ver
    src/tasks/celery_worker_heartbeat.py): se ejecuta cada
    CELERY_HEARTBEAT_INTERVALO_SEGUNDOS para siempre y, a diferencia de las
    demás tareas, nunca falla ni aporta señal una vez confirmado que el
    mecanismo funciona -- serían miles de líneas idénticas por día tapando el
    log real. No afecta logs de ninguna otra tarea.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return "celery_worker_heartbeat.emitir_heartbeat" not in record.getMessage()


for _logger_name in ("celery.worker.strategy", "celery.app.trace", "celery.beat"):
    logging.getLogger(_logger_name).addFilter(_SilenciarHeartbeatFilter())


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
