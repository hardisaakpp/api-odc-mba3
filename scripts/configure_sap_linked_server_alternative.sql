-- ============================================================================
-- Script SQL ALTERNATIVO para configurar servidor vinculado a SAP HANA
-- ============================================================================
-- Esta versión usa el proveedor SAP HANA OLE DB directamente
-- Requiere tener instalado el driver SAP HANA ODBC/OLE DB
-- ============================================================================

USE master;
GO

-- Variables de configuración
DECLARE @server NVARCHAR(128) = N'MYHANADB';
DECLARE @datasrc NVARCHAR(4000) = N'10.10.100.12:30015';  -- IP:Puerto de SAP HANA
DECLARE @catalog NVARCHAR(128) = N'SBO_MABEL_PROD';

-- Eliminar si existe
IF EXISTS (SELECT * FROM sys.servers WHERE name = @server)
BEGIN
    EXEC sp_dropserver @server, 'droplogins';
END
GO

-- Crear servidor vinculado con proveedor SAP HANA
-- Opción 2: Usando proveedor SAP HANA OLE DB (si está instalado)
EXEC sp_addlinkedserver
    @server = @server,
    @srvproduct = N'HANA',
    @provider = N'HDBODBC',  -- Proveedor SAP HANA ODBC
    @datasrc = @datasrc,
    @catalog = @catalog;

-- Configurar opciones
EXEC sp_serveroption @server, 'rpc', 'true';
EXEC sp_serveroption @server, 'rpc out', 'true';
EXEC sp_serveroption @server, 'connect timeout', '30';
EXEC sp_serveroption @server, 'query timeout', '30';

-- Configurar login (ajusta según tu configuración)
-- Opción A: Windows Authentication
EXEC sp_addlinkedsrvlogin 
    @rmtsrvname = @server,
    @useself = 'true',
    @locallogin = NULL,
    @rmtuser = NULL,
    @rmtpassword = NULL;

-- Opción B: Credenciales específicas (descomenta y ajusta)
-- EXEC sp_addlinkedsrvlogin 
--     @rmtsrvname = @server,
--     @useself = 'false',
--     @locallogin = NULL,
--     @rmtuser = 'SYSTEM',  -- Usuario SAP HANA
--     @rmtpassword = 'tu_contraseña';

PRINT 'Servidor vinculado configurado.';
GO

-- Verificar
SELECT * FROM sys.servers WHERE name = 'MYHANADB';
GO

