-- ============================================================================
-- Script de Migración: Completar campos de auditoría en todas las tablas
-- ============================================================================
-- Descripción: Agrega campos de auditoría faltantes para cumplir con las
--              buenas prácticas de desarrollo (Sección 3)
-- Fecha: 2026-02-06
-- Referencia: Guía de Buenas Prácticas - Sección 3 (Campos de auditoría)
-- ============================================================================
-- 
-- ESTRATEGIA DE BAJO RIESGO:
--   1. NO se renombran campos existentes (created_at se mantiene)
--   2. Se agregan campos NUEVOS como NULL (no afecta datos existentes)
--   3. Se usa IF NOT EXISTS para idempotencia
--
-- CAMPOS A AGREGAR:
--   - modificado_por: Usuario que realizó la última modificación
--   - modificado_fecha: Fecha/hora de la última modificación
--   - origen: Origen del registro ('API', 'WEB', 'EXCEL', 'CELERY', 'MANUAL')
--   - ip_origen: Dirección IP del cliente
--
-- NOTA: Se omite id_equipo ya que no hay requerimiento claro de cómo capturarlo
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '============================================================================';
PRINT '🔧 Migración: Completar campos de auditoría (Buenas Prácticas Sección 3)';
PRINT '============================================================================';
PRINT '';
PRINT 'Estrategia: Agregar campos faltantes sin modificar campos existentes';
PRINT '';
GO

-- ============================================================================
-- TABLA: pedido - Agregar modificado_por, modificado_fecha
-- ============================================================================
PRINT '📋 Tabla: pedido';

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido') AND name = 'modificado_por')
BEGIN
    PRINT '  ➕ Agregando columna modificado_por...';
    ALTER TABLE pedido ADD modificado_por NVARCHAR(450) NULL;
    PRINT '  ✅ Columna modificado_por agregada.';
END
ELSE
BEGIN
    PRINT '  ✓ Columna modificado_por ya existe.';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido') AND name = 'modificado_fecha')
BEGIN
    PRINT '  ➕ Agregando columna modificado_fecha...';
    ALTER TABLE pedido ADD modificado_fecha DATETIME2 NULL;
    PRINT '  ✅ Columna modificado_fecha agregada.';
END
ELSE
BEGIN
    PRINT '  ✓ Columna modificado_fecha ya existe.';
END
GO

-- ============================================================================
-- TABLA: pedido_detalle - Agregar creado_por, origen, ip_origen
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: pedido_detalle';

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido_detalle') AND name = 'creado_por')
BEGIN
    PRINT '  ➕ Agregando columna creado_por...';
    ALTER TABLE pedido_detalle ADD creado_por NVARCHAR(450) NULL;
    PRINT '  ✅ Columna creado_por agregada.';
END
ELSE
BEGIN
    PRINT '  ✓ Columna creado_por ya existe.';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido_detalle') AND name = 'origen')
BEGIN
    PRINT '  ➕ Agregando columna origen...';
    ALTER TABLE pedido_detalle ADD origen NVARCHAR(50) NULL;
    PRINT '  ✅ Columna origen agregada.';
END
ELSE
BEGIN
    PRINT '  ✓ Columna origen ya existe.';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido_detalle') AND name = 'ip_origen')
BEGIN
    PRINT '  ➕ Agregando columna ip_origen...';
    ALTER TABLE pedido_detalle ADD ip_origen NVARCHAR(45) NULL;
    PRINT '  ✅ Columna ip_origen agregada.';
END
ELSE
BEGIN
    PRINT '  ✓ Columna ip_origen ya existe.';
END
GO

