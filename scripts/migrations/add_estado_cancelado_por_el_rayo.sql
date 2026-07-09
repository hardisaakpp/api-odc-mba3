-- ============================================================================
-- Script de Migración: Agregar estado CANCELADO POR EL RAYO a pedido_estado
-- ============================================================================
-- Descripción: Agrega el estado CANCELADO POR EL RAYO (id=20) a la tabla
--              pedido_estado para que el frontend pueda mostrarlo en los
--              filtros de búsqueda y en la UI.
-- Fecha: 2026-02-12
-- ============================================================================

PRINT '🔧 Iniciando migración: Agregar estado CANCELADO POR EL RAYO';
GO

-- ============================================================================
-- Agregar estado CANCELADO POR EL RAYO si no existe
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [dbo].[pedido_estado] WHERE id = 20)
BEGIN
    PRINT '➕ Agregando estado CANCELADO POR EL RAYO (id=20)...';
    
    INSERT INTO [dbo].[pedido_estado] (id, nombre, orden, activo)
    VALUES (20, N'CANCELADO POR EL RAYO', 20, 1);
    
    PRINT '✅ Estado CANCELADO POR EL RAYO agregado exitosamente.';
END
ELSE
BEGIN
    PRINT '✓ El estado CANCELADO POR EL RAYO ya existe.';
END
GO

-- ============================================================================
-- Verificación
-- ============================================================================
PRINT '';
PRINT '📋 Estado CANCELADO POR EL RAYO:';
SELECT id, nombre, orden, activo 
FROM [dbo].[pedido_estado] 
WHERE id = 20;

PRINT '';
PRINT '✅ Migración completada: Estado CANCELADO POR EL RAYO agregado';
GO
