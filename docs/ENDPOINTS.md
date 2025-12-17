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

### Contar Despachos Disponibles

**GET `/despachos/count`**

Obtiene el conteo y información detallada de despachos con sus órdenes de compra asociadas.

**Características:**
- ✅ Cuenta despachos en `despacho_cabecera` que NO tienen OC asociada
- ✅ Devuelve información detallada de todas las tablas relacionadas:
  - `despacho_cabecera` (información de cabecera del despacho)
  - `despacho_detalle` (líneas de detalle del despacho)
  - `orden_compra_cabecera` (información de cabecera de OC si existe)
  - `orden_compra_detalle` (líneas de detalle de OC si existe)
- ✅ Permite mostrar información completa en el frontend
- ✅ Permisos: solo lectura (`mba3-consultas.facturas.view`)

**Query Parameters:**
- `limit` (int, opcional) - Número máximo de registros a retornar

**Ejemplo:**
```bash
curl "http://localhost:8000/despachos/count"
curl "http://localhost:8000/despachos/count?limit=10"
```

**Respuesta:**
```json
{
  "count": 5,
  "disponible": true,
  "despachos": [
    {
      "despacho_id": "uuid",
      "empresa": "EMPRESA001",
      "codigo_cliente": "CLI001",
      "numero_factura": "FAC-001",
      "fecha_despacho": "2025-01-21",
      "fecha_factura": "2025-01-21",
      "codigo_factura": "FAC-001",
      "anulada": false,
      "confirmado": true,
      "despacho_detalles": [
        {
          "detalle_id": "uuid",
          "sku": "SKU001",
          "cantidad_docena_mba3": 10,
          "precio_unitario_mba3": 100.0,
          "total_linea_mba3": 1000.0,
          "cantidad_pack_sap": 40.0,
          "unidad_sap": "X3",
          "precio_unitario_sap": 25.0,
          "nombre_producto": "Producto Ejemplo",
          "tipo_linea": "GrabarLineasProd"
        }
      ],
      "orden_compra_info": {
        "oc_id": "uuid",
        "proveedor": "PROVEEDOR001",
        "estado": "PENDIENTE",
        "numero_oc_sap": null,
        "fecha_generacion": "2025-01-21",
        "referencia_despacho": "FAC-001",
        "oc_detalles": [
          {
            "oc_detalle_id": "uuid",
            "sku_sap": "SKU001",
            "cantidad_sap": 40.0,
            "unidad_sap": "X3",
            "precio_unitario": 25.0,
            "total_linea": 1000.0,
            "cantidad_origen": 10.0,
            "referencia_detalle": "uuid-del-despacho-detalle"
          }
        ]
      }
    }
  ]
}
```

**Uso en Frontend:**
Este endpoint permite:
- Verificar si hay despachos disponibles antes de ejecutar `/procesar-oc`
- Mostrar información detallada de despachos y sus órdenes de compra en la interfaz
- Habilitar o deshabilitar el botón de procesamiento automáticamente

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

### Obtener Remisiones (Paginado)

**GET `/remisiones`**

Obtiene remisiones desde la base de datos con paginación.

**Características:**
- ✅ Consulta desde la tabla `remision_cabecera` (ya guardada)
- ✅ Paginación con `page` y `pageSize`
- ✅ Ordenamiento por fecha más reciente primero
- ✅ Permisos: solo lectura (`mba3-consultas.facturas.view`)

**Query Parameters:**
- `page` (int, default: 1) - Número de página (empezando en 1)
- `pageSize` (int, default: 10, max: 100) - Tamaño de página

**Ejemplo:**
```bash
curl "http://localhost:8000/remisiones?page=1&pageSize=10"
curl "http://localhost:8000/remisiones?page=2&pageSize=20"
```

**Respuesta:**
```json
{
  "status": "success",
  "data": [
    {
      "CODIGO_FACTURA": "REMSI-900125250-TRAYO",
      "ANULADA": false,
      "NUMERO_PEDIDO_SISTEMA": 175975,
      "NUMERO_ORDEN": 129065,
      "FACTURA_IMPRESA": false,
      "NUMERO_FACTURA": 900125250,
      "EMPRESA": "TRAYO",
      "CODIGO_CLIENTE": "CLI0024",
      "FECHA_FACTURA": "2025-01-21",
      "TIPO_DOCUMENTO": "REM",
      "ObjDatosFactura": null,
      "ORDEN_COMPRA": "1-10432",
      "ORDEN_COMPRA_CLIENTE": "",
      "Remision_Facturada": false,
      "CONFIRMADO": false
    }
  ],
  "metadata": {
    "count": 100
  },
  "total": 100,
  "page": 1,
  "pageSize": 10,
  "totalPages": 10
}
```

