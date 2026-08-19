-- Script para agregar columna marca_sap a producto_sap_cache
-- Este campo cachea la Marca de SAP: OITM.U_MARCA
-- SAP es la fuente de verdad; reemplaza a la marca derivada por bodega en el detalle de pedido.

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[producto_sap_cache]')
    AND name = 'marca_sap'
)
BEGIN
    ALTER TABLE producto_sap_cache
    ADD marca_sap NVARCHAR(50) NULL;

    PRINT 'Columna marca_sap agregada exitosamente a producto_sap_cache';
END
ELSE
BEGIN
    PRINT 'La columna marca_sap ya existe en producto_sap_cache';
END
GO
