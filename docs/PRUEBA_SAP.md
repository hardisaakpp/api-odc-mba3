# Guía para Probar la Consulta a SAP

Esta guía te muestra cómo probar la integración con SAP de dos formas diferentes.

## 📋 Requisitos Previos

Antes de probar, asegúrate de:

1. ✅ **Tablas creadas**: Ejecuta `scripts/create_sap_tables.sql` en SQL Server
2. ✅ **Columna agregada**: Ejecuta `scripts/add_precio_unitario_sap_column.sql` en SQL Server
3. ✅ **Servidor vinculado configurado**: El servidor vinculado `[MYHANADB]` debe estar configurado en SQL Server
4. ✅ **Variables de entorno**: Configura en `.env`:
   ```env
   ENABLE_SAP_QUERIES=true
   SAP_LINKED_SERVER=MYHANADB
   SAP_DATABASE=SBO_MABEL_PROD
   SAP_SCHEMA=SBO_MABEL_PROD
   ```

## 🔧 Método 1: Script de Prueba (Línea de Comandos)

### Ejecutar todas las pruebas

```bash
# Desde la raíz del proyecto
python scripts/test_sap_query.py
```

### Ejecutar con un SKU específico

```bash
python scripts/test_sap_query.py --sku "5-0012.9"
```

### Ejecutar una prueba específica

```bash
# Solo prueba del cliente SAP
python scripts/test_sap_query.py --test client --sku "5-0012.9"

# Solo prueba del servicio SAP (con cache)
python scripts/test_sap_query.py --test service --sku "5-0012.9"

# Solo prueba del repositorio de cache
python scripts/test_sap_query.py --test cache --sku "5-0012.9"
```

### Qué hace cada prueba

1. **Cliente SAP Directo**: Prueba la consulta directa a SAP usando `OPENQUERY`
2. **Servicio SAP con Cache**: Prueba el servicio completo que usa cache
3. **Repositorio de Cache**: Verifica qué hay almacenado en el cache

## 🌐 Método 2: Endpoints de la API

### Opción A: Prueba Completa (con cache)

**Endpoint:** `GET /sap/test`

**Ejemplo:**
```
http://localhost:8000/sap/test?sku=5-0012.9
```

**Desde Postman:**
1. Método: `GET`
2. URL: `http://localhost:8000/sap/test`
3. Query Params:
   - `sku`: `5-0012.9`

**Respuesta exitosa:**
```json
{
  "status": "success",
  "sku": "5-0012.9",
  "sap_info": {
    "item_code": "5-0012.9",
    "item_name": "Nombre del producto",
    "pack_sap": "X3",
    "pack_id": "X3",
    "unidad_conversion": 4.0
  },
  "conversion_info": {
    "unidad_conversion": 4.0,
    "formula": "1 docena = 4.0 packs",
    "ejemplo": {
      "docenas": 456,
      "packs": 1824,
      "formula_ejemplo": "456 docenas × 4.0 = 1824 packs"
    }
  },
  "config": {
    "sap_linked_server": "MYHANADB",
    "sap_enabled": true
  },
  "message": "Producto encontrado en SAP",
  "timestamp": "2025-01-21T12:00:00"
}
```

### Opción B: Prueba Directa (sin cache)

**Endpoint:** `GET /sap/test/direct`

**Ejemplo:**
```
http://localhost:8000/sap/test/direct?sku=5-0012.9
```

**Desde Postman:**
1. Método: `GET`
2. URL: `http://localhost:8000/sap/test/direct`
3. Query Params:
   - `sku`: `5-0012.9`

**Respuesta exitosa:**
```json
{
  "status": "success",
  "sku": "5-0012.9",
  "sap_direct_result": {
    "ItemCode": "5-0012.9",
    "ItemName": "Nombre del producto",
    "U_IXX_PACK": "X3"
  },
  "message": "Consulta directa a SAP exitosa",
  "timestamp": "2025-01-21T12:00:00"
}
```

### Desde el Navegador

Simplemente abre en tu navegador:
```
http://localhost:8000/sap/test?sku=5-0012.9
```

### Desde Swagger UI

1. Inicia el servidor: `python src/api_server.py`
2. Abre: `http://localhost:8000/docs`
3. Busca el endpoint `/sap/test`
4. Haz clic en "Try it out"
5. Ingresa el SKU: `5-0012.9`
6. Haz clic en "Execute"

## 🔍 Qué Verificar

### ✅ Si funciona correctamente:

1. **Consulta SAP exitosa:**
   - Debe retornar `ItemCode`, `ItemName`, `U_IXX_PACK`
   - El `U_IXX_PACK` debe ser algo como "X1", "X2", "X3", etc.

2. **Unidad de conversión calculada:**
   - Debe mostrar la unidad de conversión (ej: 4.0 para X3)
   - Debe estar en la tabla `pack_conversion`

3. **Cache funcionando:**
   - La primera consulta consulta SAP
   - Las siguientes consultas usan el cache (más rápido)

### ❌ Si hay errores:

#### Error: "Consultas SAP están deshabilitadas"
- **Solución**: Configura `ENABLE_SAP_QUERIES=true` en `.env`

#### Error: "Invalid object name 'OPENQUERY'"
- **Solución**: El servidor vinculado no está configurado. Verifica que `[MYHANADB]` exista en SQL Server

#### Error: "Producto no encontrado en SAP"
- **Solución**: 
  - Verifica que el SKU exista en SAP
  - Verifica que `SAP_DATABASE` y `SAP_SCHEMA` sean correctos
  - Verifica permisos en el servidor vinculado

#### Error: "No se pudo obtener unidad de conversión"
- **Solución**: 
  - Verifica que el pack (ej: X3) exista en la tabla `pack_conversion`
  - Ejecuta `scripts/create_sap_tables.sql` para poblar los datos iniciales

## 📊 Verificar en la Base de Datos

Después de una consulta exitosa, puedes verificar en SQL Server:

```sql
-- Ver qué hay en el cache
SELECT * FROM producto_sap_cache WHERE sku = '5-0012.9';

-- Ver la unidad de conversión
SELECT * FROM pack_conversion WHERE pack_id = 'X3';
```

## 🚀 Próximos Pasos

Una vez que las pruebas funcionen correctamente:

1. ✅ La integración está lista
2. ✅ Las consultas SAP se ejecutarán automáticamente al guardar facturas
3. ✅ Las conversiones se calcularán automáticamente
4. ✅ Los datos se guardarán en `despacho_detalle` con valores convertidos

## 💡 Tips

- **Primera consulta**: Puede ser lenta (consulta SAP)
- **Consultas siguientes**: Serán rápidas (usa cache)
- **Forzar nueva consulta**: Usa el endpoint `/sap/test/direct` o espera que expire el cache (30 días por defecto)
- **Ver logs**: Revisa la consola donde ejecutas el servidor para ver detalles de las consultas

