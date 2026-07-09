-- ============================================================================
-- Script para eliminar columna BODEGA de pedido_detalle
-- ============================================================================
-- Descripción: Elimina la columna bodega (INT) de pedido_detalle ya que 
--              quedó obsoleta. Las bodegas ahora se manejan a través de 
--              pedido_detalle_tienda con el campo es_bodega=True
-- Fecha: 2026-01-15
-- ============================================================================

-- Verificar si la columna existe antes de eliminarla
IF EXISTS (
    SELECT * 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'pedido_detalle' 
    AND COLUMN_NAME = 'bodega'
)
BEGIN
    ALTER TABLE pedido_detalle 
    DROP COLUMN bodega;
    
    PRINT '✅ Columna bodega eliminada exitosamente de pedido_detalle.';
END
ELSE
BEGIN
    PRINT '⚠️ La columna bodega no existe en pedido_detalle.';
END
GO

-- Verificar que la columna se eliminó correctamente
IF NOT EXISTS (
    SELECT * 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'pedido_detalle' 
    AND COLUMN_NAME = 'bodega'
)
BEGIN
    PRINT '✅ Verificación exitosa: columna bodega no existe en pedido_detalle.';
END
ELSE
BEGIN
    PRINT '❌ Error: la columna bodega aún existe en pedido_detalle.';
END
GO
