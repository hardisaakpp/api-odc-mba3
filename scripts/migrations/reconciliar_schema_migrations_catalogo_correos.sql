-- ============================================================================
-- Migración: Reconciliar schema_migrations con el catálogo de correos (624-632)
-- ============================================================================
-- Descripción: Las migraciones 624-632 (familia del catálogo de correos:
--              notificacion_tipo_correo / notificacion_persona_correo) se
--              ejecutaron manualmente (SSMS/sqlcmd) en distintos momentos sin
--              pasar por scripts/migration_runner.py, así que la tabla de
--              control schema_migrations no refleja su estado real.
--
--              Esta migración NO modifica datos de negocio: por cada versión
--              de esa familia, solo inserta su fila en schema_migrations si
--              puede verificar en el propio esquema/datos de este ambiente
--              que esa migración específica ya surtió efecto (tabla/columna/
--              fila existente). Si la evidencia no está, no inserta nada y
--              queda pendiente para que migration_runner.py la aplique de
--              forma normal.
--
--              Es seguro correr este script en cualquier ambiente (dev/test/
--              prod) sin conocer de antemano su estado: es idempotente
--              (repetirlo no duplica nada) y nunca marca como aplicada una
--              migración cuyo efecto no pueda comprobar en ese ambiente. Las
--              versiones 626 (seed persona/correo), 629 (correos legacy de
--              pedido), 630 (drop tabla legacy) y 631 (fix descripción
--              Pedido Descartado) no se reconcilian aquí: quedaron
--              genuinamente pendientes al momento de escribir este script
--              (verificado 2026-08-14) y deben aplicarse con
--              migration_runner.py, no solo registrarse.
-- Fecha: 2026-08-14
-- ============================================================================

PRINT '🔧 Reconciliando schema_migrations con el catálogo de correos (624-632)';
GO

-- 624: create_notificacion_tipo_correo
IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '624')
BEGIN
    IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'notificacion_tipo_correo')
    BEGIN
        INSERT INTO schema_migrations (version, name, applied_at, checksum, applied_by)
            VALUES ('624', 'create_notificacion_tipo_correo', GETDATE(),
                    'd511f6dc2fe6d14dbfc1d2d6d1f996a11698396be37cfb7aa7057483cd3f377b',
                    'reconciliacion_2026-08-14');
        PRINT '✅ 624 marcada como aplicada (tabla notificacion_tipo_correo existe)';
    END
    ELSE
        PRINT '⏳ 624 sigue pendiente: falta la tabla notificacion_tipo_correo';
END
GO

-- 625: create_notificacion_persona_correo
IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '625')
BEGIN
    IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'notificacion_persona_correo')
    BEGIN
        INSERT INTO schema_migrations (version, name, applied_at, checksum, applied_by)
            VALUES ('625', 'create_notificacion_persona_correo', GETDATE(),
                    '0ed1d5fe46de55fc9fc5f6d3e7e7978c6746b20e69ab047f3d4e998ad8f05c9a',
                    'reconciliacion_2026-08-14');
        PRINT '✅ 625 marcada como aplicada (tabla notificacion_persona_correo existe)';
    END
    ELSE
        PRINT '⏳ 625 sigue pendiente: falta la tabla notificacion_persona_correo';
END
GO

-- 626: seed_notificacion_persona_correo_desde_destinatarios
-- No se reconcilia automáticamente: la sola presencia de filas en
-- notificacion_persona_correo no prueba que el seed corrió (pueden ser altas
-- manuales desde el admin). Requiere revisión y, si corresponde, aplicarse
-- de verdad con migration_runner.py.
IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '626')
    PRINT '⏳ 626 sigue pendiente (no se puede verificar automáticamente; requiere revisión manual)';
GO

-- 627: add_fecha_facturacion_pedido
IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '627')
BEGIN
    IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('pedido') AND name = 'fecha_facturacion')
    BEGIN
        INSERT INTO schema_migrations (version, name, applied_at, checksum, applied_by)
            VALUES ('627', 'add_fecha_facturacion_pedido', GETDATE(),
                    '078eb19741da54c19032eb18802f9cfe1aac5a68de4c305375f25412f717ccc8',
                    'reconciliacion_2026-08-14');
        PRINT '✅ 627 marcada como aplicada (columna pedido.fecha_facturacion existe)';
    END
    ELSE
        PRINT '⏳ 627 sigue pendiente: falta la columna pedido.fecha_facturacion';
