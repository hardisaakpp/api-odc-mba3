-- ============================================================================
-- Migración: orden_compra_detalle - total_linea y precio_unitario a 4 decimales
-- ============================================================================
-- Descripción: Cambia total_linea y precio_unitario de 2 a 4 decimales para
--              alinearlos con redistribución, Excel ODC y correo ODC.
-- Fecha: 2026-03-04
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '============================================================================';
PRINT 'Migración: orden_compra_detalle - total_linea y precio_unitario DECIMAL(18,4)';
PRINT '============================================================================';
PRINT '';
GO

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[orden_compra_detalle]') AND type = N'U')
BEGIN
    PRINT '  ⚠️ Tabla orden_compra_detalle no existe. Nada que alterar.';
END
ELSE
BEGIN
    -- total_linea: DECIMAL(18,4) para 4 decimales
    BEGIN TRY
        ALTER TABLE [dbo].[orden_compra_detalle]
        ALTER COLUMN total_linea DECIMAL(18, 4) NULL;
        PRINT '  ✅ orden_compra_detalle.total_linea → DECIMAL(18,4)';
    END TRY
    BEGIN CATCH
        PRINT '  ⚠️ Error al alterar total_linea: ' + ERROR_MESSAGE();
    END CATCH

    -- precio_unitario: DECIMAL(18,4) para consistencia con total_linea
    BEGIN TRY
        ALTER TABLE [dbo].[orden_compra_detalle]
        ALTER COLUMN precio_unitario DECIMAL(18, 4) NULL;
        PRINT '  ✅ orden_compra_detalle.precio_unitario → DECIMAL(18,4)';
    END TRY
    BEGIN CATCH
        PRINT '  ⚠️ Error al alterar precio_unitario: ' + ERROR_MESSAGE();
    END CATCH
END
GO

PRINT '';
PRINT 'Migración finalizada.';
GO
