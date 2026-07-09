-- ============================================================================
-- Script para agregar columna BODEGA a pedido_detalle
-- ============================================================================
-- Descripción: Agrega la columna bodega (INT) para almacenar el código de 
--              bodega/almacén del producto en pedido_detalle
-- Fecha: 2026-01-08
-- ============================================================================

-- Verificar si la columna ya existe antes de agregarla
IF NOT EXISTS (
    SELECT * 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'pedido_detalle' 
    AND COLUMN_NAME = 'bodega'
)
BEGIN
    ALTER TABLE pedido_detalle 
    ADD bodega INT NULL;
    
    PRINT '✅ Columna bodega agregada exitosamente a pedido_detalle.';
END
ELSE
BEGIN
    PRINT '⚠️ La columna bodega ya existe en pedido_detalle.';
END
GO

-- Verificar que la columna se agregó correctamente
IF EXISTS (
    SELECT * 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'pedido_detalle' 
    AND COLUMN_NAME = 'bodega'
)
BEGIN
    PRINT '✅ Verificación exitosa: columna bodega existe en pedido_detalle.';
END
ELSE
BEGIN
    PRINT '❌ Error: la columna bodega no se agregó correctamente.';
END
GO
