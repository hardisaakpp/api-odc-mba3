# Scripts de Base de Datos

Este directorio contiene scripts SQL para inicialización, migraciones y mantenimiento de la base de datos.

## 🚀 Sistema de Migraciones (NUEVO)

**Ahora usamos un sistema automatizado de migraciones** para despliegues seguros y trazables.

### Inicio Rápido

```bash
# 1. Ver estado actual
python scripts/migration_runner.py --status

# 2. Validar sin ejecutar (¡SIEMPRE PRIMERO!)
python scripts/migration_runner.py --dry-run

# 3. Ejecutar migraciones pendientes
python scripts/migration_runner.py
```

### Documentación Completa

Ver **[docs/DEPLOY_MIGRATIONS.md](../docs/DEPLOY_MIGRATIONS.md)** para:
- Guía completa de uso
- Proceso de despliegue a producción
- Agregar nuevas migraciones
- Troubleshooting
- Mejores prácticas

---

## 📂 Estructura

```
scripts/
├── migrations/
│   └── 000_create_schema_migrations.sql  # Tabla de control
├── migrations_manifest.yaml               # Catálogo ordenado de migraciones
├── migration_runner.py                    # Runner principal
├── README.md                              # Este archivo
└── [scripts SQL individuales]             # Migraciones individuales
```

---

## 📋 Archivos Importantes

### Sistema de Migraciones

| Archivo | Propósito |
|---------|-----------|
| `migration_runner.py` | Runner principal - ejecuta migraciones |
| `migrations_manifest.yaml` | Catálogo de todas las migraciones en orden |
| `migrations/000_create_schema_migrations.sql` | Tabla de control |

### Scripts SQL por Categoría

#### Base (Tablas Fundamentales)
- `create_pedido_tables.sql` - Tablas principales de pedidos
- `create_pedido_estado_table.sql` - Estados de pedido
- `create_distribucion_confirmada_table.sql` - Distribución confirmada
- `create_sap_tables.sql` - Cache de productos SAP
- `create_sku_homologacion_table.sql` - Homologación de SKUs
- `create_respuesta_proveedor_tables.sql` - Respuestas de proveedor
- `create_pedido_sap_procesamiento_table.sql` - Procesamiento SAP
- `create_remision_cabecera_table.sql` - Remisiones
- `create_sap_integration_logs_table.sql` - Logs de integración SAP

#### Alteraciones (Agregar/Modificar Columnas)
- `add_doc_entry_and_pedido_id.sql` - Campos para trazabilidad SAP
- `add_respuesta_sap_fields.sql` - Campos de respuesta SAP
- `add_precio_unitario_sap_column.sql` - Precio unitario SAP
- `add_codigo_bodega_orden_compra.sql` - Bodega en orden de compra
- `add_fila_origen_pedido.sql` - Fila origen en detalle
- `add_campos_modificados_manual.sql` - Campos de auditoría

#### Índices
- `add_index_pedido_usuario_fecha.sql` - Índice compuesto usuario/fecha

#### Migraciones de Datos
- `migrate_pedido_estado_id.sql` - Migrar estado (string) a estado_id (int)
- `migrate_sku_homologacion_full.sql` - Sincronización de homologaciones

#### Estados y Configuración
- `add_estado_pedido.sql` - Estados iniciales
- `add_estado_finalizado.sql` - Estado FINALIZADO
- `add_estado_despachar_y_facturar.sql` - Estado DESPACHAR_Y_FACTURAR
- `renombrar_estado_4_a_confirmado.sql` - Renombrar estado 4
- `renumerar_estados_gestionar_3_redistribucion.sql` - Reestructurar estados

#### SAP (Configuración Manual)
- `configure_sap_linked_server.sql` - Servidor vinculado SAP HANA
- `configure_sap_linked_server_alternative.sql` - Configuración alternativa

#### Utilidades Python
- `check_db_connection.py` - Verificar conexión a BD
- `test_sap_query.py` - Probar consultas SAP
- `verify_pedido_tables.py` - Verificar integridad de tablas

---

## 🎯 Uso por Escenario

### Despliegue Inicial (Base de Datos Nueva)

```bash
# Ejecutar todas las migraciones base
python scripts/migration_runner.py --category base

# Luego alteraciones
python scripts/migration_runner.py --category alter

# Finalmente configuración
python scripts/migration_runner.py --category config
```

### Actualización de BD Existente

```bash
# Ver qué falta
python scripts/migration_runner.py --status

# Validar
python scripts/migration_runner.py --dry-run

# Aplicar pendientes
python scripts/migration_runner.py
```

### Agregar Nueva Funcionalidad

```bash
# 1. Crear script SQL en scripts/
# 2. Agregar entrada a migrations_manifest.yaml
# 3. Probar localmente
python scripts/migration_runner.py --dry-run
python scripts/migration_runner.py
```

### Producción (Con Backup)

```bash
# 1. BACKUP PRIMERO
# 2. Dry-run
python scripts/migration_runner.py --dry-run

# 3. Ejecutar
python scripts/migration_runner.py

# 4. Verificar
python scripts/migration_runner.py --status
```

---

## ⚠️ Advertencias

### NO Hacer

- ❌ Ejecutar scripts SQL manualmente sin registro
- ❌ Modificar versiones ya aplicadas en el manifest
- ❌ Editar directamente la tabla `schema_migrations`
- ❌ Saltar dry-run en producción
- ❌ Ejecutar sin backup en producción

### SÍ Hacer

- ✅ Usar siempre el `migration_runner.py`
- ✅ Dry-run antes de aplicar
- ✅ Backup antes de despliegue importante
- ✅ Scripts idempotentes (`IF NOT EXISTS`)
- ✅ Agregar nuevas migraciones al final del manifest
- ✅ Documentar dependencias

---

## 🔧 Configuración

El runner usa la misma configuración de la aplicación (`.env`):

```env
SQL_SERVER_SERVER=tu_servidor
SQL_SERVER_DATABASE=store_control
SQL_SERVER_UID=usuario
SQL_SERVER_PWD=contraseña
```

---

## 📖 Referencias

- **Documentación completa**: [docs/DEPLOY_MIGRATIONS.md](../docs/DEPLOY_MIGRATIONS.md)
- **Estados de pedido**: [docs/ESTADOS_PEDIDO.md](../docs/ESTADOS_PEDIDO.md)
- **Configuración general**: [docs/CONFIGURACION.md](../docs/CONFIGURACION.md)
- **Estructura BD**: [docs/ESTRUCTURA_BD_PEDIDOS.md](../docs/ESTRUCTURA_BD_PEDIDOS.md)

---

## 🆘 Ayuda Rápida

```bash
# Ver todas las opciones
python scripts/migration_runner.py --help

# Estado actual
python scripts/migration_runner.py --status

# Dry-run
python scripts/migration_runner.py --dry-run

# Solo categoría específica
python scripts/migration_runner.py --category base

# Hasta versión específica
python scripts/migration_runner.py --up-to 101

# Logs detallados
python scripts/migration_runner.py --verbose
```

---

## 🎓 Mejores Prácticas

1. **Siempre dry-run primero**
2. **Backup antes de cambios grandes**
3. **Scripts idempotentes** (pueden ejecutarse múltiples veces)
4. **Una migración = un propósito** (no mezclar creación de tabla con datos)
5. **Versionado secuencial** (no saltar números)
6. **Comunicación** (coordinar despliegues en producción)

---

**¿Primera vez?** → Leer [docs/DEPLOY_MIGRATIONS.md](../docs/DEPLOY_MIGRATIONS.md) antes de ejecutar cualquier comando.
