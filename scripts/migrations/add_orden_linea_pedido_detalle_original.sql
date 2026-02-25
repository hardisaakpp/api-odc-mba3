-- ============================================================================
-- Migración: Agregar orden_linea a pedido_detalle_original
-- ============================================================================
-- Descripción: Permite conservar el orden original de las líneas del pedido
--              tal como vienen en la plantilla Excel, para que "Descargar
--              Pedido Original" genere el Excel con el mismo orden.
-- Depende de: create_pedido_original_tables (605)
-- Fecha: 2026-02-25
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '============================================================================';
PRINT 'Migración: Agregar orden_linea a pedido_detalle_original';
PRINT '============================================================================';
PRINT '';
GO

-- ============================================================================
-- Agregar columna orden_linea (orden de línea en la plantilla original)
-- ============================================================================
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle_original]')
    AND name = N'orden_linea'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle_original]
    ADD orden_linea INT NOT NULL DEFAULT 0;

    PRINT '  ✅ Columna orden_linea agregada a pedido_detalle_original.';
    PRINT '     (Filas existentes tienen orden_linea = 0; nuevos snapshots guardarán el orden.)';
END
ELSE
BEGIN
    PRINT '  ✓ La columna orden_linea ya existe en pedido_detalle_original.';
END
GO

PRINT '';
PRINT '============================================================================';
PRINT '✅ Migración completada: add_orden_linea_pedido_detalle_original';
PRINT '============================================================================';
