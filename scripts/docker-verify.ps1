# Verificación del stack Docker (perfil app): infra + API + Celery.
# No modifica contenedores; solo comprueba estado y conectividad básica.
#
# Uso (desde la raíz del repo, con stack levantado):
#   .\scripts\docker-verify.ps1
#   .\scripts\docker-verify.ps1 -ShowLogErrors   # últimas líneas con ERROR en logs

param(
    [switch]$ShowLogErrors
)

$ErrorActionPreference = "Continue"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $Root

$requiredContainers = @(
    "mba3-api",
    "mba3-celery-worker",
    "mba3-celery-beat",
    "mba3-consultas-redis-1",
    "mba3-consultas-minio-1"
)

function Write-Check {
    param([string]$Name, [bool]$Ok, [string]$Detail = "")
    $icon = if ($Ok) { "[OK]" } else { "[FAIL]" }
    $color = if ($Ok) { "Green" } else { "Red" }
    $line = "$icon $Name"
    if ($Detail) { $line += " — $Detail" }
    Write-Host $line -ForegroundColor $color
}

$results = @()

Write-Host ""
Write-Host "=== Verificación stack Docker (mba3-consultas) ===" -ForegroundColor Cyan
Write-Host ""

$running = docker ps --format "{{.Names}}" 2>$null
foreach ($name in $requiredContainers) {
    $ok = $running -contains $name
    Write-Check "Contenedor $name" $ok $(if (-not $ok) { "no está en ejecución" } else { "running" })
    $results += @{ Name = "container:$name"; Ok = $ok }
}

try {
    $resp = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 10
    $ok = $resp.StatusCode -eq 200
    Write-Check "GET /health" $ok "HTTP $($resp.StatusCode)"
    $results += @{ Name = "health"; Ok = $ok }
}
catch {
    Write-Check "GET /health" $false $_.Exception.Message
    $results += @{ Name = "health"; Ok = $false }
}

$apiChecks = @(
    @{
        Name = "Config REDIS_URL (redis://redis:6379/0)"
        Script = "from src.config import REDIS_URL; import sys; sys.exit(0 if REDIS_URL == 'redis://redis:6379/0' else 1)"
    },
    @{
        Name = "Config FILE_STORAGE_ENDPOINT (http://minio:9000)"
        Script = "from src.config import FILE_STORAGE_ENDPOINT; import sys; sys.exit(0 if FILE_STORAGE_ENDPOINT == 'http://minio:9000' else 1)"
    },
    @{
        Name = "Redis ping (ProcesoEstadoService)"
        Script = "from src.database.services.proceso_estado_service import get_redis_client; get_redis_client().ping()"
    },
    @{
        Name = "MinIO / file storage health"
        Script = "from src.services.file_storage_service import get_file_storage; h=get_file_storage().health_check(); import sys; sys.exit(0 if h.get('status')=='healthy' else 1)"
    },
    @{
        Name = "SQL Server (conexión de prueba)"
        Script = "from src.database.connection import get_db_connection_context;`nwith get_db_connection_context() as c:`n    c.cursor().execute('SELECT 1')`nprint('sql ok')"
    }
)

foreach ($check in $apiChecks) {
    $out = docker exec mba3-api python -c $check.Script 2>&1
    $ok = $LASTEXITCODE -eq 0
    $lastLine = ($out | Where-Object { $_ -and $_ -notmatch "CONFIGURACI" -and $_ -notmatch "^=+$" } | Select-Object -Last 1)
    $detail = if ($ok) { $lastLine } else { ($out | Select-Object -Last 3) -join " | " }
    Write-Check $check.Name $ok $detail
    $results += @{ Name = $check.Name; Ok = $ok }
}

$celeryReg = docker exec mba3-celery-worker celery -A src.celery_app inspect registered 2>&1 | Out-String
$expectedTasks = @(
    "procesar_plantilla_upload",
    "ejecutar_proceso_completo_sap",
    "ejecutar_cruce_productos",
    "sync_productos_maestro",
    "execute_auto_migration"
)
$tasksOk = $true
$missing = @()
foreach ($t in $expectedTasks) {
    if ($celeryReg -notmatch [regex]::Escape($t)) {
        $tasksOk = $false
        $missing += $t
    }
}
Write-Check "Celery: 5 tareas registradas" $tasksOk $(if ($missing) { "faltan: $($missing -join ', ')" } else { "todas presentes" })
$results += @{ Name = "celery_tasks"; Ok = $tasksOk }

$ping = docker exec mba3-celery-worker celery -A src.celery_app inspect ping 2>&1 | Out-String
$workerPing = $ping -match "pong"
Write-Check "Celery worker ping" $workerPing
$results += @{ Name = "celery_ping"; Ok = $workerPing }

$beatLog = docker logs mba3-celery-beat --tail 40 2>&1 | Out-String
$beatOk = $beatLog -match "beat: Starting" -or $beatLog -match "Iniciando Celery Beat"
Write-Check "Celery beat (scheduler activo)" $beatOk
$results += @{ Name = "celery_beat"; Ok = $beatOk }

if ($ShowLogErrors) {
    Write-Host ""
    Write-Host "--- Errores recientes en logs (revisar red/VPN si MBA3 timeout) ---" -ForegroundColor Yellow
    foreach ($c in @("mba3-api", "mba3-celery-worker", "mba3-celery-beat")) {
        Write-Host ">> $c" -ForegroundColor DarkGray
        docker logs $c --tail 200 2>&1 |
            Select-String -Pattern "Traceback|ConnectTimeout|ConnectionError|CRITICAL" |
            Select-Object -Last 5 |
            ForEach-Object { Write-Host $_.Line }
    }
}

$failed = @($results | Where-Object { -not $_.Ok })
Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host "RESULTADO: Todas las comprobaciones automáticas pasaron." -ForegroundColor Green
    Write-Host "Flujos async (plantilla, proceso SAP, cruce) requieren prueba manual con JWT en Swagger." -ForegroundColor DarkGray
}
else {
    Write-Host "RESULTADO: $($failed.Count) comprobación(es) fallaron." -ForegroundColor Red
    Write-Host "Levanta el stack: .\scripts\docker-app-up.ps1 -Build" -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "Documentación: docs/DOCKER_COMPOSE.md" -ForegroundColor DarkGray
Write-Host ""

if ($failed.Count -gt 0) { exit 1 }
