# Ventana única del stack local. Invocado por ..\start-all-dev.ps1
param(
    [Parameter(Mandatory)]
    [ValidateSet("api", "worker", "beat", "frontend")]
    [string]$Mode,
    [string]$FrontendRoot
)

$ErrorActionPreference = "Stop"
$BackendRoot = Split-Path $PSScriptRoot -Parent
$VenvActivate = Join-Path $BackendRoot ".venv\Scripts\Activate.ps1"

function Merge-RegistryPathIntoProcessPath {
    foreach ($scope in @("Machine", "User")) {
        $chunk = [Environment]::GetEnvironmentVariable("Path", $scope)
        if ($chunk) { $env:Path = "$chunk;$env:Path" }
    }
    $env:Path = ($env:Path -split ";" | Where-Object { $_ } | Select-Object -Unique) -join ";"
}

function Import-CommonPowerShellProfiles {
    $names = @("Microsoft.PowerShell_profile.ps1", "Microsoft.VSCode_profile.ps1", "profile.ps1")
    foreach ($n in $names) {
        foreach ($dir in @(
                (Join-Path $HOME "Documents\PowerShell"),
                (Join-Path $HOME "Documents\WindowsPowerShell"),
                (Join-Path $HOME "OneDrive\Documents\PowerShell"),
                (Join-Path $HOME "OneDrive - MABEL TRADING S.A\Documents\PowerShell")
            )) {
            $f = Join-Path $dir $n
            if (Test-Path -LiteralPath $f) {
                try { . $f } catch { }
            }
        }
    }
}

function Resolve-NpmExecutable {
    Merge-RegistryPathIntoProcessPath
    foreach ($name in @("npm.cmd", "npm.exe")) {
        $cmd = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) { return $cmd.Source }
    }
    # Si un perfil hace exit o falla en host no interactivo: $env:MBA3_DEV_SKIP_POWERSHELL_PROFILES=1
    if (-not $env:MBA3_DEV_SKIP_POWERSHELL_PROFILES) {
        Import-CommonPowerShellProfiles
    }
    foreach ($name in @("npm.cmd", "npm.exe")) {
        $cmd = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) { return $cmd.Source }
    }
    foreach ($p in @(
            (Join-Path ${env:ProgramFiles} "nodejs\npm.cmd"),
            (Join-Path ${env:ProgramFiles(x86)} "nodejs\npm.cmd")
        )) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

function Write-FrontendDevDiagnostics {
    param([string]$NpmPath, [string]$ProjectRoot)
    Write-Host "Directorio: $ProjectRoot" -ForegroundColor Gray
    $nodeDir = Split-Path -Parent $NpmPath
    $nodeExe = Join-Path $nodeDir "node.exe"
    if (Test-Path -LiteralPath $nodeExe) {
        try {
            $nv = & $nodeExe --version 2>&1
            Write-Host "Node: $nv ($nodeExe)" -ForegroundColor Gray
        }
        catch {
            Write-Host "Node: no se pudo ejecutar $nodeExe" -ForegroundColor Yellow
        }
    }
    else {
        $nodeApp = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($nodeApp) {
            try {
                $nv = & $nodeApp.Source --version 2>&1
                Write-Host "Node: $nv ($($nodeApp.Source))" -ForegroundColor Gray
            }
            catch { }
        }
        else {
            Write-Host "Node: no encontrado junto a npm ni en PATH" -ForegroundColor Yellow
        }
    }
    try {
        $npmv = & $NpmPath --version 2>&1
        Write-Host "npm: $npmv" -ForegroundColor Gray
    }
    catch {
        Write-Host "npm: no se pudo leer la versión" -ForegroundColor Yellow
    }
    Write-Host ""
}

$Host.UI.RawUI.WindowTitle = switch ($Mode) {
    "api" { "MBA3: API" }
    "worker" { "MBA3: Celery worker" }
    "beat" { "MBA3: Celery beat" }
    "frontend" { "scnexus-front: npm run dev" }
}

switch ($Mode) {
    "frontend" {
        if (-not $FrontendRoot) {
            Write-Error "Modo frontend sin ruta (usa start-all-dev.ps1)."
        }
        if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot "package.json"))) {
            Write-Warning "No se encontró package.json en: $FrontendRoot"
        }
        Set-Location -LiteralPath $FrontendRoot
        $npm = Resolve-NpmExecutable
        if (-not $npm) {
            Write-Host "No se encontró npm (Node.js). Revisa PATH o instala Node." -ForegroundColor Red
            Write-Host "Ruta del proyecto: $FrontendRoot" -ForegroundColor Gray
            Write-Host "PATH actual (primeros 800 caracteres):" -ForegroundColor Gray
            $pathShow = if ([string]::IsNullOrEmpty($env:Path)) { "(vacío)" } else { $env:Path.Substring(0, [Math]::Min(800, $env:Path.Length)) }
            Write-Host $pathShow -ForegroundColor Gray
            $null = Read-Host "Pulsa Enter para cerrar"
            return
        }
        Write-Host "Usando npm: $npm" -ForegroundColor DarkGray
        Write-FrontendDevDiagnostics -NpmPath $npm -ProjectRoot $FrontendRoot

        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & $npm run dev
        }
        finally {
            $ErrorActionPreference = $prevEap
        }

        $exit = $LASTEXITCODE
        if ($null -ne $exit -and $exit -ne 0) {
            Write-Host ""
            Write-Host "npm run dev terminó con código de salida $exit (revisa puerto en uso, .env o ejecuta 'npm install' en esta carpeta)." -ForegroundColor Red
            Write-Host "Si el error fue muy breve, prueba en esta misma carpeta: npm run dev" -ForegroundColor Gray
            $null = Read-Host "Pulsa Enter para cerrar esta ventana"
        }
        return
    }
    Default {
        if (-not (Test-Path -LiteralPath $VenvActivate)) {
            Write-Error "No existe el venv: $VenvActivate"
        }
        Set-Location -LiteralPath $BackendRoot
        & $VenvActivate
        switch ($Mode) {
            "api" {
                $env:ENVIRONMENT = "development"
                & (Join-Path $BackendRoot "run-dev.ps1")
            }
            "worker" {
                celery -A src.celery_app worker --loglevel=info --pool=solo
            }
            "beat" {
                celery -A src.celery_app beat --loglevel=info
            }
        }
    }
}
