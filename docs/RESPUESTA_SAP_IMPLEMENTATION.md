# Implementación de Persistencia de Respuesta SAP

## 📋 Resumen

Este documento describe los cambios implementados para persistir automáticamente las respuestas de SAP directamente en la tabla `orden_compra_cabecera`, cumpliendo con los requisitos del frontend.

## 🎯 Objetivo

Modificar el endpoint `/integrar-sap` (POST) para que **persista automáticamente** en la base de datos el resultado de la integración con SAP, incluyendo la respuesta (`respuesta_sap`) y metadatos relacionados.

## 📝 Cambios Realizados

### 1. Script SQL: `scripts/add_respuesta_sap_fields.sql`

Se creó un script SQL que agrega los siguientes campos a la tabla `orden_compra_cabecera`:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `respuesta_sap` | NVARCHAR(MAX) | Mensaje o respuesta completa de SAP (éxito o error) |
| `fecha_procesado` | DATETIME | Timestamp cuando se procesó la orden con SAP |
| `error_message` | NVARCHAR(MAX) | Mensaje de error detallado (si aplica) |
| `error_code` | VARCHAR(50) | Código de error de SAP (ej: -4013) |
| `error_source` | VARCHAR(50) | Origen del error: 'SAP', 'BACKEND', 'SAP_CONNECTION' |
| `updated_at` | DATETIME | Timestamp de última actualización |

**Índices creados:**
- `IX_orden_compra_cabecera_estado` - Para búsquedas por estado
- `IX_orden_compra_cabecera_referencia_despacho` - Para búsquedas por referencia

### 2. Repositorio: `src/database/repositories/orden_compra_repository.py`

#### Método `update_estado` actualizado:
```python
def update_estado(
    self, 
    oc_id: str, 
    estado: str, 
    numero_oc_sap: Optional[str] = None,
    respuesta_sap: Optional[str] = None,      # ⭐ NUEVO
    error_message: Optional[str] = None,       # ⭐ NUEVO
    error_code: Optional[str] = None,          # ⭐ NUEVO
    error_source: Optional[str] = None         # ⭐ NUEVO
) -> bool:
```

**Comportamiento:**
- Actualiza `fecha_procesado` automáticamente con `GETDATE()`
- Actualiza `updated_at` automáticamente con `GETDATE()`
- Si el estado es `ENVIADA`, limpia los campos de error (los pone en NULL)
- Construye SQL dinámicamente solo con los campos proporcionados

#### Métodos de consulta actualizados:
Todos los métodos que consultan `orden_compra_cabecera` ahora incluyen los nuevos campos:
- ✅ `get_existing_cabecera()`
- ✅ `get_by_estado()`
- ✅ `get_all()`
- ✅ `find_by_referencia_despacho()`
- ✅ `update_cabecera()`

### 3. Servicio SAP: `src/database/services/oc_sap_service.py`

#### Método `enviar_oc_a_sap` actualizado:

**Caso exitoso:**
```python
oc_repo.update_estado(
    oc_id,
    "ENVIADA",
    numero_oc_sap=str(doc_num) if doc_num else None,
    respuesta_sap=mensaje_sap,        # ⭐ Mensaje de éxito
    error_message=None,
    error_code=None,
    error_source=None
)
```

**Caso de error:**
```python
oc_repo.update_estado(
    oc_id, 
    "ERROR",
    respuesta_sap=error_final,        # ⭐ Mensaje de error
    error_message=error_final,
    error_code=str(error_code) if error_code else None,
    error_source="SAP"  # o "BACKEND", "SAP_CONNECTION"
)
```

Todos los puntos de error en el servicio ahora persisten información detallada:
- ✅ Error al obtener detalles de la OC
- ✅ Error al construir JSON de SAP
- ✅ Error de conexión con SAP
- ✅ Error devuelto por SAP
- ✅ Errores inesperados

## 🚀 Cómo Usar

### Paso 1: Ejecutar el Script SQL

```bash
# Desde SQL Server Management Studio o sqlcmd
sqlcmd -S servidor -d store_control -i scripts/add_respuesta_sap_fields.sql
```

O ejecutar manualmente el contenido del archivo en SQL Server Management Studio.

### Paso 2: Reiniciar la Aplicación

Los cambios en el código Python ya están implementados. Solo necesitas reiniciar el servidor FastAPI.

### Paso 3: Probar el Endpoint

```bash
# Caso 1: Una orden exitosa
POST /integrar-sap?referencia_despacho=900125353

# Caso 2: Múltiples órdenes
POST /integrar-sap?referencia_despacho=900125353&referencia_despacho=900125354
```

## 📊 Estructura de Respuesta del Endpoint

El endpoint `/integrar-sap` ahora retorna:

**Éxito:**
```json
{
  "status": "success",
  "message": "Procesadas 1 órdenes",
  "metadata": {
    "detalles": [
      {
        "success": true,
        "referencia_despacho": "900125353",
        "oc_id": "...",
        "proveedor": "P1790389219001",
        "doc_num": 12345,
        "doc_entry": 67890,
        "message": "Orden creada exitosamente. DocNum: 12345",
        "sap_response": { /* respuesta completa de SAP */ }
      }
    ],
    "total": 1,
    "enviadas": 1,
    "errores": 0
  }
}
```

