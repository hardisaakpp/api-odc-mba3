# Backend en producción con Docker (srv-mabuiosapi)

Guía para ejecutar **API + Celery + Redis** en contenedores en el servidor de aplicaciones, con **MinIO en un host dedicado** de almacenamiento.

Sustituye el despliegue histórico con **systemd** (`odc-sap-api`, `celery-worker`, `celery-beat`) y **redis-server** nativo en el mismo host.

---

## Topología actual (referencia)

| Rol | Host / IP | Servicios |
|-----|-----------|-----------|
| **API y cola** | `srv-mabuiosapi` — **192.168.2.153** | Docker: `redis`, `mba3-api`, `mba3-celery-worker`, `mba3-celery-beat` |
| **Almacenamiento (MinIO)** | `srv-mabuiosbdo` — **192.168.2.211** | Contenedor `minio-storage` — API **9100**, consola **9101** |
| **Código** | `/opt/odc-sap/` | Rama `main`, overlay `docker-compose.prod.yml` |

**No** debe haber contenedor MinIO en **192.168.2.153**. El endpoint de archivos para la app es:

```text
FILE_STORAGE_ENDPOINT=http://192.168.2.211:9100
```

Comprobación de red desde el servidor API (ya validada):

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://192.168.2.211:9100/minio/health/live
# Esperado: 200
```

En **srv-mabuiosbdo**:

```bash
docker ps   # contenedor minio-storage, puertos 9100->9000, 9101->9001
```

---

## Archivos Compose

| Archivo | Uso |
|---------|-----|
| `docker-compose.yml` | Base: Redis, servicios `app` (incluye MinIO embebido, obligatorio en dev) |
| `docker-compose.prod.yml` | Producción: monta `/opt/odc-sap/.env`, `ENVIRONMENT=production`, MinIO **192.168.2.211:9100**, desactiva el MinIO embebido |

Comando de arranque / actualización en producción (recomendado):

```bash
/opt/odc-sap/deploy-prod.sh
# o: bash ~/deploys/mba3_api_prod.sh  (ver deploy/scripts/mba3_api_prod.launcher.sh)
```

Eso ejecuta `git fetch` + `reset --hard origin/<rama>` (evita bloqueos por `chmod` o edits locales en tracked), `docker compose` prod con `--build`, health check y log. Detalle: [deploy/README.md](../deploy/README.md).

Equivalente manual (sin pull ni log):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile app up -d --build
# o:
./scripts/docker-app-up-prod.sh --build
```

---

## Variables de entorno (`/opt/odc-sap/.env`)

El overlay de producción define:

- `ENV_FILE=/app/.env` (montaje read-only del `.env` del host)
- `ENVIRONMENT=production`
- `REDIS_URL=redis://redis:6379/0` (Redis **dentro** de la red Docker)
- `FILE_STORAGE_ENDPOINT=http://192.168.2.211:9100` (sobrescribe cualquier `localhost` del `.env`)

El resto (SQL Server, SAP, MBA3, JWT, `FILE_STORAGE_ACCESS_KEY`, `FILE_STORAGE_SECRET_KEY`, `FILE_STORAGE_BUCKET`, etc.) se lee del mismo `.env` que usaba systemd.

**Importante — contraseñas con `$`:** Docker Compose interpreta `$VAR` en el `.env` de la raíz del proyecto. Si una contraseña contiene `$` (p. ej. `M4B31$tr$...`), escapa cada `$` como `$$` en el archivo que Compose usa para interpolación, o verás avisos `The "tr" variable is not set`.

**SQL / SAP desde contenedor:** `SQL_SERVER_SERVER` y URLs no pueden ser `localhost` del host API si la BD está en otra máquina; usa IP/hostname reales alcanzables desde el contenedor.

**ODBC:** la imagen Docker incluye **Microsoft ODBC Driver 18**. En `/opt/odc-sap/.env` debe figurar:

```bash
SQL_SERVER_DRIVER={ODBC Driver 18 for SQL Server}
SQL_SERVER_SAP_DRIVER={ODBC Driver 18 for SQL Server}
```

Tras cambiar el `Dockerfile` o el driver, reconstruir: `./scripts/docker-app-up-prod.sh --build`.

---

## Migración desde systemd (primera vez)

### 1. Inventario

```bash
systemctl is-active odc-sap-api celery-worker celery-beat redis-server
ss -tlnp | grep -E '6379|8000|9100'
docker ps -a
```

### 2. Parar servicios nativos (liberar 6379 y 8000)

```bash
sudo systemctl stop odc-sap-api celery-worker celery-beat
sudo systemctl disable odc-sap-api celery-worker celery-beat   # si el corte es definitivo

sudo systemctl stop redis-server
sudo systemctl disable redis-server

# Quitar MinIO local en 153 si existiera (el bueno está en 211):
docker ps -a | grep -i minio
# docker stop <id> && docker rm <id>   # solo contenedores en srv-mabuiosapi
```

### 3. Confirmar puertos libres

```bash
ss -tlnp | grep -E '6379|8000'   # sin listeners
```

### 4. Código y build

```bash
cd /opt/odc-sap
./deploy-prod.sh
```

### 5. Verificación

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
curl -sS http://127.0.0.1:8000/health
docker logs --tail 80 mba3-celery-worker
```

Desde una máquina con acceso a la red interna, prueba un flujo con plantilla/archivo (MinIO remoto + Celery).

---

## Actualización rutinaria (solo código)

```bash
/opt/odc-sap/deploy-prod.sh
```

El script reintenta `/health` hasta 90 s tras levantar contenedores. No hace falta `pip install` ni `source venv` en el host: el `Dockerfile` instala `requirements.txt` en build.

Primera vez sin `.env`: el script copia `deploy/env/prod.env.example` → `.env` y pide editarlo antes de continuar.

---

## Detener stack

```bash
./scripts/docker-app-down-prod.sh
# Con borrado de volúmenes (Redis local, schedule de beat):
./scripts/docker-app-down-prod.sh --volumes
```

---

## Relación con otras guías

| Tema | Documento |
|------|-----------|
| Despliegue systemd (legado) | [DEPLOY_PRODUCCION.md](DEPLOY_PRODUCCION.md) |
| Desarrollo local Docker + MinIO embebido | [DOCKER_COMPOSE.md](DOCKER_COMPOSE.md) |
| Migraciones BD | [DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md) |
| Variables por ambiente | [CONFIGURACION.md](CONFIGURACION.md) |

---

## Errores frecuentes

| Síntoma | Causa | Acción |
|---------|--------|--------|
| `bind: address already in use` en **6379** | `redis-server` systemd aún activo | `systemctl stop redis-server` |
| `bind` en **8000** | `odc-sap-api` systemd activo | `systemctl stop odc-sap-api` |
| MinIO unhealthy / S3 error | Firewall 153→211 o credenciales | `curl` a `192.168.2.211:9100`; revisar keys en `.env` |
| `Can't open lib 'ODBC Driver 18 for SQL Server'` | Imagen antigua (solo Driver 17) o `.env` con Driver 17 | `SQL_SERVER_DRIVER={ODBC Driver 18 for SQL Server}` y `./scripts/docker-app-up-prod.sh --build` |
| WARN `tr` / `d3s4rr0ll0` en compose | `$` en contraseñas del `.env` | Escapar con `$$` |
| Worker sin tareas | Contenedor worker caído | `docker logs mba3-celery-worker` |
