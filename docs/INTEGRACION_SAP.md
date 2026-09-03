# Integración con SAP

Guía completa de integración con SAP para conversión de unidades y envío de órdenes de compra.

## 🏛️ Principio arquitectónico (léelo antes de tocar código de integración SAP)

**Todo proceso que apunte a SAP debe pasar por el middleware** (`SAP_MIDDLEWARE_URL`, cliente `SAPServiceLayerClient`), no por `OPENQUERY` directo a HANA.

**Única excepción:** sincronización masiva de catálogo completo hacia staging (`producto_staging_sync_service.py`, `cruce_productos_service.py`, tarea Celery `celery_sync_productos.py`). Es una lectura *bulk* (todo el catálogo de una vez para cachear localmente), no una consulta puntual — ahí `OPENQUERY` sigue siendo el canal correcto.

Regla práctica para decidir el canal de una operación nueva:

| Tipo de operación | Canal correcto |
|---|---|
| Leer/escribir UN registro puntual (un ítem, una bodega, un proveedor, crear una OC/ITR) | **Middleware** (Service Layer) |
| Traer *todo* el catálogo para cache/staging | `OPENQUERY` (excepción) |
| Búsqueda difusa/`LIKE` sobre el catálogo (ej. SKUs similares) | `OPENQUERY` (es en esencia una lectura bulk filtrada) |
| Endpoint de diagnóstico explícito (`/sap/test`, `/sap/test/direct`) | Cualquiera — es intencional, no es flujo de negocio |

**Patrón de migración obligatorio** para todo punto que hoy siga en `OPENQUERY` y debiera pasar a middleware: un dispatcher que intente middleware primero (gateado por `SAP_USE_MIDDLEWARE`) y haga *fallback* automático a `OPENQUERY` si el middleware no responde. Ver [CALIDAD_CODIGO_SONAR.md](CALIDAD_CODIGO_SONAR.md) para el estándar de calidad de ese código.

### Estado de la migración (auditoría en curso)

✅ **Ya migrados** (middleware primero, fallback a OPENQUERY, todos gateados por `SAP_USE_MIDDLEWARE`):
- Bodega puntual — `bodega_sap_service.py` (`_consultar_bodega_sap`)
- Catálogo/validación batch de bodegas — `bodega_sap_service.py`
- SKU exacto (cruce de productos) — `cruce_productos.py` (`_buscar_sku_sap_handler`)
- Prevalidación de OC (proveedor + artículos) — `oc_sap_service.py` (`_precheck_batch`), flag `USE_BATCH_VALIDATION` (independiente, no es middleware-vs-OPENQUERY sino batch-vs-línea-por-línea; ambas rutas ya pasan por `SAP_USE_MIDDLEWARE`)
- Validación de existencia de SKU al reasignarlo en una línea de OC — `ordenes_compra.py` (`_sku_existe_en_sap`)
- Enriquecimiento de detalles de pedido (descripcion_sap/pack) — `pedido_service.py` (`_consultar_productos_sap`). Nota: sigue siendo una llamada HTTP por SKU único (el endpoint batch del middleware de validación no expone `itemName`/`packCode`); si algún día se necesita un batch real de datos de catálogo, pedirlo como extensión al middleware.
- Info de producto en cache-miss — `sap_service.py` (`_consultar_producto_sap`). Alimenta validación de pedidos y facturación (regla de medias por `ItmsGrpNam`). El middleware ya expone `groupName` (verificado en vivo: `GET /api/v1/items/{code}` → `"groupName": "R-MEDIAS"`); un 404 confirmado se trata como "no existe" definitivo (sin fallback), distinguido del "middleware caído" mediante sentinel.

Nota histórica: hasta 2026-07 estos puntos tenían flags propios (`USE_MIDDLEWARE_WAREHOUSES`, `USE_MIDDLEWARE_SKU_LOOKUP`, `USE_MIDDLEWARE_PRODUCTO_INFO`), todos con default `false`, independientes de `SAP_USE_MIDDLEWARE` (que solo gateaba el envío de OC/ITR). Se consolidaron en `SAP_USE_MIDDLEWARE` para que un solo flag controle middleware-vs-directo en toda la app, como paso previo a implementar un fallback automático por salud/saturación del middleware (middleware → Service Layer directo → OPENQUERY solo para lecturas).

