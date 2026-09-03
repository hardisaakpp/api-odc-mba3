# 🚀 Quick Start - Celery para Migración Automática

Guía rápida para poner en marcha Celery y eliminar el cuello de botella entre el proceso manual y automático.

## ¿Para qué se usa Redis en este proyecto?

- **Celery**: broker y backend (colas de tareas).
- **Procesamiento de plantillas Excel en segundo plano**: upload async sin bloquear la app; estado y resultado en Redis.
- **Proceso completo SAP (Enviar ODC a SAP)**: ejecución en segundo plano; estado y resultado en Redis (mismo patrón que plantillas).
- **Cruce de productos y sugerencias**: estado de procesos (ProcesoEstadoService) y puntero al último resultado.
- **Opcional (legacy)**: migración automática y sincronización de maestros, si se activan en `.env`.

Todo se conecta a **`redis://localhost:6379/0`** (o la URL que pongas en `REDIS_URL`).

---

## ✅ Paso 1: Redis (y resto del backend)

En Windows no viene Redis instalado. **Recomendación para desarrollo: stack Docker con perfil `app`** — levanta Redis, MinIO, API, worker y beat de una vez. Ver [DOCKER_COMPOSE.md](DOCKER_COMPOSE.md) y:

```powershell
.\scripts\docker-app-up.ps1
.\scripts\docker-verify.ps1
```

Dentro del contenedor Celery usa `REDIS_URL=redis://redis:6379/0` (Compose lo define; no hace falta cambiar `.env.develop` para Redis si solo usas el stack `app`).

**Opción A – Solo Redis con Docker Compose de este repo (API/Celery en host):**
```powershell
docker compose up -d
```
Redis en `localhost:6379`. Luego `.\start-all-dev.ps1` o Celery manual en el venv.

**Opción B – Contenedor Redis suelto (legacy):**
```powershell
docker run -d --name redis -p 6379:6379 redis
```
Redis queda en segundo plano en `localhost:6379`. Para parar: `docker stop redis`. Para arrancar de nuevo: `docker start redis`.

**Comprobar Redis:**
```powershell
# Stack compose de este repo (servicio redis)
docker compose exec redis redis-cli ping

# Contenedor suelto llamado "redis"
docker exec -it redis redis-cli ping
```
Debe responder: `PONG`. Con el stack `app`, `.\scripts\docker-verify.ps1` también valida Redis y Celery.

Si obtienes **"port is already allocated"**, ya tienes un Redis en el 6379. Comprueba con `docker ps -a` y usa el contenedor existente.

Si tenías el paquete antiguo de Chocolatey (`redis-64`) y ya usas Docker, puedes desinstalarlo: `choco uninstall redis-64`.

**Opción C – Chocolatey (Redis nativo en Windows):**
```powershell
choco install redis-64
# Ejecutar por ruta completa si no está en PATH, ej: & "C:\ProgramData\chocolatey\lib\redis-64\tools\redis-server.exe"
```