-- ============================================================================
-- TABLA: pedido_detalle_tienda - Agregar campos de auditoría
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: pedido_detalle_tienda';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('pedido_detalle_tienda') AND type = 'U')
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido_detalle_tienda') AND name = 'creado_por')
    BEGIN
        PRINT '  ➕ Agregando columna creado_por...';
        ALTER TABLE pedido_detalle_tienda ADD creado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna creado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido_detalle_tienda') AND name = 'modificado_por')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_por...';
        ALTER TABLE pedido_detalle_tienda ADD modificado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna modificado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido_detalle_tienda') AND name = 'modificado_fecha')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_fecha...';
        ALTER TABLE pedido_detalle_tienda ADD modificado_fecha DATETIME2 NULL;
        PRINT '  ✅ Columna modificado_fecha agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido_detalle_tienda') AND name = 'origen')
    BEGIN
        PRINT '  ➕ Agregando columna origen...';
        ALTER TABLE pedido_detalle_tienda ADD origen NVARCHAR(50) NULL;
        PRINT '  ✅ Columna origen agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido_detalle_tienda') AND name = 'ip_origen')
    BEGIN
        PRINT '  ➕ Agregando columna ip_origen...';
        ALTER TABLE pedido_detalle_tienda ADD ip_origen NVARCHAR(45) NULL;
        PRINT '  ✅ Columna ip_origen agregada.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla pedido_detalle_tienda no existe.';
END
GO

-- ============================================================================
-- TABLA: tienda - Agregar campos de auditoría
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: tienda';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('tienda') AND type = 'U')
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('tienda') AND name = 'creado_por')
    BEGIN
        PRINT '  ➕ Agregando columna creado_por...';
        ALTER TABLE tienda ADD creado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna creado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('tienda') AND name = 'modificado_por')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_por...';
        ALTER TABLE tienda ADD modificado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna modificado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('tienda') AND name = 'modificado_fecha')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_fecha...';
        ALTER TABLE tienda ADD modificado_fecha DATETIME2 NULL;
        PRINT '  ✅ Columna modificado_fecha agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('tienda') AND name = 'origen')
    BEGIN
        PRINT '  ➕ Agregando columna origen...';
        ALTER TABLE tienda ADD origen NVARCHAR(50) NULL;
        PRINT '  ✅ Columna origen agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('tienda') AND name = 'ip_origen')
    BEGIN
        PRINT '  ➕ Agregando columna ip_origen...';
        ALTER TABLE tienda ADD ip_origen NVARCHAR(45) NULL;
        PRINT '  ✅ Columna ip_origen agregada.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla tienda no existe.';
END
GO

-- ============================================================================
-- TABLA: orden_compra_cabecera - Agregar modificado_por, modificado_fecha
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: orden_compra_cabecera';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('orden_compra_cabecera') AND type = 'U')
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('orden_compra_cabecera') AND name = 'creado_por')
    BEGIN
        PRINT '  ➕ Agregando columna creado_por...';
        ALTER TABLE orden_compra_cabecera ADD creado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna creado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('orden_compra_cabecera') AND name = 'modificado_por')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_por...';
        ALTER TABLE orden_compra_cabecera ADD modificado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna modificado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('orden_compra_cabecera') AND name = 'modificado_fecha')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_fecha...';
        ALTER TABLE orden_compra_cabecera ADD modificado_fecha DATETIME2 NULL;
        PRINT '  ✅ Columna modificado_fecha agregada.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla orden_compra_cabecera no existe.';
END
GO

-- ============================================================================
-- TABLA: orden_compra_detalle - Agregar campos de auditoría
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: orden_compra_detalle';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('orden_compra_detalle') AND type = 'U')
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('orden_compra_detalle') AND name = 'creado_por')
    BEGIN
        PRINT '  ➕ Agregando columna creado_por...';
        ALTER TABLE orden_compra_detalle ADD creado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna creado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('orden_compra_detalle') AND name = 'modificado_por')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_por...';
        ALTER TABLE orden_compra_detalle ADD modificado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna modificado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('orden_compra_detalle') AND name = 'modificado_fecha')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_fecha...';
        ALTER TABLE orden_compra_detalle ADD modificado_fecha DATETIME2 NULL;
        PRINT '  ✅ Columna modificado_fecha agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('orden_compra_detalle') AND name = 'origen')
    BEGIN
        PRINT '  ➕ Agregando columna origen...';
        ALTER TABLE orden_compra_detalle ADD origen NVARCHAR(50) NULL;
        PRINT '  ✅ Columna origen agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('orden_compra_detalle') AND name = 'ip_origen')
    BEGIN
        PRINT '  ➕ Agregando columna ip_origen...';
        ALTER TABLE orden_compra_detalle ADD ip_origen NVARCHAR(45) NULL;
        PRINT '  ✅ Columna ip_origen agregada.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla orden_compra_detalle no existe.';
END
GO

