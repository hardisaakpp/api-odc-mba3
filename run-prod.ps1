$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

$env:ENVIRONMENT = "production"
Write-Host "ENVIRONMENT=$($env:ENVIRONMENT)" -ForegroundColor Cyan

& "$ProjectRoot\start_api.ps1"
