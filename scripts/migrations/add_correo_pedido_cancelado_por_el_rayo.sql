-- ============================================================================
-- Migración: Agregar correo "Pedido Cancelado por El Rayo" al catálogo (MABEL_TRADING)
-- ============================================================================
-- Descripción: Nuevo correo (req. 1.8 segunda fase): se envía a MABEL TRADING
--              cuando Administración El Rayo (odcsap.view) cancela un pedido
--              desde Detalle del Pedido (botón "Cancelar Pedido"), disponible
--              únicamente en estado CONFIRMADO POR PRODUCCION (23). Cambia el
--              estado del pedido a CANCELADO POR EL RAYO (20).
--
--              Ocupa el puesto orden_flujo = 3, la posición que dejó libre el
--              correo "Pedido Eliminado" (MABEL_TRADING) al retirarse del
--              catálogo en la migración 632 (drop_correo_pedido_eliminado):
--              esa migración solo borró la fila, sin renumerar el resto, así
--              que el puesto 3 quedó vacante. No se renumeran las demás
--              filas: se reutiliza directamente ese hueco.
-- Fecha: 2026-08-14
-- ============================================================================

PRINT '🔧 Iniciando migración: Agregar correo Pedido Cancelado por El Rayo';
GO

IF NOT EXISTS (
    SELECT 1 FROM notificacion_tipo_correo
    WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Pedido Cancelado por El Rayo'
)
BEGIN
    INSERT INTO notificacion_tipo_correo (tipo_notificacion, tipo_correo, descripcion, orden_flujo, creado_por)
    VALUES (
        'MABEL_TRADING',
        N'Pedido Cancelado por El Rayo',
        N'Se envía a MABEL TRADING cuando Administración El Rayo cancela un pedido desde Detalle del Pedido (botón "Cancelar Pedido"), disponible solo en estado Confirmado por Producción',
        3,
        'add_cancelado_por_el_rayo_2026-08-14'
    );

    PRINT '✅ Correo "Pedido Cancelado por El Rayo" agregado en orden_flujo = 3.';
END
ELSE
BEGIN
    PRINT '✓ El correo "Pedido Cancelado por El Rayo" ya existe.';
END
GO

PRINT '';
PRINT '✅ Migración completada: correo Pedido Cancelado por El Rayo';
GO
