# Guía de Buenas Prácticas SQL - mba3-consultas

Esta guía define los estándares para el desarrollo de scripts SQL y migraciones en el proyecto.

## Tabla de Contenidos

1. [Template para Nuevas Tablas](#template-para-nuevas-tablas)
2. [Convenciones de Nomenclatura](#convenciones-de-nomenclatura)
3. [Campos de Auditoría Obligatorios](#campos-de-auditoría-obligatorios)
4. [Índices Recomendados](#índices-recomendados)
5. [Template para Migraciones](#template-para-migraciones)
6. [Ejemplo Completo](#ejemplo-completo)

---

## Template para Nuevas Tablas

```sql
-- ============================================================================
-- Script: Crear tabla [nombre_tabla] (descripción breve)
-- ============================================================================
-- Descripción: [Descripción detallada de la tabla y su propósito]
-- Fecha: YYYY-MM-DD
-- Autor: [Nombre]
-- Referencia: [Ticket/Issue relacionado]
-- ============================================================================

SET NOCOUNT ON;
GO

USE [MBA3_Consultas]
GO

-- ============================================================================
-- Tabla: [nombre_tabla] (descripción)
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[nombre_tabla]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[nombre_tabla] (
        -- PK: UUID recomendado para tablas con relaciones externas
        id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        -- Campos de negocio
        codigo NVARCHAR(50) NOT NULL,
        nombre NVARCHAR(150) NULL,
        descripcion NVARCHAR(500) NULL,
        estado NVARCHAR(50) DEFAULT 'ACTIVO',
        
        -- Campos numéricos (usar precisión apropiada)
        cantidad INT NOT NULL DEFAULT 0,
        monto DECIMAL(18, 4) NULL,
        porcentaje DECIMAL(5, 2) NULL,
        
        -- ===== CAMPOS DE AUDITORÍA (OBLIGATORIOS) =====
        creado_por NVARCHAR(450) NULL,        -- User ID del JWT
        creado_fecha DATETIME DEFAULT GETDATE(),
        modificado_por NVARCHAR(450) NULL,
        modificado_fecha DATETIME NULL,
        activo BIT DEFAULT 1,                  -- Soft delete
        
        -- Campos de trazabilidad (recomendados)
        origen NVARCHAR(50) NULL,              -- 'API', 'WEB', 'EXCEL', 'CELERY'
        ip_origen NVARCHAR(45) NULL,           -- Soporta IPv6
        
        -- ===== CONSTRAINTS =====
        CONSTRAINT UQ_nombre_tabla_codigo UNIQUE (codigo)
    );
    
    -- ===== ÍNDICES (crear en campos de filtros frecuentes) =====
    CREATE INDEX idx_nombre_tabla_codigo ON nombre_tabla(codigo);
    CREATE INDEX idx_nombre_tabla_estado ON nombre_tabla(estado);
    CREATE INDEX idx_nombre_tabla_creado_fecha ON nombre_tabla(creado_fecha DESC);
    CREATE INDEX idx_nombre_tabla_activo ON nombre_tabla(activo);
    
    PRINT 'Tabla nombre_tabla creada exitosamente.';
END
ELSE
BEGIN
    PRINT 'La tabla nombre_tabla ya existe.';
END
GO

SET NOCOUNT OFF;
GO
```

---

## Convenciones de Nomenclatura

### Tablas
| Regla | Ejemplo Correcto | Ejemplo Incorrecto |
|-------|------------------|-------------------|
| snake_case | `pedido_detalle` | `PedidoDetalle` |
| Plural (recomendado) | `pedidos` | `pedido` |
| Prefijo según módulo | `sap_integration_logs` | `logs` |

### Columnas
| Regla | Ejemplo Correcto | Ejemplo Incorrecto |
|-------|------------------|-------------------|
| snake_case | `fecha_pedido` | `FechaPedido` |
| Singular | `id_usuario` | `ids_usuarios` |
| Prefijo para FKs | `pedido_id` | `fk_pedido` |

### Índices
```
idx_[tabla]_[columna]           -- Índice simple
idx_[tabla]_[col1]_[col2]       -- Índice compuesto
uq_[tabla]_[columna]            -- Unique constraint
```

### Foreign Keys
```
FK_[tabla_origen]_[tabla_referencia]
```

---

## Campos de Auditoría Obligatorios

Todas las tablas deben incluir estos campos:

```sql
-- Campos mínimos obligatorios
creado_por NVARCHAR(450) NULL,        -- ID del usuario que creó el registro
creado_fecha DATETIME DEFAULT GETDATE(),
activo BIT DEFAULT 1,                  -- Para soft delete

-- Campos recomendados
modificado_por NVARCHAR(450) NULL,
modificado_fecha DATETIME NULL,
origen NVARCHAR(50) NULL,              -- Fuente: 'API', 'WEB', 'EXCEL', 'CELERY'
ip_origen NVARCHAR(45) NULL,
```

### Valores válidos para `origen`:
- `API` - Creado desde endpoint REST
- `WEB` - Creado desde interfaz web
- `EXCEL` - Importado desde archivo Excel
- `CELERY` - Creado por tarea automática
- `MANUAL` - Creado manualmente (SQL directo)
- `LEGACY` - Registros anteriores a la implementación

---

## Índices Recomendados

### Siempre crear índices en:
1. **Campos de búsqueda frecuente**: `codigo`, `numero_pedido`
2. **Campos de filtros**: `estado`, `activo`, `fecha`
3. **Foreign Keys**: `pedido_id`, `tienda_id`
4. **Campos de ordenamiento**: `creado_fecha DESC`

### Ejemplo:
```sql
-- Índices básicos
CREATE INDEX idx_tabla_codigo ON tabla(codigo);
CREATE INDEX idx_tabla_estado ON tabla(estado);
CREATE INDEX idx_tabla_activo ON tabla(activo);

-- Índice compuesto para consultas frecuentes
CREATE INDEX idx_tabla_estado_fecha ON tabla(estado, creado_fecha DESC);

-- Índice en FK
CREATE INDEX idx_tabla_pedido_id ON tabla(pedido_id);
```

---

## Template para Migraciones

```sql
-- ============================================================================
-- Script de Migración: [Descripción breve]
-- ============================================================================
-- Descripción: [Descripción detallada del cambio]
-- Fecha: YYYY-MM-DD
-- Autor: [Nombre]
-- Referencia: [Ticket/Issue]
-- ============================================================================
-- 
-- CAMBIOS:
--   - [Cambio 1]
--   - [Cambio 2]
--
-- ROLLBACK (si es necesario):
--   ALTER TABLE tabla DROP COLUMN columna;
-- ============================================================================

SET NOCOUNT ON;
GO

USE [MBA3_Consultas]
GO

PRINT '🔧 Iniciando migración: [Descripción]';
PRINT '============================================================================';
GO

-- ============================================================================
-- Agregar columna si no existe
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('tabla') AND name = 'nueva_columna')
BEGIN
    PRINT '  ➕ Agregando columna nueva_columna...';
    ALTER TABLE tabla ADD nueva_columna NVARCHAR(50) NULL;
    PRINT '  ✅ Columna nueva_columna agregada.';
END
ELSE
BEGIN
    PRINT '  ✓ Columna nueva_columna ya existe.';
END
GO

-- ============================================================================
-- Crear índice si no existe
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_tabla_columna' AND object_id = OBJECT_ID('tabla'))
BEGIN
    PRINT '  ➕ Creando índice idx_tabla_columna...';
    CREATE INDEX idx_tabla_columna ON tabla(columna);
    PRINT '  ✅ Índice idx_tabla_columna creado.';
END
GO

-- ============================================================================
-- Resumen
-- ============================================================================
PRINT '';
PRINT '============================================================================';
PRINT '✅ Migración completada: [Descripción]';
PRINT '============================================================================';
GO

SET NOCOUNT OFF;
GO
```

---

## Ejemplo Completo

### Nueva tabla `notificacion_email`

```sql
-- ============================================================================
-- Script: Crear tabla notificaciones_email (registro de emails enviados)
-- ============================================================================
-- Descripción: Almacena historial de notificaciones por email enviadas
-- Fecha: 2026-02-06
-- Autor: Sistema
-- Referencia: Buenas Prácticas - Sección 5 (Logs obligatorios)
-- ============================================================================

SET NOCOUNT ON;
GO

USE [MBA3_Consultas]
GO

IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[notificaciones_email]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[notificaciones_email] (
        -- PK
        notificacion_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        -- Datos del email
        tipo_notificacion NVARCHAR(50) NOT NULL,   -- 'PEDIDO_NUEVO', 'CONFIRMACION', etc.
        destinatario NVARCHAR(255) NOT NULL,
        asunto NVARCHAR(500) NOT NULL,
        cuerpo NVARCHAR(MAX) NULL,
        
        -- Estado del envío
        estado NVARCHAR(50) DEFAULT 'PENDIENTE',   -- 'PENDIENTE', 'ENVIADO', 'ERROR'
        fecha_envio DATETIME NULL,
        error_mensaje NVARCHAR(1000) NULL,
        intentos INT DEFAULT 0,
        
        -- Relaciones (opcionales)
        pedido_id UNIQUEIDENTIFIER NULL,
        oc_id UNIQUEIDENTIFIER NULL,
        
        -- ===== CAMPOS DE AUDITORÍA =====
        creado_por NVARCHAR(450) NULL,
        creado_fecha DATETIME DEFAULT GETDATE(),
        modificado_por NVARCHAR(450) NULL,
        modificado_fecha DATETIME NULL,
        activo BIT DEFAULT 1,
        origen NVARCHAR(50) NULL,
        ip_origen NVARCHAR(45) NULL,
        
        -- FKs opcionales (sin constraint para flexibilidad)
        -- CONSTRAINT FK_notificacion_pedido FOREIGN KEY (pedido_id) REFERENCES pedido(pedido_id)
    );
    
    -- Índices
    CREATE INDEX idx_notificaciones_tipo ON notificaciones_email(tipo_notificacion);
    CREATE INDEX idx_notificaciones_estado ON notificaciones_email(estado);
    CREATE INDEX idx_notificaciones_fecha ON notificaciones_email(creado_fecha DESC);
    CREATE INDEX idx_notificaciones_pedido ON notificaciones_email(pedido_id);
    CREATE INDEX idx_notificaciones_destinatario ON notificaciones_email(destinatario);
    
    PRINT 'Tabla notificaciones_email creada exitosamente.';
END
GO

SET NOCOUNT OFF;
GO
```

---

## Checklist para Nuevas Tablas

- [ ] Nombre en snake_case
- [ ] PK definida (UUID o INT según caso)
- [ ] Campos de auditoría incluidos
- [ ] Índices en campos de filtro
- [ ] Comentario de cabecera con descripción y fecha
- [ ] Validación IF NOT EXISTS
- [ ] SET NOCOUNT ON al inicio
- [ ] Mensajes PRINT informativos

---

## Referencias

- **Guía de Buenas Prácticas Backend** - Documento interno
- **Microsoft SQL Server Best Practices** - [docs.microsoft.com](https://docs.microsoft.com)
