-- ============================================================================
-- Migración: Agregar costo_margen a pedido_detalle y pedido_detalle_original
-- ============================================================================
-- Descripción: Req. 1.4/1.5 (SIS-PYTD-0002) — nueva columna "Costo" en la
--              plantilla Excel de carga de pedidos, distinta de costo_doc_sin_iva
--              (que es el costo/precio negociado con El Rayo y ya alimenta OC,
--              ajustes y exportación TXT MBA3). costo_margen es únicamente
--              informativo para calcular el Margen de Rentabilidad
--              (1 - (costo_margen / (pvp / 1.15))); no actualiza SAP ni afecta
--              las órdenes de compra (RN-05).
-- Fecha: 2026-08-06
-- ============================================================================

SET NOCOUNT ON;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]')
    AND name = N'costo_margen'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle]
    ADD costo_margen DECIMAL(18,4) NULL;
    PRINT '  ✅ Columna costo_margen agregada a pedido_detalle.';
END
ELSE
BEGIN
    PRINT '  ✓ La columna costo_margen ya existe en pedido_detalle.';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle_original]')
    AND name = N'costo_margen'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle_original]
    ADD costo_margen DECIMAL(18,4) NULL;
    PRINT '  ✅ Columna costo_margen agregada a pedido_detalle_original.';
END
ELSE
BEGIN
    PRINT '  ✓ La columna costo_margen ya existe en pedido_detalle_original.';
END
GO

PRINT '✅ Migración completada: add_costo_margen_pedido_detalle';
