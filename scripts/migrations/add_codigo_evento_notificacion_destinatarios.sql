-- ============================================================================
-- Script de Migración: Agregar codigo_evento a notificacion_destinatarios
-- ============================================================================
-- Descripción: Permite excluir un destinatario de un evento puntual (ej. solo
--              el correo "Redistribución Confirmada") sin sacarlo del resto
--              de notificaciones de su mismo tipo_notificacion (OPERACIONES,
--              MABEL_TRADING, HOMOLOGACIONES, TECNICOS).
--
--              Las filas existentes quedan con codigo_evento = NULL y siguen
--              aplicando a TODOS los eventos de su tipo, sin cambio de
--              comportamiento.
--
--              Para excluir un email de un evento puntual se inserta una fila:
--                tipo_notificacion = <mismo tipo>, email = <correo>,
--                codigo_evento = <código del evento>, activo = 0
--              Esa fila no agrega destinatarios, solo excluye al email de ese
--              codigo_evento específico (ver notificacion_destinatario_repository.py).
-- Fecha: 2026-08-12
-- ============================================================================

PRINT '🔧 Iniciando migración: Agregar codigo_evento a notificacion_destinatarios';
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.notificacion_destinatarios') AND name = 'codigo_evento'
)
BEGIN
    PRINT '➕ Agregando columna codigo_evento...';

    ALTER TABLE [dbo].[notificacion_destinatarios]
        ADD codigo_evento NVARCHAR(100) NULL;

    PRINT '✅ Columna codigo_evento agregada exitosamente.';
END
ELSE
BEGIN
    PRINT '✓ La columna codigo_evento ya existe.';
END
GO

PRINT '';
PRINT '✅ Migración completada: codigo_evento en notificacion_destinatarios';
GO
