-- ============================================================================
-- Tabla de control de migraciones
-- ============================================================================
-- Esta tabla rastrea qué migraciones se han aplicado y cuándo.
-- NO MODIFICAR MANUALMENTE - usar migration_runner.py
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[schema_migrations]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[schema_migrations] (
        version VARCHAR(50) NOT NULL PRIMARY KEY,
        name NVARCHAR(255) NOT NULL,
        applied_at DATETIME DEFAULT GETDATE(),
        execution_time_ms INT NULL,
        checksum VARCHAR(64) NULL,  -- SHA256 del contenido del script
        applied_by NVARCHAR(100) NULL  -- Usuario/entorno que aplicó
    );
    
    CREATE INDEX idx_schema_migrations_applied_at ON schema_migrations(applied_at);
    
    PRINT '✅ Tabla schema_migrations creada exitosamente.';
END
ELSE
BEGIN
    PRINT 'ℹ️ Tabla schema_migrations ya existe.';
END
GO

-- Registrar esta misma migración como aplicada
IF NOT EXISTS (SELECT 1 FROM [dbo].[schema_migrations] WHERE version = '000')
BEGIN
    INSERT INTO [dbo].[schema_migrations] (version, name, applied_at, applied_by)
    VALUES ('000', 'create_schema_migrations', GETDATE(), SYSTEM_USER);
    
    PRINT '✅ Migración 000 registrada.';
END
GO
