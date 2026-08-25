-- ============================================================================
-- Migración: Retirar el correo "Pedido Eliminado" del catálogo (MABEL_TRADING)
-- ============================================================================
-- Descripción: Este tipo de correo correspondía al endpoint DELETE
--              /api/pedidos/{pedido_id}/eliminar (botón "Eliminar Pedido" en
--              Detalle del Pedido), que borraba el pedido físicamente y
--              notificaba a MABEL TRADING por correo
--              (send_pedido_eliminado_mabel_notification). Ese endpoint fue
--              retirado y reemplazado por POST
--              /api/pedidos/{pedido_id}/cancelar-por-el-rayo en el commit
--              "cancelar pedido" (2026-02-12): ya no borra el pedido, cambia
--              su estado a CANCELADO POR EL RAYO (20) y solo notifica en
--              tiempo real (sin correo). La fila del catálogo quedó
--              fosilizada al sembrarse en create_notificacion_tipo_correo.sql
--              (2026-08-13) a partir del código de email_notifier.py sin
--              detectar que esa función ya no la llamaba ningún endpoint.
--              Se elimina la fila y, por si algún admin llegó a configurar un
--              destinatario para ella, también sus filas en
--              notificacion_persona_correo (FK_notificacion_persona_correo_tipo_correo).
-- Fecha: 2026-08-14
-- ============================================================================

PRINT '🔧 Iniciando migración: retirar correo "Pedido Eliminado" (MABEL_TRADING) del catálogo';
GO

DECLARE @tipo_correo_id INT;
SELECT @tipo_correo_id = id
FROM notificacion_tipo_correo
WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Pedido Eliminado';

IF @tipo_correo_id IS NOT NULL
BEGIN
    DELETE FROM notificacion_persona_correo WHERE tipo_correo_id = @tipo_correo_id;
    DELETE FROM notificacion_tipo_correo WHERE id = @tipo_correo_id;
    PRINT '✅ Correo "Pedido Eliminado" (MABEL_TRADING) retirado del catálogo';
END
ELSE
BEGIN
    PRINT '✓ El correo "Pedido Eliminado" (MABEL_TRADING) ya no existe en el catálogo';
END
GO
