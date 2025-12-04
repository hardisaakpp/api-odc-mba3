# Logs de Integración SAP

Este documento describe la tabla `sap_integration_logs` que almacena todos los logs generados durante el proceso de integración con SAP Service Layer.

## Estructura de la Tabla

La tabla `sap_integration_logs` almacena información detallada de cada paso del proceso de integración:

- **Información del proceso**: `proceso_id`, `timestamp_log`, `nivel_log`, `mensaje`
- **Información del usuario**: `usuario`, `fuente`
- **Información de la OC**: `oc_id`, `referencia_despacho`, `proveedor`
- **Información de SAP**: `doc_entry`, `doc_num`, `error_code`, `error_source`, `success`
- **Detalles adicionales**: `detalles_adicionales` (JSON con información completa)

## Filtrado Automático

**Importante**: El sistema filtra automáticamente los logs que no aportan información relevante **antes de guardarlos en la base de datos**. 

Solo se guardan logs que tienen al menos uno de estos campos con valor:
- `oc_id` (UUID de la orden de compra)
- `referencia_despacho` (Referencia del despacho)
- `proveedor` (Código del proveedor)

Los logs de inicio/fin del proceso que no están asociados a una OC específica (donde los tres campos son NULL) **no se guardan** en la base de datos. Esto significa que todas las consultas a la tabla solo devolverán logs relevantes asociados a OCs.

## Crear la Tabla

Ejecutar el script SQL:

```bash
# Desde SQL Server Management Studio o sqlcmd
sqlcmd -S servidor -d store_control -i scripts/create_sap_integration_logs_table.sql
```

O ejecutar el contenido del archivo `scripts/create_sap_integration_logs_table.sql` directamente.

## Consultas Útiles

### 1. Ver todos los logs de un proceso específico

```sql
SELECT 
    timestamp_log,
    nivel_log,
    mensaje,
    oc_id,
    referencia_despacho,
    proveedor,
    doc_num,
    error_code,
    success
FROM sap_integration_logs 
WHERE proceso_id = 'PROCESO_ID_AQUI'
ORDER BY timestamp_log;
```

### 2. Ver todos los errores de las últimas 24 horas

```sql
SELECT 
    timestamp_log,
    proceso_id,
    mensaje,
    oc_id,
    referencia_despacho,
    proveedor,
    error_code,
    error_source,
    detalles_adicionales
FROM sap_integration_logs 
WHERE nivel_log = 'ERROR' 
  AND timestamp_log >= DATEADD(day, -1, GETDATE())
ORDER BY timestamp_log DESC;
```

### 3. Ver resumen de OCs procesadas en un proceso

```sql
SELECT 
    oc_id,
    referencia_despacho,
    proveedor,
    MAX(CASE WHEN success = 1 THEN 'EXITOSO' 
            WHEN success = 0 THEN 'ERROR' 
            ELSE 'EN PROCESO' END) as estado,
    MAX(doc_num) as doc_num_sap,
    MAX(doc_entry) as doc_entry_sap,
    MAX(error_code) as codigo_error,
    MAX(error_source) as origen_error,
    MIN(timestamp_log) as inicio_procesamiento,
    MAX(timestamp_log) as fin_procesamiento
FROM sap_integration_logs
WHERE proceso_id = 'PROCESO_ID_AQUI'
  AND oc_id IS NOT NULL
GROUP BY oc_id, referencia_despacho, proveedor
ORDER BY inicio_procesamiento;
```

### 4. Ver estadísticas por día

```sql
SELECT 
    CAST(timestamp_log AS DATE) as fecha,
    COUNT(*) as total_logs,
    SUM(CASE WHEN nivel_log = 'ERROR' THEN 1 ELSE 0 END) as errores,
    SUM(CASE WHEN nivel_log = 'INFO' THEN 1 ELSE 0 END) as info,
    SUM(CASE WHEN nivel_log = 'WARNING' THEN 1 ELSE 0 END) as warnings,
    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as exitosos,
    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as fallidos,
    COUNT(DISTINCT proceso_id) as procesos_unicos,
    COUNT(DISTINCT oc_id) as ocs_procesadas
FROM sap_integration_logs
WHERE timestamp_log >= DATEADD(day, -7, GETDATE())
GROUP BY CAST(timestamp_log AS DATE)
ORDER BY fecha DESC;
```

### 5. Ver últimas integraciones completadas

```sql
SELECT 
    proceso_id,
    MIN(timestamp_log) as inicio,
    MAX(timestamp_log) as fin,
    DATEDIFF(second, MIN(timestamp_log), MAX(timestamp_log)) as duracion_segundos,
    COUNT(*) as total_logs,
    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as exitosos,
    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as fallidos,
    COUNT(DISTINCT oc_id) as ocs_procesadas,
    MAX(usuario) as usuario,
    MAX(fuente) as fuente
FROM sap_integration_logs
WHERE timestamp_log >= DATEADD(day, -1, GETDATE())
GROUP BY proceso_id
ORDER BY inicio DESC;
```

