-- ============================================================================
-- Script de Migración: Agregar campos de auditoría origen e ip_origen
-- ============================================================================
-- Descripción: Agrega campos opcionales para rastrear el origen de las operaciones
-- Fecha: 2026-02-06
-- Referencia: Guía de Buenas Prácticas - Sección 3 (Campos de auditoría)
-- ============================================================================
-- 
-- CAMPOS AGREGADOS:
--   - origen: Indica el origen del registro ('API', 'WEB', 'EXCEL', 'CELERY', 'MANUAL')
--   - ip_origen: Dirección IP del cliente que realizó la operación
--
-- NOTA: Los campos son NULL para no afectar registros existentes.
--       Los endpoints nuevos pueden poblarlos opcionalmente.
-- ============================================================================

SET NOCOUNT ON;
GO

USE [MBA3_Consultas]
GO

PRINT '🔧 Iniciando migración: Agregar campos de auditoría (origen, ip_origen)';
PRINT '============================================================================';
GO

-- ============================================================================
-- TABLA: pedido - Campos de auditoría
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: pedido';

-- Campo: origen
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido') AND name = 'origen')
BEGIN
    PRINT '  ➕ Agregando columna origen...';
    ALTER TABLE pedido ADD origen NVARCHAR(50) NULL;
    PRINT '  ✅ Columna origen agregada.';
END
ELSE
BEGIN
    PRINT '  ✓ Columna origen ya existe.';
END
GO

-- Campo: ip_origen
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido') AND name = 'ip_origen')
BEGIN
    PRINT '  ➕ Agregando columna ip_origen...';
    ALTER TABLE pedido ADD ip_origen NVARCHAR(45) NULL;  -- 45 chars para soportar IPv6
    PRINT '  ✅ Columna ip_origen agregada.';
END
ELSE
BEGIN
    PRINT '  ✓ Columna ip_origen ya existe.';
END
GO

-- ============================================================================
-- TABLA: pedido_detalle - Campos de auditoría
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: pedido_detalle';

-- Campo: modificado_por (para rastrear quién editó el detalle)
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido_detalle') AND name = 'modificado_por')
BEGIN
    PRINT '  ➕ Agregando columna modificado_por...';
    ALTER TABLE pedido_detalle ADD modificado_por NVARCHAR(450) NULL;
    PRINT '  ✅ Columna modificado_por agregada.';
END
ELSE
BEGIN
    PRINT '  ✓ Columna modificado_por ya existe.';
END
GO

-- Campo: modificado_fecha
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido_detalle') AND name = 'modificado_fecha')
BEGIN
    PRINT '  ➕ Agregando columna modificado_fecha...';
    ALTER TABLE pedido_detalle ADD modificado_fecha DATETIME NULL;
    PRINT '  ✅ Columna modificado_fecha agregada.';
END
ELSE
BEGIN
    PRINT '  ✓ Columna modificado_fecha ya existe.';
END
GO

-- ============================================================================
-- TABLA: orden_compra_cabecera - Campos de auditoría
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: orden_compra_cabecera';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('orden_compra_cabecera') AND type = 'U')
BEGIN
    -- Campo: origen
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('orden_compra_cabecera') AND name = 'origen')
    BEGIN
        PRINT '  ➕ Agregando columna origen...';
        ALTER TABLE orden_compra_cabecera ADD origen NVARCHAR(50) NULL;
        PRINT '  ✅ Columna origen agregada.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Columna origen ya existe.';
    END
    
    -- Campo: ip_origen
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('orden_compra_cabecera') AND name = 'ip_origen')
    BEGIN
        PRINT '  ➕ Agregando columna ip_origen...';
        ALTER TABLE orden_compra_cabecera ADD ip_origen NVARCHAR(45) NULL;
        PRINT '  ✅ Columna ip_origen agregada.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Columna ip_origen ya existe.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla orden_compra_cabecera no existe, omitiendo campos.';
END
GO

-- ============================================================================
-- TABLA: distribucion_confirmada - Campos de auditoría
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: distribucion_confirmada';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('distribucion_confirmada') AND type = 'U')
BEGIN
    -- Campo: confirmado_por
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('distribucion_confirmada') AND name = 'confirmado_por')
    BEGIN
        PRINT '  ➕ Agregando columna confirmado_por...';
        ALTER TABLE distribucion_confirmada ADD confirmado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna confirmado_por agregada.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Columna confirmado_por ya existe.';
    END
    
    -- Campo: ip_origen
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('distribucion_confirmada') AND name = 'ip_origen')
    BEGIN
        PRINT '  ➕ Agregando columna ip_origen...';
        ALTER TABLE distribucion_confirmada ADD ip_origen NVARCHAR(45) NULL;
        PRINT '  ✅ Columna ip_origen agregada.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Columna ip_origen ya existe.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla distribucion_confirmada no existe, omitiendo campos.';
END
GO

-- ============================================================================
-- Crear índice en origen para filtros por tipo de operación
-- ============================================================================
PRINT '';
PRINT '📋 Creando índices en campos origen...';

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido') AND name = 'origen')
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_pedido_origen' AND object_id = OBJECT_ID('pedido'))
    BEGIN
        PRINT '  ➕ Creando índice idx_pedido_origen...';
        CREATE INDEX idx_pedido_origen ON pedido(origen);
        PRINT '  ✅ Índice idx_pedido_origen creado.';
    END
END
GO

-- ============================================================================
-- Actualizar registros existentes con valor por defecto (opcional)
-- ============================================================================
PRINT '';
PRINT '📋 Actualizando registros existentes...';

-- Marcar registros existentes como origen='LEGACY' para distinguirlos
UPDATE pedido 
SET origen = 'LEGACY' 
WHERE origen IS NULL;

PRINT '  ✅ Registros de pedido actualizados con origen=LEGACY';
GO

-- ============================================================================
-- Resumen
-- ============================================================================
PRINT '';
PRINT '============================================================================';
PRINT '✅ Migración completada: Campos de auditoría agregados';
PRINT '============================================================================';
PRINT '';
PRINT '📊 Campos agregados:';
PRINT '  - pedido: origen, ip_origen';
PRINT '  - pedido_detalle: modificado_por, modificado_fecha';
PRINT '  - orden_compra_cabecera: origen, ip_origen';
PRINT '  - distribucion_confirmada: confirmado_por, ip_origen';
PRINT '';
PRINT '📌 Valores de origen válidos:';
PRINT '  - LEGACY: Registros existentes antes de esta migración';
PRINT '  - API: Creado desde endpoint API';
PRINT '  - WEB: Creado desde interfaz web';
PRINT '  - EXCEL: Importado desde archivo Excel';
PRINT '  - CELERY: Creado por tarea automática';
PRINT '  - MANUAL: Creado manualmente (SQL directo)';
GO

SET NOCOUNT OFF;
GO
