-- Script para agregar columna pvp_sap a producto_sap_cache
-- Este campo cachea el PVP de SAP: "Price" en ITM1 para PriceList = 1
-- (lista de precios "Precio Minorista", confirmada como fuente de PVP para RN-02).
-- SAP es la fuente de verdad: se valida obligatoriamente contra el PVP del Excel.

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[producto_sap_cache]')
    AND name = 'pvp_sap'
)
BEGIN
    ALTER TABLE producto_sap_cache
    ADD pvp_sap DECIMAL(19, 6) NULL;

    PRINT 'Columna pvp_sap agregada exitosamente a producto_sap_cache';
END
ELSE
BEGIN
    PRINT 'La columna pvp_sap ya existe en producto_sap_cache';
END
GO
