# Despliegue en servidor (runbook)

Un solo comando desde la raíz del clone:

```bash
cd /opt/odc-sap
chmod +x deploy-prod.sh deploy/scripts/mba3_api_prod.sh
./deploy-prod.sh
```

Hace: comprobar `.env` → `git pull` (rama actual) → `docker compose` prod con `--build` → health check → append en `deploy/logs/deploy-prod.log`.

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

## Copia opcional a `~/deploys/`

```bash
cp deploy/scripts/mba3_api_prod.sh ~/deploys/mba3_api_prod.sh
chmod +x ~/deploys/mba3_api_prod.sh
# PROJECT_DIR=/opt/odc-sap ~/deploys/mba3_api_prod.sh
```

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

Documentación completa: [docs/DEPLOY_DOCKER_PRODUCCION.md](../docs/DEPLOY_DOCKER_PRODUCCION.md).
