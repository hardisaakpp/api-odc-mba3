-- ============================================================================
-- Migración: Crear tabla notificacion_destinatarios
-- Descripción: Configuración de destinatarios por tipo de notificación por email.
--              Sustituye listas fijas en .env; .env sigue como fallback si la tabla
--              está vacía o no existe.
-- Fecha: 2026-02-23
-- ============================================================================
-- Tipos de notificación (códigos):
--   OPERACIONES     -> El Rayo / Operaciones (despachos, ODC, cancelaciones, etc.)
--   MABEL_TRADING   -> MABEL TRADING (confirmaciones, redistribución, etc.)
--   HOMOLOGACIONES  -> Homologaciones (productos no homologados)
--   TECNICOS       -> Soporte técnico (errores, advertencias del sistema)
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'notificacion_destinatarios')
BEGIN
    CREATE TABLE notificacion_destinatarios (
        id INT IDENTITY(1,1) PRIMARY KEY,
        tipo_notificacion NVARCHAR(50) NOT NULL,
        email NVARCHAR(255) NOT NULL,
        activo BIT NOT NULL DEFAULT 1,
        creado_fecha DATETIME2 NOT NULL DEFAULT GETDATE(),
        modificado_fecha DATETIME2 NULL,
        creado_por NVARCHAR(255) NULL,
        modificado_por NVARCHAR(255) NULL
    );

    CREATE INDEX IX_notificacion_destinatarios_tipo_activo
        ON notificacion_destinatarios(tipo_notificacion, activo);

    PRINT 'Tabla notificacion_destinatarios creada correctamente.';
END
ELSE
BEGIN
    PRINT 'Tabla notificacion_destinatarios ya existe.';
END
GO

-- Para migrar desde .env: insertar filas con los valores actuales, por ejemplo:
-- INSERT INTO notificacion_destinatarios (tipo_notificacion, email, activo) VALUES
--   ('OPERACIONES', 'user1@empresa.com', 1),
--   ('OPERACIONES', 'user2@empresa.com', 1),
--   ('MABEL_TRADING', 'mabel@empresa.com', 1),
--   ('HOMOLOGACIONES', 'homologaciones@empresa.com', 1),
--   ('TECNICOS', 'soporte@empresa.com', 1);
