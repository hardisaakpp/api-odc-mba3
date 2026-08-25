-- ============================================================================
-- Script de Migración: Agregar fecha_facturacion a pedido
-- ============================================================================
-- Descripción: Nuevo campo "Fecha Facturación" en el apartado "Información del
--              Pedido" (req. 1.8, perfil Producción El Rayo). En blanco por
--              defecto; el usuario elige la fecha libremente (sin default ni
--              cálculo automático). Editable únicamente cuando el pedido está
--              en estado GESTIONAR PEDIDO (estado_id = 3), vía
--              PUT /api/pedidos/{pedido_id} (mismo endpoint que fecha_pedido/
--              fecha_entrega).
-- Fecha: 2026-08-13
-- ============================================================================

PRINT '🔧 Iniciando migración: Agregar fecha_facturacion a pedido';
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.pedido') AND name = 'fecha_facturacion'
)
BEGIN
    PRINT '➕ Agregando columna fecha_facturacion...';

    ALTER TABLE [dbo].[pedido]
        ADD fecha_facturacion DATE NULL;

    PRINT '✅ Columna fecha_facturacion agregada exitosamente.';
END
ELSE
BEGIN
    PRINT '✓ La columna fecha_facturacion ya existe.';
END
GO

PRINT '';
PRINT '✅ Migración completada: fecha_facturacion en pedido';
GO
