# Script de inicio para Celery (Windows PowerShell)
# Este script inicia todos los procesos necesarios para la migración automática con Celery

Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "MBA3 Consultas - Inicio de Celery" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""

# Verificar que Redis está corriendo
Write-Host "Verificando Redis..." -ForegroundColor Yellow
try {
    $redisTest = redis-cli ping 2>&1
    if ($redisTest -eq "PONG") {
        Write-Host "✅ Redis está corriendo" -ForegroundColor Green
    } else {
        Write-Host "❌ Redis no responde correctamente" -ForegroundColor Red
        Write-Host "   Inicia Redis con: redis-server" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "❌ Redis no está instalado o no está en el PATH" -ForegroundColor Red
    Write-Host "   Instala Redis: choco install redis-64" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "Instrucciones para iniciar los procesos:" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""
Write-Host "Terminal 1: FastAPI (proceso manual)" -ForegroundColor Green
Write-Host "   cd C:\Users\cortiz\PycharmProjects\mba3-consultas" -ForegroundColor Gray
Write-Host "   python src/api_server.py" -ForegroundColor Gray
Write-Host ""
Write-Host "Terminal 2: Celery Worker (proceso automático)" -ForegroundColor Green
Write-Host "   cd C:\Users\cortiz\PycharmProjects\mba3-consultas" -ForegroundColor Gray
Write-Host "   celery -A src.celery_app worker --loglevel=info --pool=solo" -ForegroundColor Gray
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
celery -A src.celery_app worker --loglevel=info --pool=solo


