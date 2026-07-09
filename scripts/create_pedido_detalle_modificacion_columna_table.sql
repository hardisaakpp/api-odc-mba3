-- ============================================================================
-- Script SQL: Crear tabla para modificaciones de columnas de pedido_detalle
-- ============================================================================
-- Descripción: Almacena un historial de modificaciones manuales de columnas
--              (costo_doc_sin_iva, total, comentario) con información de auditoría
-- Fecha: 2026-01-15
-- ============================================================================
-- Ejecuta en la base de datos actual (la de la conexión).
-- ============================================================================

-- Crear tabla si no existe
IF NOT EXISTS (
    SELECT * 
    FROM sys.objects 
    WHERE object_id = OBJECT_ID(N'[dbo].[pedido_detalle_modificacion_columna]') 
    AND type in (N'U')
)
BEGIN
    CREATE TABLE [dbo].[pedido_detalle_modificacion_columna] (
        modificacion_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        
        -- Referencia al detalle del pedido
        pedido_detalle_id UNIQUEIDENTIFIER NOT NULL,
        
        -- Columna modificada (costo_doc_sin_iva, total, comentario)
        columna_key NVARCHAR(50) NOT NULL,
        
        -- Auditoría
        modificado_por NVARCHAR(450) NULL,  -- User ID del JWT
        fecha_modificacion DATETIME DEFAULT GETDATE(),
        
        -- Constraints
        CONSTRAINT FK_pedido_detalle_modificacion_columna_detalle 
            FOREIGN KEY (pedido_detalle_id) 
            REFERENCES pedido_detalle(pedido_detalle_id) 
            ON DELETE CASCADE,
        
        -- Un detalle solo puede tener una modificación por columna (última modificación)
        CONSTRAINT UQ_pedido_detalle_modificacion_columna_detalle_columna 
            UNIQUE (pedido_detalle_id, columna_key),
        
        -- Validar que columna_key sea uno de los valores permitidos
        CONSTRAINT CK_pedido_detalle_modificacion_columna_columna_key 
            CHECK (columna_key IN ('costo_doc_sin_iva', 'total', 'comentario'))
    );
    
    -- Índices para mejorar rendimiento
    CREATE INDEX idx_pedido_detalle_modificacion_columna_detalle_id 
        ON pedido_detalle_modificacion_columna(pedido_detalle_id);
    
    CREATE INDEX idx_pedido_detalle_modificacion_columna_columna_key 
        ON pedido_detalle_modificacion_columna(columna_key);
    
    CREATE INDEX idx_pedido_detalle_modificacion_columna_fecha 
        ON pedido_detalle_modificacion_columna(fecha_modificacion DESC);
    
    -- Índice compuesto para búsquedas por detalle y columna
    CREATE INDEX idx_pedido_detalle_modificacion_columna_detalle_columna 
        ON pedido_detalle_modificacion_columna(pedido_detalle_id, columna_key);
    
    PRINT '✅ Tabla pedido_detalle_modificacion_columna creada exitosamente.';
END
ELSE
BEGIN
    PRINT '⚠️ La tabla pedido_detalle_modificacion_columna ya existe.';
END
GO

-- Verificar que la tabla se creó correctamente
SELECT 
    c.name AS column_name,
    t.name AS data_type,
    c.max_length,
    c.is_nullable,
    CASE WHEN dc.definition IS NOT NULL THEN dc.definition ELSE 'Sin default' END AS default_value
FROM sys.columns c
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
LEFT JOIN sys.default_constraints dc ON c.default_object_id = dc.object_id
WHERE c.object_id = OBJECT_ID(N'[dbo].[pedido_detalle_modificacion_columna]')
ORDER BY c.column_id;
GO

PRINT '✅ Verificación de tabla completada.';
GO
