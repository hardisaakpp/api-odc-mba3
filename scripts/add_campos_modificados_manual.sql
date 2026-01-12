-- ============================================================================
-- Script de migración: Agregar campos para marcar columnas modificadas manualmente
-- ============================================================================
-- Descripción: Agrega campos booleanos para rastrear qué columnas del
--              pedido_detalle fueron modificadas manualmente por el usuario
--              (costo_doc_sin_iva, total, comentario)
-- Fecha: 2026-01-09
-- ============================================================================

USE [MBA3_Consultas]
GO

-- Agregar campo costo_modificado_manual si no existe
IF NOT EXISTS (
    SELECT * 
    FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') 
    AND name = 'costo_modificado_manual'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle]
    ADD costo_modificado_manual BIT DEFAULT 0 NOT NULL;
    
    PRINT '✅ Columna "costo_modificado_manual" agregada exitosamente a la tabla pedido_detalle.';
END
ELSE
BEGIN
    PRINT '⚠️ La columna "costo_modificado_manual" ya existe en la tabla pedido_detalle.';
END
GO

-- Agregar campo total_modificado_manual si no existe
IF NOT EXISTS (
    SELECT * 
    FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') 
    AND name = 'total_modificado_manual'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle]
    ADD total_modificado_manual BIT DEFAULT 0 NOT NULL;
    
    PRINT '✅ Columna "total_modificado_manual" agregada exitosamente a la tabla pedido_detalle.';
END
ELSE
BEGIN
    PRINT '⚠️ La columna "total_modificado_manual" ya existe en la tabla pedido_detalle.';
END
GO

-- Agregar campo comentario_modificado_manual si no existe
IF NOT EXISTS (
    SELECT * 
    FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') 
    AND name = 'comentario_modificado_manual'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle]
    ADD comentario_modificado_manual BIT DEFAULT 0 NOT NULL;
    
    PRINT '✅ Columna "comentario_modificado_manual" agregada exitosamente a la tabla pedido_detalle.';
END
ELSE
BEGIN
    PRINT '⚠️ La columna "comentario_modificado_manual" ya existe en la tabla pedido_detalle.';
END
GO

-- Crear índices para mejorar rendimiento en búsquedas de campos modificados
IF NOT EXISTS (
    SELECT * 
    FROM sys.indexes 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') 
    AND name = 'idx_pedido_detalle_costo_modificado'
)
BEGIN
    CREATE INDEX idx_pedido_detalle_costo_modificado 
    ON pedido_detalle(costo_modificado_manual)
    WHERE costo_modificado_manual = 1; -- Índice filtrado (solo valores true)
    
    PRINT '✅ Índice "idx_pedido_detalle_costo_modificado" creado exitosamente.';
END
ELSE
BEGIN
    PRINT '⚠️ El índice "idx_pedido_detalle_costo_modificado" ya existe.';
END
GO

IF NOT EXISTS (
    SELECT * 
    FROM sys.indexes 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') 
    AND name = 'idx_pedido_detalle_total_modificado'
)
BEGIN
    CREATE INDEX idx_pedido_detalle_total_modificado 
    ON pedido_detalle(total_modificado_manual)
    WHERE total_modificado_manual = 1; -- Índice filtrado (solo valores true)
    
    PRINT '✅ Índice "idx_pedido_detalle_total_modificado" creado exitosamente.';
END
ELSE
BEGIN
    PRINT '⚠️ El índice "idx_pedido_detalle_total_modificado" ya existe.';
END
GO

IF NOT EXISTS (
    SELECT * 
    FROM sys.indexes 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') 
    AND name = 'idx_pedido_detalle_comentario_modificado'
)
BEGIN
    CREATE INDEX idx_pedido_detalle_comentario_modificado 
    ON pedido_detalle(comentario_modificado_manual)
    WHERE comentario_modificado_manual = 1; -- Índice filtrado (solo valores true)
    
    PRINT '✅ Índice "idx_pedido_detalle_comentario_modificado" creado exitosamente.';
END
ELSE
BEGIN
    PRINT '⚠️ El índice "idx_pedido_detalle_comentario_modificado" ya existe.';
END
GO

-- Verificar que las columnas se agregaron correctamente
SELECT 
    c.name AS column_name,
    t.name AS data_type,
    c.max_length,
    c.is_nullable,
    CASE WHEN dc.definition IS NOT NULL THEN dc.definition ELSE 'Sin default' END AS default_value
FROM sys.columns c
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
LEFT JOIN sys.default_constraints dc ON c.default_object_id = dc.object_id
WHERE c.object_id = OBJECT_ID(N'[dbo].[pedido_detalle]')
AND c.name IN ('costo_modificado_manual', 'total_modificado_manual', 'comentario_modificado_manual')
ORDER BY c.name;
GO

PRINT '✅ Migración de campos de modificación manual completada.';
GO
