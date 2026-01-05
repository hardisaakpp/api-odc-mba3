-- Índice para optimizar consultas de último pedido por usuario
-- 
-- Este índice optimiza:
-- 1. WHERE creado_por = ? ORDER BY creado_en DESC (get_ultimo_pedido)
-- 2. Consultas de pedidos por usuario ordenados por fecha
--
-- Fecha: 2025-01-21
-- Autor: Sistema MBA3 Consultas

-- Verificar si el índice ya existe antes de crearlo
IF NOT EXISTS (
    SELECT 1 
    FROM sys.indexes 
    WHERE name = 'idx_pedido_usuario_fecha' 
    AND object_id = OBJECT_ID('pedido')
)
BEGIN
    CREATE NONCLUSTERED INDEX idx_pedido_usuario_fecha 
    ON pedido(creado_por, creado_en DESC)
    INCLUDE (pedido_id);
    
    PRINT '✅ Índice idx_pedido_usuario_fecha creado exitosamente';
END
ELSE
BEGIN
    PRINT 'ℹ️ El índice idx_pedido_usuario_fecha ya existe';
END
GO
