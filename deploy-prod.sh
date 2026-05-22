#!/usr/bin/env bash
# Wrapper: ejecutar desde la raíz del clone en el servidor (p. ej. /opt/odc-sap).
#   chmod +x deploy-prod.sh deploy/scripts/mba3_api_prod.sh
#   ./deploy-prod.sh
exec "$(cd "$(dirname "$0")" && pwd)/deploy/scripts/mba3_api_prod.sh" "$@"
