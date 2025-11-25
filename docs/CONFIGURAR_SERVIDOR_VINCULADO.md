# Configurar Servidor Vinculado para SAP

Este documento explica cómo configurar el servidor vinculado en SQL Server para poder consultar SAP HANA usando `OPENQUERY`.

## 🔴 Error Común

Si ves este error:
```
Could not find server 'MYHANADB' in sys.servers. 
Verify that the correct server name was specified.
```

Significa que el servidor vinculado no está configurado en SQL Server.

## 📋 Requisitos Previos

1. **SQL Server Management Studio (SSMS)** instalado
2. **Driver ODBC para SAP HANA** instalado (o driver OLE DB)
3. **Acceso al servidor SAP HANA** (IP: 10.10.100.12 según tu configuración)
4. **Credenciales** para conectarse a SAP HANA

## 🔧 Método 1: Script SQL (Recomendado)

### Paso 1: Abrir SQL Server Management Studio

1. Conéctate a tu instancia de SQL Server
2. Abre una nueva consulta

### Paso 2: Ejecutar Script

Ejecuta el script `scripts/configure_sap_linked_server.sql`:

```sql
-- Ajusta estos valores según tu configuración
DECLARE @server NVARCHAR(128) = N'MYHANADB';
DECLARE @datasrc NVARCHAR(4000) = N'10.10.100.12';  -- Tu IP de SAP
DECLARE @catalog NVARCHAR(128) = N'SBO_MABEL_PROD';  -- Tu base de datos
```

### Paso 3: Configurar Autenticación

**Opción A: Windows Authentication (si SAP acepta Windows Auth)**
```sql
EXEC sp_addlinkedsrvlogin 
    @rmtsrvname = 'MYHANADB',
    @useself = 'true',
    @locallogin = NULL,
    @rmtuser = NULL,
    @rmtpassword = NULL;
```

**Opción B: Credenciales Específicas**
```sql
EXEC sp_addlinkedsrvlogin 
    @rmtsrvname = 'MYHANADB',
    @useself = 'false',
    @locallogin = NULL,
    @rmtuser = 'SYSTEM',  -- Usuario SAP
    @rmtpassword = 'tu_contraseña';
```

### Paso 4: Verificar

```sql
-- Ver servidores vinculados
SELECT * FROM sys.servers WHERE name = 'MYHANADB';

-- Probar conexión
SELECT * FROM OPENQUERY([MYHANADB], 'SELECT 1 AS Test');
```

## 🔧 Método 2: Interfaz Gráfica (SSMS)

### Paso 1: Abrir Servidores Vinculados

1. En SSMS, expande **Server Objects**
2. Click derecho en **Linked Servers**
3. Selecciona **New Linked Server...**

### Paso 2: Configurar General

- **Linked server**: `MYHANADB`
- **Server type**: 
  - Selecciona **Other data source**
  - **Provider**: `Microsoft OLE DB Provider for ODBC Drivers` (o el driver SAP HANA)
  - **Product name**: `HANA`
  - **Data source**: `10.10.100.12` (tu IP de SAP)
  - **Catalog**: `SBO_MABEL_PROD` (tu base de datos)

### Paso 3: Configurar Security

1. Click en **Security**
2. Selecciona una de estas opciones:

   **Opción A: Mapear a credenciales locales**
   - Selecciona **Be made using this security context**
   - Ingresa:
     - **Remote login**: Usuario SAP
     - **With password**: Contraseña SAP

   **Opción B: Usar credenciales de Windows**
   - Selecciona **Be made using the login's current security context**

### Paso 4: Configurar Server Options

1. Click en **Server Options**
2. Habilita:
   - ✅ **RPC**: `True`
   - ✅ **RPC Out**: `True`
   - **Connect timeout**: `30`
   - **Query timeout**: `30`

3. Click **OK**

## 🧪 Probar la Configuración

### Desde SQL Server Management Studio

```sql
-- Probar conexión básica
SELECT * FROM OPENQUERY([MYHANADB], 'SELECT 1 AS Test');

-- Probar consulta a tabla SAP
SELECT * FROM OPENQUERY([MYHANADB], '
    SELECT TOP 5 
        "ItemCode",
        "ItemName",
        "U_IXX_PACK"
    FROM "SBO_MABEL_PROD"."OITM"
');
```

### Desde Python (Script de Prueba)

```bash
python scripts/test_sap_query.py --test client --sku "5-0012.9"
```

### Desde la API

```
GET http://localhost:8000/sap/test?sku=5-0012.9
```

## ⚠️ Problemas Comunes

### Error: "Provider is not registered"

**Solución**: Instala el driver ODBC o OLE DB para SAP HANA

### Error: "Login failed for user"

**Solución**: 
- Verifica las credenciales en `sp_addlinkedsrvlogin`
- Asegúrate de que el usuario tenga permisos en SAP HANA

### Error: "Timeout expired"

**Solución**:
- Verifica que la IP `10.10.100.12` sea accesible desde SQL Server
- Aumenta el timeout en las opciones del servidor vinculado
- Verifica firewall

### Error: "Invalid object name"

**Solución**:
- Verifica que `SAP_DATABASE` y `SAP_SCHEMA` en `.env` sean correctos
- Verifica que la base de datos exista en SAP HANA

## 📝 Verificar Configuración Actual

```sql
-- Ver todos los servidores vinculados
SELECT * FROM sys.servers WHERE is_linked = 1;

-- Ver detalles de un servidor específico
SELECT 
    name AS ServerName,
    product AS Product,
    provider AS Provider,
    data_source AS DataSource,
    catalog AS Catalog
FROM sys.servers
WHERE name = 'MYHANADB';

-- Ver mapeos de login
SELECT * FROM sys.linked_logins WHERE server_id = (SELECT server_id FROM sys.servers WHERE name = 'MYHANADB');
```

## 🔄 Eliminar y Recrear

Si necesitas eliminar y recrear el servidor vinculado:

```sql
-- Eliminar
EXEC sp_dropserver 'MYHANADB', 'droplogins';

-- Luego ejecuta el script de configuración nuevamente
```

## 💡 Tips

1. **Nombre del servidor vinculado**: Debe coincidir exactamente con `SAP_LINKED_SERVER` en tu `.env`
2. **IP y Puerto**: Si SAP HANA usa un puerto específico, inclúyelo: `10.10.100.12:30015`
3. **Prueba primero**: Siempre prueba con una consulta simple antes de usar en producción
4. **Permisos**: Asegúrate de que el usuario tenga permisos de lectura en las tablas de SAP

## 📞 Siguiente Paso

Una vez configurado el servidor vinculado, vuelve a ejecutar:

```bash
python scripts/test_sap_query.py --test client --sku "5-0012.9"
```

Deberías ver:
```
✅ Consulta exitosa!
📊 Resultado:
   ItemCode: 5-0012.9
   ItemName: ...
   U_IXX_PACK: X3
```

