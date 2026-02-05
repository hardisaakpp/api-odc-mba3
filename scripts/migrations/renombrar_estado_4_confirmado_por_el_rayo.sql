-- ============================================================================
-- Migración: Renombrar estado id=4 de "CONFIRMADO" a "CONFIRMADO POR EL RAYO"
-- Fecha: 2025-02-05
-- Descripción: Cambia el nombre del estado para clarificar que fue confirmado
--              por EL RAYO (proveedor)
-- ============================================================================

-- Verificar estado actual
SELECT id, nombre, orden, activo 
FROM [dbo].[pedido_estado] 
WHERE id = 4;

-- Actualizar el nombre del estado
UPDATE [dbo].[pedido_estado] 
SET nombre = N'CONFIRMADO POR EL RAYO' 
WHERE id = 4;

PRINT '✅ Estado id=4 renombrado de "CONFIRMADO" a "CONFIRMADO POR EL RAYO".';

-- Verificar cambio
SELECT id, nombre, orden, activo 
FROM [dbo].[pedido_estado] 
WHERE id = 4;

-- ============================================================================
-- Notas:
-- - Este cambio afecta SOLO la presentación/nombre del estado
-- - El estado_id (4) permanece igual, no afecta la lógica del sistema
-- - La constante ESTADO_REDISTRIBUCION = 4 sigue funcionando igual
-- - El cambio se reflejará automáticamente en todas las interfaces
-- ============================================================================
