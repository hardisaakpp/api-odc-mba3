#!/usr/bin/env bash
# Wrapper: ejecutar desde la raíz del clone o con ruta absoluta desde ~:
#   /opt/odc-sap/deploy-prod.sh
#   bash ~/deploys/mba3_api_prod.sh   # tras copiar deploy/scripts/mba3_api_prod.launcher.sh
exec "$(cd "$(dirname "$0")" && pwd)/deploy/scripts/mba3_api_prod.sh" "$@"
