# Script para registrar permisos del módulo MBA3 Consultas en el Core
# Uso: .\registrar_permisos_core.ps1 -CoreUrl "http://localhost:5000" -AdminToken "tu-token-jwt"

param(
    [Parameter(Mandatory=$true)]
    [string]$CoreUrl = "http://localhost:5000",
    
    [Parameter(Mandatory=$true)]
    [string]$AdminToken,
    
    [Parameter(Mandatory=$false)]
    [string]$RoleName = "Ventas"
)

$headers = @{
    "Authorization" = "Bearer $AdminToken"
    "Content-Type" = "application/json"
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Registro de Permisos MBA3 Consultas" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Permisos a registrar
$permisos = @(
    @{
        key = "mba3-consultas.facturas.view"
        description = "Ver facturas MBA3"
        module = "mba3-consultas"
    },
    @{
        key = "mba3-consultas.proceso.execute"
        description = "Ejecutar procesos MBA3 (consultar, migrar, procesar OC, integrar SAP)"
        module = "mba3-consultas"
    },
    @{
        key = "mba3-consultas.ordenes-compra.view"
        description = "Ver órdenes de compra"
        module = "mba3-consultas"
    }
)

$permissionIds = @()

# Paso 1: Registrar permisos
Write-Host "Paso 1: Registrando permisos..." -ForegroundColor Yellow
Write-Host ""

foreach ($permiso in $permisos) {
    Write-Host "Registrando: $($permiso.key)" -ForegroundColor Green
    
    $body = $permiso | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "$CoreUrl/api/permissions" `
            -Method POST `
            -Headers $headers `
            -Body $body `
            -ErrorAction Stop
        
        $permissionId = $response.id
        $permissionIds += $permissionId
        
        Write-Host "  ✅ Permiso registrado con ID: $permissionId" -ForegroundColor Green
        Write-Host ""
    }
    catch {
        if ($_.Exception.Response.StatusCode -eq 409) {
            Write-Host "  ⚠️  Permiso ya existe, obteniendo ID..." -ForegroundColor Yellow
            # Intentar obtener el permiso existente
            try {
                $getResponse = Invoke-RestMethod -Uri "$CoreUrl/api/permissions" `
                    -Method GET `
                    -Headers $headers `
                    -ErrorAction Stop
                
                $existingPermiso = $getResponse | Where-Object { $_.key -eq $permiso.key }
                if ($existingPermiso) {
                    $permissionIds += $existingPermiso.id
                    Write-Host "  ✅ Permiso encontrado con ID: $($existingPermiso.id)" -ForegroundColor Green
                }
            }
            catch {
                Write-Host "  ❌ Error al obtener permiso existente: $($_.Exception.Message)" -ForegroundColor Red
            }
        }
        else {
            Write-Host "  ❌ Error al registrar permiso: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "  Detalles: $($_.Exception.Response)" -ForegroundColor Red
        }
        Write-Host ""
    }
}

# Paso 2: Asignar permisos a rol
Write-Host "Paso 2: Asignando permisos al rol '$RoleName'..." -ForegroundColor Yellow
Write-Host ""

foreach ($permissionId in $permissionIds) {
    Write-Host "Asignando permiso ID: $permissionId" -ForegroundColor Green
    
    $assignBody = @{
        roleName = $RoleName
        permissionId = $permissionId
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "$CoreUrl/api/permissions/assign" `
            -Method POST `
            -Headers $headers `
            -Body $assignBody `
            -ErrorAction Stop
        
        Write-Host "  ✅ Permiso asignado exitosamente" -ForegroundColor Green
        Write-Host ""
    }
    catch {
        if ($_.Exception.Response.StatusCode -eq 409) {
            Write-Host "  ⚠️  Permiso ya está asignado a este rol" -ForegroundColor Yellow
        }
        else {
            Write-Host "  ❌ Error al asignar permiso: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "  Detalles: $($_.Exception.Response)" -ForegroundColor Red
        }
        Write-Host ""
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ Proceso completado" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "⚠️  IMPORTANTE: Los usuarios deben hacer login nuevamente" -ForegroundColor Yellow
Write-Host "   para obtener tokens con los nuevos permisos." -ForegroundColor Yellow
Write-Host ""











