#!/usr/bin/env bash
# Launcher para ~/deploys/ (mismo patrón que nexus_frontend_prod.sh).
# Instalación en el servidor (una vez):
#   mkdir -p ~/deploys
#   cp /opt/odc-sap/deploy/scripts/mba3_api_prod.launcher.sh ~/deploys/mba3_api_prod.sh
#   chmod +x ~/deploys/mba3_api_prod.sh
#
# Uso desde cualquier directorio:
#   bash ~/deploys/mba3_api_prod.sh

set -euo pipefail
PROJECT_DIR="${PROJECT_DIR:-/opt/odc-sap}"
exec "${PROJECT_DIR}/deploy-prod.sh" "$@"
