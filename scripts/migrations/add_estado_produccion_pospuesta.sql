-- ============================================================================
-- Script de Migración: Agregar estado PRODUCCION POSPUESTA a pedido_estado
-- ============================================================================
-- Descripción: Agrega el estado PRODUCCION POSPUESTA (id=22) a la tabla
--              pedido_estado para que el frontend pueda mostrarlo en los
--              filtros de búsqueda y en la UI.
-- Fecha: 2026-08-12
-- ============================================================================

PRINT '🔧 Iniciando migración: Agregar estado PRODUCCION POSPUESTA';
GO

-- ============================================================================
-- Agregar estado PRODUCCION POSPUESTA si no existe
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM [dbo].[pedido_estado] WHERE id = 22)
BEGIN
    PRINT '➕ Agregando estado PRODUCCION POSPUESTA (id=22)...';
    
    INSERT INTO [dbo].[pedido_estado] (id, nombre, orden, activo)
    VALUES (22, N'PRODUCCION POSPUESTA', 22, 1);
    
    PRINT '✅ Estado PRODUCCION POSPUESTA agregado exitosamente.';
END
ELSE
BEGIN
    PRINT '✓ El estado PRODUCCION POSPUESTA ya existe.';
END
GO

-- ============================================================================
-- Verificación
-- ============================================================================
PRINT '';
PRINT '📋 Estado PRODUCCION POSPUESTA:';
SELECT id, nombre, orden, activo 
FROM [dbo].[pedido_estado] 
WHERE id = 22;

PRINT '';
PRINT '✅ Migración completada: Estado PRODUCCION POSPUESTA agregado';
GO