**Opción D – Memurai:**  
[memurai.com](https://www.memurai.com/) — Redis compatible para Windows.

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

# Migración automática (opcional, legacy; por defecto está deshabilitada)
# ENABLE_AUTO_MIGRATE=false   # por defecto: no se programa migración periódica
# Si la activas: ENABLE_AUTO_MIGRATE=true y AUTO_MIGRATE_INTERVAL_MINUTES=15

# Sync nocturna de maestros de productos (deshabilitada por defecto desde 2026-07, ver abajo)
# ENABLE_SYNC_PRODUCTOS_AUTOMATICA=false

# Reconciliación automática de ST pendientes: SIEMPRE activa, sin flag de
# encendido/apagado (mismo criterio que la reconciliación de ODC ENCOLADAS de abajo).
# Corre UNA VEZ AL DÍA (ventana de baja congestión en SAP), con dos horarios según el
# día -- ver tabla abajo. Solo los horarios/ventanas son configurables.
# RECONCILIAR_ST_HORA=23        # 11:00 PM
# RECONCILIAR_ST_MINUTO=0
# RECONCILIAR_ST_VENTANA_DIAS=2          # lunes a sábado: solo OCs enviadas en estos días
# RECONCILIAR_ST_VENTANA_DIAS_DOMINGO=7  # domingo: barrido semanal más amplio
# RECONCILIAR_ST_MARGEN_COLCHON_HORAS=48   # colchón de seguridad, ver abajo
# RECONCILIAR_ST_MARGEN_ANTIGUEDAD_MINUTOS=30   # margen anti-carrera con envío en curso, ver abajo

# Reconciliación automática de ODC ENCOLADAS (HTTP 202 del middleware): SIEMPRE
# activa, sin flag de encendido/apagado. Solo el intervalo es configurable.
# RECONCILIAR_OC_INTERVALO_MINUTOS=5
```

### Tareas programadas (Celery Beat) y sus flags

Todas las tareas de Beat se encolan en la cola `maintenance` (las interactivas disparadas
desde la API usan la cola por defecto `celery`). El worker consume **ambas** colas: están
declaradas en `task_queues` en `src/celery_app.py`, así que aplica aunque se lance sin `-Q`.

> ⚠️ **Lección de producción (2026-07):** el worker corría sin `-Q` y sin `task_queues`
> declaradas, por lo que solo consumía la cola `celery`. Las tareas de Beat se acumularon
> ~18 días en Redis (5,318 mensajes en `maintenance`) sin ejecutarse nunca. Si se cambia
> la topología de colas, verificar con `redis-cli LLEN maintenance` que se mantenga en ~0.

| Tarea | Flag | Default | Frecuencia |
|---|---|---|---|
| `reconciliar_transferencias_pendientes` (diaria) | *(ninguno, siempre activa)* | — | lunes-sábado, `RECONCILIAR_ST_HORA:MINUTO` (11:00 PM), ventana de `RECONCILIAR_ST_VENTANA_DIAS` (2) días + colchón de seguridad |
| `reconciliar_transferencias_pendientes` (semanal) | *(ninguno, siempre activa)* | — | domingo, misma hora, ventana de `RECONCILIAR_ST_VENTANA_DIAS_DOMINGO` (7) días + colchón de seguridad |
| `reconciliar_ordenes_compra_pendientes` | *(ninguno, siempre activa)* | — | cada `RECONCILIAR_OC_INTERVALO_MINUTOS` (5 min) |
| `sync_productos_maestro` | `ENABLE_SYNC_PRODUCTOS_AUTOMATICA` | `false` | diaria, `SYNC_PRODUCTOS_HOUR:MINUTE` (3:00 AM) |
| `execute_auto_migration` (legacy) | `ENABLE_AUTO_MIGRATE` | `false` | cada `AUTO_MIGRATE_INTERVAL_MINUTES` |

**Sobre `reconciliar_transferencias_pendientes` (rediseño 2026-08-28):** antes corría cada
5 minutos sin límite de antigüedad; los datos de producción mostraron que el caso real es
raro (~1 cada 4-5 días). El diseño final usa la MISMA tarea con dos configuraciones (ver
`beat_schedule` en `src/celery_app.py`), pasadas como `kwargs` de Celery Beat:
- **Lunes a sábado**: `dias_ventana=RECONCILIAR_ST_VENTANA_DIAS` (2) -- solo mira ODCs cuyo
  primer intento de ST fue en los últimos 2 días. A propósito no alcanza nada más viejo: no
  se quiere que la automatización reintente a ciegas órdenes de hace meses sin supervisión.
- **Domingo**: `dias_ventana=RECONCILIAR_ST_VENTANA_DIAS_DOMINGO` (7) -- barrido más amplio,
  alcanza cualquier OC que se le haya "escapado" a los barridos cortos entre semana.

El colchón de seguridad (¿la corrida anterior completó?) corre en **cada** ejecución (lunes a
domingo), no solo la del domingo -- dentro de la MISMA tarea, en vez de una aparte corriendo
cada hora: el problema que vigila no es urgente, pero corriendo todos los días la latencia de
detección queda acotada a ~24-48h en vez de hasta una semana.

**Candidatas: Error, Encolada y faltantes (2026-08-28).** Las dos consultas que alimentan la
reconciliación (`get_oc_ids_con_tiendas_pendientes`, `get_oc_ids_con_tiendas_faltantes`) ahora
también recogen tiendas `'Encolada'` (HTTP 202 del middleware, job sin resolver) -- antes solo
se reconciliaba `'Error'`, así que una OC 100% encolada nunca se auto-reparaba. Ambas exigen
además `margen_antiguedad_minutos=RECONCILIAR_ST_MARGEN_ANTIGUEDAD_MINUTOS` (30 min por
defecto) de antigüedad en el último envío, para no chocar con un envío original todavía en
curso para la misma OC (el envío original no toma ningún lock). El valor por defecto tiene
margen sobre el techo real medido en el middleware .NET (`api-middleware-sap`): 5 reintentos
con backoff fijo `[15,30,60,120,240]s` (465s) más hasta 4 llamadas HTTP a SAP por intento
(~40s c/u) ⇒ máximo teórico ~11-19 minutos para que un job encolado llegue a un estado
terminal (COMPLETADO o ERROR).

El escalamiento a técnicos ya no se mide en horas transcurridas (con una corrida diaria,
cualquier OC pendiente ya lleva "más horas" que cualquier umbral razonable en el primer
chequeo) sino en **corridas consecutivas**: la primera vez solo se marca, la segunda seguida
sin resolverse escala por correo (`_evaluar_escalamiento_por_recurrencia`). El colchón de
seguridad (`RECONCILIAR_ST_MARGEN_COLCHON_HORAS`, 48h por defecto) avisa por correo si, al
iniciar cualquier corrida, la última corrida exitosa registrada es más vieja que ese margen --
señal de que Celery Beat estuvo caído o la tarea viene fallando.

Algo que se queda sin resolver más allá del barrido semanal del domingo deja de reintentarse
automáticamente (a propósito), pero ya generó su correo de escalamiento mucho antes -- el
botón manual "Reintentar ST" sigue disponible.

**Sobre `sync_productos_maestro` (deshabilitada el 2026-07):** copia los catálogos completos
de productos MBA3 (API) y SAP (OPENQUERY) a las tablas staging `producto_mba3_staging` /
`producto_sap_staging`, que alimentan únicamente el **cruce de productos** (homologación de
SKUs). Se deshabilitó porque la homologación masiva concluyó y la pantalla de cruce tiene
sincronización manual (`cruce_productos.py`: endpoints `/sincronizar-maestros*`), así que la
nocturna solo consumía recursos (lee dos ERPs completos, límite de 30 min). La tarea y los
endpoints manuales siguen operativos. **Para reactivarla:** `ENABLE_SYNC_PRODUCTOS_AUTOMATICA=true`
en el `.env` y reiniciar `celery-beat` (y el worker si también estaba abajo) — nada más.

## ✅ Paso 4: Ejecutar los procesos

Si usaste el **stack `app`** en el Paso 1, **omite este paso**: API, worker y beat ya están en Docker (`mba3-api`, `mba3-celery-worker`, `mba3-celery-beat`). Pasa al Paso 5 (`http://localhost:8000/health`).

### Opción A: Usando el script de PowerShell (host)

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

## 📤 Upload de plantillas en segundo plano (async)

Para que la **carga de plantillas Excel** no bloquee la aplicación (y otros usuarios puedan seguir navegando), el frontend puede usar el endpoint **async**:

- **POST /api/plantillas/upload-async** → responde de inmediato con `process_id`
- **GET /api/plantillas/resultado/{process_id}** → consultar resultado (polling)
- **GET /api/plantillas/stream/{process_id}** → progreso en tiempo real (SSE)

**Requisitos:**

1. **Redis** en marcha (mismo que para migración automática).
2. **Celery Worker** en marcha (misma terminal que arriba):
   ```powershell
   cd C:\Users\cortiz\PycharmProjects\mba3-consultas
   celery -A src.celery_app worker --loglevel=info --pool=solo
   ```

## 📤 Proceso completo SAP (Enviar ODC a SAP) en segundo plano

El flujo **"Enviar ODC a SAP"** (Redistribución + Generar ODC + Enviar a SAP) puede ejecutarse en segundo plano con Celery, igual que la carga de plantillas:

- **POST /api/pedidos/{numero_pedido}/proceso-completo-sap-async** → body: `{ "ajustes_detalle": [...] }`; responde **202** con `process_id`, `resultado_url`, `stream_url`.
- **GET /api/pedidos/proceso-sap/resultado/{process_id}** → consultar resultado (polling). Si `status === "completed"`, el cuerpo es el mismo que el endpoint síncrono (incluye `envio_sap.oc_id` para descargar el PDF).
- **GET /api/pedidos/proceso-sap/stream/{process_id}** → progreso en tiempo real (SSE).

**Requisitos:** Redis y Celery Worker en marcha (mismos que para plantillas).

El frontend en `/mba3-consultas/proceso` debe llamar al **async** y usar `resultado_url` o `stream_url` para mostrar progreso y, al terminar, el modal de éxito con opción de descargar PDF (`GET /ordenes-compra/{oc_id}/pdf`).

**Resumen para arrancar todo (plantillas async + proceso SAP async + migración automática):**

| Terminal | Comando |
|----------|--------|
| 1. FastAPI | `cd mba3-consultas` → `python src/api_server.py` |
| 2. Redis | `redis-server` (o ya instalado como servicio) |
| 3. Celery Worker | `cd mba3-consultas` → `celery -A src.celery_app worker --loglevel=info --pool=solo` |
| 4. Celery Beat (opcional) | `celery -A src.celery_app beat --loglevel=info` |

Verificar Redis: `redis-cli ping` → debe responder `PONG`.

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

---

**✅ ¡Listo!** El proceso automático ahora corre en un proceso completamente aislado sin afectar al proceso manual.
