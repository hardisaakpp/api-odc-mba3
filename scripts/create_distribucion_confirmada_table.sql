-- ============================================================================
-- Script SQL para crear tabla de distribución confirmada (FASE 4)
-- ============================================================================
-- Modelo: Almacena la redistribución realizada por MABEL TRADING
-- después de recibir la confirmación del proveedor
-- ============================================================================

-- ============================================================================
-- Tabla: distribucion_confirmada
-- Almacena la redistribución por producto y tienda después de la confirmación
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[distribucion_confirmada]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[distribucion_confirmada] (
        id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        -- Relaciones
        pedido_id UNIQUEIDENTIFIER NOT NULL,
        pedido_detalle_id UNIQUEIDENTIFIER NOT NULL,
        tienda_id UNIQUEIDENTIFIER NOT NULL,
        
        -- Cantidades
        cantidad_solicitada INT NOT NULL CHECK (cantidad_solicitada >= 0),
        cantidad_confirmada INT NOT NULL CHECK (cantidad_confirmada >= 0),
        cantidad_asignada INT NOT NULL CHECK (cantidad_asignada >= 0),
        
        -- Costos
        costo_unitario_original DECIMAL(18, 4) NULL,
        costo_unitario_ajustado DECIMAL(18, 4) NULL,
        subtotal_original DECIMAL(18, 2) NULL,
        subtotal_ajustado DECIMAL(18, 2) NULL,
        
        -- Versionado y estado
        version INT NOT NULL DEFAULT 1,
        estado NVARCHAR(50) NOT NULL DEFAULT 'PENDIENTE',
        
        -- Auditoría
        creado_por NVARCHAR(450) NULL,
        fecha_creacion DATETIME DEFAULT GETDATE(),
        modificado_por NVARCHAR(450) NULL,
        fecha_modificacion DATETIME NULL,
        
        -- Foreign Keys
        CONSTRAINT FK_distribucion_confirmada_pedido 
            FOREIGN KEY (pedido_id) 
            REFERENCES pedido(pedido_id) 
            ON DELETE CASCADE,
        
        CONSTRAINT FK_distribucion_confirmada_pedido_detalle 
            FOREIGN KEY (pedido_detalle_id) 
            REFERENCES pedido_detalle(pedido_detalle_id) 
            ON DELETE CASCADE,
        
        CONSTRAINT FK_distribucion_confirmada_tienda 
            FOREIGN KEY (tienda_id) 
            REFERENCES tienda(tienda_id) 
            ON DELETE NO ACTION,
        
        -- Constraint: Una sola distribución confirmada por producto+tienda+versión
        CONSTRAINT UQ_distribucion_confirmada_producto_tienda_version 
            UNIQUE (pedido_detalle_id, tienda_id, version)
    );
    
    -- Índices para optimizar consultas
    CREATE INDEX idx_distribucion_confirmada_pedido_id ON distribucion_confirmada(pedido_id);
    CREATE INDEX idx_distribucion_confirmada_pedido_detalle_id ON distribucion_confirmada(pedido_detalle_id);
    CREATE INDEX idx_distribucion_confirmada_tienda_id ON distribucion_confirmada(tienda_id);
    CREATE INDEX idx_distribucion_confirmada_version ON distribucion_confirmada(version);
    CREATE INDEX idx_distribucion_confirmada_estado ON distribucion_confirmada(estado);
    CREATE INDEX idx_distribucion_confirmada_pedido_version ON distribucion_confirmada(pedido_id, version);
    
    PRINT '✅ Tabla distribucion_confirmada creada exitosamente.';
END
ELSE
BEGIN
    PRINT '⚠️ La tabla distribucion_confirmada ya existe.';
END
GO

-- ============================================================================
-- Tabla: distribucion_confirmada_historial
-- Almacena el historial de cambios en las redistribuciones
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[distribucion_confirmada_historial]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[distribucion_confirmada_historial] (
        id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        distribucion_confirmada_id UNIQUEIDENTIFIER NOT NULL,
        
        -- Datos del cambio
        accion NVARCHAR(50) NOT NULL,  -- 'CREAR', 'ACTUALIZAR', 'ELIMINAR', 'CONFIRMAR'
        version_anterior INT NULL,
        version_nueva INT NULL,
        
        -- Valores anteriores (snapshot)
        cantidad_asignada_anterior INT NULL,
        costo_unitario_ajustado_anterior DECIMAL(18, 4) NULL,
        subtotal_ajustado_anterior DECIMAL(18, 2) NULL,
        estado_anterior NVARCHAR(50) NULL,
        
        -- Valores nuevos (snapshot)
        cantidad_asignada_nuevo INT NULL,
        costo_unitario_ajustado_nuevo DECIMAL(18, 4) NULL,
        subtotal_ajustado_nuevo DECIMAL(18, 2) NULL,
        estado_nuevo NVARCHAR(50) NULL,
        
        -- Auditoría
        usuario NVARCHAR(450) NULL,
        fecha_cambio DATETIME DEFAULT GETDATE(),
        observaciones NVARCHAR(1000) NULL,
        
        CONSTRAINT FK_distribucion_confirmada_historial_distribucion 
            FOREIGN KEY (distribucion_confirmada_id) 
            REFERENCES distribucion_confirmada(id) 
            ON DELETE CASCADE
    );
    
    CREATE INDEX idx_distribucion_confirmada_historial_distribucion_id ON distribucion_confirmada_historial(distribucion_confirmada_id);
    CREATE INDEX idx_distribucion_confirmada_historial_fecha ON distribucion_confirmada_historial(fecha_cambio);
    CREATE INDEX idx_distribucion_confirmada_historial_usuario ON distribucion_confirmada_historial(usuario);
    
    PRINT '✅ Tabla distribucion_confirmada_historial creada exitosamente.';
END
ELSE
BEGIN
    PRINT '⚠️ La tabla distribucion_confirmada_historial ya existe.';
END
GO

-- ============================================================================
-- Verificar si existe columna estado en pedido y agregarla si no existe
-- ============================================================================
IF NOT EXISTS (
    SELECT * 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'pedido' 
    AND COLUMN_NAME = 'estado'
)
BEGIN
    ALTER TABLE pedido 
    ADD estado NVARCHAR(50) NULL DEFAULT 'PENDIENTE_CONFIRMACION_PROVEEDOR';
    
    CREATE INDEX idx_pedido_estado ON pedido(estado);
    
    PRINT '✅ Columna estado agregada a tabla pedido.';
END
ELSE
BEGIN
    PRINT '⚠️ La columna estado ya existe en tabla pedido.';
END
GO

-- ============================================================================
-- Comentarios de documentación
-- ============================================================================
EXEC sp_addextendedproperty 
    @name = N'MS_Description', 
    @value = N'Tabla que almacena la redistribución realizada por MABEL TRADING después de recibir la confirmación del proveedor. Permite versionado y trazabilidad completa.', 
    @level0type = N'SCHEMA', @level0name = N'dbo', 
    @level1type = N'TABLE', @level1name = N'distribucion_confirmada';

EXEC sp_addextendedproperty 
    @name = N'MS_Description', 
    @value = N'Historial de cambios en las redistribuciones confirmadas. Permite auditoría completa de todas las modificaciones.', 
    @level0type = N'SCHEMA', @level0name = N'dbo', 
    @level1type = N'TABLE', @level1name = N'distribucion_confirmada_historial';

PRINT '✅ Script de creación de tablas de distribución confirmada completado.';
GO
