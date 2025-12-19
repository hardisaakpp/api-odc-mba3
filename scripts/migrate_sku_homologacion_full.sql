-- ============================================================================
-- Script de Migración Completa: sku_homologacion
-- ============================================================================
-- Este script asegura que la tabla sku_homologacion tenga todas las columnas
-- necesarias para el sistema de homologaciones SKU.
-- Es seguro ejecutarlo múltiples veces (idempotente)
-- ============================================================================

PRINT '============================================================================';
PRINT 'MIGRACIÓN COMPLETA: sku_homologacion';
PRINT '============================================================================';
PRINT ' ';

-- ============================================================================
-- 1. Verificar si la tabla existe
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[sku_homologacion]') AND type in (N'U'))
BEGIN
    PRINT '❌ ERROR: La tabla sku_homologacion no existe';
    PRINT '   Por favor, ejecute primero: scripts/create_sku_homologacion_table.sql';
    PRINT ' ';
END
ELSE
BEGIN
    PRINT '✅ Tabla sku_homologacion existe';
    PRINT ' ';
    
    -- ========================================================================
    -- 2. Agregar columnas faltantes de datos SAP
    -- ========================================================================
    PRINT '📋 Verificando columnas de datos SAP...';
    
    -- Columna: unidad_sap
    IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'sku_homologacion' AND COLUMN_NAME = 'unidad_sap')
    BEGIN
        PRINT '  ➕ Agregando columna: unidad_sap';
        ALTER TABLE sku_homologacion ADD unidad_sap VARCHAR(20) NULL;
    END
    ELSE
        PRINT '  ✓ unidad_sap ya existe';
    
    -- Columna: subtotal_sap
    IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'sku_homologacion' AND COLUMN_NAME = 'subtotal_sap')
    BEGIN
        PRINT '  ➕ Agregando columna: subtotal_sap';
        ALTER TABLE sku_homologacion ADD subtotal_sap DECIMAL(18, 2) NULL;
    END
    ELSE
        PRINT '  ✓ subtotal_sap ya existe';
    
    PRINT ' ';
    
    -- ========================================================================
    -- 3. Verificar columnas de estado y flags
    -- ========================================================================
    PRINT '📋 Verificando columnas de estado y flags...';
    
    -- Columna: tiene_diferencias
    IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'sku_homologacion' AND COLUMN_NAME = 'tiene_diferencias')
    BEGIN
        PRINT '  ➕ Agregando columna: tiene_diferencias';
        ALTER TABLE sku_homologacion ADD tiene_diferencias BIT NOT NULL DEFAULT 0;
    END
    ELSE
        PRINT '  ✓ tiene_diferencias ya existe';
    
    -- Columna: tiene_datos_sap
    IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'sku_homologacion' AND COLUMN_NAME = 'tiene_datos_sap')
    BEGIN
        PRINT '  ➕ Agregando columna: tiene_datos_sap';
        ALTER TABLE sku_homologacion ADD tiene_datos_sap BIT NOT NULL DEFAULT 0;
    END
    ELSE
        PRINT '  ✓ tiene_datos_sap ya existe';
    
    PRINT ' ';
    
    -- ========================================================================
    -- 4. Verificar columnas de metadata
    -- ========================================================================
    PRINT '📋 Verificando columnas de metadata...';
    
    -- Columna: ultima_modificacion
    IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'sku_homologacion' AND COLUMN_NAME = 'ultima_modificacion')
    BEGIN
        PRINT '  ➕ Agregando columna: ultima_modificacion';
        ALTER TABLE sku_homologacion ADD ultima_modificacion DATETIME NULL;
    END
    ELSE
        PRINT '  ✓ ultima_modificacion ya existe';
    
    -- Columna: modificado_por
    IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'sku_homologacion' AND COLUMN_NAME = 'modificado_por')
    BEGIN
        PRINT '  ➕ Agregando columna: modificado_por';
        ALTER TABLE sku_homologacion ADD modificado_por VARCHAR(100) NULL;
    END
    ELSE
        PRINT '  ✓ modificado_por ya existe';
    
    PRINT ' ';
    
    -- ========================================================================
    -- 5. Verificar constraint de estado
    -- ========================================================================
    PRINT '📋 Verificando constraint de estado...';
    
    IF NOT EXISTS (
        SELECT * FROM sys.check_constraints 
        WHERE name = 'CK_sku_homologacion_estado' 
        AND parent_object_id = OBJECT_ID('sku_homologacion')
    )
    BEGIN
        PRINT '  ➕ Agregando constraint: CK_sku_homologacion_estado';
        ALTER TABLE sku_homologacion
        ADD CONSTRAINT CK_sku_homologacion_estado 
        CHECK (estado IN ('PENDIENTE', 'HOMOLOGADO', 'ERROR'));
    END
    ELSE
        PRINT '  ✓ Constraint de estado ya existe';
    
    PRINT ' ';
    
    -- ========================================================================
    -- 6. Crear índices faltantes
    -- ========================================================================
    PRINT '📋 Verificando índices...';
    
    -- Índice: unidad_sap (nuevo, si no existe)
    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_sku_homologacion_unidad_sap' AND object_id = OBJECT_ID('sku_homologacion'))
    BEGIN
        PRINT '  ➕ Creando índice: idx_sku_homologacion_unidad_sap';
        CREATE INDEX idx_sku_homologacion_unidad_sap ON sku_homologacion(unidad_sap);
    END
    ELSE
        PRINT '  ✓ Índice unidad_sap ya existe';
    
    PRINT ' ';
    
    -- ========================================================================
    -- 7. Mostrar estructura final
    -- ========================================================================
    PRINT '============================================================================';
    PRINT 'ESTRUCTURA FINAL DE LA TABLA';
    PRINT '============================================================================';
    
    SELECT 
        ORDINAL_POSITION AS [#],
        COLUMN_NAME AS [Columna],
        DATA_TYPE AS [Tipo],
        CASE 
            WHEN CHARACTER_MAXIMUM_LENGTH IS NOT NULL 
            THEN CAST(CHARACTER_MAXIMUM_LENGTH AS VARCHAR)
            WHEN NUMERIC_PRECISION IS NOT NULL 
            THEN CAST(NUMERIC_PRECISION AS VARCHAR) + ',' + CAST(NUMERIC_SCALE AS VARCHAR)
            ELSE '-'
        END AS [Longitud],
        IS_NULLABLE AS [Nullable],
        COLUMN_DEFAULT AS [Default]
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'sku_homologacion'
    ORDER BY ORDINAL_POSITION;
    
    PRINT ' ';
    PRINT '============================================================================';
    PRINT '✅ MIGRACIÓN COMPLETADA EXITOSAMENTE';
    PRINT '============================================================================';
    PRINT ' ';
    PRINT 'Siguiente paso: Reiniciar el backend y probar el endpoint /api/homologaciones-sku/sincronizar';
    PRINT ' ';
END

GO




