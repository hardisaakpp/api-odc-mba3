# Levanta el stack de desarrollo recomendado (perfil "app"):
# Redis, MinIO, API FastAPI, Celery worker y Celery beat.
# Requiere: Docker Desktop (o Docker Engine), archivo .env.develop en la raíz del repo.
#
# Reconstruye la imagen por defecto: el Dockerfile hornea el código con `COPY . .`
# (no hay bind-mount de src/), así que sin rebuild el contenedor sigue corriendo lo
# que sea que se compiló la última vez -- código Python desactualizado y en silencio.
# El costo es bajo (~segundos: las capas de apt/pip quedan en caché). Usar -NoBuild
# solo cuando se sabe que no cambió código desde el último build (ej. tras reiniciar
# Docker Desktop sin tocar el repo). Ver docs/DOCKER_COMPOSE.md.
#
# Uso (desde la raíz del repo):
#   .\scripts\docker-app-up.ps1
#   .\scripts\docker-app-up.ps1 -NoBuild   # omite el rebuild (usa la imagen ya construida)
#
# Detener: .\scripts\docker-app-down.ps1
# Documentación: docs/DOCKER_COMPOSE.md

param(
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path -LiteralPath (Join-Path $Root "docker-compose.yml"))) {
    Write-Error "No se encontró docker-compose.yml bajo: $Root"
}
Set-Location -LiteralPath $Root

$envFile = Join-Path $Root ".env.develop"
if (-not (Test-Path -LiteralPath $envFile)) {
    Write-Error "No existe .env.develop en: $envFile`nCrea el archivo según docs/CONFIGURACION.md antes de usar el stack Docker."
}

$args = @("compose", "--profile", "app", "--profile", "bundled-minio", "up", "-d")
if (-not $NoBuild) {
    $args += "--build"
}

Write-Host "Directorio: $Root" -ForegroundColor Gray
Write-Host "docker $($args -join ' ')" -ForegroundColor Cyan
& docker @args
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
Write-Host ""
Write-Host "Listo. API: http://localhost:8000/docs  |  MinIO consola: http://localhost:9101" -ForegroundColor Green
Write-Host "Verificar: .\scripts\docker-verify.ps1" -ForegroundColor DarkGray
Write-Host "Logs API: docker logs -f mba3-api" -ForegroundColor DarkGray
