-- ============================================================================
-- Migración: Agregar orden_linea a pedido_detalle
-- ============================================================================
-- Descripción: Conserva el orden de las líneas tal como vienen en la plantilla
--              Excel, para que las interfaces (pedidos, cargar-plantilla) y
--              el Excel "Descargar Pedido Original" muestren el mismo orden.
-- Depende de: create_pedido_tables (004)
-- Fecha: 2026-03-04
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '============================================================================';
PRINT 'Migración: Agregar orden_linea a pedido_detalle';
PRINT '============================================================================';
PRINT '';
GO

-- ============================================================================
-- Agregar columna orden_linea (orden de línea en la plantilla)
-- ============================================================================
-- Batch 1: agregar columna (y GO) para que el siguiente batch compile con la columna ya existente
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]')
    AND name = N'orden_linea'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle]
    ADD orden_linea INT NOT NULL DEFAULT 0;
    PRINT '  ✅ Columna orden_linea agregada a pedido_detalle.';
END
ELSE
BEGIN
    PRINT '  ✓ La columna orden_linea ya existe en pedido_detalle.';
END
GO

-- Batch 2: backfill orden_linea (en batch separado para que SQL Server compile el UPDATE con la columna ya existente)
;WITH numerado AS (
    SELECT pedido_detalle_id,
           ROW_NUMBER() OVER (PARTITION BY pedido_id ORDER BY created_at) - 1 AS rn
    FROM [dbo].[pedido_detalle]
)
UPDATE pd
SET pd.orden_linea = n.rn
FROM [dbo].[pedido_detalle] pd
INNER JOIN numerado n ON pd.pedido_detalle_id = n.pedido_detalle_id
WHERE pd.orden_linea = 0;
PRINT '  Filas existentes actualizadas con orden_linea según created_at (donde orden_linea=0).';
GO

PRINT '';
PRINT '============================================================================';
PRINT '✅ Migración completada: add_orden_linea_pedido_detalle';
PRINT '============================================================================';
