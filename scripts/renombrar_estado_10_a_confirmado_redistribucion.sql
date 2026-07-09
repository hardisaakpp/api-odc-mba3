-- ============================================================================
-- Renombrar estado id=10 de PEDIDO_CONFIRMADO a CONFIRMADO REDISTRIBUCION
-- ============================================================================
-- El nombre es solo presentación; la API lee estado_nombre desde pedido_estado.
-- Ejecutar contra la base de datos donde está la tabla pedido_estado.
-- ============================================================================

UPDATE [dbo].[pedido_estado] SET nombre = N'CONFIRMADO REDISTRIBUCION' WHERE id = 10;
PRINT 'Estado id=10 renombrado a CONFIRMADO REDISTRIBUCION.';
