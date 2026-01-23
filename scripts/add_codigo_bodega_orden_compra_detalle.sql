-- ============================================================================
-- Script para agregar campo codigo_bodega a orden_compra_detalle
-- ============================================================================
-- Este script agrega el campo codigo_bodega para almacenar la bodega
-- por línea de detalle, permitiendo que las ITR por bodega sean 100% dinámicas
-- desde la plantilla Excel (RL-CD, OUT-CD, RG-CD)
-- ============================================================================

USE store_control;
GO

-- Agregar campo codigo_bodega (código de bodega por línea: RL-CD, OUT-CD, RG-CD)
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'orden_compra_detalle' 
    AND COLUMN_NAME = 'codigo_bodega'
)
BEGIN
    ALTER TABLE orden_compra_detalle
    ADD codigo_bodega NVARCHAR(50) NULL;
    
    PRINT '✅ Campo codigo_bodega agregado a orden_compra_detalle';
END
ELSE
BEGIN
    PRINT 'ℹ️ Campo codigo_bodega ya existe en orden_compra_detalle';
END
GO

-- Agregar índice para búsquedas por codigo_bodega (útil para agrupar ITR por bodega)
IF NOT EXISTS (
    SELECT * FROM sys.indexes 
    WHERE name = 'idx_orden_compra_detalle_codigo_bodega' 
    AND object_id = OBJECT_ID(N'[dbo].[orden_compra_detalle]')
)
BEGIN
    CREATE INDEX idx_orden_compra_detalle_codigo_bodega 
    ON orden_compra_detalle(codigo_bodega);
    
    PRINT '✅ Índice idx_orden_compra_detalle_codigo_bodega creado.';
END
ELSE
BEGIN
    PRINT 'ℹ️ El índice idx_orden_compra_detalle_codigo_bodega ya existe.';
END
GO

PRINT '';
PRINT '✅ Script completado exitosamente';
PRINT 'La tabla orden_compra_detalle ahora tiene el campo codigo_bodega para almacenar la bodega por línea';
PRINT 'Esto permite que las ITR por bodega sean 100% dinámicas desde la plantilla Excel';
