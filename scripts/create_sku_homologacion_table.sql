-- ============================================================================
-- Script SQL para crear tabla sku_homologacion
-- ============================================================================
-- Esta tabla almacena las homologaciones entre SKUs de MBA3 y SAP,
-- permitiendo la gestión manual de correspondencias y diferencias.
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[sku_homologacion]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[sku_homologacion] (
        -- Primary Key
        homologacion_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        -- Datos de MBA3 (requeridos)
        sku_mba3 VARCHAR(100) NOT NULL,
        nombre_producto_mba3 NVARCHAR(255) NULL,
        precio_unitario_mba3 DECIMAL(18, 2) NULL,
        cantidad_docena_mba3 DECIMAL(18, 2) NULL,
        total_linea_mba3 DECIMAL(18, 2) NULL,
        
        -- Datos de SAP (opcionales - pueden ser NULL)
        sku_sap VARCHAR(100) NULL,
        nombre_producto_sap NVARCHAR(255) NULL,
        precio_unitario_sap DECIMAL(18, 2) NULL,
        cantidad_pack_sap DECIMAL(18, 2) NULL,
        unidad_sap VARCHAR(20) NULL,  -- Ej: "UN", "PC", "KG", etc.
        subtotal_sap DECIMAL(18, 2) NULL,
        
        -- Estado y flags
        estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',  -- PENDIENTE | HOMOLOGADO | ERROR
        tiene_diferencias BIT NOT NULL DEFAULT 0,         -- true si hay diferencias MBA3 vs SAP
        tiene_datos_sap BIT NOT NULL DEFAULT 0,           -- true si tiene al menos un campo SAP
        
        -- Relaciones con otras tablas
        detalle_id UNIQUEIDENTIFIER NULL,  -- FK a despacho_detalle
        despacho_id UNIQUEIDENTIFIER NULL, -- FK a despacho_cabecera
        
        -- Metadata
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE(),
        ultima_modificacion DATETIME NULL,
        modificado_por VARCHAR(100) NULL,  -- Usuario que modificó
        
        -- Constraints para validar estado
        CONSTRAINT CK_sku_homologacion_estado CHECK (estado IN ('PENDIENTE', 'HOMOLOGADO', 'ERROR'))
    );
    
    -- Crear índices para búsquedas rápidas
    CREATE INDEX idx_sku_homologacion_sku_mba3 ON sku_homologacion(sku_mba3);
    CREATE INDEX idx_sku_homologacion_sku_sap ON sku_homologacion(sku_sap);
    CREATE INDEX idx_sku_homologacion_estado ON sku_homologacion(estado);
    CREATE INDEX idx_sku_homologacion_tiene_diferencias ON sku_homologacion(tiene_diferencias);
    CREATE INDEX idx_sku_homologacion_tiene_datos_sap ON sku_homologacion(tiene_datos_sap);
    CREATE INDEX idx_sku_homologacion_detalle_id ON sku_homologacion(detalle_id);
    CREATE INDEX idx_sku_homologacion_despacho_id ON sku_homologacion(despacho_id);
    CREATE INDEX idx_sku_homologacion_created_at ON sku_homologacion(created_at DESC);
    
    -- Índice compuesto para búsquedas complejas
    CREATE INDEX idx_sku_homologacion_estado_diferencias ON sku_homologacion(estado, tiene_diferencias);
    
    PRINT '✅ Tabla sku_homologacion creada exitosamente';
    
END
ELSE
BEGIN
    PRINT '⚠️ La tabla sku_homologacion ya existe';
END
GO

-- ============================================================================
-- Verificación de la tabla creada
-- ============================================================================
PRINT ' ';
PRINT '============================================================================';
PRINT 'VERIFICACIÓN DE LA TABLA sku_homologacion';
PRINT '============================================================================';

SELECT 
    c.name AS [Columna],
    t.name AS [Tipo],
    c.max_length AS [Longitud],
    c.is_nullable AS [Nullable],
    ISNULL(dc.definition, '-') AS [Valor por defecto]
FROM sys.columns c
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
LEFT JOIN sys.default_constraints dc ON c.default_object_id = dc.object_id
WHERE c.object_id = OBJECT_ID('sku_homologacion')
ORDER BY c.column_id;

PRINT ' ';
PRINT '============================================================================';
PRINT 'ÍNDICES CREADOS';
PRINT '============================================================================';

-- Compatible con SQL Server 2012+ (sin STRING_AGG)
SELECT 
    i.name AS [Nombre Indice],
    i.type_desc AS [Tipo],
    STUFF((
        SELECT ', ' + c2.name
        FROM sys.index_columns ic2
        INNER JOIN sys.columns c2 ON ic2.object_id = c2.object_id AND ic2.column_id = c2.column_id
        WHERE ic2.object_id = i.object_id AND ic2.index_id = i.index_id
        ORDER BY ic2.key_ordinal
        FOR XML PATH('')
    ), 1, 2, '') AS [Columnas]
FROM sys.indexes i
WHERE i.object_id = OBJECT_ID('sku_homologacion')
    AND i.name IS NOT NULL
ORDER BY i.index_id;

GO

