-- ============================================================================
-- Renombrar estado id=4 de REDISTRIBUCION a CONFIRMADO
-- ============================================================================
-- Ejecutar en BD ya migrada. El nombre es solo presentación (pedido.estado
-- se actualiza en el próximo update_estado; la API lee desde pedido_estado).
-- ============================================================================

UPDATE [dbo].[pedido_estado] SET nombre = N'CONFIRMADO' WHERE id = 4;
PRINT 'Nombre id=4 actualizado a CONFIRMADO.';
GO
