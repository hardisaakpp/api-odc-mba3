# Sistema de Migraciones para Producción

Sistema robusto y trazable para ejecutar migraciones SQL en producción de forma controlada e idempotente.

## 🎯 Características

- ✅ **Trazabilidad**: Cada migración se registra en `schema_migrations` con timestamp y checksum
- ✅ **Idempotencia**: Las migraciones no se ejecutan dos veces
- ✅ **Orden garantizado**: Manifest YAML define dependencias y orden de ejecución
- ✅ **Dry-run**: Validar sin ejecutar
- ✅ **Categorización**: Filtrar por tipo (base, alter, data, config, etc)
- ✅ **Control fino**: Ejecutar hasta una versión específica
- ✅ **Seguridad**: Manejo de errores, rollback automático y confirmaciones para cambios críticos

---

## 📋 Tabla de Control

```sql
CREATE TABLE schema_migrations (
    version VARCHAR(50) PRIMARY KEY,
    name NVARCHAR(255),
    applied_at DATETIME,
    execution_time_ms INT,
    checksum VARCHAR(64),
    applied_by NVARCHAR(100)
);
```

**NO modificar manualmente** - usar siempre `migration_runner.py`

---

## 🚀 Uso Básico

### 1. Ver estado actual

```bash
python scripts/migration_runner.py --status
```

Muestra:
- Migraciones aplicadas (con las últimas 10)
- Migraciones pendientes
- Total y progreso

### 2. Dry-run (validar sin ejecutar)

```bash
python scripts/migration_runner.py --dry-run
```

**¡SIEMPRE ejecutar dry-run antes de aplicar en producción!**

Valida:
- ✅ Scripts existen
- ✅ Sintaxis SQL es correcta
- ✅ Dependencias están satisfechas
- ✅ No hay errores de ejecución

### 3. Ejecutar migraciones pendientes

```bash
# Solo migraciones base (tablas principales)
python scripts/migration_runner.py --category base

# Hasta una versión específica
python scripts/migration_runner.py --up-to 101

# Todas las pendientes (¡CUIDADO!)
python scripts/migration_runner.py
```

---

## 📂 Estructura de Archivos

```
scripts/
├── migrations/
│   └── 000_create_schema_migrations.sql  # Tabla de control (ejecutar primero)
├── migrations_manifest.yaml               # Catálogo ordenado de migraciones
├── migration_runner.py                    # Runner principal
└── [scripts SQL individuales]
```

---

## 📚 Catálogo y esquema

- [CATALOGO_MIGRACIONES.md](CATALOGO_MIGRACIONES.md): las 113 migraciones del manifest, en orden de ejecución, con su categoría, archivo y descripción (generado con `python scripts/generar_catalogo_migraciones.py`).
- [ESQUEMA_BD.md](ESQUEMA_BD.md): el esquema resultante (43 tablas), leído de la base real (generado con `scripts/generar_esquema_bd.py`).

## 🆕 Base de datos vacía y migraciones idempotentes

- **Migración `000.5` (`bootstrap_tablas_sin_script`)**: crea, si no existen, `despacho_cabecera`, `despacho_detalle`, `orden_compra_cabecera`, `orden_compra_detalle` y `pack_conversion`. Esas tablas se crearon a mano en los ambientes originales y el resto del manifest asume que existen; sin ella una **base vacía** (por ejemplo, un entorno local nuevo) no se puede levantar. Va primero a propósito y es un *no-op* en test y producción.
- **Orden 008 antes que 007:** en el manifest la 008 se ejecuta antes que la 007, porque la 007 depende de ella (`FK_confirmacion_rayo_respuesta`).
- **Migraciones 665, 666 y 667 son idempotentes:** al re-ejecutarlas no reducen columnas que ya se ampliaron ni borran un `CHECK` equivocado. Cada `ALTER` solo corre si la columna mide menos de lo que se pretende.
- La última versión del manifest es la **669** (`add_orden_compra_listado_indexes`); la 668 amplía `pedido.mensaje` a NVARCHAR(500).

## 📝 Manifest de Migraciones

El archivo `migrations_manifest.yaml` define todas las migraciones en orden:

