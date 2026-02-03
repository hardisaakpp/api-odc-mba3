-- ============================================================================
-- Añadir estado "DESPACHAR Y FACTURAR" (id 17) a pedido_estado
-- ============================================================================
-- Permite marcar manualmente un pedido en estado Confirmado y Enviado
-- (ODC enviada a SAP, solicitudes de transferencia generadas) como
-- "Despachar y Facturar" desde la interfaz de detalle del pedido.
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM [dbo].[pedido_estado] WHERE id = 17)
BEGIN
    INSERT INTO [dbo].[pedido_estado] (id, nombre, orden, activo) VALUES
        (17, N'DESPACHAR Y FACTURAR', 17, 1);
    PRINT 'Estado id=17 DESPACHAR Y FACTURAR insertado.';
END
ELSE
BEGIN
    PRINT 'Estado id=17 ya existe.';
END
GO