END
GO

-- 628: add_correo_pedido_confirmado_produccion
IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '628')
BEGIN
    IF EXISTS (
        SELECT 1 FROM notificacion_tipo_correo
        WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'Pedido Confirmado por Producción'
    )
    BEGIN
        INSERT INTO schema_migrations (version, name, applied_at, checksum, applied_by)
            VALUES ('628', 'add_correo_pedido_confirmado_produccion', GETDATE(),
                    '3f941c32b2e53cf217c6224362ce69fddad6bef5ca6fa039124bf3d1bdf69a20',
                    'reconciliacion_2026-08-14');
        PRINT '✅ 628 marcada como aplicada (correo "Pedido Confirmado por Producción" existe)';
    END
    ELSE
        PRINT '⏳ 628 sigue pendiente: falta el correo "Pedido Confirmado por Producción" en el catálogo';
END
GO

-- 629: add_correos_legacy_pedido_a_catalogo
-- Diagnóstico únicamente. Si esta migración no ha corrido y el código de
-- email_notifier_pedido.py ya usa get_destinatarios_por_correo (ya lo usa),
-- estos 3 correos no tienen destinatarios y no se están enviando.
IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '629')
BEGIN
    IF EXISTS (
        SELECT 1 FROM notificacion_tipo_correo
        WHERE tipo_correo IN (N'Pedido Confirmado por El Rayo', N'Pedido Despachar y Facturar', N'Pedido Finalizado')
    )
        PRINT '⚠️ 629 parece aplicada parcialmente: revisar manualmente antes de registrarla';
    ELSE
        PRINT '⏳ 629 sigue pendiente: faltan los 3 correos legacy de pedido en el catálogo (posible envío silencioso sin destinatarios)';
END
GO

-- 630: drop_notificacion_destinatarios
IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '630')
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'notificacion_destinatarios')
    BEGIN
        INSERT INTO schema_migrations (version, name, applied_at, applied_by)
            VALUES ('630', 'drop_notificacion_destinatarios', GETDATE(), 'reconciliacion_2026-08-14');
        PRINT '✅ 630 marcada como aplicada (tabla notificacion_destinatarios ya no existe)';
    END
    ELSE
        PRINT '⏳ 630 sigue pendiente: la tabla notificacion_destinatarios todavía existe';
END
GO

-- 631: fix_descripcion_correo_pedido_descartado
IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '631')
BEGIN
    IF EXISTS (
        SELECT 1 FROM notificacion_tipo_correo
        WHERE tipo_notificacion = 'OPERACIONES' AND tipo_correo = N'Pedido Descartado'
          AND descripcion = N'Se envía a El Rayo al descartar un pedido en estado Nuevo Pedido (Cargar Plantilla), o al cancelarlo desde Redistribución. Descartar en Borrador NO envía este correo: el pedido aún no se le había enviado a El Rayo/Producción'
    )
    BEGIN
        INSERT INTO schema_migrations (version, name, applied_at, applied_by)
            VALUES ('631', 'fix_descripcion_correo_pedido_descartado', GETDATE(), 'reconciliacion_2026-08-14');
        PRINT '✅ 631 marcada como aplicada (descripción de "Pedido Descartado" ya corregida)';
    END
    ELSE
        PRINT '⏳ 631 sigue pendiente: la descripción de "Pedido Descartado" todavía tiene el texto viejo';
END
GO

-- 632: drop_correo_pedido_eliminado
IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '632')
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM notificacion_tipo_correo
        WHERE tipo_notificacion = 'MABEL_TRADING' AND tipo_correo = N'Pedido Eliminado'
    )
    BEGIN
        INSERT INTO schema_migrations (version, name, applied_at, checksum, applied_by)
            VALUES ('632', 'drop_correo_pedido_eliminado', GETDATE(),
                    'bac5909720895649dde79f2f482b48314aa4e90696a75638537b59262ae30c12',
                    'reconciliacion_2026-08-14');
        PRINT '✅ 632 marcada como aplicada (correo "Pedido Eliminado" ya no existe en el catálogo)';
    END
    ELSE
        PRINT '⏳ 632 sigue pendiente: el correo "Pedido Eliminado" (MABEL_TRADING) todavía existe';
END
GO

PRINT '';
PRINT '✅ Reconciliación completada. Revisar los mensajes ⏳/⚠️ de arriba: esas versiones siguen genuinamente pendientes y deben aplicarse con migration_runner.py.';
GO
