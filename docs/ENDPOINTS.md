# Documentación de Endpoints

## Endpoints Principales

### Health Check

**GET `/health`**

Verifica el estado del servidor.

**Respuesta:**
```json
{
  "status": "ok",
  "time": "2025-01-21T12:00:00.123456"
}
```

---

### Consultar Facturas

**GET `/facturas`** ⭐ **Recomendado para Frontend**

Obtiene facturas desde MBA3 con filtros configurables. La query está integrada en el backend.

**Query Parameters:**
- `anulada` (boolean, default: `false`) - Filtrar por facturas anuladas
- `confirmado` (boolean, default: `true`) - Filtrar por facturas confirmadas
- `remision_facturada` (boolean, default: `false`) - Filtrar por remisión facturada
- `include_obj_datos` (boolean, default: `true`) - Incluir solo facturas con ObjDatosFactura
- `save_to_db` (boolean, default: `true`) - Guardar en SQL Server

**Ejemplo:**
```bash
curl "http://localhost:8000/facturas?anulada=false&confirmado=true"
```

**Respuesta:**
```json
{
  "data": [...],
  "metadata": {
    "count": 10,
    "filters": {...},
    "save_status": {...}
  }
}
```

---

### Consultar Despachos

**GET `/consultar`**

Consulta despachos desde MBA3 (solo lectura, no guarda en BD).

**Respuesta:** Array JSON con datos de MBA3

---

### Migrar Despachos

**GET `/migrar`**

Consulta desde MBA3 y guarda en `despacho_cabecera`/`despacho_detalle`.

**Respuesta:**
```json
{
  "data": [...],
  "metadata": {
    "save_status": {
      "facturas_guardadas": 5,
      "total_detalles": 20
    }
  }
}
```

---

### Procesar Orden de Compra

**GET `/procesar-oc`**

Copia despachos existentes a `orden_compra_cabecera`/`orden_compra_detalle`.

**Respuesta:**
```json
{
  "status": "success",
  "metadata": {
    "oc_creadas": 5,
    "oc_errores": 0
  }
}
```

---

### Proceso Completo (Pruebas)

**GET `/pruebas`**

Ejecuta el proceso completo: consulta + guarda + copia a OC.

---

### Consulta SQL Dinámica

**POST `/consulta`**

Ejecuta una consulta SQL personalizada contra MBA3.

**Body (JSON):**
```json
{
  "query": "SELECT * FROM CLNT_FACTURA_PRINCIPAL WHERE NUMERO_PEDIDO_SISTEMA='176120'"
}
```

**GET `/consulta?query=...`**

Mismo comportamiento pero con método GET.

---

### Validar Consulta SQL

**POST `/query`**

Valida y parsea una consulta SQL sin ejecutarla.

**Body (JSON):**
```json
{
  "query": "SELECT * FROM tabla WHERE condicion"
}
```

**Respuesta:**
```json
{
  "original": "SELECT * FROM tabla",
  "parsed": {
    "select": "*",
    "from": "tabla",
    "where": "condicion"
  },
  "received_at": "2025-01-21T12:00:00",
  "source": "Postman",
  "note": "PARSE_OK"
}
```

---

### Consultar SAP

**GET `/sap/test?sku=5-0012.9`**

Consulta información de un producto en SAP (usa cache).

**GET `/sap/test/direct?sku=5-0012.9`**

Consulta directa a SAP sin usar cache.

**Respuesta:**
```json
{
  "status": "success",
  "sku": "5-0012.9",
  "sap_info": {
    "item_code": "5-0012.9",
    "item_name": "Producto",
    "pack_sap": "X3",
    "unidad_conversion": 12
  }
}
```

---

## Validaciones de Seguridad

El servidor bloquea automáticamente:
- ❌ Consultas que no sean SELECT
- ❌ Operaciones peligrosas: INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, EXEC, etc.
- ❌ Múltiples statements separados por `;`
- ❌ Consultas que excedan 5000 caracteres

