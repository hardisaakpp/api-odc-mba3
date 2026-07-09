# Script de inicio para la API FastAPI (MBA3 Consultas)
# Uso:
#   .\start_api.ps1           → Modo estable (sin --reload), menos ECONNRESET en el frontend
#   .\start_api.ps1 -Dev      → Modo desarrollo (con --reload), recarga al guardar archivos

param(
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "MBA3 Consultas - API Backend (FastAPI)" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""

# Comprobar que el puerto 8000 no esté en uso por otro proceso (opcional)
try {
    $portInUse = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
    if ($portInUse) {
        $proc = Get-Process -Id $portInUse.OwningProcess -ErrorAction SilentlyContinue
        Write-Host "Advertencia: el puerto 8000 ya está en uso (PID $($portInUse.OwningProcess)$(if ($proc) { ", $($proc.ProcessName)" }))." -ForegroundColor Yellow
        Write-Host "Cierra ese proceso o usa otro puerto si quieres levantar otra instancia." -ForegroundColor Yellow
        Write-Host ""
    }
} catch { }

if ($Dev) {
    Write-Host "Modo: DESARROLLO (--reload). El servidor se reiniciará al guardar archivos." -ForegroundColor Yellow
    Write-Host "      El proxy del frontend puede mostrar ECONNRESET durante el reinicio." -ForegroundColor Gray
    Write-Host ""
    & python -m uvicorn src.api_server:app --reload --host 0.0.0.0 --port 8000 --reload-dir src
} else {
    Write-Host "Modo: ESTABLE (sin --reload). Menos desconexiones en el frontend." -ForegroundColor Green
    Write-Host "      Reinicia este script cuando cambies código del backend." -ForegroundColor Gray
    Write-Host ""
    & python -m uvicorn src.api_server:app --host 0.0.0.0 --port 8000
}
