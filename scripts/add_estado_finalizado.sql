-- ============================================================================
-- Añadir estado "FINALIZADO" (id 18) a pedido_estado
-- ============================================================================
-- Estado final del flujo. Solo se puede asignar desde "Despachar y Facturar"
-- (estado_id 17), mediante el botón "Finalizado" en la interfaz
-- cargar-plantilla (solo para la plantilla P-12.01 - 12 - 2025).
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM [dbo].[pedido_estado] WHERE id = 18)
BEGIN
    INSERT INTO [dbo].[pedido_estado] (id, nombre, orden, activo) VALUES
        (18, N'FINALIZADO', 18, 1);
    PRINT 'Estado id=18 FINALIZADO insertado.';
END
ELSE
BEGIN
    PRINT 'Estado id=18 ya existe.';
END
GO
