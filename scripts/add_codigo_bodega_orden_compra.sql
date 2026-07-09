-- ============================================================================
-- Script para agregar campo codigo_bodega a orden_compra_cabecera
-- ============================================================================
-- Este script agrega el campo codigo_bodega para almacenar la bodega
-- determinada desde las distribuciones del pedido o desde origen_traslado
-- ============================================================================
-- Ejecuta en la base de datos de la conexión (p. ej. SQL_SERVER_DATABASE).

-- Agregar campo codigo_bodega (código de bodega usada en la ODC: RL-CD, OUT-CD, REG-CD)
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'orden_compra_cabecera' 
    AND COLUMN_NAME = 'codigo_bodega'
)
BEGIN
    ALTER TABLE orden_compra_cabecera
    ADD codigo_bodega NVARCHAR(50) NULL;
    
    PRINT '✅ Campo codigo_bodega agregado a orden_compra_cabecera';
END
ELSE
BEGIN
    PRINT 'ℹ️ Campo codigo_bodega ya existe en orden_compra_cabecera';
END
GO

PRINT '';
PRINT '✅ Script completado exitosamente';
PRINT 'La tabla orden_compra_cabecera ahora tiene el campo codigo_bodega para almacenar la bodega determinada';
