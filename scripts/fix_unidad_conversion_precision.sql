-- Script para corregir la precisión del campo unidad_conversion
-- El campo DECIMAL(10,9) no puede almacenar valores mayores a 9.999999999
-- pero algunos packs tienen valores como 12.0 (X1), por lo que necesitamos más precisión
-- 
-- Cambiamos a DECIMAL(10,4) para permitir valores hasta 999999.9999 con mayor precisión decimal
-- Ejecuta en la base de datos de la conexión (p. ej. SQL_SERVER_DATABASE).

-- Verificar si la columna existe y su tipo actual
IF EXISTS (
    SELECT * 
    FROM sys.columns 
    WHERE object_id = OBJECT_ID(N'[dbo].[producto_sap_cache]') 
    AND name = 'unidad_conversion'
)
BEGIN
    PRINT 'Campo unidad_conversion existe. Verificando tipo actual...';
    
    -- Obtener tipo actual
    DECLARE @CurrentType NVARCHAR(50);
    SELECT @CurrentType = TYPE_NAME(system_type_id) + '(' + 
        CAST(max_length AS VARCHAR) + ',' + 
        CAST(scale AS VARCHAR) + ')'
    FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[producto_sap_cache]')
    AND name = 'unidad_conversion';
    
    PRINT 'Tipo actual: ' + @CurrentType;
    
    -- Si el tipo es DECIMAL(10,9) o DECIMAL(10,2), cambiarlo a DECIMAL(10,4)
    IF @CurrentType LIKE 'decimal(10,9)%' OR @CurrentType LIKE 'numeric(10,9)%' 
       OR @CurrentType LIKE 'decimal(10,2)%' OR @CurrentType LIKE 'numeric(10,2)%'
    BEGIN
        PRINT 'Cambiando unidad_conversion a DECIMAL(10,4)...';
        
        ALTER TABLE [dbo].[producto_sap_cache]
        ALTER COLUMN unidad_conversion DECIMAL(10, 4) NULL;
        
        PRINT '✅ Campo unidad_conversion actualizado a DECIMAL(10,4)';
    END
    ELSE
    BEGIN
        PRINT '⚠️ El campo ya tiene un tipo diferente. Tipo actual: ' + @CurrentType;
        PRINT '   Si necesitas cambiarlo manualmente, usa:';
        PRINT '   ALTER TABLE [dbo].[producto_sap_cache] ALTER COLUMN unidad_conversion DECIMAL(10, 4) NULL;';
    END
END
ELSE
BEGIN
    PRINT '❌ El campo unidad_conversion no existe en producto_sap_cache';
END
GO

PRINT 'Script completado';
GO

