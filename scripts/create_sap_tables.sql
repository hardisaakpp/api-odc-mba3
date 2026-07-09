-- ============================================================================
-- Script SQL para crear tablas de conversión SAP
-- ============================================================================
-- Este script crea las tablas necesarias para manejar conversiones de unidades
-- entre El Rayo (docenas) y Mabel (packs SAP)
-- ============================================================================

-- Tabla maestra de conversión PACK → unidad de conversión
-- Almacena la relación entre packs (X1, X2, X3, etc.) y sus unidades de conversión
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[pack_conversion]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[pack_conversion] (
        pack_id VARCHAR(10) PRIMARY KEY,              -- 'X1', 'X2', 'X3', etc.
        unidad_conversion DECIMAL(10, 9) NOT NULL,     -- 12, 6, 4, 2.4, etc.
        descripcion VARCHAR(100) NULL,                  -- Descripción opcional
        activo BIT DEFAULT 1,                          -- Para habilitar/deshabilitar
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE()
    );
    
    -- Crear índice para búsquedas rápidas
    CREATE INDEX idx_pack_conversion_activo ON pack_conversion(activo);
    
    PRINT 'Tabla pack_conversion creada exitosamente';
END
ELSE
BEGIN
    PRINT 'Tabla pack_conversion ya existe';
END
GO

-- Poblar tabla pack_conversion con datos iniciales
-- Estos valores representan: unidad_conversion = 12 / número_del_pack
IF NOT EXISTS (SELECT 1 FROM pack_conversion WHERE pack_id = 'X1')
BEGIN
    INSERT INTO pack_conversion (pack_id, unidad_conversion, descripcion) VALUES
        ('X1', 12.0, 'Pack X1 - 12 unidades por docena'),
        ('X2', 6.0, 'Pack X2 - 6 unidades por docena'),
        ('X3', 4.0, 'Pack X3 - 4 unidades por docena'),
        ('X4', 3.0, 'Pack X4 - 3 unidades por docena'),
        ('X5', 2.4, 'Pack X5 - 2.4 unidades por docena'),
        ('X6', 2.0, 'Pack X6 - 2 unidades por docena'),
        ('X7', 1.714285714, 'Pack X7 - 1.714285714 unidades por docena'),
        ('X8', 1.5, 'Pack X8 - 1.5 unidades por docena'),
        ('X9', 1.333333333, 'Pack X9 - 1.333333333 unidades por docena'),
        ('X12', 1.0, 'Pack X12 - 1 unidad por docena');
    
    PRINT 'Datos iniciales de pack_conversion insertados';
END
ELSE
BEGIN
    PRINT 'Datos iniciales de pack_conversion ya existen';
END
GO

-- Tabla de cache para información de productos SAP
-- Almacena información consultada de SAP para evitar consultas repetidas
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[producto_sap_cache]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[producto_sap_cache] (
        cache_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        sku VARCHAR(50) NOT NULL,                      -- SKU del producto (ItemCode)
        item_code VARCHAR(50) NOT NULL,                 -- ItemCode de SAP (mismo que SKU)
        item_name VARCHAR(200) NULL,                    -- Nombre del producto en SAP
        pack_sap VARCHAR(10) NULL,                      -- U_IXX_PACK de SAP (X1, X2, X3, etc.)
        unidad_conversion DECIMAL(10, 4) NULL,          -- Unidad de conversión calculada (10,4 permite valores hasta 999999.9999 con mayor precisión decimal)
        pack_id VARCHAR(10) NULL,                       -- FK a pack_conversion.pack_id
        ultima_consulta DATETIME NULL,                  -- Cuándo se consultó SAP por última vez
        activo BIT DEFAULT 1,
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE(),
        
        -- Constraint para asegurar unicidad por SKU
        CONSTRAINT UQ_producto_sap_cache_sku UNIQUE (sku)
    );
    
    -- Crear índices para búsquedas rápidas
    CREATE INDEX idx_producto_sap_cache_sku ON producto_sap_cache(sku);
    CREATE INDEX idx_producto_sap_cache_pack_sap ON producto_sap_cache(pack_sap);
    CREATE INDEX idx_producto_sap_cache_activo ON producto_sap_cache(activo);
    
    -- Foreign key a pack_conversion (opcional, puede ser NULL si no hay pack)
    -- ALTER TABLE producto_sap_cache
    -- ADD CONSTRAINT FK_producto_sap_cache_pack_conversion
    -- FOREIGN KEY (pack_id) REFERENCES pack_conversion(pack_id);
    
    PRINT 'Tabla producto_sap_cache creada exitosamente';
END
ELSE
BEGIN
    PRINT 'Tabla producto_sap_cache ya existe';
END
GO

PRINT 'Script completado exitosamente';
GO

