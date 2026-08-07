-- Script para agregar columna codigo_barras a producto_sap_cache
-- Este campo almacena el código de barras (CodeBars) de SAP, vinculado al ItemCode.
-- SAP es la fuente de verdad para este campo: se toma siempre que se consulta el
-- producto por ItemCode y reemplaza la referencia que traiga el Excel.

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[producto_sap_cache]')
    AND name = 'codigo_barras'
)
BEGIN
    ALTER TABLE producto_sap_cache
    ADD codigo_barras VARCHAR(50) NULL;

    PRINT 'Columna codigo_barras agregada exitosamente a producto_sap_cache';
END
ELSE
BEGIN
    PRINT 'La columna codigo_barras ya existe en producto_sap_cache';
END
GO
