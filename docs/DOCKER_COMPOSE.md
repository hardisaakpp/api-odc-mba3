# Docker Compose (Redis, MinIO y stack de aplicación)

Este repositorio define varios modos con `docker-compose.yml` (+ overlay de producción si aplica):

| Modo | Comando | Qué levanta |
|------|-----------|-------------|
| **Solo Redis** (por defecto) | `docker compose up -d` | Redis (6379). |
| **Redis + MinIO local** (desarrollo) | `docker compose --profile bundled-minio up -d` | Redis + MinIO (9100/9101). |
| **Stack desarrollo** (perfil `app` + MinIO embebido) | `.\scripts\docker-app-up.ps1` (rebuild por defecto) o `docker compose --profile app --profile bundled-minio up -d --build` | Redis, MinIO, API, Celery worker y beat. |
| **Stack producción** (`srv-mabuiosapi`) | `docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile app up -d --build` o `./scripts/docker-app-up-prod.sh` | Redis, API, Celery; **MinIO en 192.168.2.211**. Ver [DEPLOY_DOCKER_PRODUCCION.md](DEPLOY_DOCKER_PRODUCCION.md). |

Con el perfil **`app`** corre **toda la aplicación backend de este repo** (mismos endpoints y tareas Celery que en host). No hay funcionalidad reservada al modo host; solo cambia dónde se ejecutan los procesos.

## Flujo de desarrollo con stack `app`

1. Crear o actualizar **`.env.develop`** (ver [CONFIGURACION.md](CONFIGURACION.md)).
2. `.\scripts\docker-app-up.ps1` (reconstruye la imagen por defecto, así el contenedor siempre corre el código Python actual; usar `-NoBuild` solo si no cambió nada desde el último build).
3. `.\scripts\docker-verify.ps1` — smoke test de contenedores y dependencias.
4. Frontend **scnexus-front**: `npm run dev` con proxy/API en **`http://localhost:8000`** (el navegador no usa el hostname `mba3-api`).
5. Pruebas de negocio (plantilla async, proceso SAP, ODC, cruce) con JWT como en DESA — checklist: [ALINEACION_FRONT_ASYNC.md](ALINEACION_FRONT_ASYNC.md).

**Ciclo tras implementar una feature:** editar código → `.\scripts\docker-app-up.ps1` (rebuild automático) → verificar con `docker-verify` y el flujo en el front → commit.

**Qué no incluye el compose** (deben ser alcanzables desde la red del contenedor):

| Fuera del stack | Configuración típica |
|-----------------|----------------------|
| SQL Server | `SQL_SERVER_SERVER` en `.env.develop` (no `localhost` si la BD está en el host Windows: `host.docker.internal` o IP) |
| SAP Service Layer, MBA3 | URLs/credenciales en `.env.develop` |
| SCNexus Core (JWT) | `CORE_API_URL` |
| Frontend Vue | Repo `scnexus-front`, `npm run dev` en el host (o su propio compose + red `mba3-nexus_edge`) |

Migraciones, `pytest` y lint suelen ejecutarse en el **host** con el venv del proyecto (`python scripts/migration_runner.py`, etc.), aunque uses el stack `app` para la API.

El modo “solo infra” sigue disponible si solo necesitas Redis/MinIO y prefieres API/Celery en Windows (`--pool=solo`).

## Requisitos

- Docker Desktop (Windows/Mac) o Docker Engine + Compose v2.
- Archivo **`.env.develop`** en la raíz del proyecto (obligatorio para la app; ver [CONFIGURACION.md](CONFIGURACION.md)). Los servicios del perfil `app` montan ese archivo en `/app/.env.develop` dentro del contenedor.

## Variables que Compose fuerza en el perfil `app`

Dentro de la red Docker, `localhost` no apunta a Redis ni a MinIO. Por eso, para `api`, `celery-worker` y `celery-beat` se definen (y tienen prioridad sobre el `.env` cargado por `python-dotenv` con `override=False`):

- `REDIS_URL=redis://redis:6379/0`
- `FILE_STORAGE_ENDPOINT=http://minio:9000`

El resto de variables (SQL Server, SAP, MBA3, JWT, etc.) salen de tu `.env.develop`. Si la base de datos corre **en tu máquina Windows** y en el `.env` usas `SQL_SERVER_SERVER=localhost`, desde el contenedor **no funcionará**: usa el hostname/IP real del SQL Server o `host.docker.internal` si aplica a tu red y puerto (p. ej. `host.docker.internal,1433`). El compose añade `extra_hosts: host.docker.internal:host-gateway` para Linux; en Docker Desktop para Windows suele resolverse igualmente.

