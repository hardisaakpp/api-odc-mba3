-- ============================================================================
-- Migración: pedido.mensaje y pedido_original.mensaje → NVARCHAR(500)
-- ============================================================================
-- Ejecutar en scnexus_test (o la BD del proyecto) si aún tienes NVARCHAR(50/100).
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT 'Migración: pedido / pedido_original .mensaje → NVARCHAR(500)';
GO

IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'pedido')
   AND EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido') AND name = 'mensaje')
BEGIN
    ALTER TABLE [dbo].[pedido] ALTER COLUMN mensaje NVARCHAR(500) NULL;
    PRINT '  ✅ pedido.mensaje → NVARCHAR(500)';
END
GO

IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'pedido_original')
   AND EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido_original') AND name = 'mensaje')
BEGIN
    ALTER TABLE [dbo].[pedido_original] ALTER COLUMN mensaje NVARCHAR(500) NULL;
    PRINT '  ✅ pedido_original.mensaje → NVARCHAR(500)';
END
GO

SET NOCOUNT OFF;
GO
