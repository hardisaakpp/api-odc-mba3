-- ============================================================================
-- Migración: Agregar pedido_padre_id a pedido
-- ============================================================================
-- Descripción: Req. 1.2 (Gestión de pedidos parciales). Cuando Administración
--              El Rayo confirma un pedido con cantidades por debajo de lo
--              solicitado y elige generar un pedido nuevo con la diferencia
--              (numero_pedido = "<original>.01"), este campo enlaza ese
--              pedido "hijo" con el pedido original ("padre") para
--              trazabilidad. No se agrega una columna booleana aparte tipo
--              "es_parcial": se infiere con pedido_padre_id IS NOT NULL.
-- Fecha: 2026-08-17
-- ============================================================================

PRINT '🔧 Iniciando migración: agregar pedido_padre_id a pedido';
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'pedido'
      AND COLUMN_NAME = 'pedido_padre_id'
)
BEGIN
    ALTER TABLE [dbo].[pedido]
        ADD pedido_padre_id UNIQUEIDENTIFIER NULL;
    PRINT '✅ Columna pedido_padre_id agregada a pedido';
END
ELSE
    PRINT '⏭️ Columna pedido_padre_id ya existe en pedido';
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = 'FK_pedido_padre'
      AND parent_object_id = OBJECT_ID('dbo.pedido')
)
BEGIN
    ALTER TABLE [dbo].[pedido]
        ADD CONSTRAINT FK_pedido_padre
        FOREIGN KEY (pedido_padre_id) REFERENCES [dbo].[pedido](pedido_id);
    PRINT '✅ FK FK_pedido_padre creada';
END
ELSE
    PRINT '⏭️ FK FK_pedido_padre ya existe';
GO
