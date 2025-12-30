-- ============================================================================
-- Script SQL para crear tabla de productos no homologados ya notificados
-- ============================================================================
-- Esta tabla registra qué productos ya fueron notificados por email
-- para evitar enviar notificaciones repetidas del mismo producto
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[productos_no_homologados_notificados]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[productos_no_homologados_notificados] (
        notificacion_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        sku VARCHAR(50) NOT NULL,                      -- SKU del producto no homologado
        fecha_notificacion DATETIME NOT NULL DEFAULT GETDATE(),  -- Cuándo se notificó
        veces_notificado INT DEFAULT 1,                -- Cuántas veces se ha notificado
        ultima_notificacion DATETIME NOT NULL DEFAULT GETDATE(), -- Última vez que se notificó
        activo BIT DEFAULT 1,                          -- Para habilitar/deshabilitar
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE(),
        
        -- Constraint para asegurar unicidad por SKU
        CONSTRAINT UQ_productos_no_homologados_notificados_sku UNIQUE (sku)
    );
    
    -- Crear índices para búsquedas rápidas
    CREATE INDEX idx_productos_no_homologados_notificados_sku ON productos_no_homologados_notificados(sku);
    CREATE INDEX idx_productos_no_homologados_notificados_activo ON productos_no_homologados_notificados(activo);
    CREATE INDEX idx_productos_no_homologados_notificados_fecha ON productos_no_homologados_notificados(fecha_notificacion);
    
    PRINT 'Tabla productos_no_homologados_notificados creada exitosamente';
END
ELSE
BEGIN
    PRINT 'Tabla productos_no_homologados_notificados ya existe';
END
GO

PRINT 'Script completado exitosamente';
GO

























