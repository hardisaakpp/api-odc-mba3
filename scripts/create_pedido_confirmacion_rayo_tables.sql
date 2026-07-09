-- ============================================================================
-- Script SQL: Crear tablas para historial de confirmaciones de EL RAYO
-- ============================================================================
-- Descripción: Almacena un historial completo de cada confirmación realizada
--              por EL RAYO cuando hace clic en "Confirmar", incluyendo
--              snapshot de todos los cambios (valores antes y después)
-- Fecha: 2026-01-15
-- ============================================================================
-- Ejecuta en la base de datos actual (la de la conexión); no usar USE para
-- permitir distintos nombres de BD (ej. store_control, MBA3_Consultas, etc.).
-- ============================================================================

-- ============================================================================
-- Tabla principal: pedido_confirmacion_rayo
-- ============================================================================
-- Almacena cada evento de confirmación realizado por EL RAYO
IF NOT EXISTS (
    SELECT * 
    FROM sys.objects 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_confirmacion_rayo]') 
    AND type in (N'U')
)
BEGIN
    CREATE TABLE [dbo].[pedido_confirmacion_rayo] (
        confirmacion_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        -- Referencias
        pedido_id UNIQUEIDENTIFIER NOT NULL,
        respuesta_id UNIQUEIDENTIFIER NULL,  -- FK a pedido_respuesta_proveedor
        
        -- Auditoría
        confirmado_por NVARCHAR(450) NOT NULL,  -- User ID de EL RAYO
        fecha_confirmacion DATETIME DEFAULT GETDATE(),
        
        -- Resumen de cambios
        total_detalles_modificados INT DEFAULT 0,
        detalles_modificados NVARCHAR(MAX) NULL,  -- JSON con resumen de cambios
        
        -- Campos adicionales
        observaciones_generales NVARCHAR(MAX) NULL,
        
        -- Constraints
        CONSTRAINT FK_confirmacion_rayo_pedido 
            FOREIGN KEY (pedido_id) 
            REFERENCES pedido(pedido_id) 
            ON DELETE CASCADE,
        
        CONSTRAINT FK_confirmacion_rayo_respuesta 
            FOREIGN KEY (respuesta_id) 
            REFERENCES pedido_respuesta_proveedor(respuesta_id) 
            ON DELETE NO ACTION
    );
    
    -- Índices para mejorar rendimiento
    CREATE INDEX idx_confirmacion_rayo_pedido_id 
        ON pedido_confirmacion_rayo(pedido_id);
    
    CREATE INDEX idx_confirmacion_rayo_respuesta_id 
        ON pedido_confirmacion_rayo(respuesta_id);
    
    CREATE INDEX idx_confirmacion_rayo_fecha 
        ON pedido_confirmacion_rayo(fecha_confirmacion DESC);
    
    CREATE INDEX idx_confirmacion_rayo_usuario 
        ON pedido_confirmacion_rayo(confirmado_por);
    
    -- Índice compuesto para búsquedas por pedido y fecha
    CREATE INDEX idx_confirmacion_rayo_pedido_fecha 
        ON pedido_confirmacion_rayo(pedido_id, fecha_confirmacion DESC);
    
    PRINT '✅ Tabla pedido_confirmacion_rayo creada exitosamente.';
END
ELSE
BEGIN
    PRINT '⚠️ La tabla pedido_confirmacion_rayo ya existe.';
END
GO

