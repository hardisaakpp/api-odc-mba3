-- ============================================================================
-- Migración: Agregar costo_unitario a pedido_detalle y pedido_detalle_original
-- ============================================================================
-- Descripción: Reemplazo del insumo de costo para el Margen de Rentabilidad
--              (req. 1.4/1.5, SIS-PYTD-0002). costo_unitario = costo_doc_sin_iva /
--              unidad_conversion (tabla pack_conversion, por el pack ya resuelto
--              SAP/Excel). Reemplaza a costo_margen (columna "Costo" del Excel,
--              manual y desconectada) como insumo del margen; costo_margen se deja
--              intacta, sin usarse para el cálculo. No actualiza SAP ni afecta las
--              órdenes de compra.
-- Fecha: 2026-08-11
-- ============================================================================

SET NOCOUNT ON;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]')
    AND name = N'costo_unitario'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle]
    ADD costo_unitario DECIMAL(18,4) NULL;
    PRINT '  ✅ Columna costo_unitario agregada a pedido_detalle.';
END
ELSE
BEGIN
    PRINT '  ✓ La columna costo_unitario ya existe en pedido_detalle.';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle_original]')
    AND name = N'costo_unitario'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle_original]
    ADD costo_unitario DECIMAL(18,4) NULL;
    PRINT '  ✅ Columna costo_unitario agregada a pedido_detalle_original.';
END
ELSE
BEGIN
    PRINT '  ✓ La columna costo_unitario ya existe en pedido_detalle_original.';
END
GO

PRINT '✅ Migración completada: add_costo_unitario_pedido_detalle';
