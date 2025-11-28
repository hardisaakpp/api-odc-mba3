# Flujo Completo de Procesamiento

Este documento describe el flujo completo de procesamiento de despachos desde MBA3 hasta SAP.

## 📋 Visión General

El sistema está diseñado con **4 endpoints principales** que forman un flujo secuencial:

```
1. CONSULTAR → 2. MIGRAR → 3. PROCESAR → 4. INTEGRAR
```

Cada endpoint tiene una responsabilidad específica y puede ejecutarse de forma independiente.

---

## 🔄 Flujo Detallado

### 1. CONSULTAR - `GET /consultar`

**Responsabilidad:** Consultar datos desde MBA3 (solo lectura)

**Qué hace:**
- Consulta despachos desde MBA3 usando query predefinida
- Retorna datos en formato JSON
- **NO guarda** en base de datos

**Cuándo usarlo:**
- Para verificar qué datos hay disponibles en MBA3
- Para inspeccionar datos antes de procesarlos
- Para debugging

**Ejemplo:**
```bash
GET /consultar
```

**Respuesta:**
```json
{
  "data": [
    {
      "CODIGO_FACTURA": "900125351",
      "EMPRESA": "EMPRESA001",
      "FECHA_FACTURA": "2025-01-21",
      ...
    }
  ]
}
```

---

### 2. MIGRAR - `GET /migrar`

**Responsabilidad:** Consultar y guardar en base de datos

**Qué hace:**
- Consulta despachos desde MBA3
- Guarda en `despacho_cabecera`/`despacho_detalle`
- Consulta información de productos en SAP (ItemCode, Pack, conversiones)
- Calcula cantidades y precios en unidades SAP
- Retorna datos y metadata del guardado

**Cuándo usarlo:**
- Para migrar datos desde MBA3 a SQL Server
- Cuando necesitas guardar despachos para procesamiento posterior

**Ejemplo:**
```bash
GET /migrar
```

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

### 3. PROCESAR - `GET /procesar-oc`

**Responsabilidad:** Copiar despachos a órdenes de compra

**Qué hace:**
- Busca despachos en `despacho_cabecera` que NO tienen OC asociada
- Copia cada despacho a `orden_compra_cabecera`/`orden_compra_detalle`
- Mapea empresa → proveedor desde tabla `cliente`
- Crea ODCs con estado `"PENDIENTE"` (listas para enviar a SAP)
- Omite despachos que ya tienen OC (evita duplicados)

**Cuándo usarlo:**
- Después de haber migrado despachos (paso 2)
- Cuando necesitas crear órdenes de compra desde despachos existentes

**Ejemplo:**
```bash
GET /procesar-oc
```

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

**📖 Para detalles técnicos del mapeo de campos y estructura de tablas, ver [ORDEN_COMPRA_COPIA.md](ORDEN_COMPRA_COPIA.md)**

---

### 4. INTEGRAR - `POST /integrar-sap`

**Responsabilidad:** Enviar ODCs a SAP Service Layer

**Qué hace:**
- Busca ODCs en `orden_compra_cabecera` con estado `"PENDIENTE"`
- Convierte cada ODC a formato JSON de SAP Service Layer
- Envía cada ODC directamente a SAP Service Layer (sin middleware)
- Actualiza estado y número de OC en la base de datos:
  - `"PENDIENTE"` → `"ENVIADA"` (si fue exitoso)
  - `"PENDIENTE"` → `"ERROR"` (si falló)
- Guarda el número de OC de SAP (`DocNum`) en la base de datos

**Cuándo usarlo:**
- Después de haber procesado ODCs (paso 3)
- Cuando necesitas enviar órdenes de compra a SAP

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

**Respuesta con errores parciales:**
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

**Estados de ODC:**
- `PENDIENTE`: Creada pero no enviada a SAP (estado inicial)
- `ENVIADA`: Enviada exitosamente a SAP (se actualiza aquí)
- `ERROR`: Error al enviar a SAP (se actualiza aquí)

