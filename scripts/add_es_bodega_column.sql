-- ============================================================================
-- Script para agregar campo es_bodega a pedido_detalle_tienda
-- ============================================================================
-- Este campo permite distinguir si un registro es una bodega central
-- (RL-CD, OUT-CD, REG-CD) o una tienda normal
-- Útil para la interfaz de Redistribución de Productos - MABEL TRADING
-- Fecha: 2026-01-15
-- ============================================================================

-- Agregar columna es_bodega a pedido_detalle_tienda
IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle_tienda]') 
    AND name = 'es_bodega'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle_tienda]
    ADD es_bodega BIT NOT NULL DEFAULT 0;  -- 0 = tienda, 1 = bodega
    
    PRINT '✅ Columna es_bodega agregada a pedido_detalle_tienda.';
END
ELSE
BEGIN
    PRINT '⚠️ La columna es_bodega ya existe en pedido_detalle_tienda.';
END
GO

-- Agregar índice para búsquedas por es_bodega (útil para filtrar bodegas vs tiendas)
IF NOT EXISTS (
    SELECT * FROM sys.indexes 
    WHERE name = 'idx_pedido_detalle_tienda_es_bodega' 
    AND object_id = OBJECT_ID(N'[dbo].[pedido_detalle_tienda]')
)
BEGIN
    CREATE INDEX idx_pedido_detalle_tienda_es_bodega 
    ON pedido_detalle_tienda(es_bodega);
    
    PRINT '✅ Índice idx_pedido_detalle_tienda_es_bodega creado.';
END
ELSE
BEGIN
    PRINT '⚠️ El índice idx_pedido_detalle_tienda_es_bodega ya existe.';
END
GO

-- Verificar que la columna se agregó correctamente
IF EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle_tienda]') 
    AND name = 'es_bodega'
)
BEGIN
    PRINT '✅ Verificación exitosa: columna es_bodega existe en pedido_detalle_tienda.';
END
ELSE
BEGIN
    PRINT '❌ Error: la columna es_bodega no se agregó correctamente.';
END
GO
