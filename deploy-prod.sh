#!/usr/bin/env bash
# Wrapper (ejecutable en git). Desde ~:
#   /opt/odc-sap/deploy-prod.sh
# Si aparece "Permission denied": bash /opt/odc-sap/deploy-prod.sh
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec bash "${ROOT}/deploy/scripts/mba3_api_prod.sh" "$@"