-- ============================================================================
-- TABLA: despacho_cabecera - Agregar campos de auditoría
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: despacho_cabecera';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('despacho_cabecera') AND type = 'U')
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('despacho_cabecera') AND name = 'creado_por')
    BEGIN
        PRINT '  ➕ Agregando columna creado_por...';
        ALTER TABLE despacho_cabecera ADD creado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna creado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('despacho_cabecera') AND name = 'modificado_por')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_por...';
        ALTER TABLE despacho_cabecera ADD modificado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna modificado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('despacho_cabecera') AND name = 'modificado_fecha')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_fecha...';
        ALTER TABLE despacho_cabecera ADD modificado_fecha DATETIME2 NULL;
        PRINT '  ✅ Columna modificado_fecha agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('despacho_cabecera') AND name = 'origen')
    BEGIN
        PRINT '  ➕ Agregando columna origen...';
        ALTER TABLE despacho_cabecera ADD origen NVARCHAR(50) NULL;
        PRINT '  ✅ Columna origen agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('despacho_cabecera') AND name = 'ip_origen')
    BEGIN
        PRINT '  ➕ Agregando columna ip_origen...';
        ALTER TABLE despacho_cabecera ADD ip_origen NVARCHAR(45) NULL;
        PRINT '  ✅ Columna ip_origen agregada.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla despacho_cabecera no existe.';
END
GO

-- ============================================================================
-- TABLA: despacho_detalle - Agregar campos de auditoría
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: despacho_detalle';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('despacho_detalle') AND type = 'U')
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('despacho_detalle') AND name = 'creado_por')
    BEGIN
        PRINT '  ➕ Agregando columna creado_por...';
        ALTER TABLE despacho_detalle ADD creado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna creado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('despacho_detalle') AND name = 'modificado_por')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_por...';
        ALTER TABLE despacho_detalle ADD modificado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna modificado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('despacho_detalle') AND name = 'modificado_fecha')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_fecha...';
        ALTER TABLE despacho_detalle ADD modificado_fecha DATETIME2 NULL;
        PRINT '  ✅ Columna modificado_fecha agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('despacho_detalle') AND name = 'origen')
    BEGIN
        PRINT '  ➕ Agregando columna origen...';
        ALTER TABLE despacho_detalle ADD origen NVARCHAR(50) NULL;
        PRINT '  ✅ Columna origen agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('despacho_detalle') AND name = 'ip_origen')
    BEGIN
        PRINT '  ➕ Agregando columna ip_origen...';
        ALTER TABLE despacho_detalle ADD ip_origen NVARCHAR(45) NULL;
        PRINT '  ✅ Columna ip_origen agregada.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla despacho_detalle no existe.';
END
GO

-- ============================================================================
-- TABLA: sku_homologacion - Agregar campos faltantes
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: sku_homologacion';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('sku_homologacion') AND type = 'U')
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('sku_homologacion') AND name = 'creado_por')
    BEGIN
        PRINT '  ➕ Agregando columna creado_por...';
        ALTER TABLE sku_homologacion ADD creado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna creado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('sku_homologacion') AND name = 'origen')
    BEGIN
        PRINT '  ➕ Agregando columna origen...';
        ALTER TABLE sku_homologacion ADD origen NVARCHAR(50) NULL;
        PRINT '  ✅ Columna origen agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('sku_homologacion') AND name = 'ip_origen')
    BEGIN
        PRINT '  ➕ Agregando columna ip_origen...';
        ALTER TABLE sku_homologacion ADD ip_origen NVARCHAR(45) NULL;
        PRINT '  ✅ Columna ip_origen agregada.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla sku_homologacion no existe.';
END
GO

-- ============================================================================
-- TABLA: remision_cabecera - Agregar campos faltantes
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: remision_cabecera';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('remision_cabecera') AND type = 'U')
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('remision_cabecera') AND name = 'creado_por')
    BEGIN
        PRINT '  ➕ Agregando columna creado_por...';
        ALTER TABLE remision_cabecera ADD creado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna creado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('remision_cabecera') AND name = 'modificado_por')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_por...';
        ALTER TABLE remision_cabecera ADD modificado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna modificado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('remision_cabecera') AND name = 'modificado_fecha')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_fecha...';
        ALTER TABLE remision_cabecera ADD modificado_fecha DATETIME2 NULL;
        PRINT '  ✅ Columna modificado_fecha agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('remision_cabecera') AND name = 'origen')
    BEGIN
        PRINT '  ➕ Agregando columna origen...';
        ALTER TABLE remision_cabecera ADD origen NVARCHAR(50) NULL;
        PRINT '  ✅ Columna origen agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('remision_cabecera') AND name = 'ip_origen')
    BEGIN
        PRINT '  ➕ Agregando columna ip_origen...';
        ALTER TABLE remision_cabecera ADD ip_origen NVARCHAR(45) NULL;
        PRINT '  ✅ Columna ip_origen agregada.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla remision_cabecera no existe.';
