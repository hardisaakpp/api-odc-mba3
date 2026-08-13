-- ============================================================================
-- Seed de datos de PRUEBA para notificacion_destinatarios — SOLO DESARROLLO
-- ============================================================================
-- NO ejecutar en producción. NO está registrado en migrations_manifest.yaml
-- a propósito: es data de prueba del equipo de desarrollo, no un cambio de
-- esquema ni una configuración real de negocio.
--
-- Objetivo: cubrir los 5 tipos de notificación con destinatarios internos del
-- equipo de desarrollo, para poder probar el envío de cada tipo de correo de
-- punta a punta en el ambiente local/dev.
--
--   MABEL_TRADING      -> cortiz@mabeltrading.com.ec
--   OPERACIONES        -> desarrollo1_ext@mabeltrading.com.ec
--   TECNICOS           -> dbravo@mabeltrading.com.ec
--   PRODUCCION_ELRAYO  -> dpalma@cosmec.com.ec
--   HOMOLOGACIONES     -> cortiz@mabeltrading.com.ec
--
-- También elimina la exclusión de nvelasquez@elrayo.com.ec para
-- REDISTRIBUCION_CONFIRMADA: en dev no se necesita (no es parte del equipo
-- de pruebas) y el correo base de OPERACIONES en dev ya no es el de ella.
-- Fecha: 2026-08-13
-- ============================================================================

DELETE FROM [dbo].[notificacion_destinatarios]
WHERE tipo_notificacion = 'OPERACIONES'
  AND codigo_evento = 'REDISTRIBUCION_CONFIRMADA'
  AND email = 'nvelasquez@elrayo.com.ec';

DELETE FROM [dbo].[notificacion_destinatarios]
WHERE tipo_notificacion IN ('MABEL_TRADING', 'OPERACIONES', 'TECNICOS', 'PRODUCCION_ELRAYO', 'HOMOLOGACIONES')
  AND codigo_evento IS NULL;

INSERT INTO [dbo].[notificacion_destinatarios]
    (tipo_notificacion, email, activo, creado_por)
VALUES
    ('MABEL_TRADING',     'cortiz@mabeltrading.com.ec',        1, 'seed_dev_2026-08-13'),
    ('OPERACIONES',       'desarrollo1_ext@mabeltrading.com.ec', 1, 'seed_dev_2026-08-13'),
    ('TECNICOS',          'dbravo@mabeltrading.com.ec',        1, 'seed_dev_2026-08-13'),
    ('PRODUCCION_ELRAYO', 'dpalma@cosmec.com.ec',              1, 'seed_dev_2026-08-13'),
    ('HOMOLOGACIONES',    'cortiz@mabeltrading.com.ec',        1, 'seed_dev_2026-08-13');

SELECT tipo_notificacion, email, codigo_evento, activo, creado_fecha, creado_por
FROM [dbo].[notificacion_destinatarios]
ORDER BY tipo_notificacion, id;
