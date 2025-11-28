# Script de Pruebas para Endpoints - PowerShell
# Ejecutar: .\docs\pruebas\test_endpoints.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PRUEBAS DE ENDPOINTS - MBA3 Consultas" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Función para probar endpoint
function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Uri,
        [string]$Method = "Get",
        [hashtable]$Body = $null
    )
    
    Write-Host "[TEST] $Name" -ForegroundColor Yellow
    Write-Host "  URI: $Uri" -ForegroundColor Gray
    Write-Host "  Method: $Method" -ForegroundColor Gray
    
    try {
        if ($Body) {
            $jsonBody = $Body | ConvertTo-Json
            Write-Host "  Body: $jsonBody" -ForegroundColor Gray
            $result = Invoke-RestMethod -Uri $Uri -Method $Method -Body $jsonBody -ContentType "application/json"
        } else {
            $result = Invoke-RestMethod -Uri $Uri -Method $Method
        }
        
        Write-Host "  ✅ ÉXITO" -ForegroundColor Green
        Write-Host "  Resultado:" -ForegroundColor Gray
        $result | ConvertTo-Json -Depth 5 | Write-Host
        Write-Host ""
        return $result
    } catch {
        Write-Host "  ❌ ERROR: $($_.Exception.Message)" -ForegroundColor Red
        if ($_.ErrorDetails.Message) {
            Write-Host "  Detalles: $($_.ErrorDetails.Message)" -ForegroundColor Red
        }
        Write-Host ""
        return $null
    }
}

# 1. Health Check
Write-Host "1. HEALTH CHECK" -ForegroundColor Magenta
Test-Endpoint -Name "Health Check" -Uri "http://localhost:8000/health" -Method "Get"
Start-Sleep -Seconds 1

# 2. Consultar Despachos
Write-Host "2. CONSULTAR DESPACHOS (GET /consultar)" -ForegroundColor Magenta
Test-Endpoint -Name "Consultar Despachos" -Uri "http://localhost:8000/consultar" -Method "Get"
Start-Sleep -Seconds 2

# 3. Migrar Despachos
Write-Host "3. MIGRAR DESPACHOS (GET /migrar)" -ForegroundColor Magenta
Test-Endpoint -Name "Migrar Despachos" -Uri "http://localhost:8000/migrar" -Method "Get"
Start-Sleep -Seconds 2

# 4. Procesar Orden de Compra
Write-Host "4. PROCESAR ORDEN DE COMPRA (GET /procesar-oc)" -ForegroundColor Magenta
Test-Endpoint -Name "Procesar OC" -Uri "http://localhost:8000/procesar-oc" -Method "Get"
Start-Sleep -Seconds 2

# 5. Proceso Completo
Write-Host "5. PROCESO COMPLETO (GET /pruebas)" -ForegroundColor Magenta
Test-Endpoint -Name "Proceso Completo" -Uri "http://localhost:8000/pruebas" -Method "Get"
Start-Sleep -Seconds 2

# 6. Consultar Facturas
Write-Host "6. CONSULTAR FACTURAS (GET /facturas)" -ForegroundColor Magenta
Test-Endpoint -Name "Consultar Facturas" -Uri "http://localhost:8000/facturas" -Method "Get"
Start-Sleep -Seconds 1

# 7. Consultar Facturas con Filtros
Write-Host "7. CONSULTAR FACTURAS CON FILTROS" -ForegroundColor Magenta
Test-Endpoint -Name "Facturas con Filtros" -Uri "http://localhost:8000/facturas?anulada=false&confirmado=true&remision_facturada=false" -Method "Get"
Start-Sleep -Seconds 1

# 8. Consultar SAP (si está habilitado)
Write-Host "8. CONSULTAR SAP" -ForegroundColor Magenta
Test-Endpoint -Name "Consultar SAP" -Uri "http://localhost:8000/sap/test?sku=5-0012.9" -Method "Get"
Start-Sleep -Seconds 1

# 9. Integrar con SAP
Write-Host "9. INTEGRAR CON SAP (POST /integrar-sap)" -ForegroundColor Magenta
Test-Endpoint -Name "Integrar SAP" -Uri "http://localhost:8000/integrar-sap" -Method "Post"
Start-Sleep -Seconds 1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PRUEBAS COMPLETADAS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