Con esto, **la migración de consultas puntuales a middleware está completa**: no quedan puntos de negocio que consulten OPENQUERY sin alternativa de middleware. OPENQUERY queda solo como fallback automático y para las excepciones bulk documentadas arriba.

## 📋 Resumen

El sistema integra con SAP de tres formas:

1. **Middleware (SAP Service Layer)** — canal por defecto para toda operación puntual: lectura de ítems/bodegas/proveedores y creación de OC/ITR. Ver principio arquitectónico arriba.
2. **Consultas SAP HANA (`OPENQUERY`)** — reservado para sincronización bulk de catálogo hacia staging, y para los puntos aún pendientes de migrar listados arriba.
3. **SAP Service Layer sin pasar por el middleware** — histórico; hoy toda comunicación con Service Layer debería ir a través del middleware, no directo.

### Conversión de Unidades

- **El Rayo (MBA3)**: Maneja unidades en **docenas**
- **Mabel (SAP)**: Maneja unidades en **packs** (X1, X2, X3, etc.)

**Fórmula de Conversión:**
```
cantidad_sap (packs) = cantidad (docenas) × unidad_conversion
precio_unitario_sap = precio_unitario_mba3 / unidad_conversion
subtotal_sap = cantidad_sap × precio_unitario_sap
```

**Ejemplo:**
- Docenas: 456
- Pack SAP: X3 → Unidad de conversión: 4
- Packs: 456 × 4 = 1824 packs
- precio_unitario_mba3: 4.65 (por docena - El Rayo)
- precio_unitario_sap: 4.65 / 4 = 1.1625 (por pack - Mabel Trading)
- subtotal_sap: 1824 × 1.1625 = 2120.4

## 🗄️ Estructura de Tablas

### 1. `pack_conversion` (Tabla Maestra)

Almacena la relación entre packs y unidades de conversión.

```sql
CREATE TABLE pack_conversion (
    pack_id VARCHAR(10) PRIMARY KEY,              -- 'X1', 'X2', 'X3', etc.
    unidad_conversion DECIMAL(10, 9) NOT NULL,   -- 12, 6, 4, 2.4, etc.
    descripcion VARCHAR(100) NULL,
    activo BIT DEFAULT 1,
    created_at DATETIME DEFAULT GETDATE(),
    updated_at DATETIME DEFAULT GETDATE()
);
```

**Datos iniciales:**
- X1 → 12.0
- X2 → 6.0
- X3 → 4.0
- X4 → 3.0
- X5 → 2.4
- X6 → 2.0
- X7 → 1.714285714
- X8 → 1.5
- X9 → 1.333333333
- X12 → 1.0

### 2. `producto_sap_cache` (Cache de Productos SAP)

Almacena información consultada de SAP para evitar consultas repetidas.

```sql
CREATE TABLE producto_sap_cache (
    cache_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    sku VARCHAR(50) NOT NULL UNIQUE,
    item_code VARCHAR(50) NOT NULL,
    item_name VARCHAR(200) NULL,
    pack_sap VARCHAR(10) NULL,                    -- U_IXX_PACK de SAP
    unidad_conversion DECIMAL(10, 9) NULL,        -- Calculada desde pack_conversion
    pack_id VARCHAR(10) NULL,
    ultima_consulta DATETIME NULL,
    activo BIT DEFAULT 1,
    created_at DATETIME DEFAULT GETDATE(),
    updated_at DATETIME DEFAULT GETDATE()
);
```

### 3. `despacho_detalle` (Modificada)

Se agregó el campo `precio_unitario_sap`:

```sql
ALTER TABLE despacho_detalle
ADD precio_unitario_sap DECIMAL(18, 4) NULL;
```

**Campos relacionados:**
- `cantidad`: Docenas de El Rayo (original)
- `cantidad_sap`: Packs convertidos para Mabel
- `unidad_sap`: Pack usado (X1, X2, X3, etc.)
- `precio_unitario`: Precio por docena (original)
- `precio_unitario_sap`: Precio por pack (convertido)

