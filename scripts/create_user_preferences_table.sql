-- ============================================================================
-- Script SQL: Crear tabla UserPreferences
-- ============================================================================
-- Este script crea la tabla para almacenar preferencias de usuario por tabla
-- Ejecutar en la base de datos SQL Server configurada en el proyecto
--
-- Uso:
--   1. Conectarse a la base de datos SQL Server
--   2. Ejecutar este script completo
--   3. Verificar que la tabla se creó correctamente
-- ============================================================================

-- Crear tabla UserPreferences
IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[UserPreferences]') AND type in (N'U'))
BEGIN
    CREATE TABLE [dbo].[UserPreferences] (
        [Id] INT PRIMARY KEY IDENTITY(1,1),
        [UserId] NVARCHAR(450) NOT NULL,
        [TableId] NVARCHAR(100) NOT NULL,
        [VisibleColumns] NVARCHAR(MAX) NOT NULL,  -- JSON array: ["col1", "col2"]
        [ColumnOrder] NVARCHAR(MAX) NOT NULL,     -- JSON array: ["col1", "col2"]
        [Filters] NVARCHAR(MAX) NULL,              -- JSON object: {} o null
        [PageSize] INT NULL,                       -- Opcional
        [UpdatedAt] DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
        [CreatedAt] DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
        
        CONSTRAINT [UK_UserPreferences_UserTable] UNIQUE ([UserId], [TableId])
    );
    
    PRINT 'Tabla UserPreferences creada exitosamente.';
END
ELSE
BEGIN
    PRINT 'La tabla UserPreferences ya existe.';
END
GO

-- Crear índices para mejorar rendimiento
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_UserPreferences_UserId' AND object_id = OBJECT_ID('dbo.UserPreferences'))
BEGIN
    CREATE INDEX [IX_UserPreferences_UserId] ON [dbo].[UserPreferences]([UserId]);
    PRINT 'Índice IX_UserPreferences_UserId creado exitosamente.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_UserPreferences_TableId' AND object_id = OBJECT_ID('dbo.UserPreferences'))
BEGIN
    CREATE INDEX [IX_UserPreferences_TableId] ON [dbo].[UserPreferences]([TableId]);
    PRINT 'Índice IX_UserPreferences_TableId creado exitosamente.';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_UserPreferences_UpdatedAt' AND object_id = OBJECT_ID('dbo.UserPreferences'))
BEGIN
    CREATE INDEX [IX_UserPreferences_UpdatedAt] ON [dbo].[UserPreferences]([UpdatedAt] DESC);
    PRINT 'Índice IX_UserPreferences_UpdatedAt creado exitosamente.';
END
GO

-- Nota: La foreign key a Users se omite por ahora ya que puede que la tabla Users
-- no exista en esta base de datos o tenga un nombre diferente.
-- Si necesitas la foreign key, descomenta y ajusta según tu esquema:
--
-- IF EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[Users]') AND type in (N'U'))
-- BEGIN
--     ALTER TABLE [dbo].[UserPreferences]
--     ADD CONSTRAINT [FK_UserPreferences_Users] 
--     FOREIGN KEY ([UserId]) REFERENCES [dbo].[Users]([Id]);
--     PRINT 'Foreign key FK_UserPreferences_Users creada exitosamente.';
-- END
-- GO

PRINT 'Script completado. Verificar que todos los objetos se crearon correctamente.';
GO

