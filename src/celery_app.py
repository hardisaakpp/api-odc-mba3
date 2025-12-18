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
import os
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown, beat_init, worker_ready

logger = logging.getLogger(__name__)

# Obtener configuración de Redis desde variables de entorno
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
AUTO_MIGRATE_INTERVAL_MINUTES = int(os.getenv('AUTO_MIGRATE_INTERVAL_MINUTES', '5'))

# Crear app Celery
celery_app = Celery(
    'mba3_auto_migrate',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['src.tasks.celery_auto_migrate']  # Incluir el módulo de tareas
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
    
    # Programación de tarea automática (Celery Beat)
    beat_schedule={
        'auto-migrate-periodic': {
            'task': 'src.tasks.celery_auto_migrate.execute_auto_migration',
            'schedule': float(AUTO_MIGRATE_INTERVAL_MINUTES * 60),  # Convertir minutos a segundos
            'options': {
                'expires': 60.0,  # Expira si no se ejecuta en 60 segundos
            }
        },
    },
    
    # CRÍTICO: Configuración de workers para prevenir acumulación de recursos
    worker_prefetch_multiplier=1,  # Solo tomar 1 tarea a la vez
    worker_max_tasks_per_child=20,  # Reiniciar worker después de 20 tareas (previene memory leaks)
    
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
    logger.info("=" * 70)
    logger.info("🔧 Iniciando worker Celery para migración automática")
    logger.info(f"   PID: {os.getpid()}")
    logger.info(f"   Intervalo de migración: cada {AUTO_MIGRATE_INTERVAL_MINUTES} minutos")
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
    logger.info(f"   Programación: migración automática cada {AUTO_MIGRATE_INTERVAL_MINUTES} minutos")
    logger.info("   Las tareas se encolarán en Redis y serán ejecutadas por los workers")
    logger.info("=" * 70)


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    """
    Se ejecuta cuando el worker está completamente listo y puede recibir tareas.
    
    Ejecuta la migración automática inmediatamente al iniciar para:
    - Ver resultados inmediatos
    - Monitorear funcionamiento desde el inicio
    - Realizar correcciones si es necesario
    
    Después continuará ejecutándose cada N minutos según la programación de Beat.
    """
    import os
    logger.info("=" * 70)
    logger.info("🚀 Worker listo - Ejecutando migración automática inicial...")
    logger.info(f"   PID: {os.getpid()}")
    logger.info(f"   Esta migración consultará MBA3 y guardará en SQL Server")
    logger.info(f"   Próxima ejecución automática: en {AUTO_MIGRATE_INTERVAL_MINUTES} minutos")
    logger.info("=" * 70)
    
    # Importar y ejecutar la tarea inmediatamente
    # countdown=3 da tiempo para que el log se muestre antes de comenzar
    from src.tasks.celery_auto_migrate import execute_auto_migration
    execute_auto_migration.apply_async(countdown=3)
    
    logger.info("✅ Migración automática inicial programada (iniciará en 3 segundos)")


# Log de inicialización
logger.info("✅ Celery configurado correctamente")
logger.info(f"   Broker: {REDIS_URL}")
logger.info(f"   Backend: {REDIS_URL}")
logger.info(f"   Intervalo de migración: {AUTO_MIGRATE_INTERVAL_MINUTES} minutos")

