-- ============================================================================
-- Migración: Retirar el correo "Diferencia en Pedido" del catálogo (MABEL_TRADING)
-- ============================================================================
-- Descripción: Este correo (migración 644, req. 1.2) se enviaba una vez por cada
--              pedido "hijo" generado en POST /api/pedidos/{pedido_id}/confirmar-con-
--              diferencia. Se decidió simplificar el flujo de notificaciones: los tres
--              casos de confirmación (Confirmar sin diferencia, Diferencia no será
--              entregada, Confirmar y generar N pedidos con la diferencia) ahora
--              reutilizan un solo correo, "Pedido Confirmado por El Rayo", enviado una
--              sola vez para el pedido padre -- en vez de un correo "Diferencia en
--              Pedido" separado por cada hijo. El endpoint ya no llama a
--              send_diferencia_pedido_notification desde 2026-08-24. Se elimina la fila
--              y, por si algún admin llegó a configurar un destinatario para ella,
--              también sus filas en notificacion_persona_correo
--              (FK_notificacion_persona_correo_tipo_correo). orden_flujo=12 queda
--              vacante (no se renumera, mismo criterio que las migraciones 632/634/
--              638/640).
-- Fecha: 2026-08-24
-- ============================================================================

PRINT '🔧 Iniciando migración: retirar correo "Diferencia en Pedido" (MABEL_TRADING) del catálogo';
GO

DECLARE @tipo_correo_id INT;
SELECT @tipo_correo_id = id
FROM notificacion_tipo_correo
WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Diferencia en Pedido';

IF @tipo_correo_id IS NOT NULL
BEGIN
    DELETE FROM notificacion_persona_correo WHERE tipo_correo_id = @tipo_correo_id;
    DELETE FROM notificacion_tipo_correo WHERE id = @tipo_correo_id;
    PRINT '✅ Correo "Diferencia en Pedido" (MABEL_TRADING) retirado del catálogo';
END
ELSE
BEGIN
    PRINT '✓ El correo "Diferencia en Pedido" (MABEL_TRADING) ya no existe en el catálogo';
END
GO