**Uso en Frontend:**
Este endpoint permite:
- Consultar remisiones guardadas en la base de datos
- Implementar paginación en la interfaz
- Mostrar información de remisiones en una pantalla exclusiva
- Ordenar por fecha más reciente primero

---

### Consultar Documentos de Remisión desde MBA3

**GET `/remisiones/consultar`**

Consulta documentos de remisión desde MBA3 y guarda solo cabeceras en la base de datos.

**Características:**
- ✅ Consulta documentos de remisión desde MBA3 (sin detalles)
- ✅ Guarda solo cabeceras en `remision_cabecera` (tabla exclusiva, NO guarda detalles)
- ✅ Filtro automático: siempre trae los últimos N días desde hoy (configurado en `MIGRATE_DATE_FILTER_DAYS`)
- ✅ Sin parámetros: solo ejecutar el endpoint
- ✅ Fecha relativa: calcula automáticamente desde hoy hacia atrás
- ✅ Configurable: se puede cambiar en `.env` con `MIGRATE_DATE_FILTER_DAYS`
- ✅ Estos documentos no tienen `ObjDatosFactura`, por lo que no se crean registros de detalles
- ✅ Se almacenan en la tabla exclusiva `remision_cabecera` (separada de `despacho_cabecera`)
- ✅ Permisos: requiere `mba3-consultas.proceso.execute`
- ✅ Usa la misma configuración de filtro de fecha que los procesos manual y automático

**Query utilizada:**
Consulta documentos de remisión con:
- `TIPO_DOCUMENTO='REM'`
- `CONFIRMADO='false'`
- `Remision_Facturada='false'`
- `ObjDatosFactura IS NULL` (sin detalles)
- `FACTURA_IMPRESA='false'`
- `ANULADA='false'`
- `FECHA_FACTURA >= (fecha calculada según MIGRATE_DATE_FILTER_DAYS)`

**Ejemplo:**
```bash
curl "http://localhost:8000/remisiones/consultar"
```

**Respuesta:**
```json
{
  "status": "success",
  "data": [
    {
      "CODIGO_FACTURA": "REMSI-900125250-TRAYO",
      "ANULADA": false,
      "NUMERO_PEDIDO_SISTEMA": 175975,
      "NUMERO_ORDEN": 129065,
      "FACTURA_IMPRESA": false,
      "NUMERO_FACTURA": 900125250,
      "EMPRESA": "TRAYO",
      "CODIGO_CLIENTE": "CLI0024",
      "FECHA_FACTURA": "2025-01-21",
      "TIPO_DOCUMENTO": "REM",
      "ObjDatosFactura": null,
      "ORDEN_COMPRA": "1-10432",
      "ORDEN_COMPRA_CLIENTE": "",
      "Remision_Facturada": false,
      "CONFIRMADO": false
    }
  ],
  "metadata": {
    "query": "SELECT CODIGO_FACTURA,ANULADA...",
    "count": 5,
    "date_filter": {
      "enabled": true,
      "days": 365
    },
    "save_status": {
      "status": "success",
      "facturas_guardadas": 3,
      "facturas_actualizadas": 2,
      "total_detalles": 0
    },
    "note": "Estos documentos de remisión no tienen detalles. Solo se guardan cabeceras en remision_cabecera (tabla exclusiva)."
  }
}
```

**Uso en Frontend:**
Este endpoint permite:
- Consultar documentos de remisión específicos (sin detalles)
- Guardar automáticamente las cabeceras en la base de datos
- Mostrar información de remisiones en una pantalla exclusiva
- Usar la misma configuración de filtro de fecha que los procesos manual y automático

**Nota:** 
- Este endpoint guarda automáticamente en la base de datos
- Usa la misma configuración de filtro de fecha (`MIGRATE_DATE_FILTER_DAYS`) que los procesos `/migrar/completo` y la migración automática
- El filtro de fecha se aplica automáticamente, no requiere parámetros

---

## 🔄 Homologaciones SKU

### Listar Homologaciones

**GET `/api/homologaciones-sku`**

Obtiene lista paginada de homologaciones SKU entre MBA3 y SAP.

**Query Parameters:**
- `page` (int, default: 1) - Número de página
- `pageSize` (int, default: 10, max: 100) - Tamaño de página
- `estado` (string, opcional) - PENDIENTE | HOMOLOGADO | ERROR
- `tiene_diferencias` (boolean, opcional) - Filtrar por diferencias
- `tiene_datos_sap` (boolean, opcional) - Filtrar por datos SAP
- `sku` (string, opcional) - Búsqueda por SKU (MBA3 o SAP)

