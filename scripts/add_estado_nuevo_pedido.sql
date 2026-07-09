-- ============================================================================
-- Renombrar estado para mostrar "NUEVO PEDIDO" en la UI
-- ============================================================================
-- Sin renumerar ni insertar filas: solo se actualiza el nombre del estado
-- con id = 2 para que al leer desde la BD se muestre "NUEVO PEDIDO" y no
-- confunda al usuario (antes podía mostrarse como RESPUESTA_PROVEEDOR_CARGADA).
-- ============================================================================

UPDATE [dbo].[pedido_estado]
SET nombre = N'NUEVO PEDIDO'
WHERE id = 2;

PRINT 'Estado id=2 actualizado a nombre ''NUEVO PEDIDO''.';
GO
