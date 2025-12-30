-- ============================================================================
-- Script SQL para actualizar el tamaño de la columna codigo en la tabla tienda
-- ============================================================================
-- PROBLEMA: La columna codigo está definida como NVARCHAR(20), pero los nombres
-- de tiendas pueden exceder ese límite (ej: "PASEO SHOPPING PORTOVIEJO" = 25 caracteres)
-- 
-- SOLUCIÓN: Aumentar el tamaño a NVARCHAR(100) para permitir nombres más largos
-- ============================================================================

USE [store_control]
GO

-- Verificar que la tabla existe antes de hacer cambios
IF EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[tienda]') AND type in (N'U'))
BEGIN
    -- Verificar el tamaño actual de la columna
    DECLARE @CurrentSize INT;
    SELECT @CurrentSize = CHARACTER_MAXIMUM_LENGTH 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = 'dbo' 
      AND TABLE_NAME = 'tienda' 
      AND COLUMN_NAME = 'codigo';
    
    PRINT 'Tamaño actual de la columna codigo: ' + CAST(@CurrentSize AS VARCHAR(10));
    
    -- Si el tamaño actual es menor a 100, actualizarlo
    IF @CurrentSize < 100
    BEGIN
        PRINT 'Actualizando columna codigo de NVARCHAR(' + CAST(@CurrentSize AS VARCHAR(10)) + ') a NVARCHAR(100)...';
        
        -- Actualizar el tamaño de la columna
        ALTER TABLE [dbo].[tienda] 
        ALTER COLUMN codigo NVARCHAR(100) NOT NULL;
        
        PRINT '✅ Columna codigo actualizada exitosamente a NVARCHAR(100).';
    END
    ELSE
    BEGIN
        PRINT 'ℹ️ La columna codigo ya tiene un tamaño igual o mayor a 100 caracteres. No se requiere actualización.';
    END
END
ELSE
BEGIN
    PRINT '❌ ERROR: La tabla tienda no existe. Ejecuta primero create_pedido_tables.sql';
END
GO

-- Verificar el nuevo tamaño
SELECT 
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo' 
  AND TABLE_NAME = 'tienda' 
  AND COLUMN_NAME = 'codigo';
GO

PRINT '';
PRINT '============================================================================';
PRINT 'Script completado. La columna codigo ahora acepta hasta 100 caracteres.';
PRINT '============================================================================';
GO


