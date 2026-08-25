# Script de inicio para Celery (Windows PowerShell)
# Este script inicia todos los procesos necesarios para la migración automática con Celery

Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "MBA3 Consultas - Inicio de Celery" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""

# Verificar que Redis está corriendo (Docker o nativo)
Write-Host "Verificando Redis..." -ForegroundColor Yellow
$redisOk = $false
# 1) Intentar Redis en Docker (recomendado)
try {
    $dockerTest = docker exec redis redis-cli ping 2>&1
    if ($LASTEXITCODE -eq 0 -and ($dockerTest -match "PONG")) {
        Write-Host "✅ Redis está corriendo (contenedor Docker 'redis')" -ForegroundColor Green
        $redisOk = $true
    }
} catch { }
# 2) Si no, intentar redis-cli en PATH (instalación nativa)
if (-not $redisOk) {
    try {
        $redisTest = redis-cli ping 2>&1
        if ($redisTest -eq "PONG") {
            Write-Host "✅ Redis está corriendo (nativo)" -ForegroundColor Green
            $redisOk = $true
        }
    } catch { }
}
if (-not $redisOk) {
    Write-Host "❌ Redis no está disponible en localhost:6379" -ForegroundColor Red
    Write-Host "   Con Docker (recomendado): docker run -d --name redis -p 6379:6379 redis" -ForegroundColor Yellow
    Write-Host "   Ver docs/CELERY_QUICKSTART.md para más opciones." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "Instrucciones para iniciar los procesos:" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""
Write-Host "Terminal 1: FastAPI (proceso manual)" -ForegroundColor Green
Write-Host "   .\start_api.ps1        (estable) o  .\start_api.ps1 -Dev  (desarrollo)" -ForegroundColor Gray
Write-Host ""
Write-Host "Terminal 2: Celery Worker (proceso automático)" -ForegroundColor Green
Write-Host "   cd C:\Users\cortiz\PycharmProjects\mba3-consultas" -ForegroundColor Gray
Write-Host "   celery -A src.celery_app worker --loglevel=info --pool=threads" -ForegroundColor Gray
Write-Host ""
Write-Host "Terminal 3: Celery Beat (scheduler)" -ForegroundColor Green
Write-Host "   cd C:\Users\cortiz\PycharmProjects\mba3-consultas" -ForegroundColor Gray
Write-Host "   celery -A src.celery_app beat --loglevel=info" -ForegroundColor Gray
Write-Host ""
Write-Host "Terminal 4: Flower (monitoreo - opcional)" -ForegroundColor Green
Write-Host "   cd C:\Users\cortiz\PycharmProjects\mba3-consultas" -ForegroundColor Gray
Write-Host "   celery -A src.celery_app flower" -ForegroundColor Gray
Write-Host "   Luego abrir: http://localhost:5555" -ForegroundColor Gray
Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "Presiona cualquier tecla para continuar con el inicio del Worker..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

Write-Host ""
Write-Host "Iniciando Celery Worker en esta terminal..." -ForegroundColor Green
Write-Host ""

# Iniciar Celery Worker desde el directorio raíz del proyecto
# --pool=threads (no --pool=solo): permite atender pings de control (inspect().ping())
# mientras se ejecuta una tarea, en vez de bloquear todo en un único hilo secuencial.
# --pool=prefork (el de Docker) no es viable en Windows nativo por depender de os.fork().
celery -A src.celery_app worker --loglevel=info --pool=threads


