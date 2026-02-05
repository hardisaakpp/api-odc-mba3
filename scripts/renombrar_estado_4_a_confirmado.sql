-- ============================================================================
-- Renombrar estado id=4 de REDISTRIBUCION a CONFIRMADO POR EL RAYO
-- ============================================================================
-- Ejecutar en BD ya migrada. El nombre es solo presentación (pedido.estado
-- se actualiza en el próximo update_estado; la API lee desde pedido_estado).
-- NOTA: Actualizado 2025-02-05 - Nombre cambiado a "CONFIRMADO POR EL RAYO"
-- ============================================================================

UPDATE [dbo].[pedido_estado] SET nombre = N'CONFIRMADO POR EL RAYO' WHERE id = 4;
PRINT 'Nombre id=4 actualizado a CONFIRMADO POR EL RAYO.';
GO
