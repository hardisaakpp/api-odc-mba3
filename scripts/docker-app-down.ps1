# Detiene y elimina contenedores del proyecto Compose (incluye perfil app si estaba activo).
#
# Uso (desde la raíz del repo):
#   .\scripts\docker-app-down.ps1
#
# No borra volúmenes de datos (redis_data, minio_data, celerybeat_data) salvo que uses -Volumes.

param(
    [switch]$Volumes
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path -LiteralPath (Join-Path $Root "docker-compose.yml"))) {
    Write-Error "No se encontró docker-compose.yml bajo: $Root"
}
Set-Location -LiteralPath $Root

$args = @("compose", "--profile", "app", "--profile", "bundled-minio", "down")
if ($Volumes) {
    $args += "-v"
}

Write-Host "docker $($args -join ' ')" -ForegroundColor Cyan
& docker @args
exit $LASTEXITCODE
