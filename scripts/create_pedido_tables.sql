-- ============================================================================
-- Script SQL para crear tablas de pedidos desde plantillas Excel
-- ============================================================================
-- Modelo: Pedido → PedidoDetalle → PedidoDetalleTienda
-- ENFOQUE: Solo ingesta y persistencia, sin cálculos ni validaciones de negocio
-- ============================================================================

-- ============================================================================
-- 1. Tabla: tienda (maestro de tiendas)
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[tienda]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[tienda] (
        tienda_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        codigo NVARCHAR(100) NOT NULL,  -- Aumentado de 20 a 100 para soportar nombres largos de tiendas
        nombre NVARCHAR(150) NULL,
        activa BIT DEFAULT 1,
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE(),
        
        CONSTRAINT UQ_tienda_codigo UNIQUE (codigo)
    );
    
    CREATE INDEX idx_tienda_codigo ON tienda(codigo);
    CREATE INDEX idx_tienda_activa ON tienda(activa);
    
    PRINT 'Tabla tienda creada exitosamente.';
END
ELSE
BEGIN
    PRINT 'La tabla tienda ya existe.';
END
GO

-- ============================================================================
-- 2. Tabla: pedido (cabecera)
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[pedido]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[pedido] (
        pedido_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        -- Business key (único pero no PK)
        numero_pedido NVARCHAR(100) NOT NULL,
        
        fecha_pedido DATE NULL,
        fecha_entrega NVARCHAR(50) NULL,  -- Puede ser "INMEDIATO" o fecha
        forma_pago NVARCHAR(50) NULL,
        
        mensaje NVARCHAR(100) NULL,
        proveedor_nombre NVARCHAR(150) NULL,
        comprador_nombre NVARCHAR(150) NULL,
        comprador_codigo NVARCHAR(50) NULL,
        
        origen_traslado NVARCHAR(50) NULL,
        serie NVARCHAR(50) NULL,
        
        archivo_nombre NVARCHAR(255) NOT NULL,
        creado_por NVARCHAR(450) NULL,  -- User ID del JWT
        creado_en DATETIME DEFAULT GETDATE(),
        
        CONSTRAINT UQ_pedido_numero_pedido UNIQUE (numero_pedido)
    );
    
    CREATE INDEX idx_pedido_numero_pedido ON pedido(numero_pedido);
    CREATE INDEX idx_pedido_creado_en ON pedido(creado_en);
    CREATE INDEX idx_pedido_proveedor ON pedido(proveedor_nombre);
    CREATE INDEX idx_pedido_comprador ON pedido(comprador_codigo);
    
    PRINT 'Tabla pedido creada exitosamente.';
END
ELSE
BEGIN
    PRINT 'La tabla pedido ya existe.';
END
GO

-- ============================================================================
-- 3. Tabla: pedido_detalle (artículos del pedido)
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[pedido_detalle] (
        pedido_detalle_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        pedido_id UNIQUEIDENTIFIER NOT NULL,
        
        -- Información del producto
        codigo_interno NVARCHAR(50) NULL,
        descripcion_sap NVARCHAR(255) NULL,
        marca NVARCHAR(50) NULL,
        codigo_barras NVARCHAR(50) NULL,
        
        -- Datos SAP
        pack NVARCHAR(50) NULL,
        
        -- Precios (NO cantidad aquí, va en pedido_detalle_tienda)
        costo_doc_sin_iva DECIMAL(18, 4) NULL,
        descuento_1 DECIMAL(5, 2) NULL,  -- Porcentaje de descuento
        pvp DECIMAL(18, 4) NULL,  -- Precio de venta público
        
        -- Totales (se guardan tal cual vienen del Excel, NO se recalculan)
        subtotal DECIMAL(18, 2) NULL,
        total DECIMAL(18, 2) NULL,
        
        created_at DATETIME DEFAULT GETDATE(),
        
        CONSTRAINT FK_pedido_detalle_pedido 
            FOREIGN KEY (pedido_id) 
            REFERENCES pedido(pedido_id) 
            ON DELETE CASCADE
    );
    
    CREATE INDEX idx_pedido_detalle_pedido_id ON pedido_detalle(pedido_id);
    CREATE INDEX idx_pedido_detalle_codigo_interno ON pedido_detalle(codigo_interno);
    CREATE INDEX idx_pedido_detalle_codigo_barras ON pedido_detalle(codigo_barras);
    
    PRINT 'Tabla pedido_detalle creada exitosamente.';
END
ELSE
BEGIN
    PRINT 'La tabla pedido_detalle ya existe.';
END
GO

-- ============================================================================
-- 4. Tabla: pedido_detalle_tienda (distribución por tienda)
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle_tienda]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[pedido_detalle_tienda] (
        id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        pedido_detalle_id UNIQUEIDENTIFIER NOT NULL,
        tienda_id UNIQUEIDENTIFIER NOT NULL,
        
        -- Aquí vive la cantidad (único campo que cambia por tienda; acepta decimales, ej. 0.5, 1.25)
        cantidad DECIMAL(18, 4) NOT NULL CHECK (cantidad >= 0),
        
        created_at DATETIME DEFAULT GETDATE(),
        
        CONSTRAINT FK_pedido_detalle_tienda_detalle 
            FOREIGN KEY (pedido_detalle_id) 
            REFERENCES pedido_detalle(pedido_detalle_id) 
            ON DELETE CASCADE,
        
        CONSTRAINT FK_pedido_detalle_tienda_tienda 
            FOREIGN KEY (tienda_id) 
            REFERENCES tienda(tienda_id) 
            ON DELETE CASCADE,
        
        CONSTRAINT UQ_pedido_detalle_tienda_detalle_tienda 
            UNIQUE (pedido_detalle_id, tienda_id)
    );
    
    CREATE INDEX idx_pedido_detalle_tienda_detalle_id ON pedido_detalle_tienda(pedido_detalle_id);
    CREATE INDEX idx_pedido_detalle_tienda_tienda_id ON pedido_detalle_tienda(tienda_id);
    
    PRINT 'Tabla pedido_detalle_tienda creada exitosamente.';
END
ELSE
BEGIN
    PRINT 'La tabla pedido_detalle_tienda ya existe.';
END
GO