### 6. Ver errores más comunes

```sql
SELECT 
    error_code,
    error_source,
    LEFT(mensaje, 100) as mensaje_resumen,
    COUNT(*) as cantidad,
    MAX(timestamp_log) as ultima_ocurrencia
FROM sap_integration_logs
WHERE nivel_log = 'ERROR'
  AND timestamp_log >= DATEADD(day, -7, GETDATE())
GROUP BY error_code, error_source, LEFT(mensaje, 100)
ORDER BY cantidad DESC;
```

### 7. Ver detalles completos de un error específico

```sql
SELECT 
    timestamp_log,
    proceso_id,
    oc_id,
    referencia_despacho,
    proveedor,
    mensaje,
    error_code,
    error_source,
    detalles_adicionales
FROM sap_integration_logs
WHERE log_id = 'LOG_ID_AQUI'
   OR (oc_id = 'OC_ID_AQUI' AND nivel_log = 'ERROR')
ORDER BY timestamp_log DESC;
```

### 8. Ver OCs que fallaron con código de error específico

```sql
SELECT DISTINCT
    oc_id,
    referencia_despacho,
    proveedor,
    error_code,
    error_source,
    MAX(timestamp_log) as fecha_error
FROM sap_integration_logs
WHERE error_code = '-4013'  -- Ejemplo: Posting period locked
  AND timestamp_log >= DATEADD(day, -7, GETDATE())
GROUP BY oc_id, referencia_despacho, proveedor, error_code, error_source
ORDER BY fecha_error DESC;
```

### 9. Ver logs de un usuario específico

```sql
SELECT 
    timestamp_log,
    proceso_id,
    nivel_log,
    mensaje,
    oc_id,
    referencia_despacho,
    success
FROM sap_integration_logs
WHERE usuario = 'admin'
  AND timestamp_log >= DATEADD(day, -1, GETDATE())
ORDER BY timestamp_log DESC;
```

### 10. Ver timeline completo de un proceso

```sql
SELECT 
    timestamp_log,
    nivel_log,
    mensaje,
    CASE 
        WHEN oc_id IS NOT NULL THEN CONCAT('OC: ', LEFT(oc_id, 8), '...')
        ELSE NULL
    END as oc_info,
    CASE 
        WHEN doc_num IS NOT NULL THEN CONCAT('DocNum: ', doc_num)
        WHEN error_code IS NOT NULL THEN CONCAT('Error: ', error_code)
        ELSE NULL
    END as resultado
FROM sap_integration_logs
WHERE proceso_id = 'PROCESO_ID_AQUI'
ORDER BY timestamp_log;
```

## Niveles de Log

- **INFO**: Información general del proceso (inicio, conexión, procesamiento, éxito)
- **WARNING**: Advertencias (ej: SSL deshabilitado)
- **ERROR**: Errores (fallos de conexión, errores de SAP, errores del backend)
- **DEBUG**: Información de debugging (no se guarda actualmente en la tabla)

## Origen de Errores (error_source)

- **SAP**: Error devuelto por SAP Service Layer (incluye `error_code`)
- **BACKEND**: Error generado por el backend antes de enviar a SAP
- **SAP_CONNECTION**: Error de conexión con SAP Service Layer
- **NULL**: Sin error (éxito)

## Detalles Adicionales (detalles_adicionales)

Campo JSON que puede contener:

- **sap_response**: Respuesta completa de SAP cuando la OC se crea exitosamente
- **sap_error_details**: Detalles completos del error cuando SAP devuelve un error

Ejemplo de consulta para ver detalles:

```sql
SELECT 
    log_id,
    timestamp_log,
    mensaje,
    detalles_adicionales
FROM sap_integration_logs
WHERE detalles_adicionales IS NOT NULL
ORDER BY timestamp_log DESC;
```

## Mantenimiento

### Limpiar logs antiguos (más de 30 días)

```sql
DELETE FROM sap_integration_logs
WHERE timestamp_log < DATEADD(day, -30, GETDATE());
```

### Estadísticas de uso de espacio

```sql
SELECT 
    COUNT(*) as total_registros,
    COUNT(DISTINCT proceso_id) as procesos_unicos,
    COUNT(DISTINCT oc_id) as ocs_unicas,
    MIN(timestamp_log) as log_mas_antiguo,
    MAX(timestamp_log) as log_mas_reciente,
    SUM(DATALENGTH(detalles_adicionales)) / 1024.0 / 1024.0 as mb_detalles,
    -- Verificar que todos los logs tienen información de OC (debería ser 0)
    SUM(CASE WHEN oc_id IS NULL AND referencia_despacho IS NULL AND proveedor IS NULL 
        THEN 1 ELSE 0 END) as logs_sin_oc
FROM sap_integration_logs;
```

**Nota**: El campo `logs_sin_oc` debería ser siempre 0, ya que el sistema filtra automáticamente estos logs antes de guardarlos.

