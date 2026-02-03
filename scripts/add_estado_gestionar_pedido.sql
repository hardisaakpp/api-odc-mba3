-- ============================================================================
-- Agregar estado GESTIONAR PEDIDO (id=16)
-- ============================================================================
-- Se usa cuando el usuario hace clic en "Ver Detalle" desde la tabla Pedidos.
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM [dbo].[pedido_estado] WHERE id = 16)
BEGIN
    INSERT INTO [dbo].[pedido_estado] (id, nombre, orden, activo) VALUES
        (16, N'GESTIONAR PEDIDO', 16, 1);
    PRINT 'Estado GESTIONAR PEDIDO (id=16) insertado.';
END
ELSE
    PRINT 'Estado id=16 ya existe.';
GO