**Error:**
```json
{
  "status": "partial",
  "metadata": {
    "detalles": [
      {
        "success": false,
        "referencia_despacho": "900125353",
        "oc_id": "...",
        "proveedor": "P1790389219001",
        "error": "El proveedor no existe en SAP (Código SAP: -4013)",
        "error_message": "El proveedor no existe en SAP (Código SAP: -4013)",
        "error_code": "-4013",
        "error_source": "SAP",
        "sap_error_details": { /* detalles completos del error */ }
      }
    ],
    "total": 1,
    "enviadas": 0,
    "errores": 1
  }
}
```

## 🔍 Consultar Respuestas SAP

### Desde el Frontend

```javascript
// GET /ordenes-compra?estado=ENVIADA
// Cada orden ahora incluye:
{
  "oc_id": "...",
  "estado": "ENVIADA",
  "numero_oc_sap": "12345",
  "respuesta_sap": "Orden creada exitosamente. DocNum: 12345",
  "fecha_procesado": "2025-12-16T10:30:00",
  "error_message": null,
  "error_code": null,
  "error_source": null,
  "updated_at": "2025-12-16T10:30:00"
}
```

### Desde SQL

```sql
-- Ver órdenes procesadas recientemente con sus respuestas
SELECT 
    oc_id,
    referencia_despacho,
    proveedor,
    estado,
    numero_oc_sap,
    respuesta_sap,           -- ⭐ Mensaje de SAP
    fecha_procesado,
    error_message,
    error_code,
    error_source,
    updated_at
FROM orden_compra_cabecera 
WHERE fecha_procesado > DATEADD(hour, -1, GETDATE())
ORDER BY fecha_procesado DESC;

-- Ver solo órdenes con error
SELECT 
    referencia_despacho,
    proveedor,
    respuesta_sap,
    error_code,
    error_source,
    fecha_procesado
FROM orden_compra_cabecera 
WHERE estado = 'ERROR'
ORDER BY fecha_procesado DESC;

-- Ver solo órdenes enviadas exitosamente
SELECT 
    referencia_despacho,
    numero_oc_sap,
    respuesta_sap,
    fecha_procesado
FROM orden_compra_cabecera 
WHERE estado = 'ENVIADA'
ORDER BY fecha_procesado DESC;
```

## ⚠️ Compatibilidad

### Sistema de Logs
Los cambios **NO afectan** el sistema de logs existente. El sistema continúa guardando logs detallados en `sap_integration_logs` con información completa de cada integración.

**Ahora tienes dos formas de consultar respuestas SAP:**

1. **`orden_compra_cabecera`** - Para consultas rápidas y directas de cada orden
2. **`sap_integration_logs`** - Para logs detallados, auditoría y troubleshooting

### Endpoints Existentes
Todos los endpoints existentes siguen funcionando sin cambios:
- ✅ `GET /ordenes-compra` - Ahora incluye los nuevos campos
- ✅ `GET /ordenes-compra/logs` - Sin cambios, sigue funcionando igual
- ✅ `POST /integrar-sap` - Ahora persiste respuestas automáticamente

## 📌 Notas Importantes

1. **Retrocompatibilidad**: Los nuevos campos son `NULL` por defecto, así que las órdenes antiguas no se ven afectadas.

2. **Timestamps automáticos**: 
   - `fecha_procesado` se actualiza cuando cambia el estado
   - `updated_at` se actualiza en cada modificación

3. **Limpieza de errores**: Cuando una orden pasa a estado `ENVIADA`, los campos de error se limpian automáticamente.

4. **Validación**: El script SQL incluye validaciones para no duplicar columnas si ya existen.

5. **Índices**: Se agregan índices en `estado` y `referencia_despacho` para mejorar el rendimiento de consultas.

## ✅ Checklist de Implementación

- [x] Script SQL creado (`scripts/add_respuesta_sap_fields.sql`)
- [x] Repositorio actualizado (`orden_compra_repository.py`)
- [x] Servicio SAP actualizado (`oc_sap_service.py`)
- [x] Todos los métodos de consulta actualizados
- [x] Todos los puntos de error cubiertosmétodos de consulta actualizados
- [x] Sin errores de linter
- [x] Documentación completa

## 🔄 Próximos Pasos

1. **Ejecutar el script SQL** en el servidor de base de datos
2. **Reiniciar el servidor** FastAPI
3. **Probar** con el endpoint `/integrar-sap`
4. **Verificar** que el frontend pueda leer los nuevos campos

## 📞 Soporte

Si hay algún problema con la implementación:
1. Verificar que el script SQL se ejecutó correctamente
2. Revisar logs del servidor FastAPI
3. Consultar `sap_integration_logs` para detalles de errores
4. Verificar estructura de la tabla con:
   ```sql
   SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH 
   FROM INFORMATION_SCHEMA.COLUMNS 
   WHERE TABLE_NAME = 'orden_compra_cabecera';
   ```

---

**Fecha de implementación:** 2025-12-16
**Versión:** 1.0
**Responsable:** Backend Team





