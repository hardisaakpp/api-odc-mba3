-- ============================================================================
-- Script de Migración: Renombrar columna odc a mensaje en tabla pedido
-- ============================================================================
-- Descripción: Renombra la columna 'odc' a 'mensaje' en la tabla pedido
-- Fecha: 2026-02-12
-- ============================================================================

PRINT '🔧 Iniciando migración: Renombrar columna odc → mensaje';
GO

-- ============================================================================
-- Renombrar columna odc a mensaje
-- ============================================================================
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'pedido' AND COLUMN_NAME = 'odc'
)
BEGIN
    PRINT '➕ Renombrando columna odc → mensaje en tabla pedido...';
    EXEC sp_rename 'dbo.pedido.odc', 'mensaje', 'COLUMN';
    PRINT '✅ Columna renombrada exitosamente.';
END
ELSE IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'pedido' AND COLUMN_NAME = 'mensaje'
)
BEGIN
    PRINT '⚠️ La columna ya se llama "mensaje". No se requiere cambio.';
END
ELSE
BEGIN
    PRINT '❌ No se encontró la columna odc ni mensaje en la tabla pedido.';
END
GO

PRINT '✅ Migración completada.';
GO
