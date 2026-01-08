# ⚠️ IMPORTANTE: Migración Fase 5 - Orden de Ejecución

## 🔴 PROBLEMA COMÚN

Si obtienes el error:
```
SQL Error [207] [S0001]: Invalid column name 'doc_entry'.
```

**Causa:** El código Python ya fue actualizado para usar `doc_entry` y `pedido_id`, pero el script SQL **NO se ha ejecutado todavía** en la base de datos.

## ✅ SOLUCIÓN

**EJECUTAR EL SCRIPT SQL PRIMERO**, antes de usar la aplicación:

### Opción 1: Script Python DIRECTO (RECOMENDADO) ⭐

Usa la misma configuración de conexión que tu aplicación:

```bash
python scripts/ejecutar_migracion_fase5_directo.py
```

**Ventajas:**
- ✅ Usa la misma configuración de conexión que la app (del `.env`)
- ✅ No necesitas configurar sqlcmd
- ✅ Maneja autenticación Windows automáticamente
- ✅ Ejecuta comandos SQL directamente (más confiable)
- ✅ Muestra resultados y errores detallados
- ✅ Verifica automáticamente que las columnas se crearon

**Nota:** Este es el método más confiable y el que ya funcionó exitosamente.

### Opción 2: SQL Server Management Studio (SSMS)

1. Abre SQL Server Management Studio
2. Conéctate a tu servidor
3. Abre el archivo: `scripts/add_doc_entry_and_pedido_id.sql`
4. Ejecuta el script completo (F5)

### Opción 3: sqlcmd (si tienes la conexión configurada)

```bash
sqlcmd -S tu_servidor -d store_control -U tu_usuario -P tu_password -i scripts/add_doc_entry_and_pedido_id.sql
```

O si usas autenticación Windows:

```bash
sqlcmd -S tu_servidor -d store_control -E -i scripts/add_doc_entry_and_pedido_id.sql
```

### Paso 2: Verificar

Después de ejecutar el script, verifica que las columnas existan:

```sql
SELECT 
    COLUMN_NAME, 
    DATA_TYPE, 
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'orden_compra_cabecera'
AND COLUMN_NAME IN ('doc_entry', 'pedido_id')
ORDER BY COLUMN_NAME;
```

Deberías ver:
- `doc_entry` (INT, NULL)
- `pedido_id` (UNIQUEIDENTIFIER, NULL)

### Paso 3: Reiniciar Aplicación

Si la aplicación estaba corriendo, **reiníciala** después de ejecutar el script SQL.

---

## 📋 Orden Correcto de Implementación

1. ✅ **Ejecutar script SQL** → `scripts/add_doc_entry_and_pedido_id.sql`
2. ✅ **Verificar columnas** creadas
3. ✅ **Reiniciar aplicación** (si estaba corriendo)
4. ✅ **Probar endpoints** → Verificar que funcionen correctamente

---

## 🔧 Si Ya Ejecutaste Código Antes del Script

Si ya ejecutaste código Python que intenta usar `doc_entry`:

1. **Detener la aplicación** (si está corriendo)
2. **Ejecutar el script SQL** (ver arriba)
3. **Verificar columnas** creadas
4. **Reiniciar la aplicación**
5. **Probar de nuevo**

---

## ✅ Verificación Final

Para confirmar que todo está bien:

```sql
-- Verificar estructura completa de la tabla
SELECT 
    COLUMN_NAME, 
    DATA_TYPE, 
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'orden_compra_cabecera'
ORDER BY ORDINAL_POSITION;
```

Deberías ver `doc_entry` y `pedido_id` en la lista.

