-- ============================================================================
-- Script de migración: Agregar campos de auditoría a pedido_detalle
-- ============================================================================
-- Descripción: Agrega campos para rastrear quién y cuándo se modificaron
--              los registros de pedido_detalle (costo, total, comentario, etc.)
-- Fecha: 2026-01-09
-- ============================================================================

USE [MBA3_Consultas]
GO

-- Agregar campo updated_at si no existe
IF NOT EXISTS (
    SELECT * 
    FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') 
    AND name = 'updated_at'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle]
    ADD updated_at DATETIME NULL;
    
    PRINT '✅ Columna "updated_at" agregada exitosamente a la tabla pedido_detalle.';
END
ELSE
BEGIN
    PRINT '⚠️ La columna "updated_at" ya existe en la tabla pedido_detalle.';
END
GO

-- Agregar campo modificado_por si no existe
IF NOT EXISTS (
    SELECT * 
    FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') 
    AND name = 'modificado_por'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle]
    ADD modificado_por NVARCHAR(450) NULL;
    
    PRINT '✅ Columna "modificado_por" agregada exitosamente a la tabla pedido_detalle.';
END
ELSE
BEGIN
    PRINT '⚠️ La columna "modificado_por" ya existe en la tabla pedido_detalle.';
END
GO

-- Crear índice para búsquedas por fecha de modificación
IF NOT EXISTS (
    SELECT * 
    FROM sys.indexes 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') 
    AND name = 'idx_pedido_detalle_updated_at'
)
BEGIN
    CREATE INDEX idx_pedido_detalle_updated_at 
    ON pedido_detalle(updated_at);
    
    PRINT '✅ Índice "idx_pedido_detalle_updated_at" creado exitosamente.';
END
ELSE
BEGIN
    PRINT '⚠️ El índice "idx_pedido_detalle_updated_at" ya existe.';
END
GO

-- Crear índice para búsquedas por usuario que modificó
IF NOT EXISTS (
    SELECT * 
    FROM sys.indexes 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') 
    AND name = 'idx_pedido_detalle_modificado_por'
)
BEGIN
    CREATE INDEX idx_pedido_detalle_modificado_por 
    ON pedido_detalle(modificado_por);
    
    PRINT '✅ Índice "idx_pedido_detalle_modificado_por" creado exitosamente.';
END
ELSE
BEGIN
    PRINT '⚠️ El índice "idx_pedido_detalle_modificado_por" ya existe.';
END
GO

-- Verificar que las columnas se agregaron correctamente
SELECT 
    c.name AS column_name,
    t.name AS data_type,
    c.max_length,
    c.is_nullable
FROM sys.columns c
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
WHERE c.object_id = OBJECT_ID(N'[dbo].[pedido_detalle]')
AND c.name IN ('updated_at', 'modificado_por')
ORDER BY c.name;
GO

PRINT '✅ Migración de campos de auditoría completada.';
GO
