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

**Características:**
- Busca despachos en `despacho_cabecera` que NO tienen OC asociada
- Copia cada despacho a `orden_compra_cabecera`/`orden_compra_detalle`
- Mapea empresa → proveedor desde tabla `cliente`
- Crea las ODC con estado `"PENDIENTE"` (listas para enviar a SAP)

**Respuesta:**
```json
{
  "status": "success",
  "message": "Proceso completado: 5 OCs creadas de 5 despachos (estado: PENDIENTE)",
  "metadata": {
    "oc_creadas": 5,
    "oc_errores": 0,
    "total_procesadas": 5,
    "total_despachos": 5,
    "detalles": [
      {
        "despacho_id": "uuid",
        "oc_id": "uuid",
        "proveedor": "PROVEEDOR001",
        "detalles_insertados": 10,
        "accion": "creada",
        "estado": "PENDIENTE"
      }
    ]
  }
}
```

**Estados de ODC:**
- `PENDIENTE`: Creada pero no enviada a SAP (estado inicial)
- `ENVIADA`: Enviada exitosamente a SAP (se actualiza en `/integrar-sap`)
- `ERROR`: Error al enviar a SAP (se actualiza en `/integrar-sap`)

---

### Integrar con SAP

**POST `/integrar-sap`** ⭐ **Endpoint #4 del flujo completo**

Envía órdenes de compra con estado `"PENDIENTE"` a SAP Service Layer.

**Características:**
- Busca ODCs en `orden_compra_cabecera` con estado `"PENDIENTE"`
- Convierte cada ODC a formato JSON de SAP Service Layer
- Envía cada ODC directamente a SAP Service Layer (sin middleware)
- Actualiza estado y número de OC en la base de datos
- Retorna resumen detallado del proceso

**Ejemplo:**
```bash
POST /integrar-sap
```

**Respuesta exitosa:**
```json
{
  "status": "success",
  "message": "Proceso completado: 5 ODC(s) enviada(s) exitosamente a SAP",
  "metadata": {
    "total_pendientes": 5,
    "enviadas": 5,
    "errores": 0,
    "detalles": [
      {
        "oc_id": "uuid",
        "proveedor": "PROVEEDOR001",
        "success": true,
        "doc_entry": 12345,
        "doc_num": 67890,
        "error": null
      }
    ]
  }
}
```

**Respuesta con errores:**
```json
{
  "status": "partial",
  "message": "Proceso completado parcialmente: 3 enviada(s), 2 error(es)",
  "metadata": {
    "total_pendientes": 5,
    "enviadas": 3,
    "errores": 2,
    "detalles": [
      {
        "oc_id": "uuid-1",
        "success": true,
        "doc_entry": 12345,
        "doc_num": 67890
      },
      {
        "oc_id": "uuid-2",
        "success": false,
        "error": "Error al crear Purchase Order en SAP: ..."
      }
    ]
  }
}
```

**Configuración requerida:**
- Variables de entorno en `.env`:
  - `SAP_SERVICE_LAYER_URL` - URL del Service Layer
  - `SAP_SERVICE_LAYER_USERNAME` - Usuario de SAP
  - `SAP_SERVICE_LAYER_PASSWORD` - Contraseña de SAP
  - `SAP_SERVICE_LAYER_DATABASE` - Base de datos SAP
  - `ENABLE_SAP_SERVICE_LAYER=true` - Habilitar integración

**Nota:** Este endpoint asume que las ODCs ya están creadas con estado `"PENDIENTE"` (usando `/procesar-oc`).

---

### Proceso Completo (Pruebas)

**GET `/pruebas`**

Ejecuta el proceso completo de los 3 primeros endpoints: consulta + guarda + copia a OC.

**Características:**
- ✅ Consulta datos desde MBA3 usando query predefinida
- ✅ Guarda resultados en SQL Server (`despacho_cabecera`/`despacho_detalle`)
- ✅ Copia despachos a `orden_compra_cabecera`/`orden_compra_detalle`
- ❌ NO envía a SAP (ese paso lo hace `/integrar-sap`)

**Nota:** Este endpoint ejecuta los 3 primeros pasos del flujo completo. Para enviar a SAP, usar el endpoint `POST /integrar-sap`.

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

---

## 📋 Flujo Completo de Procesamiento

El sistema está diseñado con **4 endpoints principales** que forman un flujo completo:

1. **GET `/consultar`** - Consultar datos desde MBA3 (solo lectura)
2. **GET `/migrar`** - Consultar y guardar en base de datos
3. **GET `/procesar-oc`** - Copiar despachos a órdenes de compra
4. **POST `/integrar-sap`** - Enviar ODCs a SAP Service Layer

Para una descripción detallada del flujo completo, ver [FLUJO_COMPLETO.md](FLUJO_COMPLETO.md).

---

## Validaciones de Seguridad

El servidor bloquea automáticamente:
- ❌ Consultas que no sean SELECT
- ❌ Operaciones peligrosas: INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, EXEC, etc.
- ❌ Múltiples statements separados por `;`
- ❌ Consultas que excedan 5000 caracteres