## ⚙️ Configuración

### Variables de Entorno (.env)

```env
# Middleware (canal por defecto — ver Principio Arquitectónico)
SAP_MIDDLEWARE_URL=http://localhost:8011
SAP_USE_MIDDLEWARE=true             # Middleware vs Service Layer directo — gatea TODO lo anterior (envío de OC/ITR, bodegas, SKU, info de producto)
USE_BATCH_VALIDATION=false          # Prevalidación de OC (proveedor + artículos): batch vs línea por línea (independiente)

# SAP HANA (Consultas) — solo sync bulk de staging + puntos pendientes de migrar
SAP_LINKED_SERVER=MYHANADB
SAP_DATABASE=SBO_MABEL_PROD
SAP_SCHEMA=SBO_MABEL_PROD
SAP_CACHE_DAYS=30

# SAP Service Layer (usado por el middleware; también accesible directo — ver excepciones)
SAP_SERVICE_LAYER_URL=http://tu-servidor-sap:50000/b1s/v1
SAP_SERVICE_LAYER_USERNAME=tu_usuario
SAP_SERVICE_LAYER_PASSWORD=tu_contraseña
SAP_SERVICE_LAYER_DATABASE=SBO_MABEL_PROD
ENABLE_SAP_SERVICE_LAYER=true
```

### Requisitos Previos

