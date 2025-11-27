# Guía de Pruebas - Comandos PowerShell

## Comandos para PowerShell (Windows)

### 1. Health Check

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
```

### 2. Test Endpoint

```powershell
$body = @{texto = "Prueba de comunicación"} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/test" -Method Post -Body $body -ContentType "application/json"
```

### 3. Validar Consulta SQL (POST /query)

```powershell
$body = @{query = "SELECT CODIGO_FACTURA, NUMERO_FACTURA FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'"} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/query" -Method Post -Body $body -ContentType "application/json"
```

### 4. Ejecutar Consulta SQL (POST /consulta)

```powershell
$body = @{query = "SELECT CODIGO_FACTURA, NUMERO_FACTURA, EMPRESA FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'"} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/consulta" -Method Post -Body $body -ContentType "application/json"
```

### 5. Consultar Despachos (GET /consultar)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/consultar" -Method Get
```

### 6. Migrar Despachos (GET /migrar)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/migrar" -Method Get
```

### 7. Procesar Orden de Compra (GET /procesar-oc)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/procesar-oc" -Method Get
```

### 8. Proceso Completo (GET /pruebas)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/pruebas" -Method Get
```

### 9. Consultar Facturas (GET /facturas)

```powershell
# Sin filtros
Invoke-RestMethod -Uri "http://localhost:8000/facturas" -Method Get

# Con filtros
Invoke-RestMethod -Uri "http://localhost:8000/facturas?anulada=false&confirmado=true&remision_facturada=false" -Method Get
```

### 10. Consultar SAP

```powershell
# Con cache
Invoke-RestMethod -Uri "http://localhost:8000/sap/test?sku=5-0012.9" -Method Get

# Directo (sin cache)
Invoke-RestMethod -Uri "http://localhost:8000/sap/test/direct?sku=5-0012.9" -Method Get
```

### 11. GET /consulta con query parameter

```powershell
$query = "SELECT CODIGO_FACTURA,NUMERO_FACTURA FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'"
$encodedQuery = [System.Web.HttpUtility]::UrlEncode($query)
Invoke-RestMethod -Uri "http://localhost:8000/consulta?query=$encodedQuery" -Method Get
```

## Alternativa: Usar curl.exe (si está disponible)

Si prefieres usar curl estilo Unix, puedes usar `curl.exe`:

```powershell
curl.exe -X POST "http://localhost:8000/test" -H "Content-Type: application/json" -d '{\"texto\": \"Prueba\"}'
```

## Ver resultados formateados

Para ver los resultados en formato JSON legible:

```powershell
$result = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
$result | ConvertTo-Json -Depth 10
```

