# Despliegue en servidor (runbook)

Un solo comando (desde `~` o desde el repo):

```bash
/opt/odc-sap/deploy-prod.sh
# Si "Permission denied" (script sin +x tras git reset):
bash /opt/odc-sap/deploy-prod.sh
```

O desde la raíz del clone:

```bash
cd /opt/odc-sap
chmod +x deploy-prod.sh deploy/scripts/mba3_api_prod.sh
./deploy-prod.sh
```

Hace: comprobar `.env` → `git fetch` + `reset --hard origin/<rama>` (descarta cambios locales en archivos versionados, p. ej. `chmod` en scripts) → `docker compose` prod con `--build` → health check → log en `deploy/logs/deploy-prod.log`.

**No** edites archivos del repo en el servidor; usa solo `.env` (ignorado por git). Los commits van en tu PC → `git push` → deploy.

## Primera vez

1. Clonar en `/opt/odc-sap` (rama `main`).
2. Crear entorno:
   ```bash
   cp deploy/env/prod.env.example .env
   # editar .env (credenciales, SQL, SAP, MinIO 211, JWT)
   ```
   O usar `deploy/env/active.env` (no va a git) y el script enlazará a `.env`.
3. Migrar desde systemd si aplica: [docs/DEPLOY_DOCKER_PRODUCCION.md](../docs/DEPLOY_DOCKER_PRODUCCION.md).
4. `./deploy-prod.sh`

## Mismo patrón que el front (`~/deploys/`)

```bash
mkdir -p ~/deploys
cp /opt/odc-sap/deploy/scripts/mba3_api_prod.launcher.sh ~/deploys/mba3_api_prod.sh
chmod +x ~/deploys/mba3_api_prod.sh
bash ~/deploys/mba3_api_prod.sh
```

Equivalente a `nexus_frontend_prod.sh` → llama a `/opt/odc-sap/deploy-prod.sh`.

**No** copies `mba3_api_prod.sh` directo a `~/deploys/` (calcula mal la ruta del repo).

## Flags

| Flag | Efecto |
|------|--------|
| `--no-pull` | Solo reconstruir/levantar contenedores |
| `--no-build` | `up -d` sin rebuild de imagen |

## Variables del operador

| Variable | Default |
|----------|---------|
| `PROJECT_DIR` | Raíz del repo |
| `DEPLOY_BRANCH` | Rama actual (`git rev-parse`) |
| `LOG_FILE` | `deploy/logs/deploy-prod.log` |
| `ENV_PATH` | `$PROJECT_DIR/.env` |
| `API_PORT` | `8000` |
| `HEALTH_WAIT_SECONDS` | `90` (reintentos tras `up`) |
| `HEALTH_RETRY_INTERVAL` | `3` |

El health check espera a que uvicorn termine de arrancar (evita falso fallo con `Connection reset`).

Documentación completa: [docs/DEPLOY_DOCKER_PRODUCCION.md](../docs/DEPLOY_DOCKER_PRODUCCION.md).
