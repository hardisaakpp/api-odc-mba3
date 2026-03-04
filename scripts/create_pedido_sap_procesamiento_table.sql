-- ============================================================================
-- Script SQL: Crear tabla para procesamiento SAP de pedidos (DETALLE)
-- ============================================================================
-- Descripción: Almacena información SAP procesada para cada producto del pedido
--              cuando MT confirma la redistribución. Similar a despacho_detalle
--              pero para pedidos (sin vínculo con MBA3).
-- 
-- NOTA: La cabecera se reutiliza de la tabla 'pedido' (no se modifica)
--       Solo se crea esta tabla de detalle para información SAP procesada.
-- Fecha: 2026-01-21
-- ============================================================================
-- Ejecuta en la base de datos actual (la de la conexión).
-- ============================================================================

-- ============================================================================
-- Tabla: pedido_sap_procesamiento_detalle
-- ============================================================================
-- Almacena información SAP procesada por producto del pedido
-- La cabecera se reutiliza de la tabla 'pedido' (no necesita tabla separada)
IF NOT EXISTS (
    SELECT * 
    FROM sys.objects 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_sap_procesamiento_detalle]') 
    AND type in (N'U')
)
BEGIN
    CREATE TABLE [dbo].[pedido_sap_procesamiento_detalle] (
        procesamiento_detalle_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        -- Referencias
        pedido_id UNIQUEIDENTIFIER NOT NULL,
        pedido_detalle_id UNIQUEIDENTIFIER NOT NULL,
        
        -- Información del producto
        descripcion_producto NVARCHAR(255) NULL,        -- Descripción del producto (desde pedido_detalle.descripcion_sap)
        
        -- Información SAP consultada
        item_code_sap NVARCHAR(50) NULL,              -- ItemCode de SAP
        pack_sap NVARCHAR(10) NULL,                   -- Pack SAP (X1, X2, X3, etc.)
        unidad_conversion DECIMAL(18, 4) NULL,       -- Factor de conversión
        unidad_sap NVARCHAR(10) NULL,                -- Unidad SAP
        
        -- Cantidades convertidas (suma total de todas las tiendas)
        cantidad_original DECIMAL(18, 4) NULL,       -- Total en docenas/unidades originales
        cantidad_sap DECIMAL(18, 4) NULL,           -- Total convertido a unidades SAP
        
        -- Precios convertidos
        precio_unitario_original DECIMAL(18, 4) NULL, -- Precio por unidad original
        precio_unitario_sap DECIMAL(18, 4) NULL,     -- Precio por unidad SAP
        total_linea_original DECIMAL(18, 2) NULL,   -- Total en unidades originales
        total_linea_sap DECIMAL(18, 2) NULL,         -- Total en unidades SAP
        
        -- Estado de homologación
        producto_homologado BIT DEFAULT 1,           -- Si el producto está homologado
        tipo_problema NVARCHAR(50) NULL,              -- 'no_existe', 'mismatch', 'error'
        item_code_sap_encontrado NVARCHAR(50) NULL,  -- ItemCode encontrado en SAP (para mismatch)
        mensaje_error NVARCHAR(500) NULL,            -- Mensaje de error si hubo problema
        
        -- Auditoría
        fecha_procesamiento DATETIME DEFAULT GETDATE(),
        procesado_por NVARCHAR(450) NULL,            -- User ID que procesó
        
        -- Constraints
        CONSTRAINT FK_pedido_sap_procesamiento_detalle_pedido 
            FOREIGN KEY (pedido_id) 
            REFERENCES pedido(pedido_id) 
            ON DELETE CASCADE,
        
        CONSTRAINT FK_pedido_sap_procesamiento_detalle_pedido_detalle 
            FOREIGN KEY (pedido_detalle_id) 
            REFERENCES pedido_detalle(pedido_detalle_id) 
            ON DELETE NO ACTION,
        
        -- Un solo procesamiento por producto (puede reprocesarse con UPDATE)
        CONSTRAINT UQ_pedido_sap_procesamiento_detalle_pedido_detalle 
            UNIQUE (pedido_detalle_id)
    );
    
    -- Índices para mejorar rendimiento
    CREATE INDEX idx_pedido_sap_procesamiento_detalle_pedido_id 
        ON pedido_sap_procesamiento_detalle(pedido_id);
    
    CREATE INDEX idx_pedido_sap_procesamiento_detalle_pedido_detalle_id 
        ON pedido_sap_procesamiento_detalle(pedido_detalle_id);
    
    CREATE INDEX idx_pedido_sap_procesamiento_detalle_homologado 
        ON pedido_sap_procesamiento_detalle(producto_homologado);
    
    CREATE INDEX idx_pedido_sap_procesamiento_detalle_fecha 
        ON pedido_sap_procesamiento_detalle(fecha_procesamiento DESC);
    
    -- Índice compuesto para búsquedas por pedido y homologación
    CREATE INDEX idx_pedido_sap_procesamiento_detalle_pedido_homologado 
        ON pedido_sap_procesamiento_detalle(pedido_id, producto_homologado);
    
    PRINT '✅ Tabla pedido_sap_procesamiento_detalle creada exitosamente.';
END
ELSE
BEGIN
    PRINT '⚠️ La tabla pedido_sap_procesamiento_detalle ya existe.';
END
GO

-- ============================================================================
-- Agregar columna descripcion_producto si no existe (para tablas existentes)
-- ============================================================================
IF EXISTS (
    SELECT * 
    FROM sys.objects 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_sap_procesamiento_detalle]') 
    AND type in (N'U')
)
BEGIN
    IF NOT EXISTS (
        SELECT * 
        FROM sys.columns 
        WHERE object_id = OBJECT_ID(N'[dbo].[pedido_sap_procesamiento_detalle]') 
        AND name = 'descripcion_producto'
    )
    BEGIN
        ALTER TABLE [dbo].[pedido_sap_procesamiento_detalle]
        ADD descripcion_producto NVARCHAR(255) NULL;
        
        PRINT '✅ Columna descripcion_producto agregada exitosamente.';
    END
    ELSE
    BEGIN
        PRINT '⚠️ La columna descripcion_producto ya existe.';
    END
END
GO

-- ============================================================================
-- Verificar que la tabla se creó correctamente
-- ============================================================================
PRINT '';
PRINT '📋 Estructura de pedido_sap_procesamiento_detalle:';
SELECT 
    c.name AS column_name,
    t.name AS data_type,
    c.max_length,
    c.is_nullable,
    CASE WHEN dc.definition IS NOT NULL THEN dc.definition ELSE 'Sin default' END AS default_value
FROM sys.columns c
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
LEFT JOIN sys.default_constraints dc ON c.default_object_id = dc.object_id
WHERE c.object_id = OBJECT_ID(N'[dbo].[pedido_sap_procesamiento_detalle]')
ORDER BY c.column_id;
GO

PRINT '';
PRINT '✅ Script de creación de tabla pedido_sap_procesamiento_detalle completado.';
PRINT '📝 NOTA: La cabecera se reutiliza de la tabla pedido (no se modifica).';
GO
