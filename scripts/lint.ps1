<#
.SYNOPSIS
    Ejecuta comprobaciones estáticas (Ruff + Pyright) sobre el código.

.DESCRIPTION
    Uso previsto: máquina de desarrollo o agente local. La imagen Docker / producción no ejecuta
    este script ni instala requirements-dev.txt. La opción -Fix modifica archivos: solo en desarrollo.

    Activa el primer intérprete disponible (.venv o venv) y corre:
      - ruff check
      - pyright (usa pyrightconfig.json del repo)

    Ejemplos:
      .\scripts\lint.ps1
      .\scripts\lint.ps1 -Paths src/database/services,tests/test_retry_utils.py
      .\scripts\lint.ps1 -SkipPyright
#>
param(
    [string[]]$Paths = @("src", "tests"),
    [switch]$SkipPyright,
    [switch]$Fix
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$venvPython = $null
foreach ($dir in @(".venv", "venv")) {
    $candidate = Join-Path $Root "$dir/Scripts/python.exe"
    if (Test-Path $candidate) {
        $venvPython = $candidate
        break
    }
}

if (-not $venvPython) {
    Write-Warning "No se encontró .venv\Scripts\python.exe ni venv\Scripts\python.exe; se usa python del PATH."
    $venvPython = "python"
}

Write-Host "==> Ruff ($(Join-Path $Root 'pyproject.toml'))" -ForegroundColor Cyan
$ruffArgs = @("check") + $Paths
if ($Fix) { $ruffArgs += "--fix" }
& $venvPython -m ruff @ruffArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $SkipPyright) {
    Write-Host "==> Pyright (pyrightconfig.json)" -ForegroundColor Cyan
    & $venvPython -m pyright
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "OK: lint terminado sin errores." -ForegroundColor Green
