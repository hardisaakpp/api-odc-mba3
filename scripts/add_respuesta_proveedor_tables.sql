-- ============================================================================
-- Script SQL para agregar tablas de respuesta del proveedor (FASE 3)
-- ============================================================================
-- Modelo: Respuesta por PRODUCTO (consolidado) + Detalle por tienda (opcional)
-- ============================================================================

-- ============================================================================
-- Tabla: pedido_respuesta_proveedor (CABECERA)
-- Representa el EVENTO de respuesta del proveedor como acto de negocio
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[pedido_respuesta_proveedor]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[pedido_respuesta_proveedor] (
        respuesta_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        pedido_id UNIQUEIDENTIFIER NOT NULL,
        
        -- Metadatos de la respuesta
        version INT NOT NULL DEFAULT 1,
        estado NVARCHAR(50) NOT NULL DEFAULT 'PENDIENTE_REVISION',
        fecha_respuesta DATETIME NOT NULL DEFAULT GETDATE(),
        fecha_aprobacion DATETIME NULL,
        
        -- Auditoría
        creado_por NVARCHAR(450) NULL,
        aprobado_por NVARCHAR(450) NULL,
        observaciones_generales NVARCHAR(1000) NULL,
        
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE(),
        
        CONSTRAINT FK_respuesta_pedido 
            FOREIGN KEY (pedido_id) 
            REFERENCES pedido(pedido_id) 
            ON DELETE CASCADE,
        
        CONSTRAINT UQ_respuesta_pedido_version 
            UNIQUE (pedido_id, version)
    );
    
    CREATE INDEX idx_respuesta_pedido_id ON pedido_respuesta_proveedor(pedido_id);
    CREATE INDEX idx_respuesta_estado ON pedido_respuesta_proveedor(estado);
    CREATE INDEX idx_respuesta_fecha ON pedido_respuesta_proveedor(fecha_respuesta);
    
    PRINT 'Tabla pedido_respuesta_proveedor creada exitosamente.';
END
ELSE
BEGIN
    PRINT 'La tabla pedido_respuesta_proveedor ya existe.';
END
GO

-- ============================================================================
-- Tabla: pedido_respuesta_proveedor_detalle
-- Respuesta a nivel PRODUCTO (consolidado) - modelo principal
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[pedido_respuesta_proveedor_detalle]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[pedido_respuesta_proveedor_detalle] (
        id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        respuesta_id UNIQUEIDENTIFIER NOT NULL,
        pedido_detalle_id UNIQUEIDENTIFIER NOT NULL,
        
        -- Cantidades a nivel producto (consolidado)
        cantidad_solicitada_total INT NOT NULL,
        cantidad_confirmada_total INT NOT NULL CHECK (cantidad_confirmada_total >= 0),
        
        -- Precios ajustados
        costo_doc_sin_iva_original DECIMAL(18, 4) NULL,
        costo_doc_sin_iva_ajustado DECIMAL(18, 4) NULL,
        descuento_1_original DECIMAL(5, 2) NULL,
        descuento_1_ajustado DECIMAL(5, 2) NULL,
        
        -- Observaciones específicas del producto
        observaciones NVARCHAR(500) NULL,
        
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE(),
        
        CONSTRAINT FK_respuesta_detalle_respuesta 
            FOREIGN KEY (respuesta_id) 
            REFERENCES pedido_respuesta_proveedor(respuesta_id) 
            ON DELETE CASCADE,
        
        CONSTRAINT FK_respuesta_detalle_pedido_detalle 
            FOREIGN KEY (pedido_detalle_id) 
            REFERENCES pedido_detalle(pedido_detalle_id) 
            ON DELETE NO ACTION,
        
        CONSTRAINT UQ_respuesta_detalle_respuesta_producto 
            UNIQUE (respuesta_id, pedido_detalle_id)
    );
    
    CREATE INDEX idx_respuesta_detalle_respuesta_id ON pedido_respuesta_proveedor_detalle(respuesta_id);
    CREATE INDEX idx_respuesta_detalle_pedido_detalle_id ON pedido_respuesta_proveedor_detalle(pedido_detalle_id);
    
    PRINT 'Tabla pedido_respuesta_proveedor_detalle creada exitosamente.';
END
ELSE
BEGIN
    PRINT 'La tabla pedido_respuesta_proveedor_detalle ya existe.';
END
GO

-- ============================================================================
-- Tabla: pedido_respuesta_proveedor_detalle_tienda (OPCIONAL)
-- Solo si el proveedor especifica distribución por tienda
-- Si no, el sistema distribuye automáticamente basado en proporciones
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[pedido_respuesta_proveedor_detalle_tienda]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[pedido_respuesta_proveedor_detalle_tienda] (
        id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        respuesta_detalle_id UNIQUEIDENTIFIER NOT NULL,
        pedido_detalle_tienda_id UNIQUEIDENTIFIER NOT NULL,
        
        -- Cantidad confirmada por tienda (si el proveedor especifica)
        cantidad_confirmada INT NOT NULL CHECK (cantidad_confirmada >= 0),
        
        -- Observaciones específicas de esta distribución
        observaciones NVARCHAR(500) NULL,
        
        created_at DATETIME DEFAULT GETDATE(),
        
        CONSTRAINT FK_respuesta_detalle_tienda_respuesta_detalle 
            FOREIGN KEY (respuesta_detalle_id) 
            REFERENCES pedido_respuesta_proveedor_detalle(id) 
            ON DELETE CASCADE,
        
        CONSTRAINT FK_respuesta_detalle_tienda_pedido_detalle_tienda 
            FOREIGN KEY (pedido_detalle_tienda_id) 
            REFERENCES pedido_detalle_tienda(id) 
            ON DELETE NO ACTION,
        
        CONSTRAINT UQ_respuesta_detalle_tienda 
            UNIQUE (pedido_detalle_tienda_id)
    );
    
    CREATE INDEX idx_respuesta_detalle_tienda_respuesta_detalle_id ON pedido_respuesta_proveedor_detalle_tienda(respuesta_detalle_id);
    
    PRINT 'Tabla pedido_respuesta_proveedor_detalle_tienda creada exitosamente (opcional).';
END
ELSE
BEGIN
    PRINT 'La tabla pedido_respuesta_proveedor_detalle_tienda ya existe.';
END
GO

