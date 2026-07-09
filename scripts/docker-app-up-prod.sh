#!/usr/bin/env bash
# Stack Docker de producción en srv-mabuiosapi (/opt/odc-sap).
# Redis + API + Celery (sin MinIO local; storage en 192.168.2.211).
#
# Requisitos:
#   - /opt/odc-sap/.env con ENVIRONMENT=production y credenciales FILE_STORAGE_*
#   - systemd API/Celery y redis-server nativo detenidos (puertos 8000 y 6379 libres)
#
# Uso:
#   ./deploy-prod.sh                    # recomendado: pull + build + health + log
#   ./scripts/docker-app-up-prod.sh
#   ./scripts/docker-app-up-prod.sh --build

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ROOT}/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: No existe ${ENV_FILE}" >&2
  echo "Crea el archivo según docs/DEPLOY_DOCKER_PRODUCCION.md y docs/CONFIGURACION.md" >&2
  exit 1
fi

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.prod.yml)
PROFILE=(--profile app)
BUILD=()
if [[ "${1:-}" == "--build" ]] || [[ "${1:-}" == "-Build" ]]; then
  BUILD=(--build)
fi

echo "Directorio: $ROOT"
echo "docker compose ${COMPOSE_FILES[*]} ${PROFILE[*]} up -d ${BUILD[*]}"
docker compose "${COMPOSE_FILES[@]}" "${PROFILE[@]}" up -d "${BUILD[@]}"

echo ""
echo "Listo. Verificar:"
echo "  curl -sS http://127.0.0.1:8000/health"
echo "  docker compose ${COMPOSE_FILES[*]} ps"
echo "  docker logs --tail 50 mba3-api"
