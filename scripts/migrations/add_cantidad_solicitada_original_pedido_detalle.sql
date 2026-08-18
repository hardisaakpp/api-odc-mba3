-- ============================================================================
-- Migración: Agregar cantidad_solicitada_original a pedido_detalle
-- ============================================================================
-- Descripción: Req. 1.2 (Gestión de pedidos parciales). Hoy "total" en
--              pedido_detalle es una sola columna mutable que sobrescriben en
--              secuencia produccion-elrayo.view (GESTIONAR_PEDIDO) y
--              odcsap.view (CONFIRMADO_POR_PRODUCCION) vía
--              PATCH .../detalle/{id}/total — no queda registro de la
--              cantidad que Mabel Trading cargó originalmente en la plantilla
--              Excel. Se agrega cantidad_solicitada_original, escrita UNA SOLA
--              VEZ en el INSERT (PedidoDetalleRepository.insert) y que ningún
--              endpoint de edición posterior debe tocar. Permite calcular la
--              diferencia (solicitada - total actual) sin importar cuántas
--              veces se haya editado "Total" en el camino.
--              Filas existentes quedan en NULL: no se puede reconstruir el
--              original de un pedido cuyo "total" ya fue sobrescrito antes de
--              esta migración; la lógica de comparación debe tratar NULL como
--              "sin dato, no evaluar diferencia".
-- Fecha: 2026-08-17
-- ============================================================================

PRINT '🔧 Iniciando migración: agregar cantidad_solicitada_original a pedido_detalle';
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'pedido_detalle'
      AND COLUMN_NAME = 'cantidad_solicitada_original'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle]
        ADD cantidad_solicitada_original DECIMAL(18,4) NULL;
    PRINT '✅ Columna cantidad_solicitada_original agregada a pedido_detalle';
END
ELSE
    PRINT '⏭️ Columna cantidad_solicitada_original ya existe en pedido_detalle';
GO
