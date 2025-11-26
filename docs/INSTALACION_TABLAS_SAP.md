# Instalación de Tablas SAP

Esta guía te muestra cómo crear las tablas necesarias para la integración con SAP en la base de datos `store_control`.

## 📋 Requisitos Previos

- Acceso a SQL Server Management Studio (SSMS) o herramienta similar
- Permisos para crear tablas en la base de datos `store_control`
- Base de datos: `store_control` en el servidor `210.17.1.54`

## 🗄️ Base de Datos

- **Servidor**: `210.17.1.54`
- **Base de datos**: `store_control`

## 📝 Pasos de Instalación

### Paso 1: Verificar Estado Actual

Primero, verifica qué tablas ya existen:

```sql
-- Conectarte a: 210.17.1.54, Base de datos: store_control
-- Ejecutar:
scripts/verify_sap_tables.sql
```

O ejecuta manualmente:

```sql
USE store_control;
GO

-- Verificar pack_conversion
SELECT * FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_NAME = 'pack_conversion';

-- Verificar producto_sap_cache
SELECT * FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_NAME = 'producto_sap_cache';
```

### Paso 2: Crear Tablas SAP

Ejecuta el script de creación de tablas:

```sql
-- Conectarte a: 210.17.1.54, Base de datos: store_control
-- Ejecutar el script completo:
scripts/create_sap_tables.sql
```

**O ejecuta manualmente en SSMS:**

1. Abre SQL Server Management Studio
2. Conéctate al servidor `210.17.1.54`
3. Selecciona la base de datos `store_control`
4. Abre el archivo `scripts/create_sap_tables.sql`
5. Ejecuta el script (F5)

### Paso 3: Agregar Columna a despacho_detalle

Ejecuta el script para agregar la columna `precio_unitario_sap`:

```sql
-- Conectarte a: 210.17.1.54, Base de datos: store_control
-- Ejecutar:
scripts/add_precio_unitario_sap_column.sql
```

### Paso 4: Verificar Instalación

Ejecuta el script de verificación:

```sql
-- Conectarte a: 210.17.1.54, Base de datos: store_control
-- Ejecutar:
scripts/verify_sap_tables.sql
```

Deberías ver:
- ✅ Tabla pack_conversion: EXISTE (con 10 registros)
- ✅ Tabla producto_sap_cache: EXISTE
- ✅ Columna precio_unitario_sap en despacho_detalle: EXISTE

## 📊 Tablas que se Crean

### 1. `pack_conversion`

Tabla maestra con las conversiones de packs:

```sql
pack_id          | unidad_conversion | descripcion
-----------------|-------------------|----------------------------
X1               | 12.0              | Pack X1 - 12 unidades por docena
X2               | 6.0               | Pack X2 - 6 unidades por docena
X3               | 4.0               | Pack X3 - 4 unidades por docena
X4               | 3.0               | Pack X4 - 3 unidades por docena
X5               | 2.4               | Pack X5 - 2.4 unidades por docena
X6               | 2.0               | Pack X6 - 2 unidades por docena
X7               | 1.714285714       | Pack X7 - 1.714285714 unidades por docena
X8               | 1.5               | Pack X8 - 1.5 unidades por docena
X9               | 1.333333333       | Pack X9 - 1.333333333 unidades por docena
X12              | 1.0               | Pack X12 - 1 unidad por docena
```

### 2. `producto_sap_cache`

Tabla de cache para información de productos SAP. Se llena automáticamente cuando se consultan productos.

### 3. Modificación a `despacho_detalle`

Se agrega la columna `precio_unitario_sap` para almacenar el precio convertido por pack.

## ✅ Verificación Post-Instalación

Después de ejecutar los scripts, verifica que todo esté correcto:

```sql
USE store_control;
GO

-- 1. Verificar que pack_conversion tiene datos
SELECT COUNT(*) AS total_packs FROM pack_conversion;
-- Debe mostrar: 10

-- 2. Verificar estructura de producto_sap_cache
SELECT TOP 1 * FROM producto_sap_cache;
-- Debe mostrar la estructura de la tabla (aunque esté vacía)

-- 3. Verificar columna en despacho_detalle
SELECT precio_unitario_sap 
FROM despacho_detalle 
WHERE 1=0;  -- Solo verificar que la columna existe
```

## 🔧 Solución de Problemas

### Error: "Invalid object name 'producto_sap_cache'"

**Causa**: La tabla no existe en la base de datos.

**Solución**: Ejecuta `scripts/create_sap_tables.sql` en la base de datos `store_control`.

### Error: "Cannot insert duplicate key"

**Causa**: Los datos de `pack_conversion` ya existen.

**Solución**: El script usa `IF NOT EXISTS`, así que es seguro ejecutarlo múltiples veces. Si aún hay error, verifica que no haya duplicados:

```sql
SELECT pack_id, COUNT(*) 
FROM pack_conversion 
GROUP BY pack_id 
HAVING COUNT(*) > 1;
```

### Error de permisos

**Causa**: El usuario no tiene permisos para crear tablas.

**Solución**: Solicita permisos `CREATE TABLE` al administrador de la base de datos.

## 📝 Notas Importantes

1. **Base de datos correcta**: Asegúrate de estar conectado a `store_control` antes de ejecutar los scripts.

2. **Scripts idempotentes**: Los scripts están diseñados para ejecutarse múltiples veces sin causar errores (usan `IF NOT EXISTS`).

3. **Datos iniciales**: El script `create_sap_tables.sql` inserta automáticamente los 10 packs en `pack_conversion`.

4. **Cache vacío**: Es normal que `producto_sap_cache` esté vacía inicialmente. Se llenará automáticamente cuando el sistema consulte productos desde SAP.

## 🚀 Próximos Pasos

Una vez instaladas las tablas:

1. Verifica la configuración en `.env`:
   ```env
   SQL_SERVER_SERVER=210.17.1.54
   SQL_SERVER_DATABASE=store_control
   ```

2. Ejecuta las pruebas:
   ```bash
   python scripts/test_sap_query.py --sku "5-0012.9"
   ```

3. Verifica que el guardado funcione consultando la base de datos:
   ```sql
   SELECT * FROM producto_sap_cache WHERE sku = '5-0012.9';
   ```

