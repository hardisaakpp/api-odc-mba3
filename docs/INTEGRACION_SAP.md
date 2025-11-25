# Integración con SAP para Conversión de Unidades

Este documento describe la integración del sistema con SAP para realizar conversiones automáticas de unidades entre El Rayo (docenas) y Mabel (packs SAP).

## 📋 Resumen

El sistema consulta automáticamente información de productos desde SAP (HANA) usando `OPENQUERY` desde SQL Server, y realiza conversiones de unidades:

- **El Rayo (MBA3)**: Maneja unidades en **docenas**
- **Mabel (SAP)**: Maneja unidades en **packs** (X1, X2, X3, etc.)

### Fórmula de Conversión

```
cantidad_sap (packs) = cantidad (docenas) × unidad_conversion
precio_unitario_sap = total_linea / cantidad_sap
```

**Ejemplo:**
- Docenas: 456
- Pack SAP: X3 → Unidad de conversión: 4
- Packs: 456 × 4 = 1824 packs
- Precio unitario: 2120.4 / 1824 = 1.1625

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
# Configuración SAP
SAP_LINKED_SERVER=MYHANADB
SAP_DATABASE=SBO_MABEL_PROD
SAP_SCHEMA=SBO_MABEL_PROD
ENABLE_SAP_QUERIES=true
SAP_CACHE_DAYS=30
```

### Requisitos Previos

1. **Servidor Vinculado en SQL Server:**
   - Debe estar configurado un servidor vinculado llamado `[MYHANADB]` (o el nombre que configures)
   - Este servidor debe apuntar a SAP HANA
   - Debe tener permisos para ejecutar `OPENQUERY`

2. **Ejecutar Scripts SQL:**
   ```sql
   -- Crear tablas
   scripts/create_sap_tables.sql
   
   -- Agregar columna precio_unitario_sap
   scripts/add_precio_unitario_sap_column.sql
   ```

## 🔄 Flujo de Trabajo

### Paso 1: Consulta SAP y Cache

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

### Paso 2: Conversión al Guardar Detalles

Cuando se guarda una línea de detalle:

1. Se consulta información SAP del SKU (usando cache si está disponible)
2. Si hay información SAP:
   - `cantidad_sap = cantidad × unidad_conversion`
   - `precio_unitario_sap = total_linea / cantidad_sap`
   - `unidad_sap = pack_sap` (X1, X2, etc.)
3. Se guarda en `despacho_detalle` con ambos valores (original y convertido)

## 📁 Estructura de Archivos

```
src/database/
├── clients/
│   ├── __init__.py
│   └── sap_client.py          # Cliente para consultar SAP
├── repositories/
│   ├── __init__.py
│   ├── despacho_repository.py
│   └── producto_sap_repository.py  # Repositorio para producto_sap_cache
├── services/
│   ├── __init__.py
│   ├── factura_service.py     # Modificado para integrar SAP
│   └── sap_service.py         # Servicio para gestionar SAP y cache
└── mappers/
    └── factura_mapper.py       # Modificado para calcular conversiones

scripts/
├── create_sap_tables.sql      # Script para crear tablas SAP
└── add_precio_unitario_sap_column.sql  # Script para agregar columna
```

## 🔧 Componentes Principales

### SAPClient

Cliente para ejecutar consultas `OPENQUERY` a SAP.

```python
from src.database.clients.sap_client import SAPClient

client = SAPClient()
producto_info = client.get_producto_info("5-0012.9")
# Retorna: {"ItemCode": "5-0012.9", "ItemName": "...", "U_IXX_PACK": "X3"}
```

### SAPService

Servicio de alto nivel que gestiona cache y consultas SAP.

```python
from src.database.services.sap_service import SAPService

service = SAPService()
producto_info = service.get_or_fetch_producto_info("5-0012.9")
# Retorna información desde cache o consulta SAP si es necesario
```

### ProductoSAPRepository

Repositorio para operaciones CRUD en `producto_sap_cache`.

```python
from src.database.repositories.producto_sap_repository import ProductoSAPRepository

repository = ProductoSAPRepository(conn)
producto = repository.find_by_sku("5-0012.9")
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
   - precio_unitario: 4.65 (por docena)
   - precio_unitario_sap: 1.1625 (por pack)
```

## 🚀 Activación

La integración está activa por defecto si:
- `ENABLE_SAP_QUERIES=true` en `.env`
- Las tablas están creadas
- El servidor vinculado está configurado

Para desactivar temporalmente:
```env
ENABLE_SAP_QUERIES=false
```

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

