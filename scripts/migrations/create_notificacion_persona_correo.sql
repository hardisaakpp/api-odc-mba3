-- ============================================================================
-- Migración: Crear tabla notificacion_persona_correo
-- ============================================================================
-- Descripción: Vista de organización persona-céntrica: qué correos (de
--              notificacion_tipo_correo) debería recibir cada persona
--              (nombre + email), sin importar a qué tipo_notificacion
--              pertenece cada correo.
--
--              Es la fuente real de destinatarios del envío de correos, vía
--              src.utils.notificacion_destinatarios.get_destinatarios_por_correo
--              (usado por email_notifier.py). notificacion_destinatarios (por
--              tipo_notificacion, sin distinguir el correo específico) queda
--              como tabla histórica; sus destinatarios activos se migraron
--              aquí con seed_notificacion_persona_correo_desde_destinatarios.sql.
--
--              Una persona (email) puede tener varias filas, una por cada
--              correo al que está suscrita. nombre se repite en cada fila
--              (denormalizado), igual que el resto de tablas de este módulo.
-- Fecha: 2026-08-13
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'notificacion_persona_correo')
BEGIN
    CREATE TABLE notificacion_persona_correo (
        id INT IDENTITY(1,1) PRIMARY KEY,
        nombre NVARCHAR(255) NOT NULL,
        email NVARCHAR(255) NOT NULL,
        tipo_correo_id INT NOT NULL,
        creado_fecha DATETIME2 NOT NULL DEFAULT GETDATE(),
        creado_por NVARCHAR(255) NULL,
        CONSTRAINT FK_notificacion_persona_correo_tipo_correo
            FOREIGN KEY (tipo_correo_id) REFERENCES notificacion_tipo_correo(id)
            ON DELETE CASCADE,
        CONSTRAINT UQ_notificacion_persona_correo_email_tipo_correo
            UNIQUE (email, tipo_correo_id)
    );

    CREATE INDEX IX_notificacion_persona_correo_email
        ON notificacion_persona_correo(email);

    PRINT 'Tabla notificacion_persona_correo creada correctamente.';
END
ELSE
BEGIN
    PRINT 'Tabla notificacion_persona_correo ya existe.';
END
GO
