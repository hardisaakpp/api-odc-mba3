-- ============================================================================
-- Script de Migración: Agregar columna unidad_sap a sku_homologacion
-- ============================================================================
-- Este script agrega la columna unidad_sap si no existe
-- Es seguro ejecutarlo múltiples veces (idempotente)
-- ============================================================================

PRINT '============================================================================';
PRINT 'Migrando tabla sku_homologacion - Agregando columna unidad_sap';
PRINT '============================================================================';
PRINT ' ';

-- Verificar si la columna ya existe
IF NOT EXISTS (
    SELECT * 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'sku_homologacion' 
    AND COLUMN_NAME = 'unidad_sap'
)
BEGIN
    PRINT '➕ Agregando columna unidad_sap...';
    
    ALTER TABLE sku_homologacion
    ADD unidad_sap VARCHAR(20) NULL;
    
    PRINT '✅ Columna unidad_sap agregada exitosamente';
END
ELSE
BEGIN
    PRINT '✓ La columna unidad_sap ya existe';
END

PRINT ' ';
PRINT '============================================================================';
PRINT 'Verificación de estructura de tabla';
PRINT '============================================================================';

-- Mostrar todas las columnas de la tabla
SELECT 
    COLUMN_NAME AS [Columna],
    DATA_TYPE AS [Tipo],
    CHARACTER_MAXIMUM_LENGTH AS [Longitud],
    IS_NULLABLE AS [Nullable]
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'sku_homologacion'
ORDER BY ORDINAL_POSITION;

PRINT ' ';
PRINT '============================================================================';
PRINT 'Migración completada';
PRINT '============================================================================';

GO






