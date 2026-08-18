-- ============================================================================
-- Migración: Agregar rol_modificador a pedido_detalle_modificacion_columna
-- ============================================================================
-- Descripción: El resaltado de celdas TOTAL/COMENTARIO editadas en Detalle del
--              Pedido debe mostrar un color distinto según qué rol hizo la
--              última edición (morado = produccion-elrayo.view, ámbar =
--              odcsap.view), y ese color debe persistir sin importar quién esté
--              viendo la pantalla después. La tabla ya guarda modificado_por
--              (usuario) por celda vía MERGE, pero no el rol. Se agrega
--              rol_modificador (NULL = desconocido/histórico, sin backfill: no
--              se puede reconstruir en qué estado se hizo cada edición pasada).
--              El backend deriva el valor desde el estado del pedido al
--              guardar (GESTIONAR_PEDIDO -> PRODUCCION_ELRAYO,
--              CONFIRMADO_POR_PRODUCCION -> ODCSAP), no desde el permiso del
--              usuario. Ver src/endpoints/pedidos/pedidos_edicion.py.
-- Fecha: 2026-08-16
-- ============================================================================

PRINT '🔧 Iniciando migración: agregar rol_modificador a pedido_detalle_modificacion_columna';
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'pedido_detalle_modificacion_columna'
      AND COLUMN_NAME = 'rol_modificador'
)
BEGIN
    ALTER TABLE [dbo].[pedido_detalle_modificacion_columna]
        ADD rol_modificador NVARCHAR(30) NULL;
    PRINT '✅ Columna rol_modificador agregada a pedido_detalle_modificacion_columna';
END
ELSE
    PRINT '⏭️ Columna rol_modificador ya existe en pedido_detalle_modificacion_columna';
GO