**Configuración requerida:**
- Variables de entorno en `.env`:
  - `SAP_SERVICE_LAYER_URL`
  - `SAP_SERVICE_LAYER_USERNAME`
  - `SAP_SERVICE_LAYER_PASSWORD`
  - `SAP_SERVICE_LAYER_DATABASE`
  - `ENABLE_SAP_SERVICE_LAYER=true`

---

## 🚀 Flujo Recomendado

### Flujo Completo (4 Pasos)

```bash
# Paso 1: Consultar (opcional, solo para verificar)
GET /consultar

# Paso 2: Migrar (consulta + guarda)
GET /migrar

# Paso 3: Procesar (copia a OC)
GET /procesar-oc

# Paso 4: Integrar (envía a SAP)
POST /integrar-sap
```

### Flujo Rápido (Solo Pasos Esenciales)

```bash
# Paso 1: Migrar (consulta + guarda)
GET /migrar

# Paso 2: Procesar (copia a OC)
GET /procesar-oc

# Paso 3: Integrar (envía a SAP)
POST /integrar-sap
```

---

## 🧪 Endpoint de Pruebas

### `GET /pruebas`

Ejecuta los pasos 1, 2 y 3 en un solo endpoint (útil para testing).

**Qué hace:**
- ✅ Consulta datos desde MBA3
- ✅ Guarda en `despacho_cabecera`/`despacho_detalle`
- ✅ Copia a `orden_compra_cabecera`/`orden_compra_detalle`
- ❌ **NO envía a SAP** (ese paso lo hace `/integrar-sap`)

**Cuándo usarlo:**
- Para probar el flujo completo sin enviar a SAP
- Para desarrollo y debugging
- Para verificar que todo funciona antes de integrar con SAP

**Ejemplo:**
```bash
GET /pruebas
```

---

## 📊 Estados de ODC

Las órdenes de compra pasan por diferentes estados durante el proceso:

| Estado | Descripción | Cuándo se asigna |
|--------|-------------|------------------|
| `PENDIENTE` | Creada pero no enviada a SAP | Al crear la OC (paso 3) |
| `ENVIADA` | Enviada exitosamente a SAP | Al completar el envío (paso 4) |
| `ERROR` | Error al enviar a SAP | Si falla el envío (paso 4) |

---

## 🔍 Verificación

### Verificar ODCs Pendientes

```sql
SELECT oc_id, proveedor, estado, fecha_generacion, created_at
FROM orden_compra_cabecera
WHERE estado = 'PENDIENTE'
ORDER BY created_at DESC;
```

### Verificar ODCs Enviadas

```sql
SELECT oc_id, proveedor, estado, numero_oc_sap, fecha_generacion, updated_at
FROM orden_compra_cabecera
WHERE estado = 'ENVIADA'
ORDER BY updated_at DESC;
```

### Verificar ODCs con Errores

```sql
SELECT oc_id, proveedor, estado, fecha_generacion, updated_at
FROM orden_compra_cabecera
WHERE estado = 'ERROR'
ORDER BY updated_at DESC;
```

---

## ⚠️ Notas Importantes

1. **Orden de ejecución:** Los endpoints deben ejecutarse en secuencia (1 → 2 → 3 → 4)

2. **Idempotencia:** 
   - El paso 2 (MIGRAR) usa UPSERT, puede ejecutarse múltiples veces
   - El paso 3 (PROCESAR) omite despachos que ya tienen OC
   - El paso 4 (INTEGRAR) solo procesa ODCs con estado "PENDIENTE"

3. **Configuración SAP:** El paso 4 requiere configuración de SAP Service Layer en `.env`

4. **Middleware:** El middleware NO se usa para crear Purchase Orders, solo para operaciones posteriores (GoodsReceipt cuando llegue la mercadería)

---

## 📚 Documentación Relacionada

- [Endpoints](ENDPOINTS.md) - Documentación completa de todos los endpoints
- [Configuración](CONFIGURACION.md) - Variables de entorno y setup
- [Integración SAP](INTEGRACION_SAP.md) - Configuración e integración con SAP
- [Orden de Compra](ORDEN_COMPRA_COPIA.md) - Detalles técnicos del mapeo de campos (Paso 3)

