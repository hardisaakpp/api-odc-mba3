-- ============================================================================
-- Script SQL para configurar el servidor vinculado a SAP HANA
-- ============================================================================
-- Este script configura un servidor vinculado en SQL Server para poder
-- ejecutar consultas OPENQUERY hacia SAP HANA.
-- ============================================================================
-- IMPORTANTE: Ajusta los valores según tu configuración:
--   - @server: Nombre del servidor vinculado (debe coincidir con SAP_LINKED_SERVER en .env)
--   - @srvproduct: Tipo de servidor (HANA, SQL Server, etc.)
--   - @provider: Proveedor OLE DB
--   - @datasrc: IP o nombre del servidor SAP HANA (ej: 10.10.100.12)
--   - @catalog: Base de datos de SAP (ej: SBO_MABEL_PROD)
--   - @location: Ubicación del servidor (opcional)
--   - @provstr: String de conexión adicional
-- ============================================================================

USE master;
GO

-- Variables de configuración (AJUSTA ESTOS VALORES)
DECLARE @server NVARCHAR(128) = N'MYHANADB';  -- Nombre del servidor vinculado
DECLARE @srvproduct NVARCHAR(128) = N'HANA';   -- Tipo de servidor
DECLARE @provider NVARCHAR(128) = N'MSDASQL';  -- Proveedor OLE DB (MSDASQL para ODBC)
DECLARE @datasrc NVARCHAR(4000) = N'10.10.100.12';  -- IP del servidor SAP HANA
DECLARE @catalog NVARCHAR(128) = N'SBO_MABEL_PROD';  -- Base de datos de SAP
DECLARE @location NVARCHAR(4000) = NULL;
DECLARE @provstr NVARCHAR(4000) = NULL;

-- Verificar si el servidor vinculado ya existe
IF EXISTS (SELECT * FROM sys.servers WHERE name = @server)
BEGIN
    PRINT 'Servidor vinculado ' + @server + ' ya existe. Eliminando...';
    EXEC sp_dropserver @server, 'droplogins';
END
GO

-- Crear el servidor vinculado
-- Opción 1: Para SAP HANA usando ODBC (MSDASQL)
-- Nota: Requiere que tengas un DSN ODBC configurado para SAP HANA

PRINT 'Creando servidor vinculado ' + @server + '...';

EXEC sp_addlinkedserver
    @server = @server,
    @srvproduct = @srvproduct,
    @provider = @provider,
    @datasrc = @datasrc,
    @catalog = @catalog,
    @location = @location,
    @provstr = @provstr;

-- Configurar opciones del servidor vinculado
EXEC sp_serveroption @server, 'rpc', 'true';
EXEC sp_serveroption @server, 'rpc out', 'true';
EXEC sp_serveroption @server, 'use remote collation', 'false';
EXEC sp_serveroption @server, 'collation compatible', 'false';
EXEC sp_serveroption @server, 'connect timeout', '30';
EXEC sp_serveroption @server, 'query timeout', '30';

-- Configurar mapeo de login (usar las credenciales de Windows o SQL Server)
-- Opción A: Usar credenciales de Windows (Trusted Connection)
EXEC sp_addlinkedsrvlogin 
    @rmtsrvname = @server,
    @useself = 'true',  -- Usa las credenciales del usuario actual
    @locallogin = NULL,
    @rmtuser = NULL,
    @rmtpassword = NULL;

-- Opción B: Usar credenciales específicas (descomenta y ajusta si es necesario)
-- EXEC sp_addlinkedsrvlogin 
--     @rmtsrvname = @server,
--     @useself = 'false',
--     @locallogin = NULL,
--     @rmtuser = 'tu_usuario_sap',
--     @rmtpassword = 'tu_contraseña_sap';

PRINT 'Servidor vinculado ' + @server + ' configurado exitosamente.';
GO

-- Verificar la configuración
SELECT 
    name AS ServerName,
    product AS Product,
    provider AS Provider,
    data_source AS DataSource,
    catalog AS Catalog,
    is_linked AS IsLinked
FROM sys.servers
WHERE name = 'MYHANADB';
GO

-- Probar la conexión (opcional - descomenta para probar)
-- SELECT * FROM OPENQUERY([MYHANADB], 'SELECT 1 AS Test');
-- GO

PRINT 'Script completado.';
PRINT '';
PRINT 'NOTAS:';
PRINT '1. Si usas autenticación específica, ajusta sp_addlinkedsrvlogin arriba';
PRINT '2. Verifica que el DSN ODBC para SAP HANA esté configurado';
PRINT '3. Prueba la conexión con: SELECT * FROM OPENQUERY([MYHANADB], ''SELECT 1 AS Test'');';
GO

