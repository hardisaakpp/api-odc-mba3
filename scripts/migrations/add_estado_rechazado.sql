-- ============================================================================
-- Script de Migración: Agregar estado RECHAZADO a pedido_estado
-- ============================================================================
-- Descripción: Agrega el estado RECHAZADO (id=24) a la tabla pedido_estado.
--              Botón "Rechazar" (ex "Cancelar Pedido Pospuesto") sobre un pedido
--              "hijo" en PRODUCCION POSPUESTA (22): Mabel Trading rechaza la
--              diferencia pospuesta en vez de esperar a que El Rayo la retome.
--              Terminal, igual que CANCELADO (19).
-- Fecha: 2026-08-19
-- ============================================================================

PRINT '🔧 Iniciando migración: Agregar estado RECHAZADO';
GO

IF NOT EXISTS (SELECT 1 FROM [dbo].[pedido_estado] WHERE id = 24)
BEGIN
    PRINT '➕ Agregando estado RECHAZADO (id=24)...';

    INSERT INTO [dbo].[pedido_estado] (id, nombre, orden, activo)
    VALUES (24, N'RECHAZADO', 24, 1);

    PRINT '✅ Estado RECHAZADO agregado exitosamente.';
END
ELSE
BEGIN
    PRINT '✓ El estado RECHAZADO ya existe.';
END
GO

PRINT '';
PRINT '📋 Estado RECHAZADO:';
SELECT id, nombre, orden, activo
FROM [dbo].[pedido_estado]
WHERE id = 24;

PRINT '';
PRINT '✅ Migración completada: Estado RECHAZADO agregado';
GO