La API en contenedor debe poder alcanzar **MBA3**, **SAP Service Layer** y **SQL Server** por red (VPN, firewall, DNS). Eso no lo resuelve Docker por sí solo.

## Verificación del stack (revisión rápida)

Con el perfil `app` en marcha:

```powershell
.\scripts\docker-verify.ps1
.\scripts\docker-verify.ps1 -ShowLogErrors   # timeouts MBA3, etc.
```

Comprueba los 5 contenedores, `/health`, Redis/MinIO/SQL desde `mba3-api`, tareas Celery registradas y beat. No sustituye pruebas manuales con JWT (upload-async, proceso SAP, cruce).

## Comandos útiles

```powershell
# Solo Redis
docker compose up -d

# Redis + MinIO local (desarrollo)
docker compose --profile bundled-minio up -d

# Stack completo desarrollo (reconstruye la imagen por defecto)
.\scripts\docker-app-up.ps1

# Solo levantar sin rebuild (nada cambió desde el último build)
.\scripts\docker-app-up.ps1 -NoBuild

# Ver logs
docker logs -f mba3-api
docker logs -f mba3-celery-worker

# Parar contenedores del proyecto (volúmenes de datos se conservan)
.\scripts\docker-app-down.ps1

# Parar y eliminar también volúmenes (Redis/MinIO/beat schedule)
.\scripts\docker-app-down.ps1 -Volumes
```

## Detalles técnicos

- **Imagen**: se construye con el `Dockerfile` de la raíz (Python 3.11 + **ODBC Driver 18**). El código se copia en build; `.env.*` no se incluye en la imagen (`.dockerignore`), solo se monta en runtime. En `.env` usa `SQL_SERVER_DRIVER={ODBC Driver 18 for SQL Server}` (Driver 17 no está instalado en la imagen).
- **Celery worker**: en contenedor Linux se usa `--pool=prefork`. En Windows nativo el repo usa `--pool=solo` (ver `scripts/dev-terminal.ps1`).
- **Celery beat**: el archivo de programación se guarda en el volumen `celerybeat_data` (`--schedule=/var/lib/celery/celerybeat-schedule`) para que sobreviva a reinicios del contenedor.
- **Puerto 8000**: si ya tienes la API en el host con `uvicorn`, habrá conflicto; detén una de las dos instancias.

## URLs presignadas / MinIO y el navegador

El cliente S3 usa `FILE_STORAGE_ENDPOINT=http://minio:9000` dentro de Docker. Las operaciones servidor–MinIO funcionan. Si en el futuro se devolvieran al navegador URLs firmadas con host `minio`, el navegador no las resolvería; en ese caso haría falta un endpoint “público” separado o proxy. Hoy el flujo principal no depende de eso para el día a día.

## Enlace con scnexus-front (Docker en otro repo)

Este backend expone la API en el contenedor con nombre fijo **`mba3-api`** y publica **`8000`** en el host.

Para que el **frontend en Docker** (compose distinto, p. ej. `scnexus-front`) pueda llamar al API **desde dentro de la red Docker** (SSR, `nginx` hacia upstream, healthchecks, scripts de entrypoint), ambos stacks deben compartir la red bridge con nombre fijo **`mba3-nexus_edge`**.

- En **mba3-consultas**, la red se define en `docker-compose.yml` y **`redis`** y **`api`** (perfil `app`) están conectados a ella. Así la red **se crea** aunque solo levantes Redis + MinIO (`docker compose up -d`), sin obligar al perfil `app`.
- En **scnexus-front**, declara la red como externa y conecta tu servicio web:

```yaml
networks:
  mba3-nexus_edge:
    external: true
    name: mba3-nexus_edge

services:
  tu-servicio-frontend:
    networks:
      - default
      - mba3-nexus_edge
```

URL interna del API: **`http://mba3-api:8000`**.

**SPA / Vite (fetch desde el navegador):** el JavaScript corre en la máquina del usuario, no en el contenedor; ahí **`mba3-api` no resuelve DNS**. Usa la URL publicada en el host, p. ej. **`http://localhost:8000`**, en las variables `VITE_*` que inyectes al **build** o al runtime que lea el navegador.

**CORS:** con `ENABLE_CORS_RESTRICTION=false` (típico en desarrollo) el backend acepta orígenes amplios. Si activas restricción, añade en `.env` los orígenes del front (p. ej. `http://localhost:5173`, `http://localhost:4173`).

Fragmento de ejemplo listo para copiar: [examples/scnexus-front-docker-network.attach.yml](examples/scnexus-front-docker-network.attach.yml).

## Privacidad / CI

Evita ejecutar `docker compose config` en entornos con `.env.develop` real y compartir la salida: Compose expande `env_file` y puede imprimir secretos.