-- ============================================================================
-- Tabla de detalle: pedido_confirmacion_rayo_detalle
-- ============================================================================
-- Almacena los cambios específicos de cada detalle del pedido en cada confirmación
IF NOT EXISTS (
    SELECT * 
    FROM sys.objects 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_confirmacion_rayo_detalle]') 
    AND type in (N'U')
)
BEGIN
    CREATE TABLE [dbo].[pedido_confirmacion_rayo_detalle] (
        confirmacion_detalle_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        -- Referencias
        confirmacion_id UNIQUEIDENTIFIER NOT NULL,
        pedido_detalle_id UNIQUEIDENTIFIER NOT NULL,
        
        -- Valores anteriores (antes de la confirmación)
        costo_anterior DECIMAL(18,2) NULL,
        total_anterior DECIMAL(18,2) NULL,
        comentario_anterior NVARCHAR(MAX) NULL,
        
        -- Valores nuevos (confirmados por EL RAYO)
        costo_nuevo DECIMAL(18,2) NULL,
        total_nuevo DECIMAL(18,2) NULL,
        comentario_nuevo NVARCHAR(MAX) NULL,
        
        -- Flags de qué campos cambiaron
        cambio_costo BIT DEFAULT 0,
        cambio_total BIT DEFAULT 0,
        cambio_comentario BIT DEFAULT 0,
        
        -- Metadata adicional
        codigo_producto NVARCHAR(100) NULL,  -- Para facilitar consultas
        
        -- Constraints
        CONSTRAINT FK_confirmacion_rayo_detalle_confirmacion 
            FOREIGN KEY (confirmacion_id) 
            REFERENCES pedido_confirmacion_rayo(confirmacion_id) 
            ON DELETE CASCADE,
        
        CONSTRAINT FK_confirmacion_rayo_detalle_pedido_detalle 
            FOREIGN KEY (pedido_detalle_id) 
            REFERENCES pedido_detalle(pedido_detalle_id) 
            ON DELETE NO ACTION
    );
    
    -- Índices para mejorar rendimiento
    CREATE INDEX idx_confirmacion_rayo_detalle_confirmacion_id 
        ON pedido_confirmacion_rayo_detalle(confirmacion_id);
    
    CREATE INDEX idx_confirmacion_rayo_detalle_pedido_detalle_id 
        ON pedido_confirmacion_rayo_detalle(pedido_detalle_id);
    
    CREATE INDEX idx_confirmacion_rayo_detalle_codigo 
        ON pedido_confirmacion_rayo_detalle(codigo_producto);
    
    -- Índice compuesto para búsquedas por confirmación y detalle
    CREATE INDEX idx_confirmacion_rayo_detalle_confirmacion_detalle 
        ON pedido_confirmacion_rayo_detalle(confirmacion_id, pedido_detalle_id);
    
    PRINT '✅ Tabla pedido_confirmacion_rayo_detalle creada exitosamente.';
END
ELSE
BEGIN
    PRINT '⚠️ La tabla pedido_confirmacion_rayo_detalle ya existe.';
END
GO

-- ============================================================================
-- Verificar que las tablas se crearon correctamente
-- ============================================================================

-- Verificar tabla principal
PRINT '';
PRINT '📋 Estructura de pedido_confirmacion_rayo:';
SELECT 
    c.name AS column_name,
    t.name AS data_type,
    c.max_length,
    c.is_nullable,
    CASE WHEN dc.definition IS NOT NULL THEN dc.definition ELSE 'Sin default' END AS default_value
FROM sys.columns c
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
LEFT JOIN sys.default_constraints dc ON c.default_object_id = dc.object_id
WHERE c.object_id = OBJECT_ID(N'[dbo].[pedido_confirmacion_rayo]')
ORDER BY c.column_id;
GO

-- Verificar tabla de detalle
PRINT '';
PRINT '📋 Estructura de pedido_confirmacion_rayo_detalle:';
SELECT 
    c.name AS column_name,
    t.name AS data_type,
    c.max_length,
    c.is_nullable,
    CASE WHEN dc.definition IS NOT NULL THEN dc.definition ELSE 'Sin default' END AS default_value
FROM sys.columns c
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
LEFT JOIN sys.default_constraints dc ON c.default_object_id = dc.object_id
WHERE c.object_id = OBJECT_ID(N'[dbo].[pedido_confirmacion_rayo_detalle]')
ORDER BY c.column_id;
GO

PRINT '';
PRINT '✅ Verificación de tablas completada.';
GO
