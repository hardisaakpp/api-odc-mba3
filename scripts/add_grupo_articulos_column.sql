-- Script para agregar columna grupo_articulos a producto_sap_cache
-- Este campo almacena el nombre del grupo de artículos (ItmsGrpNam) de SAP

IF NOT EXISTS (
    SELECT * FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[producto_sap_cache]') 
    AND name = 'grupo_articulos'
)
BEGIN
    ALTER TABLE producto_sap_cache
    ADD grupo_articulos VARCHAR(100) NULL;
    
    PRINT 'Columna grupo_articulos agregada exitosamente a producto_sap_cache';
END
ELSE
BEGIN
    PRINT 'La columna grupo_articulos ya existe en producto_sap_cache';
END
GO


