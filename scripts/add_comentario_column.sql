-- ============================================================================
-- Script de migración: Agregar columna 'comentario' a pedido_detalle
-- ============================================================================
-- Descripción: Agrega un campo de comentario opcional a la tabla pedido_detalle
--              para permitir notas adicionales por producto.
-- Fecha: 2026-01-09
-- ============================================================================

-- Verificar si la columna ya existe antes de agregarla
IF NOT EXISTS (
    SELECT * 
    FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') 
    AND name = 'comentario'
)
BEGIN
    -- Agregar columna comentario
    ALTER TABLE [dbo].[pedido_detalle]
    ADD comentario NVARCHAR(2000) NULL;
    
    PRINT '✅ Columna "comentario" agregada exitosamente a la tabla pedido_detalle.';
END
ELSE
BEGIN
    PRINT '⚠️ La columna "comentario" ya existe en la tabla pedido_detalle.';
END
GO

-- Verificar que la columna se agregó correctamente
IF EXISTS (
    SELECT * 
    FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') 
    AND name = 'comentario'
)
BEGIN
    PRINT '✅ Verificación: La columna "comentario" existe en pedido_detalle.';
    
    -- Mostrar información de la columna
    SELECT 
        c.name AS column_name,
        t.name AS data_type,
        c.max_length,
        c.is_nullable
    FROM sys.columns c
    INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
    WHERE c.object_id = OBJECT_ID(N'[dbo].[pedido_detalle]')
    AND c.name = 'comentario';
END
ELSE
BEGIN
    PRINT '❌ Error: La columna "comentario" no se pudo agregar.';
END
GO