**Headers requeridos:**
```
Authorization: Bearer {JWT_TOKEN}
```

**Respuesta:**
```json
{
  "status": "success",
  "data": [
    {
      "homologacion_id": "uuid-123",
      "sku_mba3": "SKU001",
      "nombre_producto_mba3": "Producto Ejemplo",
      "precio_unitario_mba3": 100.50,
      "cantidad_docena_mba3": 12.0,
      "total_linea_mba3": 1206.00,
      "sku_sap": "SKU001-SAP",
      "nombre_producto_sap": "Producto SAP",
      "precio_unitario_sap": 100.00,
      "cantidad_pack_sap": 10.0,
      "unidad_sap": "UN",
      "subtotal_sap": 1000.00,
      "estado": "PENDIENTE",
      "tiene_diferencias": true,
      "tiene_datos_sap": true,
      "detalle_id": "detalle-123",
      "despacho_id": "despacho-456",
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ],
  "metadata": {
    "count": 150,
    "total_pendientes": 50,
    "total_homologados": 80,
    "total_errores": 20,
    "filters": {}
  },
  "total": 150,
  "page": 1,
  "pageSize": 10,
  "totalPages": 15
}
```

---

### Actualizar Homologación

**PUT `/api/homologaciones-sku/{homologacion_id}`**

Actualiza una homologación SKU específica.

**Headers requeridos:**
```
Authorization: Bearer {JWT_TOKEN}
Content-Type: application/json
```

**Body (todos los campos son opcionales):**
```json
{
  "sku_sap": "SKU001-SAP",
  "nombre_producto_sap": "Producto SAP Actualizado",
  "precio_unitario_sap": 105.00,
  "cantidad_pack_sap": 12,
  "unidad_sap": "UN",
  "subtotal_sap": 1260.00,
  "estado": "HOMOLOGADO"
}
```

**Respuesta:**
```json
{
  "status": "success",
  "data": {
    "homologacion_id": "uuid-123",
    // ... objeto completo actualizado
  },
  "message": "Homologación actualizada correctamente"
}
```

**Validaciones:**
- `precio_unitario_sap` >= 0
- `cantidad_pack_sap` >= 0
- `estado` debe ser PENDIENTE, HOMOLOGADO o ERROR

---

### Actualización Masiva

**POST `/api/homologaciones-sku/bulk-update`**

Actualiza múltiples homologaciones en lote.

**Headers requeridos:**
```
Authorization: Bearer {JWT_TOKEN}
Content-Type: application/json
```

**Body:**
```json
{
  "updates": [
    {
      "homologacion_id": "uuid-123",
      "data": {
        "sku_sap": "SKU001-SAP",
        "precio_unitario_sap": 105.00,
        "estado": "HOMOLOGADO"
      }
    },
    {
      "homologacion_id": "uuid-456",
      "data": {
        "sku_sap": "SKU002-SAP",
        "estado": "HOMOLOGADO"
      }
    }
  ]
}
```

**Respuesta:**
```json
{
  "status": "success",
  "data": {
    "actualizadas": 2,
    "errores": 0,
    "detalles": [
      {
        "homologacion_id": "uuid-123",
        "success": true
      },
      {
        "homologacion_id": "uuid-456",
        "success": true
      }
    ]
  }
}
```

---

### Sincronizar Homologaciones

**POST `/api/homologaciones-sku/sincronizar`**

Sincroniza homologaciones desde los despachos. Detecta SKUs que no coinciden entre MBA3 y SAP.

**Headers requeridos:**
```
Authorization: Bearer {JWT_TOKEN}
```

**Body:** vacío

**Respuesta:**
```json
{
  "status": "success",
  "data": {
    "homologaciones_encontradas": 25,
    "homologaciones_nuevas": 10,
    "homologaciones_actualizadas": 15,
    "mensaje": "Sincronización completada"
  }
}
```

**Proceso de sincronización:**
1. Lee todos los productos de `despacho_detalle`
2. Busca información SAP en `producto_sap_cache`
3. Detecta diferencias entre MBA3 y SAP
4. Crea nuevas homologaciones o actualiza existentes
5. Calcula flags automáticamente (`tiene_diferencias`, `tiene_datos_sap`)
6. Asigna estado apropiado

**Nota:** Para más detalles sobre homologaciones SKU, ver [HOMOLOGACIONES_SKU.md](HOMOLOGACIONES_SKU.md).

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

