#!/usr/bin/env bash
# Detiene el stack Docker de producción (perfil app + overlay prod).
#
# Uso:
#   ./scripts/docker-app-down-prod.sh
#   ./scripts/docker-app-down-prod.sh --volumes

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.prod.yml)
ARGS=(down)
if [[ "${1:-}" == "--volumes" ]] || [[ "${1:-}" == "-Volumes" ]]; then
  ARGS+=(-v)
fi

echo "docker compose ${COMPOSE_FILES[*]} --profile app ${ARGS[*]}"
docker compose "${COMPOSE_FILES[@]}" --profile app "${ARGS[@]}"
