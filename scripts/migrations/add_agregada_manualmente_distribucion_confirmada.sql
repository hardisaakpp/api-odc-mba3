-- ============================================================================
-- Migración: Agregar agregada_manualmente a distribucion_confirmada
-- ============================================================================
-- Descripción: Marca qué filas de distribucion_confirmada corresponden a una
--              tienda agregada manualmente en la Vista Excel de Redistribución
--              (pedidos hijo, tiendas fuera del Excel original del pedido padre),
--              en vez de una tienda que ya venía en la distribución original.
--              Permite que el frontend resalte esas columnas de forma permanente
--              (sobrevive recargar la página y confirmar la redistribución), no
--              solo mientras dura la sesión del navegador.
-- Fecha: 2026-09-05
-- ============================================================================

SET NOCOUNT ON;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[distribucion_confirmada]')
    AND name = N'agregada_manualmente'
)
BEGIN
    ALTER TABLE [dbo].[distribucion_confirmada]
    ADD agregada_manualmente BIT NOT NULL DEFAULT 0;
    PRINT '  ✅ Columna agregada_manualmente agregada a distribucion_confirmada.';
END
ELSE
BEGIN
    PRINT '  ✓ La columna agregada_manualmente ya existe en distribucion_confirmada.';
END
GO

PRINT '✅ Migración completada: add_agregada_manualmente_distribucion_confirmada';
