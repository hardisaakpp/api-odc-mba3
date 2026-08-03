# Arranca API + Celery worker + Celery beat (y opcionalmente frontend en otra ventana).
# Por defecto: 3 ventanas de PowerShell sueltas (no depende de Windows Terminal).
# El frontend (Vite) no se incluye por defecto: suele fallar en ventanas hijas; arráncalo aparte con npm run dev.
# Desarrollo recomendado: stack completo en Docker (perfil app):
#   .\scripts\docker-app-up.ps1 -Build
#   .\scripts\docker-verify.ps1
# Ver docs/DOCKER_COMPOSE.md. Este script es la alternativa host (venv + ventanas).
#
# Uso (desde la raíz del repo):
#   .\start-all-dev.ps1                          # 3 ventanas PowerShell (api, worker, beat)
#   .\start-all-dev.ps1 -WindowsTerminal         # Una ventana WT con pestañas (requiere wt.exe sano)
#   .\start-all-dev.ps1 -SeparateWindows         # Igual que el default (explícito; útil en scripts)
#   .\start-all-dev.ps1 -WithFrontend            # + pestaña o ventana frontend (opcional)
#   .\start-all-dev.ps1 -WithFrontend -WindowsTerminal
#
# Si MBA3_START_SEPARATE_WINDOWS=1 (usuario): nunca se usa WT aunque pases -WindowsTerminal (útil si WT está roto).
#
# -SkipFrontend sigue aceptado (equivale al default; fuerza no front aunque uses -WithFrontend).
#
# Ruta del frontend (-WithFrontend): SCNEXUS_FRONT_ROOT, -FrontendRoot, o valor por defecto Mabel.
#
# Termius: no hay API conocida para abrir varias pestañas locales desde un .ps1 dentro de Termius.

param(
    [string]$FrontendRoot = $env:SCNEXUS_FRONT_ROOT,
    [switch]$WithFrontend,
    [switch]$SeparateWindows,
    [switch]$SkipFrontend,
    [switch]$WindowsTerminal
)

$ErrorActionPreference = "Stop"
$BackendRoot = $PSScriptRoot
$SubScript = Join-Path $BackendRoot "scripts\dev-terminal.ps1"
$VenvActivate = Join-Path $BackendRoot ".venv\Scripts\Activate.ps1"

if (-not (Test-Path -LiteralPath $SubScript)) {
    Write-Error "No se encontró: $SubScript"
}
if (-not (Test-Path -LiteralPath $VenvActivate)) {
    Write-Error "No existe el entorno virtual: $VenvActivate`nCrea el venv en la raíz del proyecto antes de arrancar."
}

# Frontend solo si -WithFrontend; -SkipFrontend explícito gana sobre -WithFrontend.
$includeFrontend = [bool]$WithFrontend
if ($PSBoundParameters.ContainsKey("SkipFrontend") -and $SkipFrontend) {
    $includeFrontend = $false
}
$SkipFrontend = -not $includeFrontend

if ($WindowsTerminal -and $SeparateWindows) {
    Write-Warning "-WindowsTerminal no aplica junto con -SeparateWindows (se usan ventanas sueltas)."
}

# Por defecto: ventanas sueltas. -WindowsTerminal pide pestañas en WT. -SeparateWindows es explícito (mismo default).
$effectiveSeparateWindows = $true
if ($SeparateWindows) {
    $effectiveSeparateWindows = $true
}
elseif ($WindowsTerminal) {
    $effectiveSeparateWindows = $false
}

$envSeparate = $env:MBA3_START_SEPARATE_WINDOWS
if (-not [string]::IsNullOrWhiteSpace($envSeparate) -and $envSeparate.Trim() -in @('1', 'true', 'yes')) {
    $effectiveSeparateWindows = $true
    if ($WindowsTerminal) {
        Write-Host "MBA3_START_SEPARATE_WINDOWS: se ignoran pestañas de Windows Terminal." -ForegroundColor DarkYellow
    }
}

if ($includeFrontend) {
    if ([string]::IsNullOrWhiteSpace($FrontendRoot)) {
        $FrontendRoot = "C:\Users\cortiz\OneDrive - MABEL TRADING S.A\Documents\GitHub\scnexus-front"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot "package.json"))) {
        Write-Warning "No hay package.json en: $FrontendRoot`nDefine SCNEXUS_FRONT_ROOT o -FrontendRoot. Continuando sin pestaña de frontend..."
        $SkipFrontend = $true
        $includeFrontend = $false
    }
}

# Start-Process -ArgumentList (array) no cita automáticamente elementos con espacios al
# construir la línea de comandos del proceso hijo: una ruta con espacios (ej. rutas bajo
# "OneDrive - MABEL TRADING S.A") se parte en varios argumentos y powershell.exe falla al
# resolver -File, cerrando la ventana de inmediato pese a -NoExit.
function ConvertTo-QuotedArg {
    param([string]$Value)
    if ([string]::IsNullOrEmpty($Value)) { return $Value }
    if ($Value -match '\s' -and -not ($Value.StartsWith('"') -and $Value.EndsWith('"'))) {
        return '"' + $Value + '"'
    }
    return $Value
}

