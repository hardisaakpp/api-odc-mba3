-- ============================================================================
-- Migración: Eliminar tabla notificacion_destinatarios (legacy)
-- ============================================================================
-- Descripción: Tabla histórica ya sin efecto en el envío real de correos desde
--              la migración 626 (seed_notificacion_persona_correo_desde_destinatarios):
--              el envío real vive en notificacion_persona_correo +
--              notificacion_tipo_correo ("Personas y Correos" en el admin).
--              Se retira también la interfaz de administración "Destinatarios
--              por Tipo (histórico)" y sus endpoints/repositorio en el mismo
--              cambio (código, no BD).
--
--              Requiere que la migración 629 (add_correos_legacy_pedido_a_catalogo)
--              ya se haya aplicado: esa migración agrega al catálogo los 3
--              correos de email_notifier_pedido.py que todavía dependían de
--              esta tabla antes de que el código se migrara a
--              get_destinatarios_por_correo.
-- Fecha: 2026-08-13
-- ============================================================================

PRINT '🔧 Iniciando migración: Eliminar tabla notificacion_destinatarios';
GO

IF EXISTS (SELECT * FROM sys.tables WHERE name = 'notificacion_destinatarios')
BEGIN
    DROP TABLE notificacion_destinatarios;
    PRINT '✅ Tabla notificacion_destinatarios eliminada.';
END
ELSE
BEGIN
    PRINT '✓ La tabla notificacion_destinatarios ya no existe.';
END
GO

PRINT '';
PRINT '✅ Migración completada: notificacion_destinatarios eliminada';
GO
