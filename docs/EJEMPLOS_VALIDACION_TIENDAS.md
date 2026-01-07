# Ejemplos Prácticos: Validación de Tiendas contra SAP

## Escenario 1: ✅ Validación EXITOSA

### Excel de Entrada
**Hoja: Movimiento**
```
| CODIGO PRODUCTO | TIENDAS | CANTIDAD |
|-----------------|---------|----------|
| MTF123.9        | ROL01   | 10       |
| MTF456.2        | ROL02   | 15       |
| MTF789.5        | ROL03   | 20       |
```

### Proceso
```
1. Parsear Excel
2. Extraer tiendas únicas: ["ROL01", "ROL02", "ROL03"]
3. Consultar SAP OWHS
   - ROL01: ✅ ENCONTRADA (ROLAND QUICENTRO NORTE)
   - ROL02: ✅ ENCONTRADA (ROLAND CC EL BOSQUE)
   - ROL03: ✅ ENCONTRADA (ROLAND IÑAQUITO)
4. Todas válidas → Continuar con validaciones
5. Guardar pedido en BD
```

### Respuesta HTTP 200 OK
```json
{
    "status": "success",
    "message": "Plantilla procesada y guardada exitosamente",
    "pedido_id": "PED-20250107-A1B2C3",
    "formato_detectado": "cuatro_hojas_v1_0",
    "articulos_cargados": 3,
    "distribuciones_cargadas": 3,
    "validacion_tiendas_sap": {
        "total_codigos": 3,
        "validas": 3,
        "no_encontradas": 0,
        "errores": 0,
        "warnings": 0,
        "todas_validas": true
    },
    "validation": {
        "valid": true,
        "total_issues": 0,
        "errors": 0,
        "warnings": 0
    },
    "file_info": {
        "filename": "Pedido_Enero_2025.xlsx",
        "size_mb": 0.52
    }
}
```

---

## Escenario 2: ❌ Validación FALLA - Tienda no existe

### Excel de Entrada
**Hoja: Movimiento**
```
| CODIGO PRODUCTO | TIENDAS | CANTIDAD |
|-----------------|---------|----------|
| MTF123.9        | ROL01   | 10       |
| MTF456.2        | ROL99   | 15       |  ← TIENDA INVÁLIDA
| MTF789.5        | ROL03   | 20       |
```

### Proceso
```
1. Parsear Excel
2. Extraer tiendas únicas: ["ROL01", "ROL99", "ROL03"]
3. Consultar SAP OWHS
   - ROL01: ✅ ENCONTRADA
   - ROL99: ❌ NO ENCONTRADA
   - ROL03: ✅ ENCONTRADA
4. Hay tiendas inválidas + sap_obligatorio=true
   → RECHAZAR CARGA
5. NO guardar pedido
```

### Respuesta HTTP 400 Bad Request
```json
{
    "status": "validation_error",
    "message": "No se puede procesar la plantilla: existen tiendas (ID TIENDA) no válidas en SAP. Tiendas no encontradas en SAP OWHS: ROL99",
    "pedido_id": null,
    "formato_detectado": "cuatro_hojas_v1_0",
    "articulos_cargados": 0,
    "distribuciones_cargadas": 0,
    "validacion_tiendas_sap": {
        "total_codigos": 3,
        "validas": 2,
        "no_encontradas": 1,
        "errores": 0,
        "warnings": 0,
        "todas_validas": false
    },
    "errores": [
        "No se puede procesar la plantilla: existen tiendas (ID TIENDA) no válidas en SAP. Tiendas no encontradas en SAP OWHS: ROL99"
    ],
    "file_info": {
        "filename": "Pedido_Enero_2025.xlsx",
        "size_mb": 0.52
    }
}
```