```yaml
migrations:
  - version: "001"
    name: "create_pedido_tables"
    file: "create_pedido_tables.sql"
    description: "Crear tablas principales de pedidos"
    category: "base"
    dependencies: []

  - version: "301"
    name: "migrate_pedido_estado_id"
    file: "migrate_pedido_estado_id.sql"
    description: "Migrar columna estado a estado_id"
    category: "data"
    dependencies: ["004", "005"]
    
  - version: "501"
    name: "configure_sap_linked_server"
    file: "configure_sap_linked_server.sql"
    description: "Configurar servidor vinculado SAP"
    category: "sap"
    manual: true
    warning: "⚠️ Requiere credenciales y permisos de administrador"
```

### Campos del Manifest

| Campo | Obligatorio | Descripción |
|-------|-------------|-------------|
| `version` | ✅ | Identificador único (ej. "001", "101") |
| `name` | ✅ | Nombre descriptivo de la migración |
| `file` | ✅ | Nombre del archivo SQL en `scripts/` |
| `description` | ✅ | Descripción completa de qué hace |
| `category` | ✅ | base, alter, index, data, config, sap, rollback |
| `dependencies` | ❌ | Array de versiones que deben aplicarse antes |
| `manual` | ❌ | Si `true`, se salta a menos que se use `--include-manual` |
| `warning` | ❌ | Mensaje de advertencia que requiere confirmación |
| `skip_by_default` | ❌ | Si `true`, se salta siempre (para rollbacks) |

---

## 🏷️ Categorías de Migraciones

| Categoría | Descripción | Ejemplos |
|-----------|-------------|----------|
| `base` | Tablas y estructuras fundamentales | `create_pedido_tables.sql` |
| `alter` | Agregar/modificar columnas | `add_doc_entry_and_pedido_id.sql` |
| `index` | Crear índices para optimización | `add_index_pedido_usuario_fecha.sql` |
| `data` | Migración de datos existentes | `migrate_pedido_estado_id.sql` |
| `config` | Estados, configuraciones | `add_estado_finalizado.sql` |
| `sap` | Configuración de servidores SAP | `configure_sap_linked_server.sql` |
| `rollback` | Revertir cambios (solo manual) | `remove_bodega_column.sql` |

---

## 🔧 Opciones Avanzadas

### Filtrar por categoría

```bash
# Solo migraciones base
python scripts/migration_runner.py --category base

# Solo alteraciones de columnas
python scripts/migration_runner.py --category alter

# Solo configuración de estados
python scripts/migration_runner.py --category config
```

### Ejecutar hasta una versión

```bash
# Ejecutar migraciones 001 hasta 101 (inclusive)
python scripts/migration_runner.py --up-to 101
```

### Incluir migraciones manuales

```bash
# Por defecto se saltan, usar --include-manual para incluirlas
python scripts/migration_runner.py --include-manual --dry-run
```

**⚠️ Migraciones manuales** requieren intervención porque:
- Necesitan credenciales específicas
- Tienen impacto en otros sistemas
- Requieren coordinación con equipos

### Logs detallados

```bash
python scripts/migration_runner.py --verbose
```

---

## 🏭 Proceso de Despliegue a Producción

### Fase 1: Preparación (Desarrollo/QA)

1. **Crear nueva migración**
   - Escribir script SQL idempotente en `scripts/`
   - Agregar entrada al final de `migrations_manifest.yaml`
   - Probar localmente

2. **Validar**
   ```bash
   # Dry-run en ambiente de desarrollo
   python scripts/migration_runner.py --dry-run --verbose
   ```

3. **Ejecutar en desarrollo**
   ```bash
   python scripts/migration_runner.py
   ```

4. **Commit y PR**
   ```bash
   git add scripts/ docs/
   git commit -m "feat: agregar migración 610 - nueva tabla xyz"
   git push
   ```

### Fase 2: Pre-Producción

1. **Backup de BD producción** (¡CRÍTICO!)
   ```sql
   BACKUP DATABASE store_control 
   TO DISK = 'C:\Backups\store_control_pre_migracion_YYYYMMDD.bak'
   WITH FORMAT, COMPRESSION;
   ```

2. **Conectar a entorno de pre-producción**
   - Verificar `.env` apunta a servidor correcto
   - Confirmar credenciales y permisos

3. **Estado actual**
   ```bash
   python scripts/migration_runner.py --status
   ```

4. **Dry-run**
   ```bash
   python scripts/migration_runner.py --dry-run
   ```
   
   ✅ Si todo OK → continuar  
   ❌ Si falla → corregir y repetir

### Fase 3: Ejecución en Producción

