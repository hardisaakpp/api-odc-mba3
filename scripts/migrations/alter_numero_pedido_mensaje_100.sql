-- ============================================================================
-- Migración: numero_pedido y mensaje de 50 a 100 caracteres
-- ============================================================================
-- Descripción: Aumenta el tamaño de numero_pedido y mensaje en pedido y tablas
--              relacionadas; también referencia_despacho donde guarda numero_pedido.
-- Fecha: 2026-03-02
-- Idempotente (2026-09-24): cada ALTER solo corre si la columna mide menos de
-- 100 caracteres (max_length en bytes < 200; -1 = MAX). Sin esto, re-ejecutarlo
-- después de alter_pedido_mensaje_nvarchar_500 reduciría pedido.mensaje a 100.
-- ============================================================================

SET NOCOUNT ON;
GO

PRINT '============================================================================';
PRINT 'Migración: numero_pedido / mensaje → NVARCHAR(100)';
PRINT '============================================================================';
GO

-- 1. Tabla pedido
IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'pedido')
BEGIN
    IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido') AND name = 'numero_pedido' AND max_length BETWEEN 0 AND 199)
    BEGIN
        ALTER TABLE [dbo].[pedido] ALTER COLUMN numero_pedido NVARCHAR(100) NOT NULL;
        PRINT '  ✅ pedido.numero_pedido → NVARCHAR(100)';
    END
    IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido') AND name = 'mensaje' AND max_length BETWEEN 0 AND 199)
    BEGIN
        ALTER TABLE [dbo].[pedido] ALTER COLUMN mensaje NVARCHAR(100) NULL;
        PRINT '  ✅ pedido.mensaje → NVARCHAR(100)';
    END
END
ELSE
    PRINT '  ⚠️ Tabla pedido no existe.';
GO

-- 2. Tabla pedido_original
IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'pedido_original')
BEGIN
    IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido_original') AND name = 'numero_pedido' AND max_length BETWEEN 0 AND 199)
    BEGIN
        ALTER TABLE [dbo].[pedido_original] ALTER COLUMN numero_pedido NVARCHAR(100) NOT NULL;
        PRINT '  ✅ pedido_original.numero_pedido → NVARCHAR(100)';
    END
    IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido_original') AND name = 'mensaje' AND max_length BETWEEN 0 AND 199)
    BEGIN
        ALTER TABLE [dbo].[pedido_original] ALTER COLUMN mensaje NVARCHAR(100) NULL;
        PRINT '  ✅ pedido_original.mensaje → NVARCHAR(100)';
    END
END
ELSE
    PRINT '  ⚠️ Tabla pedido_original no existe.';
GO

-- 3. Tabla redistribucion_borrador
IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'redistribucion_borrador')
BEGIN
    IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('redistribucion_borrador') AND name = 'numero_pedido' AND max_length BETWEEN 0 AND 199)
    BEGIN
        ALTER TABLE [dbo].[redistribucion_borrador] ALTER COLUMN numero_pedido NVARCHAR(100) NOT NULL;
        PRINT '  ✅ redistribucion_borrador.numero_pedido → NVARCHAR(100)';
    END
END
ELSE
    PRINT '  ⚠️ Tabla redistribucion_borrador no existe.';
GO

-- 4. Tabla sap_integration_logs (referencia_despacho = numero_pedido)
IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'sap_integration_logs')
BEGIN
    IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('sap_integration_logs') AND name = 'referencia_despacho' AND max_length BETWEEN 0 AND 199)
    BEGIN
        ALTER TABLE [dbo].[sap_integration_logs] ALTER COLUMN referencia_despacho NVARCHAR(100) NULL;
        PRINT '  ✅ sap_integration_logs.referencia_despacho → NVARCHAR(100)';
    END
END
ELSE
    PRINT '  ⚠️ Tabla sap_integration_logs no existe.';
GO

-- 5. Tabla orden_compra_cabecera (referencia_despacho se llena con numero_pedido)
IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'orden_compra_cabecera')
BEGIN
    IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('orden_compra_cabecera') AND name = 'referencia_despacho' AND max_length BETWEEN 0 AND 199)
    BEGIN
        ALTER TABLE [dbo].[orden_compra_cabecera] ALTER COLUMN referencia_despacho NVARCHAR(100) NULL;
        PRINT '  ✅ orden_compra_cabecera.referencia_despacho → NVARCHAR(100)';
    END
END
ELSE
    PRINT '  ⚠️ Tabla orden_compra_cabecera no existe.';
GO

PRINT '';
PRINT '============================================================================';
PRINT '✅ Migración completada.';
PRINT '============================================================================';
GO

SET NOCOUNT OFF;
GO
