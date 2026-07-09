-- ============================================================================
-- Script SQL para agregar columna precio_unitario_sap a despacho_detalle
-- ============================================================================
-- Esta columna almacena el precio unitario convertido para Mabel (por pack)
-- ============================================================================

-- Verificar si la columna ya existe
IF NOT EXISTS (
    SELECT * 
    FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[despacho_detalle]') 
    AND name = 'precio_unitario_sap'
)
BEGIN
    ALTER TABLE despacho_detalle
    ADD precio_unitario_sap DECIMAL(18, 4) NULL;
    
    PRINT 'Columna precio_unitario_sap agregada exitosamente a despacho_detalle';
END
ELSE
BEGIN
    PRINT 'Columna precio_unitario_sap ya existe en despacho_detalle';
END
GO

PRINT 'Script completado';
GO

