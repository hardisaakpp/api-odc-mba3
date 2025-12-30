-- ============================================================================
-- Script SQL para agregar campo 'estado' a tabla pedido (FASE 2)
-- ============================================================================
-- Agrega campo estado para manejar estados del pedido como:
-- - PENDIENTE_CONFIRMACION_PROVEEDOR (estado inicial)
-- - CONFIRMADO_PROVEEDOR
-- - RECHAZADO_PROVEEDOR
-- - EN_PROCESO
-- - COMPLETADO
-- ============================================================================

-- Verificar si la columna ya existe antes de agregarla
IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido]') 
    AND name = 'estado'
)
BEGIN
    ALTER TABLE [dbo].[pedido]
    ADD estado NVARCHAR(50) NOT NULL DEFAULT 'PENDIENTE_CONFIRMACION_PROVEEDOR';
    
    -- Crear índice para búsquedas rápidas por estado
    CREATE INDEX idx_pedido_estado ON pedido(estado);
    
    PRINT 'Campo estado agregado exitosamente a tabla pedido.';
END
ELSE
BEGIN
    PRINT 'El campo estado ya existe en la tabla pedido.';
END
GO

