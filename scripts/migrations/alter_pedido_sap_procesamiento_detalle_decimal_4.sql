-- ============================================================================
-- Migración: pedido_sap_procesamiento_detalle - total_linea_original y total_linea_sap a 4 decimales
-- ============================================================================
-- Descripción: Cambia total_linea_original y total_linea_sap de 2 a 4 decimales
--              para alinearlos con orden_compra_detalle y flujo ODC.
-- Fecha: 2026-03-04
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '============================================================================';
PRINT 'Migración: pedido_sap_procesamiento_detalle - total_linea_* DECIMAL(18,4)';
PRINT '============================================================================';
PRINT '';
GO

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[pedido_sap_procesamiento_detalle]') AND type = N'U')
BEGIN
    PRINT '  ⚠️ Tabla pedido_sap_procesamiento_detalle no existe. Nada que alterar.';
END
ELSE
BEGIN
    -- total_linea_original: DECIMAL(18,4)
    BEGIN TRY
        ALTER TABLE [dbo].[pedido_sap_procesamiento_detalle]
        ALTER COLUMN total_linea_original DECIMAL(18, 4) NULL;
        PRINT '  ✅ pedido_sap_procesamiento_detalle.total_linea_original → DECIMAL(18,4)';
    END TRY
    BEGIN CATCH
        PRINT '  ⚠️ Error al alterar total_linea_original: ' + ERROR_MESSAGE();
    END CATCH

    -- total_linea_sap: DECIMAL(18,4)
    BEGIN TRY
        ALTER TABLE [dbo].[pedido_sap_procesamiento_detalle]
        ALTER COLUMN total_linea_sap DECIMAL(18, 4) NULL;
        PRINT '  ✅ pedido_sap_procesamiento_detalle.total_linea_sap → DECIMAL(18,4)';
    END TRY
    BEGIN CATCH
        PRINT '  ⚠️ Error al alterar total_linea_sap: ' + ERROR_MESSAGE();
    END CATCH
END
GO

PRINT '';
PRINT 'Migración finalizada.';
GO
