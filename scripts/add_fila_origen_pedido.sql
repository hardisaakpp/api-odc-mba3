-- ============================================================================
-- Script para agregar campo fila_origen a pedido_detalle_tienda
-- ============================================================================
-- Este campo permite rastrear de qué fila del Excel vino cada registro
-- Útil para auditoría y debugging
-- ============================================================================

-- Agregar columna fila_origen a pedido_detalle_tienda
IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle_tienda]') 
    AND name = 'fila_origen'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle_tienda]
    ADD fila_origen INT NULL;
    
    PRINT 'Columna fila_origen agregada a pedido_detalle_tienda.';
END
ELSE
BEGIN
    PRINT 'La columna fila_origen ya existe en pedido_detalle_tienda.';
END
GO

-- Agregar índice para búsquedas por fila_origen (opcional, útil para debugging)
IF NOT EXISTS (
    SELECT * FROM sys.indexes 
    WHERE name = 'idx_pedido_detalle_tienda_fila_origen' 
    AND object_id = OBJECT_ID(N'[dbo].[pedido_detalle_tienda]')
)
BEGIN
    CREATE INDEX idx_pedido_detalle_tienda_fila_origen 
    ON pedido_detalle_tienda(fila_origen);
    
    PRINT 'Índice idx_pedido_detalle_tienda_fila_origen creado.';
END
ELSE
BEGIN
    PRINT 'El índice idx_pedido_detalle_tienda_fila_origen ya existe.';
END
GO

