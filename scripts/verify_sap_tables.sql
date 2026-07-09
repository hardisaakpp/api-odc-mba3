-- ============================================================================
-- Script de verificación de tablas SAP
-- ============================================================================
-- Este script verifica si las tablas necesarias existen en la base de datos
-- ============================================================================

PRINT 'Verificando tablas SAP...';
PRINT '';

-- Verificar pack_conversion
IF EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[pack_conversion]') AND type in (N'U'))
BEGIN
    PRINT '✅ Tabla pack_conversion: EXISTE';
    
    -- Contar registros
    DECLARE @count_pack INT;
    SELECT @count_pack = COUNT(*) FROM pack_conversion;
    PRINT '   Registros en pack_conversion: ' + CAST(@count_pack AS VARCHAR(10));
    
    -- Mostrar algunos registros
    PRINT '   Primeros registros:';
    SELECT TOP 5 pack_id, unidad_conversion, descripcion 
    FROM pack_conversion 
    ORDER BY pack_id;
END
ELSE
BEGIN
    PRINT '❌ Tabla pack_conversion: NO EXISTE';
    PRINT '   Ejecuta: scripts/create_sap_tables.sql';
END
PRINT '';

-- Verificar producto_sap_cache
IF EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[producto_sap_cache]') AND type in (N'U'))
BEGIN
    PRINT '✅ Tabla producto_sap_cache: EXISTE';
    
    -- Contar registros
    DECLARE @count_cache INT;
    SELECT @count_cache = COUNT(*) FROM producto_sap_cache;
    PRINT '   Registros en producto_sap_cache: ' + CAST(@count_cache AS VARCHAR(10));
    
    -- Mostrar algunos registros
    IF @count_cache > 0
    BEGIN
        PRINT '   Últimos registros:';
        SELECT TOP 5 
            sku, 
            item_name, 
            pack_sap, 
            unidad_conversion,
            ultima_consulta
        FROM producto_sap_cache 
        WHERE activo = 1
        ORDER BY created_at DESC;
    END
    ELSE
    BEGIN
        PRINT '   (Tabla vacía - esto es normal si aún no se han consultado productos)';
    END
END
ELSE
BEGIN
    PRINT '❌ Tabla producto_sap_cache: NO EXISTE';
    PRINT '   Ejecuta: scripts/create_sap_tables.sql';
END
PRINT '';

-- Verificar columna precio_unitario_sap en despacho_detalle
IF EXISTS (
    SELECT * 
    FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[despacho_detalle]') 
    AND name = 'precio_unitario_sap'
)
BEGIN
    PRINT '✅ Columna precio_unitario_sap en despacho_detalle: EXISTE';
END
ELSE
BEGIN
    PRINT '❌ Columna precio_unitario_sap en despacho_detalle: NO EXISTE';
    PRINT '   Ejecuta: scripts/add_precio_unitario_sap_column.sql';
END
PRINT '';

PRINT 'Verificación completada.';
PRINT '';