1. **Ventana de mantenimiento** (opcional, según impacto)
   - Notificar a usuarios si aplica
   - Detener servicios dependientes si es necesario

2. **Ejecutar migraciones**
   ```bash
   # Si son pocas migraciones base/alter
   python scripts/migration_runner.py --category base
   python scripts/migration_runner.py --category alter
   
   # O ejecutar todo pendiente
   python scripts/migration_runner.py
   ```

3. **Verificar**
   ```bash
   # Ver qué se aplicó
   python scripts/migration_runner.py --status
   
   # Verificar tablas manualmente si aplica
   sqlcmd -S servidor -d store_control -Q "SELECT * FROM schema_migrations ORDER BY applied_at DESC"
   ```

4. **Reiniciar servicios**
   - Reiniciar API (si aplica): ver [DEPLOY_PRODUCCION.md](DEPLOY_PRODUCCION.md) — en producción típica: `sudo systemctl restart odc-sap-api`; si aplica Celery con el mismo código/entorno: `sudo systemctl restart celery-worker celery-beat` (nombres exactos en esa guía).
   - Verificar logs de aplicación
   - Probar funcionalidad crítica

### Fase 4: Rollback (si algo sale mal)

Si una migración falla:

1. **El runner hace rollback automático** del bloque fallido
2. Las migraciones anteriores exitosas **NO** se revierten automáticamente
3. Opciones:
   
   **A. Corregir y continuar**
   ```bash
   # Corregir el script SQL problemático
   # Actualizar checksum en manifest si es necesario
   # Re-ejecutar
   python scripts/migration_runner.py
   ```
   
   **B. Rollback manual** (si existe migración de rollback)
   ```bash
   # Agregar migración de rollback al manifest
   python scripts/migration_runner.py --category rollback --include-manual
   ```
   
   **C. Restaurar backup** (último recurso)
   ```sql
   -- Desconectar usuarios
   ALTER DATABASE store_control SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
   
   -- Restaurar
   RESTORE DATABASE store_control 
   FROM DISK = 'C:\Backups\store_control_pre_migracion_YYYYMMDD.bak'
   WITH REPLACE;
   
   -- Reconectar
   ALTER DATABASE store_control SET MULTI_USER;
   ```

---

## ✅ Checklist de Despliegue

### Pre-Despliegue
- [ ] Backup de base de datos realizado
- [ ] Variables de entorno verificadas (`.env`)
- [ ] Dry-run ejecutado sin errores
- [ ] Coordinación con equipo (si aplica)
- [ ] Ventana de mantenimiento agendada (si aplica)

### Durante Despliegue
- [ ] Status verificado
- [ ] Migraciones ejecutadas por categoría
- [ ] Logs revisados sin errores
- [ ] Verificación en BD exitosa

### Post-Despliegue
- [ ] Servicios reiniciados
- [ ] Funcionalidad crítica probada
- [ ] Logs de aplicación sin errores
- [ ] Notificación a equipo/usuarios

---

## 📖 Agregar Nueva Migración

1. **Crear script SQL**
   ```sql
   -- scripts/nueva_funcionalidad.sql
   IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'nueva_tabla')
   BEGIN
       CREATE TABLE nueva_tabla (
           id INT PRIMARY KEY,
           nombre NVARCHAR(100)
       );
       PRINT '✅ Tabla nueva_tabla creada';
   END
   ELSE
   BEGIN
       PRINT 'ℹ️ Tabla nueva_tabla ya existe';
   END
   GO
   ```

2. **Agregar al manifest**
   ```yaml
   # En scripts/migrations_manifest.yaml
   migrations:
     # ... migraciones existentes ...
     
     - version: "610"  # Siguiente número disponible
       name: "create_nueva_tabla"
       file: "nueva_funcionalidad.sql"
       description: "Crear tabla para nueva funcionalidad X"
       category: "base"
       dependencies: ["004"]  # Si depende de otras migraciones
   ```

3. **Probar localmente**
   ```bash
   python scripts/migration_runner.py --dry-run --verbose
   python scripts/migration_runner.py
   ```

4. **Commit**
   ```bash
   git add scripts/nueva_funcionalidad.sql scripts/migrations_manifest.yaml
   git commit -m "feat: agregar tabla nueva_funcionalidad (migración 610)"
   ```

---

## 🔍 Troubleshooting

### Error: "Tabla schema_migrations no existe"

