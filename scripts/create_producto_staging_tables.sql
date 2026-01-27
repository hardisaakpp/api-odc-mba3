-- ============================================================================
-- Script SQL para crear tablas de staging de productos
-- ============================================================================
-- Este script crea las tablas necesarias para almacenar copias locales
-- de los maestros de productos MBA3 y SAP, evitando consultas en tiempo real.
-- ============================================================================

-- ============================================================================
-- 1. Tabla: producto_mba3_staging
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[producto_mba3_staging]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[producto_mba3_staging] (
        -- Primary Key (UUID para tracking, pero product_id es la clave natural)
        staging_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        -- Clave natural del producto (única)
        product_id VARCHAR(100) NOT NULL,
        
        -- Datos del producto
        product_name NVARCHAR(255) NULL,
        corp VARCHAR(50) NULL,
        grupo_prenda VARCHAR(100) NULL,
        talla VARCHAR(50) NULL,
        presentacion VARCHAR(100) NULL,
        descontinuado BIT NOT NULL DEFAULT 0,
        
        -- CORRECCIÓN CRÍTICA: Normalización persistida
        product_id_normalizado VARCHAR(100) NOT NULL,
        
        -- Metadata de sincronización
        ultima_sincronizacion DATETIME NOT NULL,  -- Sin DEFAULT, se setea explícitamente
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE(),
        
        -- Constraint para asegurar unicidad por product_id
        CONSTRAINT UQ_producto_mba3_staging_product_id UNIQUE (product_id)
    );
    
    -- Índices para búsquedas rápidas
    CREATE INDEX idx_producto_mba3_staging_product_id ON producto_mba3_staging(product_id);
    CREATE INDEX idx_producto_mba3_staging_product_id_norm ON producto_mba3_staging(product_id_normalizado);
    CREATE INDEX idx_producto_mba3_staging_descontinuado ON producto_mba3_staging(descontinuado);
    CREATE INDEX idx_producto_mba3_staging_grupo_prenda ON producto_mba3_staging(grupo_prenda);
    CREATE INDEX idx_producto_mba3_staging_ultima_sync ON producto_mba3_staging(ultima_sincronizacion);
    
    PRINT 'Tabla producto_mba3_staging creada exitosamente';
END
ELSE
BEGIN
    PRINT 'Tabla producto_mba3_staging ya existe';
END
GO

-- ============================================================================
-- 2. Tabla: producto_sap_staging
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[producto_sap_staging]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[producto_sap_staging] (
        -- Primary Key (UUID para tracking, pero item_code es la clave natural)
        staging_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        -- Clave natural del producto (única)
        item_code VARCHAR(100) NOT NULL,
        
        -- Datos del producto
        item_name NVARCHAR(255) NULL,
        pack_sap VARCHAR(10) NULL,
        itms_grp_cod INT NULL,
        itms_grp_nam VARCHAR(100) NULL,  -- Nombre del grupo de artículos
        valid_for CHAR(1) NULL,  -- 'Y' o 'N' (dato crudo de SAP)
        
        -- CORRECCIÓN CRÍTICA: Normalización persistida
        item_code_normalizado VARCHAR(100) NOT NULL,
        
        -- CORRECCIÓN: activo es derivado de valid_for, no editable manualmente
        activo BIT NOT NULL DEFAULT 0,  -- Calculado: valid_for == 'Y'
        
        -- Metadata de sincronización
        ultima_sincronizacion DATETIME NOT NULL,  -- Sin DEFAULT, se setea explícitamente
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE(),
        
        -- Constraint para asegurar unicidad por item_code
        CONSTRAINT UQ_producto_sap_staging_item_code UNIQUE (item_code)
    );
    
    -- Índices para búsquedas rápidas
    CREATE INDEX idx_producto_sap_staging_item_code ON producto_sap_staging(item_code);
    CREATE INDEX idx_producto_sap_staging_item_code_norm ON producto_sap_staging(item_code_normalizado);
    CREATE INDEX idx_producto_sap_staging_activo ON producto_sap_staging(activo);
    CREATE INDEX idx_producto_sap_staging_valid_for ON producto_sap_staging(valid_for);
    CREATE INDEX idx_producto_sap_staging_pack_sap ON producto_sap_staging(pack_sap);
    CREATE INDEX idx_producto_sap_staging_itms_grp_nam ON producto_sap_staging(itms_grp_nam);
    CREATE INDEX idx_producto_sap_staging_ultima_sync ON producto_sap_staging(ultima_sincronizacion);
    
    PRINT 'Tabla producto_sap_staging creada exitosamente';
END
ELSE
BEGIN
    PRINT 'Tabla producto_sap_staging ya existe';
END
GO

-- ============================================================================
-- 3. Tabla: sync_control
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[sync_control]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[sync_control] (
        sync_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        -- Entidad sincronizada
        entidad VARCHAR(50) NOT NULL,  -- 'MBA3' o 'SAP'
        
        -- Estado de la sincronización
        estado VARCHAR(20) NOT NULL,  -- 'EXITOSA', 'ERROR', 'EN_PROGRESO'
        
        -- Resultados
        ultima_sync_exitosa DATETIME NULL,
        registros_sincronizados INT DEFAULT 0,
        registros_nuevos INT DEFAULT 0,
        registros_actualizados INT DEFAULT 0,
        registros_eliminados INT DEFAULT 0,  -- Si implementas soft delete
        
        -- Errores
        mensaje_error NVARCHAR(MAX) NULL,
        stack_trace NVARCHAR(MAX) NULL,
        
        -- Metadata
        duracion_segundos INT NULL,
        iniciado_por VARCHAR(100) NULL,  -- Usuario o 'CELERY'
        created_at DATETIME DEFAULT GETDATE(),
        
        -- Constraints
        CONSTRAINT CK_sync_control_entidad CHECK (entidad IN ('MBA3', 'SAP')),
        CONSTRAINT CK_sync_control_estado CHECK (estado IN ('EXITOSA', 'ERROR', 'EN_PROGRESO'))
    );
    
    -- Índices
    CREATE INDEX idx_sync_control_entidad ON sync_control(entidad);
    CREATE INDEX idx_sync_control_estado ON sync_control(estado);
    CREATE INDEX idx_sync_control_ultima_sync ON sync_control(ultima_sync_exitosa);
    CREATE INDEX idx_sync_control_created_at ON sync_control(created_at);
    
    PRINT 'Tabla sync_control creada exitosamente';
END
ELSE
BEGIN
    PRINT 'Tabla sync_control ya existe';
END
GO

PRINT 'Script de staging de productos completado exitosamente';
GO



