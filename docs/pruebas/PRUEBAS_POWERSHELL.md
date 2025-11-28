# Guía de Pruebas - Comandos PowerShell

## Comandos para PowerShell (Windows)

### 1. Health Check

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
```

### 2. Consultar Despachos (GET /consultar)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/consultar" -Method Get
```

### 3. Migrar Despachos (GET /migrar)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/migrar" -Method Get
```

### 4. Procesar Orden de Compra (GET /procesar-oc)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/procesar-oc" -Method Get
```

### 5. Proceso Completo (GET /pruebas)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/pruebas" -Method Get
```

### 6. Consultar Facturas (GET /facturas)

```powershell
# Sin filtros
Invoke-RestMethod -Uri "http://localhost:8000/facturas" -Method Get

# Con filtros
Invoke-RestMethod -Uri "http://localhost:8000/facturas?anulada=false&confirmado=true&remision_facturada=false" -Method Get
```

### 7. Consultar SAP

```powershell
# Con cache
Invoke-RestMethod -Uri "http://localhost:8000/sap/test?sku=5-0012.9" -Method Get

# Directo (sin cache)
Invoke-RestMethod -Uri "http://localhost:8000/sap/test/direct?sku=5-0012.9" -Method Get
```

### 8. Integrar con SAP (POST /integrar-sap)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/integrar-sap" -Method Post
```

## Ver resultados formateados

Para ver los resultados en formato JSON legible:

```powershell
$result = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
$result | ConvertTo-Json -Depth 10
```