**Solución**: Ejecutar primero:
```bash
# Opción 1: Con el runner (recomendado)
python scripts/migration_runner.py --status

# Opción 2: Manualmente
sqlcmd -S servidor -d store_control -i scripts/migrations/000_create_schema_migrations.sql
```

### Error: "No se encontró el script X.sql"

**Causa**: El `file` en el manifest no coincide con el nombre real del archivo.

**Solución**: Verificar que el archivo existe en `scripts/` y el nombre coincide exactamente.

### Error: "Dependencias sin aplicar: ['004']"

**Causa**: La migración requiere que otras se apliquen primero.

**Solución**: Ejecutar migraciones en orden o eliminar filtros:
```bash
# Ejecutar sin filtros para aplicar en orden correcto
python scripts/migration_runner.py
```

### Migración tarda mucho

**Causa**: Migraciones de datos grandes o índices en tablas grandes.

**Solución**: 
1. Verificar con dry-run primero
2. Ejecutar en ventana de mantenimiento
3. Monitorear progreso con `--verbose`

### ¿Cómo re-ejecutar una migración?

**NO RECOMENDADO** - el sistema previene esto para evitar duplicados.

Si realmente necesitas:
```sql
-- 1. Eliminar el registro (¡PELIGRO!)
DELETE FROM schema_migrations WHERE version = '610';

-- 2. Re-ejecutar
python scripts/migration_runner.py
```

**Mejor opción**: Crear una nueva migración correctiva.

---

## 📚 Relación con Documentos Existentes

Este sistema reemplaza/mejora los procesos manuales descritos en:

- `ESTADOS_PEDIDO.md` - Migración de estados ahora automatizada
- `IMPLEMENTACION_HOMOLOGACIONES_SKU.md` - Scripts ahora en manifest
- `RESPUESTA_SAP_IMPLEMENTATION.md` - Pasos SQL ahora migraciones
- `CONFIGURACION.md` - Scripts de configuración ahora trazables

**Nueva arquitectura**:
- ❌ Antes: Ejecutar scripts manualmente, sin orden, sin trazabilidad
- ✅ Ahora: Un comando, orden garantizado, registro completo

---

## 🎓 Mejores Prácticas

### Escritura de Scripts SQL

1. **Siempre idempotente**
   ```sql
   -- ✅ Bueno
   IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'mi_tabla')
   BEGIN
       CREATE TABLE mi_tabla (...);
   END
   
   -- ❌ Malo
   CREATE TABLE mi_tabla (...);  -- Falla si ya existe
   ```

2. **Usar transacciones implícitas** (el runner maneja rollback)

3. **Mensajes informativos**
   ```sql
   PRINT '✅ Tabla creada exitosamente';
   PRINT 'ℹ️ Tabla ya existe, saltando';
   PRINT '⚠️ Advertencia: ...';
   ```

4. **Dividir por GO** cuando sea necesario
   ```sql
   CREATE TABLE tabla1 (...);
   GO
   
   ALTER TABLE tabla1 ADD CONSTRAINT ...;
   GO
   ```

### Gestión del Manifest

1. **Versionado secuencial**: 001, 002, ..., no saltar números
2. **Nunca modificar versiones aplicadas** en producción
3. **Categorías claras**: Facilita filtrado y despliegues parciales
4. **Dependencies**: Solo cuando hay FK o lógica que depende de otra migración
5. **Warnings**: Para cambios que afectan producción o requieren coordinación

### Coordinación de Equipo

1. **Una persona ejecuta** en producción (evitar conflictos)
2. **Comunicar antes** de ejecutar migraciones data/config
3. **Backup siempre** antes de despliegue grande
4. **Dry-run obligatorio** en producción

---

## 🔗 Referencias

- **Código**: `scripts/migration_runner.py`
- **Manifest**: `scripts/migrations_manifest.yaml`
- **Scripts**: `scripts/*.sql`
- **Control de versiones**: Tabla `schema_migrations`

---

## 📞 Soporte

Si tienes problemas:

1. Revisar logs con `--verbose`
2. Verificar estado con `--status`
3. Probar con `--dry-run` primero
4. Consultar este documento
5. Revisar código del runner para entender comportamiento

**Nota**: El sistema está diseñado para ser seguro y conservador. Si el runner impide algo, probablemente es por una buena razón. Revisa dependencias y orden de migraciones antes de forzar cambios.