END
GO

-- ============================================================================
-- TABLA: archivo_plantilla - Agregar campos faltantes
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: archivo_plantilla';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('archivo_plantilla') AND type = 'U')
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('archivo_plantilla') AND name = 'modificado_por')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_por...';
        ALTER TABLE archivo_plantilla ADD modificado_por NVARCHAR(450) NULL;
        PRINT '  ✅ Columna modificado_por agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('archivo_plantilla') AND name = 'modificado_fecha')
    BEGIN
        PRINT '  ➕ Agregando columna modificado_fecha...';
        ALTER TABLE archivo_plantilla ADD modificado_fecha DATETIME2 NULL;
        PRINT '  ✅ Columna modificado_fecha agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('archivo_plantilla') AND name = 'origen')
    BEGIN
        PRINT '  ➕ Agregando columna origen...';
        ALTER TABLE archivo_plantilla ADD origen NVARCHAR(50) NULL;
        PRINT '  ✅ Columna origen agregada.';
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('archivo_plantilla') AND name = 'ip_origen')
    BEGIN
        PRINT '  ➕ Agregando columna ip_origen...';
        ALTER TABLE archivo_plantilla ADD ip_origen NVARCHAR(45) NULL;
        PRINT '  ✅ Columna ip_origen agregada.';
    END
END
ELSE
BEGIN
    PRINT '  ⚠️ Tabla archivo_plantilla no existe.';
END
GO

-- ============================================================================
-- TABLA: distribucion_confirmada - Agregar origen faltante
-- ============================================================================
PRINT '';
PRINT '📋 Tabla: distribucion_confirmada';

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID('distribucion_confirmada') AND type = 'U')
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('distribucion_confirmada') AND name = 'origen')
    BEGIN
        PRINT '  ➕ Agregando columna origen...';
        ALTER TABLE distribucion_confirmada ADD origen NVARCHAR(50) NULL;
        PRINT '  ✅ Columna origen agregada.';
    END
    ELSE
    BEGIN
        PRINT '  ✓ Columna origen ya existe.';
    END
END
GO

-- ============================================================================
-- Resumen
-- ============================================================================
PRINT '';
PRINT '============================================================================';
PRINT '✅ Migración completada: Campos de auditoría agregados';
PRINT '============================================================================';
PRINT '';
PRINT '📊 Tablas actualizadas:';
PRINT '  - pedido: modificado_por, modificado_fecha';
PRINT '  - pedido_detalle: creado_por, origen, ip_origen';
PRINT '  - pedido_detalle_tienda: creado_por, modificado_por, modificado_fecha, origen, ip_origen';
PRINT '  - tienda: creado_por, modificado_por, modificado_fecha, origen, ip_origen';
PRINT '  - orden_compra_cabecera: creado_por, modificado_por, modificado_fecha';
PRINT '  - orden_compra_detalle: creado_por, modificado_por, modificado_fecha, origen, ip_origen';
PRINT '  - despacho_cabecera: creado_por, modificado_por, modificado_fecha, origen, ip_origen';
PRINT '  - despacho_detalle: creado_por, modificado_por, modificado_fecha, origen, ip_origen';
PRINT '  - sku_homologacion: creado_por, origen, ip_origen';
PRINT '  - remision_cabecera: creado_por, modificado_por, modificado_fecha, origen, ip_origen';
PRINT '  - archivo_plantilla: modificado_por, modificado_fecha, origen, ip_origen';
PRINT '  - distribucion_confirmada: origen';
PRINT '';
PRINT '📌 NOTA: Los campos son NULL para no afectar registros existentes.';
PRINT '         El backend debe poblarlos en nuevas operaciones.';
GO

SET NOCOUNT OFF;
GO