1. **Servidor Vinculado en SQL Server:**
   - Debe estar configurado un servidor vinculado llamado `[MYHANADB]` (o el nombre que configures)
   - Este servidor debe apuntar a SAP HANA
   - Debe tener permisos para ejecutar `OPENQUERY`
   - Ver [CONFIGURACION.md](CONFIGURACION.md#configurar-servidor-vinculado-para-sap) para instrucciones

2. **Ejecutar Scripts SQL:**
   ```sql
   -- Crear tablas
   scripts/create_sap_tables.sql
   
   -- Agregar columna precio_unitario_sap
   scripts/add_precio_unitario_sap_column.sql
   ```

## 🔄 Flujo de Trabajo

### Consulta SAP y Conversión

Cuando se procesa una factura con un SKU nuevo:

1. El sistema busca en `producto_sap_cache` si existe información del SKU
2. Si no existe o expiró (más de 30 días), consulta SAP usando `OPENQUERY`:
   ```sql
   SELECT 
       T0."ItemCode",
       T0."ItemName",
       T0."U_IXX_PACK"
   FROM OPENQUERY([MYHANADB], '
       SELECT 
           "ItemCode",
           "ItemName",
           "U_IXX_PACK"
       FROM "SBO_MABEL_PROD"."OITM"
       WHERE "ItemCode" = ''5-0012.9''
       LIMIT 100
   ') T0;
   ```
3. Obtiene la unidad de conversión desde `pack_conversion` basado en `U_IXX_PACK`
4. Guarda/actualiza el cache en `producto_sap_cache`

### Conversión al Guardar Detalles

Cuando se guarda una línea de detalle:

1. Se consulta información SAP del SKU (usando cache si está disponible)
2. Si hay información SAP:
   - `cantidad_sap = cantidad × unidad_conversion`
   - `precio_unitario_sap = precio_unitario_mba3 / unidad_conversion`
   - `subtotal_sap = cantidad_sap × precio_unitario_sap`
   - `unidad_sap = pack_sap` (X1, X2, etc.)
3. Se guarda en `despacho_detalle` con ambos valores (original y convertido)

## 🧪 Pruebas

### Script de Prueba

```bash
# Probar con un SKU específico
python scripts/test_sap_query.py --sku "5-0012.9"

# Probar componentes específicos
python scripts/test_sap_query.py --test client --sku "5-0012.9"
python scripts/test_sap_query.py --test service --sku "5-0012.9"
python scripts/test_sap_query.py --test cache --sku "5-0012.9"
```

### Endpoints de Prueba

**Prueba Completa (con cache):**
```
GET http://localhost:8000/sap/test?sku=5-0012.9
```

**Prueba Directa (sin cache):**
```
GET http://localhost:8000/sap/test/direct?sku=5-0012.9
```

### Verificar en Base de Datos

```sql
-- Ver qué hay en el cache
SELECT * FROM producto_sap_cache WHERE sku = '5-0012.9';

-- Ver la unidad de conversión
SELECT * FROM pack_conversion WHERE pack_id = 'X3';
```

## 🚀 Activación

La integración está siempre activa (sin flag) si:
- Las tablas están creadas
- El servidor vinculado está configurado

## ⚠️ Notas Importantes

1. **Cache:** El sistema usa cache para evitar consultas repetidas a SAP. El cache expira después de 30 días (configurable con `SAP_CACHE_DAYS`).

2. **Manejo de Errores:** Si falla la consulta a SAP, el sistema continúa guardando los datos sin conversión (campos SAP quedan en NULL).

3. **Servidor Vinculado:** Asegúrate de que el servidor vinculado `[MYHANADB]` esté correctamente configurado en SQL Server antes de usar esta funcionalidad.

4. **Performance:** Las consultas a SAP pueden ser lentas. El cache ayuda a mejorar el rendimiento.

## 🔍 Troubleshooting

### Error: "Invalid object name 'OPENQUERY'"
- Verifica que el servidor vinculado esté configurado correctamente
- Verifica permisos del usuario de SQL Server

### No se obtienen datos de SAP
- Verifica que `SAP_LINKED_SERVER` coincida con el nombre del servidor vinculado
- Verifica que `SAP_DATABASE` y `SAP_SCHEMA` sean correctos
- Verifica permisos en SAP HANA

### Cache no se actualiza
- Verifica que `SAP_CACHE_DAYS` esté configurado correctamente
- Puedes forzar refresh usando `force_refresh=True` en `get_or_fetch_producto_info()`

### Error: "Producto no encontrado en SAP"
- Verifica que el SKU exista en SAP
- Verifica que `SAP_DATABASE` y `SAP_SCHEMA` sean correctos
- Verifica permisos en el servidor vinculado

### Error: "No se pudo obtener unidad de conversión"
- Verifica que el pack (ej: X3) exista en la tabla `pack_conversion`
- Ejecuta `scripts/create_sap_tables.sql` para poblar los datos iniciales

## 📁 Estructura de Archivos

```
src/database/
├── clients/
│   ├── sap_client.py          # OPENQUERY directo a HANA (bulk + pendientes de migrar)
│   └── sap_service_layer_client.py  # Cliente del middleware (canal por defecto)
├── repositories/
│   ├── producto_sap_repository.py  # Repositorio para producto_sap_cache
│   └── orden_compra_repository.py  # Repositorio para órdenes de compra
├── services/
│   ├── sap_service.py          # Cache-first de producto; en cache-miss usa sap_client (OPENQUERY) — pendiente de migrar
│   ├── bodega_sap_service.py   # Dispatcher bodegas: middleware primero, fallback OPENQUERY — ya migrado
│   └── oc_sap_service.py       # Prevalidación de OC: middleware primero, fallback línea a línea — ya migrado
└── mappers/
    └── sap_oc_mapper.py       # Mapeo de órdenes de compra a SAP

scripts/
├── create_sap_tables.sql      # Script para crear tablas SAP
└── add_precio_unitario_sap_column.sql  # Script para agregar columna
```

## 📊 Ejemplo de Uso

Cuando se guarda una factura desde MBA3:

```python
# En factura_service.py, automáticamente:
1. Se procesa cada línea de detalle
2. Para cada SKU, se consulta SAP (o se usa cache)
3. Se calculan las conversiones
4. Se guarda en despacho_detalle con:
   - cantidad: 456 (docenas)
   - cantidad_sap: 1824 (packs)
   - unidad_sap: "X3"
   - precio_unitario: 4.65 (por docena - El Rayo)
   - precio_unitario_sap: 1.1625 (por pack - Mabel Trading: 4.65 / 4)
   - subtotal_sap: 2120.4 (1824 × 1.1625)
```
