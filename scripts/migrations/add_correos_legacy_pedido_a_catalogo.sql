-- ============================================================================
-- Migración: Agregar al catálogo los correos de src/utils/email_notifier_pedido.py
-- ============================================================================
-- Descripción: Ese módulo quedó con un import roto (get_destinatarios_por_tipo,
--              eliminado por la migración 625/626) desde que el envío real se
--              trasladó a notificacion_persona_correo; los 3 correos que sigue
--              enviando (rayo-confirmación, despachar y facturar, finalizar
--              pedido) nunca llegaban a destino (excepción silenciada, ver
--              try/except "no crítico" en los endpoints que los disparan).
--              Se corrige el código para usar get_destinatarios_por_correo,
--              que requiere que el tipo_correo exista en este catálogo.
--              orden_flujo NULL: no hay un lugar seguro en la secuencia 1-9
--              existente sin renumerar entradas ya usadas (ver
--              create_notificacion_tipo_correo.sql).
-- Fecha: 2026-08-13
-- ============================================================================

PRINT '🔧 Iniciando migración: Agregar correos legacy de email_notifier_pedido.py al catálogo';
GO

IF NOT EXISTS (
    SELECT 1 FROM notificacion_tipo_correo
    WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Pedido Confirmado por El Rayo'
)
BEGIN
    INSERT INTO notificacion_tipo_correo (tipo_notificacion, tipo_correo, descripcion, orden_flujo, creado_por)
    VALUES ('MABEL_TRADING', N'Pedido Confirmado por El Rayo',
            N'Se envía a MABEL TRADING cuando El Rayo confirma un pedido (botón "Confirmar")',
            NULL, 'seed_legacy_pedido_2026-08-13');
    PRINT '✅ Correo "Pedido Confirmado por El Rayo" agregado.';
END
ELSE
BEGIN
    PRINT '✓ El correo "Pedido Confirmado por El Rayo" ya existe.';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM notificacion_tipo_correo
    WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Pedido Despachar y Facturar'
)
BEGIN
    INSERT INTO notificacion_tipo_correo (tipo_notificacion, tipo_correo, descripcion, orden_flujo, creado_por)
    VALUES ('MABEL_TRADING', N'Pedido Despachar y Facturar',
            N'Se envía a MABEL TRADING cuando El Rayo marca el pedido como Despachar y Facturar',
            NULL, 'seed_legacy_pedido_2026-08-13');
    PRINT '✅ Correo "Pedido Despachar y Facturar" agregado.';
END
ELSE
BEGIN
    PRINT '✓ El correo "Pedido Despachar y Facturar" ya existe.';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM notificacion_tipo_correo
    WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'Pedido Finalizado'
)
BEGIN
    INSERT INTO notificacion_tipo_correo (tipo_notificacion, tipo_correo, descripcion, orden_flujo, creado_por)
    VALUES ('OPERACIONES', N'Pedido Finalizado',
            N'Se envía a El Rayo cuando MABEL TRADING marca el pedido como Finalizado',
            NULL, 'seed_legacy_pedido_2026-08-13');
    PRINT '✅ Correo "Pedido Finalizado" agregado.';
END
ELSE
BEGIN
    PRINT '✓ El correo "Pedido Finalizado" ya existe.';
END
GO

PRINT '';
PRINT '✅ Migración completada: correos legacy de email_notifier_pedido.py en el catálogo';
GO