### Acciones del Usuario
```
1. Ver la respuesta: "ROL99 no encontrada"
2. Abrir Excel
3. Cambiar ROL99 por tienda válida (ej: ROL02)
4. Guardar Excel
5. Subir nuevamente

↓ (Segunda intención)

1. Parsear Excel
2. Tiendas: ["ROL01", "ROL02", "ROL03"]
3. Todas encontradas en SAP ✅
4. Procesar normalmente
```

---

## Escenario 3: ⚠️ Validación CON WARNING - No obligatoria

### Configuración
```bash
POST /api/plantillas/upload?sap_obligatorio=false
```

### Excel de Entrada (mismo que Escenario 2)
```
| CODIGO PRODUCTO | TIENDAS | CANTIDAD |
|-----------------|---------|----------|
| MTF123.9        | ROL01   | 10       |
| MTF456.2        | ROL99   | 15       |  ← TIENDA INVÁLIDA
| MTF789.5        | ROL03   | 20       |
```

### Proceso
```
1. Parsear Excel
2. Extraer tiendas: ["ROL01", "ROL99", "ROL03"]
3. Validar contra SAP
   - ROL01: ✅ ENCONTRADA
   - ROL99: ❌ NO ENCONTRADA
   - ROL03: ✅ ENCONTRADA
4. Hay tiendas inválidas pero sap_obligatorio=false
   → CONTINUAR (registrar como WARNING)
5. Guardar pedido (con warnings en respuesta)
```

### Respuesta HTTP 200 OK (con warnings)
```json
{
    "status": "success",
    "message": "Plantilla procesada y guardada exitosamente",
    "pedido_id": "PED-20250107-D4E5F6",
    "formato_detectado": "cuatro_hojas_v1_0",
    "validacion_tiendas_sap": {
        "total_codigos": 3,
        "validas": 2,
        "no_encontradas": 1,
        "errores": 0,
        "warnings": 0,
        "todas_validas": false
    },
    "warnings": [
        "⚠️ La tienda 'ROL99' no existe en SAP OWHS (modo no obligatorio)"
    ],
    "validation": {
        "valid": true,
        "total_issues": 1,
        "errors": 0,
        "warnings": 1
    }
}
```

---

## Escenario 4: ❌ Múltiples tiendas inválidas

### Excel de Entrada
```
| CODIGO PRODUCTO | TIENDAS | CANTIDAD |
|-----------------|---------|----------|
| MTF123.9        | ROL01   | 10       |
| MTF456.2        | ROL98   | 15       |  ← INVÁLIDA
| MTF789.5        | ROL99   | 20       |  ← INVÁLIDA
| MTF999.1        | ROL97   | 25       |  ← INVÁLIDA
| MTF555.3        | ROL02   | 30       |
```

### Respuesta HTTP 400 Bad Request
```json
{
    "status": "validation_error",
    "message": "No se puede procesar la plantilla: existen tiendas (ID TIENDA) no válidas en SAP. Tiendas no encontradas en SAP OWHS: ROL97, ROL98, ROL99",
    "validacion_tiendas_sap": {
        "total_codigos": 5,
        "validas": 2,
        "no_encontradas": 3,
        "errores": 0,
        "warnings": 0,
        "todas_validas": false
    },
    "errores": [
        "No se puede procesar la plantilla: existen tiendas (ID TIENDA) no válidas en SAP. Tiendas no encontradas en SAP OWHS: ROL97, ROL98, ROL99"
    ]
}
```

---

## Escenario 5: Error de Conexión SAP

### Contexto
- SAP está temporalmente no disponible
- `sap_obligatorio=true`

### Proceso
```
1. Parsear Excel
2. Extraer tiendas: ["ROL01", "ROL02"]
3. Intentar conectar a SAP
4. ❌ Error de conexión (timeout, conexión rechazada, etc.)
5. No se puede obtener catálogo SAP
6. sap_obligatorio=true → RECHAZAR
```

