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

# 2. Test Endpoint
Write-Host "2. TEST ENDPOINT" -ForegroundColor Magenta
Test-Endpoint -Name "Test Endpoint" -Uri "http://localhost:8000/test" -Method "Post" -Body @{texto = "Prueba desde PowerShell"}
Start-Sleep -Seconds 1

# 3. Validar Consulta SQL
Write-Host "3. VALIDAR CONSULTA SQL (POST /query)" -ForegroundColor Magenta
Test-Endpoint -Name "Validar Query" -Uri "http://localhost:8000/query" -Method "Post" -Body @{
    query = "SELECT CODIGO_FACTURA, NUMERO_FACTURA FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'"
}
Start-Sleep -Seconds 1

# 4. Ejecutar Consulta SQL (POST)
Write-Host "4. EJECUTAR CONSULTA SQL (POST /consulta)" -ForegroundColor Magenta
Test-Endpoint -Name "Ejecutar Consulta POST" -Uri "http://localhost:8000/consulta" -Method "Post" -Body @{
    query = "SELECT CODIGO_FACTURA, NUMERO_FACTURA, EMPRESA FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'"
}
Start-Sleep -Seconds 2

# 5. Consultar Despachos
Write-Host "5. CONSULTAR DESPACHOS (GET /consultar)" -ForegroundColor Magenta
Test-Endpoint -Name "Consultar Despachos" -Uri "http://localhost:8000/consultar" -Method "Get"
Start-Sleep -Seconds 2

# 6. Migrar Despachos
Write-Host "6. MIGRAR DESPACHOS (GET /migrar)" -ForegroundColor Magenta
Test-Endpoint -Name "Migrar Despachos" -Uri "http://localhost:8000/migrar" -Method "Get"
Start-Sleep -Seconds 2

# 7. Consultar Facturas
Write-Host "7. CONSULTAR FACTURAS (GET /facturas)" -ForegroundColor Magenta
Test-Endpoint -Name "Consultar Facturas" -Uri "http://localhost:8000/facturas" -Method "Get"
Start-Sleep -Seconds 1

# 8. Consultar Facturas con Filtros
Write-Host "8. CONSULTAR FACTURAS CON FILTROS" -ForegroundColor Magenta
Test-Endpoint -Name "Facturas con Filtros" -Uri "http://localhost:8000/facturas?anulada=false&confirmado=true&remision_facturada=false" -Method "Get"
Start-Sleep -Seconds 1

# 9. Consultar SAP (si está habilitado)
Write-Host "9. CONSULTAR SAP" -ForegroundColor Magenta
Test-Endpoint -Name "Consultar SAP" -Uri "http://localhost:8000/sap/test?sku=5-0012.9" -Method "Get"
Start-Sleep -Seconds 1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PRUEBAS COMPLETADAS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

