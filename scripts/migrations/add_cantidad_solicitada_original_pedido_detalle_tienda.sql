-- ============================================================================
-- Migración: Agregar cantidad_solicitada_original a pedido_detalle_tienda
-- ============================================================================
-- Descripción: Req. 1.2 (Gestión de pedidos parciales). Complemento de
--              add_cantidad_solicitada_original_pedido_detalle.sql a nivel de
--              tienda: protege a futuro la cantidad original por tienda de la
--              misma sobreescritura que sufre "total" en pedido_detalle,
--              cuando "cantidad" en pedido_detalle_tienda se ajuste por
--              redistribución/confirmación de proveedor. No es consumida por
--              la detección de diferencia de req. 1.2 (que opera a nivel
--              agregado de pedido_detalle) — es preparación para cálculos por
--              tienda a futuro.
--              Filas existentes quedan en NULL: no se puede reconstruir el
--              original de una fila ya ajustada antes de esta migración.
-- Fecha: 2026-08-17
-- ============================================================================

PRINT '🔧 Iniciando migración: agregar cantidad_solicitada_original a pedido_detalle_tienda';
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'pedido_detalle_tienda'
      AND COLUMN_NAME = 'cantidad_solicitada_original'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle_tienda]
        ADD cantidad_solicitada_original DECIMAL(18,4) NULL;
    PRINT '✅ Columna cantidad_solicitada_original agregada a pedido_detalle_tienda';
END
ELSE
    PRINT '⏭️ Columna cantidad_solicitada_original ya existe en pedido_detalle_tienda';
GO
