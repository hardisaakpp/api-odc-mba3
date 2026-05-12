# Arranca API + Celery worker + Celery beat en una sola ventana de Windows Terminal (3 pestañas).
# El frontend (Vite) no se incluye por defecto: suele fallar en ventanas hijas; arráncalo aparte con npm run dev.
#
# Uso (desde la raíz del repo):
#   .\start-all-dev.ps1                          # WT, 3 pestañas (recomendado)
#   .\start-all-dev.ps1 -SeparateWindows         # 3 ventanas de PowerShell sueltas (comportamiento antiguo sin WT)
#   .\start-all-dev.ps1 -WithFrontend            # WT con 4ª pestaña para npm (opcional, puede cerrarse si falla)
#   .\start-all-dev.ps1 -WithFrontend -SeparateWindows   # 4 ventanas sueltas
#
# Compatibilidad: -WindowsTerminal sigue aceptado (redundante; el modo por defecto ya es WT).
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

if ($PSBoundParameters.ContainsKey("WindowsTerminal")) {
    if ($WindowsTerminal -and $SeparateWindows) {
        Write-Warning "-WindowsTerminal no aplica junto con -SeparateWindows (se usan ventanas sueltas)."
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
    if ($Mode -eq "frontend") {
        Start-Process powershell.exe -ArgumentList @(
            "-NoExit",
            "-NoLogo",
            "-ExecutionPolicy", "Bypass",
            "-File", $SubScript,
            "-Mode", "frontend",
            "-FrontendRoot", $FrontendPath
        ) -WorkingDirectory $FrontendPath
    }
    else {
        Start-Process powershell.exe -ArgumentList @(
            "-NoExit",
            "-NoLogo",
            "-ExecutionPolicy", "Bypass",
            "-File", $SubScript,
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
    $out.Add($StartingDirectory)
    $out.Add("powershell.exe")
    $out.Add("-NoExit")
    $out.Add("-NoLogo")
    $out.Add("-ExecutionPolicy")
    $out.Add("Bypass")
    $out.Add("-File")
    $out.Add($SubScript)
    foreach ($a in $DevTerminalArgs) { $out.Add($a) }
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
        Write-Error "No se encontró wt.exe (Windows Terminal). Instálalo o usa -SeparateWindows."
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

# Por defecto: pestañas en WT. -SeparateWindows fuerza consolas sueltas. -WindowsTerminal (legado) no cambia el default.
$useWindowsTerminal = -not $SeparateWindows
if ($useWindowsTerminal -and -not (Get-WtExecutable)) {
    Write-Warning "No se encontró Windows Terminal (wt.exe). Abriendo ventanas de PowerShell sueltas. Instala WT desde Microsoft Store para usar pestañas."
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
    Write-Host "Para pestañas en un solo programa: instala Windows Terminal y ejecuta sin -SeparateWindows." -ForegroundColor DarkGray
}
Write-Host ""