### Respuesta HTTP 400 Bad Request
```json
{
    "status": "validation_error",
    "message": "No se puede procesar la plantilla: existen tiendas (ID TIENDA) no válidas en SAP. Errores al consultar SAP: Connection refused",
    "validacion_tiendas_sap": {
        "total_codigos": 2,
        "validas": 0,
        "no_encontradas": 0,
        "errores": 2,
        "warnings": 0,
        "todas_validas": false
    }
}
```

### Acciones del Usuario
```
1. Ver error: "Error de conexión a SAP"
2. Esperar a que SAP esté disponible
3. Reintentar la carga
```

---

## Escenario 6: Formato SIMPLE (CodigoProducto, IdTienda, Cantidad)

### Excel de Entrada
```
| CodigoProducto | IdTienda | Cantidad |
|----------------|----------|----------|
| MTF123.9       | ROL01    | 10       |
| MTF456.2       | ROL02    | 15       |
| MTF789.5       | INVALID  | 20       |  ← TIENDA INVÁLIDA
```

### Proceso
```
1. Detectar formato: SIMPLE
2. Parsear detalles simples
3. Consolidar por producto y tienda
4. Extraer tiendas únicas: ["ROL01", "ROL02", "INVALID"]
5. Validar contra SAP
   - ROL01: ✅ ENCONTRADA
   - ROL02: ✅ ENCONTRADA
   - INVALID: ❌ NO ENCONTRADA
6. Rechazar si sap_obligatorio=true
```

### Respuesta HTTP 400 Bad Request
```json
{
    "status": "validation_error",
    "message": "No se puede procesar la plantilla: existen tiendas (ID TIENDA) no válidas en SAP. Tiendas no encontradas en SAP OWHS: INVALID",
    "validacion_tiendas_sap": {
        "total_codigos": 3,
        "validas": 2,
        "no_encontradas": 1,
        "errores": 0,
        "todos_validas": false
    }
}
```

---

## Guía de Integración del Cliente (Frontend)

### 1. Detectar si la validación falló por tiendas
```javascript
const response = await fetch('/api/plantillas/upload', {
    method: 'POST',
    body: formData
});

const data = await response.json();

if (data.status === 'validation_error' && 
    data.validacion_tiendas_sap && 
    !data.validacion_tiendas_sap.todas_validas) {
    
    // Error por tiendas inválidas
    showError(
        `Tiendas no válidas en SAP: ${data.validacion_tiendas_sap.no_encontradas.join(', ')}`
    );
}
```

### 2. Mostrar detalles de validación
```javascript
if (data.validacion_tiendas_sap) {
    console.log(`Validación de tiendas SAP:`);
    console.log(`  Total: ${data.validacion_tiendas_sap.total_codigos}`);
    console.log(`  Válidas: ${data.validacion_tiendas_sap.validas}`);
    console.log(`  No encontradas: ${data.validacion_tiendas_sap.no_encontradas.length}`);
    console.log(`  Tiendas: ${data.validacion_tiendas_sap.no_encontradas.join(', ')}`);
}
```

### 3. Reintentar con sap_obligatorio=false (para debugging)
```javascript
// Primer intento
const resp1 = await fetch('/api/plantillas/upload?sap_obligatorio=true', {
    method: 'POST',
    body: formData
});

// Si falla por tiendas, reintentar en modo warning
if (resp1.status === 400) {
    const resp2 = await fetch('/api/plantillas/upload?sap_obligatorio=false', {
        method: 'POST',
        body: formData
    });
    
    const data = await resp2.json();
    console.log('Pedido creado con warnings:', data.warnings);
}
```

---

## Resumen de Respuestas

| Escenario | Status | todas_validas | Acción |
|-----------|--------|---------------|----- |
| Todas válidas | 200 | true | ✅ Pedido creado |
| Tiendas inválidas + obligatorio | 400 | false | ❌ Rechazar |
| Tiendas inválidas + no obligatorio | 200 | false | ⚠️ Crear con warnings |
| Error SAP + obligatorio | 400 | false | ❌ Rechazar |
| Error SAP + no obligatorio | 200 | false | ⚠️ Crear con warnings |