function Start-Mba3Window {
    param(
        [Parameter(Mandatory)][ValidateSet("api", "worker", "beat", "frontend")][string]$Mode,
        [string]$FrontendPath
    )
    $title = switch ($Mode) {
        "api" { "MBA3 API" }
        "worker" { "MBA3 Celery worker" }
        "beat" { "MBA3 Celery beat" }
        "frontend" { "scnexus-front" }
    }
    $quotedSubScript = ConvertTo-QuotedArg $SubScript
    if ($Mode -eq "frontend") {
        Start-Process powershell.exe -ArgumentList @(
            "-NoExit",
            "-NoLogo",
            "-ExecutionPolicy", "Bypass",
            "-File", $quotedSubScript,
            "-Mode", "frontend",
            "-FrontendRoot", (ConvertTo-QuotedArg $FrontendPath)
        ) -WorkingDirectory $FrontendPath
    }
    else {
        Start-Process powershell.exe -ArgumentList @(
            "-NoExit",
            "-NoLogo",
            "-ExecutionPolicy", "Bypass",
            "-File", $quotedSubScript,
            "-Mode", $Mode
        ) -WorkingDirectory $BackendRoot
    }
    Write-Host "  Ventana: $title" -ForegroundColor Green
}

function Get-WtExecutable {
    $cmd = Get-Command wt.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:LocalAppData "Microsoft\WindowsApps\wt.exe"),
        "$env:SystemRoot\System32\wt.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

function Add-WtPowerShellTab {
    param(
        [Parameter(Mandatory)][string]$StartingDirectory,
        [Parameter(Mandatory)][string[]]$DevTerminalArgs
    )
    $out = [System.Collections.Generic.List[string]]::new()
    $out.Add("nt")
    $out.Add("-d")
    $out.Add((ConvertTo-QuotedArg $StartingDirectory))
    $out.Add("powershell.exe")
    $out.Add("-NoExit")
    $out.Add("-NoLogo")
    $out.Add("-ExecutionPolicy")
    $out.Add("Bypass")
    $out.Add("-File")
    $out.Add((ConvertTo-QuotedArg $SubScript))
    foreach ($a in $DevTerminalArgs) { $out.Add((ConvertTo-QuotedArg $a)) }
    return $out.ToArray()
}

function Add-WtTabToArgumentList {
    param(
        [Parameter(Mandatory)]$ArgumentList,
        [Parameter(Mandatory)][string]$StartingDirectory,
        [Parameter(Mandatory)][string[]]$DevTerminalArgs
    )
    foreach ($part in (Add-WtPowerShellTab $StartingDirectory $DevTerminalArgs)) {
        [void]$ArgumentList.Add([string]$part)
    }
}

function Start-Mba3WindowsTerminal {
    $wtExe = Get-WtExecutable
    if (-not $wtExe) {
        Write-Error "No se encontró wt.exe (Windows Terminal). Instálalo desde Microsoft Store o ejecuta sin -WindowsTerminal (por defecto: ventanas sueltas)."
    }
    $wtArgumentList = [System.Collections.Generic.List[string]]::new()
    $wtArgumentList.Add("-w")
    $wtArgumentList.Add("0")
    Add-WtTabToArgumentList -ArgumentList $wtArgumentList -StartingDirectory $BackendRoot -DevTerminalArgs @("-Mode", "api")
    $wtArgumentList.Add(";")
    Add-WtTabToArgumentList -ArgumentList $wtArgumentList -StartingDirectory $BackendRoot -DevTerminalArgs @("-Mode", "worker")
    $wtArgumentList.Add(";")
    Add-WtTabToArgumentList -ArgumentList $wtArgumentList -StartingDirectory $BackendRoot -DevTerminalArgs @("-Mode", "beat")
    if (-not $SkipFrontend) {
        $wtArgumentList.Add(";")
        Add-WtTabToArgumentList -ArgumentList $wtArgumentList -StartingDirectory $FrontendRoot -DevTerminalArgs @("-Mode", "frontend", "-FrontendRoot", $FrontendRoot)
    }
    Write-Host "  Iniciando Windows Terminal: $wtExe" -ForegroundColor Green
    Start-Process -FilePath $wtExe -ArgumentList $wtArgumentList.ToArray()
}

$useWindowsTerminal = -not $effectiveSeparateWindows
if ($useWindowsTerminal -and -not (Get-WtExecutable)) {
    Write-Warning "No se encontró Windows Terminal (wt.exe). Abriendo ventanas de PowerShell sueltas. Instala o repara WT desde Microsoft Store; luego puedes usar .\start-all-dev.ps1 -WindowsTerminal para pestañas."
    $useWindowsTerminal = $false
}

Write-Host ""
Write-Host "Abriendo desarrollo (backend + Celery)..." -ForegroundColor Cyan
if ($useWindowsTerminal) {
    Start-Mba3WindowsTerminal
}
else {
    Start-Mba3Window -Mode "api"
    Start-Mba3Window -Mode "worker"
    Start-Mba3Window -Mode "beat"
    if (-not $SkipFrontend) {
        Start-Mba3Window -Mode "frontend" -FrontendPath $FrontendRoot
    }
}
Write-Host ""
if ($useWindowsTerminal) {
    $tabCount = $(if ($SkipFrontend) { 3 } else { 4 })
    Write-Host "Listo. Windows Terminal con $tabCount pestaña(s). Frontend: arranca aparte en el repo del front con: npm run dev" -ForegroundColor Gray
}
else {
    Write-Host "Listo. Ventanas sueltas de PowerShell (cierra cada una para detener ese proceso). Redis/Docker aparte." -ForegroundColor Gray
    Write-Host "Para pestañas en un solo programa: .\start-all-dev.ps1 -WindowsTerminal (requiere Windows Terminal operativo)." -ForegroundColor DarkGray
}
Write-Host ""
