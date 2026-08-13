-- ============================================================================
-- Script de Migración: Excluir a nvelasquez@elrayo.com.ec del correo
-- "Redistribución Confirmada por MABEL TRADING"
-- ============================================================================
-- Descripción: Nicole Velasquez (El Rayo) solicitó dejar de recibir
--              específicamente el correo de confirmación de redistribución
--              (evento REDISTRIBUCION_CONFIRMADA, tipo OPERACIONES). Se
--              mantiene como destinataria del resto de notificaciones de
--              OPERACIONES (pedido cancelado, pedido descartado, plantilla
--              procesada, despachos).
--
--              Requiere que la columna codigo_evento ya exista (ver
--              add_codigo_evento_notificacion_destinatarios.sql).
-- Solicitado por: Nicole Velasquez (nvelasquez@elrayo.com.ec), 2026-08-12.
-- Fecha: 2026-08-12
-- ============================================================================

PRINT '🔧 Iniciando migración: Excluir nvelasquez@elrayo.com.ec de REDISTRIBUCION_CONFIRMADA';
GO

IF NOT EXISTS (
    SELECT 1 FROM [dbo].[notificacion_destinatarios]
    WHERE tipo_notificacion = 'OPERACIONES'
      AND codigo_evento = 'REDISTRIBUCION_CONFIRMADA'
      AND email = 'nvelasquez@elrayo.com.ec'
)
BEGIN
    PRINT '➕ Agregando exclusión para nvelasquez@elrayo.com.ec...';

    INSERT INTO [dbo].[notificacion_destinatarios]
        (tipo_notificacion, email, codigo_evento, activo, creado_por)
    VALUES
        ('OPERACIONES', 'nvelasquez@elrayo.com.ec', 'REDISTRIBUCION_CONFIRMADA', 0, 'solicitud_nicole_velasquez_2026-08-12');

    PRINT '✅ Exclusión agregada exitosamente.';
END
ELSE
BEGIN
    PRINT '✓ La exclusión ya existía.';
END
GO

PRINT '';
PRINT '📋 Exclusiones activas para REDISTRIBUCION_CONFIRMADA:';
SELECT tipo_notificacion, email, codigo_evento, activo, creado_fecha, creado_por
FROM [dbo].[notificacion_destinatarios]
WHERE codigo_evento = 'REDISTRIBUCION_CONFIRMADA';

PRINT '';
PRINT '✅ Migración completada: exclusión de nvelasquez@elrayo.com.ec en REDISTRIBUCION_CONFIRMADA';
GO
