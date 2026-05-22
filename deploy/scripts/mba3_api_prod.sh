#!/usr/bin/env bash
# Despliegue de producción — un solo comando desde la raíz del repo en el servidor.
#
# Uso (en srv-mabuiosapi, p. ej. /opt/odc-sap):
#   ./deploy-prod.sh
#   ./deploy/scripts/mba3_api_prod.sh
#
# Opciones:
#   --no-pull    No ejecutar git pull
#   --no-build   docker compose up sin --build
#
# Requisitos: git, docker, .env en la raíz (o deploy/env/active.env).
# Ver docs/DEPLOY_DOCKER_PRODUCCION.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$ROOT"

PROJECT_DIR="${PROJECT_DIR:-$ROOT}"
LOG_FILE="${LOG_FILE:-$PROJECT_DIR/deploy/logs/deploy-prod.log}"
ENV_PATH="${ENV_PATH:-$PROJECT_DIR/.env}"
ACTIVE_ENV="${ACTIVE_ENV:-$PROJECT_DIR/deploy/env/active.env}"
EXAMPLE_ENV="${EXAMPLE_ENV:-$PROJECT_DIR/deploy/env/prod.env.example}"
BRANCH="${DEPLOY_BRANCH:-}"
API_PORT="${API_PORT:-8000}"
HEALTH_WAIT_SECONDS="${HEALTH_WAIT_SECONDS:-90}"
HEALTH_RETRY_INTERVAL="${HEALTH_RETRY_INTERVAL:-3}"
DO_PULL=1
DO_BUILD=1

for arg in "$@"; do
  case "$arg" in
    --no-pull) DO_PULL=0 ;;
    --no-build) DO_BUILD=0 ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *)
      echo "Opción desconocida: $arg (usa --help)" >&2
      exit 1
      ;;
  esac
done

mkdir -p "$(dirname "$LOG_FILE")"

resolve_env_file() {
  if [[ -f "$ENV_PATH" ]]; then
    echo "$ENV_PATH"
    return 0
  fi
  if [[ -f "$ACTIVE_ENV" ]]; then
    echo "Enlazando $ACTIVE_ENV -> $ENV_PATH" >&2
    ln -sf "$ACTIVE_ENV" "$ENV_PATH"
    echo "$ENV_PATH"
    return 0
  fi
  if [[ -f "$EXAMPLE_ENV" ]]; then
    cp "$EXAMPLE_ENV" "$ENV_PATH"
    echo "Creado $ENV_PATH desde plantilla. Edítalo con credenciales y vuelve a ejecutar este script." >&2
    exit 1
  fi
  echo "ERROR: No existe $ENV_PATH ni $ACTIVE_ENV ni $EXAMPLE_ENV" >&2
  exit 1
}

wait_for_health() {
  local url="http://127.0.0.1:${API_PORT}/health"
  local max="$HEALTH_WAIT_SECONDS"
  local interval="$HEALTH_RETRY_INTERVAL"
  local elapsed=0

  while [[ "$elapsed" -lt "$max" ]]; do
    if curl -sfS "$url" 2>/dev/null; then
      echo ""
      return 0
    fi
    sleep "$interval"
    elapsed=$((elapsed + interval))
    echo "   esperando API (${elapsed}s / ${max}s)..." >&2
  done
  return 1
}

run_deploy() {
  local env_file branch build_args
  env_file="$(resolve_env_file)"
  branch="${BRANCH:-$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD)}"

  build_args=()
  if [[ "$DO_BUILD" -eq 1 ]]; then
    build_args=(--build)
  fi

  echo "=== $(date -Iseconds 2>/dev/null || date) ==="
  echo "Proyecto: $PROJECT_DIR"
  echo "Rama:     $branch"
  echo "Env:      $env_file"
  echo ""

  cd "$PROJECT_DIR"

  if [[ "$DO_PULL" -eq 1 ]]; then
    echo ">> git pull origin $branch"
    git pull origin "$branch"
  fi

  echo ">> docker compose (producción) up -d ${build_args[*]}"
  docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile app up -d "${build_args[@]}"

  echo ""
  echo ">> Contenedores"
  docker ps --filter name=mba3-api --filter name=mba3-celery --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

  echo ""
  echo ">> Health http://127.0.0.1:${API_PORT}/health (reintentos hasta ${HEALTH_WAIT_SECONDS}s)"
  if wait_for_health; then
    echo "Deploy OK."
  else
    echo "ERROR: health check falló tras ${HEALTH_WAIT_SECONDS}s. Revisa: docker logs --tail 80 mba3-api" >&2
    exit 1
  fi
}

{
  run_deploy
} 2>&1 | tee -a "$LOG_FILE"
