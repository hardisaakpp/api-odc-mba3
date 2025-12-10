-- ============================================================================
-- Script SQL para agregar columna grupo_articulos a producto_sap_cache
-- ============================================================================
-- Este script agrega la columna grupo_articulos para almacenar el nombre
-- del grupo de artículos (ItmsGrpNam) obtenido de SAP
-- ============================================================================

-- Verificar si la columna ya existe antes de agregarla
IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[producto_sap_cache]') 
    AND name = 'grupo_articulos'
)
BEGIN
    ALTER TABLE [dbo].[producto_sap_cache]
    ADD grupo_articulos VARCHAR(100) NULL;
    
    -- Crear índice para búsquedas rápidas por grupo
    CREATE INDEX idx_producto_sap_cache_grupo_articulos ON producto_sap_cache(grupo_articulos);
    
    PRINT 'Columna grupo_articulos agregada exitosamente a producto_sap_cache';
END
ELSE
BEGIN
    PRINT 'Columna grupo_articulos ya existe en producto_sap_cache';
END
GO

PRINT 'Script completado exitosamente';
GO

