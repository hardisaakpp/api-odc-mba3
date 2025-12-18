# 🚀 Quick Start - Celery para Migración Automática

Guía rápida para poner en marcha Celery y eliminar el cuello de botella entre el proceso manual y automático.

## ✅ Paso 1: Instalar Redis

**Windows (usando Chocolatey):**
```powershell
choco install redis-64
redis-server
```

**Verificar instalación:**
```bash
redis-cli ping
# Debe responder: PONG
```

## ✅ Paso 2: Instalar dependencias de Python

```bash
cd C:\Users\cortiz\PycharmProjects\mba3-consultas
pip install -r requirements.txt
```

Esto instalará:
- `celery>=5.3.4` - Sistema de colas
- `redis>=5.0.1` - Broker para Celery
- `flower>=2.0.1` - Dashboard de monitoreo

## ✅ Paso 3: Configurar variables de entorno

Agregar al archivo `.env`:

```bash
# Redis para Celery
REDIS_URL=redis://localhost:6379/0

# Habilitar migración automática
ENABLE_AUTO_MIGRATE=true
AUTO_MIGRATE_INTERVAL_MINUTES=15
MIGRATE_DATE_FILTER_DAYS=365
```

## ✅ Paso 4: Ejecutar los procesos

### Opción A: Usando el script de PowerShell

```powershell
cd C:\Users\cortiz\PycharmProjects\mba3-consultas
.\start_celery.ps1
```

### Opción B: Manual (3 terminales)

**Terminal 1: FastAPI (proceso manual)**
```bash
cd C:\Users\cortiz\PycharmProjects\mba3-consultas
python src/api_server.py
```

**Terminal 2: Celery Worker (proceso automático)**
```bash
cd C:\Users\cortiz\PycharmProjects\mba3-consultas
celery -A src.celery_app worker --loglevel=info --pool=solo

# Nota: Asegúrate de estar en el directorio raíz del proyecto
```

**Terminal 3: Celery Beat (scheduler)**
```bash
cd C:\Users\cortiz\PycharmProjects\mba3-consultas
celery -A src.celery_app beat --loglevel=info
```

**Terminal 4 (opcional): Flower (dashboard)**
```bash
cd C:\Users\cortiz\PycharmProjects\mba3-consultas
celery -A src.celery_app flower
# Abrir: http://localhost:5555
```

## ✅ Paso 5: Verificar que funciona

1. **FastAPI**: http://localhost:8000/health → Debe responder OK
2. **Flower** (opcional): http://localhost:5555 → Debe mostrar dashboard
3. **Logs**: Verificar en las terminales que todo está corriendo

## 📊 ¿Qué cambió?

### ❌ Antes (con asyncio):
- Proceso manual y automático corrían en el mismo proceso
- Competían por recursos (conexiones DB, cliente MBA3)
- El proceso manual se bloqueaba cuando el automático estaba corriendo
- **Cuello de botella**

### ✅ Ahora (con Celery):
- Proceso manual: 100% dedicado a peticiones del usuario
- Proceso automático: 100% aislado en worker separado
- No compiten por recursos
- **Sin cuello de botella**

## 🎯 Resultado

- **Proceso manual** (`/migrar/completo`): Responde instantáneamente siempre
- **Proceso automático** (Celery): Corre cada 15 minutos sin afectar al manual
- **Base de datos**: Context managers previenen conexiones huérfanas
- **Monitoreo**: Flower muestra el estado de las tareas en tiempo real

## 📚 Documentación Completa

Para más detalles, ver: [CELERY_IMPLEMENTATION.md](CELERY_IMPLEMENTATION.md)

## 🐛 Troubleshooting Rápido

**Redis no conecta:**
```bash
redis-cli ping  # Verificar que Redis está corriendo
redis-server    # Si no está corriendo, iniciar
```

**Worker no inicia:**
```bash
# Verificar que estás en el directorio correcto
cd C:\Users\cortiz\PycharmProjects\mba3-consultas

# Verificar que celery está instalado
pip list | grep celery
```

**Proceso manual lento:**
- Verificar que Celery Worker está corriendo
- El proceso manual NO usa Celery, debería ser rápido siempre
- Si es lento, el problema no es Celery

## ⚙️ Configuración

**Cambiar intervalo de migración** (editar `.env`):
```bash
AUTO_MIGRATE_INTERVAL_MINUTES=30  # Cambiar de 15 a 30 minutos
```

**Cambiar filtro de fecha** (editar `.env`):
```bash
MIGRATE_DATE_FILTER_DAYS=180  # Cambiar de 365 a 180 días
```

---

**✅ ¡Listo!** El proceso automático ahora corre en un proceso completamente aislado sin afectar al proceso manual.

