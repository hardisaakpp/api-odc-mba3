-- ============================================================================
-- Migración: Sembrar notificacion_persona_correo desde notificacion_destinatarios
-- ============================================================================
-- Descripción: notificacion_persona_correo (persona -> correo específico del
--              catálogo) pasa a ser la fuente real de destinatarios del envío
--              de correos (ver src/utils/notificacion_destinatarios.py y
--              src/utils/email_notifier.py). notificacion_destinatarios (por
--              tipo_notificacion, sin distinguir el correo específico) queda
--              como tabla histórica.
--
--              Este script traslada cada destinatario base activo de
--              notificacion_destinatarios (codigo_evento IS NULL, activo=1) a
--              un vínculo persona->correo por cada correo activo del catálogo
--              que comparta su mismo tipo_notificacion, preservando el
--              comportamiento actual (quien hoy recibe todo OPERACIONES sigue
--              recibiendo cada correo de OPERACIONES).
--
--              Excepción respetada: nvelasquez@elrayo.com.ec tiene en
--              notificacion_destinatarios una exclusión puntual (codigo_evento
--              = 'REDISTRIBUCION_CONFIRMADA', activo=0) para no recibir
--              "Redistribución Confirmada por MABEL TRADING"; este script NO
--              crea ese vínculo específico para ella (ver el CASE de más
--              abajo). Es el único codigo_evento en uso hoy; si en el futuro
--              se agregan otros, hay que sumarlos al mismo CASE.
--
--              nombre se completa con el propio email (notificacion_destinatarios
--              no guarda nombres); el admin puede renombrar después desde la
--              pantalla "Personas y Correos".
--
--              Idempotente: el UNIQUE(email, tipo_correo_id) de
--              notificacion_persona_correo, sumado al NOT EXISTS, hace que
--              volver a correr este script no duplique vínculos.
-- Fecha: 2026-08-13
-- ============================================================================

INSERT INTO notificacion_persona_correo (nombre, email, tipo_correo_id, creado_por)
SELECT DISTINCT
    d.email,
    d.email,
    tc.id,
    'seed_persona_correo_desde_destinatarios_2026-08-13'
FROM notificacion_destinatarios d
INNER JOIN notificacion_tipo_correo tc
    ON tc.tipo_notificacion = d.tipo_notificacion AND tc.activo = 1
WHERE d.codigo_evento IS NULL
  AND d.activo = 1
  AND NOT EXISTS (
      SELECT 1 FROM notificacion_persona_correo pc
      WHERE pc.email = d.email AND pc.tipo_correo_id = tc.id
  )
  AND NOT EXISTS (
      -- Exclusión puntual por evento en notificacion_destinatarios (hoy solo
      -- existe REDISTRIBUCION_CONFIRMADA, para "Redistribución Confirmada por
      -- MABEL TRADING"): si existe, no se crea el vínculo a ese correo.
      SELECT 1 FROM notificacion_destinatarios dx
      WHERE dx.tipo_notificacion = d.tipo_notificacion
        AND dx.email = d.email
        AND dx.activo = 0
        AND dx.codigo_evento = CASE tc.tipo_correo
            WHEN N'Redistribución Confirmada por MABEL TRADING' THEN 'REDISTRIBUCION_CONFIRMADA'
            ELSE NULL
        END
  );

PRINT 'Vínculos persona-correo sembrados desde notificacion_destinatarios (idempotente).';
GO

PRINT '';
PRINT '📋 Resumen de notificacion_persona_correo tras el seed:';
SELECT tc.tipo_notificacion, tc.tipo_correo, COUNT(*) AS personas_vinculadas
FROM notificacion_persona_correo pc
INNER JOIN notificacion_tipo_correo tc ON tc.id = pc.tipo_correo_id
GROUP BY tc.tipo_notificacion, tc.tipo_correo
ORDER BY tc.tipo_notificacion, tc.tipo_correo;
GO
